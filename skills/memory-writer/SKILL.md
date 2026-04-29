---
name: memory-writer
description: "memory-writer"
allowed-tools: Read,Write,Bash
---

﻿---
name: memory-writer
description: 从对话中提取偏好与事实并写入记忆。
---

# memory-writer

## 定位
- 目标: 自动抽取用户事实并写入记忆层。
- 边界: 不负责最终回答生成。

## 输入
- `user_input`: 用户输入文本
- `memory_scope`: 写入范围（可选）

## 输出
- `status`: success | error
- `data`: 提取出的记忆条目
- `notes`: 过滤或去重说明

## 参数示例
- 示例1: user_input=...
- 示例2: source_url=https://example.com
## 错误码规范
- missing_input: 缺少必要输入参数
- invalid_param: 参数格式不合法
- upstream_error: 外部依赖失败（网络/模型/站点限制）
- internal_error: 运行时异常（已降级或记录）

