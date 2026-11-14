# Porting the USB framebuffer capture to another M5Stack board

The protocol and host script are board-independent. The firmware side depends on
four things: the USB transport, the amount of RAM, how rotation is applied, and
how fast bytes can leave the device.

## 1. Identify the USB transport

| Transport | Common VID:PID | Baud rate | Reset risk | Host detection |
|---|---|---|---|---|
| ESP32-P4/S3/S2/C3 native USB-Serial/JTAG | `303A:1001` | ignored | DTR/RTS can reset | automatic |
| Silicon Labs CP210x | `10C4:EA60` | must match | DTR/RTS can reset | pass `--port` |
| WCH CH9102 | `1A86:55D4` | must match | DTR/RTS can reset | pass `--port` |
| WCH CH340 | `1A86:7523` | must match | DTR/RTS can reset | pass `--port` |
| FTDI | `0403:6001` | must match | DTR/RTS can reset | pass `--port` |

The host script auto-detects only the Espressif native VID. For a bridge, either
pass `--port COM7` or extend `candidate_ports()` with the bridge VID.

On a bridge, the baud rate is real. A 320x240 frame is 230,400 bytes:

| Baud | Throughput (8N1) | 230,400 B | 2,764,800 B |
|---|---|---|---|
| 115200 | ~11.5 KB/s | ~20 s | ~240 s |
| 460800 | ~46 KB/s | ~5 s | ~60 s |
| 921600 | ~92 KB/s | ~2.5 s | ~30 s |

Use the highest rate the cable and bridge tolerate, and raise both timeouts.

## 2. Budget the RAM

| Panel | Pixels | Canvas RGB565 | 8-row strip | RGB888 payload |
|---|---|---|---|---|
| 720x1280 (Tab5) | 921,600 | 1,843,200 B | 17,280 B | 2,764,800 B |
| 320x240 (CoreS3/Core2) | 76,800 | 153,600 B | 7,680 B | 230,400 B |
| 240x135 (StickC Plus) | 32,400 | 64,800 B | 5,760 B | 97,200 B |
| 128x128 | 16,384 | 32,768 B | 3,072 B | 49,152 B |

The canvas must live in PSRAM on larger panels. The strip buffer must be static
(or a member), never a local array on the task stack. If PSRAM is unavailable,
reduce color depth or stream row by row from a smaller sprite.

## 3. Decide where rotation lives

Keep the canvas at logical rotation 0:

```cpp
M5Canvas canvas;
canvas.setPsram(true);
canvas.setColorDepth(16);
canvas.createSprite(width, height);
// ...
canvas.pushSprite(0, 0);
M5.Display.setRotation(upsideDown ? 2 : 0);
```

With this split, `readRectRGB()` always returns the same logical pixels, and a
0-degree and 180-degree capture are byte-identical. If the app draws directly to
`M5.Display`, the capture follows the panel rotation and this invariant is lost.

`NB_TOUCH`-style maintenance commands should also use logical coordinates, so
they keep working under rotation.

## 4. Calculate the timeout

```text
firmware_timeout > frame_bytes / worst_observed_throughput * 2
host_frame_timeout > firmware_timeout + several seconds
```

Field measurement on a 720x1280 Tab5: the native USB link occasionally dropped
to about 280 KB/s while BLE and the panel were active, so 2,764,800 bytes took
about 10 s. A 25 s firmware cap leaves roughly 2.5x headroom. The host waits
45 s, longer than the firmware cap, so it can report the short read instead of
timing out first.

On a 115200 bridge, 2.7 MB needs about 240 s. Either raise the baud rate or
accept a much longer timeout; do not reuse the Tab5 numbers unchanged.

## 5. Check the M5GFX API

| Need | API | Notes |
|---|---|---|
| Full-frame sprite | `M5Canvas` (`LGFX_Sprite`) | `createSprite(w, h)` after `setPsram`/`setColorDepth` |
| Read a strip | `readRectRGB(x, y, w, h, uint8_t*)` | Converts RGB565 to RGB888 |
| Read without conversion | `readRect(...)` | Convert RGB565 manually if `readRectRGB` is unavailable |
| Submit frame | `pushSprite(0, 0)` | Rotation is applied here |
| Panel size | `M5.Display.width()/height()` | Confirm it matches the canvas |

If the project uses LovyanGFX directly rather than M5Unified, the same methods
exist on `LGFX_Sprite`; replace the type and include path.

## 6. Handle logs, radios and watchdogs

- Call `Serial.setDebugOutput(false)` and `esp_log_level_set("*", ESP_LOG_NONE)`
  before enabling BLE/Wi-Fi or any SDK that logs from another task.
- If logs are required, send them on a different UART, or only between captures.
- BLE/Wi-Fi keep running on their own tasks, but the render loop is blocked for
  the duration of the capture. Touch and animation pause.
- A long busy loop can trip the task watchdog. If your board resets during a
  capture, feed the watchdog, add `delay(1)` in the write loop, or lower the
  timeout.
- Never read the canvas from a second task while the render loop is writing it.

## 7. Validation matrix

| Case | Expected |
|---|---|
| Native USB | host auto-detects; capture completes |
| Bridge | `--port` works; baud matches both ends |
| 0 degrees | logical PNG matches the UI |
| 180 degrees | PNG byte-identical to 0 degrees |
| Short/bad cable | host reports a short frame; firmware recovers |
| Three consecutive captures | no truncation, no drift |
| BLE/Wi-Fi active | capture still completes; no binary corruption |
| Mid-transfer unplug | host fails cleanly; device does not hang |
| Solid-color screen | sampled RGB matches within RGB565 quantization |
| `--expect` mismatch | host rejects before reading the payload |

## 8. Quick adaptation checklist

1. Record panel width/height and whether PSRAM is present.
2. Identify the USB VID/PID; decide auto-detect or `--port`.
3. Set the baud rate and both timeouts from the throughput table.
4. Keep the canvas at logical rotation; apply rotation on the panel.
5. Suppress logs that share the capture port.
6. Run `--self-test`, then one real capture, then the 0/180 pair.
