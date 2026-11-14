#!/usr/bin/env python3
"""Capture a logical framebuffer from an M5Stack/ESP32 device over USB.

The device must answer a line command with a header and a fixed-length RGB888
payload. The default protocol is the one documented in SKILL.md:

    host -> ``NB_SCREEN\n``
    dev  -> ``NB_SCREEN <width> <height> <bytes>\n``
            ``<bytes>`` bytes of RGB888, row-major, top-left origin

Examples:
    python scripts/usb_screenshot.py --port COM7 --output shot.png
    python scripts/usb_screenshot.py --wait 15 --open
    python scripts/usb_screenshot.py --self-test
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import serial
from PIL import Image
from serial.tools import list_ports

REQUEST = b"NB_SCREEN\n"
ERROR_PREFIX = b"NB_ERROR"
ESP_USB_VID = 0x303A
HEADER_RE = re.compile(rb"^NB_SCREEN\s+(\d+)\s+(\d+)\s+(\d+)\s*$")
MAX_DIMENSION = 4096
MAX_FRAME_BYTES = 64 * 1024 * 1024
HEADER_TIMEOUT_S = 8.0
FRAME_TIMEOUT_S = 45.0
DEFAULT_DIR = Path("screenshots")
READ_CHUNK = 262144


def describe(port) -> str:
    return f"{port.device} ({port.description or 'unknown'})"


def candidate_ports() -> list:
    """Return serial ports that look like an Espressif native USB device."""
    found = []
    for port in list_ports.comports():
        hwid = (port.hwid or "").upper()
        if port.vid == ESP_USB_VID or f"{ESP_USB_VID:04X}:" in hwid:
            found.append(port)
    return found


def pick_port(explicit: str | None, wait_s: float) -> str:
    if explicit:
        return explicit
    deadline = time.monotonic() + max(wait_s, 0)
    while True:
        candidates = candidate_ports()
        if len(candidates) == 1:
            return candidates[0].device
        if len(candidates) > 1:
            listing = ", ".join(describe(port) for port in candidates)
            raise SystemExit(f"找到多个疑似设备串口，请用 --port 指定：{listing}")
        if time.monotonic() >= deadline:
            others = ", ".join(describe(port) for port in list_ports.comports()) or "无"
            raise SystemExit(
                "没有检测到 Espressif USB 串口（VID 303A）。"
                "请确认设备已开机并用 USB-C 数据线连接；"
                "如果是 CP210x/CH9102/CH340 等桥片，请用 --port 指定。"
                f"当前串口：{others}"
            )
        time.sleep(0.5)


def open_link(port_name: str) -> serial.Serial:
    link = serial.Serial(baudrate=115200, timeout=0.2, write_timeout=5)
    # Set DTR/RTS before open so the ESP32 auto-reset circuit is not triggered.
    link.dtr = False
    link.rts = False
    link.port = port_name
    link.open()
    link.reset_input_buffer()
    return link


def read_header(link, timeout: float) -> tuple[int, int, int]:
    deadline = time.monotonic() + timeout
    pending = b""
    while time.monotonic() < deadline:
        chunk = link.readline()
        if not chunk:
            continue
        pending += chunk
        while b"\n" in pending:
            raw, pending = pending.split(b"\n", 1)
            raw = raw.strip()
            if not raw:
                continue
            if raw.startswith(ERROR_PREFIX):
                raise RuntimeError(raw.decode("utf-8", "replace"))
            match = HEADER_RE.match(raw)
            if match is None:
                continue  # A log line; keep reading.
            width, height, length = (int(value) for value in match.groups())
            if width <= 0 or height <= 0 or width > MAX_DIMENSION or height > MAX_DIMENSION:
                raise RuntimeError(f"设备报告的尺寸异常：{width}x{height}")
            if length != width * height * 3 or length > MAX_FRAME_BYTES:
                raise RuntimeError(f"设备报告的帧长度异常：{length} 字节（{width}x{height}）")
            return width, height, length
    raise TimeoutError(
        "没有收到 NB_SCREEN 响应。请确认固件包含截图命令、命令名一致，"
        "并且串口没有被 PlatformIO/Arduino 监视器占用。"
    )


def read_payload(link, length: int, timeout: float) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + timeout
    while len(data) < length and time.monotonic() < deadline:
        data.extend(link.read(min(READ_CHUNK, length - len(data))))
    if len(data) != length:
        raise TimeoutError(
            f"画面传输不完整：{len(data)}/{length} 字节。"
            "请检查线缆，或增大固件端超时后重试。"
        )
    return bytes(data)


def capture(link, header_timeout: float = HEADER_TIMEOUT_S,
            frame_timeout: float = FRAME_TIMEOUT_S,
            expected: tuple[int, int] | None = None) -> Image.Image:
    link.write(REQUEST)
    width, height, length = read_header(link, header_timeout)
    if expected is not None and (width, height) != expected:
        raise RuntimeError(
            f"画面尺寸是 {width}x{height}，与 --expect {expected[0]}x{expected[1]} 不符"
        )
    data = read_payload(link, length, frame_timeout)
    return Image.frombytes("RGB", (width, height), data)


def save_png(image: Image.Image, target: Path,
             copy_latest: bool = False) -> tuple[Path, Path | None]:
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    latest = None
    if copy_latest:
        latest = target.parent / "latest.png"
        shutil.copyfile(target, latest)
    return target, latest


class _FakeLink:
    """In-memory stand-in for serial.Serial used by --self-test."""

    def __init__(self, payload: bytes):
        self._rx = io.BytesIO(payload)
        self.tx = bytearray()

    def write(self, data: bytes) -> int:
        self.tx.extend(data)
        return len(data)

    def readline(self) -> bytes:
        return self._rx.readline()

    def read(self, size: int) -> bytes:
        return self._rx.read(size)


def self_test() -> None:
    width, height = 4, 2
    pixels = bytes([
        255, 0, 0,   0, 255, 0,   0, 0, 255,   255, 255, 255,
        0, 0, 0,     128, 128, 128, 255, 255, 0, 0, 255, 255,
    ])
    link = _FakeLink(
        b"boot log line\n" + f"NB_SCREEN {width} {height} {len(pixels)}\n".encode() + pixels
    )
    image = capture(link, header_timeout=1, frame_timeout=1)
    assert link.tx == REQUEST, "self-test did not send the request"
    assert image.size == (width, height)
    assert image.getpixel((0, 0)) == (255, 0, 0)
    assert image.getpixel((2, 0)) == (0, 0, 255)
    assert image.getpixel((3, 1)) == (0, 255, 255)

    try:
        capture(_FakeLink(b"NB_ERROR unsupported_geometry\n"), header_timeout=1, frame_timeout=1)
    except RuntimeError as exc:
        assert "unsupported_geometry" in str(exc)
    else:
        raise AssertionError("self-test did not surface NB_ERROR")

    try:
        capture(_FakeLink(f"NB_SCREEN {width} {height} 12\n".encode()),
                header_timeout=1, frame_timeout=1)
    except RuntimeError as exc:
        assert "帧长度异常" in str(exc)
    else:
        raise AssertionError("self-test did not reject an impossible frame length")

    declared = width * height * 3
    try:
        capture(_FakeLink(f"NB_SCREEN {width} {height} {declared}\n".encode() + pixels[:6]),
                header_timeout=1, frame_timeout=0.5)
    except TimeoutError as exc:
        assert f"6/{declared}" in str(exc)
    else:
        raise AssertionError("self-test did not detect a short frame")

    with tempfile.TemporaryDirectory() as tmp:
        target, latest = save_png(image, Path(tmp) / "self-test.png", copy_latest=True)
        assert latest is not None and latest.exists()
        with Image.open(target) as reopened:
            reopened.load()
            assert reopened.size == (width, height)

    print("SELF_TEST_OK")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Capture an M5Stack/ESP32 logical framebuffer over USB and save a PNG."
    )
    parser.add_argument("--port", help="serial port such as COM7; auto-detected by default")
    parser.add_argument("--output", type=Path,
                        help="target PNG; defaults to screenshots/screen-<time>.png")
    parser.add_argument("--wait", type=float, default=0,
                        help="seconds to wait for the device to appear (default: 0)")
    parser.add_argument("--open", action="store_true",
                        help="open the PNG when done (Windows)")
    parser.add_argument("--expect", metavar="WxH",
                        help="reject a frame whose size differs, e.g. 720x1280")
    parser.add_argument("--self-test", action="store_true",
                        help="run the protocol/PNG self-test without a device")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    expected = None
    if args.expect:
        match = re.fullmatch(r"(\d+)[xX](\d+)", args.expect)
        if match is None:
            parser.error("--expect must look like 720x1280")
        expected = (int(match.group(1)), int(match.group(2)))

    port = pick_port(args.port, args.wait)
    try:
        link = open_link(port)
    except (serial.SerialException, OSError) as exc:
        raise SystemExit(
            f"无法打开串口 {port}：{exc}\n"
            "请关闭 PlatformIO/Arduino 串口监视器或其他占用该串口的程序后重试。"
        ) from None

    try:
        image = capture(link, expected=expected)
    except (RuntimeError, TimeoutError) as exc:
        raise SystemExit(str(exc)) from None
    except (serial.SerialException, OSError) as exc:
        raise SystemExit(f"串口 {port} 通信失败：{exc}") from None
    finally:
        link.close()

    target = args.output or DEFAULT_DIR / f"screen-{datetime.now():%Y%m%d-%H%M%S}.png"
    saved, latest = save_png(image, target, copy_latest=args.output is None)
    print(f"{image.size[0]}x{image.size[1]} -> {saved.resolve()}")
    if latest:
        print(f"latest: {latest.resolve()}")
    if args.open:
        if sys.platform == "win32":
            os.startfile(saved)  # noqa: S606 - local preview convenience
        else:
            print("--open is only implemented on Windows", file=sys.stderr)


if __name__ == "__main__":
    main()
