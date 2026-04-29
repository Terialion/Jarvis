---
name: web-open-page
description: "web-open-page"
allowed-tools: Read,Write,Bash
---

﻿---
name: web-open-page
description: 只负责打开网页并返回基础确认信息。
---

# web-open-page

## 输入
- `user_input`: 含 URL 的文本
- `source_url`: 目标 URL（可选）
- `open_in_browser`: 是否打开浏览器（默认 true）
- `fetch_meta`: 是否抓取 title/final_url（默认 true）

## 输出
- `status`: success | error
- `url`: 目标地址
- `opened`: 是否已触发打开
- `meta`: 页面基础信息

## 参数示例
- 示例1: user_input=...
- 示例2: source_url=https://example.com
## 错误码规范
- missing_input: 缺少必要输入参数
- invalid_param: 参数格式不合法
- upstream_error: 外部依赖失败（网络/模型/站点限制）
- internal_error: 运行时异常（已降级或记录）

