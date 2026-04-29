"""
Jarvis Code Agent - Skill 入口文件 (main.py)

Toolkit.SkillTool 的主入口点。
通过 getattr(module, 'execute') 调用 execute() 函数。

注意: 此文件使用绝对导入（非相对导入），
     因为 Toolkit 用 spec_from_file_location 加载时相对导入不可用。
"""

import os
import sys
import json

DESCRIPTION = "Jarvis 编码代理，支持规划、执行与状态管理"
ICON = "🤖"

# === 路径设置 ===
_skill_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_skill_dir)

if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# === 导入核心组件（绝对导入）===
from agent_loop import JarvisCodeAgent
from planner import TaskPlanner, quick_plan

__version__ = "2.0.0"
__all__ = ['execute']


# ============================================
# 全局 Agent 实例缓存
# ============================================
_agent_instance = None


def _get_agent(**kwargs) -> JarvisCodeAgent:
    """获取或创建全局 Agent 实例"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = JarvisCodeAgent(**kwargs)
    return _agent_instance


# ============================================
# Skill 执行入口 - Toolkit.SkillTool 调用此函数
# ============================================
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
            agent = _get_agent(workspace=workspace, voice_enabled=voice_enabled)
            status = {
                "status": "ok",
                "mode": "code_agent_status",
                "data": {
                    "version": __version__,
                    "is_running": agent.is_running,
                    "current_task": agent.current_task,
                    "todo_count": len(agent.todo_list),
                    "todo_items": [
                        {"id": t.id, "content": t.content, "status": t.status}
                        for t in agent.todo_list
                    ],
                    "stats": agent.stats,
                    "llm_enabled": agent.llm_enabled,
                    "sub_agents_available": agent.sub_agent_orchestrator is not None
                }
            }
            return json.dumps(status, ensure_ascii=False, indent=2)
        
        elif mode == "reset":
            global _agent_instance
            if _agent_instance is not None:
                try:
                    _agent_instance.end_session()
                except Exception:
                    pass
            _agent_instance = None
            result = {"status": "ok", "mode": "reset", "message": "Code Agent has been reset"}
            return json.dumps(result, ensure_ascii=False)
        
        elif mode in ("code", "plan", ""):
            if not request:
                return json.dumps({
                    "status": "error",
                    "message": "Missing 'request' parameter. Please provide a coding task description."
                }, ensure_ascii=False)
            
            agent = _get_agent(workspace=workspace, voice_enabled=voice_enabled)
            
            if not agent.is_running:
                agent.start_session()
            
            response = agent.handle_request(request, use_sub_agents=use_sub_agents)
            
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
                "message": f"Unknown mode: {mode}. Supported: code, plan, status, reset"
            }, ensure_ascii=False)
            
    except Exception as e:
        import traceback
        error_result = {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }
        return json.dumps(error_result, ensure_ascii=False)


# ============================================
# 自检测试
# ============================================
if __name__ == "__main__":
    print("=" * 50)
    print("Jarvis Code Agent Skill - Self Test")
    print("=" * 50)
    
    print(f"\n[TEST 1] execute function exists: {callable(execute)}")
    
    print("\n[TEST 2] status mode:")
    result = execute(mode="status")
    # 解析并格式化输出
    data = json.loads(result)
    if data.get("status") == "ok":
        d = data["data"]
        print(f"  version: {d['version']}")
        print(f"  running: {d['is_running']}")
        print(f"  llm_enabled: {d['llm_enabled']}")
        print(f"  sub_agents: {d['sub_agents_available']}")
        print(f"  todo_count: {d['todo_count']}")
    else:
        print(f"  ERROR: {result}")
    
    print("\n[TEST 3] error case (no request):")
    err = execute(mode="code", request="")
    print(f"  {err}")
    
    print("\n[TEST 4] reset mode:")
    rst = execute(mode="reset")
    print(f"  {rst}")
    
    print("\n" + "=" * 50)
    print("All tests passed!")
    print("=" * 50)
