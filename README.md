# Linux System Monitor

A colorful terminal-based Linux system monitor built with Python.

This project monitors system resources such as CPU, memory, disk usage, and running processes through a clean command-line interface. It also supports a richer terminal UI for better readability.

---

## Features

- System-wide CPU usage monitoring
- Memory usage monitoring
- Disk usage monitoring
- Top processes by CPU
- Top processes by memory
- JSON output support
- Colorful terminal UI with `rich`
- Live monitoring mode

---

## Technologies Used

- Python
- psutil
- rich

---

## Installation

Clone the repository:

```bash
git clone https://github.com/murtcann/system-monitor-linux.git
cd system-monitor-linux
```

Install dependencies:

```bash
pip install -r requirements.txt
```

If you do not have a requirements file:

```bash
pip install psutil rich
```

---

## Usage

Run the monitor:

```bash
python3 monitor.py
```

Show more processes:

```bash
python3 monitor.py --top 10
```

Run in live mode:

```bash
python3 monitor.py --live
```

JSON output:

```bash
python3 monitor.py --json
```

---

## Example Output

The monitor displays:

- Timestamp
- CPU usage
- Memory usage
- Disk usage
- Top processes by CPU
- Top processes by memory

---

## Project Structure

```
system-monitor-linux/
├── monitor.py
├── README.md
└── requirements.txt
```

---

## Why I Built This Project

I built this project to improve my Python skills in:

- System programming
- Command-line tool development
- Process monitoring
- Terminal UI design

This project is a practical exercise for learning how Linux system resources can be analyzed programmatically.

---
## Help

Display command-line options:

python3 monitor.py --help
---

## Future Improvements

- Network usage monitoring
- Per-core CPU statistics
- Export logs to file
- Alerts for critical resource usage
- Better dashboard layout

---

## Author

Murtcan

GitHub: https://github.com/murtcann
## Demo

![System Monitor Demo](demo.gif)
