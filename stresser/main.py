"""
main.py – Stress tester giriş noktası.

Kullanım:
    python main.py
    python main.py --config config.yaml

config.yaml dosyasını düzenleyerek ayarları değiştirin.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

from ad_library_worker import is_ad_library_url, run_ad_library_worker
from browser_worker import run_worker
from reporter import Reporter


import os

def load_config(path: str) -> dict:
    config_path = Path(path)
    cfg = {}

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        # config.yaml yoksa config.example.yaml kontrol et
        example_path = config_path.parent / "config.example.yaml"
        if example_path.exists():
            with open(example_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

    # Ortam degiskenlerinden fallback al
    cfg["use_proxy"] = str(os.getenv("USE_PROXY", cfg.get("use_proxy", True))).lower() in ("true", "1", "yes")
    cfg["oxylabs_username"] = os.getenv("OXYLABS_USERNAME", cfg.get("oxylabs_username", ""))
    cfg["oxylabs_password"] = os.getenv("OXYLABS_PASSWORD", cfg.get("oxylabs_password", ""))
    cfg["oxylabs_country"] = os.getenv("OXYLABS_COUNTRY", cfg.get("oxylabs_country", "TR"))
    cfg["oxylabs_host"] = os.getenv("OXYLABS_HOST", cfg.get("oxylabs_host", "pr.oxylabs.io"))
    cfg["oxylabs_port"] = int(os.getenv("OXYLABS_PORT", cfg.get("oxylabs_port", 7777)))
    cfg["workers"] = int(os.getenv("WORKERS", cfg.get("workers", 10)))
    cfg["requests_per_worker"] = int(os.getenv("REQUESTS_PER_WORKER", cfg.get("requests_per_worker", 20)))
    cfg["request_timeout"] = int(os.getenv("REQUEST_TIMEOUT", cfg.get("request_timeout", 30)))
    cfg["headless"] = str(os.getenv("HEADLESS", cfg.get("headless", True))).lower() in ("true", "1", "yes")

    return cfg


def ask_proxy(cfg: dict) -> None:
    """Proxy kullanılıp kullanılmayacağını sor."""
    prompt = "  \033[96m[?]\033[0m Proxy kullanılsın mı? (\033[92mE\033[0m/h): "
    choice = input(prompt).strip().lower()
    if choice in ("h", "hayır", "n", "no"):
        cfg["use_proxy"] = False
        print("  \033[93m[i]\033[0m Proxy devre dışı bırakıldı (Doğrudan yerel internet kullanılacak).\n")
    else:
        cfg["use_proxy"] = True
        host = cfg.get("oxylabs_host", "proxy.smartproxy.net")
        port = cfg.get("oxylabs_port", 3120)
        print(f"  \033[92m[OK]\033[0m Proxy aktif: {host}:{port}\n")


def ask_target_url(cfg: dict) -> None:
    """Başlangıçta hedef URL'yi kullanıcıdan sor, config'i güncelle."""
    default = cfg.get("target_url", "")
    if default and default != "http://localhost":
        prompt = f"  \033[96m[?]\033[0m Hedef Gönderi / Reels URL [\033[93m{default[:45]}...\033[0m]: "
    else:
        prompt = "  \033[96m[?]\033[0m Hedef Gönderi / Reels URL: "

    while True:
        url = input(prompt).strip()
        if not url and default:
            url = default
        if url.startswith("http://") or url.startswith("https://"):
            cfg["target_url"] = url
            break
        print("  \033[91m[!]\033[0m Geçerli bir URL girin (http:// veya https:// ile başlamalı)")


def ask_total_requests(cfg: dict) -> int:
    """Kaç adet istek gönderileceğini kullanıcıdan sor."""
    default_total = cfg.get("workers", 5) * cfg.get("requests_per_worker", 20)
    prompt = f"  Toplam İstek Sayısı [{default_total}]: "

    while True:
        val = input(prompt).strip()
        if not val:
            total = default_total
            break
        if val.isdigit() and int(val) > 0:
            total = int(val)
            break
        print("  [!] Lütfen 0'dan büyük geçerli bir tamsayı girin")

    cfg["total_requests"] = total
    return total


import json

def ask_workers(cfg: dict) -> int:
    """Eşzamanlı çalışacak worker sayısını sor."""
    default = cfg.get("workers", 10)
    prompt = f"  Eşzamanlı Worker Sayısı (Paralel İşlem) [{default}]: "
    while True:
        val = input(prompt).strip()
        if not val:
            workers = default
            break
        if val.isdigit() and int(val) > 0:
            workers = int(val)
            break
        print("  [!] Lütfen 0'dan büyük geçerli bir tamsayı girin")
    cfg["workers"] = workers
    return workers


def ask_cookies(cfg: dict) -> None:
    """Kullanıcıya özel Cookie / Session JSON kullanmak isteyip istemediğini sor."""
    prompt = "  Cookie JSON kullanılsın mı? (e/H): "
    choice = input(prompt).strip().lower()
    if choice in ("e", "evet", "y", "yes"):
        while True:
            file_or_json = input("  Cookie JSON dosya yolu veya içeriği [cookies.json]: ").strip()
            if not file_or_json:
                file_or_json = "cookies.json"

            # Dosya yolu kontrolü
            path = Path(file_or_json)
            if path.exists() and path.is_file():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    cfg["cookies_data"] = data
                    count_str = f"({len(data)} hesap havuzu)" if isinstance(data, list) and data and isinstance(data[0], list) else ""
                    print(f"  [OK] Cookie dosyası yüklendi: {path.name} {count_str}")
                    break
                except Exception as e:
                    print(f"  [!] JSON dosyası okunamadı: {e}")
            else:
                # Doğrudan girilen JSON string kontrolü
                try:
                    data = json.loads(file_or_json)
                    cfg["cookies_data"] = data
                    print("  [OK] Cookie JSON içeriği başarıyla yüklendi.")
                    break
                except Exception:
                    print(f"  [!] Geçerli bir dosya bulunamadı veya JSON sözdizimi hatalı: '{file_or_json}'")
    else:
        cfg["cookies_data"] = None


def print_banner(cfg: dict) -> None:
    workers = cfg.get("workers", 10)
    total = cfg.get("total_requests", workers * cfg.get("requests_per_worker", 20))
    cookies = cfg.get("cookies_data")
    if isinstance(cookies, list) and cookies and isinstance(cookies[0], list):
        has_cookie = f"\033[92mEvet ({len(cookies)} hesap havuzu)\033[0m"
    elif cookies:
        has_cookie = "\033[92mEvet (Tekil Oturum)\033[0m"
    else:
        has_cookie = "\033[90mHayır (Anonim Mobil FB)\033[0m"

    proxy_str = f"\033[92m{cfg.get('oxylabs_host')}:{cfg.get('oxylabs_port')}\033[0m" if cfg.get("use_proxy", True) else "\033[93mDevre Dışı (Yerel IP)\033[0m"

    print("\n\033[95m" + "━" * 58 + "\033[0m")
    print("  \033[1;97m🚀  META ADS & REELS VIEW STRESS TESTER  🚀\033[0m")
    print("\033[95m" + "━" * 58 + "\033[0m")
    print(f"  \033[1m🎯 Hedef URL   :\033[0m \033[94m{cfg['target_url']}\033[0m")
    print(f"  \033[1m👥 Hesap/Cookie:\033[0m {has_cookie}")
    print(f"  \033[1m⚡ Worker Sayısı:\033[0m \033[93m{workers}\033[0m paralel işlem")
    print(f"  \033[1m📊 Toplam İstek:\033[0m \033[93m{total}\033[0m")
    print(f"  \033[1m🌐 Proxy Durumu:\033[0m {proxy_str}")
    print(f"  \033[1m👻 Headless Mod:\033[0m {'Aktif' if cfg['headless'] else 'Görünür Tarayıcı'}")
    print(f"  \033[1m⏱️  Zaman Aşımı :\033[0m {cfg['request_timeout']}s")
    print("\033[95m" + "━" * 58 + "\033[0m\n")


async def main(cfg: dict) -> None:
    print("\033[1;96m" + "=" * 58)
    print("       YAPILANDIRMA VE TEST BAŞLATMA SİHİRBAZI")
    print("=" * 58 + "\033[0m\n")

    ask_target_url(cfg)
    ask_proxy(cfg)
    ask_workers(cfg)
    total_requests = ask_total_requests(cfg)
    ask_cookies(cfg)
    print_banner(cfg)

    workers = cfg.get("workers", 10)
    reporter = Reporter(total_expected=total_requests)

    # İstekleri worker'lar arasında dengeli dağıt
    base = total_requests // workers
    rem = total_requests % workers
    worker_counts = [base + (1 if i < rem else 0) for i in range(workers)]

    worker_fn = run_ad_library_worker if is_ad_library_url(cfg["target_url"]) else run_worker

    tasks = [
        worker_fn(
            worker_id=i + 1,
            config=cfg,
            reporter=reporter,
            num_requests=worker_counts[i],
        )
        for i in range(workers)
        if worker_counts[i] > 0
    ]

    await asyncio.gather(*tasks)
    reporter.print_summary()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Browser Stress Tester")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Config dosyasının yolu (varsayılan: config.yaml)",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    try:
        asyncio.run(main(cfg))
    except KeyboardInterrupt:
        print("\n[!] Kullanıcı tarafından durduruldu.")
