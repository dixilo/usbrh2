from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TextIO

from usbrh2 import USBRH2


DEFAULT_INTERVAL = 10.0
DEFAULT_PREFIX = "temperature"
HEADER = "# Datetime temperature[C] humidity[%]"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log USBRH2 temperature data to daily files.")
    parser.add_argument(
        "device",
        help="Device path or serial number (for example /dev/ttyACM0 or E02A).",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"Output file prefix. Default: {DEFAULT_PREFIX}.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"Measurement interval in seconds. Default: {DEFAULT_INTERVAL}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for output files. Default: current directory.",
    )
    return parser.parse_args()


def current_local_time() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def build_log_path(output_dir: Path, prefix: str, now: datetime) -> Path:
    filename = f"{prefix}_{now.strftime('%Y%m%d')}.dat"
    return output_dir / filename


def open_log_file(path: Path) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not path.exists() or path.stat().st_size == 0
    handle = path.open("a", encoding="ascii")
    if is_new_file:
        handle.write(f"{HEADER}\n")
        handle.flush()
    return handle


def main() -> None:
    args = parse_args()
    auto_interval = max(1, int(round(args.interval)))
    measurement_timeout = max(auto_interval + 5.0, auto_interval * 1.5)
    output_dir = args.output_dir.resolve()

    current_handle: Optional[TextIO] = None
    current_path: Optional[Path] = None

    with USBRH2(args.device) as sensor:
        sensor.auto(auto_interval)
        try:
            while True:
                measurement = sensor.read_measurement(timeout=measurement_timeout)
                now = current_local_time()
                log_path = build_log_path(output_dir, args.prefix, now)

                if current_path != log_path:
                    if current_handle is not None:
                        current_handle.close()
                    current_handle = open_log_file(log_path)
                    current_path = log_path

                current_handle.write(
                    f"{now.isoformat()} "
                    f"{measurement.temperature_c:.2f} "
                    f"{measurement.humidity_rh:.2f}\n"
                )
                current_handle.flush()
        finally:
            if current_handle is not None:
                current_handle.close()
            sensor.auto(None)


if __name__ == "__main__":
    main()
