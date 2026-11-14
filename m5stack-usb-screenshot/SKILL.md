---
name: m5stack-usb-screenshot
description: 通过 USB 维护命令从 M5Stack Tab5 / ESP32-P4 等 Arduino 设备抓取逻辑帧缓冲并保存为 PNG，包含固件端命令、主机端 Python 工具、超时与排错。Use when adding a reproducible framebuffer screenshot command to an M5Stack/ESP32 firmware, or capturing device screens over USB for docs and E2E tests.
disable-model-invocation: true
---

# M5Stack USB 帧缓冲截图

通过设备已有的整帧 canvas 和 USB 串口维护通道抓取屏幕，不在 PC 端重建 UI，也不依赖摄像头。

## 适用范围

适合：

- M5Stack Tab5、CoreS3 等有整帧 canvas（PSRAM）的 Arduino/M5GFX 工程；
- 需要文档配图、E2E 回归、UI 评审，且希望截图与屏幕旋转无关；
- 设备已经通过 USB-CDC 或 UART 暴露维护命令。

不适合：

- 固件只直接写面板、没有可读的整帧缓冲；
- 板子没有余量再分配整帧或行缓冲；
- 串口被业务日志或高频数据占满，无法插入带长度头的二进制传输。

## 架构

```text
render -> canvas (PSRAM, RGB565) -> pushSprite -> panel
                    |
                    +-- readRectRGB -> USB -> host -> PNG
```

三条不变量：

1. 渲染只写逻辑正向 canvas；0°/180° 在 `pushSprite` 写面板时应用。截图读 canvas，所以两种方向字节一致。
2. 控制面是 ASCII 行，数据面是定长二进制；先发头行，主机按长度读，绝不靠分隔符猜结束。
3. 截图期间关闭调试日志；截图只从渲染主循环发起，不和另一个任务并发读 canvas。

## 固件端实现

完整的可复制代码见 `references/firmware_capture.cpp`。下面只列关键步骤。

### 1. 用一整帧 canvas 作为唯一真源

```cpp
static M5Canvas canvas;

bool initCanvas() {
    canvas.setPsram(true);
    canvas.setColorDepth(16);
    return canvas.createSprite(M5.Display.width(), M5.Display.height()) != nullptr;
}
```

所有绘制都进 `canvas`，提交时 `canvas.pushSprite(0, 0)`。不要在绘制函数里直接写 `M5.Display`，否则截图会受旋转影响。

### 2. 串口先开足够大的接收缓冲

```cpp
Serial.setRxBufferSize(32768);   // 必须在 begin() 之前
Serial.begin(115200);
Serial.setTimeout(100);
```

USB-CDC 会忽略波特率；UART 桥片则必须让两端一致。

### 3. 用行缓冲解析命令

```cpp
static String command;

void serialCommands() {
    while (Serial.available()) {
        char ch = Serial.read();
        if (ch == '\n') {
            command.trim();
            if (command == "NB_SCREEN") captureDisplay(canvas, Serial);
            else if (command == "NB_INFO") printInfo();
            command = "";
        } else if (command.length() < 160) {
            command += ch;
        } else {
            command = "";  // 丢弃超长且未换行的命令
        }
    }
}
```

命令名可以换成项目自己的前缀，但固件、主机脚本、文档三处必须同时改。

### 4. 分块读回，先头行后数据

核心约束：

- 头行：`NB_SCREEN <width> <height> <bytes>\n`；
- 数据：RGB888，行优先，左上角原点；
- 每 8 行取一块，静态行缓冲，避免申请第二整帧；
- 单帧 25 s 上限；中止后不再发任何 ASCII；
- 处理 `output.write()` 的部分写和 0 写；
- 几何不符时，在发头行之前输出 `NB_ERROR unsupported_geometry`。

### 5. 关掉会插进二进制流的日志

```cpp
Serial.setDebugOutput(false);
esp_log_level_set("*", ESP_LOG_NONE);
```

SDK/BLE 回调可能从其他任务按字符打印。只要它们和截图共用 `Serial`，就必须在截图期间静音；否则主机会在 payload 中间读到日志。

### 6. 接受阻塞

截图会占住渲染主循环数秒，期间 UI 和触摸暂停。维护用途可以接受；不要为了“并发截图”让另一个任务读同一块 canvas。

## 线协议

| 项 | 内容 |
|---|---|
| 请求 | `NB_SCREEN\n` |
| 响应头 | `NB_SCREEN <width> <height> <bytes>\n` |
| 数据 | `<bytes>` 字节 RGB888，行优先，左上角原点 |
| 错误 | `NB_ERROR <reason>\n`，只允许在二进制开始前发送 |
| Tab5 常值 | 720×1280，2,764,800 字节，8 行一块（17,280 字节） |

约束：

- `bytes` 必须等于 `width * height * 3`；主机先校验再读。
- 二进制开始后不要再输出 ASCII 错误行；主机只会把它当作像素，图像会被污染，而且不一定报错。
- 超时中止时直接返回，让主机报“短帧”；不要补发错误行。
- 需要更强校验时可在 payload 后追加 CRC32，但要在头行增加字段，两端同步升级。

## 主机端实现

完整脚本：`scripts/usb_screenshot.py`。依赖：

```powershell
python -m pip install pyserial Pillow
```

```powershell
python scripts/usb_screenshot.py --port COM7 --output shot.png
python scripts/usb_screenshot.py --wait 15 --open
python scripts/usb_screenshot.py --expect 720x1280
python scripts/usb_screenshot.py --self-test
```

流程：

1. 找串口：Espressif VID `0x303A` 或 hwid 包含 `303A:1001`；多个候选要求 `--port`。
2. 打开前 `dtr=False; rts=False`，避免 ESP32 自动复位。
3. 清输入缓冲，发 `NB_SCREEN\n`。
4. 8 s 内等头行；忽略日志行，遇 `NB_ERROR` 立即失败。
5. 45 s 内按声明长度读满；超时报告已收/应收字节数。
6. `Image.frombytes("RGB", (width, height), data)` 保存 PNG；默认输出时同步 `latest.png`。

## 让截图可复现

- 先查询状态（如 `NB_INFO`），确认页面、连接状态和帧序号已经稳定。
- 需要切页面或点按钮时，用 `NB_TOUCH <x> <y>` 注入逻辑坐标，走与真实触摸相同的处理函数。
- 等一帧稳定后再抓；不要在动画或滚动中途截图。
- `NB_TOUCH` 只验证逻辑路径，不能代替物理触摸面板检测。

## 移植到其他型号

先读 `references/porting.md`，重点确认：

1. 板子用的是原生 USB-CDC 还是 CP210x/CH9102/CH340/FTDI 桥片；
2. canvas 需要多少 PSRAM，行缓冲是否放得下；
3. 屏幕旋转是画在 canvas 上，还是在 `pushSprite` 时应用；
4. 最差吞吐下 2.7 MB 级 payload 要多久，固件和主机超时是否匹配；
5. 日志、BLE、Wi-Fi 是否会和截图共用串口。

## 验证清单

- [ ] `--self-test` 输出 `SELF_TEST_OK`。
- [ ] 实机抓一帧，PNG 尺寸与面板一致，颜色无明显偏色。
- [ ] 旋转 180° 后再抓，逻辑截图字节一致（如果旋转在 `pushSprite` 时应用）。
- [ ] 连续抓 3 次，无截断、无残影。
- [ ] 抓取中途拔线：主机报短帧，固件超时后恢复渲染，不死机。
- [ ] 截图期间 BLE/Wi-Fi 业务不崩；UI 在截图结束后恢复。

## 故障排查

| 现象 | 常见原因 | 处理 |
|---|---|---|
| 找不到串口 | 不是数据线、未开机、驱动缺失 | 换 USB-C 数据线，确认系统里有串口，或用 `--port` |
| 找到多个串口 | 电脑同时接了多个 Espressif 设备 | 用 `--port` 指定，或拔掉其他设备 |
| 串口打不开 | PlatformIO/Arduino 监视器占用 | 关闭监视器、串口终端后重试 |
| 发命令后设备重启 | DTR/RTS 触发自动复位 | 开串口前把 DTR/RTS 置低；桥片板子确认接线 |
| 头行超时 | 固件没有该命令、命令名不一致、波特率不对 | 先用 `NB_INFO` 验证链路，核对命令名和波特率 |
| payload 中间混入文字 | 调试日志与截图共用串口 | `setDebugOutput(false)`，截图期间关闭 esp_log |
| 短帧 | 链路降速、固件超时太短 | 加大固件上限，主机窗口更大；检查线缆 |
| 图像颜色不对 | 通道顺序或 RGB565 转换错误 | 用已知纯色画面抽查；确认 `readRectRGB` 输出 RGB888 |
| 图像撕裂/错位 | 截图与渲染并发 | 只在渲染主循环截图；抓稳定帧 |
| 内存分配失败 | 没有 PSRAM 或 canvas 太大 | 降分辨率/色深，或改用行级读回 |

## 参考文件

- `references/firmware_capture.cpp`：固件端完整参考实现。
- `references/porting.md`：其他 M5Stack 型号、总线、内存和超时差异。
- `references/field-notes.md`：实测数据、两次真实故障与修复记录。
- `scripts/usb_screenshot.py`：主机端可直接运行的工具。

此 skill 设为手动调用（`disable-model-invocation: true`），避免模型在无关任务里自动套用。
