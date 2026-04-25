---
name: apimart-image-generation
description: 调用 APIMart 异步生图接口，支持文生图、图生图、多张本地参考图或公网参考图、任务轮询、结果下载与任务状态排查。Use when user needs to generate images through APIMart, validate multi-reference image requests, or debug an existing APIMart image task.
---

# Apimart Image Generation

使用 APIMart 的异步图像生成接口完成提交、轮询、下载和排障。

## 工作流

1. 获取用户的 prompt。
如果用户没有提供 prompt，先补问一句，不要自行脑补画面细节。

2. 获取可选参考图。
支持两种输入：

- 本地绝对路径参考图，通过 `--reference-image-path` 重复传入
- 公网参考图链接，通过 `--reference-image-url` 重复传入

如果用户同时给了多张图，保留输入顺序，并提醒用户在 prompt 中明确每张图的职责。

3. 确认环境变量 `APIMART_API_KEY` 已存在。
如果缺失，明确告诉用户需要先设置这个变量。

4. 如果在 Windows PowerShell 中运行，先主动切到 UTF-8，避免中文 prompt、错误信息和日志出现乱码。

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
```

5. 默认使用 `gpt-image-2`、`1:1` 和 `1k`。
除非用户明确要求，不要改模型，也不要传 `n` 大于 `1`。

6. 这是收费接口。
除非用户明确要求“生成图片”或“继续执行验证”，否则不要主动发起新的生成请求。
如果用户只是想排查已有任务，优先使用 `status` 子命令查询已有 `task_id`。

7. 运行主脚本。
生成图片：

```powershell
python "<path-to-skill>\scripts\generate_apimart_image.py" generate `
  --prompt "<prompt>"
```

常用参数：

```powershell
python "<path-to-skill>scripts\generate_apimart_image.py" generate `
  --prompt "<prompt>" `
  --size "16:9" `
  --resolution "2k" `
  --reference-image-path "C:\img\layout.png" `
  --reference-image-url "https://example.com/reference.jpg" `
  --output-dir "C:\path\to\images"
```

分辨率约束：

- `resolution` 可选值：`1k`、`2k`、`4k`，默认 `1k`
- `4k` 仅支持 6 个比例：`16:9`、`9:16`、`2:1`、`1:2`、`21:9`、`9:21`
- 其他比例如果搭配 `4k`，会在本地直接报错，不会发起请求

只查询任务状态：

```powershell
python "<path-to-skill>\scripts\generate_apimart_image.py" status `
  --task-id "task_01KPW6REVT94MPYCK6XRTEA00B"
```

如果要把日志写到其他位置，可以显式传 `--log-file`：

```powershell
python "<path-to-skill>\scripts\generate_apimart_image.py" generate `
  --prompt "<prompt>" `
  --log-file "C:\path\to\apimart-generation-history.jsonl"
```

8. 读取脚本输出 JSON。
成功生成时优先看：

- `task_id`
- `status`
- `image_url`
- `saved_path`
- `log_path`

如果只是查状态，则优先看：

- `task_id`
- `status`
- `progress`
- `error`

9. 在展示图片时，如果有 `saved_path`，优先使用本地绝对路径展示。

```markdown
![生成结果](C:\absolute\path\to\image.png)
```

## 输出约定

`generate` 成功时，脚本至少会输出：

- `task_id`
- `status`
- `progress`
- `prompt`
- `size`
- `resolution`
- `model`
- `reference_image_count`
- `image_url`
- `expires_at`
- `log_path`

下载成功时还会附带：

- `saved_path`

`status` 子命令会输出当前任务快照，并在可用时附带：

- `image_url`
- `expires_at`
- `error`

## 日志约定

- 默认日志文件：`<path-to-skill>\logs\generation-history.jsonl`
- 格式：JSON Lines，每次 `generate` 调用追加一行
- 默认记录字段包括：生成时间、prompt、size、resolution、参考图输入、提交响应、轮询历史、最终任务响应、图片链接、本地保存路径、错误信息

## 资源

- `scripts/generate_apimart_image.py`：提交任务、轮询状态、按需下载图片
- `references/api.md`：接口约束、轮询建议、5 图验证用例

## 排查

- 先看 `APIMART_API_KEY` 是否存在。
- 如果返回 `submitted`，这是正常行为，不是失败。继续轮询 `GET /v1/tasks/{task_id}`。
- 如果用户传了参考图，确认总数不超过 16 张。
- 本地参考图必须是绝对路径且文件存在。
- `size` 只能传比例值，例如 `1:1`、`16:9`，不要传 `1024x1024`。
- `resolution` 只能传 `1k`、`2k`、`4k`；大小写会被归一化为小写。
- `4k` 只支持 `16:9`、`9:16`、`2:1`、`1:2`、`21:9`、`9:21`，其他比例会因为总像素超上限而不可用。
- 如果任务最终是 `failed`，优先查看 `error.message`。
- 如果结果里有 `image_url`，尽快下载；文档说明链接是稳定镜像链接，但 `expires_at` 仍然提示应尽早落地。
