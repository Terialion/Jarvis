---
name: arxiv-reader
description: "通过 marketplace 的 arxiv-reader 引擎读取并总结单篇 arXiv 论文。"
allowed-tools: Read,Write,Bash
slash_command: /arxiv
---

# arxiv-reader

## 输入
- `user_input`: 含 arXiv ID/URL 的请求文本
- `arxiv_id`: 直接指定 arXiv ID（可选）
- `category`: 可选分类标签（默认 auto）

## 输出
- `status`: success | error
- `arxiv_id`: 目标论文编号
- `summary`: 论文阅读结果摘要
- `notes`: arxiv_reader_adapter

## 参数示例
- 示例1: user_input=读取 arxiv 2401.12345
- 示例2: arxiv_id=2401.12345

## 错误码规范
- missing_input: 缺少 arXiv ID 或 URL
- upstream_error: marketplace 引擎缺失或执行失败
- internal_error: 运行时异常（已降级或记录）
