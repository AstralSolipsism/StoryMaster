"""
数据库连接管理模块

负责管理Neo4j和Redis数据库的连接、初始化和健康检查。
提供统一的数据库连接接口和生命周期管理。
"""

import asyncio
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

import redis
from neo4j import GraphDatabase, Driver, AsyncGraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from .config import settings


class DatabaseManager:
    """
    数据库管理器
    
    负责管理Neo4j和Redis连接，提供连接池和健康检查功能。
    """
    
    def __init__(self):
        self._neo4j_driver: Optional[AsyncGraphDatabase.driver] = None
        self._redis_client: Optional[redis.Redis] = None
        self._is_initialized = False
    
    async def initialize(self) -> None:
        """
        初始化所有数据库连接
        
        Raises:
            ConnectionError: 当数据库连接失败时
        """
        if self._is_initialized:
            return
        
        try:
            # 初始化Neo4j连接
            await self._init_neo4j()
            
            # 初始化Redis连接
            await self._init_redis()
            
            self._is_initialized = True
            print("✅ 数据库连接初始化成功")
            
        except Exception as e:
            print(f"❌ 数据库连接初始化失败: {e}")
            raise ConnectionError(f"数据库连接初始化失败: {e}")
    
    async def _init_neo4j(self) -> None:
        """初始化Neo4j连接"""
        try:
            self._neo4j_driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
                max_connection_lifetime=3600,  # 1小时
                max_connection_pool_size=50,
                connection_acquisition_timeout=60,  # 60秒超时
            )
            
            # 测试连接
            await self._verify_neo4j_connection()
            
        except AuthError as e:
            raise ConnectionError(f"Neo4j认证失败: {e}")
        except ServiceUnavailable as e:
            raise ConnectionError(f"Neo4j服务不可用: {e}")
        except Exception as e:
            raise ConnectionError(f"Neo4j连接失败: {e}")
    
    async def _init_redis(self) -> None:
        """初始化Redis连接"""
        try:
            # 创建Redis连接配置
            redis_kwargs = {
                'decode_responses': True,  # 自动解码响应
                'socket_connect_timeout': 5,
                'socket_timeout': 5,
                'retry_on_timeout': True,
                'health_check_interval': 30,
            }
            
            # 如果有密码，添加到配置中
            if settings.redis_password:
                redis_kwargs['password'] = settings.redis_password
            
            # 创建Redis客户端
            self._redis_client = redis.from_url(
                settings.redis_url,
                **redis_kwargs
            )
            
            # 测试连接
            await self._verify_redis_connection()
            
        except Exception as e:
            raise ConnectionError(f"Redis连接失败: {e}")
    
    async def _verify_neo4j_connection(self) -> None:
        """验证Neo4j连接"""
        if not self._neo4j_driver:
            raise ConnectionError("Neo4j驱动未初始化")
        
        async with self._neo4j_driver.session() as session:
            result = await session.run("RETURN 1 as test")
            record = await result.single()
            if record["test"] != 1:
                raise ConnectionError("Neo4j连接测试失败")
    
    async def _verify_redis_connection(self) -> None:
        """验证Redis连接"""
        if not self._redis_client:
            raise ConnectionError("Redis客户端未初始化")
        
        # 测试连接
        try:
            # 使用同步版本，因为redis-py没有原生异步支持
            self._redis_client.ping()
        except Exception as e:
            raise ConnectionError(f"Redis连接测试失败: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        检查所有数据库的健康状态
        
        Returns:
            包含各数据库健康状态的字典
        """
        health_status = {
            "neo4j": {"status": "unknown", "message": ""},
            "redis": {"status": "unknown", "message": ""},
        }
        
        # 检查Neo4j
        try:
            if self._neo4j_driver:
                await self._verify_neo4j_connection()
                health_status["neo4j"]["status"] = "healthy"
                health_status["neo4j"]["message"] = "连接正常"
            else:
                health_status["neo4j"]["status"] = "error"
                health_status["neo4j"]["message"] = "驱动未初始化"
        except Exception as e:
            health_status["neo4j"]["status"] = "error"
            health_status["neo4j"]["message"] = str(e)
        
        # 检查Redis
        try:
            if self._redis_client:
                await self._verify_redis_connection()
                health_status["redis"]["status"] = "healthy"
                health_status["redis"]["message"] = "连接正常"
            else:
                health_status["redis"]["status"] = "error"
                health_status["redis"]["message"] = "客户端未初始化"
        except Exception as e:
            health_status["redis"]["status"] = "error"
            health_status["redis"]["message"] = str(e)
        
        return health_status
    
    @property
    def neo4j_driver(self) -> Optional[AsyncGraphDatabase.driver]:
        """获取Neo4j驱动实例"""
        return self._neo4j_driver
    
    @property
    def redis_client(self) -> Optional[redis.Redis]:
        """获取Redis客户端实例"""
        return self._redis_client
    
    async def close(self) -> None:
        """关闭所有数据库连接"""
        try:
            if self._neo4j_driver:
                self._neo4j_driver.close()
                self._neo4j_driver = None
            
            if self._redis_client:
                # Redis客户端没有异步close方法，使用同步方式
                self._redis_client.close()
                self._redis_client = None
            
            self._is_initialized = False
            print("✅ 数据库连接已关闭")
            
        except Exception as e:
            print(f"❌ 关闭数据库连接时出错: {e}")


# 创建全局数据库管理器实例
db_manager = DatabaseManager()


@asynccontextmanager
async def get_neo4j_session():
    """
    获取Neo4j会话的上下文管理器
    
    使用示例:
        async with get_neo4j_session() as session:
            result = await session.run("MATCH (n) RETURN n LIMIT 1")
            records = await result.data()
    """
    if not db_manager.neo4j_driver:
        raise ConnectionError("Neo4j驱动未初始化")
    
    async with db_manager.neo4j_driver.session() as session:
        yield session


async def get_redis_client() -> redis.Redis:
    """
    获取Redis客户端
    
    Returns:
        Redis客户端实例
        
    Raises:
        ConnectionError: 当Redis未初始化时
    """
    if not db_manager.redis_client:
        raise ConnectionError("Redis客户端未初始化")
    
    return db_manager.redis_client


# 导出函数和实例
__all__ = [
    "db_manager",
    "get_neo4j_session",
    "get_redis_client",
    "DatabaseManager",
]