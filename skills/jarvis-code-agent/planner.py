"""
Jarvis Code Agent - 任务规划器 v2.0

智能任务分解、依赖管理、进度跟踪
"""

import os
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """任务优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Task:
    """任务定义"""
    id: str
    content: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    dependencies: List[str] = field(default_factory=list)
    subtasks: List['Task'] = field(default_factory=list)
    estimated_time: Optional[int] = None  # 分钟
    actual_time: Optional[int] = None
    notes: str = ""
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "dependencies": self.dependencies,
            "subtasks": [t.to_dict() for t in self.subtasks],
            "estimated_time": self.estimated_time,
            "actual_time": self.actual_time,
            "notes": self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Task':
        """从字典创建"""
        task = cls(
            id=data["id"],
            content=data["content"],
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", "medium")),
            dependencies=data.get("dependencies", []),
            estimated_time=data.get("estimated_time"),
            actual_time=data.get("actual_time"),
            notes=data.get("notes", "")
        )
        
        if data.get("created_at"):
            task.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            task.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            task.completed_at = datetime.fromisoformat(data["completed_at"])
        
        # 递归创建子任务
        for subtask_data in data.get("subtasks", []):
            task.subtasks.append(Task.from_dict(subtask_data))
        
        return task
    
    def start(self):
        """开始任务"""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.now()
    
    def complete(self):
        """完成任务"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()
        if self.started_at:
            self.actual_time = int((self.completed_at - self.started_at).total_seconds() / 60)
    
    def block(self):
        """阻塞任务"""
        self.status = TaskStatus.BLOCKED
    
    def is_ready(self) -> bool:
        """检查任务是否准备好执行（依赖已完成）"""
        return self.status == TaskStatus.PENDING and len(self.dependencies) == 0


class TaskPlanner:
    """
    任务规划器
    
    功能：
    1. 任务分解
    2. 依赖管理
    3. 进度跟踪
    4. 智能调度
    """
    
    def __init__(self, workspace: str = r"D:\jarvis\workspace"):
        self.workspace = workspace
        self.tasks: Dict[str, Task] = {}
        self.plans_dir = os.path.join(workspace, ".jarvis_plans")
        os.makedirs(self.plans_dir, exist_ok=True)
    
    def create_plan(self, goal: str, task_descriptions: List[str]) -> List[Task]:
        """
        创建任务计划
        
        Args:
            goal: 总体目标
            task_descriptions: 任务描述列表
            
        Returns:
            任务列表
        """
        tasks = []
        for i, desc in enumerate(task_descriptions, 1):
            task = Task(
                id=f"task_{i}",
                content=desc,
                priority=TaskPriority.MEDIUM
            )
            
            # 设置依赖：每个任务依赖于前一个任务
            if i > 1:
                task.dependencies = [f"task_{i-1}"]
            
            tasks.append(task)
            self.tasks[task.id] = task
        
        return tasks
    
    def create_smart_plan(self, goal: str, context: str = "") -> List[Task]:
        """
        基于目标智能创建任务计划
        
        Args:
            goal: 目标描述
            context: 额外上下文
            
        Returns:
            任务列表
        """
        goal_lower = goal.lower()
        
        # 根据目标类型选择模板
        if any(kw in goal_lower for kw in ["web", "网站", "flask", "django", "app"]):
            return self._create_web_app_plan(goal)
        elif any(kw in goal_lower for kw in ["script", "脚本", "工具", "tool"]):
            return self._create_script_plan(goal)
        elif any(kw in goal_lower for kw in ["fix", "修复", "bug", "debug"]):
            return self._create_debug_plan(goal)
        elif any(kw in goal_lower for kw in ["refactor", "重构", "优化", "improve"]):
            return self._create_refactor_plan(goal)
        else:
            return self._create_general_plan(goal)
    
    def _create_web_app_plan(self, goal: str) -> List[Task]:
        """创建 Web 应用开发计划"""
        tasks = [
            Task(id="1", content="分析需求并设计应用架构", priority=TaskPriority.HIGH),
            Task(id="2", content="创建项目结构和基础文件", priority=TaskPriority.HIGH),
            Task(id="3", content="实现核心功能模块", priority=TaskPriority.HIGH),
            Task(id="4", content="添加前端界面", priority=TaskPriority.MEDIUM),
            Task(id="5", content="编写测试用例", priority=TaskPriority.MEDIUM),
            Task(id="6", content="运行测试并修复问题", priority=TaskPriority.HIGH),
        ]
        
        # 设置依赖
        for i in range(1, len(tasks)):
            tasks[i].dependencies = [str(i)]
        
        for task in tasks:
            self.tasks[task.id] = task
        
        return tasks
    
    def _create_script_plan(self, goal: str) -> List[Task]:
        """创建脚本开发计划"""
        tasks = [
            Task(id="1", content="分析需求并设计脚本逻辑", priority=TaskPriority.HIGH),
            Task(id="2", content="编写核心代码", priority=TaskPriority.HIGH),
            Task(id="3", content="添加错误处理", priority=TaskPriority.MEDIUM),
            Task(id="4", content="测试脚本功能", priority=TaskPriority.HIGH),
        ]
        
        for i in range(1, len(tasks)):
            tasks[i].dependencies = [str(i)]
        
        for task in tasks:
            self.tasks[task.id] = task
        
        return tasks
    
    def _create_debug_plan(self, goal: str) -> List[Task]:
        """创建调试计划"""
        tasks = [
            Task(id="1", content="复现问题", priority=TaskPriority.CRITICAL),
            Task(id="2", content="分析错误日志和代码", priority=TaskPriority.CRITICAL),
            Task(id="3", content="定位问题根源", priority=TaskPriority.CRITICAL),
            Task(id="4", content="实施修复", priority=TaskPriority.HIGH),
            Task(id="5", content="验证修复效果", priority=TaskPriority.HIGH),
        ]
        
        for i in range(1, len(tasks)):
            tasks[i].dependencies = [str(i)]
        
        for task in tasks:
            self.tasks[task.id] = task
        
        return tasks
    
    def _create_refactor_plan(self, goal: str) -> List[Task]:
        """创建重构计划"""
        tasks = [
            Task(id="1", content="分析现有代码结构", priority=TaskPriority.HIGH),
            Task(id="2", content="识别重构点", priority=TaskPriority.HIGH),
            Task(id="3", content="编写重构后的代码", priority=TaskPriority.HIGH),
            Task(id="4", content="运行测试确保功能正常", priority=TaskPriority.CRITICAL),
        ]
        
        for i in range(1, len(tasks)):
            tasks[i].dependencies = [str(i)]
        
        for task in tasks:
            self.tasks[task.id] = task
        
        return tasks
    
    def _create_general_plan(self, goal: str) -> List[Task]:
        """创建通用计划"""
        tasks = [
            Task(id="1", content="分析需求", priority=TaskPriority.HIGH),
            Task(id="2", content="制定实现方案", priority=TaskPriority.HIGH),
            Task(id="3", content="执行实现", priority=TaskPriority.HIGH),
            Task(id="4", content="验证结果", priority=TaskPriority.MEDIUM),
        ]
        
        for i in range(1, len(tasks)):
            tasks[i].dependencies = [str(i)]
        
        for task in tasks:
            self.tasks[task.id] = task
        
        return tasks
    
    def get_next_task(self) -> Optional[Task]:
        """获取下一个可执行的任务"""
        for task in self.tasks.values():
            if task.is_ready():
                return task
        return None
    
    def get_progress(self) -> Dict[str, Any]:
        """获取进度统计"""
        total = len(self.tasks)
        if total == 0:
            return {"total": 0, "completed": 0, "percentage": 0}
        
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        in_progress = sum(1 for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS)
        pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        blocked = sum(1 for t in self.tasks.values() if t.status == TaskStatus.BLOCKED)
        
        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
            "blocked": blocked,
            "percentage": int(completed / total * 100)
        }
    
    def save_plan(self, name: str):
        """保存计划到文件"""
        plan_data = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "tasks": [task.to_dict() for task in self.tasks.values()]
        }
        
        filepath = os.path.join(self.plans_dir, f"{name}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(plan_data, f, ensure_ascii=False, indent=2)
        
        return filepath
    
    def load_plan(self, name: str) -> bool:
        """从文件加载计划"""
        filepath = os.path.join(self.plans_dir, f"{name}.json")
        
        if not os.path.exists(filepath):
            return False
        
        with open(filepath, 'r', encoding='utf-8') as f:
            plan_data = json.load(f)
        
        self.tasks = {}
        for task_data in plan_data.get("tasks", []):
            task = Task.from_dict(task_data)
            self.tasks[task.id] = task
        
        return True
    
    def list_plans(self) -> List[str]:
        """列出所有保存的计划"""
        plans = []
        if os.path.exists(self.plans_dir):
            for filename in os.listdir(self.plans_dir):
                if filename.endswith('.json'):
                    plans.append(filename[:-5])  # 去掉 .json
        return plans
    
    def clear(self):
        """清空所有任务"""
        self.tasks = {}


# 便捷函数
def quick_plan(goal: str) -> List[Task]:
    """
    快速创建任务计划
    
    Args:
        goal: 目标描述
        
    Returns:
        任务列表
    """
    planner = TaskPlanner()
    return planner.create_smart_plan(goal)


def format_plan(tasks: List[Task]) -> str:
    """
    格式化任务计划为字符串
    
    Args:
        tasks: 任务列表
        
    Returns:
        格式化字符串
    """
    lines = ["[任务计划]", "=" * 40]
    
    for i, task in enumerate(tasks, 1):
        status_icon = {
            TaskStatus.COMPLETED: "[OK]",
            TaskStatus.IN_PROGRESS: "[>]",
            TaskStatus.PENDING: "[ ]",
            TaskStatus.BLOCKED: "[!]",
            TaskStatus.CANCELLED: "[X]"
        }.get(task.status, "[ ]")
        
        priority_icon = {
            TaskPriority.CRITICAL: "[CRIT]",
            TaskPriority.HIGH: "[HIGH]",
            TaskPriority.MEDIUM: "[MED]",
            TaskPriority.LOW: "[LOW]"
        }.get(task.priority, "[MED]")
        
        lines.append(f"{i}. {status_icon} {priority_icon} {task.content}")
        
        if task.dependencies:
            lines.append(f"   依赖: {', '.join(task.dependencies)}")
    
    return "\n".join(lines)


# 测试代码
if __name__ == "__main__":
    # 测试任务规划
    planner = TaskPlanner()
    
    print("=== 测试 Web 应用计划 ===")
    tasks = planner.create_smart_plan("创建一个 Flask Web 应用")
    print(format_plan(tasks))
    
    print("\n=== 测试脚本计划 ===")
    planner.clear()
    tasks = planner.create_smart_plan("写一个文件处理脚本")
    print(format_plan(tasks))
    
    print("\n=== 测试进度跟踪 ===")
    planner.clear()
    tasks = planner.create_smart_plan("示例任务")
    
    # 模拟进度
    tasks[0].start()
    tasks[0].complete()
    tasks[1].start()
    
    progress = planner.get_progress()
    print(f"进度: {progress['completed']}/{progress['total']} ({progress['percentage']}%)")
