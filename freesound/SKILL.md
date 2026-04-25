---
name: freesound
description: 用 Freesound API 按关键词搜索音效、环境声、简单背景音乐和预览链接，并按授权类型筛选结果。Use when the user wants to find sound effects or simple music by keyword, needs Freesound preview links, wants to test a Freesound API key, or wants quick search results for terms like explosion, gunshot, UI click, ambience, battle music, and background music.
---

# Freesound

用 Freesound API 按关键词搜索并返回可试听的结果。

## 工作流

1. 先确认有 API key。
优先使用环境变量 `FREESOUND_API_KEY`。
如果没有，再让用户提供 API key。

2. 明确搜索词。
不要擅自扩写很多条件；默认直接用用户给的关键词。
如果用户要更准的结果，再补充风格词，例如：
- `explosion`
- `gunshot`
- `ui click`
- `battle music`
- `forest ambience`

3. 默认只做搜索，不下载原文件。
优先返回：
- 名称
- 作者
- 时长
- 授权类型
- 预览链接

4. 如果用户关心商用，优先提醒看授权。
常见关注点：
- `CC0`：最宽松
- `CC-BY`：通常需要署名
- `CC-BY-NC`：非商用

5. 如果用户只说“随便找几个”，默认每个关键词给 3 个结果就够了。
不要一次返回过长清单。

## Python 调用模板

用标准库直接请求即可：

```python
import json
import urllib.parse
import urllib.request

api_key = "YOUR_FREESOUND_API_KEY"
query = "explosion"
url = "https://freesound.org/apiv2/search/text/?" + urllib.parse.urlencode({
    "query": query,
    "token": api_key,
    "fields": "id,name,previews,license,username,duration"
})

with urllib.request.urlopen(url, timeout=20) as r:
    data = json.load(r)

for item in data.get("results", [])[:3]:
    print({
        "name": item.get("name"),
        "user": item.get("username"),
        "duration": item.get("duration"),
        "license": item.get("license"),
        "preview": item.get("previews", {}).get("preview-hq-mp3"),
    })
```

## 输出约定

默认输出这 5 个字段：

- `name`
- `user`
- `duration`
- `license`
- `preview`

如果用户明确要更多信息，再补充 sound id 或详情页链接。

## 关键词建议

音效类：
- `explosion`
- `gunshot`
- `footstep`
- `door open`
- `ui click`
- `magic spell`
- `car crash`

环境类：
- `rain ambience`
- `forest ambience`
- `city night`
- `battle ambience`

音乐类：
- `background music`
- `battle music`
- `epic action music`
- `happy kids music`

## 排查

- 如果返回 401 或 403，先检查 API key。
- 如果结果很差，先缩短关键词，不要一开始写太长句子。
- 如果要商用素材，优先筛 `CC0` 或 `CC-BY`，避开 `CC-BY-NC`。
- Freesound 更偏音效和素材库，不是纯背景音乐平台；搜音乐时结果可能不稳定。
