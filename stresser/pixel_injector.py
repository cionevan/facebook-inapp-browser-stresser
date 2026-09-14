"""
pixel_injector.py – Meta Pixel Event Injector (Yontem C Testi)

Kendi siteniz uzerinde Meta Pixel event basimini test etmek icin kullanilir.
Her istek: gercek Chromium tarayici + residential proxy IP + benzersiz fbclid + stealth modu.

Calistirilmasi:
    python pixel_injector.py
    python pixel_injector.py --config config.yaml
"""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

stealth = Stealth()

# ─── Desteklenen Meta Pixel Event Turleri ──────────────────────────────────────
EVENTS: dict[str, dict[str, Any]] = {
    "1": {
        "name": "PageView",
        "label": "Sayfa Goruntulemesi",
        "params": {},
    },
    "2": {
        "name": "ViewContent",
        "label": "Icerigi Goruntule (Urun Sayfasi)",
        "params": {"content_type": "product", "currency": "TRY"},
    },
    "3": {
        "name": "AddToCart",
        "label": "Sepete Ekle",
        "params": {"content_type": "product", "currency": "TRY", "value": 299.0},
    },
    "4": {
        "name": "InitiateCheckout",
        "label": "Odeme Baslatildi",
        "params": {"currency": "TRY", "num_items": 1},
    },
    "5": {
        "name": "Purchase",
        "label": "Satin Alma (En Guclu - Algoritmayi Besler)",
        "params": {"currency": "TRY", "value": 349.0},
    },
    "6": {
        "name": "Lead",
        "label": "Form Doldurma / Lead",
        "params": {"currency": "TRY", "value": 50.0},
    },
    "7": {
        "name": "CompleteRegistration",
        "label": "Kayit Tamamlandi",
        "params": {"currency": "TRY", "status": True},
    },
}


def load_config(path: str) -> dict[str, Any]:
    config_path = Path(path)
    cfg: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    cfg["use_proxy"] = str(os.getenv("USE_PROXY", cfg.get("use_proxy", True))).lower() in ("true", "1", "yes")
    cfg["oxylabs_username"] = os.getenv("OXYLABS_USERNAME", cfg.get("oxylabs_username", ""))
    cfg["oxylabs_password"] = os.getenv("OXYLABS_PASSWORD", cfg.get("oxylabs_password", ""))
    cfg["oxylabs_host"] = os.getenv("OXYLABS_HOST", cfg.get("oxylabs_host", "pr.oxylabs.io"))
    cfg["oxylabs_port"] = int(os.getenv("OXYLABS_PORT", cfg.get("oxylabs_port", 7777)))
    cfg["workers"] = int(cfg.get("workers", 3))
    cfg["request_timeout"] = int(cfg.get("request_timeout", 30))
    cfg["headless"] = str(cfg.get("headless", True)).lower() in ("true", "1", "yes")
    return cfg


def _gen_fbclid() -> str:
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    b64 = base64.urlsafe_b64encode(bytes.fromhex(raw)).decode().rstrip("=")
    aem = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()).decode().rstrip("=")[:22]
    return f"IwdGRjcAUU{b64[:24]}_aem_{aem}"


def _inject_fbclid(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs["fbclid"] = [_gen_fbclid()]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    return parsed._replace(query=new_query).geturl()


def _detect_pixel_id(html: str) -> str | None:
    """HTML icerisinden Meta Pixel ID'sini otomatik tespit eder."""
    patterns = [
        r"fbq\s*\(\s*['\"]init['\"]\s*,\s*['\"](\d+)['\"]",
        r"_fbq\.push\(\[.init.,\s*['\"](\d+)['\"]",
        r"facebook\.com/tr\?id=(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# INTERAKTIF WIZARD
# ──────────────────────────────────────────────────────────────────────────────

def ask_target_site(cfg: dict) -> str:
    default = cfg.get("target_url", "")
    # Dogrudan site URL'si iste (Facebook degil, hedef site)
    if "facebook.com" in default:
        default = ""
    print("  \033[90m(Facebook URL'si degil, pixel'in yuklendigi asil site girin)\033[0m")
    prompt = f"  \033[96m[?]\033[0m Hedef Site URL{f' [\033[93m{default}\033[0m]' if default else ''}: "
    while True:
        val = input(prompt).strip()
        if not val and default:
            return default
        if val.startswith(("http://", "https://")):
            return val
        print("  \033[91m[!]\033[0m Gecerli bir URL girin (http:// veya https:// ile baslamali)")


def ask_event(cfg: dict) -> tuple[str, dict[str, Any]]:
    print("\n  \033[1mHangi Meta Pixel eventi basilsin?\033[0m")
    for k, v in EVENTS.items():
        print(f"    \033[93m{k}\033[0m) {v['label']}  \033[90m→ fbq('track', '{v['name']}')\033[0m")
    print()
    while True:
        choice = input("  \033[96m[?]\033[0m Event secin [5]: ").strip() or "5"
        if choice in EVENTS:
            ev = EVENTS[choice]
            print(f"  \033[92m[OK]\033[0m Secilen event: \033[1m{ev['name']}\033[0m – {ev['label']}\n")
            return ev["name"], ev["params"]
        print("  \033[91m[!]\033[0m Gecersiz secim, 1-7 arasi bir sayi girin.")


def ask_proxy(cfg: dict) -> None:
    choice = input("  \033[96m[?]\033[0m Proxy kullanilsin mi? (\033[92mE\033[0m/h): ").strip().lower()
    if choice in ("h", "hayir", "n", "no"):
        cfg["use_proxy"] = False
        print("  \033[93m[i]\033[0m Proxy devre disi – dogrudan yerel internet kullanilacak.\n")
    else:
        cfg["use_proxy"] = True
        host = cfg.get("oxylabs_host", "proxy.smartproxy.net")
        port = cfg.get("oxylabs_port", 3120)
        print(f"  \033[92m[OK]\033[0m Proxy aktif: {host}:{port}\n")


def ask_count() -> int:
    while True:
        val = input("  \033[96m[?]\033[0m Kac adet event basilsin? [20]: ").strip() or "20"
        if val.isdigit() and int(val) > 0:
            return int(val)
        print("  \033[91m[!]\033[0m 0'dan buyuk bir tamsayi girin.")


def ask_workers() -> int:
    while True:
        val = input("  \033[96m[?]\033[0m Paralel worker sayisi [3]: ").strip() or "3"
        if val.isdigit() and int(val) > 0:
            return int(val)
        print("  \033[91m[!]\033[0m 0'dan buyuk bir tamsayi girin.")


def ask_value(event_name: str, params: dict[str, Any]) -> dict[str, Any]:
    if "value" not in params:
        return params
    p = dict(params)
    raw = input(f"  \033[96m[?]\033[0m {event_name} deger (TRY) [{p['value']}]: ").strip()
    if raw and raw.replace(".", "").isdigit():
        p["value"] = float(raw)
    return p


# ──────────────────────────────────────────────────────────────────────────────
# PIXEL INJECTION WORKER
# ──────────────────────────────────────────────────────────────────────────────

RESULTS: list[dict[str, Any]] = []
_lock = asyncio.Lock()


async def _inject_worker(
    worker_id: int,
    site_url: str,
    pixel_id: str,
    event_name: str,
    event_params: dict[str, Any],
    config: dict[str, Any],
    n: int,
    total: int,
    start_idx: int,
) -> None:
    host = config.get("oxylabs_host", "")
    port = config.get("oxylabs_port", 7777)
    raw_user = config.get("oxylabs_username", "")
    pwd = config.get("oxylabs_password", "")
    timeout_ms = config["request_timeout"] * 1000
    headless = config["headless"]
    is_smartproxy = "smartproxy" in host.lower() or raw_user.startswith("smart-")

    async with async_playwright() as pw:
        for i in range(n):
            req_num = start_idx + i
            sess_id = uuid.uuid4().hex[:8]
            start = time.perf_counter()
            success = False
            error_msg = ""
            fired_url = site_url

            try:
                if config.get("use_proxy", True):
                    if is_smartproxy:
                        user_base = raw_user
                        sess_user = f"{user_base}_session-{sess_id}"
                    else:
                        sess_user = f"customer-{raw_user}_cc-TR_session-{sess_id}"
                    proxy_settings: dict[str, Any] | None = {
                        "server": f"http://{host}:{port}",
                        "username": sess_user,
                        "password": pwd,
                    }
                else:
                    proxy_settings = None

                browser = await pw.chromium.launch(
                    headless=headless,
                    proxy=proxy_settings,  # type: ignore[arg-type]
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--window-size=1280,800",
                    ],
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    locale="tr-TR",
                    timezone_id="Europe/Istanbul",
                    ignore_https_errors=True,
                )
                await stealth.apply_stealth_async(context)
                page = await context.new_page()

                # fbclid ekle
                target = _inject_fbclid(site_url)
                fired_url = target

                # Gorselleri engelle, JS/HTML gecir (pixel icin gerekli)
                async def _block_heavy(route):  # type: ignore[no-untyped-def]
                    rt = route.request.resource_type
                    if rt in ("image", "media", "font", "stylesheet"):
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/*", _block_heavy)

                # Sayfaya git – fbq'nun yuklenmesi yeterli, tum render gerekmez
                try:
                    await page.goto(target, timeout=timeout_ms, wait_until="domcontentloaded")
                except Exception:
                    pass

                # fbq'nun window'a yuklenmesini bekle (max 8 sn)
                fbq_loaded = False
                try:
                    await page.wait_for_function("typeof window.fbq === 'function'", timeout=8000)
                    fbq_loaded = True
                except Exception:
                    pass

                if not fbq_loaded:
                    # Fallback: fbq stub inject edip pixel_id ile manual init yap
                    await page.evaluate(f"""() => {{
                        window.fbq = function(action, eventOrPixelId, ...args) {{
                            var img = new Image();
                            var params = args[0] || {{}};
                            img.src = 'https://www.facebook.com/tr/?id={pixel_id}&ev=' +
                                encodeURIComponent(typeof eventOrPixelId === 'string' ? eventOrPixelId : eventOrPixelId) +
                                '&dl=' + encodeURIComponent(window.location.href) +
                                '&rl=' + encodeURIComponent(document.referrer) +
                                '&if=false&ts=' + Date.now() +
                                '&sw=1280&sh=800&cd[currency]=' + (params.currency || 'TRY') +
                                '&cd[value]=' + (params.value || '') +
                                '&rand=' + Math.random().toString().slice(2);
                            document.head.appendChild(img);
                        }};
                        window._fbq = window.fbq;
                        fbq('init', '{pixel_id}');
                    }}""")

                # Pixel event'i basilacak parametreler
                params_js = json.dumps(event_params)

                # Event'i bas
                beacon_sent = await page.evaluate(f"""() => {{
                    try {{
                        fbq('track', '{event_name}', {params_js});
                        return true;
                    }} catch(e) {{
                        return false;
                    }}
                }}""")

                # Meta'nin pixel beacon'inin gitmesini bekle (~1-2 sn)
                await asyncio.sleep(1.5)

                elapsed = time.perf_counter() - start
                success = bool(beacon_sent)

                async with _lock:
                    RESULTS.append({"success": success, "elapsed": elapsed})

                status_icon = "\033[92m[OK]\033[0m" if success else "\033[91m[FAIL]\033[0m"
                fbq_src = "\033[92mSayfa fbq\033[0m" if fbq_loaded else "\033[93mInjected fbq\033[0m"
                print(
                    f"\033[90m[{req_num:4d}/{total}]\033[0m "
                    f"[\033[93mW{worker_id:02d}\033[0m] "
                    f"{status_icon} "
                    f"\033[1m{event_name}\033[0m | "
                    f"{elapsed:.2f}s | "
                    f"{fbq_src} | "
                    f"\033[94m{fired_url[:60]}...\033[0m"
                )

                await context.close()
                await browser.close()

            except Exception as e:
                elapsed = time.perf_counter() - start
                error_msg = str(e)[:80]
                async with _lock:
                    RESULTS.append({"success": False, "elapsed": elapsed})
                print(
                    f"\033[90m[{req_num:4d}/{total}]\033[0m "
                    f"[\033[93mW{worker_id:02d}\033[0m] "
                    f"\033[91m[FAIL]\033[0m {error_msg}"
                )


# ──────────────────────────────────────────────────────────────────────────────
# ANA AKIS
# ──────────────────────────────────────────────────────────────────────────────

async def main(cfg: dict[str, Any]) -> None:
    print("\n\033[1;96m" + "=" * 60)
    print("     META PIXEL EVENT INJECTOR  —  C YONTEMI TESTI")
    print("=" * 60 + "\033[0m\n")

    site_url = ask_target_site(cfg)

    # Pixel ID'yi otomatik tespit et
    print(f"\n  \033[90m[i] Pixel ID taranıyor: {site_url}\033[0m")
    try:
        import urllib.request as urlreq
        req = urlreq.Request(site_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlreq.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        detected_id = _detect_pixel_id(html)
        if detected_id:
            print(f"  \033[92m[OK]\033[0m Pixel ID otomatik bulundu: \033[1m{detected_id}\033[0m")
            pixel_id = detected_id
        else:
            print("  \033[93m[!]\033[0m Pixel ID HTML'de bulunamadi (dinamik yuklenebilir).")
            pixel_id = input("  \033[96m[?]\033[0m Pixel ID'yi manuel girin: ").strip()
    except Exception:
        print("  \033[93m[!]\033[0m Site acilamadi, Pixel ID manuel girilecek.")
        pixel_id = input("  \033[96m[?]\033[0m Pixel ID'yi manuel girin: ").strip()

    if not pixel_id:
        print("  \033[91m[!]\033[0m Pixel ID bos olamaz. Cikiliyor.")
        return

    event_name, event_params = ask_event(cfg)
    event_params = ask_value(event_name, event_params)
    ask_proxy(cfg)

    total = ask_count()
    workers = ask_workers()

    # Banner
    proxy_str = (
        f"\033[92m{cfg.get('oxylabs_host')}:{cfg.get('oxylabs_port')}\033[0m"
        if cfg.get("use_proxy", True)
        else "\033[93mDevre Disi (Yerel IP)\033[0m"
    )
    print("\n\033[95m" + "━" * 60 + "\033[0m")
    print("  \033[1;97m🎯  PIXEL INJECTION BASLATILIYOR  🎯\033[0m")
    print("\033[95m" + "━" * 60 + "\033[0m")
    print(f"  \033[1mHedef Site  :\033[0m \033[94m{site_url}\033[0m")
    print(f"  \033[1mPixel ID    :\033[0m \033[92m{pixel_id}\033[0m")
    print(f"  \033[1mEvent       :\033[0m \033[1m{event_name}\033[0m {json.dumps(event_params)}")
    print(f"  \033[1mToplam      :\033[0m {total} event")
    print(f"  \033[1mWorker      :\033[0m {workers} paralel")
    print(f"  \033[1mProxy       :\033[0m {proxy_str}")
    print("\033[95m" + "━" * 60 + "\033[0m\n")

    wall_start = time.time()
    base = total // workers
    rem = total % workers
    worker_counts = [base + (1 if i < rem else 0) for i in range(workers)]

    tasks = []
    idx = 1
    for wid, count in enumerate(worker_counts, start=1):
        if count > 0:
            tasks.append(
                _inject_worker(
                    worker_id=wid,
                    site_url=site_url,
                    pixel_id=pixel_id,
                    event_name=event_name,
                    event_params=event_params,
                    config=cfg,
                    n=count,
                    total=total,
                    start_idx=idx,
                )
            )
            idx += count

    await asyncio.gather(*tasks)

    elapsed = time.time() - wall_start
    ok = sum(1 for r in RESULTS if r["success"])
    fail = len(RESULTS) - ok
    avg = sum(r["elapsed"] for r in RESULTS) / len(RESULTS) if RESULTS else 0

    print("\n\033[96m" + "━" * 60 + "\033[0m")
    print("  \033[1;97m📊  INJECTION TAMAMLANDI\033[0m")
    print("\033[96m" + "━" * 60 + "\033[0m")
    print(f"  \033[1mToplamda Atilan   :\033[0m {len(RESULTS)} event")
    print(f"  \033[1mBasarili          :\033[0m \033[92m{ok} (%{int(100*ok/len(RESULTS)) if RESULTS else 0})\033[0m")
    print(f"  \033[1mBasarisiz         :\033[0m \033[91m{fail}\033[0m")
    print(f"  \033[1mOrtalama Sure     :\033[0m {avg:.2f}s")
    print(f"  \033[1mToplam Gecen Sure :\033[0m {elapsed:.1f}s")
    print("\033[96m" + "━" * 60 + "\033[0m")
    print(f"\n  \033[90m[i] Meta Ads Manager > Events Manager > {pixel_id} panelinden")
    print(f"      '{event_name}' event kaydini kontrol edebilirsiniz (~5-15 dakika gecikme).\033[0m\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meta Pixel Event Injector")
    parser.add_argument("--config", default="config.yaml", help="Config dosyasinin yolu")
    args = parser.parse_args()
    cfg = load_config(args.config)
    try:
        asyncio.run(main(cfg))
    except KeyboardInterrupt:
        print("\n  [!] Kullanici tarafindan durduruldu.")
