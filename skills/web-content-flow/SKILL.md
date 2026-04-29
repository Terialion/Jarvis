---
name: web-content-flow
description: "web-content-flow"
allowed-tools: Read,Write,Bash
---

﻿---
name: web-content-flow
description: 先规划再执行的网页打开流程 skill。
---

# web-content-flow

## 定位
- 目标: 将“打开某站某内容”拆解成可执行步骤。
- 边界: 不做深度内容总结。

## 输入
- `user_input`: 操作目标描述
- `execute_steps`: 是否执行步骤（默认 true）
- `open_in_browser`: 是否打开浏览器（默认 true）

## 输出
- `status`: success | error
- `analysis`: 规划结果
- `steps`: 规划步骤
- `executed`: 实际执行结果
- `final_url`: 最终 URL

## 参数示例
- 示例1: user_input=...
- 示例2: source_url=https://example.com
## 错误码规范
- missing_input: 缺少必要输入参数
- invalid_param: 参数格式不合法
- upstream_error: 外部依赖失败（网络/模型/站点限制）
- internal_error: 运行时异常（已降级或记录）

