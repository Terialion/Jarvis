# J.A.R.V.I.S - Just A Rather Very Intelligent System

<div align="center">

![Version](https://img.shields.io/badge/version-3.2-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-red)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)

**智能 AI 编程助手 - 基于 DeepSeek API + ReAct 架构**

[🚀 快速开始](#快速开始) · [📚 使用指南](#使用指南) · [🛠️ Skills 开发](#skills-开发) · [⚙️ 配置说明](#配置说明)

</div>

---

## 🌟 项目介绍

Jarvis 是一个受 Claude Code 和 OpenClaw 启发的本地 AI 编程助手，具备：

- **🎯 Claude-style CLI**：友好的命令行交互界面
- **🧠 ReAct 架构**：推理-行动循环，支持复杂任务分解
- **🔧 Skills 系统**：可扩展的技能插件机制
- **🔐 安全模式**：文件操作、Shell 命令、网络访问均需审批
- **📊 质量门禁**：完善的测试体系和基准测试

---

## ✨ 核心特性

### 1. 🖥️ Claude-style CLI

```powershell
# 启动交互式 CLI
python -m jarvis.cli

# 查看帮助
python -m jarvis.cli --help

# 查看可用 Skills
python -m jarvis.cli skills

# 查看 Skills 详细信息
python -m jarvis.cli skills --debug

# 运行任务（安全模式）
python -m jarvis.cli task run "检查这个代码仓库的结构" --safe --trace
```

### 2. 🧠 ReAct 推理引擎

- **观察 → 计划 → 行动 → 检查**：标准的 ReAct 循环
- **有界迭代**：防止无限循环（max_steps/max_failures/max_budget）
- **上下文管理**：智能压缩历史对话，避免超限
- **回放机制**：支持任务回放和证据记录

### 3. 🔧 Skills 系统

- **动态加载**：从 `skills/` 目录自动发现和加载
- **标准接口**：统一的 `execute(*args, **kwargs)` 入口
- **安全执行**：支持 dry-run 模式和安全审批
- **丰富的 Skills**：内置 100+ 技能（GitHub、文档处理、浏览器自动化等）

示例 Skills：
- `github`：GitHub 操作（issue、PR、CI）
- `pdf` / `docx` / `xlsx` / `pptx`：文档处理
- `agent-browser`：浏览器自动化
- `skill-creator`：创建新 Skill

### 4. 🔐 安全机制

- **审批门控**：文件写入、Shell 命令、网络访问、引用 Skills 均需审批
- **安全模式**：默认开启，防止意外操作
- **权限系统**：细粒度的工具权限控制

### 5. 🌐 API 和 Web UI

- **HTTP API**：`src/jarvis/api/server.py`（默认 8765 端口）
- **Web 控制界面**：`web/control-ui/`（类 OpenClaw 风格）
- **远程控制**：支持 Gateway 模式，可远程管理

---

## 🚀 快速开始

### 环境要求

- **Python**：3.10+（推荐 3.12）
- **操作系统**：Windows 10/11、Linux、macOS
- **可选**：麦克风（语音交互）、Node.js（Web UI）

### 安装步骤

#### 1. 克隆项目

```powershell
git clone https://github.com/your-username/jarvis.git
cd jarvis
```

#### 2. 创建虚拟环境

```powershell
# Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. 安装依赖

```powershell
pip install -r requirements.txt
```

#### 4. 配置环境变量

```powershell
# 复制示例配置
copy .env.example .env    # Windows
cp .env.example .env      # Linux/macOS

# 编辑 .env，填入你的 API Key
# 必填：DEEPSEEK_API_KEY
# 可选：OPENAI_API_KEY, MINIMAX_API_KEY 等
```

#### 5. 验证安装

```powershell
# 检查 CLI
python -m jarvis.cli --help

# 查看可用 Skills
python -m jarvis.cli skills

# 运行测试
python -m pytest tests/cli -q
```

---

## 📚 使用指南

### 1. CLI 基础使用

#### 启动交互式 CLI

```powershell
python -m jarvis.cli
```

#### 常用命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `python -m jarvis.cli --help` | 查看帮助 | - |
| `python -m jarvis.cli skills` | 列出 Skills | - |
| `python -m jarvis.cli skills --debug` | 查看 Skills 详情 | - |
| `python -m jarvis.cli task run "<任务>"` | 运行任务 | `python -m jarvis.cli task run "分析这个项目"` |
| `python -m jarvis.cli task run "<任务>" --safe` | 安全模式运行 | - |
| `python -m jarvis.cli task run "<任务>" --trace` | 启用追踪 | - |

#### 交互式命令（CLI 内）

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助 |
| `/skills` | 查看 Skills |
| `/status` | 查看状态 |
| `/tools` | 查看工具 |
| `/replay <id>` | 回放任务 |
| `/evidence <id>` | 查看证据 |
| `exit` / `quit` | 退出 |

### 2. Skills 使用

#### 查看可用 Skills

```powershell
python -m jarvis.cli skills
```

输出示例：

```
📦 已加载 Skills (120):
  ✅ github           - GitHub 操作
  ✅ pdf              - PDF 处理
  ✅ docx             - Word 文档处理
  ✅ xlsx             - Excel 处理
  ✅ pptx             - PowerPoint 处理
  ✅ agent-browser    - 浏览器自动化
  ✅ skill-creator    - 创建新 Skill
  ...
```

#### 使用 Skill

在交互式 CLI 中，直接描述你的需求，Jarvis 会自动选择合适的 Skill：

```
你: 帮我总结这个 PDF 文件：C:\Users\Administrator\Downloads\report.pdf
Jarvis: [调用 pdf Skill，提取并总结 PDF 内容]
```

或者显式调用：

```
你: /skill pdf summarize C:\Users\Administrator\Downloads\report.pdf
```

### 3. API 使用

#### 启动 API 服务器

```powershell
python -m src.jarvis.api.server
```

默认监听 `http://127.0.0.1:8765`

#### API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/task` | POST | 提交任务 |
| `/api/task/<id>` | GET | 查询任务状态 |
| `/api/skills` | GET | 列出 Skills |
| `/api/tools` | GET | 列出工具 |

示例：

```powershell
# 提交任务
curl -X POST http://127.0.0.1:8765/api/task \
  -H "Content-Type: application/json" \
  -d '{"task": "分析这个代码仓库"}'

# 查询任务状态
curl http://127.0.0.1:8765/api/task/<task_id>
```

### 4. Web UI 使用

#### 启动 Web UI

```powershell
# 方法 1：直接打开 HTML 文件
start web/control-ui/index.html

# 方法 2：通过 API 服务器访问
python -m src.jarvis.api.server
# 然后访问 http://127.0.0.1:8765
```

Web UI 功能：

- 📊 实时任务状态监控
- 🎛️ 控制面板（启动/停止任务）
- 📝 查看任务日志和证据
- ⚙️ 配置管理

---

## 🛠️ Skills 开发

### 创建新 Skill

#### 1. 创建 Skill 目录

```powershell
mkdir skills\my-skill
```

#### 2. 编写 SKILL.md

```markdown
# skills/my-skill/SKILL.md

---
name: my-skill
description: "我的自定义技能"
icon: "🚀"
---

# 技能说明

这个 Skill 用来...
```

#### 3. 编写 main.py

```python
# skills/my-skill/main.py

DESCRIPTION = "我的自定义技能"
ICON = "🚀"

def execute(*args, **kwargs):
    """
    技能入口函数
    
    Args:
        *args: 位置参数
        **kwargs: 关键字参数
        
    Returns:
        执行结果（字符串或字典）
    """
    # 实现你的逻辑
    return "执行成功"
```

#### 4. 测试 Skill

```powershell
# 在交互式 CLI 中测试
python -m jarvis.cli
你: 使用 my-skill 执行...

# 或者直接调用
python -c "from jarvis.tools.loader import load_skill; skill = load_skill('my-skill'); print(skill.execute())"
```

### Skill 最佳实践

1. **清晰的描述**：在 `SKILL.md` 中写明技能用途和使用方法
2. **错误处理**：捕获异常并返回友好的错误信息
3. **安全优先**：避免危险操作（删除文件、执行未经验证的命令等）
4. **文档完善**：提供使用示例和参数说明
5. **测试覆盖**：编写单元测试（`tests/skills/test_my_skill.py`）

---

## ⚙️ 配置说明

### 环境变量 (.env)

```bash
# === 必填 ===
DEEPSEEK_API_KEY=your_api_key_here

# === 可选：LLM 提供商 ===
OPENAI_API_KEY=
MINIMAX_API_KEY=
MINIMAX_API_BASE=

# === Jarvis 运行时 ===
JARVIS_MODE=safe                    # safe: 安全模式（默认）, debug: 调试模式
JARVIS_API_HOST=127.0.0.1          # API 服务器地址
JARVIS_API_PORT=8765                # API 服务器端口
JARVIS_NETWORK_ENABLED=false        # 是否启用网络访问
JARVIS_DOCKER_ENABLED=false        # 是否启用 Docker

# === 语音功能（可选）===
WHISPER_MODEL=paraformer-zh
ASR_MODEL=paraformer-zh
TTS_VOICE=zh-CN-YunxiNeural
MAX_RECORD_SECONDS=10

# === 联网搜索（可选）===
TAVILY_API_KEY=
SCRAPE_DO_API_KEY=
BING_SEARCH_API_KEY=
SERPER_API_KEY=
SEARCH_PREFER_API=auto
SEARCH_TOTAL_BUDGET=12
```

### 配置文件 (config/)

- `config/manager.py`：配置管理器
- `config/schema.py`：配置 Schema 定义
- `config/vault.py`：敏感信息保险库

### CLI 配置

```powershell
# 查看当前配置
python -m jarvis.cli config list

# 获取配置项
python -m jarvis.cli config get JARVIS_MODE

# 设置配置项
python -m jarvis.cli config set JARVIS_MODE debug
```

---

## 🧪 测试

### 运行测试

```powershell
# 运行所有测试
python -m pytest tests/ -q

# 运行特定测试
python -m pytest tests/cli/ -q           # CLI 测试
python -m pytest tests/skills/ -q        # Skills 测试
python -m pytest tests/api/ -q           # API 测试
python -m pytest tests/core_v0/ -q       # 核心功能测试
python -m pytest tests/react_readiness/ -q  # ReAct 就绪测试

# 运行质量门禁
python scripts/run_comparable_gate.py
python scripts/run_gap_closure_benchmark.py
python scripts/run_phase1_acceptance.py
```

### 测试覆盖率

```powershell
# 生成覆盖率报告
python -m pytest --cov=jarvis --cov=src/jarvis --cov-report=html

# 查看报告
start htmlcov/index.html
```

---

## 📁 项目结构

```
jarvis/
├── jarvis/                          # CLI 和工具管理
│   ├── cli.py                      # CLI 主入口
│   ├── cli_command_map.py           # CLI 命令映射
│   ├── runtime_bootstrap.py        # 运行时引导
│   ├── config/                    # 配置管理
│   ├── logger/                     # 日志系统
│   └── tools/                     # 工具加载器
│
├── src/jarvis/                     # 核心运行时和 API
│   ├── api/                       # HTTP API
│   ├── core/                      # 核心引擎
│   │   ├── task_runtime.py        # 任务运行时
│   │   ├── gateway_state.py        # Gateway 状态管理
│   │   ├── control_surface.py     # 控制面
│   │   ├── react_readiness/       # ReAct 就绪模块
│   │   ├── skill_harness/         # Skills 执行环境
│   │   └── ...
│   ├── runtime/                   # 运行时组件
│   ├── ui/                        # UI 组件
│   ├── web/                       # Web 组件
│   └── benchmarks/                # 基准测试
│
├── skills/                         # Skills 插件目录
│   ├── github/                    # GitHub 操作
│   ├── pdf/                       # PDF 处理
│   ├── docx/                      # Word 文档
│   ├── xlsx/                      # Excel 处理
│   ├── agent-browser/             # 浏览器自动化
│   └── ...
│
├── tests/                          # 测试套件
│   ├── cli/                       # CLI 测试
│   ├── skills/                    # Skills 测试
│   ├── api/                       # API 测试
│   ├── core_v0/                   # 核心功能测试
│   ├── react_readiness/           # ReAct 测试
│   └── ...
│
├── scripts/                        # 工具脚本
│   ├── run_comparable_gate.py     # 质量门禁
│   ├── run_gap_closure_benchmark.py  # 差距分析
│   └── ...
│
├── web/                           # Web 控制界面（编译后）
│   └── control-ui/
│
├── ui/                            # Web UI 源码
│   ├── public/
│   └── src/
│
├── config/                         # 全局配置
├── data/                           # 数据文件
├── docs/                           # 文档
├── examples/                       # 示例代码
│
├── .env.example                   # 环境变量示例
├── .gitignore                     # Git 忽略规则
├── requirements.txt               # Python 依赖
├── README.md                      # 本文件
└── main.py                        # 主入口（语音模式）
```

---

## 🤝 贡献指南

我们欢迎任何形式的贡献！

### 贡献流程

1. **Fork 项目**
2. **创建分支**：`git checkout -b feature/my-feature`
3. **提交更改**：`git commit -m "Add: 新功能"`
4. **推送到分支**：`git push origin feature/my-feature`
5. **创建 Pull Request**

### 代码规范

- **Python**：遵循 PEP 8，使用 `ruff` 格式化
- **提交信息**：使用 Conventional Commits 风格
  - `Add: 新功能`
  - `Fix: 修复 bug`
  - `Docs: 更新文档`
  - `Refactor: 重构代码`
- **测试覆盖**：新功能必须包含测试用例

### 开发环境搭建

```powershell
# 安装开发依赖
pip install -r requirements-dev.txt

# 安装 pre-commit hooks
pre-commit install

# 运行测试
python -m pytest tests/ -q

# 代码格式化
ruff format .
ruff check . --fix
```

---

## 🐛 问题排查

### 常见问题

#### 1. CLI 启动失败

**问题**：`python -m jarvis.cli` 报错 `ModuleNotFoundError`

**解决**：

```powershell
# 确保在项目根目录
cd D:\jarvis

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 重新安装依赖
pip install -r requirements.txt
```

#### 2. Skills 加载失败

**问题**：`python -m jarvis.cli skills` 显示 `❌`

**解决**：

- 检查 `skills/` 目录是否存在
- 检查 Skill 的 `SKILL.md` 和 `main.py` 是否完整
- 查看日志：`logs/jarvis.log`

#### 3. API 连接失败

**问题**：`Connection refused`

**解决**：

```powershell
# 检查 API 服务器是否启动
python -m src.jarvis.api.server

# 检查端口是否被占用
netstat -ano | findstr :8765
```

#### 4. 测试结果不一致

**问题**：本地测试通过，CI 失败

**解决**：

```powershell
# 清理缓存
python scripts/clean_python_cache.py

# 删除 __pycache__
find . -type d -name __pycache__ -exec rm -rf {} +

# 重新运行测试
python -m pytest tests/ -v
```

---

## 📊 版本历史

### v3.2 (2026-04-29)

- ✅ Claude-style CLI 命令对标
- ✅ ReAct Readiness Phase Pack 1 完成
- ✅ Skills 系统完善（100+ Skills）
- ✅ 质量门禁和基准测试

### v3.1 (2026-04-03)

- ✅ 打断功能（语音+键盘）
- ✅ 括号内容跳过朗读
- ✅ 记忆 Markdown 存储

### v3.0

- ✅ 性格系统 + 自我认知 + 工具包 + 记忆

---

## 📄 许可证

MIT License © 2024-2026 J.A.R.V.I.S Project

详见 [LICENSE](LICENSE) 文件。

---

## 🙏 致谢

- **Claude Code**：CLI 设计灵感
- **OpenClaw**：Web UI 和架构参考
- **DeepSeek**：LLM 引擎
- **FunASR**：语音识别
- **Edge TTS**：语音合成

---

## 📧 联系方式

- **Issues**：[GitHub Issues](https://github.com/your-username/jarvis/issues)
- **Discussions**：[GitHub Discussions](https://github.com/your-username/jarvis/discussions)
- **Email**：your-email@example.com

---

<div align="center">

⭐ 如果这个项目对你有帮助，请给一个 Star！

Made with ❤️ by J.A.R.V.I.S Team

</div>
