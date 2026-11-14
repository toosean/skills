# skills

Personal skill collection.

## 新增或修改 SKILL 前的确认

每次新增或修改 SKILL，必须先向用户确认一个问题。

该问题是：这个 SKILL 是否要在 `SKILL.md` 元数据加入 `disable-model-invocation: true`。

不要自行预设答案。先问用户，再按用户回答写元数据。

### 字段含义

加入该字段后，模型不自动选择这个 SKILL。
只有用户显式点名时，才加载这个 SKILL。
不加该字段时，模型可以自行判断调用。
以上含义与 Pi 文档 `docs/skills.md` 的说明一致。

### 建议加入的情况

满足任一条，就建议加入：

- 这个 SKILL 只在用户点名时才该加载。
- 这个 SKILL 有副作用，例如写文件、发消息、调用付费接口。
- 这个 SKILL 耗时长或成本高，误触发代价大。
- 这个 SKILL 需要用户先给出参数，模型无法推断。

### 建议不加的情况

- 这个 SKILL 安全通用，例如格式转换、只读检索。
- 模型能自行判断何时需要这个 SKILL。

### 元数据示例：不加字段

模型可以自动选择这个 SKILL。

```yaml
---
name: pdf-text-extract
description: Extract text from PDF files. Use when a PDF needs reading.
---
```

### 元数据示例：加入字段

只有用户显式调用时，才加载这个 SKILL。

```yaml
---
name: prod-db-migrate
description: Apply database migrations to production. Use only when the user asks.
disable-model-invocation: true
---
```

本节只约束后续新增和修改。现有 SKILL 不受本节影响。
