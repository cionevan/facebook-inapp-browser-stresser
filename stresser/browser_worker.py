"""
browser_worker.py – Tek bir worker'in calisma mantigi.

Evrensel Facebook Post & CTA Motoru:
  - Desteklenen URL'ler:
      * Reels (/reel/...)
      * Standart Gonderiler (/posts/..., /permalink.php, /story.php, photo.php vb.)
      * Videolar (/watch/..., /videos/...)
      * Dogrudan Linkler (l.facebook.com, normal website linkleri)
  
  - Desteklenen CTA (Eyleme Cagri) Butonlari:
      * Daha Fazla Bilgi Al (LEARN_MORE)
      * Simdi Alisveris Yap / Cumpara (SHOP_NOW)
      * Kaydol (SIGN_UP)
      * Bize Ulasin (CONTACT_US)
      * Basvur (APPLY_NOW)
      * Teklif Al / Siparis Ver (GET_QUOTE / ORDER_NOW)
      * Indir / Uygulamayi Yukle (DOWNLOAD / INSTALL_APP)
      * Gonderi metnindeki tum harici linkler
"""

import asyncio
import random
import re
import string
import time
import urllib.parse
import uuid
from typing import Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from playwright_stealth import Stealth

from reporter import Reporter, RequestResult
from user_agents import random_user_agent

stealth = Stealth()


def _ua_short(ua: str) -> str:
    """'FB/Android' veya 'FB/iOS' ve versiyon etiketini cikarir."""
    if "FBIOS" in ua:
        m = re.search(r"FBAV/([\d\.]+)", ua) or re.search(r"FBSV/([\d\.]+)", ua)
        ver = m.group(1)[:5] if m else "iOS"
        return f"FB/iOS ({ver})"
    elif "FB4A" in ua or "FB_IAB" in ua:
        m = re.search(r"FBAV/([\d\.]+)", ua)
        ver = m.group(1)[:5] if m else "Andr"
        return f"FB/Andr ({ver})"
    elif "Windows" in ua or "Macintosh" in ua:
        m = re.search(r"Chrome/([\d]+)", ua)
        return f"PC/Chr ({m.group(1)})" if m else "PC/Desk"
    m = re.search(r"Chrome/([\d]+)", ua)
    return f"Chrome/{m.group(1)}" if m else "Mobile/?"



def _is_facebook_post_url(url: str) -> bool:
    """Verilen adresin bir Facebook post/video/reel sayfasi olup olmadigini belirler."""
    if "l.facebook.com" in url or "facebook.com/flx/" in url:
        return False
    if not ("facebook.com" in url or "fb.watch" in url):
        return False
    indicators = [
        "/reel/",
        "/watch/",
        "/posts/",
        "/videos/",
        "story.php",
        "permalink.php",
        "/photo",
        "/share/",
        "fb.watch/",
    ]
    return any(ind in url for ind in indicators)


async def _resolve_cta_from_page(page, post_url: str, timeout_ms: int):
    """
    Facebook gonderisindeki her turlu CTA butonunu veya harici baglantiyi bekler, bulur ve tiklar.
    """
    target_link = None

    # Facebook SPA yapisinda butonlarin render edilmesi icin kisa araliklarla tara
    for _ in range(8):
        await asyncio.sleep(0.6)

        # 1. DOM'daki a[href] etiketlerini kontrol et
        try:
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            for lk in links:
                if not lk:
                    continue
                # l.facebook.com yönlendirmesi
                if "l.facebook.com" in lk and "u=" in lk:
                    u_param = urllib.parse.unquote(lk.split("u=")[1].split("&")[0])
                    if "facebook.com" not in u_param:
                        target_link = lk
                        break
                # Doğrudan harici web sitesi linki (örn: menoxintr.com vb.)
                parsed_lk = urllib.parse.urlparse(lk)
                if parsed_lk.scheme in ("http", "https") and parsed_lk.hostname:
                    h = parsed_lk.hostname.lower()
                    if "facebook.com" not in h and "fb.com" not in h and "instagram.com" not in h and "meta.com" not in h and "meta.ai" not in h:
                        target_link = lk
                        break
        except Exception:
            pass

        if target_link:
            break

        # 2. Sayfa icerigindeki relay/graphql json verisini kontrol et
        try:
            content = await page.content()
            matches = re.findall(r'"url":"(https:\\/\\/l\.facebook\.com\\/l\.php[^"]+)"', content)
            for m in matches:
                cta_raw = m.replace("\\/", "/").encode("utf-8").decode("unicode_escape")
                if "u=" in cta_raw:
                    target_dest = urllib.parse.unquote(cta_raw.split("u=")[1].split("&")[0])
                    if "facebook.com" not in target_dest:
                        target_link = cta_raw
                        break
        except Exception:
            pass

        if target_link:
            break

    # Bulunan harici CTA linkine post referer ile git
    if target_link:
        return await _safe_goto(page, target_link, timeout_ms, referer=post_url)


async def _safe_goto(page, url: str, timeout_ms: int, referer: str | None = None):
    """ERR_ABORTED ve ani redirect durumlarinda dayanikli sayfa yukleme."""
    kwargs = {"wait_until": "domcontentloaded", "timeout": timeout_ms}
    if referer:
        kwargs["referer"] = referer
    try:
        return await page.goto(url, **kwargs)
    except PlaywrightError as exc:
        err_msg = str(exc)
        if "ERR_ABORTED" in err_msg or "ERR_CONNECTION_RESET" in err_msg:
            # Hizli redirect veya reset durumunda commit modunda dene
            try:
                kwargs["wait_until"] = "commit"
                return await page.goto(url, **kwargs)
            except Exception:
                return None
        raise


async def run_worker(
    worker_id: int,
    config: dict[str, Any],
    reporter: Reporter,
    num_requests: int | None = None,
) -> None:
    """
    Belirlenen sayida istek atar.
    Her istek ayri bir browser context'te calisir (farkli UA + proxy session).
    """
    target_url: str = config["target_url"]
    n_requests: int = num_requests if num_requests is not None else config["requests_per_worker"]
    timeout_ms: int = config["request_timeout"] * 1000
    headless: bool = config["headless"]

    proxy_server = f"http://{config['oxylabs_host']}:{config['oxylabs_port']}"
    proxy_password = config["oxylabs_password"]

    # Ulke kodu varsa Oxylabs formatina cevir: customer-{user}-cc-{country}
    raw_user = config["oxylabs_username"]
    country = config.get("oxylabs_country", "").strip().lower()
    if country:
        proxy_username = f"customer-{raw_user}-cc-{country}"
    else:
        proxy_username = f"customer-{raw_user}"

    is_fb_post = _is_facebook_post_url(target_url)

    async with async_playwright() as pw:
        for _ in range(n_requests):
            cookies_data = config.get("cookies_data")
            is_desktop_cookie = bool(cookies_data)
            ua = random_user_agent(mode="desktop" if is_desktop_cookie else "mobile")
            sess_id = uuid.uuid4().hex[:8]
            session_proxy_user = f"{proxy_username}-sessid-{sess_id}"
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
                        "--window-size=1280,800" if is_desktop_cookie else "--window-size=393,852",
                    ],
                )

                if is_desktop_cookie:
                    headers = {
                        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Upgrade-Insecure-Requests": "1",
                    }
                    context = await browser.new_context(
                        user_agent=ua,
                        viewport={"width": 1280, "height": 800},
                        device_scale_factor=1,
                        is_mobile=False,
                        has_touch=False,
                        locale="tr-TR",
                        timezone_id="Europe/Istanbul",
                        java_script_enabled=True,
                        extra_http_headers=headers,
                    )
                else:
                    # Mobil Facebook In-App Browser ortami
                    is_ios = "iPhone" in ua
                    headers = {
                        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Upgrade-Insecure-Requests": "1",
                    }
                    if not is_ios:
                        headers["X-Requested-With"] = "com.facebook.katana"
                        headers["Sec-CH-UA-Mobile"] = "?1"
                        headers["Sec-CH-UA-Platform"] = '"Android"'

                    context = await browser.new_context(
                        user_agent=ua,
                        viewport={"width": 393, "height": 852},
                        device_scale_factor=3,
                        is_mobile=True,
                        has_touch=True,
                        locale="tr-TR",
                        timezone_id="Europe/Istanbul",
                        java_script_enabled=True,
                        extra_http_headers=headers,
                    )


                # Kullanici ozel Cookie JSON'i vermisse context'e yukle
                cookies_data = config.get("cookies_data")
                if cookies_data:
                    try:
                        raw_list = cookies_data if isinstance(cookies_data, list) else cookies_data.get("cookies", [])
                        valid_cookies = []
                        parsed_target = urllib.parse.urlparse(target_url)
                        default_domain = parsed_target.hostname or "localhost"

                        for c in raw_list:
                            if isinstance(c, dict) and "name" in c and "value" in c:
                                ck = {
                                    "name": str(c["name"]),
                                    "value": str(c["value"]),
                                    "path": str(c.get("path", "/")),
                                }
                                # Domain tanimla
                                domain_val = c.get("domain", "")
                                if domain_val:
                                    ck["domain"] = str(domain_val)
                                elif not c.get("url"):
                                    ck["domain"] = default_domain

                                if "url" in c and c["url"]:
                                    ck["url"] = str(c["url"])

                                if c.get("sameSite") in ("Strict", "Lax", "None"):
                                    ck["sameSite"] = c["sameSite"]
                                if "httpOnly" in c:
                                    ck["httpOnly"] = bool(c["httpOnly"])
                                if "secure" in c:
                                    ck["secure"] = bool(c["secure"])

                                valid_cookies.append(ck)

                        if valid_cookies:
                            await context.add_cookies(valid_cookies)
                    except Exception:
                        pass

                page = await context.new_page()
                await stealth.apply_stealth_async(page)

                # ─── DURUM 1: FACEBOOK GONDERISI (REEL / POST / VIDEO) ───────
                if is_fb_post:
                    await _safe_goto(page, target_url, timeout_ms)
                    await asyncio.sleep(2)

                    response = await _resolve_cta_from_page(page, target_url, timeout_ms)

                # ─── DURUM 2: DOGRUDAN BAGLANTI ──────────────────────────────
                else:
                    response = await _safe_goto(page, target_url, timeout_ms)

                # Facebook ara uyari ekrani (flx/warn) cikarsa butona bas
                if "flx/warn" in page.url or "facebook.com/l.php" in page.url:
                    try:
                        btn = page.locator("a.selected, a._42g-, a:has-text('Bağlantıya Git'), a:has-text('Devam'), a:has-text('Follow Link')").first
                        if await btn.is_visible(timeout=3000):
                            async with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
                                await btn.click()
                    except Exception:
                        pass

                # Hedef sitenin networkunun oturmasini bekle
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

                elapsed = time.perf_counter() - start
                status = response.status if response else 200
                final_url = page.url

                reporter.record(
                    RequestResult(
                        worker_id=worker_id,
                        success=True,
                        status_code=status,
                        latency=elapsed,
                        final_url=final_url,
                        user_agent_short=_ua_short(ua),
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
                        user_agent_short=_ua_short(ua),
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
                        user_agent_short=_ua_short(ua),
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
