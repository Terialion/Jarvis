---
name: jarvis-code-agent
description: "jarvis-code-agent"
allowed-tools: Read,Write,Bash
---

﻿---
name: jarvis-code-agent
description: 面向编码任务的规划与执行型 agent skill。
---

# jarvis-code-agent

## 定位
- 目标: 完成多步骤代码任务（规划、修改、验证）。
- 边界: 不替代通用聊天。

## 输入
- `user_input`: 编码任务描述
- `context`: 可选上下文

## 输出
- `status`: success | error
- `summary`: 任务结论
- `data`: 修改记录与关键结果

## 参数示例
- 示例1: user_input=...
- 示例2: source_url=https://example.com
## 错误码规范
- missing_input: 缺少必要输入参数
- invalid_param: 参数格式不合法
- upstream_error: 外部依赖失败（网络/模型/站点限制）
- internal_error: 运行时异常（已降级或记录）

