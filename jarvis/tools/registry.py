"""
工具注册表 — 管理所有工具的注册、查找、调用
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Type

from .base import BaseTool, ToolMeta, ToolResult, ToolStatus


class ToolRegistry:
    """
    全局工具注册表
    
    职责：
    - 注册 / 注销工具
    - 按名称 / 分类 / 标签检索
    - 调用工具（附带日志和指标）
    - 生成工具清单文档（供 LLM 使用）
    """

    _instance: Optional["ToolRegistry"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._tools:   Dict[str, BaseTool]    = {}   # name → instance
        self._aliases: Dict[str, str]         = {}   # alias → canonical name
        self._stats:   Dict[str, Dict]        = {}   # name → call stats
        self._initialized = True

    # ──────────────────────────────────────
    # 注册
    # ──────────────────────────────────────

    def register(
        self,
        tool_cls_or_instance: Type[BaseTool] | BaseTool,
        aliases: Optional[List[str]] = None,
        override: bool = False,
    ) -> "ToolRegistry":
        """
        注册工具，支持类或实例。
        返回 self 以便链式调用。
        """
        # 实例化（如果传入的是类）
        if isinstance(tool_cls_or_instance, type):
            instance: BaseTool = tool_cls_or_instance()
        else:
            instance = tool_cls_or_instance

        name = instance.name
        if not name:
            raise ValueError(f"工具 {tool_cls_or_instance} 缺少 name 属性")

        if name in self._tools and not override:
            raise ValueError(f"工具 '{name}' 已注册，使用 override=True 强制覆盖")

        self._tools[name]  = instance
        self._stats[name]  = {"calls": 0, "success": 0, "failed": 0, "total_ms": 0}

        # 注册别名
        for alias in (aliases or []):
            self._aliases[alias] = name

        return self

    def unregister(self, name: str):
        """注销工具"""
        self._tools.pop(name, None)
        self._stats.pop(name, None)
        # 清除别名
        dead = [k for k, v in self._aliases.items() if v == name]
        for k in dead:
            del self._aliases[k]

    # ──────────────────────────────────────
    # 查找
    # ──────────────────────────────────────

    def get(self, name: str) -> Optional[BaseTool]:
        """按名称或别名获取工具"""
        canonical = self._aliases.get(name, name)
        return self._tools.get(canonical)

    def list_tools(
        self,
        category: Optional[str]   = None,
        tags:     Optional[List[str]] = None,
        requires_network: Optional[bool] = None,
    ) -> List[BaseTool]:
        """列出工具，支持过滤"""
        tools = list(self._tools.values())

        if category:
            tools = [t for t in tools if t.category == category]
        if tags:
            tools = [t for t in tools if any(tag in t.tags for tag in tags)]
        if requires_network is not None:
            tools = [t for t in tools if t.requires_network == requires_network]

        return tools

    def categories(self) -> List[str]:
        """获取所有分类"""
        return sorted({t.category for t in self._tools.values()})

    def has(self, name: str) -> bool:
        """工具是否已注册"""
        return self.get(name) is not None

    # ──────────────────────────────────────
    # 调用
    # ──────────────────────────────────────

    def call(self, name: str, **kwargs) -> ToolResult:
        """
        调用工具（附带指标统计）
        
        即使工具不存在也返回 ToolResult，不抛异常。
        """
        tool = self.get(name)
        if tool is None:
            return ToolResult.fail(f"工具 '{name}' 不存在，可用工具: {self.tool_names()}")

        stat = self._stats[tool.name]
        stat["calls"] += 1

        result = tool(**kwargs)     # 调用 __call__，内部已捕获异常

        stat["total_ms"] += int(result.elapsed * 1000)
        if result.status == ToolStatus.SUCCESS:
            stat["success"] += 1
        elif result.status == ToolStatus.FAILED:
            stat["failed"] += 1

        return result

    # ──────────────────────────────────────
    # 文档生成（供 LLM Prompt 使用）
    # ──────────────────────────────────────

    def to_prompt(self, category: Optional[str] = None) -> str:
        """
        生成工具清单文本，格式适合注入到 LLM System Prompt。
        
        输出示例::
        
            ## 可用工具
            
            ### search_web [network]
            搜索互联网，返回相关网页摘要。
            参数:
              - query (str, 必填): 搜索关键词
              - max_results (int, 默认=10): 最大结果数
        """
        tools = self.list_tools(category=category)
        if not tools:
            return "（暂无可用工具）"

        lines = ["## 可用工具\n"]
        for t in sorted(tools, key=lambda x: (x.category, x.name)):
            lines.append(f"### {t.name}  [{t.category}]")
            if t.description:
                lines.append(t.description)
            if t.requires_network:
                lines.append("⚠️ 需要联网")
            if t.params:
                lines.append("参数:")
                for p in t.params:
                    req_str  = "必填" if p.required else f"默认={p.default}"
                    desc_str = f"  {p.description}" if p.description else ""
                    lines.append(f"  - {p.name} ({p.type.__name__}, {req_str}){desc_str}")
            lines.append("")

        return "\n".join(lines)

    def to_openai_functions(self, category: Optional[str] = None) -> List[Dict]:
        """
        生成 OpenAI function-calling 格式的工具描述列表
        （用于 DeepSeek / OpenAI function calling）
        """
        tools = self.list_tools(category=category)
        result = []

        for t in tools:
            properties = {}
            required   = []

            for p in t.params:
                type_map = {
                    str:   "string",
                    int:   "integer",
                    float: "number",
                    bool:  "boolean",
                    list:  "array",
                    dict:  "object",
                }
                prop: Dict[str, Any] = {
                    "type":        type_map.get(p.type, "string"),
                    "description": p.description or "",
                }
                if p.choices:
                    prop["enum"] = p.choices
                if p.default is not None:
                    prop["default"] = p.default

                properties[p.name] = prop
                if p.required:
                    required.append(p.name)

            result.append({
                "type": "function",
                "function": {
                    "name":        t.name,
                    "description": t.description,
                    "parameters": {
                        "type":       "object",
                        "properties": properties,
                        "required":   required,
                    }
                }
            })

        return result

    # ──────────────────────────────────────
    # 统计 & 调试
    # ──────────────────────────────────────

    def stats(self, name: Optional[str] = None) -> Dict:
        """获取调用统计"""
        if name:
            return self._stats.get(name, {})
        return self._stats.copy()

    def tool_names(self) -> List[str]:
        return sorted(self._tools.keys())

    def __len__(self):
        return len(self._tools)

    def __repr__(self):
        return f"<ToolRegistry: {len(self)} tools>"


# 全局单例
def get_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    return ToolRegistry()
