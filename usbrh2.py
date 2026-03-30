from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import serial


DEFAULT_BAUDRATE = 9600
DEFAULT_TIMEOUT = 1.0
DEFAULT_PROMPT = ">"
DEFAULT_SERIAL_DIR = Path("/dev/serial/by-id")
DEFAULT_DEVICE_PATTERN = "usb-Strawberry_Linux_USBRH2_{serial}-if00"


class USBRH2Error(Exception):
    """Base exception for USBRH2 errors."""


class USBRH2ProtocolError(USBRH2Error):
    """Raised when the device returns an unexpected response."""


@dataclass(frozen=True)
class Measurement:
    temperature_c: float
    humidity_rh: float
    crc: str


class USBRH2:
    """Driver for the Strawberry Linux USBRH2 temperature/humidity module."""

    def __init__(
        self,
        device: str,
        *,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        prompt: str = DEFAULT_PROMPT,
    ) -> None:
        self.device = self.resolve_device_path(device)
        self.prompt = prompt
        self._serial = serial.Serial(
            port=self.device,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        self._clear_startup_noise()

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def __enter__(self) -> "USBRH2":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @classmethod
    def resolve_device_path(cls, device_or_serial: str) -> str:
        candidate = Path(device_or_serial)
        if candidate.exists():
            return str(candidate)

        serial_number = device_or_serial.upper()
        serial_dir = DEFAULT_SERIAL_DIR
        exact = serial_dir / DEFAULT_DEVICE_PATTERN.format(serial=serial_number)
        if exact.exists():
            return str(exact)

        matches = sorted(serial_dir.glob(f"usb-Strawberry_Linux_USBRH2_{serial_number}*"))
        if matches:
            return str(matches[0])

        raise FileNotFoundError(
            f"Device path not found for '{device_or_serial}'. "
            f"Tried '{candidate}' and '{exact}'."
        )

    def getrh(self) -> Measurement:
        response = self._send_command("getrh")
        return self._parse_measurement(response)

    def auto(self, interval_seconds: Optional[int]) -> str:
        command = "auto off" if interval_seconds is None else f"auto {interval_seconds}"
        return self._send_command(command)

    def read_measurement(self, timeout: Optional[float] = None) -> Measurement:
        wait_timeout = timeout
        if wait_timeout is None:
            wait_timeout = max(self._serial.timeout or DEFAULT_TIMEOUT, 0.1) + 2.0

        deadline = time.monotonic() + wait_timeout

        while time.monotonic() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue

            text = raw.decode("ascii", errors="ignore").strip()
            if not text or text == self.prompt:
                continue

            if text.startswith(self.prompt):
                text = text[len(self.prompt) :].strip()

            if not text:
                continue

            if text.startswith(":"):
                return self._parse_measurement(text)

        raise TimeoutError("No measurement received from device.")

    def led(self, channel: int, value: bool | str) -> str:
        if channel not in (1, 2):
            raise ValueError("LED channel must be 1 or 2.")

        led_value = self._normalize_led_value(value)
        return self._send_command(f"led{channel}={led_value}")

    def heater(self, enabled: bool) -> str:
        return self._send_command(f"heater {'on' if enabled else 'off'}")

    def status(self) -> str:
        return self._send_command("status")

    def list_state(self) -> str:
        return self._send_command("list")

    def echo(self, enabled: bool) -> str:
        return self._send_command(f"echo {'on' if enabled else 'off'}")

    def version(self) -> str:
        return self._send_command("ver")

    def serial_number(self) -> str:
        return self._send_command("serial")

    def help(self) -> str:
        return self._send_command("help")

    def _normalize_led_value(self, value: bool | str) -> str:
        if isinstance(value, bool):
            return "on" if value else "off"

        normalized = value.strip().lower()
        allowed = {"0", "1", "off", "on", "false", "true", "blink"}
        if normalized not in allowed:
            raise ValueError(f"Unsupported LED value: {value!r}")
        return normalized

    def _parse_measurement(self, response: str) -> Measurement:
        if not response.startswith(":"):
            raise USBRH2ProtocolError(f"Unexpected measurement response: {response!r}")

        fields = [part.strip() for part in response[1:].split(",")]
        if len(fields) != 3:
            raise USBRH2ProtocolError(f"Unexpected measurement payload: {response!r}")

        return Measurement(
            temperature_c=float(fields[0]),
            humidity_rh=float(fields[1]),
            crc=fields[2],
        )

    def _clear_startup_noise(self) -> None:
        time.sleep(0.1)
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()

    def _send_command(self, command: str) -> str:
        self._serial.write(f"{command}\r".encode("ascii"))
        self._serial.flush()
        return self._read_until_prompt(command)

    def _read_until_prompt(self, command: str) -> str:
        lines: list[str] = []
        started = False
        deadline = time.monotonic() + max(self._serial.timeout or DEFAULT_TIMEOUT, 0.1) + 2.0

        while time.monotonic() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue

            text = raw.decode("ascii", errors="ignore").strip()
            if not text:
                continue

            if text == self.prompt:
                break

            if text.startswith(self.prompt):
                text = text[len(self.prompt) :].strip()

            if not text:
                continue

            if text == command:
                started = True
                continue

            lines.append(text)
            started = True

        if not started:
            raise TimeoutError(f"No response received for command {command!r}.")

        if not lines:
            return ""

        return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read measurements from a USBRH2 device.")
    parser.add_argument(
        "device",
        help="Device path or serial number (for example /dev/ttyACM0 or E02A).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Measurement interval in seconds. Default: 10.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    auto_interval = max(1, int(round(args.interval)))
    measurement_timeout = max(auto_interval + 5.0, auto_interval * 1.5)

    with USBRH2(args.device) as sensor:
        print("# Datetime temperature[C] humidity[%]")
        sensor.auto(auto_interval)

        try:
            while True:
                measurement = sensor.read_measurement(timeout=measurement_timeout)
                timestamp = datetime.now(timezone.utc).astimezone().isoformat()
                print(
                    f"{timestamp} "
                    f"{measurement.temperature_c:.2f} "
                    f"{measurement.humidity_rh:.2f}"
                )
        finally:
            sensor.auto(None)


if __name__ == "__main__":
    main()
