#!/usr/bin/env python3
import argparse
import json
import logging
import time
from datetime import datetime, timezone

import psutil


def bytes_to_gb(value: float) -> float:
    return round(value / (1024 ** 3), 2)


def collect_system_stats() -> dict:
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "cpu_percent": cpu_percent,
        "memory": {
            "total_gb": bytes_to_gb(memory.total),
            "used_gb": bytes_to_gb(memory.used),
            "available_gb": bytes_to_gb(memory.available),
            "percent": memory.percent,
        },
        "disk_root": {
            "total_gb": bytes_to_gb(disk.total),
            "used_gb": bytes_to_gb(disk.used),
            "free_gb": bytes_to_gb(disk.free),
            "percent": disk.percent,
        },
    }


def collect_process_stats(top_n: int, sample_interval: float = 0.5) -> list[dict]:
    processes = []
    proc_map = {}

    for proc in psutil.process_iter(attrs=["pid", "name", "username"]):
        try:
            proc.cpu_percent(interval=None)
            proc_map[proc.pid] = proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    time.sleep(sample_interval)

    for pid, proc in proc_map.items():
        try:
            cpu_percent = proc.cpu_percent(interval=None)
            mem_rss = proc.memory_info().rss

            processes.append(
                {
                    "pid": pid,
                    "name": proc.info.get("name") or "",
                    "user": proc.info.get("username") or "",
                    "cpu_percent": round(cpu_percent, 1),
                    "mem_rss_gb": bytes_to_gb(mem_rss),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    processes_sorted = sorted(
        processes,
        key=lambda p: (p["cpu_percent"], p["mem_rss_gb"]),
        reverse=True,
    )

    return processes_sorted[:top_n]


def collect_stats(top_n: int, sample_interval: float = 0.5) -> dict:
    logging.debug("Collecting system stats")
    system_stats = collect_system_stats()

    logging.debug("Collecting process stats")
    top_processes = collect_process_stats(top_n=top_n, sample_interval=sample_interval)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": system_stats,
        "top_processes": top_processes,
    }


def print_human(data: dict) -> None:
    system = data["system"]
    memory = system["memory"]
    disk = system["disk_root"]

    print("Linux System Monitor")
    print("-" * 72)
    print(f"Timestamp (UTC): {data['timestamp']}")
    print(f"CPU Usage       : {system['cpu_percent']}%")
    print(
        f"Memory Usage    : {memory['percent']}% "
        f"({memory['used_gb']} / {memory['total_gb']} GB)"
    )
    print(
        f"Disk Usage (/)  : {disk['percent']}% "
        f"({disk['used_gb']} / {disk['total_gb']} GB)"
    )
    print("-" * 72)

    print("Top Processes")
    print(f"{'PID':>7}  {'CPU%':>6}  {'MEM(GB)':>8}  {'USER':<16}  NAME")
    for proc in data["top_processes"]:
        print(
            f"{proc['pid']:>7}  "
            f"{proc['cpu_percent']:>6.1f}  "
            f"{proc['mem_rss_gb']:>8.2f}  "
            f"{proc['user'][:16]:<16}  "
            f"{proc['name']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Linux System Monitor (clean and accurate version)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Show top N processes (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output stats as JSON",
    )
    parser.add_argument(
        "--log",
        default="WARNING",
        help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=0.5,
        help="CPU sampling interval for processes in seconds (default: 0.5)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.WARNING),
        format="%(levelname)s: %(message)s",
    )

    if args.top <= 0:
        raise SystemExit("--top must be greater than 0")

    if args.sample_interval <= 0:
        raise SystemExit("--sample-interval must be greater than 0")

    data = collect_stats(top_n=args.top, sample_interval=args.sample_interval)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_human(data)


if __name__ == "__main__":
    main()
