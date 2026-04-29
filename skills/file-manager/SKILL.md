---
name: file-manager
description: "file-manager"
allowed-tools: Read,Write,Bash
---

﻿---
name: file-manager
description: 统一文件读写、搜索与整理操作。
---

# file-manager

## 定位
- 目标: 提供文件系统基础能力。
- 边界: 不负责业务语义分析。

## 输入
- `action`: read | write | list | search
- `path`: 文件或目录路径
- `content`: 写入内容（可选）

## 输出
- `status`: success | error
- `data`: 文件结果或列表
- `notes`: 失败原因或提示

## 参数示例
- 示例1: user_input=...
- 示例2: source_url=https://example.com
## 错误码规范
- missing_input: 缺少必要输入参数
- invalid_param: 参数格式不合法
- upstream_error: 外部依赖失败（网络/模型/站点限制）
- internal_error: 运行时异常（已降级或记录）

