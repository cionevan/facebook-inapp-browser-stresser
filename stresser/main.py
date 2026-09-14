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
    cfg["oxylabs_username"] = os.getenv("OXYLABS_USERNAME", cfg.get("oxylabs_username", ""))
    cfg["oxylabs_password"] = os.getenv("OXYLABS_PASSWORD", cfg.get("oxylabs_password", ""))
    cfg["oxylabs_country"] = os.getenv("OXYLABS_COUNTRY", cfg.get("oxylabs_country", "TR"))
    cfg["oxylabs_host"] = os.getenv("OXYLABS_HOST", cfg.get("oxylabs_host", "pr.oxylabs.io"))
    cfg["oxylabs_port"] = int(os.getenv("OXYLABS_PORT", cfg.get("oxylabs_port", 7777)))
    cfg["workers"] = int(os.getenv("WORKERS", cfg.get("workers", 5)))
    cfg["requests_per_worker"] = int(os.getenv("REQUESTS_PER_WORKER", cfg.get("requests_per_worker", 20)))
    cfg["request_timeout"] = int(os.getenv("REQUEST_TIMEOUT", cfg.get("request_timeout", 30)))
    cfg["headless"] = str(os.getenv("HEADLESS", cfg.get("headless", True))).lower() in ("true", "1", "yes")

    # Zorunlu alan kontrolü
    required = ["oxylabs_username", "oxylabs_password"]
    for key in required:
        val = cfg.get(key, "")
        if not val or val in ("kullanici_adiniz", "sifreniz", "your_username_here", "your_password_here"):
            print(f"[HATA] config.yaml veya ortam değişkenlerinde '{key}' tanımlanmalı.")
            print("Lütfen 'config.example.yaml' dosyasını 'config.yaml' olarak kopyalayıp bilgilerinizi girin.")
            sys.exit(1)

    return cfg


def ask_target_url(cfg: dict) -> None:
    """Başlangıçta hedef URL'yi kullanıcıdan sor, config'i güncelle."""
    default = cfg.get("target_url", "")
    if default and default != "http://localhost":
        prompt = f"  Hedef URL [{default}]: "
    else:
        prompt = "  Hedef URL: "

    while True:
        url = input(prompt).strip()
        if not url and default:
            url = default
        if url.startswith("http://") or url.startswith("https://"):
            cfg["target_url"] = url
            break
        print("  [!] Geçerli bir URL girin (http:// veya https:// ile başlamalı)")


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
                    print(f"  [OK] Cookie dosyası yüklendi: {path.name}")
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
    workers = cfg.get("workers", 5)
    total = cfg.get("total_requests", workers * cfg.get("requests_per_worker", 20))
    has_cookie = "Evet" if cfg.get("cookies_data") else "Hayır"
    sep = "─" * 50
    print(sep)
    print("  [>>]  Browser Stress Tester")
    print(sep)
    print(f"  Hedef      : {cfg['target_url']}")
    print(f"  Cookie     : {has_cookie}")
    print(f"  Worker     : {workers}")
    print(f"  Toplam     : {total}")
    print(f"  Proxy      : {cfg['oxylabs_host']}:{cfg['oxylabs_port']}")
    print(f"  Headless   : {cfg['headless']}")
    print(f"  Timeout    : {cfg['request_timeout']}s")
    print(sep)
    print()


async def main(cfg: dict) -> None:
    ask_target_url(cfg)
    ask_cookies(cfg)
    total_requests = ask_total_requests(cfg)
    print_banner(cfg)

    workers = cfg.get("workers", 5)
    reporter = Reporter(total_expected=total_requests)

    # İstekleri worker'lar arasında dengeli dağıt
    base = total_requests // workers
    rem = total_requests % workers
    worker_counts = [base + (1 if i < rem else 0) for i in range(workers)]

    tasks = [
        run_worker(
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
