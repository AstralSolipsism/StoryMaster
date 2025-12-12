"""
Redis缓存适配器实现

提供Redis缓存的连接和操作功能。
"""

import json
import logging
from typing import Dict, List, Any, Optional, Callable
import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from ..interfaces import ICacheManager


class RedisAdapter(ICacheManager):
    """Redis缓存适配器"""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0,
                 password: Optional[str] = None, max_connections: int = 10):
        """
        初始化Redis适配器
        
        Args:
            host: Redis主机地址
            port: Redis端口
            db: 数据库编号
            password: 密码
            max_connections: 最大连接数
        """
        import hashlib
        import os
        
        self.host = host
        self.port = port
        self.db = db
        # 对密码进行哈希处理，避免明文存储
        self._password_hash = hashlib.sha256(password.encode()).hexdigest() if password else None
        # 在内存中保留明文密码仅用于连接，使用后应清除
        self._password = password
        self.max_connections = max_connections
        
        self.client = None
        self.connection_pool = None
        self.logger = logging.getLogger(__name__)
    
    async def connect(self) -> bool:
        """连接Redis"""
        try:
            # 创建连接池
            self.connection_pool = ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self._password,
                max_connections=self.max_connections,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            
            # 创建Redis客户端
            self.client = redis.Redis(connection_pool=self.connection_pool)
            
            # 连接成功后，清除内存中的明文密码
            self._clear_password()
            
            # 测试连接
            await self.client.ping()
            
            self.logger.info(f"成功连接到Redis: {self.host}:{self.port}")
            return True
            
        except Exception as e:
            self.logger.error(f"连接Redis失败: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """断开Redis连接"""
        try:
            if self.client:
                await self.client.close()
            if self.connection_pool:
                await self.connection_pool.disconnect()
            
            self.logger.info("已断开Redis连接")
            return True
            
        except Exception as e:
            self.logger.error(f"断开Redis连接时发生错误: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value.decode('utf-8'))
            return None
            
        except Exception as e:
            self.logger.error(f"获取缓存数据时发生错误: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存数据"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            serialized_value = json.dumps(value, ensure_ascii=False, default=str)
            
            if ttl:
                return await self.client.setex(key, ttl, serialized_value)
            else:
                return await self.client.set(key, serialized_value)
                
        except Exception as e:
            self.logger.error(f"设置缓存数据时发生错误: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """删除缓存数据"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            result = await self.client.delete(key)
            return result > 0
            
        except Exception as e:
            self.logger.error(f"删除缓存数据时发生错误: {e}")
            return False
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """根据模式批量删除缓存"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            # 获取匹配的键
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                # 批量删除
                result = await self.client.delete(*keys)
                self.logger.debug(f"批量删除缓存，模式: {pattern}, 删除数量: {result}")
                return result
            
            return 0
            
        except Exception as e:
            self.logger.error(f"批量删除缓存时发生错误: {e}")
            return 0
    
    async def get_or_set(self, key: str, fetch_func: Callable, 
                        ttl: Optional[int] = None) -> Any:
        """获取缓存，如果不存在则调用fetch_func获取并缓存"""
        # 先尝试从缓存获取
        cached_value = await self.get(key)
        if cached_value is not None:
            return cached_value
        
        # 缓存未命中，调用fetch_func
        try:
            new_value = await fetch_func()
            if new_value is not None:
                await self.set(key, new_value, ttl)
            return new_value
            
        except Exception as e:
            self.logger.error(f"调用fetch_func时发生错误: {e}")
            return None
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            return await self.client.exists(key) > 0
            
        except Exception as e:
            self.logger.error(f"检查键是否存在时发生错误: {e}")
            return False
    
    async def expire(self, key: str, ttl: int) -> bool:
        """设置键的过期时间"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            return await self.client.expire(key, ttl)
            
        except Exception as e:
            self.logger.error(f"设置键过期时间时发生错误: {e}")
            return False
    
    async def ttl(self, key: str) -> int:
        """获取键的剩余生存时间"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            return await self.client.ttl(key)
            
        except Exception as e:
            self.logger.error(f"获取键TTL时发生错误: {e}")
            return -1
    
    async def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配模式的所有键"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key.decode('utf-8'))
            return keys
            
        except Exception as e:
            self.logger.error(f"获取键列表时发生错误: {e}")
            return []
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """将键的值增加指定数量"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            return await self.client.incrby(key, amount)
            
        except Exception as e:
            self.logger.error(f"增加键值时发生错误: {e}")
            return 0
    
    async def hash_get(self, key: str, field: str) -> Optional[Any]:
        """获取哈希字段值"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            value = await self.client.hget(key, field)
            if value:
                return json.loads(value.decode('utf-8'))
            return None
            
        except Exception as e:
            self.logger.error(f"获取哈希字段值时发生错误: {e}")
            return None
    
    async def hash_set(self, key: str, field: str, value: Any) -> bool:
        """设置哈希字段值"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            serialized_value = json.dumps(value, ensure_ascii=False, default=str)
            return await self.client.hset(key, field, serialized_value)
            
        except Exception as e:
            self.logger.error(f"设置哈希字段值时发生错误: {e}")
            return False
    
    async def hash_get_all(self, key: str) -> Dict[str, Any]:
        """获取哈希所有字段和值"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            hash_data = await self.client.hgetall(key)
            result = {}
            for field, value in hash_data.items():
                try:
                    result[field.decode('utf-8')] = json.loads(value.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    result[field.decode('utf-8')] = value.decode('utf-8')
            return result
            
        except Exception as e:
            self.logger.error(f"获取哈希所有字段时发生错误: {e}")
            return {}
    
    async def list_push(self, key: str, *values) -> int:
        """向列表推入值"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            serialized_values = [
                json.dumps(value, ensure_ascii=False, default=str) 
                for value in values
            ]
            return await self.client.lpush(key, *serialized_values)
            
        except Exception as e:
            self.logger.error(f"向列表推入值时发生错误: {e}")
            return 0
    
    async def list_pop(self, key: str) -> Optional[Any]:
        """从列表弹出值"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            value = await self.client.rpop(key)
            if value:
                return json.loads(value.decode('utf-8'))
            return None
            
        except Exception as e:
            self.logger.error(f"从列表弹出值时发生错误: {e}")
            return None
    
    async def list_range(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """获取列表范围内的值"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化")
        
        try:
            values = await self.client.lrange(key, start, end)
            result = []
            for value in values:
                try:
                    result.append(json.loads(value.decode('utf-8')))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    result.append(value.decode('utf-8'))
            return result
            
        except Exception as e:
            self.logger.error(f"获取列表范围值时发生错误: {e}")
            return []
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        if not self.client:
            return {"connected": False}
        
        try:
            info = await self.client.info()
            return {
                "connected": True,
                "host": self.host,
                "port": self.port,
                "db": self.db,
                "redis_version": info.get("redis_version"),
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients")
            }
        except Exception as e:
            self.logger.error(f"获取连接信息时发生错误: {e}")
            return {"connected": False, "error": str(e)}
    
    def _clear_password(self) -> None:
        """清除内存中的明文密码"""
        if hasattr(self, '_password'):
            delattr(self, '_password')
            # 尝试覆盖内存中的密码数据
            import sys
            self._password = None
            # 强制垃圾回收
            import gc
            gc.collect()
    
    def __del__(self):
        """析构函数，确保密码被清除"""
        self._clear_password()