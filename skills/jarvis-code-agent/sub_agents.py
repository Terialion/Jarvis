"""
子代理系统 - 多 Agent 协作架构
实现规划 Agent、执行 Agent、审查 Agent 三个专业子代理
"""

import json
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from colorama import Fore, Style


class AgentRole(Enum):
    """子代理角色"""
    PLANNER = "planner"      # 规划 Agent
    EXECUTOR = "executor"    # 执行 Agent
    REVIEWER = "reviewer"    # 审查 Agent


@dataclass
class SubAgentResult:
    """子代理执行结果"""
    agent_role: AgentRole
    success: bool
    output: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TaskContext:
    """任务上下文，在子代理之间传递"""
    task_id: str
    original_request: str
    plan: Optional[Dict] = None
    code_files: List[str] = field(default_factory=list)
    test_results: Optional[Dict] = None
    review_comments: List[str] = field(default_factory=list)
    current_phase: str = "planning"
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseSubAgent:
    """子代理基类"""
    
    def __init__(self, role: AgentRole, llm_client: Optional[Any] = None):
        self.role = role
        self.llm_client = llm_client
        self.tools: Dict[str, Callable] = {}
        
    def register_tool(self, name: str, func: Callable):
        """注册工具"""
        self.tools[name] = func
        
    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """执行工具"""
        if tool_name in self.tools:
            return self.tools[tool_name](**kwargs)
        raise ValueError(f"工具不存在: {tool_name}")
    
    def run(self, context: TaskContext) -> SubAgentResult:
        """运行子代理（子类必须实现）"""
        raise NotImplementedError


class PlanningAgent(BaseSubAgent):
    """
    规划 Agent - 分析需求并生成详细计划
    
    职责：
    1. 分析用户需求的复杂度和范围
    2. 将大任务分解为可执行的子任务
    3. 确定任务依赖关系和执行顺序
    4. 选择合适的实现策略和模板
    """
    
    def __init__(self, llm_client: Optional[Any] = None):
        super().__init__(AgentRole.PLANNER, llm_client)
        
    def run(self, context: TaskContext) -> SubAgentResult:
        """运行规划 Agent"""
        print(f"\n{Fore.CYAN}[规划 Agent] 正在分析需求...{Style.RESET_ALL}")
        
        request = context.original_request
        
        # 使用 LLM 进行需求分析
        if self.llm_client:
            analysis = self._analyze_with_llm(request)
        else:
            analysis = self._analyze_with_rules(request)
        
        # 生成任务计划
        plan = self._generate_plan(request, analysis)
        context.plan = plan
        context.current_phase = "planning_complete"
        
        # 格式化输出
        output = self._format_plan_output(plan)
        
        print(f"{Fore.GREEN}[规划 Agent] 计划生成完成{Style.RESET_ALL}")
        
        return SubAgentResult(
            agent_role=self.role,
            success=True,
            output=output,
            metadata={
                "analysis": analysis,
                "plan": plan,
                "estimated_steps": len(plan.get("tasks", []))
            }
        )
    
    def _analyze_with_llm(self, request: str) -> Dict:
        """使用 LLM 分析需求"""
        prompt = f"""请分析以下编程任务需求，并提供结构化分析：

任务描述：
{request}

请从以下维度分析：
1. 任务类型（web_app/script/debug/refactor/general）
2. 技术栈建议
3. 复杂度评估（1-10）
4. 主要功能模块
5. 潜在风险点

以 JSON 格式返回：
{{
    "task_type": "类型",
    "tech_stack": ["技术1", "技术2"],
    "complexity": 5,
    "modules": ["模块1", "模块2"],
    "risks": ["风险1"],
    "estimated_time": "预计时间"
}}"""
        
        try:
            response = self.llm_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是一个专业的软件架构师，擅长分析需求并制定技术方案。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content
            # 提取 JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"{Fore.YELLOW}[规划 Agent] LLM 分析失败，使用规则分析: {e}{Style.RESET_ALL}")
        
        return self._analyze_with_rules(request)
    
    def _analyze_with_rules(self, request: str) -> Dict:
        """使用规则分析需求"""
        request_lower = request.lower()
        
        # 任务类型检测
        if any(kw in request_lower for kw in ["网站", "web", "页面", "html", "css"]):
            task_type = "web_app"
            tech_stack = ["HTML", "CSS", "JavaScript"]
        elif any(kw in request_lower for kw in ["脚本", "script", "自动化", "批处理"]):
            task_type = "script"
            tech_stack = ["Python"]
        elif any(kw in request_lower for kw in ["修复", "bug", "错误", "调试", "debug"]):
            task_type = "debug"
            tech_stack = ["Python"]
        elif any(kw in request_lower for kw in ["重构", "优化", "改进", "refactor"]):
            task_type = "refactor"
            tech_stack = ["Python"]
        else:
            task_type = "general"
            tech_stack = ["Python"]
        
        # 复杂度评估
        complexity = min(5 + len(request) // 50, 10)
        
        return {
            "task_type": task_type,
            "tech_stack": tech_stack,
            "complexity": complexity,
            "modules": ["主要功能模块"],
            "risks": [],
            "estimated_time": "未知"
        }
    
    def _generate_plan(self, request: str, analysis: Dict) -> Dict:
        """生成任务计划"""
        task_type = analysis.get("task_type", "general")
        
        # 根据任务类型选择模板
        templates = {
            "web_app": self._web_app_template,
            "script": self._script_template,
            "debug": self._debug_template,
            "refactor": self._refactor_template,
            "general": self._general_template
        }
        
        template_func = templates.get(task_type, self._general_template)
        return template_func(request, analysis)
    
    def _web_app_template(self, request: str, analysis: Dict) -> Dict:
        """Web 应用模板"""
        return {
            "project_type": "web_app",
            "description": request,
            "tasks": [
                {"id": "1", "content": "创建项目结构和基础文件", "type": "setup"},
                {"id": "2", "content": "编写 HTML 结构和内容", "type": "code"},
                {"id": "3", "content": "添加 CSS 样式", "type": "code"},
                {"id": "4", "content": "实现 JavaScript 交互逻辑", "type": "code"},
                {"id": "5", "content": "测试和验证功能", "type": "test"},
                {"id": "6", "content": "代码审查和优化", "type": "review"}
            ],
            "tech_stack": analysis.get("tech_stack", ["HTML", "CSS", "JavaScript"]),
            "files_to_create": ["index.html", "style.css", "script.js"]
        }
    
    def _script_template(self, request: str, analysis: Dict) -> Dict:
        """脚本模板"""
        return {
            "project_type": "script",
            "description": request,
            "tasks": [
                {"id": "1", "content": "分析需求和设计算法", "type": "plan"},
                {"id": "2", "content": "编写核心功能代码", "type": "code"},
                {"id": "3", "content": "添加错误处理和日志", "type": "code"},
                {"id": "4", "content": "编写测试用例", "type": "test"},
                {"id": "5", "content": "运行测试验证", "type": "test"},
                {"id": "6", "content": "代码审查和优化", "type": "review"}
            ],
            "tech_stack": analysis.get("tech_stack", ["Python"]),
            "files_to_create": ["main.py", "test_main.py"]
        }
    
    def _debug_template(self, request: str, analysis: Dict) -> Dict:
        """调试模板"""
        return {
            "project_type": "debug",
            "description": request,
            "tasks": [
                {"id": "1", "content": "分析错误信息和代码", "type": "analyze"},
                {"id": "2", "content": "定位问题根源", "type": "analyze"},
                {"id": "3", "content": "修复代码错误", "type": "code"},
                {"id": "4", "content": "验证修复结果", "type": "test"},
                {"id": "5", "content": "代码审查", "type": "review"}
            ],
            "tech_stack": analysis.get("tech_stack", ["Python"]),
            "files_to_create": []
        }
    
    def _refactor_template(self, request: str, analysis: Dict) -> Dict:
        """重构模板"""
        return {
            "project_type": "refactor",
            "description": request,
            "tasks": [
                {"id": "1", "content": "分析现有代码结构", "type": "analyze"},
                {"id": "2", "content": "制定重构计划", "type": "plan"},
                {"id": "3", "content": "逐步重构代码", "type": "code"},
                {"id": "4", "content": "运行测试确保功能不变", "type": "test"},
                {"id": "5", "content": "代码审查和优化", "type": "review"}
            ],
            "tech_stack": analysis.get("tech_stack", ["Python"]),
            "files_to_create": []
        }
    
    def _general_template(self, request: str, analysis: Dict) -> Dict:
        """通用模板"""
        return {
            "project_type": "general",
            "description": request,
            "tasks": [
                {"id": "1", "content": "分析需求", "type": "plan"},
                {"id": "2", "content": "设计和实现", "type": "code"},
                {"id": "3", "content": "测试验证", "type": "test"},
                {"id": "4", "content": "代码审查", "type": "review"}
            ],
            "tech_stack": analysis.get("tech_stack", ["Python"]),
            "files_to_create": []
        }
    
    def _format_plan_output(self, plan: Dict) -> str:
        """格式化计划输出"""
        lines = [
            f"{Fore.CYAN}╔════════════════════════════════════════╗{Style.RESET_ALL}",
            f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.YELLOW}[任务计划]{Style.RESET_ALL}".ljust(43) + f"{Fore.CYAN}║{Style.RESET_ALL}",
            f"{Fore.CYAN}╠════════════════════════════════════════╣{Style.RESET_ALL}",
            f"项目类型: {plan.get('project_type', 'unknown')}",
            f"技术栈: {', '.join(plan.get('tech_stack', []))}",
            f"描述: {plan.get('description', '')[:50]}...",
            "",
            "任务列表:",
        ]
        
        for task in plan.get("tasks", []):
            lines.append(f"  [{task.get('id', '?')}] {task.get('content', '')} ({task.get('type', 'task')})")
        
        if plan.get("files_to_create"):
            lines.extend(["", "需要创建的文件:"])
            for f in plan.get("files_to_create", []):
                lines.append(f"  - {f}")
        
        lines.append(f"{Fore.CYAN}╚════════════════════════════════════════╝{Style.RESET_ALL}")
        
        return "\n".join(lines)


class ExecutionAgent(BaseSubAgent):
    """
    执行 Agent - 编写代码和运行测试
    
    职责：
    1. 根据计划编写代码
    2. 创建项目文件
    3. 运行和调试代码
    4. 执行测试验证
    """
    
    def __init__(self, llm_client: Optional[Any] = None):
        super().__init__(AgentRole.EXECUTOR, llm_client)
        self.execution_log: List[Dict] = []
        
    def run(self, context: TaskContext) -> SubAgentResult:
        """运行执行 Agent"""
        print(f"\n{Fore.CYAN}[执行 Agent] 开始执行任务...{Style.RESET_ALL}")
        
        if not context.plan:
            return SubAgentResult(
                agent_role=self.role,
                success=False,
                output="错误：没有可用的任务计划"
            )
        
        plan = context.plan
        results = []
        
        # 执行每个任务
        for task in plan.get("tasks", []):
            task_id = task.get("id", "?")
            task_content = task.get("content", "")
            task_type = task.get("type", "task")
            
            print(f"{Fore.YELLOW}  执行任务 [{task_id}]: {task_content}{Style.RESET_ALL}")
            
            # 根据任务类型执行不同操作
            if task_type == "setup":
                result = self._execute_setup(task, context)
            elif task_type == "code":
                result = self._execute_code(task, context)
            elif task_type == "test":
                result = self._execute_test(task, context)
            elif task_type == "analyze":
                result = self._execute_analyze(task, context)
            elif task_type == "plan":
                result = self._execute_plan(task, context)
            else:
                result = self._execute_generic(task, context)
            
            results.append({
                "task_id": task_id,
                "content": task_content,
                "success": result.get("success", False),
                "output": result.get("output", "")
            })
            
            if result.get("success"):
                print(f"{Fore.GREEN}    [OK] 完成{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}    [FAIL] {result.get('output', '失败')}{Style.RESET_ALL}")
        
        context.current_phase = "execution_complete"
        
        # 统计结果
        success_count = sum(1 for r in results if r["success"])
        total_count = len(results)
        
        output = f"执行完成: {success_count}/{total_count} 个任务成功"
        
        print(f"{Fore.GREEN}[执行 Agent] {output}{Style.RESET_ALL}")
        
        return SubAgentResult(
            agent_role=self.role,
            success=success_count == total_count,
            output=output,
            metadata={
                "results": results,
                "success_count": success_count,
                "total_count": total_count
            }
        )
    
    def _execute_setup(self, task: Dict, context: TaskContext) -> Dict:
        """执行设置任务"""
        try:
            # 创建项目结构
            if "create_project" in self.tools:
                result = self.tools["create_project"](
                    name=context.task_id,
                    template="python" if context.plan.get("project_type") != "web_app" else "web"
                )
                return {"success": True, "output": str(result)}
            return {"success": True, "output": "跳过设置"}
        except Exception as e:
            return {"success": False, "output": str(e)}
    
    def _execute_code(self, task: Dict, context: TaskContext) -> Dict:
        """执行编码任务"""
        try:
            # 使用 LLM 生成代码
            if self.llm_client and "write_file" in self.tools:
                code = self._generate_code_with_llm(task, context)
                
                # 确定文件名
                filename = self._determine_filename(task, context)
                
                # 写入文件
                result = self.tools["write_file"](filepath=filename, content=code)
                context.code_files.append(filename)
                
                return {"success": True, "output": f"创建文件: {filename}"}
            
            return {"success": True, "output": "跳过编码"}
        except Exception as e:
            return {"success": False, "output": str(e)}
    
    def _execute_test(self, task: Dict, context: TaskContext) -> Dict:
        """执行测试任务"""
        try:
            if "run_tests" in self.tools and context.code_files:
                result = self.tools["run_tests"](filepath=context.code_files[0])
                context.test_results = result
                return {"success": result.get("success", False), "output": str(result)}
            return {"success": True, "output": "跳过测试"}
        except Exception as e:
            return {"success": False, "output": str(e)}
    
    def _execute_analyze(self, task: Dict, context: TaskContext) -> Dict:
        """执行分析任务"""
        try:
            if "analyze_code" in self.tools and context.code_files:
                result = self.tools["analyze_code"](filepath=context.code_files[0])
                return {"success": True, "output": str(result)}
            return {"success": True, "output": "分析完成"}
        except Exception as e:
            return {"success": False, "output": str(e)}
    
    def _execute_plan(self, task: Dict, context: TaskContext) -> Dict:
        """执行规划任务"""
        return {"success": True, "output": "规划完成"}
    
    def _execute_generic(self, task: Dict, context: TaskContext) -> Dict:
        """执行通用任务"""
        return {"success": True, "output": "任务完成"}
    
    def _generate_code_with_llm(self, task: Dict, context: TaskContext) -> str:
        """使用 LLM 生成代码"""
        prompt = f"""请根据以下任务生成代码：

任务：{task.get('content', '')}
项目类型：{context.plan.get('project_type', 'general')}
技术栈：{', '.join(context.plan.get('tech_stack', ['Python']))}
原始需求：{context.original_request}

请生成完整、可运行的代码，包含必要的注释。"""
        
        try:
            response = self.llm_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是一个专业的程序员，擅长编写高质量、可维护的代码。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            
            # 提取代码块
            code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', content, re.DOTALL)
            if code_blocks:
                return code_blocks[0]
            return content
        except Exception as e:
            print(f"{Fore.YELLOW}LLM 代码生成失败: {e}{Style.RESET_ALL}")
            return f"# TODO: {task.get('content', '')}\n# 代码生成失败，请手动实现"
    
    def _determine_filename(self, task: Dict, context: TaskContext) -> str:
        """确定文件名"""
        content = task.get("content", "").lower()
        project_type = context.plan.get("project_type", "general")
        
        if project_type == "web_app":
            if "html" in content:
                return "index.html"
            elif "css" in content:
                return "style.css"
            elif "javascript" in content or "js" in content:
                return "script.js"
        
        if project_type == "script" or project_type == "general":
            if "test" in content:
                return "test_main.py"
            return "main.py"
        
        return f"file_{len(context.code_files)}.py"


class ReviewAgent(BaseSubAgent):
    """
    审查 Agent - 代码审查和优化建议
    
    职责：
    1. 代码质量审查
    2. 性能优化建议
    3. 安全检查
    4. 生成审查报告
    """
    
    def __init__(self, llm_client: Optional[Any] = None):
        super().__init__(AgentRole.REVIEWER, llm_client)
        self.review_rules = self._load_review_rules()
    
    def _load_review_rules(self) -> Dict:
        """加载审查规则"""
        return {
            "python": {
                "naming": r'^[a-z_][a-z0-9_]*$',
                "max_line_length": 100,
                "required_docstring": True
            }
        }
    
    def run(self, context: TaskContext) -> SubAgentResult:
        """运行审查 Agent"""
        print(f"\n{Fore.CYAN}[审查 Agent] 开始代码审查...{Style.RESET_ALL}")
        
        if not context.code_files:
            return SubAgentResult(
                agent_role=self.role,
                success=True,
                output="没有需要审查的代码文件"
            )
        
        review_results = []
        
        for filepath in context.code_files:
            print(f"{Fore.YELLOW}  审查文件: {filepath}{Style.RESET_ALL}")
            
            # 读取文件内容
            try:
                if "read_file" in self.tools:
                    content = self.tools["read_file"](filepath=filepath)
                else:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                
                # 执行审查
                if self.llm_client:
                    review = self._review_with_llm(filepath, content, context)
                else:
                    review = self._review_with_rules(filepath, content)
                
                review_results.append({
                    "file": filepath,
                    "review": review
                })
                
                context.review_comments.extend(review.get("issues", []))
                
            except Exception as e:
                review_results.append({
                    "file": filepath,
                    "error": str(e)
                })
        
        context.current_phase = "review_complete"
        
        # 生成审查报告
        output = self._format_review_report(review_results)
        
        print(f"{Fore.GREEN}[审查 Agent] 审查完成{Style.RESET_ALL}")
        
        return SubAgentResult(
            agent_role=self.role,
            success=True,
            output=output,
            metadata={
                "reviews": review_results,
                "total_files": len(context.code_files),
                "total_issues": len(context.review_comments)
            }
        )
    
    def _review_with_llm(self, filepath: str, content: str, context: TaskContext) -> Dict:
        """使用 LLM 审查代码"""
        prompt = f"""请审查以下代码，并提供详细的审查意见：

文件：{filepath}

代码：
```python
{content[:2000]}  # 限制长度
```

请从以下维度审查：
1. 代码质量和可读性
2. 潜在的错误或 bug
3. 性能优化建议
4. 安全考虑
5. 最佳实践遵循情况

以 JSON 格式返回：
{{
    "score": 85,
    "issues": ["问题1", "问题2"],
    "suggestions": ["建议1", "建议2"],
    "summary": "总体评价"
}}"""
        
        try:
            response = self.llm_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是一个资深的代码审查专家，擅长发现代码问题和提供改进建议。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"{Fore.YELLOW}LLM 审查失败: {e}{Style.RESET_ALL}")
        
        return self._review_with_rules(filepath, content)
    
    def _review_with_rules(self, filepath: str, content: str) -> Dict:
        """使用规则审查代码"""
        issues = []
        suggestions = []
        
        lines = content.split('\n')
        
        # 检查行长度
        for i, line in enumerate(lines, 1):
            if len(line) > 100:
                issues.append(f"第{i}行超过100字符")
        
        # 检查是否有文档字符串
        if '"""' not in content and "'''" not in content:
            suggestions.append("建议添加模块文档字符串")
        
        # 检查是否有 TODO
        if 'TODO' in content:
            suggestions.append("代码中包含 TODO 项，建议完成")
        
        # 评分
        score = max(100 - len(issues) * 5 - len(suggestions) * 2, 60)
        
        return {
            "score": score,
            "issues": issues,
            "suggestions": suggestions,
            "summary": f"发现 {len(issues)} 个问题，{len(suggestions)} 条建议"
        }
    
    def _format_review_report(self, review_results: List[Dict]) -> str:
        """格式化审查报告"""
        lines = [
            f"{Fore.CYAN}╔════════════════════════════════════════╗{Style.RESET_ALL}",
            f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.YELLOW}[代码审查报告]{Style.RESET_ALL}".ljust(43) + f"{Fore.CYAN}║{Style.RESET_ALL}",
            f"{Fore.CYAN}╠════════════════════════════════════════╣{Style.RESET_ALL}",
        ]
        
        for result in review_results:
            filepath = result.get("file", "unknown")
            lines.append(f"\n文件: {filepath}")
            
            if "error" in result:
                lines.append(f"  {Fore.RED}错误: {result['error']}{Style.RESET_ALL}")
                continue
            
            review = result.get("review", {})
            score = review.get("score", 0)
            
            color = Fore.GREEN if score >= 80 else Fore.YELLOW if score >= 60 else Fore.RED
            lines.append(f"  评分: {color}{score}/100{Style.RESET_ALL}")
            
            issues = review.get("issues", [])
            if issues:
                lines.append(f"  {Fore.RED}问题 ({len(issues)}):{Style.RESET_ALL}")
                for issue in issues[:5]:  # 最多显示5个
                    lines.append(f"    - {issue}")
            
            suggestions = review.get("suggestions", [])
            if suggestions:
                lines.append(f"  {Fore.YELLOW}建议 ({len(suggestions)}):{Style.RESET_ALL}")
                for suggestion in suggestions[:3]:  # 最多显示3个
                    lines.append(f"    - {suggestion}")
            
            summary = review.get("summary", "")
            if summary:
                lines.append(f"  总结: {summary}")
        
        lines.append(f"{Fore.CYAN}╚════════════════════════════════════════╝{Style.RESET_ALL}")
        
        return "\n".join(lines)


class SubAgentOrchestrator:
    """
    子代理编排器 - 协调多个子代理协作
    """
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
        self.agents: Dict[AgentRole, BaseSubAgent] = {}
        self._init_agents()
    
    def _init_agents(self):
        """初始化子代理"""
        self.agents[AgentRole.PLANNER] = PlanningAgent(self.llm_client)
        self.agents[AgentRole.EXECUTOR] = ExecutionAgent(self.llm_client)
        self.agents[AgentRole.REVIEWER] = ReviewAgent(self.llm_client)
    
    def register_tools(self, tools: Dict[str, Callable]):
        """为所有子代理注册工具"""
        for agent in self.agents.values():
            for name, func in tools.items():
                agent.register_tool(name, func)
    
    def execute_full_workflow(self, request: str) -> Dict:
        """执行完整的工作流"""
        print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        print(f"{Fore.CYAN} 启动多 Agent 协作工作流{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        
        # 创建任务上下文
        context = TaskContext(
            task_id=f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            original_request=request
        )
        
        results = {}
        
        # Phase 1: 规划
        print(f"\n{Fore.YELLOW}>>> Phase 1: 规划{Style.RESET_ALL}")
        planner = self.agents[AgentRole.PLANNER]
        plan_result = planner.run(context)
        results["planning"] = plan_result
        
        if not plan_result.success:
            print(f"{Fore.RED}规划阶段失败，终止工作流{Style.RESET_ALL}")
            return results
        
        # Phase 2: 执行
        print(f"\n{Fore.YELLOW}>>> Phase 2: 执行{Style.RESET_ALL}")
        executor = self.agents[AgentRole.EXECUTOR]
        exec_result = executor.run(context)
        results["execution"] = exec_result
        
        # Phase 3: 审查
        print(f"\n{Fore.YELLOW}>>> Phase 3: 审查{Style.RESET_ALL}")
        reviewer = self.agents[AgentRole.REVIEWER]
        review_result = reviewer.run(context)
        results["review"] = review_result
        
        # 总结
        print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        print(f"{Fore.GREEN} 工作流执行完成{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        
        return {
            "context": context,
            "results": results,
            "success": all(r.success for r in results.values()),
            "summary": {
                "planning": plan_result.output[:100] if plan_result.success else "失败",
                "execution": exec_result.output if exec_result.success else "失败",
                "review": review_result.output[:100] if review_result.success else "失败"
            }
        }
    
    def execute_single_agent(self, role: AgentRole, context: TaskContext) -> SubAgentResult:
        """执行单个子代理"""
        if role not in self.agents:
            raise ValueError(f"未知的子代理角色: {role}")
        
        agent = self.agents[role]
        return agent.run(context)


# 便捷函数
def create_orchestrator(llm_client: Optional[Any] = None) -> SubAgentOrchestrator:
    """创建子代理编排器"""
    return SubAgentOrchestrator(llm_client)


def quick_workflow(request: str, tools: Dict[str, Callable], llm_client: Optional[Any] = None) -> Dict:
    """快速执行完整工作流"""
    orchestrator = create_orchestrator(llm_client)
    orchestrator.register_tools(tools)
    return orchestrator.execute_full_workflow(request)
