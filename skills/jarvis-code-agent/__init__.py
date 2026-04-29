"""
Jarvis Code Agent - 高效编程 Agent
基于 Claude Code、Cursor、OpenClaw 最佳实践

Skill 入口: execute() 函数，供 Toolkit.SkillTool 调用
"""

import os
import sys
import json

# 确保项目根目录在路径中（agent_loop 依赖此路径）
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from .agent_loop import JarvisCodeAgent, TodoItem, ToolCall, ToolResult, Message
from .planner import TaskPlanner, Task, quick_plan
from .tools import ToolRegistry

__version__ = "2.0.0"
__all__ = [
    "JarvisCodeAgent", 
    "TaskPlanner", 
    "ToolRegistry",
    "TodoItem",
    "ToolCall",
    "ToolResult",
    "Message",
    "Task",
    "quick_plan",
    "execute"
]

# ============================================
# Skill 执行入口 - Toolkit.SkillTool 调用此函数
# ============================================

# 全局 Agent 实例缓存（避免重复初始化 LLM）
_agent_instance = None


def _get_agent(**kwargs) -> JarvisCodeAgent:
    """获取或创建全局 Agent 实例"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = JarvisCodeAgent(**kwargs)
    return _agent_instance


def execute(mode="code", request="", **kwargs):
    """
    Skill 执行入口函数
    
    Toolkit.SkillTool 通过 getattr(module, 'execute') 调用此函数。
    
    参数:
        mode (str): 操作模式:
            - "code": 编程任务（默认）
            - "plan": 仅规划，生成 TODO 列表不执行
            - "status": 查看 Agent 状态
            - "reset": 重置 Agent（清空对话历史）
        request (str): 用户请求/编程任务描述
        **kwargs: 额外参数:
            - use_sub_agents (bool): 是否使用多Agent协作
            - workspace (str): 工作目录
            - voice_enabled (bool): 是否启用语音
            
    返回:
        str: JSON 格式的结果字符串
    """
    try:
        # 提取参数
        use_sub_agents = kwargs.get('use_sub_agents', False)
        workspace = kwargs.get('workspace', r"D:\jarvis\workspace")
        voice_enabled = kwargs.get('voice_enabled', True)
        
        if mode == "status":
            # 返回状态信息
            agent = _get_agent(workspace=workspace, voice_enabled=voice_enabled)
            status = {
                "status": "ok",
                "mode": "code_agent_status",
                "data": {
                    "version": __version__,
                    "is_running": agent.is_running,
                    "current_task": agent.current_task,
                    "todo_count": len(agent.todo_list),
                    "todo_items": [{"id": t.id, "content": t.content, "status": t.status} for t in agent.todo_list],
                    "stats": agent.stats,
                    "llm_enabled": agent.llm_enabled,
                    "sub_agents_available": agent.sub_agent_orchestrator is not None
                }
            }
            return json.dumps(status, ensure_ascii=False, indent=2)
        
        elif mode == "reset":
            # 重置 Agent
            global _agent_instance
            if _agent_instance is not None:
                try:
                    _agent_instance.end_session()
                except:
                    pass
            _agent_instance = None
            result = {"status": "ok", "mode": "reset", "message": "Code Agent 已重置"}
            return json.dumps(result, ensure_ascii=False)
        
        elif mode in ("code", "plan", ""):
            # 核心编程模式
            if not request:
                return json.dumps({
                    "status": "error",
                    "message": "缺少 request 参数，请提供编程任务描述"
                }, ensure_ascii=False)
            
            # 获取或创建 Agent
            agent = _get_agent(workspace=workspace, voice_enabled=voice_enabled)
            
            # 启动会话（如果尚未启动）
            if not agent.is_running:
                agent.start_session()
            
            # 处理请求
            response = agent.handle_request(request, use_sub_agents=use_sub_agents)
            
            # 构建结果
            result = {
                "status": "ok",
                "mode": mode,
                "request": request,
                "response": response,
                "stats": {
                    "iterations": agent.stats["total_iterations"],
                    "tool_calls": agent.stats["tool_calls"],
                    "files_created": agent.stats["files_created"],
                    "files_modified": agent.stats["files_modified"]
                }
            }
            return json.dumps(result, ensure_ascii=False, indent=2)
        
        else:
            return json.dumps({
                "status": "error",
                "message": f"未知模式: {mode}，支持的模式: code, plan, status, reset"
            }, ensure_ascii=False)
            
    except Exception as e:
        import traceback
        error_result = {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }
        return json.dumps(error_result, ensure_ascii=False)
