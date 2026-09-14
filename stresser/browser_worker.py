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


def generate_dynamic_fbclid() -> str:
    """Gercekci, dinamik ve her seferinde benzersiz bir Meta AEM fbclid uretir."""
    chars = string.ascii_letters + string.digits + "-_"
    prefix = "IwdGRjcAUU"
    part1 = "".join(random.choices(chars, k=54))
    fixed_app = "AjExAHNydGMGYXBwX2lkCjY2Mjg1NjgzNzkAAR"
    part2 = "".join(random.choices(chars, k=42))
    aem = "".join(random.choices(chars, k=22))
    return f"{prefix}{part1}{fixed_app}{part2}_aem_{aem}"


def attach_dynamic_fbclid(target_url: str) -> str:
    """
    Hedef URL veya l.facebook.com baglantisina dinamik ve benzersiz bir fbclid ekler.
    Eger zaten varsa, yenisiyle gunceller.
    """
    try:
        parsed = urllib.parse.urlparse(target_url)
        new_fbclid = generate_dynamic_fbclid()

        # Eger bu bir l.facebook.com linki ise, u parametresinin icine ekle
        if "l.facebook.com" in parsed.netloc and "l.php" in parsed.path:
            qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if "u" in qs and qs["u"]:
                inner_url = qs["u"][0]
                inner_parsed = urllib.parse.urlparse(inner_url)
                inner_qs = urllib.parse.parse_qs(inner_parsed.query, keep_blank_values=True)
                inner_qs["fbclid"] = [new_fbclid]
                new_inner_query = urllib.parse.urlencode(inner_qs, doseq=True)
                new_inner_url = urllib.parse.urlunparse(inner_parsed._replace(query=new_inner_query))
                qs["u"] = [new_inner_url]
                new_query = urllib.parse.urlencode(qs, doseq=True)
                return urllib.parse.urlunparse(parsed._replace(query=new_query))

        # Eger normal bir websitesi ise, dogrudan fbclid ekle
        elif not any(k in parsed.netloc for k in ["facebook.com", "fb.watch"]):
            qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            qs["fbclid"] = [new_fbclid]
            new_query = urllib.parse.urlencode(qs, doseq=True)
            return urllib.parse.urlunparse(parsed._replace(query=new_query))

    except Exception:
        pass

    return target_url


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
    m = re.search(r"Chrome/([\d]+)", ua)
    return f"Chrome/{m.group(1)}" if m else "Mobile/?"


def _is_facebook_post_url(url: str) -> bool:
    """Verilen adresin bir Facebook post/video/reel sayfasi olup olmadigini belirler."""
    if "l.facebook.com" in url or "facebook.com/flx/" in url:
        return False
    indicators = [
        "facebook.com/reel/",
        "facebook.com/watch/",
        "facebook.com/posts/",
        "facebook.com/videos/",
        "facebook.com/story.php",
        "facebook.com/permalink.php",
        "facebook.com/photo",
        "facebook.com/share/",
        "fb.watch/",
    ]
    return any(ind in url for ind in indicators)


async def _resolve_cta_from_page(page, post_url: str, timeout_ms: int):
    """
    Facebook gonderisindeki her turlu CTA butonunu veya baglantisini bulur ve tiklar.
    """
    # 1. Yontem: Relay / GraphQL cache icindeki action_link'leri yakala (en hizli ve guvenilir)
    try:
        content = await page.content()
        # Tum action_link / url pattern'lerini topla
        matches = re.findall(r'"url":"(https:\\/\\/l\.facebook\.com\\/l\.php[^"]+)"', content)
        if matches:
            # Genellikle ilk veya ikinci link postun asil hedefidir
            cta_raw = matches[0].replace("\\/", "/").encode("utf-8").decode("unicode_escape")
            # Dinamik ve taze Meta fbclid parametresini linke tak
            cta_raw = attach_dynamic_fbclid(cta_raw)
            return await page.goto(
                cta_raw,
                wait_until="domcontentloaded",
                timeout=timeout_ms,
                referer=post_url,
            )
    except Exception:
        pass

    # 2. Yontem: DOM uzerindeki CTA butonlarina tikla (Daha Fazla Bilgi Al, Simdi Alisveris Yap vb.)
    cta_selectors = [
        "text=/Daha Fazla Bilgi/i",
        "text=/Learn More/i",
        "text=/Şimdi Alışveriş Yap/i",
        "text=/Shop Now/i",
        "text=/Cump/i",
        "text=/Kaydol/i",
        "text=/Sign Up/i",
        "text=/Bize Ulaşın/i",
        "text=/Contact Us/i",
        "text=/Başvur/i",
        "text=/Apply Now/i",
        "text=/İndir/i",
        "text=/Download/i",
        "text=/Teklif Al/i",
        "text=/Sipariş/i",
        "a[href*='l.facebook.com']",
    ]

    for sel in cta_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1000):
                # Buton link iceriyorsa href'e git, degilse tikla
                href = await el.get_attribute("href")
                if href and ("l.facebook.com" in href or not href.startswith("/")):
                    return await page.goto(href, wait_until="domcontentloaded", timeout=timeout_ms, referer=post_url)
                else:
                    async with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
                        await el.click()
                    return None
        except Exception:
            continue

    # 3. Yontem: Sayfadaki harici tum linkleri tara
    try:
        links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        for lk in links:
            if "l.facebook.com" in lk:
                return await page.goto(lk, wait_until="domcontentloaded", timeout=timeout_ms, referer=post_url)
    except Exception:
        pass

    return None


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
            ua = random_user_agent()
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
                        "--window-size=393,852",
                    ],
                )

                # Mobil ortam basliklari
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

                page = await context.new_page()
                await stealth.apply_stealth_async(page)

                # ─── DURUM 1: FACEBOOK GONDERISI (REEL / POST / VIDEO) ───────
                if is_fb_post:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    await asyncio.sleep(2)

                    response = await _resolve_cta_from_page(page, target_url, timeout_ms)

                # ─── DURUM 2: DOGRUDAN BAGLANTI ──────────────────────────────
                else:
                    direct_url = attach_dynamic_fbclid(target_url)
                    response = await page.goto(
                        direct_url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )

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
