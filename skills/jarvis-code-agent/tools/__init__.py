"""
Jarvis Code Agent - 工具集

14个核心工具，覆盖文件操作、代码执行、代码分析和规划
"""

from .file_tools import read_file, write_file, edit_file, create_project, list_files
from .code_tools import run_python, run_command, run_tests
from .search_tools import analyze_code, search_code, find_errors
from .plan_tools import ask_user

__all__ = [
    # 文件操作
    "read_file", "write_file", "edit_file", "create_project", "list_files",
    # 代码执行
    "run_python", "run_command", "run_tests",
    # 代码分析
    "analyze_code", "search_code", "find_errors",
    # 规划
    "ask_user",
]


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self._tools = {}
        self._register_defaults()
    
    def _register_defaults(self):
        """注册默认工具"""
        defaults = {
            # 文件操作
            "read_file": read_file,
            "write_file": write_file,
            "edit_file": edit_file,
            "create_project": create_project,
            "list_files": list_files,
            # 代码执行
            "run_python": run_python,
            "run_command": run_command,
            "run_tests": run_tests,
            # 代码分析
            "analyze_code": analyze_code,
            "search_code": search_code,
            "find_errors": find_errors,
            # 规划
            "ask_user": ask_user,
        }
        self._tools.update(defaults)
    
    def register(self, name: str, func):
        """注册工具"""
        self._tools[name] = func
    
    def get(self, name: str):
        """获取工具"""
        return self._tools.get(name)
    
    def list_tools(self):
        """列出所有工具"""
        return list(self._tools.keys())
    
    def execute(self, name: str, **kwargs):
        """执行工具"""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"未知工具: {name}")
        return tool(**kwargs)
