# Tu-Zi 生图接口参考

## 单次生成

接口：

```text
POST https://api.tu-zi.com/v1/chat/completions
Authorization: Bearer <TU_ZI_API_KEY>
Accept: application/json
Content-Type: application/json
```

请求体：

```json
{
  "temperature": 0.7,
  "messages": [
    {
      "content": "一只快速奔跑的兔子",
      "role": "user"
    }
  ],
  "model": "gpt-image-2",
  "stream": false
}
```

传多张本地参考图时，脚本会先把每张图片转成 data URL，再发到同一个 `content` 数组里：

```json
{
  "temperature": 0.7,
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "请综合第 1 张的人像、第 2 张的服装、第 3 张的场景生成一张电影感海报。"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,<person-image-bytes>"
          }
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,<style-image-bytes>"
          }
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/webp;base64,<scene-image-bytes>"
          }
        }
      ]
    }
  ],
  "model": "gpt-image-2",
  "stream": false
}
```

## 典型响应

```json
{
  "id": "chatcmpl-xxxxxxxx",
  "model": "gpt-image-2",
  "object": "chat.completion",
  "created": 1776786605,
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "> 🎨 生成中...\n\n![alt](https://apioss4.sydney-ai.com/.../image.webp)\n\n[点击下载](https://filesystem.site/cdn/download/.../image.webp)"
      },
      "finish_reason": "stop"
    }
  ]
}
```

## 结果解析

- 这是单次同步响应，不需要轮询。
- 真正的图片结果不在顶层 `image_url` 字段里。
- 图片链接在 `choices[0].message.content` 的 Markdown 内容中。
- `![...](...)` 中的链接是展示图直链。
- `[点击下载](...)` 中的链接是下载链接。
- 如果没有下载链接，至少也应该能从 Markdown 图片里提取到展示图直链。

## 当前脚本约定

- 默认模型：`gpt-image-2`
- 默认比例：`1:1`
- 当前接口没有独立的 `size` 字段。
- 当脚本收到非默认 `--size` 时，会把比例要求附加进 prompt，而不是作为独立 JSON 字段发送。
- 脚本支持重复传入 `--reference-image-path`，并按参数顺序把多张本地图片编码成 data URL 后附加到同一条用户消息里。
- 脚本输出里会返回：
  - `id`
  - `status`
  - `image_url`
  - `prompt`
  - `size`
  - `model`
  - `finish_reason`
  - `content`
- 如果响应里存在下载链接，脚本还会返回 `download_url`。
- 如果没有使用 `--no-download`，脚本会下载图片并额外返回 `saved_path`。

## 注意点

- `content` 里的“生成中...”只是文案，不代表还需要继续查状态。
- `finish_reason: "stop"` 表示这次响应已经结束。
- `usage` 中的细项字段可以参考，但不要把它当成强约束字段依赖。
- 当前 skill 只支持本地路径参考图，不支持直接透传聊天附件或公网图片 URL。
- 如果后续接口返回的 Markdown 结构发生变化，优先检查 `choices[0].message.content` 的原始文本。
