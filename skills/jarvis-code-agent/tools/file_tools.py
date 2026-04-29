"""
Jarvis Code Agent - 文件操作工具集
提供文件读写、编辑、项目管理等功能
"""

import os
import re
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Union
from colorama import Fore, Style


def read_file(filepath: str, offset: int = None, limit: int = None) -> str:
    """
    读取文件内容
    
    Args:
        filepath: 文件路径（相对 workspace 或绝对路径）
        offset: 起始行号（可选）
        limit: 读取行数（可选）
    
    Returns:
        文件内容
    """
    try:
        path = Path(filepath)
        if not path.is_absolute():
            # 相对于 workspace
            workspace = Path(r"D:\jarvis\workspace")
            path = workspace / filepath
        
        if not path.exists():
            return f"[错误] 文件不存在: {filepath}"
        
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 如果指定了 offset 和 limit
        if offset is not None:
            start = max(0, offset - 1)  # 转换为 0-based
            end = start + limit if limit else len(lines)
            lines = lines[start:end]
        
        content = ''.join(lines)
        
        # 添加行号
        numbered_lines = []
        start_line = offset if offset else 1
        for i, line in enumerate(lines, start=start_line):
            numbered_lines.append(f"{i:4d}: {line}")
        
        return ''.join(numbered_lines)
        
    except Exception as e:
        return f"[错误] 读取文件失败: {str(e)}"


def write_file(filepath: str, content: str, overwrite: bool = False) -> str:
    """
    写入文件
    
    Args:
        filepath: 文件路径
        content: 文件内容
        overwrite: 是否覆盖已存在的文件
    
    Returns:
        操作结果
    """
    try:
        path = Path(filepath)
        if not path.is_absolute():
            workspace = Path(r"D:\jarvis\workspace")
            path = workspace / filepath
        
        # 检查文件是否已存在
        if path.exists() and not overwrite:
            return f"[警告] 文件已存在，使用 overwrite=True 覆盖: {filepath}"
        
        # 创建父目录
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"[成功] 文件已创建: {filepath} ({len(content)} 字符)"
        
    except Exception as e:
        return f"[错误] 写入文件失败: {str(e)}"


def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """
    编辑文件内容（差异更新）
    
    Args:
        filepath: 文件路径
        old_str: 要替换的内容
        new_str: 新内容
    
    Returns:
        操作结果
    """
    try:
        path = Path(filepath)
        if not path.is_absolute():
            workspace = Path(r"D:\jarvis\workspace")
            path = workspace / filepath
        
        if not path.exists():
            return f"[错误] 文件不存在: {filepath}"
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查 old_str 是否存在
        if old_str not in content:
            return f"[错误] 未找到要替换的内容"
        
        # 替换内容
        new_content = content.replace(old_str, new_str, 1)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return f"[成功] 文件已更新: {filepath}"
        
    except Exception as e:
        return f"[错误] 编辑文件失败: {str(e)}"


def create_project(project_name: str, structure: Dict[str, Union[str, Dict]]) -> str:
    """
    创建项目结构
    
    Args:
        project_name: 项目名称
        structure: 项目结构字典
            {
                "file.txt": "文件内容",
                "subdir/": {
                    "nested.txt": "嵌套文件内容"
                }
            }
    
    Returns:
        操作结果
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        project_dir = workspace / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        created_files = []
        
        def create_recursive(base_path: Path, struct: Dict):
            for name, content in struct.items():
                item_path = base_path / name
                
                if isinstance(content, dict):
                    # 子目录
                    item_path.mkdir(parents=True, exist_ok=True)
                    create_recursive(item_path, content)
                else:
                    # 文件
                    item_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(item_path, 'w', encoding='utf-8') as f:
                        f.write(str(content))
                    created_files.append(str(item_path.relative_to(project_dir)))
        
        create_recursive(project_dir, structure)
        
        return f"[成功] 项目 '{project_name}' 创建完成，共 {len(created_files)} 个文件"
        
    except Exception as e:
        return f"[错误] 创建项目失败: {str(e)}"


def list_files(directory: str = ".", recursive: bool = False, 
               ignore_patterns: List[str] = None) -> str:
    """
    列出目录内容
    
    Args:
        directory: 目录路径
        recursive: 是否递归列出
        ignore_patterns: 忽略的文件模式列表
    
    Returns:
        目录内容列表
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        path = workspace / directory
        
        if not path.exists():
            return f"[错误] 目录不存在: {directory}"
        
        ignore_patterns = ignore_patterns or ['__pycache__', '*.pyc', '.git', '.venv', 'node_modules']
        
        def should_ignore(p: Path) -> bool:
            for pattern in ignore_patterns:
                if pattern in str(p):
                    return True
            return False
        
        lines = [f"📁 {path.name or 'workspace'}/"]
        
        if recursive:
            for item in path.rglob("*"):
                if should_ignore(item):
                    continue
                
                rel_path = item.relative_to(path)
                depth = len(rel_path.parts) - 1
                indent = "  " * depth
                
                if item.is_dir():
                    lines.append(f"{indent}📁 {item.name}/")
                else:
                    size = item.stat().st_size
                    size_str = f"({size} bytes)" if size < 1024 else f"({size/1024:.1f} KB)"
                    lines.append(f"{indent}📄 {item.name} {size_str}")
        else:
            items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
            for item in items:
                if should_ignore(item):
                    continue
                
                if item.is_dir():
                    lines.append(f"  📁 {item.name}/")
                else:
                    size = item.stat().st_size
                    size_str = f"({size} bytes)" if size < 1024 else f"({size/1024:.1f} KB)"
                    lines.append(f"  📄 {item.name} {size_str}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"[错误] 列出目录失败: {str(e)}"


def delete_file(filepath: str, confirm: bool = False) -> str:
    """
    删除文件或目录
    
    Args:
        filepath: 文件路径
        confirm: 确认删除
    
    Returns:
        操作结果
    """
    try:
        if not confirm:
            return f"[警告] 请设置 confirm=True 确认删除: {filepath}"
        
        path = Path(filepath)
        if not path.is_absolute():
            workspace = Path(r"D:\jarvis\workspace")
            path = workspace / filepath
        
        if not path.exists():
            return f"[错误] 文件不存在: {filepath}"
        
        if path.is_dir():
            shutil.rmtree(path)
            return f"[成功] 目录已删除: {filepath}"
        else:
            path.unlink()
            return f"[成功] 文件已删除: {filepath}"
        
    except Exception as e:
        return f"[错误] 删除失败: {str(e)}"


def search_files(pattern: str, directory: str = ".", file_extension: str = None) -> str:
    """
    搜索文件内容
    
    Args:
        pattern: 搜索模式（正则表达式）
        directory: 搜索目录
        file_extension: 文件扩展名过滤（如 .py）
    
    Returns:
        搜索结果
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        path = workspace / directory
        
        if not path.exists():
            return f"[错误] 目录不存在: {directory}"
        
        results = []
        regex = re.compile(pattern, re.IGNORECASE)
        
        for file_path in path.rglob("*"):
            if not file_path.is_file():
                continue
            
            if file_extension and not file_path.suffix == file_extension:
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                matches = list(regex.finditer(content))
                if matches:
                    rel_path = file_path.relative_to(workspace)
                    results.append(f"\n📄 {rel_path} ({len(matches)} 处匹配)")
                    
                    # 显示前3处匹配
                    for i, match in enumerate(matches[:3], 1):
                        start = max(0, match.start() - 30)
                        end = min(len(content), match.end() + 30)
                        context = content[start:end].replace('\n', ' ')
                        results.append(f"  {i}. ...{context}...")
                    
                    if len(matches) > 3:
                        results.append(f"  ... 还有 {len(matches) - 3} 处匹配")
            
            except Exception:
                continue
        
        if results:
            return "\n".join(results)
        else:
            return f"未找到匹配 '{pattern}' 的内容"
        
    except Exception as e:
        return f"[错误] 搜索失败: {str(e)}"
