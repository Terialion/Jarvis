---
name: multi-search-free
version: "1.0.0"
description: "免费多引擎搜索 Skill，支持 DuckDuckGo/Bing/Baidu/Sogou/SearXNG。用于快速恢复和统一 Jarvis 联网搜索可用性。"
triggers:
  - "搜索"
  - "查找"
  - "search"
  - "搜一下"
  - "查一下"
  - "帮我搜"
  - "联网搜索"
  - "联网查"
---

# multi-search-free — 免费多引擎搜索 Skill

## 概述

本 Skill 提供免费的多搜索引擎能力，无需 API Key，通过解析各搜索引擎的 HTML/JSON 结果页面实现。

## 支持的搜索引擎

| 引擎 | URL 模板 | 特点 |
|------|----------|------|
| **DuckDuckGo** | `duckduckgo.com/html/?q=` | 无限流、隐私友好、英文首选 |
| **Bing** | `bing.com/search?q=` | 结果质量高、中英文通吃 |
| **Baidu** | `baidu.com/s?wd=` | 中文搜索首选、国内访问稳定 |
| **Sogou** | `sogou.com/web?query=` | 中文备选、微信搜索 |
| **Google** | `google.com/search?q=` | 质量最高、但可能被墙 |
| **SearXNG** | `localhost:8080/search?format=json` | 自托管聚合引擎、结构化 JSON |

## 使用方式

### 基础搜索
```python
from skills.search import execute_multi_search_free
result = execute_multi_search_free("Python asyncio 教程")
print(result)
```

### 指定引擎
```python
from skills.search.skill_multi_search_free import execute_search
result = execute_search("Docker compose", engines=["duckduckgo", "bing"])
```

### 从 Skill 系统调用
```python
from jarvis.toolkit import toolkit
toolkit.call_skill("multi-search-free", query="最新AI论文")
```

## 引擎选择策略

1. **中文查询** → baidu, bing, sogou（优先百度）
2. **英文查询** → duckduckgo, bing, google
3. **技术/GitHub 相关** → 添加 github.com 搜索 URL
4. **默认** → duckduckgo, bing

## Fallback 链

系统按引擎顺序尝试，首个成功返回结果的引擎即被采用：
- 如果首个引擎失败或返回空结果，自动尝试下一个
- 所有引擎都失败时返回错误信息
- 每次搜索记录尝试过的引擎和遇到的错误

## 返回格式

```
🔍 搜索: "query"
引擎: duckduckgo (耗时 1200ms)
─────────────────────
1. 标题
   https://example.com
   摘要文本...

2. 标题
   https://example2.com
   摘要文本...
─────────────────────
共 8 条结果 | 备用引擎: bing(未使用)
```

## 依赖

**零外部依赖** — 仅使用 Python 标准库：
- `urllib.request` — HTTP 请求
- `html.parser` — HTML 解析
- `re` — 正则匹配
- `json` — JSON 解析（SearXNG）
- `time`, `hashlib`, `logging` — 工具
