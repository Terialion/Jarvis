---
name: code-generator
description: "code-generator"
allowed-tools: Read,Write,Bash
---

﻿---
name: code-generator
description: 生成并保存可执行代码片段。
---

# code-generator

## 定位
- 目标: 根据自然语言生成代码并落盘。
- 边界: 不负责复杂多文件工程编排。

## 输入
- `user_input`: 代码需求描述
- 其他生成参数（可选）

## 输出
- `status`: success | error
- `summary`: 执行说明
- `data`: 生成代码与文件路径

## 运行策略
- 先解析需求，再生成代码
- 默认返回结构化结果，便于上游复用

## 参数示例
- 示例1: user_input=...
- 示例2: source_url=https://example.com
## 错误码规范
- missing_input: 缺少必要输入参数
- invalid_param: 参数格式不合法
- upstream_error: 外部依赖失败（网络/模型/站点限制）
- internal_error: 运行时异常（已降级或记录）

