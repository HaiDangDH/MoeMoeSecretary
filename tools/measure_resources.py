"""Đo RAM và CPU của MoeMoeSecretary.exe bằng psutil.

Dùng:
    python tools\\measure_resources.py                      # đo dist\\MoeMoeSecretary.exe 40 giây
    python tools\\measure_resources.py --seconds 60 --exe dist\\MoeMoeSecretary.exe
    python tools\\measure_resources.py --attach             # đo tiến trình đang chạy sẵn

Lưu ý: file --onefile của PyInstaller gồm 2 tiến trình (bộ khởi động + tiến trình Python
thật), nên công cụ này cộng cả hai để cho con số RAM đáng tin cậy.
Chờ vài giây đầu để nhân vật tải xong (lần đầu cần mạng) rồi mới tính "nghỉ" (idle).
"""
from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import time
from pathlib import Path

import psutil

LIMIT_MB = 1024  # yêu cầu: tuyệt đối dưới 1 GB


def tree(proc: psutil.Process) -> list[psutil.Process]:
    try:
        return [proc, *proc.children(recursive=True)]
    except psutil.NoSuchProcess:
        return []


def find_running(name: str) -> psutil.Process | None:
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() == name.lower():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=str(Path("dist") / "MoeMoeSecretary.exe"))
    ap.add_argument("--seconds", type=int, default=40)
    ap.add_argument("--warmup", type=int, default=15, help="giây bỏ qua đầu (tải dữ liệu)")
    ap.add_argument("--attach", action="store_true", help="đo tiến trình đang chạy thay vì mở mới")
    args = ap.parse_args()

    launched = None
    if args.attach:
        root = find_running("MoeMoeSecretary.exe")
        if root is None:
            print("Không thấy MoeMoeSecretary.exe đang chạy.")
            return 1
    else:
        exe = Path(args.exe)
        if not exe.exists():
            print(f"Không thấy {exe}. Hãy chạy build_exe.bat trước.")
            return 1
        launched = subprocess.Popen([str(exe)], cwd=str(exe.parent))
        root = psutil.Process(launched.pid)

    print(f"Đang đo {args.seconds}s (bỏ qua {args.warmup}s đầu)...")
    primed: dict[int, psutil.Process] = {}
    rss_all: list[float] = []
    rss_idle: list[float] = []
    cpu_idle: list[float] = []
    start = time.monotonic()
    try:
        while time.monotonic() - start < args.seconds:
            time.sleep(1.0)
            procs = tree(root)
            if not procs:
                print("Ứng dụng đã thoát.")
                break
            rss = cpu = 0.0
            for p in procs:
                try:
                    if p.pid not in primed:
                        p.cpu_percent(None)  # lần đầu để mồi bộ đếm
                        primed[p.pid] = p
                    cpu += primed[p.pid].cpu_percent(None)
                    rss += p.memory_info().rss
                except psutil.Error:
                    continue
            rss_mb = rss / 1024 / 1024
            rss_all.append(rss_mb)
            if time.monotonic() - start >= args.warmup:
                rss_idle.append(rss_mb)
                cpu_idle.append(cpu / (psutil.cpu_count() or 1) * 1.0)  # % tổng CPU máy
            print(f"  t={time.monotonic() - start:4.0f}s  RAM={rss_mb:7.1f} MB  CPU={cpu:5.1f}% (1 nhân)")
    finally:
        if launched is not None:
            for p in reversed(tree(root)):
                try:
                    p.terminate()
                except psutil.Error:
                    pass

    if not rss_all:
        return 1
    peak = max(rss_all)
    print("\n===== KẾT QUẢ =====")
    print(f"RAM đỉnh      : {peak:7.1f} MB   (giới hạn {LIMIT_MB} MB -> {'ĐẠT' if peak < LIMIT_MB else 'KHÔNG ĐẠT'})")
    if rss_idle:
        print(f"RAM khi nghỉ  : {statistics.mean(rss_idle):7.1f} MB (trung bình)   mục tiêu 80-200 MB")
        print(f"CPU khi nghỉ  : {statistics.mean(cpu_idle):7.2f} % (trung bình, trên tổng CPU máy)   mục tiêu 0-1 %")
    return 0 if peak < LIMIT_MB else 2


if __name__ == "__main__":
    sys.exit(main())
