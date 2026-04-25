# APIMart GPT-Image-2 接口参考

## 核心事实

- 接口：`POST https://api.apimart.ai/v1/images/generations`
- 模型固定：`gpt-image-2`
- 处理方式：异步提交，成功后返回 `task_id`
- 查询接口：`GET https://api.apimart.ai/v1/tasks/{task_id}?language=zh`
- 取图路径：`data.result.images[0].url[0]`

## 请求字段

最小请求体：

```json
{
  "model": "gpt-image-2",
  "prompt": "一只橘猫坐在窗台上看夕阳，水彩画风格",
  "n": 1,
  "size": "16:9",
  "resolution": "1k"
}
```

图生图请求在此基础上追加 `image_urls`：

```json
{
  "model": "gpt-image-2",
  "prompt": "请根据参考图生成一张扁平化信息海报",
  "n": 1,
  "size": "16:9",
  "resolution": "2k",
  "image_urls": [
    "https://example.com/reference.jpg",
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
  ]
}
```

## 已验证约束

- `size` 只支持比例值，不支持 `1024x1024`
- `resolution` 支持 `1k`、`2k`、`4k`，默认 `1k`
- 支持的比例共有 13 个：
  - `1:1`
  - `16:9`
  - `9:16`
  - `4:3`
  - `3:4`
  - `3:2`
  - `2:3`
  - `5:4`
  - `4:5`
  - `2:1`
  - `1:2`
  - `21:9`
  - `9:21`
- `4k` 仅支持 6 个比例：
  - `16:9`
  - `9:16`
  - `2:1`
  - `1:2`
  - `21:9`
  - `9:21`
- 其他比例搭配 `4k` 会因总像素超上限而不可用
- `image_urls` 最多 16 张
- `image_urls` 同时支持：
  - 公网图片 URL
  - base64 data URI
- URL 与 base64 可以混合传入同一数组
- `n` 只允许 `1`
- 其他 OpenAI Images 风格字段如 `response_format`、`quality`、`style` 会被忽略

## 状态与轮询

提交成功时返回：

```json
{
  "code": 200,
  "data": [
    {
      "status": "submitted",
      "task_id": "task_xxx"
    }
  ]
}
```

任务查询常见状态：

- `submitted`
- `pending`
- `processing`
- `in_progress`
- `completed`
- `failed`
- `cancelled`

轮询建议：

- 首次查询延迟：`10~20` 秒
- 查询间隔：`3~5` 秒
- 客户端超时：建议至少 `180` 秒

## 成功结果示例

```json
{
  "code": 200,
  "data": {
    "id": "task_xxx",
    "status": "completed",
    "progress": 100,
    "created": 1776748674,
    "completed": 1776748726,
    "actual_time": 52,
    "estimated_time": 100,
    "result": {
      "images": [
        {
          "url": [
            "https://upload.apimart.ai/f/image/xxxxxxxx-gpt_image_2_task_xxx_0.png"
          ],
          "expires_at": 1776835126
        }
      ]
    }
  }
}
```

## 5 图验证用例

固定参考图顺序：

1. `C:\Projects\workspace\tmp_tuzi_multi_ref_validation\refs\red_circle.png`
2. `C:\Projects\workspace\tmp_tuzi_multi_ref_validation\refs\blue_square.png`
3. `C:\Projects\workspace\tmp_tuzi_multi_ref_validation\refs\green_triangle.png`
4. `C:\Projects\workspace\tmp_tuzi_multi_ref_validation\refs\yellow_diamond.png`
5. `C:\Projects\workspace\generated\simplified_factory_floorplan.png`

固定验证 prompt：

```text
请以第5张图的工厂平面布局为整体构图基础，生成一张扁平化信息图风格的工厂导航海报。在画面中明确融合前4张参考图的几何元素：第1张红色圆形作为主警示标记，第2张蓝色方形作为功能区块标记，第3张绿色三角形作为方向指示标记，第4张黄色菱形作为关键节点标记。要求5个参考元素都能被清晰识别，布局有层次，颜色区分明确，画面整洁，16:9。
```

验收点：

- 请求体确实带有 5 个 `image_urls`
- 任务成功进入 `completed`
- 结果中存在 `data.result.images[0].url[0]`
- 生成图能识别平面布局、红圆、蓝方、绿三角、黄菱形
