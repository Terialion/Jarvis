"""
Jarvis Code Agent - 规划工具集
提供 TODO 管理、用户交互等功能
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from colorama import Fore, Style


def ask_user(question: str, options: List[str] = None) -> str:
    """
    向用户询问（用于关键决策点）
    
    Args:
        question: 问题内容
        options: 选项列表（可选）
    
    Returns:
        用户回答
    """
    print(f"\n{Fore.MAGENTA}╔════════════════════════════════════════╗{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}║{Style.RESET_ALL} {Fore.YELLOW}🤔 需要您的确认{Style.RESET_ALL}".ljust(43) + f"{Fore.MAGENTA}║{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}╠════════════════════════════════════════╣{Style.RESET_ALL}")
    
    # 分行显示问题
    words = question.split()
    lines = []
    current_line = ""
    
    for word in words:
        if len(current_line) + len(word) + 1 <= 36:
            current_line += " " + word if current_line else word
        else:
            lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    for line in lines:
        print(f"{Fore.MAGENTA}║{Style.RESET_ALL} {line}".ljust(43) + f"{Fore.MAGENTA}║{Style.RESET_ALL}")
    
    if options:
        print(f"{Fore.MAGENTA}╠════════════════════════════════════════╣{Style.RESET_ALL}")
        for i, option in enumerate(options, 1):
            print(f"{Fore.MAGENTA}║{Style.RESET_ALL}  {i}. {option}".ljust(43) + f"{Fore.MAGENTA}║{Style.RESET_ALL}")
    
    print(f"{Fore.MAGENTA}╚════════════════════════════════════════╝{Style.RESET_ALL}")
    
    if options:
        prompt = f"\n{Fore.CYAN}请选择 (1-{len(options)}): {Style.RESET_ALL}"
    else:
        prompt = f"\n{Fore.CYAN}您的回答: {Style.RESET_ALL}"
    
    try:
        response = input(prompt).strip()
        
        if options:
            try:
                choice = int(response)
                if 1 <= choice <= len(options):
                    return options[choice - 1]
            except ValueError:
                pass
            return response
        else:
            return response
            
    except (EOFError, KeyboardInterrupt):
        return "cancel"


def confirm_action(action_description: str, danger_level: str = "normal") -> bool:
    """
    确认危险操作
    
    Args:
        action_description: 操作描述
        danger_level: 危险等级 (normal, warning, danger)
    
    Returns:
        是否确认
    """
    colors = {
        "normal": Fore.CYAN,
        "warning": Fore.YELLOW,
        "danger": Fore.RED
    }
    
    color = colors.get(danger_level, Fore.CYAN)
    icons = {
        "normal": "ℹ️",
        "warning": "⚠️",
        "danger": "🚨"
    }
    
    icon = icons.get(danger_level, "ℹ️")
    
    print(f"\n{color}╔════════════════════════════════════════╗{Style.RESET_ALL}")
    print(f"{color}║{Style.RESET_ALL} {icon} 操作确认".ljust(43) + f"{color}║{Style.RESET_ALL}")
    print(f"{color}╠════════════════════════════════════════╣{Style.RESET_ALL}")
    
    # 分行显示
    words = action_description.split()
    lines = []
    current_line = ""
    
    for word in words:
        if len(current_line) + len(word) + 1 <= 36:
            current_line += " " + word if current_line else word
        else:
            lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    for line in lines:
        print(f"{color}║{Style.RESET_ALL} {line}".ljust(43) + f"{color}║{Style.RESET_ALL}")
    
    print(f"{color}╠════════════════════════════════════════╣{Style.RESET_ALL}")
    print(f"{color}║{Style.RESET_ALL} 确认执行? (yes/no):".ljust(43) + f"{color}║{Style.RESET_ALL}")
    print(f"{color}╚════════════════════════════════════════╝{Style.RESET_ALL}")
    
    try:
        response = input(f"\n{color}> {Style.RESET_ALL}").strip().lower()
        return response in ['yes', 'y', '是', '确认']
    except (EOFError, KeyboardInterrupt):
        return False


def save_plan(plan_name: str, todos: List[Dict[str, Any]]) -> str:
    """
    保存计划到文件
    
    Args:
        plan_name: 计划名称
        todos: TODO 列表
    
    Returns:
        保存结果
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        plans_dir = workspace / ".jarvis_plans"
        plans_dir.mkdir(exist_ok=True)
        
        plan_file = plans_dir / f"{plan_name}.json"
        
        plan_data = {
            "name": plan_name,
            "todos": todos,
            "status": "active"
        }
        
        with open(plan_file, 'w', encoding='utf-8') as f:
            json.dump(plan_data, f, ensure_ascii=False, indent=2)
        
        return f"[成功] 计划 '{plan_name}' 已保存"
        
    except Exception as e:
        return f"[错误] 保存计划失败: {str(e)}"


def load_plan(plan_name: str) -> Optional[List[Dict[str, Any]]]:
    """
    加载计划
    
    Args:
        plan_name: 计划名称
    
    Returns:
        TODO 列表或 None
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        plan_file = workspace / ".jarvis_plans" / f"{plan_name}.json"
        
        if not plan_file.exists():
            return None
        
        with open(plan_file, 'r', encoding='utf-8') as f:
            plan_data = json.load(f)
        
        return plan_data.get("todos", [])
        
    except Exception:
        return None


def list_plans() -> str:
    """
    列出所有保存的计划
    
    Returns:
        计划列表
    """
    try:
        workspace = Path(r"D:\jarvis\workspace")
        plans_dir = workspace / ".jarvis_plans"
        
        if not plans_dir.exists():
            return "暂无保存的计划"
        
        plans = list(plans_dir.glob("*.json"))
        
        if not plans:
            return "暂无保存的计划"
        
        result = [f"{Fore.CYAN}=== 已保存的计划 ==={Style.RESET_ALL}"]
        
        for plan_file in plans:
            try:
                with open(plan_file, 'r', encoding='utf-8') as f:
                    plan_data = json.load(f)
                
                name = plan_data.get("name", plan_file.stem)
                todos = plan_data.get("todos", [])
                completed = sum(1 for t in todos if t.get("status") == "completed")
                total = len(todos)
                status = plan_data.get("status", "unknown")
                
                result.append(f"  📋 {name} [{completed}/{total}] ({status})")
            
            except Exception:
                result.append(f"  📋 {plan_file.stem} [读取失败]")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"[错误] 列出计划失败: {str(e)}"
