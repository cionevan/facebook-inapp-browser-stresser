"""
ad_library_worker.py – Facebook Ad Library (Reklam Kütüphanesi) Özel CTA Çözücü ve Stresser Worker'ı.

Desteklenen URL Tipleri:
    https://www.facebook.com/ads/library/?id=938519609329015
    https://www.facebook.com/ads/library/?active_status=...&id=...

Ad Library sayfasına gidip reklam snapshot verisini ve CTA bağlantısını çözümler,
ardından hedef siteye referer ile giderek ziyareti gerçekleştirir.
"""

import asyncio
import re
import time
import urllib.parse
import uuid
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from reporter import Reporter, RequestResult
from user_agents import random_user_agent

stealth = Stealth()


def is_ad_library_url(url: str) -> bool:
    """Verilen URL'nin Facebook Ads Library (Reklam Kütüphanesi) olup olmadığını belirler."""
    return "facebook.com/ads/library" in url or "facebook.com/ad_library" in url


def extract_ad_library_details(html_content: str, target_id: str | None = None) -> dict[str, str | None]:
    """
    Facebook Ad Library HTML'indeki deeplink/snapshot JSON yapısından
    hedef linki (link_url) ve CTA etiketini çıkarır.
    target_id verilirse, doğrudan o ad_archive_id'ye ait snapshot bloğunu hedefler.
    """
    info = {"link_url": None, "cta_text": None, "title": None}

    # Eğer target_id varsa, önce tam olarak bu ID'nin geçtiği bloğu ara
    search_content = html_content
    if target_id:
        patterns = [
            f'"ad_archive_id":"{target_id}"',
            f'"ad_archive_id":{target_id}',
            f'"deeplink_ad_archive":{{"ad_archive_id":"{target_id}"',
            f'"id":"{target_id}"',
        ]
        for p in patterns:
            idx = html_content.find(p)
            if idx != -1:
                # Reklamın JSON snapshot bloğu ~3000 karakter civarındadır
                search_content = html_content[idx:idx + 4000]
                break

    # 1. link_url çıkarma (https://... formatında)
    m_link = re.search(r'"link_url":"(https?:[^"]+)"', search_content)
    if not m_link and search_content is not html_content:
        # ID bloğunda bulunamadıysa genel içerikten ara
        m_link = re.search(r'"link_url":"(https?:[^"]+)"', html_content)

    if m_link:
        raw_url = m_link.group(1).replace("\\/", "/")
        info["link_url"] = raw_url

    # 2. cta_text (Örn: "Şimdi alışveriş yap", "Daha fazla bilgi al")
    m_cta = re.search(r'"cta_text":"([^"]+)"', search_content)
    if not m_cta and search_content is not html_content:
        m_cta = re.search(r'"cta_text":"([^"]+)"', html_content)
    if m_cta:
        try:
            info["cta_text"] = m_cta.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
        except Exception:
            info["cta_text"] = m_cta.group(1)

    # 3. title (Başlık)
    m_title = re.search(r'"title":"([^"]+)"', search_content)
    if not m_title and search_content is not html_content:
        m_title = re.search(r'"title":"([^"]+)"', html_content)
    if m_title:
        try:
            info["title"] = m_title.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
        except Exception:
            info["title"] = m_title.group(1)

    return info


async def _safe_goto(page, url: str, timeout_ms: int, referer: str | None = None):
    """ERR_ABORTED, ERR_CONNECTION_CLOSED ve ani redirect durumlarında dayanıklı sayfa yükleme."""
    kwargs = {"wait_until": "domcontentloaded", "timeout": timeout_ms}
    if referer:
        kwargs["referer"] = referer
    try:
        return await page.goto(url, **kwargs)
    except PlaywrightError as exc:
        err_msg = str(exc)
        if any(tok in err_msg for tok in ("ERR_ABORTED", "ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED")):
            try:
                await asyncio.sleep(0.5)
                kwargs["wait_until"] = "commit"
                return await page.goto(url, **kwargs)
            except Exception:
                return None
        raise


def get_ad_id_from_url(url: str) -> str | None:
    """URL query'sinden id parametresini ayıklar."""
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        ids = qs.get("id")
        if ids:
            return ids[0]
    except Exception:
        pass
    return None


async def resolve_ad_library_cta(page, ad_lib_url: str, timeout_ms: int) -> str | None:
    """
    Ad Library sayfasını bekler ve reklamın hedef CTA bağlantısını çözer.
    """
    target_link = None
    target_id = get_ad_id_from_url(ad_lib_url)

    ignored_domains = (
        "facebook.com", "fb.com", "meta.com", "metastatus.com",
        "instagram.com", "whatsapp.com", "threads.net", "messenger.com"
    )

    # Sayfadaki dynamic relay graphql / challenge reload yüklenmesini bekle
    for attempt in range(15):
        await asyncio.sleep(1.0)

        # 1. HTML snapshot'ından link_url ara (hedef ID öncelikli)
        try:
            content = await page.content()
            details = extract_ad_library_details(content, target_id=target_id)
            if details.get("link_url"):
                target_link = details["link_url"]
                break
        except Exception:
            pass

        # 2. DOM'daki modal veya buton bağlantılarını kontrol et
        try:
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            for lk in links:
                if not lk:
                    continue
                parsed = urllib.parse.urlparse(lk)
                if parsed.scheme in ("http", "https") and parsed.hostname:
                    h = parsed.hostname.lower()
                    if not any(d in h for d in ignored_domains):
                        target_link = lk
                        break
        except Exception:
            pass

        if target_link:
            break

    return target_link


async def run_ad_library_worker(
    worker_id: int,
    config: dict[str, Any],
    reporter: Reporter,
    num_requests: int | None = None,
) -> None:
    """
    Facebook Ad Library hedefli worker.
    Her istekte:
      1. Oxylabs konut proxysi ile yeni oturum açar
      2. Ad Library sayfasına gider
      3. Reklamın CTA bağlantısını çözer
      4. Çözülen hedef bağlantıya Ad Library referer'ı ile gidip siteyi yükler.
    """
    target_url: str = config["target_url"]
    n_requests: int = num_requests if num_requests is not None else config["requests_per_worker"]
    timeout_ms: int = config["request_timeout"] * 1000
    headless: bool = config["headless"]

    host = config.get("oxylabs_host", "")
    port = config.get("oxylabs_port", 7777)
    raw_user = config.get("oxylabs_username", "")
    pwd = config.get("oxylabs_password", "")
    country = config.get("oxylabs_country", "").strip()
    proxy_server = f"http://{host}:{port}"
    is_smartproxy = "smartproxy" in host.lower() or raw_user.startswith("smart-")

    async with async_playwright() as pw:
        for _ in range(n_requests):
            sess_id = uuid.uuid4().hex[:8]
            if is_smartproxy:
                user_base = raw_user
                if country and "_area-" not in user_base and "-country-" not in user_base:
                    user_base = f"{user_base}_area-{country.upper()}"
                session_proxy_user = f"{user_base}_session-{sess_id}"
            else:
                c_lower = country.lower()
                base_user = f"customer-{raw_user}-cc-{c_lower}" if c_lower else f"customer-{raw_user}"
                session_proxy_user = f"{base_user}-sessid-{sess_id}"

            proxy_password = pwd
            ua = random_user_agent(mode="desktop")
            start = time.perf_counter()

            try:
                browser = await pw.chromium.launch(
                    headless=headless,
                    proxy={
                        "server": proxy_server,
                        "username": session_proxy_user,
                        "password": proxy_password,
                    },
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--window-size=1280,800",
                    ],
                )

                context = await browser.new_context(
                    user_agent=ua,
                    viewport={"width": 1280, "height": 800},
                    device_scale_factor=1,
                    is_mobile=False,
                    has_touch=False,
                    locale="tr-TR",
                    timezone_id="Europe/Istanbul",
                    java_script_enabled=True,
                    ignore_https_errors=True,
                )

                # Özel çerez varsa yükle
                cookies_data = config.get("cookies_data")
                if cookies_data:
                    try:
                        raw_list = cookies_data if isinstance(cookies_data, list) else cookies_data.get("cookies", [])
                        valid_cookies = []
                        for c in raw_list:
                            if isinstance(c, dict) and "name" in c and "value" in c:
                                ck = {
                                    "name": str(c["name"]),
                                    "value": str(c["value"]),
                                    "path": str(c.get("path", "/")),
                                    "domain": str(c.get("domain", ".facebook.com")),
                                }
                                valid_cookies.append(ck)
                        if valid_cookies:
                            await context.add_cookies(valid_cookies)
                    except Exception:
                        pass

                page = await context.new_page()
                await stealth.apply_stealth_async(page)

                # ─── AKILLI KOTA KORUMASI ───
                video_chunks_allowed = 0

                async def _smart_media_limiter(route):
                    nonlocal video_chunks_allowed
                    req = route.request
                    r_type = req.resource_type
                    url_lower = req.url.lower()

                    if r_type == "font" or any(ext in url_lower for ext in (".woff", ".woff2", ".ttf", ".otf", ".wav", ".mp3")):
                        await route.abort()
                        return

                    is_video = (
                        r_type == "media"
                        or any(ext in url_lower for ext in (".mp4", ".m4v", ".webm", ".m3u8", ".ts"))
                        or ("video" in url_lower and "fbcdn.net" in url_lower)
                    )
                    if is_video:
                        if video_chunks_allowed < 1:
                            video_chunks_allowed += 1
                            await route.continue_()
                            return
                        await route.abort()
                        return

                    await route.continue_()

                await page.route("**/*", _smart_media_limiter)

                # 1. Ad Library sayfasına git
                try:
                    await page.goto(target_url, wait_until="load", timeout=timeout_ms)
                except Exception:
                    await _safe_goto(page, target_url, timeout_ms)

                # 2. Reklamın CTA hedef linkini tespit et
                cta_destination = await resolve_ad_library_cta(page, target_url, timeout_ms)

                # 3. CTA hedef linkine tıkla / git
                if cta_destination:
                    response = await _safe_goto(page, cta_destination, timeout_ms, referer=target_url)
                else:
                    response = None

                # Networkün oturmasını bekle
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

                elapsed = time.perf_counter() - start
                status = response.status if response else (200 if cta_destination else 502)
                final_url = page.url

                reporter.record(
                    RequestResult(
                        worker_id=worker_id,
                        success=True,
                        status_code=status,
                        latency=elapsed,
                        final_url=final_url,
                        user_agent_short="AdLib/PC",
                    )
                )

            except PlaywrightError as exc:
                elapsed = time.perf_counter() - start
                reporter.record(
                    RequestResult(
                        worker_id=worker_id,
                        success=False,
                        status_code=None,
                        latency=elapsed,
                        final_url=target_url,
                        user_agent_short="AdLib/PC",
                        error=str(exc)[:120],
                    )
                )

            except Exception as exc:  # noqa: BLE001
                elapsed = time.perf_counter() - start
                reporter.record(
                    RequestResult(
                        worker_id=worker_id,
                        success=False,
                        status_code=None,
                        latency=elapsed,
                        final_url=target_url,
                        user_agent_short="AdLib/PC",
                        error=f"Hata: {str(exc)[:100]}",
                    )
                )

            finally:
                try:
                    await context.close()
                    await browser.close()
                except Exception:
                    pass

            await asyncio.sleep(0.3)
