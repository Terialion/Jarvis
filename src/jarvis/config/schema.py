"""
配置Schema定义 - 类型安全、验证、默认值
"""
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, List, Dict, Union
from enum import Enum
import os


class FieldType(Enum):
    """字段类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    SECRET = "secret"  # 敏感信息，会加密存储


@dataclass
class Field:
    """配置字段定义"""
    name: str
    field_type: FieldType
    default: Any = None
    env_var: Optional[str] = None
    description: str = ""
    required: bool = False
    validator: Optional[Callable[[Any], bool]] = None
    
    def get_value(self) -> Any:
        """获取字段值，优先级：环境变量 > 默认值"""
        # 1. 检查环境变量
        if self.env_var and self.env_var in os.environ:
            raw_value = os.environ[self.env_var]
            return self._convert_type(raw_value)
        
        # 2. 返回默认值
        return self.default
    
    def _convert_type(self, value: str) -> Any:
        """将字符串转换为字段类型"""
        if self.field_type == FieldType.STRING:
            return value
        elif self.field_type == FieldType.INTEGER:
            return int(value)
        elif self.field_type == FieldType.FLOAT:
            return float(value)
        elif self.field_type == FieldType.BOOLEAN:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif self.field_type == FieldType.LIST:
            return value.split(',') if value else []
        elif self.field_type in (FieldType.DICT, FieldType.SECRET):
            return value
        return value
    
    def validate(self, value: Any) -> bool:
        """验证值是否有效"""
        if self.required and value is None:
            return False
        if self.validator:
            return self.validator(value)
        return True


class ConfigSchema:
    """配置Schema基类"""
    
    def __init__(self):
        self._fields: Dict[str, Field] = {}
        self._setup_fields()
    
    def _setup_fields(self):
        """子类重写此方法定义字段"""
        pass
    
    def add_field(self, field: Field):
        """添加字段"""
        self._fields[field.name] = field
    
    def get_field(self, name: str) -> Optional[Field]:
        """获取字段定义"""
        return self._fields.get(name)
    
    def get_all_fields(self) -> Dict[str, Field]:
        """获取所有字段"""
        return self._fields.copy()
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []
        for name, field in self._fields.items():
            value = config.get(name)
            if not field.validate(value):
                errors.append(f"字段 '{name}' 验证失败: {field.description}")
        return errors


# ============================================
# 预定义的配置Schema
# ============================================

class SearchConfigSchema(ConfigSchema):
    """搜索配置Schema"""
    
    def _setup_fields(self):
        self.add_field(Field(
            name="brave_api_key",
            field_type=FieldType.SECRET,
            env_var="BRAVE_API_KEY",
            description="Brave Search API密钥 (免费 2000次/月)",
            required=False
        ))
        self.add_field(Field(
            name="tavily_api_key",
            field_type=FieldType.SECRET,
            env_var="TAVILY_API_KEY",
            description="Tavily API密钥",
            required=False
        ))
        self.add_field(Field(
            name="scrape_do_api_key",
            field_type=FieldType.SECRET,
            env_var="SCRAPE_DO_API_KEY",
            description="scrape.do API密钥",
            required=False
        ))
        self.add_field(Field(
            name="bing_api_key",
            field_type=FieldType.SECRET,
            env_var="BING_SEARCH_API_KEY",
            description="Bing Search API密钥",
            required=False
        ))
        self.add_field(Field(
            name="serper_api_key",
            field_type=FieldType.SECRET,
            env_var="SERPER_API_KEY",
            description="Serper API密钥",
            required=False
        ))
        self.add_field(Field(
            name="prefer_api",
            field_type=FieldType.STRING,
            default="auto",
            env_var="SEARCH_PREFER_API",
            description="优先使用的API (auto/tavily/bing/serper/searxng/ddgs/none)",
            required=False
        ))
        self.add_field(Field(
            name="max_results",
            field_type=FieldType.INTEGER,
            default=10,
            env_var="SEARCH_MAX_RESULTS",
            description="最大搜索结果数",
            required=False
        ))
        self.add_field(Field(
            name="fetch_content_top_k",
            field_type=FieldType.INTEGER,
            default=3,
            env_var="SEARCH_FETCH_TOP_K",
            description="抓取正文的Top-K结果数",
            required=False
        ))
        self.add_field(Field(
            name="enable_ai_summary",
            field_type=FieldType.BOOLEAN,
            default=True,
            env_var="SEARCH_ENABLE_AI_SUMMARY",
            description="是否启用AI摘要",
            required=False
        ))


class LLMConfigSchema(ConfigSchema):
    """LLM configuration schema using canonical JARVIS_LLM_* env vars."""

    def _setup_fields(self):
        self.add_field(Field(
            name="provider",
            field_type=FieldType.STRING,
            default="deepseek",
            env_var="JARVIS_LLM_PROVIDER",
            description="LLM provider (deepseek, openai, openrouter, gemini, minimax, ollama, qwen, custom)",
            required=False,
        ))
        self.add_field(Field(
            name="model",
            field_type=FieldType.STRING,
            default="deepseek-v4-pro",
            env_var="JARVIS_LLM_MODEL",
            description="Model name (e.g. deepseek-v4-pro, deepseek-v4-flash, gpt-4.1-mini)",
            required=False,
        ))
        self.add_field(Field(
            name="base_url",
            field_type=FieldType.STRING,
            default="",
            env_var="JARVIS_LLM_BASE_URL",
            description="API base URL (provider default used when empty)",
            required=False,
        ))
        self.add_field(Field(
            name="api_key",
            field_type=FieldType.SECRET,
            env_var="JARVIS_LLM_API_KEY",
            description="API key for the configured provider",
            required=True,
        ))
        self.add_field(Field(
            name="temperature",
            field_type=FieldType.FLOAT,
            default=0.2,
            env_var="JARVIS_LLM_TEMPERATURE",
            description="Generation temperature (0.0–2.0)",
            required=False,
        ))
        self.add_field(Field(
            name="timeout_seconds",
            field_type=FieldType.FLOAT,
            default=60.0,
            env_var="JARVIS_LLM_TIMEOUT_SECONDS",
            description="API request timeout in seconds",
            required=False,
        ))
        self.add_field(Field(
            name="max_tokens",
            field_type=FieldType.INTEGER,
            default=16384,
            env_var="JARVIS_LLM_MAX_TOKENS",
            description="Maximum output tokens per request",
            required=False,
        ))


class VoiceConfigSchema(ConfigSchema):
    """语音配置Schema"""
    
    def _setup_fields(self):
        self.add_field(Field(
            name="voice_enabled",
            field_type=FieldType.BOOLEAN,
            default=True,
            env_var="VOICE_ENABLED",
            description="是否启用语音",
            required=False
        ))
        self.add_field(Field(
            name="voice_model_path",
            field_type=FieldType.STRING,
            default="models/ChatTTS",
            env_var="VOICE_MODEL_PATH",
            description="语音模型路径",
            required=False
        ))
        self.add_field(Field(
            name="whisper_model",
            field_type=FieldType.STRING,
            default="base",
            env_var="WHISPER_MODEL",
            description="Whisper模型大小 (tiny/base/small/medium/large)",
            required=False
        ))


class MemoryConfigSchema(ConfigSchema):
    """记忆配置Schema"""
    
    def _setup_fields(self):
        self.add_field(Field(
            name="chroma_db_path",
            field_type=FieldType.STRING,
            default="data/chroma_db",
            env_var="CHROMA_DB_PATH",
            description="ChromaDB存储路径",
            required=False
        ))
        self.add_field(Field(
            name="embedding_model",
            field_type=FieldType.STRING,
            default="models/chroma_onnx",
            env_var="EMBEDDING_MODEL_PATH",
            description="嵌入模型路径",
            required=False
        ))
        self.add_field(Field(
            name="max_history",
            field_type=FieldType.INTEGER,
            default=20,
            env_var="MEMORY_MAX_HISTORY",
            description="最大历史对话轮数",
            required=False
        ))
