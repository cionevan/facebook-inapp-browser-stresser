"""
reporter.py – Canlı istatistik takibi ve özet çıktısı.
"""

import threading
import time
from dataclasses import dataclass


@dataclass
class RequestResult:
    worker_id: int
    success: bool
    status_code: int | None
    latency: float          # saniye
    final_url: str
    user_agent_short: str   # "Chrome/124" gibi kısa hali
    error: str | None = None


class Reporter:
    def __init__(self, total_expected: int, log_file: str = "stresser.log"):
        self._lock = threading.Lock()
        self._results: list[RequestResult] = []
        self._total_expected = total_expected
        self._start_time = time.time()
        self._log_file = log_file

    def record(self, result: RequestResult) -> None:
        """Bir isteğin sonucunu kaydet, konsola bas ve log dosyasına yaz."""
        with self._lock:
            self._results.append(result)
            count = len(self._results)

        # Renkli ve modern log ciktisi
        if result.success:
            tag = "\033[92m[OK]\033[0m"
            sc = f"\033[92m{result.status_code}\033[0m"
            dest = f"\033[94m-> {result.final_url}\033[0m"
        else:
            tag = "\033[91m[FAIL]\033[0m"
            sc = "\033[91mERR\033[0m"
            dest = f"\033[91mERR: {result.error}\033[0m"

        w_tag = f"\033[93mW{result.worker_id:02d}\033[0m"
        progress = f"\033[90m[{count:4d}/{self._total_expected}]\033[0m"
        time_str = f"{result.latency:.2f}s"

        colored_line = f"{progress} [{w_tag}] {tag} {sc} | {time_str} | UA: {result.user_agent_short} | {dest}"
        plain_line = f"[{count:4d}/{self._total_expected}] [W{result.worker_id:02d}] {'[OK]' if result.success else '[FAIL]'} {result.status_code or 'ERR'} | {time_str} | UA: {result.user_agent_short} | {result.final_url if result.success else result.error}"

        print(colored_line, flush=True)

        # Log dosyasina temiz halini kaydet
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {plain_line}\n")
        except Exception:
            pass

    def print_summary(self) -> None:
        """Bütün işler bitince özet tabloyu bas."""
        with self._lock:
            results = list(self._results)

        total = len(results)
        success = sum(1 for r in results if r.success)
        errors = total - success
        latencies = [r.latency for r in results]

        elapsed = time.time() - self._start_time
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        min_lat = min(latencies) if latencies else 0
        max_lat = max(latencies) if latencies else 0
        rps = total / elapsed if elapsed > 0 else 0
        rate = (100 * success // total) if total else 0

        print("\n\033[96m" + "━" * 58 + "\033[0m")
        print("  \033[1;97m📊  TEST TAMAMLANDI - PERFORMANS RAPORU  📊\033[0m")
        print("\033[96m" + "━" * 58 + "\033[0m")
        print(f"  \033[1mToplam Gönderilen : \033[93m{total}\033[0m")
        print(f"  \033[1mBaşarılı İstek    : \033[92m{success} (%{rate})\033[0m")
        print(f"  \033[1mHatalı / Kayan    : \033[91m{errors}\033[0m")
        print(f"  \033[1mOrtalama Gecikme  : \033[97m{avg_lat:.2f}s\033[0m")
        print(f"  \033[1mMin / Max Gecikme : \033[90m{min_lat:.2f}s / {max_lat:.2f}s\033[0m")
        print(f"  \033[1mToplam Geçen Süre : \033[95m{elapsed:.1f} saniye\033[0m")
        print(f"  \033[1mHız (İstek / sn)  : \033[92m{rps:.2f} req/s\033[0m")
        print("\033[96m" + "━" * 58 + "\033[0m\n")
