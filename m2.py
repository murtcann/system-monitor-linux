#!/usr/bin/env python3
import argparse
import json
import logging
import time
from datetime import datetime, timezone

import psutil
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


console = Console()


def bytes_to_gb(value: float) -> float:
    return round(value / (1024 ** 3), 2)


def get_color_by_percent(percent: float) -> str:
    if percent >= 90:
        return "bold red"
    if percent >= 75:
        return "bold yellow"
    return "bold green"


def collect_system_stats() -> dict:
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "cpu_percent": round(cpu_percent, 1),
        "memory": {
            "total_gb": bytes_to_gb(memory.total),
            "used_gb": bytes_to_gb(memory.used),
            "available_gb": bytes_to_gb(memory.available),
            "percent": round(memory.percent, 1),
        },
        "disk_root": {
            "total_gb": bytes_to_gb(disk.total),
            "used_gb": bytes_to_gb(disk.used),
            "free_gb": bytes_to_gb(disk.free),
            "percent": round(disk.percent, 1),
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

    processes.sort(
        key=lambda p: (p["cpu_percent"], p["mem_rss_gb"]),
        reverse=True,
    )
    return processes[:top_n]


def collect_stats(top_n: int, sample_interval: float = 0.5) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": collect_system_stats(),
        "top_processes": collect_process_stats(top_n, sample_interval),
    }


def make_bar(percent: float, width: int = 28) -> str:
    filled = int((percent / 100) * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def render_system_panel(data: dict) -> None:
    system = data["system"]
    memory = system["memory"]
    disk = system["disk_root"]

    cpu_color = get_color_by_percent(system["cpu_percent"])
    mem_color = get_color_by_percent(memory["percent"])
    disk_color = get_color_by_percent(disk["percent"])

    content = Text()
    content.append("Timestamp (UTC): ", style="bold cyan")
    content.append(f"{data['timestamp']}\n", style="white")

    content.append("CPU Usage       : ", style="bold cyan")
    content.append(
        f"{system['cpu_percent']:>5.1f}%  ",
        style=cpu_color,
    )
    content.append(make_bar(system["cpu_percent"]), style=cpu_color)
    content.append("\n")

    content.append("Memory Usage    : ", style="bold cyan")
    content.append(
        f"{memory['percent']:>5.1f}%  ",
        style=mem_color,
    )
    content.append(make_bar(memory["percent"]), style=mem_color)
    content.append(
        f"  ({memory['used_gb']} / {memory['total_gb']} GB)\n",
        style="white",
    )

    content.append("Disk Usage (/)  : ", style="bold cyan")
    content.append(
        f"{disk['percent']:>5.1f}%  ",
        style=disk_color,
    )
    content.append(make_bar(disk["percent"]), style=disk_color)
    content.append(
        f"  ({disk['used_gb']} / {disk['total_gb']} GB)",
        style="white",
    )

    panel = Panel(
        content,
        title="[bold magenta]Linux System Monitor[/bold magenta]",
        border_style="bright_blue",
        expand=True,
    )
    console.print(panel)


def render_process_table(processes: list[dict]) -> None:
    table = Table(title="Top Processes", header_style="bold bright_cyan")
    table.add_column("PID", justify="right", style="yellow")
    table.add_column("CPU%", justify="right")
    table.add_column("MEM(GB)", justify="right")
    table.add_column("USER", style="green")
    table.add_column("NAME", style="white")

    for proc in processes:
        cpu_style = get_color_by_percent(proc["cpu_percent"])
        mem_style = "red" if proc["mem_rss_gb"] >= 1 else "yellow" if proc["mem_rss_gb"] >= 0.3 else "green"

        table.add_row(
            str(proc["pid"]),
            f"[{cpu_style}]{proc['cpu_percent']:.1f}[/{cpu_style}]",
            f"[{mem_style}]{proc['mem_rss_gb']:.2f}[/{mem_style}]",
            proc["user"],
            proc["name"],
        )

    console.print(table)


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Colorful Linux System Monitor")
    parser.add_argument("--top", type=int, default=5, help="Show top N processes")
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=0.5,
        help="CPU sample interval for processes",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--log",
        default="WARNING",
        help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
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
        print_json(data)
        return

    render_system_panel(data)
    console.print()
    render_process_table(data["top_processes"])


if __name__ == "__main__":
    main()
