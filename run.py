import os
import sys
import json
import threading
import time
import subprocess
import re
import shutil
import traceback
from datetime import datetime
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import logging
from ollama import Client

# ==========================================
# 依赖检查与 GUI 初始化
# ==========================================
try:
    import pyautogui
    pyautogui.PAUSE = 0.5
    pyautogui.FAILSAFE = False  # 【修复】启用安全模式,防止失控
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    print("警告: 未安装 pyautogui，鼠标/键盘控制功能将不可用。请运行 `pip install pyautogui`。")
except Exception as e:
    GUI_AVAILABLE = False
    print(f"警告: pyautogui 初始化失败 ({e})，可能无图形界面环境。")

# ==========================================
# 配置与初始化
# ==========================================

# 创建日志目录
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 获取当前时间戳用于日志文件名
SESSION_START_TIME = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE_PATH = os.path.join(LOG_DIR, f"agent_session_{SESSION_START_TIME}.txt")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fairy_agent_secret_key')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

RAW_OLLAMA_URL = os.environ.get('OLLAMA_URL', "http://localhost:11434")
MODEL_NAME = os.environ.get('MODEL_NAME', "glm-4.6:cloud")
WORKSPACE_DIR = os.environ.get('WORKSPACE_DIR', "workspace")  # 【修复】允许通过环境变量配置
MAX_ITERATIONS = int(os.environ.get('MAX_ITERATIONS', '100000000'))  # 【修复】默认值从100万改为100,避免无限循环
COMMAND_TIMEOUT = int(os.environ.get('COMMAND_TIMEOUT', '120000'))  # 【修复】新增命令超时设置(20分钟)

# 【修复】平台检测
IS_WINDOWS = sys.platform.startswith('win')
IS_LINUX = sys.platform.startswith('linux')
IS_MACOS = sys.platform.startswith('darwin')

# 【优化】根据平台动态构建白名单
ALLOWED_COMMANDS = {
    # Python工具链
    'pip', 'pip3', 'python', 'python3', 'pytest', 'black', 'isort', 
    'flake8', 'mypy', 'pylint', 'coverage', 'tox', 'poetry', 'pipenv',
    'virtualenv', 'venv', 'bandit', 'radon', 'autopep8', 'yapf',
    'sphinx-build', 'pdoc', 'pydoc', 'ipython', 'jupyter',
    
    # Node.js工具链
    'node', 'npm', 'npx', 'yarn', 'pnpm', 'nvm', 'jest', 'mocha', 
    'eslint', 'prettier', 'webpack', 'vite', 'rollup', 'parcel',
    
    # 移动开发
    'flutter', 'dart', 'adb', 'fastlane', 'gradle', 'gradlew',
    
    # 版本控制
    'git', 'gh', 'svn', 'hg',
    
    # 基础Shell命令
    'echo', 'cat', 'ls', 'pwd', 'mkdir', 'touch', 'tree', 'cd', 
    'cp', 'mv', 'rm', 'rmdir', 'find', 'grep', 'chmod', 'chown',
    'head', 'tail', 'less', 'more', 'nano', 'vim', 'vi', 'emacs',
    'wc', 'diff', 'sort', 'uniq', 'sed', 'awk', 'tar', 'zip', 'unzip',
    'gzip', 'gunzip', 'bzip2', 'bunzip2', '7z',
    
    # 网络工具
    'curl', 'wget', 'ping', 'ssh', 'scp', 'rsync', 'nc', 'telnet',
    
    # 编译工具
    'make', 'cmake', 'gcc', 'g++', 'clang', 'javac', 'java', 'go', 
    'rustc', 'cargo',
    
    # 容器与云
    'docker', 'docker-compose', 'kubectl', 'helm', 'terraform',
    
    # 数据库
    'mysql', 'psql', 'sqlite3', 'redis-cli', 'mongo', 'mongosh',
    
    # 系统监控
    'top', 'htop', 'ps', 'kill', 'killall', 'df', 'du', 'free',
    'uptime', 'who', 'w', 'last', 'history',
    
    # Windows特定
    'dir', 'type', 'copy', 'move', 'del', 'ren', 'cls', 'tasklist',
    'taskkill', 'where', 'findstr', 'robocopy',
    
    # 脚本执行
    'bash', 'sh', 'zsh', 'fish', 'cmd', 'powershell', 'pwsh',
    
    # 文件打开
    'start', 'open', 'xdg-open',
    
    # 浏览器
    'chrome', 'google-chrome', 'firefox', 'safari', 'microsoft-edge',
    'brave', 'opera',
    
    # 其他工具
    'date', 'cal', 'bc', 'expr', 'env', 'printenv', 'export',
    'alias', 'which', 'whereis', 'man', 'info', 'help',
}

def get_ollama_host():
    """【修复】更健壮的URL解析"""
    url = RAW_OLLAMA_URL.rstrip('/')
    if '/api' in url:
        return url.split('/api')[0]
    return url

HOST_URL = get_ollama_host()

# 【修复】添加连接重试机制
def init_ollama_client(max_retries=3):
    """初始化Ollama客户端,带重试机制"""
    for i in range(max_retries):
        try:
            client = Client(host=HOST_URL)
            # 测试连接
            client.list()
            logger.info(f"成功连接到 Ollama: {HOST_URL}")
            return client
        except Exception as e:
            logger.warning(f"连接Ollama失败 (尝试 {i+1}/{max_retries}): {e}")
            if i < max_retries - 1:
                time.sleep(2)
            else:
                logger.error("无法连接到Ollama服务器")
                return None
    return None

ollama_client = init_ollama_client()

if not os.path.exists(WORKSPACE_DIR):
    os.makedirs(WORKSPACE_DIR)

agent_lock = threading.Lock()
agent_stop_flag = threading.Event()  # 【新增】停止标志

# ==========================================
# 日志与监控增强
# ==========================================

total_prompt_tokens = 0
total_completion_tokens = 0

def write_log_to_file(sender, message, log_type='info'):
    """将日志写入文件"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] [{sender}] [{log_type.upper()}] {message}\n"
    try:
        with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"写入日志文件失败: {e}")

def emit_log(sender, msg, typ='info'):
    """发送日志到前端并写入文件"""
    write_log_to_file(sender, msg, typ)
    try:
        socketio.emit('log', {'sender': sender, 'message': msg, 'type': typ})
    except Exception as e:
        logger.error(f"发送日志到前端失败: {e}")
    logger.info(f"[{sender}] [{typ}] {msg}")

def update_token_stats(prompt_count, completion_count):
    """更新并发送 token 统计"""
    global total_prompt_tokens, total_completion_tokens
    total_prompt_tokens += prompt_count
    total_completion_tokens += completion_count
    
    stats = {
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens
    }
    try:
        socketio.emit('token_stats', stats)
    except Exception as e:
        logger.error(f"发送token统计失败: {e}")

# ==========================================
# 增强版 AgentAction
# ==========================================

class AgentAction:
    @staticmethod
    def _safe_path(path):
        """【修复】更安全的路径处理"""
        if not path:
            return WORKSPACE_DIR
        
        # 【修复】处理绝对路径的情况
        if os.path.isabs(path):
            # 如果是Windows系统,允许访问项目路径和Flutter路径
            if IS_WINDOWS:
                allowed_roots = [
                    WORKSPACE_DIR,
                    'C:\\Users',  # 允许访问用户目录
                    'C:\\Program Files',
                    os.path.expanduser('~')  # 用户主目录
                ]
                # 检查路径是否在允许的根目录下
                real_path = os.path.realpath(path)
                for allowed_root in allowed_roots:
                    if real_path.startswith(os.path.realpath(allowed_root)):
                        return path
            # 如果不在允许列表中,返回workspace下的相对路径
            logger.warning(f"尝试访问受限路径: {path}, 已转换为workspace下的相对路径")
            return os.path.join(WORKSPACE_DIR, os.path.basename(path))
        
        # 相对路径处理
        full_path = os.path.join(WORKSPACE_DIR, path)
        
        # 规范化路径
        full_path = os.path.normpath(full_path)
        
        return full_path

    @staticmethod
    def write_file(path, content):
        """【优化】写文件,增加错误处理"""
        try:
            full_path = AgentAction._safe_path(path)
            
            # 创建父目录
            parent_dir = os.path.dirname(full_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            
            # 写入文件
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            file_size = len(content.encode('utf-8'))
            return f"成功写入: {path} ({file_size} 字节, {len(content)} 字符)"
        except UnicodeEncodeError as e:
            return f"编码错误: {str(e)}"
        except PermissionError as e:
            return f"权限不足: {str(e)}"
        except Exception as e:
            return f"写入失败: {str(e)}"

    @staticmethod
    def create_folder(path):
        """创建目录"""
        try:
            full_path = AgentAction._safe_path(path)
            os.makedirs(full_path, exist_ok=True)
            return f"成功创建目录: {path}"
        except Exception as e:
            return f"创建目录失败: {str(e)}"

    @staticmethod
    def list_files(path="."):
        """【优化】列出目录,增加更多信息"""
        try:
            full_path = AgentAction._safe_path(path)
            
            if not os.path.exists(full_path):
                return json.dumps({"error": "路径不存在"}, ensure_ascii=False)
            
            if not os.path.isdir(full_path):
                return json.dumps({"error": "目标不是目录"}, ensure_ascii=False)
            
            items = []
            for item in os.listdir(full_path):
                if item.startswith('.'):
                    continue
                    
                item_path = os.path.join(full_path, item)
                is_dir = os.path.isdir(item_path)
                
                item_info = {
                    "name": item,
                    "type": "directory" if is_dir else "file",
                    "size": 0 if is_dir else os.path.getsize(item_path)
                }
                
                # 添加修改时间
                try:
                    mtime = os.path.getmtime(item_path)
                    item_info["modified"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
                
                items.append(item_info)
            
            # 按类型和名称排序
            items.sort(key=lambda x: (x['type'] != 'directory', x['name']))
            
            return json.dumps({
                "path": path,
                "absolute_path": full_path,
                "items": items,
                "count": len(items)
            }, ensure_ascii=False, indent=2)
        except PermissionError as e:
            return json.dumps({"error": f"权限不足: {str(e)}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"列出目录失败: {str(e)}"}, ensure_ascii=False)

    @staticmethod
    def read_file(path):
        """【优化】读取文件,增加大文件处理"""
        try:
            full_path = AgentAction._safe_path(path)
            
            if not os.path.exists(full_path):
                return f"错误: 文件不存在 - {path}"
            
            if not os.path.isfile(full_path):
                return f"错误: 不是文件 - {path}"
            
            # 检查文件大小
            file_size = os.path.getsize(full_path)
            max_size = 10 * 1024 * 1024  # 10MB
            
            if file_size > max_size:
                return f"错误: 文件过大 ({file_size} 字节), 超过限制 ({max_size} 字节). 请使用其他方式处理大文件。"
            
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            
            for encoding in encodings:
                try:
                    with open(full_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    return content
                except UnicodeDecodeError:
                    continue
            
            # 如果所有编码都失败,尝试二进制读取
            with open(full_path, 'rb') as f:
                content = f.read()
            return f"警告: 无法以文本方式读取,二进制内容长度: {len(content)} 字节"
            
        except PermissionError as e:
            return f"权限错误: {str(e)}"
        except Exception as e:
            return f"读取失败: {str(e)}"

    @staticmethod
    def edit_file(path, start_line=None, end_line=None, new_content="", mode="replace"):
        """【修复】文件编辑,增加更多错误处理"""
        try:
            full_path = AgentAction._safe_path(path)
            
            if not os.path.exists(full_path):
                return f"错误: 文件不存在 - {path}"
            
            # 读取文件
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(full_path, 'r', encoding='gbk') as f:
                    lines = f.readlines()
            
            total_lines = len(lines)
            
            # 处理行号
            if start_line is None:
                start_line = 1
            if end_line is None:
                end_line = total_lines
            
            # 转换为0-based索引
            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, end_line)
            
            if start_idx > total_lines:
                return f"错误: 起始行 {start_line} 超出文件范围 (共 {total_lines} 行)"
            
            # 确保新内容以换行符结尾
            if new_content and not new_content.endswith('\n'):
                new_content += '\n'
            
            # 根据模式编辑
            if mode == "replace":
                new_lines = lines[:start_idx] + [new_content] + lines[end_idx:]
            elif mode == "insert_after":
                new_lines = lines[:end_idx] + [new_content] + lines[end_idx:]
            elif mode == "delete":
                new_lines = lines[:start_idx] + lines[end_idx:]
            else:
                return f"错误: 未知的编辑模式 - {mode}"
            
            # 写回文件
            with open(full_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            affected_lines = end_idx - start_idx
            return f"编辑成功: {path} (模式: {mode}, 影响行: {start_line}-{end_line}, 共 {affected_lines} 行)"
            
        except Exception as e:
            return f"编辑失败: {str(e)}\n{traceback.format_exc()}"

    @staticmethod
    def search_in_file(path, query, regex=False, context_lines=3):
        """【优化】文件内搜索"""
        try:
            full_path = AgentAction._safe_path(path)
            
            if not os.path.exists(full_path):
                return json.dumps({"error": f"文件不存在: {path}"}, ensure_ascii=False)
            
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(full_path, 'r', encoding='gbk') as f:
                    lines = f.readlines()
            
            matches = []
            pattern = re.compile(query) if regex else None
            
            for i, line in enumerate(lines, 1):
                found = False
                if regex:
                    if pattern.search(line):
                        found = True
                else:
                    if query in line:
                        found = True
                
                if found:
                    # 获取上下文
                    start = max(0, i - context_lines - 1)
                    end = min(len(lines), i + context_lines)
                    context = ''.join(lines[start:end])
                    
                    matches.append({
                        "line_number": i,
                        "line": line.rstrip(),
                        "context": context
                    })
            
            result = {
                "path": path,
                "query": query,
                "regex": regex,
                "matches_count": len(matches),
                "matches": matches[:50]  # 限制返回数量
            }
            
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            return json.dumps({"error": f"搜索失败: {str(e)}"}, ensure_ascii=False)

    @staticmethod
    def execute_shell(cmd):
        """【修复】执行Shell命令,增加超时和安全检查"""
        try:
            # 提取命令的第一个词
            cmd_parts = cmd.strip().split()
            if not cmd_parts:
                return "错误: 空命令"
            
            base_cmd = cmd_parts[0].lower()
            
            # 【修复】处理Windows特殊命令
            if IS_WINDOWS:
                # 处理cd命令(Windows下需要特殊处理)
                if base_cmd == 'cd':
                    # 【重要修复】检测是否为复合命令（如 cd workspace && dir）
                    # 如果是复合命令，不要强制格式化为 cd /d "..."，否则会导致命令参数错误
                    # 检查常见的Shell链接符号
                    is_chain = any(op in cmd for op in ['&&', '||', '|', '>', ';'])
                    
                    if len(cmd_parts) == 1:
                        cmd = 'cd'
                    elif is_chain:
                        # 如果是链式命令，保持原样，让 Shell 解析执行
                        # 例如: "cd workspace && dir" -> 保持不变
                        pass
                    else:
                        # cd到指定目录,使用/d参数
                        # 仅当这是纯粹的 cd 命令时才应用格式化以获取路径反馈
                        target_dir = ' '.join(cmd_parts[1:])
                        cmd = f'cd /d "{target_dir}" && cd'
                
                # 处理PowerShell命令
                if base_cmd in ['powershell', 'pwsh']:
                    # 确保使用正确的PowerShell路径
                    pass
            
            # 安全检查:是否在白名单中
            if base_cmd not in ALLOWED_COMMANDS:
                # 检查是否是路径(可能是可执行文件)
                if not (os.path.exists(base_cmd) or os.path.sep in base_cmd):
                    logger.warning(f"命令不在白名单中: {base_cmd}")
                    # 不阻止,但记录警告
            
            logger.info(f"执行命令: {cmd}")
            
            # 【修复】使用更合适的shell设置
            if IS_WINDOWS:
                # Windows下使用cmd
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=WORKSPACE_DIR,
                    text=True,
                    encoding='utf-8',
                    errors='ignore'  # 忽略编码错误
                )
            else:
                # Linux/Mac下使用bash
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=WORKSPACE_DIR,
                    text=True,
                    executable='/bin/bash'
                )
            
            # 【修复】添加超时机制
            try:
                stdout, stderr = process.communicate(timeout=COMMAND_TIMEOUT)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return f"命令超时: {cmd} (超过 {COMMAND_TIMEOUT} 秒)\nstdout:\n{stdout}\nstderr:\n{stderr}"
            
            # 【优化】格式化输出
            result = f"stdout:\n{stdout}\n\nstderr:\n{stderr}\n\nreturn code: {returncode}"
            
            # 限制输出长度
            max_output = 5000
            if len(result) > max_output:
                result = result[:max_output] + f"\n\n...(输出已截断,总长度: {len(result)} 字符)"
            
            return result
            
        except FileNotFoundError as e:
            return f"命令不存在: {str(e)}"
        except PermissionError as e:
            return f"权限不足: {str(e)}"
        except Exception as e:
            return f"执行失败: {str(e)}\n{traceback.format_exc()}"

    @staticmethod
    def mouse_control(action, x=None, y=None, duration=0.5, button="left"):
        """【修复】鼠标控制"""
        if not GUI_AVAILABLE:
            return "错误: PyAutoGUI 不可用 (可能无图形界面或未安装)"
        
        try:
            if action == "move":
                if x is None or y is None:
                    return "错误: move 操作需要 x 和 y 坐标"
                pyautogui.moveTo(x, y, duration=duration)
                return f"鼠标移动到: ({x}, {y})"
            
            elif action == "click":
                if x is not None and y is not None:
                    pyautogui.click(x, y, button=button)
                    return f"点击: ({x}, {y}), 按钮: {button}"
                else:
                    pyautogui.click(button=button)
                    return f"点击当前位置, 按钮: {button}"
            
            elif action == "drag":
                if x is None or y is None:
                    return "错误: drag 操作需要 x 和 y 坐标"
                pyautogui.drag(x, y, duration=duration, button=button)
                return f"拖拽到: ({x}, {y})"
            
            elif action == "scroll":
                clicks = int(y) if y is not None else 1
                pyautogui.scroll(clicks)
                return f"滚动: {clicks} 次"
            
            else:
                return f"错误: 未知的鼠标操作 - {action}"
                
        except Exception as e:
            return f"鼠标操作失败: {str(e)}"

    @staticmethod
    def keyboard_control(action, text=None, hotkey=None):
        """【修复】键盘控制"""
        if not GUI_AVAILABLE:
            return "错误: PyAutoGUI 不可用"
        
        try:
            if action == "type":
                if not text:
                    return "错误: type 操作需要 text 参数"
                pyautogui.write(text, interval=0.05)
                return f"输入文本: {text[:50]}..."
            
            elif action == "hotkey":
                if not hotkey or not isinstance(hotkey, list):
                    return "错误: hotkey 操作需要 hotkey 数组参数"
                pyautogui.hotkey(*hotkey)
                return f"组合键: {'+'.join(hotkey)}"
            
            elif action == "press":
                if not text:
                    return "错误: press 操作需要 text 参数(按键名)"
                pyautogui.press(text)
                return f"按键: {text}"
            
            else:
                return f"错误: 未知的键盘操作 - {action}"
                
        except Exception as e:
            return f"键盘操作失败: {str(e)}"

    @staticmethod
    def browser_control(action, url=None):
        """【修复】浏览器控制,支持跨平台"""
        try:
            if action == "open":
                if not url:
                    return "错误: open 操作需要 url 参数"
                
                # 跨平台打开浏览器
                if IS_WINDOWS:
                    cmd = f'start "" "{url}"'
                elif IS_MACOS:
                    cmd = f'open "{url}"'
                else:  # Linux
                    cmd = f'xdg-open "{url}"'
                
                result = AgentAction.execute_shell(cmd)
                return f"打开浏览器: {url}\n{result}"
            
            elif action == "close":
                # 关闭浏览器比较复杂,需要根据平台处理
                if IS_WINDOWS:
                    # 尝试关闭常见浏览器进程
                    browsers = ['chrome.exe', 'firefox.exe', 'msedge.exe']
                    results = []
                    for browser in browsers:
                        cmd = f'taskkill /F /IM {browser}'
                        result = AgentAction.execute_shell(cmd)
                        results.append(f"{browser}: {result}")
                    return "尝试关闭浏览器:\n" + "\n".join(results)
                else:
                    return "错误: Linux/Mac 下关闭浏览器需要使用其他方法"
            
            else:
                return f"错误: 未知的浏览器操作 - {action}"
                
        except Exception as e:
            return f"浏览器操作失败: {str(e)}"

    @staticmethod
    def get_project_tree(max_depth=3):
        """【新增】获取项目目录树"""
        try:
            tree_lines = []
            
            def build_tree(path, prefix="", depth=0):
                if depth > max_depth:
                    return
                
                try:
                    items = sorted(os.listdir(path))
                    # 过滤隐藏文件和常见忽略目录
                    items = [
                        i for i in items 
                        if not i.startswith('.') and i not in [
                            'node_modules', '__pycache__', 'venv', '.git',
                            'build', 'dist', '.idea', '.vscode'
                        ]
                    ]
                    
                    for i, item in enumerate(items):
                        is_last = (i == len(items) - 1)
                        item_path = os.path.join(path, item)
                        
                        # 绘制树形结构
                        connector = "└── " if is_last else "├── "
                        tree_lines.append(f"{prefix}{connector}{item}")
                        
                        if os.path.isdir(item_path):
                            extension = "    " if is_last else "│   "
                            build_tree(item_path, prefix + extension, depth + 1)
                except PermissionError:
                    pass
            
            tree_lines.append(WORKSPACE_DIR)
            build_tree(WORKSPACE_DIR)
            
            return "\n".join(tree_lines)
            
        except Exception as e:
            return f"获取项目树失败: {str(e)}"

# ==========================================
# Tools Schema 定义
# ==========================================

TOOLS_SCHEMA = [
    # 文件操作
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建或覆盖文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径(相对于workspace)"},
                    "content": {"type": "string", "description": "文件内容"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "创建目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出目录内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": ".", "description": "目录路径"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "局部编辑文件(推荐用于修改而非重写)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "start_line": {"type": "integer", "description": "起始行号(从1开始)"},
                    "end_line": {"type": "integer", "description": "结束行号"},
                    "new_content": {"type": "string", "description": "新内容"},
                    "mode": {
                        "type": "string",
                        "enum": ["replace", "insert_after", "delete"],
                        "default": "replace",
                        "description": "编辑模式"
                    }
                },
                "required": ["path", "new_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_file",
            "description": "在文件内搜索关键词或正则表达式",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "query": {"type": "string", "description": "搜索关键词"},
                    "regex": {"type": "boolean", "default": False, "description": "是否使用正则"},
                    "context_lines": {"type": "integer", "default": 3, "description": "上下文行数"}
                },
                "required": ["path", "query"]
            }
        }
    },
    
    # 系统控制
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": "执行Shell/Bash/CMD命令。支持系统维护、依赖安装、编译构建等。长时间任务建议使用后台运行(&或nohup)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string", "description": "要执行的命令"}
                },
                "required": ["cmd"]
            }
        }
    },
    
    # GUI控制
    {
        "type": "function",
        "function": {
            "name": "mouse_control",
            "description": "控制鼠标(移动/点击/拖拽/滚动)。坐标原点(0,0)在屏幕左上角。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["move", "click", "drag", "scroll"],
                        "description": "鼠标操作类型"
                    },
                    "x": {"type": "number", "description": "X坐标"},
                    "y": {"type": "number", "description": "Y坐标"},
                    "duration": {"type": "number", "default": 0.5, "description": "动作持续时间(秒)"},
                    "button": {
                        "type": "string",
                        "default": "left",
                        "enum": ["left", "right", "middle"],
                        "description": "鼠标按钮"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "keyboard_control",
            "description": "控制键盘(输入文本/按键/组合键)",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["type", "hotkey", "press"],
                        "description": "键盘操作类型"
                    },
                    "text": {"type": "string", "description": "要输入的文本或按键名"},
                    "hotkey": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "组合键数组,如['ctrl','c']"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_control",
            "description": "打开或关闭浏览器",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["open", "close"],
                        "description": "浏览器操作"
                    },
                    "url": {"type": "string", "description": "要打开的URL"}
                },
                "required": ["action"]
            }
        }
    },
    
    # 项目管理
    {
        "type": "function",
        "function": {
            "name": "get_project_tree",
            "description": "获取项目目录树结构(自动过滤node_modules等)",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

# ==========================================
# Agent 核心逻辑
# ==========================================

def safe_parse_args(raw):
    """【修复】更健壮的参数解析"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}, 原始内容: {raw}")
            return {}
    return {}

def run_agent_background(prompt):
    """Agent主循环"""
    global total_prompt_tokens, total_completion_tokens
    total_prompt_tokens = 0
    total_completion_tokens = 0
    
    # 重置停止标志
    agent_stop_flag.clear()

    if not ollama_client:
        emit_log('Error', 'Ollama客户端未初始化,请检查连接', 'error')
        return

    try:
        socketio.emit('agent_status', {'status': 'active'})
        
        # ==========================================
        # 系统 Prompt
        # ==========================================
        workspace_files = [
            f for f in os.listdir(WORKSPACE_DIR) 
            if not f.startswith('.')
        ]
        is_empty = len(workspace_files) == 0
        mode = "【从零开发】" if is_empty else "【迭代/维护/全能辅助】"
        
        # 【优化】更详细的系统提示
        sys_prompt = f"""你是 Fairy,一个嵌入在电脑中的全能 AI 助手。

当前模式: {mode}
工作空间: {WORKSPACE_DIR}
操作系统: {'Windows' if IS_WINDOWS else 'Linux' if IS_LINUX else 'macOS'}
可用工具: 文件操作、Shell命令、GUI控制、浏览器控制

### 核心能力:
1. **全栈开发**: 熟练使用Python/JS/Flutter等,优先使用edit_file而非write_file
2. **系统控制**: execute_shell可执行任何命令(pip install, git, flutter等)
3. **GUI交互**: 通过mouse_control和keyboard_control操作图形界面
4. **浏览器**: browser_control打开网页,execute_shell配合curl/wget获取数据
5. **智能判断**: 长耗时任务使用后台运行,避免超时

### 工作原则:
- 优先使用edit_file修改文件(更精确更安全)
- 命令执行前考虑超时(当前限制{COMMAND_TIMEOUT}秒)
- 遇到错误要分析原因,不要重复相同操作
- 完成任务后明确输出"任务完成"
- 保持高效简洁,避免冗余操作

### 当前工作空间状态:
{f"空目录,准备从零开始" if is_empty else f"已有{len(workspace_files)}个文件/目录"}
"""

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt}
        ]

        iteration = 0
        completed = False
        consecutive_errors = 0  # 【新增】连续错误计数

        while not completed and iteration < MAX_ITERATIONS and not agent_stop_flag.is_set():
            iteration += 1
            emit_log('System', f"--- 第 {iteration} 轮 ---", 'system')

            try:
                # 【修复】添加重试机制
                max_retries = 3
                response = None
                
                for retry in range(max_retries):
                    try:
                        response = ollama_client.chat(
                            model=MODEL_NAME,
                            messages=messages,
                            tools=TOOLS_SCHEMA,
                            stream=False
                        )
                        break
                    except Exception as e:
                        if retry < max_retries - 1:
                            logger.warning(f"Ollama调用失败,重试 {retry+1}/{max_retries}: {e}")
                            time.sleep(2)
                        else:
                            raise
                
                if not response:
                    emit_log('Error', 'Ollama响应失败', 'error')
                    break

                # 提取Token信息
                prompt_count = response.get('prompt_eval_count', 0)
                completion_count = response.get('eval_count', 0)
                update_token_stats(prompt_count, completion_count)

                msg = response['message']
                content = msg.get('content', '').strip()
                tool_calls = msg.get('tool_calls', [])

                # 【修复】更好的日志输出
                if content:
                    log_type = 'thinking' if tool_calls else 'final'
                    emit_log('Agent', content, log_type)

                # 将AI回复加入历史
                assistant_msg = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                # 【新增】检查是否主动完成
                if not tool_calls:
                    # 没有工具调用,检查是否表示完成
                    completion_keywords = [
                        "任务完成", "完成了", "已完成", "构建完成",
                        "task completed", "done", "finished"
                    ]
                    if any(kw in content.lower() for kw in completion_keywords):
                        completed = True
                        emit_log('System', "检测到任务完成标志", 'system')
                        break
                    
                    # 【新增】如果连续多轮没有工具调用,可能陷入循环
                    if iteration > 100000:
                        emit_log('Warning', "多轮未使用工具,可能需要人工介入", 'warning')

                # 执行工具调用
                if tool_calls:
                    consecutive_errors = 0  # 重置错误计数
                    
                    for tc in tool_calls:
                        if agent_stop_flag.is_set():
                            break
                            
                        func = tc['function']
                        name = func['name']
                        args = safe_parse_args(func['arguments'])

                        emit_log('Tool', f"调用: {name}({json.dumps(args, ensure_ascii=False)})", 'action')

                        res = ""
                        try:
                            # 【优化】工具调用路由
                            if name == "write_file":
                                res = AgentAction.write_file(args.get("path"), args.get("content", ""))
                            elif name == "create_folder":
                                res = AgentAction.create_folder(args.get("path"))
                            elif name == "list_files":
                                res = AgentAction.list_files(args.get("path", "."))
                            elif name == "read_file":
                                res = AgentAction.read_file(args.get("path"))
                            elif name == "edit_file":
                                res = AgentAction.edit_file(
                                    args.get("path"),
                                    args.get("start_line"),
                                    args.get("end_line"),
                                    args.get("new_content", ""),
                                    args.get("mode", "replace")
                                )
                            elif name == "search_in_file":
                                res = AgentAction.search_in_file(
                                    args.get("path"),
                                    args.get("query"),
                                    args.get("regex", False),
                                    args.get("context_lines", 3)
                                )
                            elif name == "execute_shell":
                                res = AgentAction.execute_shell(args.get("cmd"))
                            elif name == "mouse_control":
                                res = AgentAction.mouse_control(
                                    args.get("action"),
                                    args.get("x"),
                                    args.get("y"),
                                    args.get("duration", 0.5),
                                    args.get("button", "left")
                                )
                            elif name == "keyboard_control":
                                res = AgentAction.keyboard_control(
                                    args.get("action"),
                                    args.get("text"),
                                    args.get("hotkey")
                                )
                            elif name == "browser_control":
                                res = AgentAction.browser_control(
                                    args.get("action"),
                                    args.get("url")
                                )
                            elif name == "get_project_tree":
                                res = AgentAction.get_project_tree()
                            else:
                                res = f"错误: 未知工具 - {name}"
                                
                        except Exception as e:
                            res = f"工具执行异常: {str(e)}\n{traceback.format_exc()}"
                            consecutive_errors += 1
                            logger.exception(f"工具 {name} 执行失败")

                        # 【优化】限制结果长度
                        max_result_len = 3000
                        if len(res) > max_result_len:
                            res_preview = res[:max_result_len] + f"\n...(结果已截断,总长度: {len(res)} 字符)"
                            emit_log('Tool', f"结果: {res_preview}", 'action')
                        else:
                            emit_log('Tool', f"结果: {res}", 'action')
                        
                        # 添加到消息历史
                        messages.append({
                            "role": "tool",
                            "name": name,
                            "content": res
                        })
                
                # 【新增】错误恢复机制
                if consecutive_errors >= 3:
                    emit_log('Warning', f"连续{consecutive_errors}次工具调用失败,建议检查环境或调整策略", 'warning')
                    # 可以选择继续或停止
                    
            except KeyboardInterrupt:
                emit_log('Warning', "收到中断信号,停止任务", 'warning')
                agent_stop_flag.set()
                break
            except Exception as e:
                emit_log('Error', f"迭代异常: {str(e)}", 'error')
                logger.exception("Agent迭代异常")
                consecutive_errors += 1
                
                if consecutive_errors >= 5:
                    emit_log('Error', "连续异常过多,终止任务", 'error')
                    break

        # 结束消息
        if iteration >= MAX_ITERATIONS:
            emit_log('Warning', f"达到最大迭代次数({MAX_ITERATIONS}),强制停止", 'warning')
        elif agent_stop_flag.is_set():
            emit_log('System', "任务被手动停止", 'system')
        elif completed:
            emit_log('System', "Fairy任务完成!", 'system')

    except Exception as e:
        emit_log('Error', f"系统崩溃: {str(e)}", 'error')
        logger.exception("Agent系统异常")
    finally:
        socketio.emit('agent_status', {'status': 'idle'})
        if agent_lock.locked():
            agent_lock.release()

# ==========================================
# 路由与 SocketIO
# ==========================================

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/health')
def health():
    """健康检查接口"""
    return {
        'status': 'ok',
        'ollama_connected': ollama_client is not None,
        'workspace': WORKSPACE_DIR,
        'model': MODEL_NAME
    }

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    emit_log('System', '客户端已连接', 'system')

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    emit_log('System', '客户端已断开', 'system')

@socketio.on('start_task')
def handle_start_task(data):
    """开始新任务"""
    prompt = data.get('prompt', '').strip()
    if not prompt:
        emit_log('Error', '任务描述不能为空', 'error')
        return
    
    if not agent_lock.acquire(blocking=False):
        emit_log('Error', 'Fairy正在忙碌中,请稍后再试...', 'error')
        return
    
    # 写入新任务标记
    with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
        f.write(f"\n\n{'='*20} 新任务开始 {datetime.now()} {'='*20}\n")
    
    # 在后台线程运行
    threading.Thread(
        target=run_agent_background,
        args=(prompt,),
        daemon=True
    ).start()

@socketio.on('stop_task')
def handle_stop_task():
    """停止当前任务"""
    if agent_lock.locked():
        agent_stop_flag.set()
        emit_log('System', '正在停止任务...', 'warning')
    else:
        emit_log('System', '当前没有运行中的任务', 'info')

# ==========================================
# 启动服务
# ==========================================

if __name__ == '__main__':
    print("="*60)
    print("Fairy Agent System - 增强版")
    print("="*60)
    print(f"日志文件: {LOG_FILE_PATH}")
    print(f"工作目录: {WORKSPACE_DIR}")
    print(f"Ollama: {HOST_URL}")
    print(f"模型: {MODEL_NAME}")
    print(f"最大迭代: {MAX_ITERATIONS}")
    print(f"命令超时: {COMMAND_TIMEOUT}秒")
    print(f"GUI可用: {GUI_AVAILABLE}")
    print("="*60)
    
    # 启动服务器
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)