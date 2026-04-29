"""
Code Generator Skill - 代码生成器
功能：让 Jarvis 能够编写、保存和执行简单的 Python 程序
"""

import os
import re
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from colorama import Fore, Style

# 配置
DESCRIPTION = "代码生成与执行"
ICON = "🤖"


class CodeGenerator:
    """代码生成器核心类"""
    
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.scripts_dir = os.path.join(base_dir, "..", "data", "scripts", "generated")
        self.history_file = os.path.join(base_dir, "..", "data", "scripts", "code_history.md")
        
        # 确保目录存在
        os.makedirs(self.scripts_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
    
    def generate_and_save(self, code: str, description: str) -> str:
        """
        生成并保存代码
        
        Args:
            code: Python 代码内容
            description: 需求描述
            
        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"script_{timestamp}.py"
        filepath = os.path.join(self.scripts_dir, filename)
        
        # 文件头
        header = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
{description}
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
由 J.A.R.V.I.S 自动生成
"""
'''
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(header + code)
        
        # 记录历史
        self._log_history(filename, description)
        
        return filepath
    
    def execute_code(self, code_or_path: str, is_file: bool = False, timeout: int = 30) -> Tuple[bool, str]:
        """
        执行代码
        
        Args:
            code_or_path: 代码内容或文件路径
            is_file: 是否为文件路径
            timeout: 超时时间
            
        Returns:
            (成功与否, 输出结果)
        """
        try:
            if is_file:
                result = subprocess.run(
                    ['python', code_or_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding='utf-8'
                )
            else:
                result = subprocess.run(
                    ['python', '-c', code_or_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding='utf-8'
                )
            
            output = result.stdout
            if result.stderr:
                output += "\n[stderr] " + result.stderr
            
            return result.returncode == 0, output
            
        except subprocess.TimeoutExpired:
            return False, f"执行超时 ({timeout}秒)"
        except Exception as e:
            return False, f"执行错误: {str(e)}"
    
    def list_scripts(self) -> List[Dict]:
        """列出所有生成的脚本"""
        scripts = []
        for fname in os.listdir(self.scripts_dir):
            if fname.endswith('.py'):
                fpath = os.path.join(self.scripts_dir, fname)
                stat = os.stat(fpath)
                scripts.append({
                    'name': fname,
                    'path': fpath,
                    'time': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'size': stat.st_size
                })
        return sorted(scripts, key=lambda x: x['time'], reverse=True)
    
    def _log_history(self, filename: str, desc: str):
        """记录到历史文件"""
        entry = f"\n## {datetime.now().strftime('%H:%M:%S')}\n**文件**: `{filename}`\n**需求**: {desc}\n---\n"
        with open(self.history_file, 'a', encoding='utf-8') as f:
            f.write(entry)


def execute(*args, **kwargs) -> str:
    """
    Skill 入口函数
    
    Args:
        第一个参数可以是:
        - 自然语言描述（需要 AI 辅助生成）
        - 直接的 Python 代码（以 ``` 开头或包含 def/class/import）
    
    Returns:
        执行结果或文件路径
    """
    gen = CodeGenerator()
    
    if not args:
        return "请提供代码需求，例如：写一个计算斐波那契数列的函数"
    
    input_text = args[0]
    
    # 判断是否是直接代码还是描述
    is_code = (
        input_text.startswith('```') or 
        input_text.strip().startswith(('import ', 'def ', 'class ', '# ', 'print(')) or
        '\n' in input_text and len(input_text.split('\n')) > 2
    )
    
    if is_code:
        # 清理代码块标记
        code = re.sub(r'```(?:python)?\n?', '', input_text).strip()
        code = re.sub(r'```$', '', code).strip()
        
        # 保存并执行
        path = gen.generate_and_save(code, "用户提供的代码")
        
        success, output = gen.execute_code(path, is_file=True)
        
        result = f"📄 已保存: {path}\n"
        if success:
            result += f"✅ 执行输出:\n```\n{output}\n```"
        else:
            result += f"⚠️ 执行结果:\n```\n{output}\n```"
        
        return result
    
    else:
        # 是自然语言描述，返回提示让 AI 生成代码
        return f"""我理解您的需求：{input_text}

请根据以上需求生成完整的 Python 代码。要求：
1. 代码完整可运行
2. 添加必要注释
3. 包含示例调用

生成后我会自动保存并执行。"""


# 测试入口
if __name__ == "__main__":
    print(f"{Fore.GREEN}[Code Generator Skill] 测试{Style.RESET_ALL}")
    print(execute("写一个计算斐波那契数列的函数"))
