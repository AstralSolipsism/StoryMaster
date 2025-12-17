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
        import secrets
        
        self.host = host
        self.port = port
        self.db = db
        # 使用更安全的密码哈希算法，添加盐值
        self._salt = secrets.token_hex(16) if password else None
        if password:
            self._password_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode(),
                self._salt.encode(),
                100000  # 迭代次数
            ).hex()
        else:
            self._password_hash = None
        # 不在实例变量中存储明文密码，而是使用临时变量传递给连接方法
        self._temp_password = password  # 临时存储，将在连接后立即清除
        self.max_connections = max_connections
        
        self.client = None
        self.connection_pool = None
        self.logger = logging.getLogger(__name__)
    
    async def connect(self) -> bool:
        """连接Redis"""
        # 检查是否有临时密码可用（None密码也是有效的）
        if not hasattr(self, '_temp_password'):
            self.logger.error("没有可用的密码进行连接")
            return False
            
        # 使用局部变量存储密码，避免在实例变量中长期保存
        password = self._temp_password
        
        try:
            # 创建连接池
            self.connection_pool = ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                password=password,
                max_connections=self.max_connections,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            
            # 创建Redis客户端
            self.client = redis.Redis(connection_pool=self.connection_pool)
            
            # 立即清除临时密码
            self._clear_temp_password()
            
            # 测试连接
            await self.client.ping()
            
            self.logger.info(f"成功连接到Redis: {self.host}:{self.port}")
            return True
            
        except Exception as e:
            self.logger.error(f"连接Redis失败: {e}")
            # 即使连接失败也要清除密码
            self._clear_temp_password()
            return False
        finally:
            # 确保密码变量被清除
            password = None
    
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
    
    def _clear_temp_password(self) -> None:
        """清除临时存储的明文密码"""
        if hasattr(self, '_temp_password'):
            # 使用多种方法确保密码被安全清除
            import sys
            # 获取密码字符串的引用
            password_ref = self._temp_password
            
            # 只有当密码不是None时才清除（None是有效的无密码状态）
            if password_ref is not None:
                # 尝试覆盖内存中的密码数据
                if isinstance(password_ref, str):
                    # 对于字符串，我们无法直接覆盖内存，但可以删除引用
                    delattr(self, '_temp_password')
                    # 尝试从局部命名空间中清除
                    if 'password_ref' in locals():
                        password_ref = None
                else:
                    # 对于其他类型，直接删除
                    delattr(self, '_temp_password')
                
                # 强制垃圾回收以尽快释放内存
                import gc
                gc.collect()
    
    def _clear_password(self) -> None:
        """清除内存中的明文密码（保留向后兼容性）"""
        self._clear_temp_password()
    
    def __del__(self):
        """析构函数，确保密码被清除"""
        self._clear_password()