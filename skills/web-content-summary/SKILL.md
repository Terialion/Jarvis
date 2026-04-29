---
name: web-content-summary
description: "web-content-summary"
allowed-tools: Read,Write,Bash
---

﻿---
name: web-content-summary
description: 抓取网页并输出可读总结，支持结构化提取与多帖深读。
---

# web-content-summary

## 输入
- `user_input`: 原始请求
- `source_url`: 目标 URL（可选）
- `cookies`: Cookie 数组或 JSON 字符串（可选）
- `cookie_file`: 本地 Cookie 文件（可选）
- `deep_crawl`: 是否启用多帖深读（默认 true）

## 输出
- `status`: success | error
- `analysis`: 站点分析
- `page`: 页面信息（含 clean_text/structured_data）
- `summary`: 总结结论
- `key_points`: 要点列表
- `notes`: 状态说明（如 blocked/login/deleted）

## 参数示例
- 示例1: user_input=...
- 示例2: source_url=https://example.com
## 错误码规范
- missing_input: 缺少必要输入参数
- invalid_param: 参数格式不合法
- upstream_error: 外部依赖失败（网络/模型/站点限制）
- internal_error: 运行时异常（已降级或记录）

