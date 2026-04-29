"""
工具基类与数据结构

每个工具都是一个继承 BaseTool 的类，或用 @tool 装饰器快速定义。
"""
from __future__ import annotations

import inspect
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union


# ──────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────

class ToolStatus(Enum):
    SUCCESS  = "success"
    FAILED   = "failed"
    PARTIAL  = "partial"   # 部分成功（例如搜索只拿到部分结果）
    SKIPPED  = "skipped"   # 前置条件不满足，跳过


@dataclass
class ToolResult:
    """工具调用返回值"""
    status:  ToolStatus
    data:    Any                        = None
    message: str                        = ""
    error:   Optional[Exception]        = None
    meta:    Dict[str, Any]             = field(default_factory=dict)
    elapsed: float                      = 0.0   # 执行耗时（秒）

    # ── 便捷构造 ──────────────────────────
    @classmethod
    def ok(cls, data: Any = None, message: str = "", **meta) -> "ToolResult":
        return cls(status=ToolStatus.SUCCESS, data=data, message=message, meta=meta)

    @classmethod
    def fail(cls, message: str, error: Optional[Exception] = None, **meta) -> "ToolResult":
        return cls(status=ToolStatus.FAILED, message=message, error=error, meta=meta)

    @classmethod
    def skip(cls, reason: str = "") -> "ToolResult":
        return cls(status=ToolStatus.SKIPPED, message=reason)

    @classmethod
    def partial(cls, data: Any, message: str = "", **meta) -> "ToolResult":
        return cls(status=ToolStatus.PARTIAL, data=data, message=message, meta=meta)

    # ── 判断 ──────────────────────────────
    @property
    def ok(self) -> bool:            # type: ignore[override]
        return self.status in (ToolStatus.SUCCESS, ToolStatus.PARTIAL)

    def __bool__(self):
        return self.ok


@dataclass
class ToolParam:
    """工具参数定义"""
    name:        str
    type:        Type
    description: str       = ""
    required:    bool      = True
    default:     Any       = None
    choices:     Optional[List[Any]] = None   # 枚举可选值


@dataclass
class ToolMeta:
    """工具元数据（注册表中存储的信息）"""
    name:        str
    description: str
    category:    str              = "general"
    version:     str              = "1.0.0"
    author:      str              = ""
    params:      List[ToolParam]  = field(default_factory=list)
    tags:        List[str]        = field(default_factory=list)
    requires_network: bool        = False
    requires_config:  List[str]   = field(default_factory=list)  # 必须的配置 key

    def to_dict(self) -> Dict:
        return {
            "name":        self.name,
            "description": self.description,
            "category":    self.category,
            "version":     self.version,
            "author":      self.author,
            "tags":        self.tags,
            "requires_network": self.requires_network,
            "requires_config":  self.requires_config,
            "params": [
                {
                    "name":        p.name,
                    "type":        p.type.__name__,
                    "description": p.description,
                    "required":    p.required,
                    "default":     p.default,
                    "choices":     p.choices,
                }
                for p in self.params
            ],
        }


# ──────────────────────────────────────────
# 基类
# ──────────────────────────────────────────

class BaseTool:
    """
    工具基类
    
    继承此类并实现 execute() 方法即可注册为 Jarvis 工具。

    示例::

        class WeatherTool(BaseTool):
            name        = "weather"
            description = "获取当前天气"
            category    = "info"

            params = [
                ToolParam("city", str, "城市名称"),
            ]

            def execute(self, city: str) -> ToolResult:
                ...
                return ToolResult.ok(data=weather_data)
    """

    # ── 子类需定义的属性 ──────────────────
    name:        str  = ""
    description: str  = ""
    category:    str  = "general"
    version:     str  = "1.0.0"
    author:      str  = ""
    tags:        List[str]       = []
    params:      List[ToolParam] = []
    requires_network: bool       = False
    requires_config:  List[str]  = []

    def execute(self, **kwargs) -> ToolResult:
        """工具执行逻辑 — 子类必须实现"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 execute()")

    # ── 自动生成元数据 ────────────────────
    @classmethod
    def get_meta(cls) -> ToolMeta:
        return ToolMeta(
            name        = cls.name,
            description = cls.description,
            category    = cls.category,
            version     = cls.version,
            author      = cls.author,
            params      = cls.params,
            tags        = cls.tags,
            requires_network = cls.requires_network,
            requires_config  = cls.requires_config,
        )

    # ── 参数验证 ──────────────────────────
    def validate_params(self, kwargs: Dict) -> Optional[str]:
        """验证参数，返回错误信息（None = 通过）"""
        for p in self.params:
            if p.required and p.name not in kwargs:
                return f"缺少必填参数: {p.name}"
            if p.name in kwargs and p.choices:
                if kwargs[p.name] not in p.choices:
                    return f"参数 {p.name} 必须是 {p.choices} 之一"
        return None

    # ── 带计时和异常捕获的调用入口 ─────────
    def __call__(self, **kwargs) -> ToolResult:
        # 填充默认值
        for p in self.params:
            if p.name not in kwargs and p.default is not None:
                kwargs[p.name] = p.default

        # 参数验证
        err = self.validate_params(kwargs)
        if err:
            return ToolResult.fail(err)

        t0 = time.perf_counter()
        try:
            result = self.execute(**kwargs)
            if not isinstance(result, ToolResult):
                # 允许子类直接 return 值
                result = ToolResult.ok(data=result)
        except Exception as exc:
            result = ToolResult.fail(
                message=f"工具 {self.name} 执行异常: {exc}",
                error=exc
            )
        finally:
            elapsed = time.perf_counter() - t0
            if isinstance(result, ToolResult):
                result.elapsed = elapsed

        return result

    def __repr__(self):
        return f"<Tool: {self.name} ({self.category})>"


# ──────────────────────────────────────────
# @tool 装饰器 — 函数式快速定义
# ──────────────────────────────────────────

def tool(
    name:        Optional[str] = None,
    description: str           = "",
    category:    str           = "general",
    version:     str           = "1.0.0",
    tags:        Optional[List[str]] = None,
    requires_network: bool     = False,
    requires_config:  Optional[List[str]] = None,
):
    """
    将普通函数包装为 BaseTool 子类。

    用法::

        @tool(name="search_web", description="搜索互联网", category="network",
              requires_network=True)
        def search_web_tool(query: str, max_results: int = 10) -> ToolResult:
            ...
    """
    def decorator(fn: Callable) -> Type[BaseTool]:
        # 从函数签名自动提取参数定义
        sig = inspect.signature(fn)
        tool_params: List[ToolParam] = []
        hints = fn.__annotations__

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            ptype = hints.get(param_name, Any)
            if ptype is Any:
                ptype = str
            has_default = param.default is not inspect.Parameter.empty
            tool_params.append(ToolParam(
                name        = param_name,
                type        = ptype,
                description = "",
                required    = not has_default,
                default     = param.default if has_default else None,
            ))

        # 动态创建 BaseTool 子类
        klass = type(
            fn.__name__,
            (BaseTool,),
            {
                "name":             name or fn.__name__,
                "description":      description or (fn.__doc__ or "").strip(),
                "category":         category,
                "version":          version,
                "tags":             tags or [],
                "params":           tool_params,
                "requires_network": requires_network,
                "requires_config":  requires_config or [],
                "execute":          lambda self, **kwargs: fn(**kwargs),
            }
        )
        return klass

    return decorator
