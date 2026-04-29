"""
工具自动发现与加载器
扫描指定目录，自动发现并注册 BaseTool 子类
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from .base import BaseTool
from .registry import ToolRegistry

if TYPE_CHECKING:
    pass


def discover_tools(
    search_paths: List[str],
    registry: Optional[ToolRegistry] = None,
    verbose: bool = False,
) -> ToolRegistry:
    """
    自动扫描目录，发现并注册所有 BaseTool 子类。

    Args:
        search_paths: 要扫描的目录路径列表
        registry:     目标注册表（默认使用全局单例）
        verbose:      是否打印发现过程

    Returns:
        填充好工具的注册表
    """
    if registry is None:
        registry = ToolRegistry()

    for path_str in search_paths:
        path = Path(path_str)
        if not path.exists():
            if verbose:
                print(f"[ToolLoader] 路径不存在，跳过: {path_str}")
            continue

        # 递归扫描所有 .py 文件
        py_files = list(path.rglob("*.py"))
        for py_file in py_files:
            if py_file.name.startswith("_"):
                continue   # 跳过 __init__.py 等

            _load_tools_from_file(py_file, registry, verbose)

    return registry


def _load_tools_from_file(
    py_file: Path,
    registry: ToolRegistry,
    verbose: bool = False,
) -> int:
    """从单个 .py 文件加载工具，返回加载数量"""
    module_name = f"_jarvis_autoload.{py_file.stem}_{id(py_file)}"
    count = 0

    try:
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            return 0

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        # 找出所有 BaseTool 子类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                inspect.isclass(attr)
                and issubclass(attr, BaseTool)
                and attr is not BaseTool
                and attr.name  # 必须有 name
                and not registry.has(attr.name)   # 避免重复注册
            ):
                try:
                    registry.register(attr)
                    count += 1
                    if verbose:
                        print(f"[ToolLoader] ✓ 注册: {attr.name} ({py_file.name})")
                except Exception as e:
                    if verbose:
                        print(f"[ToolLoader] ✗ 注册失败 {attr.name}: {e}")

    except Exception as e:
        if verbose:
            print(f"[ToolLoader] ✗ 加载文件失败 {py_file}: {e}")

    return count


def load_builtin_tools(registry: Optional[ToolRegistry] = None) -> ToolRegistry:
    """
    加载 Jarvis 内置工具集

    内置工具位于 jarvis/tools/builtin/ 目录
    """
    if registry is None:
        registry = ToolRegistry()

    builtin_path = Path(__file__).parent / "builtin"
    if builtin_path.exists():
        discover_tools([str(builtin_path)], registry, verbose=False)

    return registry
