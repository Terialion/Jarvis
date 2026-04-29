"""
File Manager Skill - 文件管理
"""

import os
import glob
from datetime import datetime

DESCRIPTION = "文件管理"
ICON = "📁"


def execute(*args, **kwargs) -> str:
    """执行文件操作"""
    if not args:
        return """📁 文件管理功能：
• 读取文件: read <路径>
• 列出目录: list <目录>
• 搜索文件: search <关键词>
• 创建文件: create <路径> <内容>"""
    
    cmd = args[0].split()[0] if args else ""
    rest = " ".join(args[0].split()[1:]) if len(args[0].split()) > 1 else ""
    
    if cmd == "read" and rest:
        try:
            with open(rest, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"读取失败: {e}"
    
    elif cmd == "list" and rest:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), rest)
        if os.path.exists(path):
            items = os.listdir(path)
            return "\n".join(items)
        else:
            return f"目录不存在: {path}"
    
    elif cmd == "search":
        pattern = f"*{rest}*"
        matches = []
        for root, dirs, files in os.walk("."):
            for name in files:
                if rest.lower() in name.lower():
                    matches.append(os.path.join(root, name))
        return f"找到 {len(matches)} 个文件:\n" + "\n".join(matches[:20])
    
    else:
        return "未知命令，支持: read/list/search/create"


if __name__ == "__main__":
    print(execute("list data"))
