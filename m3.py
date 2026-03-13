#!/usr/bin/env python3
import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone

import psutil
from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


console = Console()


def bytes_to_gb(value: float) -> float:
    return round(value / (1024 ** 3), 2)


def pct_color(percent: float) -> str:
    if percent >= 90:
        return "bold red"
    if percent >= 75:
        return "bold yellow"
    return "bold green"


def mem_value_color(gb: float) -> str:
    if gb >= 2:
        return "bold red"
    if gb >= 0.5:
        return "bold yellow"
    return "bold green"


def make_bar(percent: float, width: int = 24) -> Text:
    filled = int((percent / 100) * width)
    empty = width - filled
    color = pct_color(percent)

    bar = Text()
    bar.append("█" * filled, style=color)
    bar.append("░" * empty, style="dim")
    return bar


def safe_mountpoint(partition) -> bool:
    try:
        if os.name == "nt":
            return True
        return os.path.exists(partition.mountpoint)
    except Exception:
        return False


def collect_system_stats() -> dict:
    cpu_percent = round(psutil.cpu_percent(interval=1), 1)
    vm = psutil.virtual_memory()

    disks = []
    seen = set()

    for part in psutil.disk_partitions(all=False):
        key = (part.device, part.mountpoint)
        if key in seen:
            continue
        seen.add(key)

        if not safe_mountpoint(part):
            continue

        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append(
                {
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": bytes_to_gb(usage.total),
                    "used_gb": bytes_to_gb(usage.used),
                    "free_gb": bytes_to_gb(usage.free),
                    "percent": round(usage.percent, 1),
                }
            )
        except PermissionError:
            continue
        except OSError:
            continue

    disks.sort(key = lambda d: d["percent"], reverse=True)

    return {
        "cpu_percent": cpu_percent,
        "memory": {
            "total_gb": bytes_to_gb(vm.total),
            "used_gb": bytes_to_gb(vm.used),
            "available_gb": bytes_to_gb(vm.available),
            "percent": round(vm.percent, 1),
        },
        "disks": disks,
    }


def prime_process_cpu_counters() -> dict[int, psutil.Process]:
    proc_map = {}
    for proc in psutil.process_iter(attrs=["pid", "name", "username"]):
        try:
            proc.cpu_percent(interval=None)
            proc_map[proc.pid] = proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return proc_map


def collect_process_stats(top_n: int, sample_interval: float = 0.5) -> tuple[list[dict], list[dict]]:
    proc_map = prime_process_cpu_counters()
    time.sleep(sample_interval)

    processes = []
    for pid, proc in proc_map.items():
        try:
            cpu_percent = round(proc.cpu_percent(interval=None), 1)
            mem_rss_gb = bytes_to_gb(proc.memory_info().rss)

            processes.append(
                {
                    "pid": pid,
                    "name": proc.info.get("name") or "",
                    "user": proc.info.get("username") or "",
                    "cpu_percent": cpu_percent,
                    "mem_rss_gb": mem_rss_gb,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    by_cpu = sorted(
        processes,
        key=lambda p: (p["cpu_percent"], p["mem_rss_gb"]),
        reverse=True,
    )[:top_n]

    by_mem = sorted(
        processes,
        key = lambda p: (p["mem_rss_gb"], p["cpu_percent"]),
        reverse=True,
    )[:top_n]

    return by_cpu, by_mem


def collect_stats(top_n: int, sample_interval: float) -> dict:
    system = collect_system_stats()
    top_cpu, top_mem = collect_process_stats(top_n=top_n, sample_interval=sample_interval)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": system,
        "top_processes_by_cpu": top_cpu,
        "top_processes_by_mem": top_mem,
    }


def build_summary_panel(data: dict) -> Panel:
    system = data["system"]
    mem = system["memory"]
    disks = system["disks"]
    worst_disk = disks[0] if disks else None

    text = Text()
    text.append("Timestamp (UTC): ", style="bold cyan")
    text.append(f"{data['timestamp']}\n", style="white")

    text.append("CPU Usage       : ", style="bold cyan")
    text.append(f"{system['cpu_percent']:>5.1f}%  ", style=pct_color(system["cpu_percent"]))
    text.append_text(make_bar(system["cpu_percent"]))
    text.append("\n")

    text.append("Memory Usage    : ", style="bold cyan")
    text.append(f"{mem['percent']:>5.1f}%  ", style=pct_color(mem["percent"]))
    text.append_text(make_bar(mem["percent"]))
    text.append(f"  ({mem['used_gb']} / {mem['total_gb']} GB)\n", style="white")

    if worst_disk:
        text.append(f"Disk Usage [{worst_disk['mountpoint']}] : ", style="bold cyan")
        text.append(f"{worst_disk['percent']:>5.1f}%  ", style=pct_color(worst_disk["percent"]))
        text.append_text(make_bar(worst_disk["percent"]))
        text.append(
            f"  ({worst_disk['used_gb']} / {worst_disk['total_gb']} GB)",
            style="white",
        )
    else:
        text.append("Disk Usage      : No accessible partitions", style="yellow")

    return Panel(
        text,
        title="[bold magenta]Linux System Monitor[/bold magenta]",
        border_style="bright_blue",
    )


def build_alerts_panel(data: dict) -> Panel:
    system = data["system"]
    mem = system["memory"]
    disks = system["disks"]

    alerts = []

    if system["cpu_percent"] >= 90:
        alerts.append("[bold red]High CPU usage detected[/bold red]")
    elif system["cpu_percent"] >= 75:
        alerts.append("[bold yellow]CPU usage is elevated[/bold yellow]")

    if mem["percent"] >= 90:
        alerts.append("[bold red]High memory usage detected[/bold red]")
    elif mem["percent"] >= 75:
        alerts.append("[bold yellow]Memory usage is elevated[/bold yellow]")

    disk_alerts = [d for d in disks if d["percent"] >= 90]
    if disk_alerts:
        for d in disk_alerts[:3]:
            alerts.append(
                f"[bold red]Disk nearly full:[/bold red] {d['mountpoint']} ({d['percent']}%)"
            )
    else:
        warning_disks = [d for d in disks if d["percent"] >= 75]
        for d in warning_disks[:3]:
            alerts.append(
                f"[bold yellow]Disk usage warning:[/bold yellow] {d['mountpoint']} ({d['percent']}%)"
            )

    if not alerts:
        alerts.append("[bold green]System looks healthy[/bold green]")

    body = "\n".join(f"• {a}" for a in alerts)
    return Panel(body, title="[bold]Alerts[/bold]", border_style="cyan")


def build_disk_table(disks: list[dict]) -> Table:
    table = Table(title="Disk Partitions", header_style="bold bright_cyan")
    table.add_column("Device", style="white")
    table.add_column("Mount", style="green")
    table.add_column("FS", style="yellow")
    table.add_column("Used %", justify="right")
    table.add_column("Used/Total (GB)", justify="right")

    for d in disks:
        style = pct_color(d["percent"])
        table.add_row(
            d["device"] or "-",
            d["mountpoint"],
            d["fstype"] or "-",
            f"[{style}]{d['percent']:.1f}[/{style}]",
            f"{d['used_gb']:.2f} / {d['total_gb']:.2f}",
        )
    return table


def build_process_table(processes: list[dict], title: str) -> Table:
    table = Table(title=title, header_style="bold bright_cyan")
    table.add_column("PID", justify="right", style="yellow")
    table.add_column("CPU%", justify="right")
    table.add_column("MEM(GB)", justify="right")
    table.add_column("USER", style="green")
    table.add_column("NAME", style="white")

    for p in processes:
        cpu_style = pct_color(p["cpu_percent"])
        mem_style = mem_value_color(p["mem_rss_gb"])
        table.add_row(
            str(p["pid"]),
            f"[{cpu_style}]{p['cpu_percent']:.1f}[/{cpu_style}]",
            f"[{mem_style}]{p['mem_rss_gb']:.2f}[/{mem_style}]",
            p["user"],
            p["name"],
        )
    return table


def build_layout(data: dict):
    summary = build_summary_panel(data)
    alerts = build_alerts_panel(data)
    disks = build_disk_table(data["system"]["disks"])
    cpu_table = build_process_table(data["top_processes_by_cpu"], "Top Processes by CPU")
    mem_table = build_process_table(data["top_processes_by_mem"], "Top Processes by Memory")

    return Group(
        summary,
        alerts,
        disks,
        cpu_table,
        mem_table,
        Align.center(Text("Press Ctrl+C to quit live mode", style="dim")) if False else Text(""),
    )


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2))


def run_once(top_n: int, sample_interval: float, as_json: bool) -> None:
    data = collect_stats(top_n=top_n, sample_interval=sample_interval)
    if as_json:
        print_json(data)
    else:
        console.print(build_layout(data))


def run_live(top_n: int, sample_interval: float, refresh_every: float) -> None:
    try:
        with Live(
            Text("Loading system monitor...", style="bold cyan"),
            console=console,
            screen=True,
            refresh_per_second=4,
        ) as live:
            while True:
                data = collect_stats(top_n=top_n, sample_interval=sample_interval)
                content = Group(
                    build_summary_panel(data),
                    build_alerts_panel(data),
                    build_disk_table(data["system"]["disks"]),
                    build_process_table(data["top_processes_by_cpu"], "Top Processes by CPU"),
                    build_process_table(data["top_processes_by_mem"], "Top Processes by Memory"),
                    Align.center(Text("Press Ctrl+C to quit", style="dim")),
                )
                live.update(content)
                time.sleep(refresh_every)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Stopped.[/bold yellow]")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="monitor.py",
        description="Linux System Monitor - Terminal-based system monitoring tool.",
        epilog="Example: python3 monitor.py --live --top 10",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top processes to display (default: 5)"
    )

    parser.add_argument(
        "--sample-interval",
        type=float,
        default=0.5,
        help="CPU sampling interval for per-process CPU measurement"
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live refreshing terminal dashboard"
    )

    parser.add_argument(
        "--refresh-every",
        type=float,
        default=2.0,
        help="Refresh period in live mode in seconds"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output system statistics in JSON format"
    )

    parser.add_argument(
        "--log",
        default="WARNING",
        help="Log level (DEBUG, INFO, WARNING, ERROR)"
    )

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.top <= 0:
        raise SystemExit("--top must be greater than 0")
    if args.sample_interval <= 0:
        raise SystemExit("--sample-interval must be greater than 0")
    if args.refresh_every <= 0:
        raise SystemExit("--refresh-every must be greater than 0")
    if args.live and args.json:
        raise SystemExit("--live and --json cannot be used together")


def main() -> None:
    args = parse_args()
    validate_args(args)

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.WARNING),
        format="%(levelname)s: %(message)s",
    )

    if args.live:
        run_live(
            top_n=args.top,
            sample_interval=args.sample_interval,
            refresh_every=args.refresh_every,
        )
    else:
        run_once(
            top_n=args.top,
            sample_interval=args.sample_interval,
            as_json=args.json,
        )


if __name__ == "__main__":
    main()
