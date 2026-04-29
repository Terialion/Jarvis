---
name: structured-content-extractor
description: "structured-content-extractor"
allowed-tools: Read,Write,Bash
---

﻿---
name: structured-content-extractor
description: 将网页文本提取为结构化条目，供上游总结复用。
---

# structured-content-extractor

## 输入
- `source_url`: 页面地址
- `site`: 站点标识（可选）
- `page_text`: 页面文本

## 输出
- `status`: success | error
- `site`: 识别站点
- `mode`: ecommerce_search | social_post | generic
- `items`: 结构化条目
- `summary_hint`: 上游总结提示

## 参数示例
- 示例1: user_input=...
- 示例2: source_url=https://example.com
## 错误码规范
- missing_input: 缺少必要输入参数
- invalid_param: 参数格式不合法
- upstream_error: 外部依赖失败（网络/模型/站点限制）
- internal_error: 运行时异常（已降级或记录）

