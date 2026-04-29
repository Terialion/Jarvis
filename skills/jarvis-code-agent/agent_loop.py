"""
Jarvis Code Agent - 核心 Agent Loop v2.0

基于 While-Tool 循环架构，集成 DeepSeek LLM
实现智能决策、自动规划、实时跟踪、多 Agent 协作
"""

import os
import sys
import json
import asyncio
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field

# 添加项目根目录到路径
sys.path.insert(0, r"D:\jarvis")

from colorama import Fore, Style, init
init()

from jarvis_ui import JarvisUI

# 导入子代理系统
try:
    from sub_agents import (
        SubAgentOrchestrator, PlanningAgent, ExecutionAgent, ReviewAgent,
        AgentRole, TaskContext, SubAgentResult
    )
    SUB_AGENTS_AVAILABLE = True
except ImportError as e:
    SUB_AGENTS_AVAILABLE = False
    print(f"{Fore.YELLOW}[警告] 子代理系统导入失败: {e}{Style.RESET_ALL}")


@dataclass
class ToolCall:
    """工具调用定义"""
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str = field(default_factory=lambda: f"call_{datetime.now().timestamp()}")


@dataclass
class ToolResult:
    """工具执行结果"""
    call_id: str
    success: bool
    output: str
    error: Optional[str] = None


@dataclass
class Message:
    """对话消息"""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_results: Optional[List[ToolResult]] = None
    timestamp: datetime = field(default_factory=datetime.now)


class TodoItem:
    """TODO 列表项"""
    def __init__(self, id: int, content: str, priority: str = "medium"):
        self.id = id
        self.content = content
        self.status = "pending"  # pending, in_progress, completed
        self.priority = priority  # low, medium, high
        self.created_at = datetime.now()
        self.completed_at = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class JarvisCodeAgent:
    """
    Jarvis Code Agent - 核心编程 Agent v2.0
    
    实现 While-Tool 循环架构：
    1. 接收用户输入
    2. LLM 决策（工具调用或直接回复）
    3. 执行工具
    4. 返回结果，循环继续
    """
    
    def __init__(
        self,
        voice_enabled: bool = True,
        workspace: str = r"D:\jarvis\workspace",
        ui: Optional[JarvisUI] = None,
        max_iterations: int = 50,
        llm_enabled: bool = True
    ):
        self.voice_enabled = voice_enabled
        self.workspace = workspace
        self.ui = ui or JarvisUI()
        self.max_iterations = max_iterations
        self.llm_enabled = llm_enabled
        
        # 确保工作目录存在
        os.makedirs(workspace, exist_ok=True)
        
        # 对话历史
        self.messages: List[Message] = []
        
        # TODO 列表
        self.todo_list: List[TodoItem] = []
        
        # 工具注册表
        self.tools: Dict[str, Callable] = {}
        
        # 状态
        self.is_running = False
        self.current_task = None
        
        # 统计
        self.stats = {
            "total_iterations": 0,
            "tool_calls": 0,
            "files_created": 0,
            "files_modified": 0,
            "start_time": None
        }
        
        # LLM 客户端
        self.llm_client = None
        if llm_enabled:
            self._init_llm()
        
        # 子代理编排器
        self.sub_agent_orchestrator = None
        if SUB_AGENTS_AVAILABLE:
            self._init_sub_agents()
        
        # 注册工具
        self._register_default_tools()
    
    def _init_llm(self):
        """初始化 LLM 客户端"""
        try:
            from ai_core import JarvisAI
            # 读取 settings.json 获取 API key
            settings_path = os.path.join(os.path.dirname(self.workspace), "settings.json")
            api_key = None
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    api_key = settings.get('deepseek_api_key')
            
            if api_key:
                self.llm_client = JarvisAI(
                    api_key=api_key,
                    persona="""你是 Jarvis Code Agent，一个专业的 AI 编程助手。

你的核心职责：
1. 理解用户的编程需求
2. 制定合理的执行计划（使用 TODO 列表）
3. 调用工具完成任务
4. 提供清晰的进度报告

决策规则：
- 复杂任务（需要多步骤）：先创建 TODO 列表，然后逐步执行
- 简单任务（单一步骤）：直接执行工具调用
- 需要信息：向用户询问

可用工具：
- 文件操作：read_file, write_file, edit_file, list_files
- 代码执行：run_python, run_command
- 代码分析：analyze_code, search_code
- 规划：todo_write, ask_user

重要：
- 始终以 JSON 格式返回决策
- 不要假设文件内容，先用 read_file 查看
- 危险操作前使用 ask_user 确认
""",
                    max_history_turns=20
                )
                print(f"{Fore.GREEN}[Code Agent] LLM 已初始化{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}[Code Agent] 未找到 API Key，使用规则引擎模式{Style.RESET_ALL}")
                self.llm_enabled = False
        except Exception as e:
            print(f"{Fore.YELLOW}[Code Agent] LLM 初始化失败: {e}，使用规则引擎模式{Style.RESET_ALL}")
            self.llm_enabled = False
    
    def _init_sub_agents(self):
        """初始化子代理系统"""
        try:
            self.sub_agent_orchestrator = SubAgentOrchestrator(self.llm_client)
            self.sub_agent_orchestrator.register_tools(self.tools)
            print(f"{Fore.GREEN}[Code Agent] 子代理系统已初始化{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}[Code Agent] 子代理系统初始化失败: {e}{Style.RESET_ALL}")
            self.sub_agent_orchestrator = None
    
    def _register_default_tools(self):
        """注册默认工具集"""
        # 动态导入工具，处理不同的导入路径
        try:
            # 尝试相对导入（作为包导入时）
            from .tools import (
                read_file, write_file, edit_file, create_project, list_files,
                run_python, run_command, run_tests,
                analyze_code, search_code, find_errors,
                ask_user
            )
        except ImportError:
            # 直接运行时导入
            import sys
            import os
            tools_dir = os.path.join(os.path.dirname(__file__), 'tools')
            if tools_dir not in sys.path:
                sys.path.insert(0, tools_dir)
            from file_tools import read_file, write_file, edit_file, create_project, list_files
            from code_tools import run_python, run_command, run_tests
            from search_tools import analyze_code, search_code, find_errors
            from plan_tools import ask_user
        
        tools = {
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
            "todo_write": self._tool_todo_write,
            "ask_user": ask_user,
        }
        
        # 注册网页工具
        try:
            from web_tools import (
                fetch_webpage, search_web, fetch_and_summarize,
                search_and_fetch, extract_code_from_webpage,
                format_webpage_info, format_search_results
            )
            tools.update({
                "fetch_webpage": fetch_webpage,
                "search_web": search_web,
                "fetch_and_summarize": fetch_and_summarize,
                "search_and_fetch": search_and_fetch,
                "extract_code_from_webpage": extract_code_from_webpage,
                "format_webpage_info": format_webpage_info,
                "format_search_results": format_search_results,
            })
            print(f"{Fore.GREEN}[Code Agent] 网页工具已加载{Style.RESET_ALL}")
        except ImportError as e:
            print(f"{Fore.YELLOW}[Code Agent] 网页工具加载失败: {e}{Style.RESET_ALL}")
        
        # 注册增强版网页搜索工具
        try:
            from web_search_enhanced import (
                search_web as search_web_enhanced,
                get_trending,
                format_search_results as format_search_results_enhanced,
                format_trending
            )
            tools.update({
                "search_web_enhanced": search_web_enhanced,
                "get_trending": get_trending,
                "format_search_results_enhanced": format_search_results_enhanced,
                "format_trending": format_trending,
            })
            print(f"{Fore.GREEN}[Code Agent] 增强搜索工具已加载{Style.RESET_ALL}")
        except ImportError as e:
            print(f"{Fore.YELLOW}[Code Agent] 增强搜索工具加载失败: {e}{Style.RESET_ALL}")
        
        self.tools.update(tools)
    
    def _tool_todo_write(self, todos: List[Dict]) -> str:
        """TODO 列表工具的内部实现"""
        self.update_todo_list(todos)
        return f"TODO 列表已更新，共 {len(self.todo_list)} 项任务"
    
    def update_todo_list(self, todos: List[Dict]):
        """更新 TODO 列表并播报进度"""
        old_completed = sum(1 for t in self.todo_list if t.status == "completed")
        
        # 重建 TODO 列表
        self.todo_list = []
        for i, todo_data in enumerate(todos, 1):
            item = TodoItem(
                id=i,
                content=todo_data.get("content", ""),
                priority=todo_data.get("priority", "medium")
            )
            item.status = todo_data.get("status", "pending")
            if item.status == "completed":
                item.completed_at = datetime.now()
            self.todo_list.append(item)
        
        # 播报进度
        new_completed = sum(1 for t in self.todo_list if t.status == "completed")
        total = len(self.todo_list)
        
        if new_completed > old_completed:
            try:
                from voice_output import speak
                speak(f"进度更新：已完成 {new_completed}/{total} 项任务")
            except:
                pass
        
        # 显示 TODO 列表
        self._display_todo_list()
    
    def _display_todo_list(self):
        """显示 TODO 列表"""
        print(f"\n{Fore.CYAN}╔════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.YELLOW}[任务清单]{Style.RESET_ALL}".ljust(43) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╠════════════════════════════════════════╣{Style.RESET_ALL}")
        
        for item in self.todo_list:
            status_icon = {
                "completed": f"{Fore.GREEN}[OK]{Style.RESET_ALL}",
                "in_progress": f"{Fore.YELLOW}[>]{Style.RESET_ALL}",
                "pending": f"{Fore.WHITE}[ ]{Style.RESET_ALL}"
            }.get(item.status, f"{Fore.WHITE}[ ]{Style.RESET_ALL}")
            
            priority_color = {
                "high": Fore.RED,
                "medium": Fore.YELLOW,
                "low": Fore.WHITE
            }.get(item.priority, Fore.WHITE)
            
            content = f"{status_icon} {priority_color}{item.content}{Style.RESET_ALL}"
            # 截断长文本
            if len(content) > 38:
                content = content[:35] + "..."
            
            print(f"{Fore.CYAN}║{Style.RESET_ALL} {content}".ljust(43) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        
        print(f"{Fore.CYAN}╚════════════════════════════════════════╝{Style.RESET_ALL}\n")
    
    def start_session(self):
        """启动编程会话"""
        self.is_running = True
        self.stats["start_time"] = datetime.now()
        
        print(f"{Fore.GREEN}[系统] Code Agent 已启动{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[系统] 工作目录: {self.workspace}{Style.RESET_ALL}")
        
        if self.llm_enabled:
            print(f"{Fore.GREEN}[系统] LLM 模式: 已启用{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}[系统] LLM 模式: 规则引擎{Style.RESET_ALL}")
        
        if self.voice_enabled:
            try:
                from voice_output import speak
                speak("Code Agent 已就绪，等待您的指令")
            except:
                pass
    
    def handle_request(self, user_input: str, use_sub_agents: bool = False) -> str:
        """
        处理用户请求 - 核心 Agent Loop
        
        Args:
            user_input: 用户输入的自然语言指令
            use_sub_agents: 是否使用子代理协作模式
            
        Returns:
            最终响应
        """
        # 添加用户消息
        self.messages.append(Message(role="user", content=user_input))
        
        # 初始化任务
        self.current_task = user_input
        print(f"\n{Fore.YELLOW}[任务] {user_input}{Style.RESET_ALL}")
        
        # 如果使用子代理且可用，启用多 Agent 协作模式
        if use_sub_agents and self.sub_agent_orchestrator:
            return self._handle_with_sub_agents(user_input)
        
        # Agent Loop
        iteration = 0
        while iteration < self.max_iterations and self.is_running:
            iteration += 1
            self.stats["total_iterations"] += 1
            
            # 1. 构建上下文
            context = self._build_context()
            
            # 2. LLM 决策
            decision = self._llm_decide(context)
            
            # 3. 执行决策
            if decision["action"] == "tool_call":
                # 执行工具调用
                results = self._execute_tool_calls(decision["tool_calls"])
                self.messages.append(Message(
                    role="assistant",
                    content=decision.get("thought", ""),
                    tool_calls=decision["tool_calls"],
                    tool_results=results
                ))
                
                # 检查是否完成任务
                if self._is_task_complete():
                    break
                    
            elif decision["action"] == "respond":
                # 直接回复用户
                response = decision["content"]
                self.messages.append(Message(role="assistant", content=response))
                
                print(f"\n{Fore.GREEN}[Jarvis] {response}{Style.RESET_ALL}")
                if self.voice_enabled:
                    try:
                        from voice_output import speak
                        speak(response)
                    except:
                        pass
                
                return response
            
            elif decision["action"] == "ask_user":
                # 向用户询问
                question = decision["content"]
                print(f"\n{Fore.MAGENTA}[询问] {question}{Style.RESET_ALL}")
                
                # 等待用户输入（在实际实现中需要语音或文本输入）
                # 这里简化处理
                return f"需要用户确认: {question}"
        
        # 生成最终总结
        summary = self._generate_summary()
        return summary
    
    def _handle_with_sub_agents(self, user_input: str) -> str:
        """
        使用子代理协作处理请求
        
        Args:
            user_input: 用户输入
            
        Returns:
            处理结果
        """
        print(f"\n{Fore.CYAN}[多 Agent 模式] 启动规划/执行/审查协作{Style.RESET_ALL}")
        
        try:
            # 执行完整工作流
            workflow_result = self.sub_agent_orchestrator.execute_full_workflow(user_input)
            
            # 生成总结报告
            summary_lines = [
                f"\n{Fore.GREEN}[多 Agent 协作完成]{Style.RESET_ALL}",
                f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}",
                "",
                "【规划阶段】",
                workflow_result["results"]["planning"].output[:200] + "..." if len(workflow_result["results"]["planning"].output) > 200 else workflow_result["results"]["planning"].output,
                "",
                "【执行阶段】",
                workflow_result["results"]["execution"].output,
                "",
                "【审查阶段】",
                workflow_result["results"]["review"].output[:300] + "..." if len(workflow_result["results"]["review"].output) > 300 else workflow_result["results"]["review"].output,
                "",
                f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}"
            ]
            
            summary = "\n".join(summary_lines)
            print(summary)
            
            # 保存到消息历史
            self.messages.append(Message(
                role="assistant",
                content=f"多 Agent 协作完成: {workflow_result['results']['execution'].output}"
            ))
            
            return summary
            
        except Exception as e:
            print(f"{Fore.RED}[多 Agent 模式] 执行失败: {e}{Style.RESET_ALL}")
            # 回退到普通模式
            return self.handle_request(user_input, use_sub_agents=False)
    
    def _build_context(self) -> Dict:
        """构建 LLM 上下文"""
        # 系统提示
        system_prompt = self._get_system_prompt()
        
        # 最近的对话历史
        recent_messages = self.messages[-10:]  # 最近10条
        
        # TODO 列表状态
        todo_status = self._get_todo_status()
        
        # 可用工具
        available_tools = list(self.tools.keys())
        
        return {
            "system_prompt": system_prompt,
            "messages": recent_messages,
            "todo_status": todo_status,
            "available_tools": available_tools,
            "workspace": self.workspace
        }
    
    def _get_system_prompt(self) -> str:
        """获取系统提示"""
        return f"""你是 Jarvis Code Agent，一个专业的 AI 编程助手。

当前任务: {self.current_task or "无"}
工作目录: {self.workspace}

## 核心原则
1. **规划优先**: 复杂任务先创建 TODO 列表
2. **只做必要操作**: 不创建多余文件
3. **及时播报**: 完成关键步骤时更新进度
4. **安全第一**: 危险操作需用户确认

## 可用工具
文件操作: read_file, write_file, edit_file, create_project, list_files
代码执行: run_python, run_command, run_tests
代码分析: analyze_code, search_code, find_errors
规划: todo_write, ask_user

## TODO 列表状态
{self._get_todo_status()}

## 当前状态
{self._get_current_status()}
"""
    
    def _get_todo_status(self) -> str:
        """获取 TODO 列表状态文本"""
        if not self.todo_list:
            return "暂无 TODO 列表"
        
        lines = []
        for item in self.todo_list:
            status = "[x]" if item.status == "completed" else "[>]" if item.status == "in_progress" else "[ ]"
            lines.append(f"{status} {item.content}")
        
        return "\n".join(lines)
    
    def _get_current_status(self) -> str:
        """获取当前状态描述"""
        return f"迭代次数: {self.stats['total_iterations']}, 工具调用: {self.stats['tool_calls']}"
    
    def _llm_decide(self, context: Dict) -> Dict:
        """
        LLM 决策 - v2.0 集成真实 LLM
        """
        if self.llm_enabled and self.llm_client:
            return self._llm_decide_with_api(context)
        else:
            return self._llm_decide_rule_based(context)
    
    def _llm_decide_with_api(self, context: Dict) -> Dict:
        """使用 LLM API 进行决策"""
        try:
            # 构建工具描述
            tools_desc = self._get_tools_description()
            
            # 构建提示
            prompt = f"""基于以下上下文，决定下一步操作：

## 系统提示
{context['system_prompt']}

## 最近对话
{self._format_messages(context['messages'])}

## 可用工具
{tools_desc}

## 决策格式
请以 JSON 格式返回决策：

1. 如果需要调用工具：
{{
    "action": "tool_call",
    "thought": "思考过程",
    "tool_calls": [
        {{
            "tool_name": "工具名",
            "arguments": {{"参数名": "参数值"}}
        }}
    ]
}}

2. 如果直接回复用户：
{{
    "action": "respond",
    "content": "回复内容"
}}

3. 如果需要询问用户：
{{
    "action": "ask_user",
    "content": "问题内容"
}}

请只返回 JSON，不要其他内容。"""

            # 调用 LLM
            response = self.llm_client.chat(prompt)
            
            # 解析 JSON 响应
            # 尝试提取 JSON 部分
            json_match = None
            if "```json" in response:
                json_match = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_match = response.split("```")[1].split("```")[0].strip()
            else:
                json_match = response.strip()
            
            decision = json.loads(json_match)
            
            # 转换 tool_calls 格式
            if decision.get("action") == "tool_call" and "tool_calls" in decision:
                tool_calls = []
                for tc in decision["tool_calls"]:
                    tool_calls.append(ToolCall(
                        tool_name=tc["tool_name"],
                        arguments=tc["arguments"]
                    ))
                decision["tool_calls"] = tool_calls
            
            return decision
            
        except Exception as e:
            print(f"{Fore.YELLOW}[LLM 决策失败] {e}，回退到规则引擎{Style.RESET_ALL}")
            return self._llm_decide_rule_based(context)
    
    def _get_tools_description(self) -> str:
        """获取工具描述"""
        descriptions = {
            "read_file": "读取文件内容，参数: filename",
            "write_file": "写入文件，参数: filename, content, overwrite",
            "edit_file": "编辑文件，参数: filename, old_string, new_string",
            "list_files": "列出目录文件，参数: directory, recursive",
            "run_python": "运行 Python 代码，参数: code 或 filename",
            "run_command": "运行 shell 命令，参数: command",
            "analyze_code": "分析代码，参数: filename",
            "search_code": "搜索代码，参数: pattern",
            "todo_write": "更新 TODO 列表，参数: todos",
            "ask_user": "询问用户，参数: question"
        }
        
        lines = []
        for name, desc in descriptions.items():
            if name in self.tools:
                lines.append(f"- {name}: {desc}")
        
        return "\n".join(lines)
    
    def _format_messages(self, messages: List[Message]) -> str:
        """格式化消息列表"""
        lines = []
        for m in messages:
            role_icon = {"user": "👤", "assistant": "🤖", "system": "⚙️", "tool": "🔧"}.get(m.role, "•")
            lines.append(f"{role_icon} {m.role}: {m.content[:100]}")
        return "\n".join(lines)
    
    def _llm_decide_rule_based(self, context: Dict) -> Dict:
        """
        基于规则的决策（备用方案）
        """
        last_message = context["messages"][-1] if context["messages"] else None
        
        if not last_message:
            return {"action": "respond", "content": "请告诉我您需要什么帮助"}
        
        content = last_message.content.lower()
        
        # 检查是否需要创建 TODO 列表
        if any(kw in content for kw in ["创建", "写", "实现", "开发", "做一个"]) and not self.todo_list:
            # 自动创建 TODO 列表
            return {
                "action": "tool_call",
                "thought": "这是一个复杂任务，我需要先创建 TODO 列表",
                "tool_calls": [
                    ToolCall(
                        tool_name="todo_write",
                        arguments={
                            "todos": [
                                {"content": "分析需求", "status": "in_progress", "priority": "high"},
                                {"content": "设计实现方案", "status": "pending", "priority": "high"},
                                {"content": "编写代码", "status": "pending", "priority": "high"},
                                {"content": "测试验证", "status": "pending", "priority": "medium"}
                            ]
                        }
                    )
                ]
            }
        
        # 检查是否是代码生成请求
        if any(kw in content for kw in ["写", "创建", "生成", "code", "程序"]):
            # 提取文件名（简化处理）
            filename = self._extract_filename(content) or "script.py"
            
            return {
                "action": "tool_call",
                "thought": f"我将创建文件 {filename} 并编写代码",
                "tool_calls": [
                    ToolCall(
                        tool_name="write_file",
                        arguments={
                            "filename": filename,
                            "content": "# 生成的代码\nprint('Hello from Jarvis Code Agent!')"
                        }
                    )
                ]
            }
        
        # 默认：询问更多信息
        return {
            "action": "respond",
            "content": "我明白了。请告诉我更多细节，比如您需要什么编程语言，文件保存到哪里？"
        }
    
    def _extract_filename(self, content: str) -> Optional[str]:
        """从用户输入中提取文件名（简化实现）"""
        # 这里可以使用更复杂的 NLP 来提取
        if ".py" in content:
            return "script.py"
        elif ".js" in content:
            return "script.js"
        elif ".html" in content:
            return "index.html"
        return None
    
    def _execute_tool_calls(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
        """执行工具调用"""
        results = []
        
        for call in tool_calls:
            self.stats["tool_calls"] += 1
            
            # 显示工具调用
            args_str = json.dumps(call.arguments, ensure_ascii=False)
            print(f"{Fore.CYAN}  [工具] {call.tool_name}({args_str}){Style.RESET_ALL}")
            
            # 执行工具
            if call.tool_name in self.tools:
                try:
                    tool_func = self.tools[call.tool_name]
                    output = tool_func(**call.arguments)
                    
                    results.append(ToolResult(
                        call_id=call.call_id,
                        success=True,
                        output=str(output)
                    ))
                    
                    print(f"{Fore.GREEN}  [结果] {output}{Style.RESET_ALL}")
                    
                except Exception as e:
                    results.append(ToolResult(
                        call_id=call.call_id,
                        success=False,
                        output="",
                        error=str(e)
                    ))
                    print(f"{Fore.RED}  [错误] {e}{Style.RESET_ALL}")
            else:
                results.append(ToolResult(
                    call_id=call.call_id,
                    success=False,
                    output="",
                    error=f"未知工具: {call.tool_name}"
                ))
        
        return results
    
    def _is_task_complete(self) -> bool:
        """检查任务是否完成"""
        if not self.todo_list:
            return False
        
        # 所有任务都完成
        return all(item.status == "completed" for item in self.todo_list)
    
    def _generate_summary(self) -> str:
        """生成任务总结"""
        duration = datetime.now() - self.stats["start_time"] if self.stats["start_time"] else None
        
        summary = f"""
{Fore.GREEN}╔════════════════════════════════════════╗{Style.RESET_ALL}
{Fore.GREEN}║{Style.RESET_ALL}        任务完成总结        {Fore.GREEN}║{Style.RESET_ALL}
{Fore.GREEN}╠════════════════════════════════════════╣{Style.RESET_ALL}
{Fore.GREEN}║{Style.RESET_ALL} 任务: {self.current_task[:30]}...{Style.RESET_ALL}
{Fore.GREEN}║{Style.RESET_ALL} 迭代: {self.stats['total_iterations']}{Style.RESET_ALL}
{Fore.GREEN}║{Style.RESET_ALL} 工具调用: {self.stats['tool_calls']}{Style.RESET_ALL}
{Fore.GREEN}║{Style.RESET_ALL} 文件创建: {self.stats['files_created']}{Style.RESET_ALL}
{Fore.GREEN}║{Style.RESET_ALL} 耗时: {duration.seconds if duration else 'N/A'}秒{Style.RESET_ALL}
{Fore.GREEN}╚════════════════════════════════════════╝{Style.RESET_ALL}
"""
        
        print(summary)
        
        if self.voice_enabled:
            try:
                from voice_output import speak
                speak("任务已完成")
            except:
                pass
        
        return summary
    
    def end_session(self):
        """结束编程会话"""
        self.is_running = False
        print(f"\n{Fore.CYAN}[系统] Code Agent 会话已结束{Style.RESET_ALL}")
        
        # 保存会话历史
        self._save_session()
    
    def _save_session(self):
        """保存会话历史"""
        session_data = {
            "start_time": self.stats["start_time"].isoformat() if self.stats["start_time"] else None,
            "end_time": datetime.now().isoformat(),
            "stats": {k: v for k, v in self.stats.items() if k != "start_time"},
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat()
                }
                for m in self.messages
            ]
        }
        
        session_file = os.path.join(self.workspace, ".jarvis_sessions", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        os.makedirs(os.path.dirname(session_file), exist_ok=True)
        
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)


# 便捷函数
def quick_code(description: str, code: str, workspace: str = r"D:\jarvis\workspace") -> str:
    """
    快速编写并执行代码
    
    Args:
        description: 代码描述
        code: 代码内容
        workspace: 工作目录
        
    Returns:
        执行结果
    """
    agent = JarvisCodeAgent(voice_enabled=False, workspace=workspace)
    agent.start_session()
    
    # 创建文件
    filename = f"quick_script_{datetime.now().strftime('%H%M%S')}.py"
    filepath = os.path.join(workspace, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)
    
    print(f"{Fore.GREEN}[创建] {filename}{Style.RESET_ALL}")
    
    # 执行代码
    try:
        from .tools import run_python
    except ImportError:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))
        from code_tools import run_python
    
    result = run_python(filepath)
    
    print(f"{Fore.CYAN}[执行结果]{Style.RESET_ALL}\n{result}")
    
    agent.end_session()
    return result
