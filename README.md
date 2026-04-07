# USBRH2 Python Reader

This repository provides a small Python driver and CLI for the Strawberry Linux USBRH2 USB temperature and humidity module.

The implementation uses `pyserial` and follows the command table from the device manual. It supports:

- Connecting to the device over a serial port
- Resolving a Linux device path from a USBRH2 serial number such as `E02A`
- Executing device commands including `getrh`, `auto`, `led`, `heater`, `status`, `list`, `echo`, `ver`, `serial`, and `help`
- Printing measurement data periodically from a CLI entry point

## Requirements

- Python 3.10 or later
- Linux
- `pyserial`

Install the dependency with:

```bash
pip install -r requirements.txt
```

## Files

- [`usbrh2.py`](/Users/jsuzuki/program/usbrh2/usbrh2.py): USBRH2 driver class and CLI
- [`temperature_logger.py`](/Users/jsuzuki/program/usbrh2/temperature_logger.py): daily temperature logging CLI
- [`requirements.txt`](/Users/jsuzuki/program/usbrh2/requirements.txt): Python dependency list

## Connection Settings

The device is opened with the serial settings described in the manual:

- Baud rate: `9600`
- Data bits: `8`
- Parity: `none`
- Stop bits: `1`
- Flow control: `off`

## Device Path Resolution

The CLI accepts either:

- A direct device path, for example `/dev/ttyACM0`
- A USBRH2 serial number, for example `E02A`

When a serial number is given, the script tries to resolve the Linux symlink under `/dev/serial/by-id/`, for example:

```text
/dev/serial/by-id/usb-Strawberry_Linux_USBRH2_E02A-if00
```

## Usage

Run the script with either a path or a serial number:

```bash
python3 usbrh2.py /dev/serial/by-id/usb-Strawberry_Linux_USBRH2_E02A-if00
```

```bash
python3 usbrh2.py E02A
```

You can also change the measurement interval:

```bash
python3 usbrh2.py E02A --interval 30
```

## Daily Temperature Logging

To write temperature and humidity logs to daily files, run:

```bash
python3 temperature_logger.py E02A
```

This creates files named like:

```text
temperature_20260407.dat
```

You can customize the filename prefix:

```bash
python3 temperature_logger.py E02A --prefix room1
```

This creates files named like:

```text
room1_20260407.dat
```

You can also choose a different output directory:

```bash
python3 temperature_logger.py E02A --prefix room1 --output-dir ./logs
```

Each file contains:

```text
# Datetime temperature[C] humidity[%]
2026-04-07T12:00:00+09:00 24.96 39.32
2026-04-07T12:00:10+09:00 24.95 39.20
```

The logger switches to a new file automatically when the local date changes.

## Output Format

The CLI prints a header followed by space-separated values:

```text
# Datetime temperature[C] humidity[%]
2026-03-30T17:10:00+09:00 24.96 39.32
2026-03-30T17:10:10+09:00 24.95 39.20
```

Timestamps are emitted in ISO 8601 format with the local timezone offset.

## Auto Measurement Mode

The CLI uses the device `auto` command instead of sending `getrh` for every sample. This reduces command overhead and lets the device stream measurements at the requested interval.

The interval passed to `--interval` is converted to an integer number of seconds because the device `auto` command is second-based.

When the program exits, it attempts to send `auto off`.

## Using the Driver from Python

Example:

```python
from usbrh2 import USBRH2

with USBRH2("E02A") as sensor:
    print(sensor.serial_number())
    print(sensor.version())
    measurement = sensor.getrh()
    print(measurement.temperature_c, measurement.humidity_rh, measurement.crc)
```

To use streaming mode directly:

```python
from usbrh2 import USBRH2

with USBRH2("E02A") as sensor:
    sensor.auto(10)
    try:
        while True:
            measurement = sensor.read_measurement(timeout=20)
            print(measurement)
    finally:
        sensor.auto(None)
```

## Notes

- The device prompt is `>`.
- At connection time, the prompt may already have been emitted before the host starts reading.
- Measurement responses are expected in the form `:temperature,humidity,CRC`.
