"""
Jarvis Code Agent - 代码分析工具集
提供代码分析、搜索、错误检测等功能
"""

import os
import re
import ast
from pathlib import Path
from typing import List, Dict, Any
from colorama import Fore, Style


def analyze_code(filepath: str) -> str:
    """
    分析代码文件
    
    Args:
        filepath: 代码文件路径
    
    Returns:
        分析报告
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
        
        lines = code.split('\n')
        total_lines = len(lines)
        non_empty_lines = len([l for l in lines if l.strip()])
        
        analysis = []
        analysis.append(f"{Fore.CYAN}=== 代码分析报告 ==={Style.RESET_ALL}")
        analysis.append(f"文件: {filepath}")
        analysis.append(f"总行数: {total_lines}")
        analysis.append(f"非空行: {non_empty_lines}")
        analysis.append(f"文件大小: {len(code)} 字符")
        
        # Python 特定分析
        if path.suffix == '.py':
            try:
                tree = ast.parse(code)
                
                # 统计
                functions = len([node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)])
                classes = len([node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)])
                imports = len([node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))])
                
                analysis.append(f"\n{Fore.YELLOW}结构统计:{Style.RESET_ALL}")
                analysis.append(f"  函数: {functions}")
                analysis.append(f"  类: {classes}")
                analysis.append(f"  导入: {imports}")
                
                # 查找 TODO 和 FIXME
                todos = []
                for i, line in enumerate(lines, 1):
                    if 'TODO' in line.upper() or 'FIXME' in line.upper():
                        todos.append(f"  第 {i} 行: {line.strip()}")
                
                if todos:
                    analysis.append(f"\n{Fore.YELLOW}待办事项:{Style.RESET_ALL}")
                    analysis.extend(todos[:5])
                    if len(todos) > 5:
                        analysis.append(f"  ... 还有 {len(todos) - 5} 处")
                
                # 复杂度估算（简单版本）
                if functions > 0:
                    avg_lines = non_empty_lines / functions
                    analysis.append(f"\n{Fore.YELLOW}复杂度估算:{Style.RESET_ALL}")
                    analysis.append(f"  平均每函数行数: {avg_lines:.1f}")
                    if avg_lines > 50:
                        analysis.append(f"  {Fore.RED}⚠ 函数可能过长，建议拆分{Style.RESET_ALL}")
                
            except SyntaxError as e:
                analysis.append(f"\n{Fore.RED}语法错误: {e}{Style.RESET_ALL}")
        
        return "\n".join(analysis)
        
    except Exception as e:
        return f"[错误] 分析失败: {str(e)}"


def search_code(pattern: str, directory: str = ".", language: str = None) -> str:
    """
    搜索代码（语义搜索）
    
    Args:
        pattern: 搜索模式
        directory: 搜索目录
        language: 语言过滤（如 python, javascript）
    
    Returns:
        搜索结果
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        path = workspace / directory
        
        if not path.exists():
            return f"[错误] 目录不存在: {directory}"
        
        # 文件扩展名映射
        ext_map = {
            'python': '.py',
            'javascript': '.js',
            'typescript': '.ts',
            'java': '.java',
            'c': '.c',
            'cpp': '.cpp',
            'go': '.go',
            'rust': '.rs',
        }
        
        target_ext = ext_map.get(language) if language else None
        
        results = []
        
        for file_path in path.rglob("*"):
            if not file_path.is_file():
                continue
            
            # 跳过特定目录
            if any(skip in str(file_path) for skip in ['__pycache__', '.git', 'node_modules', '.venv']):
                continue
            
            # 语言过滤
            if target_ext and file_path.suffix != target_ext:
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 简单字符串匹配（可以升级为语义搜索）
                if pattern.lower() in content.lower():
                    lines = content.split('\n')
                    matches = []
                    
                    for i, line in enumerate(lines, 1):
                        if pattern.lower() in line.lower():
                            matches.append((i, line.strip()))
                    
                    if matches:
                        rel_path = file_path.relative_to(workspace)
                        results.append(f"\n{Fore.CYAN}[文件] {rel_path}{Style.RESET_ALL} ({len(matches)} 处)")
                        
                        for line_num, line_content in matches[:3]:
                            # 高亮匹配部分
                            highlighted = line_content.replace(
                                pattern, f"{Fore.YELLOW}{pattern}{Style.RESET_ALL}"
                            )
                            results.append(f"  {line_num:4d}: {highlighted}")
                        
                        if len(matches) > 3:
                            results.append(f"  ... 还有 {len(matches) - 3} 处")
            
            except Exception:
                continue
        
        if results:
            return f"{Fore.GREEN}找到 {len(results)} 个文件包含 '{pattern}':{Style.RESET_ALL}\n" + "\n".join(results)
        else:
            return f"未找到包含 '{pattern}' 的代码"
        
    except Exception as e:
        return f"[错误] 搜索失败: {str(e)}"


def find_errors(filepath: str = None, directory: str = None) -> str:
    """
    查找代码中的潜在错误
    
    Args:
        filepath: 特定文件路径
        directory: 目录路径（与 filepath 二选一）
    
    Returns:
        错误报告
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        
        if filepath:
            files = [workspace / filepath]
        elif directory:
            path = workspace / directory
            files = list(path.rglob("*.py"))
        else:
            files = list(workspace.rglob("*.py"))
        
        all_issues = []
        
        for file_path in files:
            if not file_path.exists():
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    code = f.read()
                
                lines = code.split('\n')
                issues = []
                
                # 检查常见问题
                for i, line in enumerate(lines, 1):
                    # 检查 print 语句（可能遗留的调试代码）
                    if 'print(' in line and 'debug' not in line.lower():
                        issues.append((i, line.strip(), "可能的调试代码"))
                    
                    # 检查裸 except
                    if 'except:' in line and 'except Exception' not in line:
                        issues.append((i, line.strip(), "裸 except 可能捕获过多异常"))
                    
                    # 检查硬编码路径
                    if ':/' in line or ':\\' in line:
                        if '"' in line or "'" in line:
                            issues.append((i, line.strip(), "硬编码路径"))
                    
                    # 检查 TODO/FIXME
                    if 'TODO' in line.upper() or 'FIXME' in line.upper():
                        issues.append((i, line.strip(), "待办事项"))
                    
                    # 检查长行
                    if len(line) > 120:
                        issues.append((i, line[:50] + "...", "行过长（>120字符）"))
                
                # 语法检查
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    issues.append((e.lineno or 0, str(e), "语法错误"))
                
                if issues:
                    rel_path = file_path.relative_to(workspace)
                    all_issues.append((rel_path, issues))
            
            except Exception:
                continue
        
        if all_issues:
            report = [f"{Fore.YELLOW}=== 潜在问题报告 ==={Style.RESET_ALL}"]
            
            for rel_path, issues in all_issues:
                report.append(f"\n{Fore.CYAN}[文件] {rel_path}{Style.RESET_ALL}")
                for line_num, content, issue_type in issues[:10]:
                    report.append(f"  第 {line_num:3d} 行 [{issue_type}]: {content[:50]}")
                if len(issues) > 10:
                    report.append(f"  ... 还有 {len(issues) - 10} 处")
            
            return "\n".join(report)
        else:
            return f"{Fore.GREEN}✓ 未发现明显问题{Style.RESET_ALL}"
        
    except Exception as e:
        return f"[错误] 错误检测失败: {str(e)}"


def get_function_list(filepath: str) -> str:
    """
    获取文件中的函数列表
    
    Args:
        filepath: Python 文件路径
    
    Returns:
        函数列表
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
        
        tree = ast.parse(code)
        
        functions = []
        classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # 获取参数
                args = [arg.arg for arg in node.args.args]
                func_info = f"  def {node.name}({', '.join(args)})"
                if ast.get_docstring(node):
                    func_info += " # 有文档字符串"
                functions.append((node.lineno, func_info))
            
            elif isinstance(node, ast.ClassDef):
                class_methods = []
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        class_methods.append(item.name)
                
                class_info = f"  class {node.name}"
                if class_methods:
                    class_info += f" (方法: {', '.join(class_methods[:3])}"
                    if len(class_methods) > 3:
                        class_info += "..."
                    class_info += ")"
                classes.append((node.lineno, class_info))
        
        result = [f"{Fore.CYAN}=== {filepath} 结构 ==={Style.RESET_ALL}"]
        
        if classes:
            result.append(f"\n{Fore.YELLOW}类:{Style.RESET_ALL}")
            for line_no, info in sorted(classes):
                result.append(f"  第 {line_no} 行{info}")
        
        if functions:
            result.append(f"\n{Fore.YELLOW}函数:{Style.RESET_ALL}")
            for line_no, info in sorted(functions):
                result.append(f"  第 {line_no} 行{info}")
        
        if not classes and not functions:
            result.append("\n未找到类或函数定义")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"[错误] 获取函数列表失败: {str(e)}"
