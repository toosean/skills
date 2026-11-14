// Reference firmware-side implementation for M5Stack / ESP32-P4 + M5GFX.
//
// This file is not standalone. Copy the functions into the sketch that owns the
// full-frame canvas, then adapt the canvas type, dimensions and command prefix.
//
// Wire protocol
//   host -> "NB_SCREEN\n"
//   dev  -> "NB_SCREEN <width> <height> <bytes>\n"
//           <bytes> bytes of RGB888, row-major, top-left origin
//
// Rules
//   * capture from the render loop, never concurrently with a render task;
//   * keep the strip buffer static (8 * 720 * 3 = 17,280 bytes on Tab5);
//   * never print ASCII after the header until the payload is complete;
//   * a timeout aborts the frame and lets the host report a short read.

#include <Arduino.h>
#include <M5Unified.h>
#include <esp_log.h>

namespace screen_capture {

constexpr int kMaxWidth = 720;              // change for wider panels
constexpr int kBlockRows = 8;
constexpr uint32_t kTimeoutMs = 25000;
constexpr size_t kMaxCommandLength = 160;
constexpr const char* kCommand = "NB_SCREEN";

// 8 rows * 720 px * 3 bytes = 17,280 bytes. Static, never on the stack.
static uint8_t sRows[kBlockRows * kMaxWidth * 3];
static String sCommand;
static bool sDiscarding = false;

bool initCanvas(M5Canvas& canvas, int width, int height) {
    canvas.setPsram(true);
    canvas.setColorDepth(16);
    return canvas.createSprite(width, height) != nullptr;
}

void serialSetup() {
    Serial.setRxBufferSize(32768);  // must precede begin()
    Serial.begin(115200);
    Serial.setTimeout(100);
}

void suppressLogs() {
    // SDK/BLE callbacks may print character-by-character from other tasks. Any
    // such output would land in the middle of the binary frame.
    Serial.setDebugOutput(false);
    esp_log_level_set("*", ESP_LOG_NONE);
}

void captureDisplay(M5Canvas& canvas, Stream& output) {
    // The canvas is the logical, upright frame. Rotation, if any, is applied
    // later by pushSprite(), so this function always returns the same pixels.
    const int width = static_cast<int>(canvas.width());
    const int height = static_cast<int>(canvas.height());
    if (width <= 0 || height <= 0 || width > kMaxWidth) {
        output.println("NB_ERROR unsupported_geometry");
        return;
    }

    const size_t frameBytes = static_cast<size_t>(width) * static_cast<size_t>(height) * 3;
    output.printf("NB_SCREEN %d %d %u\n", width, height, static_cast<unsigned>(frameBytes));

    const uint32_t started = millis();
    for (int y = 0; y < height; y += kBlockRows) {
        const int rows = (height - y < kBlockRows) ? (height - y) : kBlockRows;
        const size_t total = static_cast<size_t>(width) * static_cast<size_t>(rows) * 3;
        canvas.readRectRGB(0, y, width, rows, sRows);

        size_t sent = 0;
        while (sent < total) {
            if (static_cast<uint32_t>(millis() - started) > kTimeoutMs) {
                // Do not print after the binary stream has started; the host
                // will detect the short frame from the declared length.
                return;
            }
            const size_t written = output.write(sRows + sent, total - sent);
            sent += written;
            if (written == 0) {
                delay(1);
            }
        }
    }
    output.flush();
}

void handleSerialLine(M5Canvas& canvas, const String& line) {
    if (line == kCommand) {
        captureDisplay(canvas, Serial);
    } else if (line == "NB_INFO") {
        // printInfo();  // project-specific status line
    }
}

void pollSerial(M5Canvas& canvas) {
    while (Serial.available()) {
        const char ch = static_cast<char>(Serial.read());
        if (ch == '\n') {
            sCommand.trim();
            if (!sCommand.isEmpty() && !sDiscarding) {
                handleSerialLine(canvas, sCommand);
            }
            sCommand = "";
            sDiscarding = false;
        } else if (ch == '\r' || sDiscarding) {
            continue;
        } else if (sCommand.length() < kMaxCommandLength) {
            sCommand += ch;
        } else {
            sCommand = "";
            sDiscarding = true;  // drop the rest of an oversized command
        }
    }
}

}  // namespace screen_capture

// Sketch skeleton
//
//   static M5Canvas canvas;
//
//   void setup() {
//       auto cfg = M5.config();
//       M5.begin(cfg);
//       screen_capture::serialSetup();
//       screen_capture::suppressLogs();
//       if (!screen_capture::initCanvas(canvas, M5.Display.width(), M5.Display.height())) {
//           Serial.println("NB_ERROR framebuffer_allocation_failed");
//           while (true) delay(1000);
//       }
//   }
//
//   void loop() {
//       M5.update();
//       screen_capture::pollSerial(canvas);  // capture the last completed frame
//       renderToCanvas(canvas);              // all drawing goes to the canvas
//       canvas.pushSprite(0, 0);             // rotation is applied here
//   }
