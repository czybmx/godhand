# 🖐️ GodHand

> 本地 AI 全能代理系统 —— 用自然语言驱动你的电脑

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.x-black?logo=flask)](https://flask.palletsprojects.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-orange)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()

---

## ✨ 简介

**GodHand** 是一个运行在本地的 AI 代理系统，通过 [Ollama](https://ollama.com) 驱动大语言模型，赋予其操控整台电脑的能力。

你只需用自然语言下达指令，GodHand 便会自主规划、循环执行，完成从编写代码、运行命令、操作文件，到控制鼠标键盘的一系列任务——全程无需人工干预。

系统通过浏览器提供实时 Web 界面，所有思考过程、工具调用、执行结果均以流式日志的形式呈现。

---

## 🚀 功能特性

### 🧠 智能 Agent 核心
- 基于 Ollama 的本地 LLM，支持任意兼容模型（默认 `glm-4.6:cloud`）
- 多轮自主循环执行，直至任务完成
- 内建连续错误检测与自动恢复机制
- 支持随时手动停止任务

### 📁 文件系统操作
| 工具 | 功能 |
|------|------|
| `write_file` | 创建或覆盖文件 |
| `read_file` | 读取文件内容（支持 UTF-8 / GBK / Latin-1 多编码自动识别） |
| `edit_file` | 精确行级编辑（替换 / 插入 / 删除） |
| `search_in_file` | 关键词或正则搜索，带上下文行 |
| `list_files` | 列出目录内容（含文件大小、修改时间） |
| `create_folder` | 创建目录 |
| `get_project_tree` | 可视化项目树（自动过滤 node_modules 等） |

### 💻 Shell 命令执行
- 支持 Windows（CMD）、Linux/macOS（Bash）跨平台执行
- 内建命令白名单，覆盖 Python、Node.js、Flutter、Git、Docker 等主流工具链
- 可配置命令超时，防止任务卡死
- 输出自动截断，避免上下文溢出

### 🖱️ GUI 控制（需安装 PyAutoGUI）
- **鼠标**：移动、点击（左/中/右键）、拖拽、滚轮
- **键盘**：文本输入、单键按下、组合键（如 `Ctrl+C`）
- **浏览器**：跨平台打开指定 URL

### 🌐 实时 Web 界面
- Flask + SocketIO 提供 WebSocket 实时通信
- 日志按类型分色显示（thinking / action / system / error / warning）
- Token 用量实时统计（Prompt / Completion / Total）
- 任务启动 / 停止控制按钮

### 📝 完整会话日志
- 每次会话自动生成带时间戳的日志文件，保存于 `logs/` 目录

---

## 📦 安装

### 前置要求

- Python 3.10+
- [Ollama](https://ollama.com/download) 已安装并运行
- 本地已拉取目标模型，例如：
  ```bash
  ollama pull glm4:latest
  ```

### 克隆项目

```bash
git clone https://github.com/your-username/godhand.git
cd godhand
```

### 安装依赖

```bash
pip install flask flask-socketio ollama pyautogui
```

> GUI 控制功能需要 `pyautogui`，若无图形界面环境可选择不安装，其他功能不受影响。

---

## ⚙️ 配置

所有配置均通过**环境变量**控制，无需修改源码：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama 服务地址 |
| `MODEL_NAME` | `glm-4.6:cloud` | 使用的模型名称 |
| `WORKSPACE_DIR` | `workspace` | Agent 工作目录 |
| `MAX_ITERATIONS` | `100000000` | 最大循环次数 |
| `COMMAND_TIMEOUT` | `120000` | 单条命令超时（秒） |
| `SECRET_KEY` | `fairy_agent_secret_key` | Flask 密钥 |

**示例（Linux/macOS）：**
```bash
export MODEL_NAME="qwen2.5-coder:7b"
export WORKSPACE_DIR="./my_project"
```

**示例（Windows CMD）：**
```cmd
set MODEL_NAME=qwen2.5-coder:7b
set WORKSPACE_DIR=.\my_project
```

---

## 🎮 使用方法

### 启动服务

```bash
python run.py
```

启动后终端将显示：

```
============================================================
GodHand Agent System
============================================================
日志文件: logs/agent_session_20250425_120000.txt
工作目录: workspace
Ollama: http://localhost:11434
模型: glm-4.6:cloud
最大迭代: 100000000
命令超时: 120000秒
GUI可用: True
============================================================
```

### 访问界面

打开浏览器，访问：

```
http://localhost:5000
```

### 下达任务

在输入框中用自然语言描述任务，例如：

```
用 Python 写一个 FastAPI 应用，包含用户注册和登录接口，使用 SQLite 存储数据，并运行测试验证功能正常。
```

GodHand 将自动完成：规划 → 创建文件 → 安装依赖 → 编写代码 → 执行测试 → 汇报结果。

### 健康检查 API

```
GET http://localhost:5000/health
```

返回：
```json
{
  "status": "ok",
  "ollama_connected": true,
  "workspace": "workspace",
  "model": "glm-4.6:cloud"
}
```

---

## 🏗️ 项目结构

```
godhand/
├── run.py              # 主程序（Agent 核心 + Web 服务）
├── workspace/          # Agent 工作目录（自动创建）
├── logs/               # 会话日志（自动创建）
│   └── agent_session_YYYYMMDD_HHMMSS.txt
└── templates/
    └── index.html      # Web 前端界面
```

---

## 🔧 支持的工具链

GodHand 内建白名单，默认支持以下命令：

| 类别 | 工具 |
|------|------|
| Python | `python` `pip` `pytest` `black` `mypy` `poetry` |
| Node.js | `node` `npm` `npx` `yarn` `pnpm` `jest` `eslint` |
| 移动开发 | `flutter` `dart` `adb` `gradle` |
| 版本控制 | `git` `gh` `svn` |
| 容器 | `docker` `docker-compose` `kubectl` |
| 编译 | `gcc` `g++` `go` `rustc` `cargo` `java` `javac` |
| 数据库 | `mysql` `psql` `sqlite3` `redis-cli` `mongo` |
| 网络 | `curl` `wget` `ssh` `scp` |
| Shell | `bash` `sh` `powershell` `cmd` |

---

## 🛡️ 安全说明

- 路径访问限制在 `WORKSPACE_DIR` 范围内，防止越权访问
- Windows 下额外允许访问用户目录和 Program Files
- 命令白名单记录日志（非阻断式），可根据需要调整
- 建议在隔离的虚拟机或容器内运行，以获得最大安全保障

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交改动：`git commit -m 'Add your feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 发起 Pull Request

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源。

---

<p align="center">
  Made with ❤️ · Powered by Ollama · <b>GodHand</b>
</p>


# 🖐️ GodHand

> A local AI agent that controls your entire computer through natural language

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.x-black?logo=flask)](https://flask.palletsprojects.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-orange)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()

---

## ✨ Overview

**GodHand** is a fully local AI agent system powered by [Ollama](https://ollama.com). You describe what you want in plain language, and GodHand autonomously plans and executes the task — writing code, running shell commands, managing files, controlling your mouse and keyboard — until the job is done.

A real-time web interface streams every thought, tool call, and result directly to your browser as it happens.

---

## 🚀 Features

### 🧠 Autonomous Agent Core
- Driven by a local LLM via Ollama (default: `glm-4.6:cloud`; any compatible model works)
- Multi-turn self-looping execution until task completion
- Built-in consecutive error detection and automatic recovery
- Manual stop at any time via the web UI

### 📁 File System Operations
| Tool | Description |
|------|-------------|
| `write_file` | Create or overwrite a file |
| `read_file` | Read file content (auto-detects UTF-8 / GBK / Latin-1 encoding) |
| `edit_file` | Precise line-level editing (replace / insert / delete) |
| `search_in_file` | Keyword or regex search with context lines |
| `list_files` | List directory contents with size and modification time |
| `create_folder` | Create a directory |
| `get_project_tree` | Visualize project structure (auto-filters node_modules, etc.) |

### 💻 Shell Command Execution
- Cross-platform: CMD on Windows, Bash on Linux/macOS
- Built-in command allowlist covering Python, Node.js, Flutter, Git, Docker, and more
- Configurable per-command timeout to prevent hangs
- Output auto-truncated to prevent context overflow

### 🖱️ GUI Control (requires PyAutoGUI)
- **Mouse**: move, click (left/middle/right), drag, scroll
- **Keyboard**: type text, press keys, trigger hotkeys (e.g. `Ctrl+C`)
- **Browser**: cross-platform URL opener

### 🌐 Real-Time Web Interface
- Flask + SocketIO for live WebSocket streaming
- Color-coded log types: `thinking` / `action` / `system` / `error` / `warning`
- Live token usage stats (Prompt / Completion / Total)
- Start and Stop task controls

### 📝 Session Logging
- Each session auto-generates a timestamped log file under `logs/`

---

## 📦 Installation

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/download) installed and running
- A model pulled locally, e.g.:
  ```bash
  ollama pull qwen2.5-coder:7b
  ```

### Clone the Repository

```bash
git clone https://github.com/your-username/godhand.git
cd godhand
```

### Install Dependencies

```bash
pip install flask flask-socketio ollama pyautogui
```

> `pyautogui` is only required for GUI control features. All other functionality works without it.

---

## ⚙️ Configuration

All settings are controlled via **environment variables** — no source code changes needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama service URL |
| `MODEL_NAME` | `glm-4.6:cloud` | Model to use |
| `WORKSPACE_DIR` | `workspace` | Agent working directory |
| `MAX_ITERATIONS` | `100000000` | Maximum agent loop iterations |
| `COMMAND_TIMEOUT` | `120000` | Per-command timeout in seconds |
| `SECRET_KEY` | `fairy_agent_secret_key` | Flask session secret |

**Linux/macOS:**
```bash
export MODEL_NAME="qwen2.5-coder:7b"
export WORKSPACE_DIR="./my_project"
```

**Windows CMD:**
```cmd
set MODEL_NAME=qwen2.5-coder:7b
set WORKSPACE_DIR=.\my_project
```

---

## 🎮 Usage

### Start the Server

```bash
python run.py
```

You'll see:

```
============================================================
GodHand Agent System
============================================================
Log file:   logs/agent_session_20250425_120000.txt
Workspace:  workspace
Ollama:     http://localhost:11434
Model:      glm-4.6:cloud
Max iters:  100000000
Timeout:    120000s
GUI:        True
============================================================
```

### Open the Interface

Navigate to:

```
http://localhost:5000
```

### Give a Task

Type your task in natural language, for example:

```
Build a FastAPI application with user registration and login endpoints,
store data in SQLite, and run tests to verify everything works.
```

GodHand will autonomously: plan → create files → install dependencies → write code → run tests → report results.

### Health Check Endpoint

```
GET http://localhost:5000/health
```

Response:
```json
{
  "status": "ok",
  "ollama_connected": true,
  "workspace": "workspace",
  "model": "glm-4.6:cloud"
}
```

---

## 🏗️ Project Structure

```
godhand/
├── run.py              # Main application (Agent core + Web server)
├── workspace/          # Agent working directory (auto-created)
├── logs/               # Session logs (auto-created)
│   └── agent_session_YYYYMMDD_HHMMSS.txt
└── templates/
    └── index.html      # Web frontend
```

---

## 🔧 Supported Toolchains

GodHand's built-in allowlist covers:

| Category | Tools |
|----------|-------|
| Python | `python` `pip` `pytest` `black` `mypy` `poetry` |
| Node.js | `node` `npm` `npx` `yarn` `pnpm` `jest` `eslint` |
| Mobile | `flutter` `dart` `adb` `gradle` |
| Version Control | `git` `gh` `svn` |
| Containers | `docker` `docker-compose` `kubectl` |
| Compilers | `gcc` `g++` `go` `rustc` `cargo` `java` `javac` |
| Databases | `mysql` `psql` `sqlite3` `redis-cli` `mongo` |
| Network | `curl` `wget` `ssh` `scp` |
| Shells | `bash` `sh` `powershell` `cmd` |

---

## 🛡️ Security Notes

- File access is sandboxed to `WORKSPACE_DIR` by default
- On Windows, user home and Program Files directories are additionally permitted
- Command allowlist violations are logged (non-blocking) — tighten as needed
- For maximum isolation, consider running inside a VM or container

---

## 🤝 Contributing

Issues and pull requests are welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

Released under the [MIT License](LICENSE).

---

<p align="center">
  Made with ❤️ · Powered by Ollama · <b>GodHand</b>
</p>
