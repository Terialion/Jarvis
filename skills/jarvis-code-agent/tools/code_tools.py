"""
Jarvis Code Agent - 代码执行工具集
提供 Python 代码执行、命令运行、测试等功能
"""

import os
import sys
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Tuple, Dict, Any
from colorama import Fore, Style


def run_python(code: str = None, filepath: str = None, timeout: int = 30) -> str:
    """
    执行 Python 代码
    
    Args:
        code: Python 代码字符串（与 filepath 二选一）
        filepath: Python 文件路径（与 code 二选一）
        timeout: 执行超时时间（秒）
    
    Returns:
        执行结果
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        
        if code:
            # 创建临时文件
            temp_file = workspace / f"temp_{os.urandom(4).hex()}.py"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(code)
            filepath = str(temp_file)
        
        if not filepath:
            return "[错误] 请提供 code 或 filepath 参数"
        
        path = Path(filepath)
        if not path.is_absolute():
            path = workspace / filepath
        
        if not path.exists():
            return f"[错误] 文件不存在: {filepath}"
        
        # 执行 Python 代码
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workspace)
        )
        
        output = []
        
        if result.returncode == 0:
            output.append(f"{Fore.GREEN}[执行成功]{Style.RESET_ALL}")
            if result.stdout:
                output.append(f"\n输出:\n{result.stdout}")
        else:
            output.append(f"{Fore.RED}[执行失败]{Style.RESET_ALL}")
            if result.stderr:
                output.append(f"\n错误:\n{result.stderr}")
        
        # 清理临时文件
        if code and path.exists() and 'temp_' in path.name:
            path.unlink()
        
        return "\n".join(output)
        
    except subprocess.TimeoutExpired:
        return f"[错误] 执行超时（{timeout}秒）"
    except Exception as e:
        return f"[错误] 执行失败: {str(e)}"


def run_command(command: str, cwd: str = None, timeout: int = 60) -> str:
    """
    执行系统命令
    
    Args:
        command: 命令字符串
        cwd: 工作目录
        timeout: 超时时间（秒）
    
    Returns:
        执行结果
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        working_dir = cwd or str(workspace)
        
        # 危险命令检查
        dangerous_commands = ['rm -rf /', 'del /f /s /q', 'format', 'rd /s /q']
        for dangerous in dangerous_commands:
            if dangerous in command.lower():
                return f"[错误] 检测到危险命令，已阻止执行: {command}"
        
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir
        )
        
        output = []
        output.append(f"命令: {command}")
        output.append(f"返回码: {result.returncode}")
        
        if result.stdout:
            output.append(f"\n输出:\n{result.stdout}")
        
        if result.stderr:
            output.append(f"\n错误输出:\n{result.stderr}")
        
        return "\n".join(output)
        
    except subprocess.TimeoutExpired:
        return f"[错误] 命令执行超时（{timeout}秒）"
    except Exception as e:
        return f"[错误] 命令执行失败: {str(e)}"


def run_tests(test_path: str = None, test_framework: str = "pytest") -> str:
    """
    运行测试
    
    Args:
        test_path: 测试文件或目录路径
        test_framework: 测试框架（pytest, unittest）
    
    Returns:
        测试结果
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        
        if test_path:
            path = Path(test_path)
            if not path.is_absolute():
                path = workspace / test_path
        else:
            path = workspace
        
        if test_framework == "pytest":
            cmd = f"python -m pytest {path} -v"
        elif test_framework == "unittest":
            cmd = f"python -m unittest discover {path} -v"
        else:
            return f"[错误] 不支持的测试框架: {test_framework}"
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(workspace)
        )
        
        output = []
        
        if result.returncode == 0:
            output.append(f"{Fore.GREEN}[测试通过]{Style.RESET_ALL}")
        else:
            output.append(f"{Fore.RED}[测试失败]{Style.RESET_ALL}")
        
        if result.stdout:
            output.append(result.stdout)
        
        if result.stderr:
            output.append(f"\n错误:\n{result.stderr}")
        
        return "\n".join(output)
        
    except subprocess.TimeoutExpired:
        return "[错误] 测试执行超时"
    except Exception as e:
        return f"[错误] 测试运行失败: {str(e)}"


def install_package(package_name: str, upgrade: bool = False) -> str:
    """
    安装 Python 包
    
    Args:
        package_name: 包名
        upgrade: 是否升级
    
    Returns:
        安装结果
    """
    try:
        cmd = f"pip install {package_name}"
        if upgrade:
            cmd += " --upgrade"
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            return f"[成功] 包 '{package_name}' 安装成功"
        else:
            return f"[错误] 安装失败:\n{result.stderr}"
        
    except Exception as e:
        return f"[错误] 安装失败: {str(e)}"


def check_syntax(filepath: str) -> str:
    """
    检查 Python 代码语法
    
    Args:
        filepath: Python 文件路径
    
    Returns:
        检查结果
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        path = Path(filepath)
        if not path.is_absolute():
            path = workspace / filepath
        
        if not path.exists():
            return f"[错误] 文件不存在: {filepath}"
        
        with open(path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        import py_compile
        import io
        
        # 捕获编译输出
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        
        try:
            py_compile.compile(str(path), doraise=True)
            return f"{Fore.GREEN}[语法检查通过]{Style.RESET_ALL} {filepath}"
        except py_compile.PyCompileError as e:
            error_msg = sys.stderr.getvalue()
            return f"{Fore.RED}[语法错误]{Style.RESET_ALL} {filepath}\n{error_msg}"
        finally:
            sys.stderr = old_stderr
        
    except Exception as e:
        return f"[错误] 语法检查失败: {str(e)}"
