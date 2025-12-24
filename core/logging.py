"""
日志系统配置模块

提供统一的日志配置和管理功能，包括：
- 结构化日志格式
- 多级别日志输出
- 文件和控制台输出
- 日志轮转
- 异步日志支持
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Any, Dict

import structlog
from pythonjsonlogger import jsonlogger

from .config import settings


class ColoredFormatter(logging.Formatter):
    """
    带颜色的日志格式化器（用于控制台输出）
    """
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
        'RESET': '\033[0m'      # 重置
    }
    
    def format(self, record: logging.LogRecord) -> str:
        # 添加颜色
        if hasattr(record, 'levelname'):
            color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            record.levelname = f"{color}{record.levelname}{self.COLORS['RESET']}"
        
        return super().format(record)


def setup_logging() -> None:
    """
    设置应用日志系统
    
    配置：
    - 根日志记录器
    - 文件处理器（带轮转）
    - 控制台处理器
    - 结构化日志（JSON格式）
    """
    # 确保日志目录存在
    log_dir = Path(settings.log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level))
    
    # 清除现有处理器
    root_logger.handlers.clear()
    
    # 设置文件处理器
    _setup_file_handler(root_logger)
    
    # 设置控制台处理器
    _setup_console_handler(root_logger)
    
    # 配置structlog
    _setup_structlog()
    
    # 记录日志系统初始化完成
    logger = logging.getLogger(__name__)
    logger.info(
        "日志系统初始化完成",
        extra={
            "log_level": settings.log_level,
            "log_file": settings.log_file,
            "max_file_size_mb": settings.log_file_max_size,
            "backup_count": settings.log_file_backup_count
        }
    )


def _setup_file_handler(logger: logging.Logger) -> None:
    """设置文件处理器"""
    # 创建JSON格式的文件处理器
    file_handler = logging.handlers.RotatingFileHandler(
        filename=settings.log_file,
        maxBytes=settings.log_file_max_size * 1024 * 1024,  # 转换为字节
        backupCount=settings.log_file_backup_count,
        encoding='utf-8'
    )
    
    # JSON格式化器
    json_formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(getattr(logging, settings.log_level))
    
    logger.addHandler(file_handler)


def _setup_console_handler(logger: logging.Logger) -> None:
    """设置控制台处理器"""
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    
    # 使用彩色格式化器
    console_formatter = ColoredFormatter(
        fmt='%(asctime)s [%(levelname)8s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(getattr(logging, settings.log_level))
    
    logger.addHandler(console_handler)


def _setup_structlog() -> None:
    """配置structlog结构化日志"""
    # 配置structlog处理器链
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if settings.is_production 
        else structlog.dev.ConsoleRenderer(colors=True),
    ]
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    获取结构化日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        structlog.stdlib.BoundLogger: 结构化日志记录器
    """
    return structlog.get_logger(name)


class LoggerMixin:
    """
    日志记录器混入类
    
    为类提供便捷的日志记录功能。
    """
    
    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        """获取当前类的日志记录器"""
        return get_logger(self.__class__.__name__)


def log_function_call(func):
    """
    装饰器：记录函数调用
    
    自动记录函数的开始、结束和异常。
    
    Args:
        func: 要装饰的函数
        
    Returns:
        装饰后的函数
    """
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        func_name = func.__name__
        
        logger.debug(
            f"开始执行函数: {func_name}",
            function=func_name,
            args=args,
            kwargs=kwargs
        )
        
        try:
            result = func(*args, **kwargs)
            logger.debug(
                f"函数执行完成: {func_name}",
                function=func_name,
                result=result
            )
            return result
        except Exception as e:
            logger.error(
                f"函数执行异常: {func_name}",
                function=func_name,
                error=str(e),
                exc_info=True
            )
            raise
    
    return wrapper


# 预定义的常用日志记录器
app_logger = get_logger("app")
db_logger = get_logger("database")
api_logger = get_logger("api")
auth_logger = get_logger("auth")
agent_logger = get_logger("agent")

# 导出函数和类
__all__ = [
    "setup_logging",
    "get_logger",
    "LoggerMixin",
    "log_function_call",
    "app_logger",
    "db_logger",
    "api_logger",
    "auth_logger",
    "agent_logger",
]