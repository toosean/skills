---
name: tu-zi-nano
description: 调用兔子 Tu-Zi 的 chat completions 生图接口，支持文字 prompt 和多张本地参考图，并从返回的 Markdown 内容中提取图片链接或下载图片。Use when the user asks to generate an image from a prompt, call the Tu-Zi image API at api.tu-zi.com, optionally include multiple local reference images, return the final image URL, or download the generated image for display. Typical triggers include “帮我生一张图”, “用这个 prompt 生成图片”, and “调用兔子 nano 接口出图”.
---

# 兔子nano

用用户提供的 prompt 和可选的多张本地参考图调用 Tu-Zi 的单次生图接口，并返回可展示的图片结果。

## 工作流

1. 获取用户的生图 prompt。
如果用户没有提供 prompt，先补问一句，不要自行脑补画面细节。

2. 如果用户要参考图生图，要求用户提供本地图片绝对路径。
可以提供多张，调用时按参数顺序保留语义顺序。提醒用户在 prompt 中写清每张图的用途，例如“第 1 张做人像参考，第 2 张做服装参考，第 3 张做场景参考”。

3. 确认环境变量 `TU_ZI_API_KEY` 已存在。
如果缺失，明确告诉用户需要先设置这个变量。

4. 如果在 Windows PowerShell 中运行，先主动切到 UTF-8，避免接口响应里的中文、emoji 或 Markdown 在 GBK 控制台里触发编码报错。

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
```

不要等报错后再补救；默认先做这一步，再执行脚本。

5. 默认使用 `gpt-image-2` 和 `1:1`。
只有在用户明确要求其他尺寸时，才改 `--size`。

6. 这个接口调用是收费的。
除非用户明确指定要调用接口、生图或继续执行，否则不要自行发请求测试、试跑或验证。

7. 运行脚本提交单次请求。
脚本会默认把每次生成追加记录到技能目录下的 `logs/generation-history.jsonl`，包括成功和失败两类事件。

```powershell
python "C:\Users\toose\.codex\skills\tu-zi-nano\scripts\generate_tuzi_image.py" --prompt "<prompt>"
```

常用参数：

```powershell
python "C:\Users\toose\.codex\skills\tu-zi-nano\scripts\generate_tuzi_image.py" `
  --prompt "<prompt>" `
  --size "1:1" `
  --output-dir "C:\path\to\images"
```

如果你想把日志写到其他位置，可以显式传 `--log-file`：

```powershell
python "C:\Users\toose\.codex\skills\tu-zi-nano\scripts\generate_tuzi_image.py" `
  --prompt "<prompt>" `
  --log-file "C:\path\to\tuzi-generation-history.jsonl"
```

多张本地参考图：

```powershell
python "C:\Users\toose\.codex\skills\tu-zi-nano\scripts\generate_tuzi_image.py" `
  --prompt "<prompt，写清每张图的用途>" `
  --reference-image-path "C:\img\person.png" `
  --reference-image-path "C:\img\style.jpg" `
  --reference-image-path "C:\img\scene.webp"
```

只要结果链接、不下载文件：

```powershell
python "C:\Users\toose\.codex\skills\tu-zi-nano\scripts\generate_tuzi_image.py" `
  --prompt "<prompt>" `
  --no-download
```

8. 读取脚本输出的 JSON。
如果有 `saved_path`，优先用本地绝对路径展示图片；如果只有 `image_url`，返回链接并说明没有落地到本地文件。
如果有 `log_path`，说明这次生成已经成功写入日志。

9. 在 Codex 桌面端展示图片时，直接使用本地路径：

```markdown
![生成结果](C:\absolute\path\to\image.png)
```

## 返回处理

- 接口是单次响应，不需要轮询。
- 从 `choices[0].message.content` 里解析 Markdown 图片。
- `![...](...)` 中的链接作为 `image_url`。
- `[点击下载](...)` 中的链接作为可选 `download_url`。
- 如果用户传了非默认 `--size`，脚本会把比例要求附加进 prompt，因为当前接口没有独立的 `size` 字段。
- 如果用户传了多张参考图，脚本会按 `--reference-image-path` 的顺序把它们编码后附加到同一条用户消息里。

## 输出约定

脚本会输出一条 JSON，至少包含：

- `id`
- `status`
- `image_url`
- `prompt`
- `size`
- `model`
- `finish_reason`
- `content`

如果存在额外结果，脚本还会附带：

- `download_url`
- `saved_path`
- `log_path`

## 日志约定

- 默认日志文件：`C:\Users\toose\.codex\skills\tu-zi-nano\logs\generation-history.jsonl`
- 格式：JSON Lines，每次生成追加一行，便于后续筛选、汇总或导入。
- 默认记录字段包括：生成时间、状态、prompt、模型、尺寸、参考图路径、输出目录、文件名、是否下载、本地保存路径、图片链接、下载链接、错误信息。
- 无论成功还是失败，都应该尝试写日志；不要只记录成功案例。

## 资源

- `scripts/generate_tuzi_image.py`：提交单次生图请求、解析 Markdown、按需下载图片。

## 排查

- 先看 `TU_ZI_API_KEY` 是否存在。
- 如果当前任务只是分析、评估、改代码或改文档，而用户没有明确要求实际生图，不要为了验证而直接调用这个收费接口。
- 如果用了参考图，确认每个 `--reference-image-path` 都是本地绝对路径，文件存在，而且是可识别的图片格式。
- 如果在 Windows 上调用脚本，默认先做 UTF-8 控制台初始化，不要等控制台报 `gbk` 或 Unicode 编码错误后才处理。
- 如果用户说“之前生成过但找不到记录”，优先检查 `C:\Users\toose\.codex\skills\tu-zi-nano\logs\generation-history.jsonl` 是否存在，以及当前调用有没有覆盖 `--log-file`。
- 再看接口是否返回了 `choices[0].message.content`。
- 如果没有解析出 `image_url`，把原始 `content` 原样带回，优先检查 Markdown 结构有没有变。
- 如果需要核对当前接口细节，优先查看脚本实现，不要按旧的异步轮询接口说明执行。
