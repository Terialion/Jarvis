"""
Jarvis  ??
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


class Jarvis:
    """
    Jarvis ?
    
    ?
     bootstrap() ?
    """

    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir).resolve()
        self.config   = None
        self.logger   = None
        self.registry = None

    def _init_config(self):
        from jarvis.config.manager import init_config
        config_dir = self.root_dir / "config"
        self.config = init_config(str(config_dir))
        return self

    def _init_logger(self):
        try:
            from jarvis.logger.core import init_logger, LogLevel, ConsoleHandler
            from jarvis.logger.formatters import ConsoleFormatter

            log_dir = self.root_dir / "logs"
            logger = init_logger(
                log_dir=str(log_dir),
                console_level=LogLevel.INFO,
                file_level=LogLevel.DEBUG,
                json_format=False,
            )
            for h in logger.handlers:
                if isinstance(h, ConsoleHandler):
                    h.formatter = ConsoleFormatter(use_color=True, show_trace=False)
            self.logger = logger
        except BaseException:
            class _NoopLogger:
                handlers = []

                def info(self, *args, **kwargs):
                    return None

                def warning(self, *args, **kwargs):
                    return None

                def error(self, *args, **kwargs):
                    return None

            self.logger = _NoopLogger()
        return self

    def _init_registry(self):
        from jarvis.tools.registry import ToolRegistry
        from jarvis.tools.loader import load_builtin_tools, discover_tools

        registry = ToolRegistry()

        # 
        load_builtin_tools(registry)

        #  skills 
        skills_dir = self.root_dir / "skills"
        if skills_dir.exists():
            discover_tools([str(skills_dir)], registry, verbose=False)

        self.registry = registry
        return self

    def _inject_api_keys_to_env(self):
        """?"""
        if self.config is None:
            return
        key_map = {
            "search.tavily_api_key":    "TAVILY_API_KEY",
            "search.scrape_do_api_key": "SCRAPE_DO_API_KEY",
            "search.bing_api_key":      "BING_SEARCH_API_KEY",
            "search.serper_api_key":    "SERPER_API_KEY",
            "llm.deepseek_api_key":     "DEEPSEEK_API_KEY",
        }
        for cfg_key, env_key in key_map.items():
            if not os.environ.get(env_key):
                value = self.config.get_secret(cfg_key)
                if value:
                    os.environ[env_key] = value

    def info(self):
        """?"""
        if self.logger:
            n_tools = len(self.registry) if self.registry else 0
            self.logger.info(
                f"Jarvis  | : {n_tools} ?| ? {self.root_dir}",
                component="bootstrap",
            )
            if self.registry:
                cats = self.registry.categories()
                for cat in cats:
                    tools = self.registry.list_tools(category=cat)
                    names = ", ".join(t.name for t in tools)
                    self.logger.info(f"  [{cat}] {names}", component="bootstrap")


_instance: Optional[Jarvis] = None


def bootstrap(root_dir: Optional[str] = None) -> Jarvis:
    """
     Jarvis ?
    
    ?
    
    Args:
        root_dir: ?
    """
    global _instance
    if _instance is not None:
        return _instance

    # ?
    if root_dir is None:
        # ?main.py ?
        candidate = Path(__file__).resolve().parent.parent  # d:/jarvis
        root_dir = str(candidate)

    j = Jarvis(root_dir)
    j._init_config()
    j._init_logger()
    j._init_registry()
    j._inject_api_keys_to_env()
    j.info()

    _instance = j
    return j


def get_instance() -> Optional[Jarvis]:
    """?Jarvis  None?"""
    return _instance

