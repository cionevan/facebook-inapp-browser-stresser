"""
pixel_injector.py - Meta Pixel Event Injector (Yontem C)

Calistirma:
    python pixel_injector.py          # varsayilan: auto mod (hic soru yok)
    python pixel_injector.py --auto   # zorla auto
    python pixel_injector.py --manual # event secimi yapilir
    python pixel_injector.py --config config.yaml
"""

import argparse
import asyncio
import atexit
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

stealth = Stealth()

# --- Tam Donusum Hunisi (Auto Mod) -------------------------------------------
# Hizli ve dogal akis: toplam sure ~3-4 saniyeye indirildi.
AUTO_FUNNEL: list[dict[str, Any]] = [
    {"name": "PageView",         "params": {},                                                       "delay": 0.0},
    {"name": "ViewContent",      "params": {"content_type": "product", "currency": "TRY"},           "delay": 0.8},
    {"name": "AddToCart",        "params": {"content_type": "product", "currency": "TRY", "value": 299.0}, "delay": 1.0},
    {"name": "InitiateCheckout", "params": {"currency": "TRY", "num_items": 1},                     "delay": 0.8},
    {"name": "Purchase",         "params": {"currency": "TRY", "value": 349.0},                     "delay": 0.8},
]

# --- Tek Event Secenekleri (Manuel Mod) --------------------------------------
EVENTS: dict[str, dict[str, Any]] = {
    "1": {"name": "PageView",             "label": "Sayfa Goruntulemesi",                       "params": {}},
    "2": {"name": "ViewContent",          "label": "Icerigi Goruntule (Urun Sayfasi)",           "params": {"content_type": "product", "currency": "TRY"}},
    "3": {"name": "AddToCart",            "label": "Sepete Ekle",                                "params": {"content_type": "product", "currency": "TRY", "value": 299.0}},
    "4": {"name": "InitiateCheckout",     "label": "Odeme Baslatildi",                           "params": {"currency": "TRY", "num_items": 1}},
    "5": {"name": "Purchase",             "label": "Satin Alma (En Guclu)",                      "params": {"currency": "TRY", "value": 349.0}},
    "6": {"name": "Lead",                 "label": "Form Doldurma / Lead",                       "params": {"currency": "TRY", "value": 50.0}},
    "7": {"name": "CompleteRegistration", "label": "Kayit Tamamlandi",                           "params": {"currency": "TRY", "status": True}},
}


# --- Config ------------------------------------------------------------------

def load_config(path: str) -> dict[str, Any]:
    config_path = Path(path)
    cfg: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    cfg["use_proxy"]        = str(os.getenv("USE_PROXY", cfg.get("use_proxy", True))).lower() in ("true", "1", "yes")
    cfg["oxylabs_username"] = os.getenv("OXYLABS_USERNAME", cfg.get("oxylabs_username", ""))
    cfg["oxylabs_password"] = os.getenv("OXYLABS_PASSWORD", cfg.get("oxylabs_password", ""))
    cfg["oxylabs_host"]     = os.getenv("OXYLABS_HOST", cfg.get("oxylabs_host", "pr.oxylabs.io"))
    cfg["oxylabs_port"]     = int(os.getenv("OXYLABS_PORT", cfg.get("oxylabs_port", 7777)))
    cfg["request_timeout"]  = int(cfg.get("request_timeout", 30))
    cfg["headless"]         = str(cfg.get("headless", True)).lower() in ("true", "1", "yes")
    cfg["pixel_site_url"]   = cfg.get("pixel_site_url", "")
    cfg["pixel_count"]      = int(cfg.get("pixel_count", 20))
    cfg["pixel_workers"]    = int(cfg.get("pixel_workers", 5))
    cfg["pixel_mode"]       = cfg.get("pixel_mode", "auto")
    return cfg


# --- Yardimci ----------------------------------------------------------------

def _gen_fbclid() -> str:
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    b64 = base64.urlsafe_b64encode(bytes.fromhex(raw)).decode().rstrip("=")
    aem = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()).decode().rstrip("=")[:22]
    return f"IwdGRjcAUU{b64[:24]}_aem_{aem}"


def _inject_fbclid(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs["fbclid"] = [_gen_fbclid()]
    return parsed._replace(query=urllib.parse.urlencode(qs, doseq=True)).geturl()


def _detect_pixel_id(html: str) -> str | None:
    for pat in (
        r"fbq\s*\(\s*['\"]init[\'\"]\s*,\s*[\'\"](\d+)[\'\"]",
        r"facebook\.com/tr\?id=(\d+)",
    ):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


# --- Wizard ------------------------------------------------------------------

def ask_target_site(cfg: dict) -> str:
    default = cfg.get("pixel_site_url", "") or cfg.get("target_url", "")
    if "facebook.com" in default:
        default = ""
    print("  \033[90m(Pixel'in yuklendigi asil site girin, Facebook degil)\033[0m")
    prompt = f"  \033[96m[?]\033[0m Hedef Site URL{f' [\033[93m{default}\033[0m]' if default else ''}: "
    while True:
        val = input(prompt).strip()
        if not val and default:
            return default
        if val.startswith(("http://", "https://")):
            return val
        print("  \033[91m[!]\033[0m http:// veya https:// ile baslayan bir URL girin")


def ask_event() -> tuple[str, dict[str, Any]]:
    print("\n  \033[1mHangi Meta Pixel eventi basilsin?\033[0m")
    for k, v in EVENTS.items():
        star = " \033[93m★\033[0m" if k == "5" else ""
        print(f"    \033[93m{k}\033[0m) {v['label']}{star}  \033[90m-> fbq('track', '{v['name']}'  )\033[0m")
    print()
    while True:
        choice = input("  \033[96m[?]\033[0m Event secin [5]: ").strip() or "5"
        if choice in EVENTS:
            ev = EVENTS[choice]
            print(f"  \033[92m[OK]\033[0m {ev['name']} secildi\n")
            return ev["name"], dict(ev["params"])
        print("  \033[91m[!]\033[0m 1-7 arasi bir deger girin.")


def ask_proxy(cfg: dict) -> None:
    choice = input("  \033[96m[?]\033[0m Proxy kullanilsin mi? (\033[92mE\033[0m/h): ").strip().lower()
    if choice in ("h", "hayir", "n", "no"):
        cfg["use_proxy"] = False
        print("  \033[93m[i]\033[0m Proxy devre disi - yerel internet.\n")
    else:
        cfg["use_proxy"] = True
        print(f"  \033[92m[OK]\033[0m Proxy: {cfg.get('oxylabs_host')}:{cfg.get('oxylabs_port')}\n")


def ask_count(cfg: dict) -> int:
    label   = "Kac oturum" if cfg.get("pixel_mode") == "auto" else "Kac event"
    default = cfg.get("pixel_count", 20)
    while True:
        val = input(f"  \033[96m[?]\033[0m {label}? [{default}]: ").strip() or str(default)
        if val.isdigit() and int(val) > 0:
            return int(val)
        print("  \033[91m[!]\033[0m 0'dan buyuk bir tamsayi girin.")


def ask_workers(cfg: dict) -> int:
    default = cfg.get("pixel_workers", 5)
    while True:
        val = input(f"  \033[96m[?]\033[0m Paralel worker [{default}]: ").strip() or str(default)
        if val.isdigit() and int(val) > 0:
            return int(val)
        print("  \033[91m[!]\033[0m 0'dan buyuk bir tamsayi girin.")


def ask_value(event_name: str, params: dict[str, Any]) -> dict[str, Any]:
    if "value" not in params:
        return params
    p = dict(params)
    raw = input(f"  \033[96m[?]\033[0m {event_name} degeri (TRY) [{p['value']}]: ").strip()
    if raw and raw.replace(".", "").isdigit():
        p["value"] = float(raw)
    return p


# --- Worker ------------------------------------------------------------------

RESULTS: list[dict[str, Any]] = []
_lock = asyncio.Lock()


async def _fire_event(page: Any, pixel_id: str, event_name: str, params: dict[str, Any], fbq_loaded: bool) -> bool:
    """Tek bir fbq event'i sayfaya basar."""
    pid = pixel_id
    if not fbq_loaded:
        await page.evaluate(f"""() => {{
            if (typeof window._fbq_stub_init === 'undefined') {{
                window._fbq_stub_init = true;
                window.fbq = function(action, evOrId, ...args) {{
                    var p = args[0] || {{}};
                    var img = new Image();
                    img.src = 'https://www.facebook.com/tr/?id={pid}&ev='
                        + encodeURIComponent(typeof evOrId === 'string' ? evOrId : String(evOrId))
                        + '&dl=' + encodeURIComponent(window.location.href)
                        + '&rl=' + encodeURIComponent(document.referrer)
                        + '&if=false&ts=' + Date.now()
                        + '&sw=1280&sh=800'
                        + '&cd[currency]=' + (p.currency || 'TRY')
                        + '&cd[value]=' + (p.value || '')
                        + '&rand=' + Math.random().toString().slice(2);
                    document.head.appendChild(img);
                }};
                window._fbq = window.fbq;
                fbq('init', '{pid}');
            }}
        }}""")

    params_js = json.dumps(params)
    result: bool = await page.evaluate(f"""() => {{
        try {{ fbq('track', '{event_name}', {params_js}); return true; }}
        catch(e) {{ return false; }}
    }}""")
    return result


async def _inject_worker(
    worker_id: int,
    site_url: str,
    pixel_id: str,
    auto_mode: bool,
    single_event: str,
    single_params: dict[str, Any],
    config: dict[str, Any],
    n: int,
    total: int,
    start_idx: int,
) -> None:
    host          = config.get("oxylabs_host", "")
    port          = config.get("oxylabs_port", 7777)
    raw_user      = config.get("oxylabs_username", "")
    pwd           = config.get("oxylabs_password", "")
    timeout_ms    = config["request_timeout"] * 1000
    headless      = config["headless"]
    is_smartproxy = "smartproxy" in host.lower() or raw_user.startswith("smart-")

    async with async_playwright() as pw:
        for i in range(n):
            req_num = start_idx + i
            sess_id = uuid.uuid4().hex[:8]
            browser = None
            context = None
            t_start = time.perf_counter()
            success = False
            try:
                if config.get("use_proxy", True):
                    sess_user = (
                        f"{raw_user}_session-{sess_id}"
                        if is_smartproxy
                        else f"customer-{raw_user}_cc-TR_session-{sess_id}"
                    )
                    proxy_settings: dict[str, Any] | None = {
                        "server":   f"http://{host}:{port}",
                        "username": sess_user,
                        "password": pwd,
                    }
                else:
                    proxy_settings = None

                browser = await pw.chromium.launch(
                    headless=headless,
                    proxy=proxy_settings,  # type: ignore[arg-type]
                    args=["--no-sandbox", "--disable-dev-shm-usage",
                          "--disable-blink-features=AutomationControlled", "--window-size=1280,800"],
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    locale="tr-TR", timezone_id="Europe/Istanbul",
                    ignore_https_errors=True,
                )
                await stealth.apply_stealth_async(context)
                page = await context.new_page()
                target = _inject_fbclid(site_url)

                async def _blk(route):  # type: ignore[no-untyped-def]
                    if route.request.resource_type in ("image", "media", "font", "stylesheet"):
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/*", _blk)

                try:
                    await page.goto(target, timeout=timeout_ms, wait_until="domcontentloaded")
                except Exception:
                    pass

                fbq_loaded = False
                try:
                    await page.wait_for_function("typeof window.fbq === 'function'", timeout=8000)
                    fbq_loaded = True
                except Exception:
                    pass

                src = "\033[92mfbq\033[0m" if fbq_loaded else "\033[93mstub\033[0m"

                if auto_mode:
                    fired: list[str] = []
                    for step in AUTO_FUNNEL:
                        if step["delay"] > 0:
                            await asyncio.sleep(step["delay"])
                        ok = await _fire_event(page, pixel_id, step["name"], step["params"], fbq_loaded)
                        if ok:
                            fired.append(step["name"])
                    await asyncio.sleep(1.5)
                    elapsed = time.perf_counter() - t_start
                    success = len(fired) == len(AUTO_FUNNEL)
                    icon  = "\033[92m[OK]\033[0m" if success else "\033[93m[PART]\033[0m"
                    chain = " \033[90m->\033[0m ".join(f"\033[1m{e}\033[0m" for e in fired)
                    print(
                        f"\033[90m[{req_num:4d}/{total}]\033[0m "
                        f"[\033[93mW{worker_id:02d}\033[0m] "
                        f"{icon} {elapsed:.1f}s | {src} | {chain}"
                    )
                else:
                    ok = await _fire_event(page, pixel_id, single_event, single_params, fbq_loaded)
                    await asyncio.sleep(1.5)
                    elapsed = time.perf_counter() - t_start
                    success = bool(ok)
                    icon  = "\033[92m[OK]\033[0m" if success else "\033[91m[FAIL]\033[0m"
                    print(
                        f"\033[90m[{req_num:4d}/{total}]\033[0m "
                        f"[\033[93mW{worker_id:02d}\033[0m] "
                        f"{icon} \033[1m{single_event}\033[0m | {elapsed:.2f}s | {src}"
                    )

                async with _lock:
                    RESULTS.append({"success": success, "elapsed": elapsed})

            except Exception as exc:
                elapsed = time.perf_counter() - t_start
                async with _lock:
                    RESULTS.append({"success": False, "elapsed": elapsed})
                print(
                    f"\033[90m[{req_num:4d}/{total}]\033[0m "
                    f"[\033[93mW{worker_id:02d}\033[0m] "
                    f"\033[91m[FAIL]\033[0m {str(exc)[:80]}"
                )
            finally:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                if browser is not None:
                    try:
                        await browser.close()
                    except Exception:
                        pass


# --- Ana Akis ----------------------------------------------------------------

async def main(cfg: dict[str, Any]) -> None:
    auto_mode = cfg.get("pixel_mode", "auto") == "auto"

    print("\n\033[1;96m" + "=" * 62)
    mode_lbl = "\033[92mOTO FUNNEL\033[0m\033[1;96m" if auto_mode else "\033[93mMANUEL\033[0m\033[1;96m"
    print(f"     META PIXEL EVENT INJECTOR  --  {mode_lbl} MOD")
    print("=" * 62 + "\033[0m\n")

    site_url = ask_target_site(cfg)

    print(f"\n  \033[90m[i] Pixel ID taranıyor: {site_url}\033[0m")
    pixel_id = ""
    try:
        req = urllib.request.Request(site_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        detected = _detect_pixel_id(html)
        if detected:
            print(f"  \033[92m[OK]\033[0m Pixel ID: \033[1m{detected}\033[0m")
            pixel_id = detected
        else:
            print("  \033[93m[!]\033[0m Otomatik bulunamadi.")
    except Exception:
        print("  \033[93m[!]\033[0m Site erisilemiyor.")

    if not pixel_id:
        pixel_id = input("  \033[96m[?]\033[0m Pixel ID manuel girin: ").strip()
    if not pixel_id:
        print("  \033[91m[!]\033[0m Pixel ID bos olamaz.")
        return

    single_event: str = "Purchase"
    single_params: dict[str, Any] = {"currency": "TRY", "value": 349.0}
    if not auto_mode:
        single_event, single_params = ask_event()
        single_params = ask_value(single_event, single_params)

    ask_proxy(cfg)
    total   = ask_count(cfg)
    workers = ask_workers(cfg)

    proxy_str = (
        f"\033[92m{cfg.get('oxylabs_host')}:{cfg.get('oxylabs_port')}\033[0m"
        if cfg.get("use_proxy", True)
        else "\033[93mDevre Disi\033[0m"
    )

    print("\n\033[95m" + "=" * 62 + "\033[0m")
    print("  \033[1;97mPIXEL INJECTION BASLATILIYOR\033[0m")
    print("\033[95m" + "=" * 62 + "\033[0m")
    print(f"  \033[1mHedef Site  :\033[0m \033[94m{site_url}\033[0m")
    print(f"  \033[1mPixel ID    :\033[0m \033[92m{pixel_id}\033[0m")
    if auto_mode:
        funnel_str = " -> ".join(s["name"] for s in AUTO_FUNNEL)
        print("  \033[1mMod         :\033[0m \033[92mOTO FUNNEL\033[0m (tam donusum hunisi)")
        print(f"  \033[1mHuni        :\033[0m {funnel_str}")
        print(f"  \033[1mToplamda    :\033[0m {total * len(AUTO_FUNNEL)} event  ({len(AUTO_FUNNEL)} x {total} oturum)")
    else:
        print(f"  \033[1mEvent       :\033[0m \033[1m{single_event}\033[0m  {json.dumps(single_params)}")
        print(f"  \033[1mToplam      :\033[0m {total} event")
    print(f"  \033[1mWorker      :\033[0m {workers} paralel")
    print(f"  \033[1mProxy       :\033[0m {proxy_str}")
    print("\033[95m" + "=" * 62 + "\033[0m\n")

    wall_start = time.time()
    base  = total // workers
    rem   = total % workers
    wcnts = [base + (1 if i < rem else 0) for i in range(workers)]

    tasks = []
    idx = 1
    for wid, cnt in enumerate(wcnts, start=1):
        if cnt > 0:
            tasks.append(_inject_worker(
                worker_id=wid, site_url=site_url, pixel_id=pixel_id,
                auto_mode=auto_mode, single_event=single_event, single_params=single_params,
                config=cfg, n=cnt, total=total, start_idx=idx,
            ))
            idx += cnt

    await asyncio.gather(*tasks)

    elapsed     = time.time() - wall_start
    ok          = sum(1 for r in RESULTS if r["success"])
    fail        = len(RESULTS) - ok
    avg         = sum(r["elapsed"] for r in RESULTS) / len(RESULTS) if RESULTS else 0
    total_events = len(RESULTS) * len(AUTO_FUNNEL) if auto_mode else len(RESULTS)

    print("\n\033[96m" + "=" * 62 + "\033[0m")
    print("  \033[1;97mINJECTION TAMAMLANDI\033[0m")
    print("\033[96m" + "=" * 62 + "\033[0m")
    print(f"  \033[1mOturum        :\033[0m {len(RESULTS)}")
    print(f"  \033[1mToplamda Event:\033[0m \033[93m{total_events}\033[0m")
    print(f"  \033[1mBasarili      :\033[0m \033[92m{ok} (%{int(100*ok/len(RESULTS)) if RESULTS else 0})\033[0m")
    print(f"  \033[1mBasarisiz     :\033[0m \033[91m{fail}\033[0m")
    print(f"  \033[1mOrt. Sure     :\033[0m {avg:.1f}s / oturum")
    print(f"  \033[1mToplam Sure   :\033[0m {elapsed:.1f}s")
    print("\033[96m" + "=" * 62 + "\033[0m")
    ev_list = " / ".join(s["name"] for s in AUTO_FUNNEL) if auto_mode else single_event
    print(f"\n  \033[90m[i] Events Manager > Pixel {pixel_id}")
    print(f"      Kontrol: {ev_list}  (~5-15 dk gecikme normaldir)\033[0m\n")


def _cleanup_orphan_browsers() -> None:
    """Program kapandiginda veya Ctrl+C yapildiginda arkada asili kalan Chrome processlerini temizle."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/IM", "chrome-headless-shell.exe", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    except Exception:
        pass


atexit.register(_cleanup_orphan_browsers)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meta Pixel Event Injector")
    parser.add_argument("--config", default="config.yaml", help="Config dosyasinin yolu")
    parser.add_argument("--auto",   action="store_true",   help="Soru sormadan oto funnel")
    parser.add_argument("--manual", action="store_true",   help="Manuel mod")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.auto:
        cfg["pixel_mode"] = "auto"
    elif args.manual:
        cfg["pixel_mode"] = "manual"

    try:
        asyncio.run(main(cfg))
    except KeyboardInterrupt:
        print("\n  [!] Kullanici tarafindan durduruldu. Asili processler temizleniyor...")
    finally:
        _cleanup_orphan_browsers()
