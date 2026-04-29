"""
Jarvis 核心包 — Phase 1 基础设施统一入口

使用方法:
    from jarvis import bootstrap, get_config, get_logger, get_registry

    jarvis = bootstrap()              # 一键初始化所有基础设施
    cfg    = jarvis.config            # 配置管理器
    log    = jarvis.logger            # 日志器
    tools  = jarvis.registry          # 工具注册表
"""
from .runtime_bootstrap import Jarvis, bootstrap

__all__ = ["Jarvis", "bootstrap"]
