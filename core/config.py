"""
应用配置管理模块

使用Pydantic Settings管理应用配置，支持从环境变量、.env文件和默认值读取配置。
提供类型验证、自动转换和默认值设置功能。
"""

import os
from typing import List, Optional

from pydantic import validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    应用配置类
    
    所有配置项都有类型提示和默认值，Pydantic会自动进行类型验证和转换。
    配置值从环境变量、.env文件和默认值按优先级读取。
    """
    
    # ===========================================
    # 应用基础配置
    # ===========================================
    
    # 应用环境
    environment: str = "development"
    
    # 调试模式
    debug: bool = True
    
    # 应用主机和端口
    host: str = "0.0.0.0"
    port: int = 8000
    
    # API版本
    api_version: str = "v1"
    
    # 应用密钥
    secret_key: str = "dev-secret-key-change-in-production"
    
    # JWT令牌过期时间（分钟）
    access_token_expire_minutes: int = 30
    
    @validator("environment")
    def validate_environment(cls, v):
        """验证环境配置值"""
        allowed = ["development", "testing", "production"]
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v
    
    # ===========================================
    # 数据库配置
    # ===========================================
    
    # Neo4j配置
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    
    # Redis配置
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None
    
    # ===========================================
    # AI模型提供商配置
    # ===========================================
    
    # OpenAI配置
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    
    # Anthropic配置
    anthropic_api_key: Optional[str] = None
    
    # Ollama配置
    ollama_base_url: str = "http://localhost:11434"
    
    # OpenRouter配置
    openrouter_api_key: Optional[str] = None
    
    # ===========================================
    # 文件存储配置
    # ===========================================
    
    # 文件上传路径
    upload_dir: str = "./uploads"
    
    # 最大文件上传大小（MB）
    max_upload_size: int = 10
    
    @validator("upload_dir")
    def validate_upload_dir(cls, v):
        """确保上传目录存在"""
        os.makedirs(v, exist_ok=True)
        return v
    
    # ===========================================
    # 日志配置
    # ===========================================
    
    # 日志级别
    log_level: str = "INFO"
    
    # 日志文件路径
    log_file: str = "./logs/app.log"
    
    # 日志文件最大大小（MB）
    log_file_max_size: int = 10
    
    # 日志文件备份数量
    log_file_backup_count: int = 5
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """验证日志级别"""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()
    
    # ===========================================
    # 安全配置
    # ===========================================
    
    # CORS允许的源
    cors_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    
    # 允许的主机
    allowed_hosts: List[str] = ["localhost", "127.0.0.1"]
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """解析CORS源列表（支持逗号分隔的字符串）"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("allowed_hosts", pre=True)
    def parse_allowed_hosts(cls, v):
        """解析允许主机列表（支持逗号分隔的字符串）"""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",")]
        return v
    
    # ===========================================
    # WebSocket配置
    # ===========================================
    
    # WebSocket心跳间隔（秒）
    websocket_heartbeat_interval: int = 30
    
    # WebSocket连接超时（秒）
    websocket_timeout: int = 60
    
    # ===========================================
    # 前端配置
    # ===========================================
    
    # 前端应用URL
    frontend_url: str = "http://localhost:5173"
    
    class Config:
        """Pydantic配置"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # 环境变量不区分大小写
        
    @property
    def is_development(self) -> bool:
        """判断是否为开发环境"""
        return self.environment == "development"
    
    @property
    def is_production(self) -> bool:
        """判断是否为生产环境"""
        return self.environment == "production"
    
    @property
    def is_testing(self) -> bool:
        """判断是否为测试环境"""
        return self.environment == "testing"


# 创建全局配置实例
settings = Settings()

# 导出配置实例
__all__ = ["settings", "Settings"]