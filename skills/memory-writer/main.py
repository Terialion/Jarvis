"""
Memory Writer Skill - 智能记忆写入
"""

import os
import re
from datetime import datetime
from colorama import Fore, Style

DESCRIPTION = "智能记忆写入"
ICON = "🧠"


def execute(*args, **kwargs) -> str:
    """
    分析用户输入，提取并保存重要信息到记忆文件
    
    Args:
        用户对话内容
        
    Returns:
        处理结果说明
    """
    if not args or not args[0]:
        return "请提供需要分析的内容"
    
    text = args[0]
    
    # 数据目录
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    facts_file = os.path.join(data_dir, "facts.md")
    
    # 提取的信息列表
    extracted = []
    
    # 1. 检测偏好（喜欢/不喜欢）
    preference_patterns = [
        (r"我喜欢?([^，。！？,!?]*)", "喜欢"),
        (r"我(?:很)?爱?([^，。！？,!?]*?)", "喜爱"),
        (r"我不(?:喜欢|想|要)([^，。！？,!?]*)", "不喜欢"),
    ]
    
    for pattern, category in preference_patterns:
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip()
            if value and len(value) < 50:  # 避免太长的内容
                extracted.append((f"偏好-{category}", value))
    
    # 2. 检测生日/日期
    date_patterns = [
        (r"(?:我的)?生日是?(\d{4}年?\d{1,2}月?\d{1,2}日?)", "生日"),
        (r"(?:我的)?生日是?(\d{1,2}月\d{1,2}日?)", "生日"),
        (r"(?:农历|阴历)?生日是?(.+)", "生日(农历)"),
    ]
    
    for pattern, category in date_patterns:
        match = re.search(pattern, text)
        if match:
            extracted.append(("重要日期-" + category, match.group(1).strip()))
    
    # 3. 检测个人信息
    info_patterns = [
        (r"我叫?([^\s，。！？,!?]+)", "名字"),
        (r"住在?([\u4e00-\u9fa5]+市?[\u4e00-\u9fa5]*)", "所在地"),
        (r"在([\u4e00-\u9fa5]+大学)", "学校"),
        (r"学?专业是?([\u4e00-\u9fa5]+)", "专业"),
    ]
    
    for pattern, category in info_patterns:
        match = re.search(pattern, text)
        if match and len(match.group(1)) < 30:
            extracted.append(("个人信息-" + category, match.group(1).strip()))
    
    # 写入事实文件
    if extracted:
        with open(facts_file, 'a', encoding='utf-8') as f:
            f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for key, value in extracted:
                f.write(f"- **{key}**: {value}\n")
        
        result = f"🧠 已提取 {len(extracted)} 条信息：\n"
        for key, value in extracted:
            result += f"  • {key}: {value}\n"
        return result
    
    return "未检测到需要记忆的重要信息（可尝试说：'我喜欢...' 或 '我的生日是...'）"


if __name__ == "__main__":
    print(execute("我叫张三，喜欢喝咖啡，生日是1998年5月20日"))
