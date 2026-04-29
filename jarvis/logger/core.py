"""
 - 
"""
import json
import sys
import traceback
from enum import Enum
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Callable
from threading import Lock
import uuid

def _safe_stream_write(message: str, prefer_stderr: bool = False) -> None:
    """Best-effort write to std streams that never raises."""
    if not isinstance(message, str):
        message = str(message)
    streams = [getattr(sys, 'stderr', None), getattr(sys, '__stderr__', None), getattr(sys, '__stdout__', None)] if prefer_stderr else [getattr(sys, 'stdout', None), getattr(sys, '__stdout__', None), getattr(sys, '__stderr__', None)]
    foreach_stream = streams
    for stream in foreach_stream:
        if stream is None:
            continue
        try:
            if getattr(stream, 'closed', False):
                continue
            stream.write(message + '\n')
            stream.flush()
            return
        except Exception:
            continue


class LogLevel(Enum):
    """"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    
    def __lt__(self, other):
        order = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
        return order.index(self) < order.index(other)
    
    def __le__(self, other):
        return self == other or self < other


class LogEntry:
    """"""
    
    def __init__(
        self,
        level: LogLevel,
        message: str,
        component: str = "",
        trace_id: str = "",
        context: Optional[Dict] = None,
        exception: Optional[Exception] = None
    ):
        self.timestamp = datetime.now()
        self.level = level
        self.message = message
        self.component = component
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self.context = context or {}
        self.exception = exception
    
    def to_dict(self) -> Dict:
        """JSON?"""
        data = {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "message": self.message,
            "component": self.component,
            "trace_id": self.trace_id,
        }
        
        if self.context:
            data["context"] = self.context
        
        if self.exception:
            data["exception"] = {
                "type": type(self.exception).__name__,
                "message": str(self.exception),
                "traceback": traceback.format_exception(
                    type(self.exception),
                    self.exception,
                    self.exception.__traceback__
                ) if self.exception.__traceback__ else None
            }
        
        return data
    
    def to_json(self) -> str:
        """Convert log entry to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    def to_console(self, use_color: bool = True) -> str:
        """"""
        colors = {
            LogLevel.DEBUG: "\033[36m",      # Cyan
            LogLevel.INFO: "\033[32m",       # Green
            LogLevel.WARNING: "\033[33m",    # Yellow
            LogLevel.ERROR: "\033[31m",      # Red
            LogLevel.CRITICAL: "\033[35m",   # Magenta
        }
        reset = "\033[0m"
        
        level_str = f"[{self.level.value:8}]"
        time_str = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        
        if use_color and self.level in colors:
            level_str = f"{colors[self.level]}{level_str}{reset}"
        
        parts = [f"{time_str} {level_str}"]
        
        if self.component:
            parts.append(f"[{self.component}]")
        
        parts.append(self.message)
        
        if self.trace_id:
            parts.append(f"(trace:{self.trace_id})")
        
        return " ".join(parts)


class LogHandler:
    """?"""
    
    def __init__(self, level: LogLevel = LogLevel.DEBUG):
        self.level = level
        self.formatter: Optional[Callable[[LogEntry], str]] = None
    
    def handle(self, entry: LogEntry):
        """"""
        if entry.level < self.level:
            return
        
        formatted = self.formatter(entry) if self.formatter else entry.to_console()
        self.emit(formatted, entry)
    
    def emit(self, formatted: str, entry: LogEntry):
        """"""
        raise NotImplementedError
    
    def close(self):
        """?"""
        pass


class ConsoleHandler(LogHandler):
    """"""
    
    def __init__(self, level: LogLevel = LogLevel.DEBUG, use_color: bool = True):
        super().__init__(level)
        self.use_color = use_color
        self._lock = Lock()
    
    def emit(self, formatted: str, entry: LogEntry):
        with self._lock:
            rendered = self.formatter(entry) if self.formatter else entry.to_console(self.use_color)
            _safe_stream_write(rendered, prefer_stderr=False)
            if entry.exception:
                tb_lines = traceback.format_exception(
                    type(entry.exception),
                    entry.exception,
                    entry.exception.__traceback__,
                )
                for line in tb_lines:
                    _safe_stream_write(line.rstrip("\n"), prefer_stderr=True)


class FileHandler(LogHandler):
    """"""
    
    def __init__(self, filepath: str, level: LogLevel = LogLevel.DEBUG):
        super().__init__(level)
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._file = None
        self._lock = Lock()
    
    def _get_file(self):
        if self._file is None:
            self._file = open(self.filepath, 'a', encoding='utf-8')
        return self._file
    
    def emit(self, formatted: str, entry: LogEntry):
        with self._lock:
            f = self._get_file()
            f.write(formatted + '\n')
            f.flush()
    
    def close(self):
        if self._file:
            self._file.close()
            self._file = None


class RotatingFileHandler(FileHandler):
    """?"""
    
    def __init__(
        self,
        filepath: str,
        level: LogLevel = LogLevel.DEBUG,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5
    ):
        super().__init__(filepath, level)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
    
    def emit(self, formatted: str, entry: LogEntry):
        with self._lock:
            # ?
            if self.filepath.exists() and self.filepath.stat().st_size > self.max_bytes:
                self._rotate()
            
            super().emit(formatted, entry)
    
    def _rotate(self):
        """"""
        self.close()
        
        # 
        oldest = self.filepath.with_suffix(f'.{self.backup_count}.log')
        if oldest.exists():
            oldest.unlink()
        
        # 
        for i in range(self.backup_count - 1, 0, -1):
            src = self.filepath.with_suffix(f'.{i}.log')
            dst = self.filepath.with_suffix(f'.{i+1}.log')
            if src.exists():
                src.rename(dst)
        
        # 
        self.filepath.rename(self.filepath.with_suffix('.1.log'))


class JarvisLogger:
    """
    Jarvis 
    
    
    - SON
    - (trace_id)
    - ?
    - 
    """
    
    def __init__(self, name: str = "jarvis"):
        self.name = name
        self.handlers: List[LogHandler] = []
        self.context: Dict[str, Any] = {}
        self._lock = Lock()
    
    def add_handler(self, handler: LogHandler):
        """?"""
        self.handlers.append(handler)
    
    def remove_handler(self, handler: LogHandler):
        """?"""
        if handler in self.handlers:
            self.handlers.remove(handler)
    
    def set_context(self, **kwargs):
        """"""
        self.context.update(kwargs)
    
    def clear_context(self):
        """?"""
        self.context.clear()
    
    def _log(
        self,
        level: LogLevel,
        message: str,
        component: str = "",
        trace_id: str = "",
        context: Optional[Dict] = None,
        exception: Optional[Exception] = None
    ):
        """"""
        # ?
        merged_context = {**self.context, **(context or {})}
        
        entry = LogEntry(
            level=level,
            message=message,
            component=component or self.name,
            trace_id=trace_id,
            context=merged_context,
            exception=exception
        )
        
        with self._lock:
            for handler in self.handlers:
                try:
                    handler.handle(entry)
                except Exception as e:
                    _safe_stream_write(f"[Logger Error] handler failure: {e}", prefer_stderr=True)
    # 
    def debug(self, message: str, **kwargs):
        self._log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(LogLevel.WARNING, message, **kwargs)
    
    def error(self, message: str, exception: Optional[Exception] = None, **kwargs):
        self._log(LogLevel.ERROR, message, exception=exception, **kwargs)
    
    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs):
        self._log(LogLevel.CRITICAL, message, exception=exception, **kwargs)
    
    # 
    def span(self, name: str, **context):
        """"""
        return LogSpan(self, name, **context)
    
    def close(self):
        """"""
        for handler in self.handlers:
            handler.close()


class LogSpan:
    """"""
    
    def __init__(self, logger: JarvisLogger, name: str, **context):
        self.logger = logger
        self.name = name
        self.context = context
        self.trace_id = str(uuid.uuid4())[:8]
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info(f"[span-start] {self.name}", trace_id=self.trace_id, **self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_val:
            self.logger.error(
                f"?{self.name}  ({duration:.2f}s)",
                exception=exc_val,
                trace_id=self.trace_id
            )
        else:
            self.logger.info(
                f"?{self.name}  ({duration:.2f}s)",
                trace_id=self.trace_id
            )


# ?
_default_logger: Optional[JarvisLogger] = None

def get_logger(name: str = "jarvis") -> JarvisLogger:
    """?"""
    global _default_logger
    if _default_logger is None:
        _default_logger = JarvisLogger(name)
        # 
        _default_logger.add_handler(ConsoleHandler())
    return _default_logger


def init_logger(
    log_dir: str = "logs",
    console_level: LogLevel = LogLevel.INFO,
    file_level: LogLevel = LogLevel.DEBUG,
    json_format: bool = False
) -> JarvisLogger:
    """
    ?
    
    Args:
        log_dir: 
        console_level: ?
        file_level: 
        json_format: JSON?
    """
    global _default_logger
    
    logger = JarvisLogger("jarvis")
    
    # 
    console = ConsoleHandler(level=console_level)
    logger.add_handler(console)
    
    # ?
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # ?
    main_file = RotatingFileHandler(
        str(log_path / "jarvis.log"),
        level=file_level,
        max_bytes=10*1024*1024,
        backup_count=5
    )
    if json_format:
        main_file.formatter = lambda e: e.to_json()
    logger.add_handler(main_file)
    
    # RROR
    error_file = RotatingFileHandler(
        str(log_path / "error.log"),
        level=LogLevel.ERROR,
        max_bytes=10*1024*1024,
        backup_count=5
    )
    if json_format:
        error_file.formatter = lambda e: e.to_json()
    logger.add_handler(error_file)
    
    _default_logger = logger
    return logger



