"""
配置管理器 - 统一入口，支持多环境、热更新
"""
import os
import json
from pathlib import Path
from typing import Any, Optional, Dict, Type, Callable
from dataclasses import dataclass, asdict
from threading import Lock
import time

from .schema import ConfigSchema, Field, FieldType
from .vault import SecretVault


@dataclass
class ConfigChangeEvent:
    """配置变更事件"""
    key: str
    old_value: Any
    new_value: Any
    source: str  # 'env', 'file', 'vault', 'code'


class ConfigManager:
    """
    统一配置管理器
    
    特性：
    - 多源优先级：环境变量 > 配置文件 > 加密保险箱 > 代码默认值
    - 热更新支持（配置文件变更自动加载）
    - 变更监听回调
    - 类型安全
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls, config_dir: Optional[str] = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config_dir: Optional[str] = None):
        if self._initialized:
            return
        
        # 配置目录
        self._config_dir = Path(config_dir) if config_dir else Path("config")
        self._config_dir.mkdir(parents=True, exist_ok=True)
        
        # 子配置文件
        self._config_file = self._config_dir / "jarvis.json"
        
        # Schema注册表
        self._schemas: Dict[str, ConfigSchema] = {}
        
        # 配置值缓存
        self._values: Dict[str, Any] = {}
        
        # 加密保险箱
        self._vault = SecretVault()
        
        # 变更监听器
        self._listeners: list[Callable[[ConfigChangeEvent], None]] = []
        
        # 热更新
        self._last_modified = 0
        self._auto_reload = True
        
        self._initialized = True
        
        # 初始加载
        self._load_all()
    
    def register_schema(self, name: str, schema: ConfigSchema):
        """注册配置Schema"""
        self._schemas[name] = schema
        self._load_schema_values(name, schema)
    
    def _load_all(self):
        """加载所有配置"""
        # 加载配置文件
        self._load_config_file()
        
        # 加载已注册的schema
        for name, schema in self._schemas.items():
            self._load_schema_values(name, schema)
    
    def _load_config_file(self):
        """加载配置文件"""
        if not self._config_file.exists():
            return
        
        try:
            with open(self._config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._last_modified = self._config_file.stat().st_mtime
            
            # 合并到values
            for key, value in data.items():
                if key not in self._values:
                    self._values[key] = value
                    
        except Exception as e:
            print(f"[Config] 加载配置文件失败: {e}")
    
    def _load_schema_values(self, name: str, schema: ConfigSchema):
        """从Schema加载配置值"""
        for field_name, field in schema.get_all_fields().items():
            full_key = f"{name}.{field_name}"
            
            # 优先级：环境变量 > 配置文件 > 保险箱 > 默认值
            value = None
            source = "default"
            
            # 1. 环境变量
            if field.env_var and field.env_var in os.environ:
                value = field.get_value()
                source = "env"
            
            # 2. 配置文件
            elif full_key in self._values:
                value = self._values[full_key]
                source = "file"
            
            # 3. 加密保险箱（仅SECRET类型）
            elif field.field_type == FieldType.SECRET:
                vault_value = self._vault.get(full_key)
                if vault_value:
                    value = vault_value
                    source = "vault"
            
            # 4. 默认值
            else:
                value = field.default
            
            # 验证
            if not field.validate(value):
                print(f"[Config] 警告: {full_key} 验证失败，使用默认值")
                value = field.default
            
            # 存储
            old_value = self._values.get(full_key)
            self._values[full_key] = value
            
            # 触发变更事件
            if old_value != value:
                self._notify_change(ConfigChangeEvent(full_key, old_value, value, source))
    
    def _notify_change(self, event: ConfigChangeEvent):
        """通知监听器"""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"[Config] 监听器错误: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        支持格式：
        - "search.tavily_api_key" - 获取search schema下的字段
        - "tavily_api_key" - 直接获取（向后兼容）
        """
        # 检查热更新
        if self._auto_reload:
            self._check_reload()
        
        # 尝试直接获取
        if key in self._values:
            return self._values[key]
        
        # 尝试schema格式
        if "." in key:
            parts = key.split(".")
            if len(parts) == 2:
                schema_name, field_name = parts
                if schema_name in self._schemas:
                    schema = self._schemas[schema_name]
                    field = schema.get_field(field_name)
                    if field:
                        return field.get_value()
        
        return default
    
    def get_secret(self, key: str) -> Optional[str]:
        """获取敏感信息（自动从保险箱解密）"""
        # 先尝试普通获取
        value = self.get(key)
        if value:
            return value
        
        # 从保险箱获取
        return self._vault.get(key)
    
    def set(self, key: str, value: Any, persist: bool = False, encrypt: bool = False):
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
            persist: 是否持久化到配置文件
            encrypt: 是否加密存储到保险箱
        """
        old_value = self._values.get(key)
        self._values[key] = value
        
        # 持久化
        if encrypt:
            self._vault.set(key, str(value))
        elif persist:
            self._persist_to_file()
        
        # 通知
        source = "vault" if encrypt else ("file" if persist else "code")
        self._notify_change(ConfigChangeEvent(key, old_value, value, source))
    
    def _persist_to_file(self):
        """持久化到配置文件"""
        try:
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(self._values, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Config] 保存配置文件失败: {e}")
    
    def _check_reload(self):
        """检查配置文件是否需要重新加载"""
        if not self._config_file.exists():
            return
        
        try:
            mtime = self._config_file.stat().st_mtime
            if mtime > self._last_modified:
                print("[Config] 配置文件变更，重新加载...")
                self._load_config_file()
                self._load_all()
        except Exception:
            pass
    
    def add_listener(self, callback: Callable[[ConfigChangeEvent], None]):
        """添加配置变更监听器"""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[ConfigChangeEvent], None]):
        """移除配置变更监听器"""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置值（调试用）"""
        return self._values.copy()
    
    def get_schema_names(self) -> list:
        """获取所有注册的schema名称"""
        return list(self._schemas.keys())
    
    def get_schema_info(self, name: str) -> Optional[Dict]:
        """获取Schema信息"""
        if name not in self._schemas:
            return None
        
        schema = self._schemas[name]
        fields = {}
        for field_name, field in schema.get_all_fields().items():
            full_key = f"{name}.{field_name}"
            fields[field_name] = {
                "type": field.field_type.value,
                "description": field.description,
                "required": field.required,
                "env_var": field.env_var,
                "current_value": "***" if field.field_type == FieldType.SECRET else self._values.get(full_key, field.default)
            }
        
        return {"name": name, "fields": fields}
    
    def setup_wizard(self):
        """交互式配置向导"""
        print("\n" + "="*50)
        print("Jarvis 配置向导")
        print("="*50)
        
        for name, schema in self._schemas.items():
            print(f"\n【{name} 配置】")
            for field_name, field in schema.get_all_fields().items():
                full_key = f"{name}.{field_name}"
                current = self.get(full_key)
                
                # 敏感信息不显示值
                display_current = "***" if field.field_type == FieldType.SECRET and current else current
                
                print(f"\n{field.description}")
                print(f"  当前值: {display_current or '(未设置)'}")
                
                if field.env_var:
                    env_set = "✓" if field.env_var in os.environ else "✗"
                    print(f"  环境变量 {field.env_var}: {env_set}")
                
                # 询问是否修改
                if field.field_type == FieldType.SECRET:
                    new_value = input(f"  输入新值 (直接回车保持当前): ").strip()
                    if new_value:
                        self.set(full_key, new_value, encrypt=True)
                        print(f"  ✓ 已加密保存")
                else:
                    new_value = input(f"  输入新值 (直接回车保持当前): ").strip()
                    if new_value:
                        self.set(full_key, new_value, persist=True)
                        print(f"  ✓ 已保存")
        
        print("\n" + "="*50)
        print("配置完成！")
        print("="*50)


# 全局实例
_config_manager: Optional[ConfigManager] = None


def mask_secret(value: Optional[str]) -> str:
    """Mask secret value for logs/tests without exposing raw content."""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"


def _load_env_file(env_path: Path) -> None:
    """Load simple KEY=VALUE pairs from .env into process env without override."""
    if not env_path.exists():
        return
    try:
        with env_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    continue
                if value and ((value[0] == value[-1]) and value[0] in ("'", '"')):
                    value = value[1:-1]
                # process environment has higher priority than .env
                os.environ.setdefault(key, value)
    except Exception:
        # Keep config bootstrap resilient; missing/corrupt .env should not crash CLI.
        return


def _apply_llm_env_aliases() -> None:
    """Map compatible env names into canonical LLM env names."""
    canonical = "DEEPSEEK_API_KEY"
    if os.environ.get(canonical):
        return
    for alias in ("LLM_DEEPSEEK_API_KEY", "JARVIS_LLM_DEEPSEEK_API_KEY"):
        alias_value = os.environ.get(alias)
        if alias_value:
            os.environ[canonical] = alias_value
            return


def bootstrap_env(config_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Load project .env and apply env compatibility aliases.
    Priority: process env > .env > local config file > defaults.
    """
    project_root = Path(config_dir).resolve().parent if config_dir else Path.cwd().resolve()
    env_path = project_root / ".env"
    _load_env_file(env_path)
    _apply_llm_env_aliases()
    return {
        "env_path": str(env_path),
        "env_exists": env_path.exists(),
        "supported_aliases": [
            "DEEPSEEK_API_KEY",
            "LLM_DEEPSEEK_API_KEY",
            "JARVIS_LLM_DEEPSEEK_API_KEY",
        ],
    }

def get_config(config_dir: Optional[str] = None) -> ConfigManager:
    """获取配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_dir)
    return _config_manager


def init_config(config_dir: Optional[str] = None) -> ConfigManager:
    """
    初始化配置系统
    
    注册所有默认Schema并加载配置
    """
    from .schema import SearchConfigSchema, LLMConfigSchema, VoiceConfigSchema, MemoryConfigSchema

    # Ensure project .env and env aliases are available before schema env resolution.
    bootstrap_env(config_dir)
    
    manager = get_config(config_dir)
    
    # 注册默认schemas
    manager.register_schema("search", SearchConfigSchema())
    manager.register_schema("llm", LLMConfigSchema())
    manager.register_schema("voice", VoiceConfigSchema())
    manager.register_schema("memory", MemoryConfigSchema())
    
    return manager


def _reset_for_tests() -> None:
    """Reset config singletons for isolated tests."""
    global _config_manager
    _config_manager = None
    ConfigManager._instance = None
