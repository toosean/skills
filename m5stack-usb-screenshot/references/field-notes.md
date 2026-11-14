# Field notes: why the capture is shaped this way

These notes come from a 720x1280 ESP32-P4 Tab5 navigation display. Only the
generic technique and measurements are kept; the product code is not part of
this skill.

## Measured facts

| Item | Value |
|---|---|
| Logical frame | 720 x 1280 |
| Payload per frame | 720 x 1280 x 3 = 2,764,800 bytes |
| Strip size | 8 rows x 720 x 3 = 17,280 bytes |
| Firmware capture cap | 25 s |
| Host header / frame window | 8 s / 45 s |
| Normal render time | about 135-175 ms per frame |
| Rotation check | 0-degree and 180-degree captures were byte-identical |

The rotation result is the important one: because the canvas stays upright and
the 180-degree flip is applied only when writing the panel, the screenshot does
not need to know the current orientation.

## Failure 1: the 10-second timeout truncated the tail

The first implementation gave up after 10 s. On a healthy USB link the whole
2,764,800-byte frame arrived in time, but occasionally the link dropped to about
280 KB/s while BLE and the panel were active. A capture then stopped at
2,761,044 / 2,764,800 bytes; the host saved a PNG with a corrupted bottom edge.

Fix:

- write in 8-row blocks instead of one row per write;
- keep a static 17,280-byte strip buffer;
- raise the firmware cap to 25 s;
- widen the host read window to 30-45 s, longer than the firmware cap.

The host must be able to outwait the device; otherwise it reports a timeout while
the device is still sending.

## Failure 2: logs appeared inside the binary frame

SDK and BLE callbacks ran on other tasks and printed character by character.
During a capture, that output interleaved with the RGB888 payload, so the image
contained stray text bands and the byte count was still "correct" only by luck.

Fix:

```cpp
Serial.setDebugOutput(false);
esp_log_level_set("*", ESP_LOG_NONE);
```

Do this before starting BLE/Wi-Fi or any SDK that may log. If logs are needed,
move them to another UART or print only between captures.

## Difference from the first version

The first version read one row at a time with no timeout:

```cpp
uint8_t row[720 * 3];
for (int y = 0; y < height; ++y) {
    canvas.readRectRGB(0, y, width, 1, row);
    output.write(row, width * 3);
}
```

It worked, but it had no way to recover from a slow or stalled link, and it could
not tell the host why the frame stopped. The current version batches rows,
checks a deadline, and lets the host detect a short read from the declared
length.

## What to copy, what to change

Safe to copy:

- the 8-row block loop and static strip buffer;
- the 25 s abort without printing after the payload starts;
- `dtr=False; rts=False` before opening the serial port;
- the host's header-first, fixed-length read.

Must change per board:

- panel width/height and maximum width;
- USB VID/PID and whether the port is auto-detected;
- baud rate on UART bridges;
- memory budget and PSRAM availability;
- command prefix, if the project already uses another maintenance namespace.

## Limits

- The capture is the logical framebuffer, not an optical measurement of the
  panel. It cannot prove that the physical panel is flipped, that brightness is
  correct, or that colors are calibrated.
- A frame captured while another task is rendering can tear. Capture a stable
  frame from the render loop.
- RGB565 to RGB888 conversion can shift colors slightly; compare with a known
  solid-color screen rather than expecting exact desktop RGB values.
