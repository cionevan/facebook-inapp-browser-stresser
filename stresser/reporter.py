"""
reporter.py – Canlı istatistik takibi ve özet çıktısı.
"""

import time
import threading
from dataclasses import dataclass, field
from typing import List


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
        self._results: List[RequestResult] = []
        self._total_expected = total_expected
        self._start_time = time.time()
        self._log_file = log_file

    def record(self, result: RequestResult) -> None:
        """Bir isteğin sonucunu kaydet, konsola bas ve log dosyasına yaz."""
        with self._lock:
            self._results.append(result)
            count = len(self._results)

        status_icon = "[OK]" if result.success else "[FAIL]"
        status_str = str(result.status_code) if result.status_code else "ERR"

        if result.success:
            line = (
                f"[W{result.worker_id:02d}] {status_icon} {status_str} | "
                f"{result.latency:.2f}s | "
                f"UA: {result.user_agent_short} | "
                f"-> {result.final_url}"
            )
        else:
            line = (
                f"[W{result.worker_id:02d}] {status_icon} {status_str} | "
                f"{result.latency:.2f}s | "
                f"UA: {result.user_agent_short} | "
                f"ERR: {result.error}"
            )

        output_line = f"[{count:4d}/{self._total_expected}] {line}"
        print(output_line[:120], flush=True)

        # Log dosyasina tam halini kaydet
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {output_line}\n")
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

        sep = "=" * 50
        print(f"\n{sep}")
        print(f"  Toplam İstek  : {total}")
        print(f"  Başarılı      : {success} (%{100 * success // total if total else 0})")
        print(f"  Hata          : {errors}")
        print(f"  Ort. Latency  : {avg_lat:.3f}s")
        print(f"  Min Latency   : {min_lat:.3f}s")
        print(f"  Max Latency   : {max_lat:.3f}s")
        print(f"  Toplam Süre   : {elapsed:.1f}s")
        print(f"  İstek/saniye  : {rps:.2f}")
        print(sep)
