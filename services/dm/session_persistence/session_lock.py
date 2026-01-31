"""
会话锁实现
使用Redis实现分布式锁，防止并发访问冲突
"""

import asyncio
from typing import Optional

from ...core.database import get_redis_client
from ...core.logging import app_logger


class SessionLock:
    """会话锁"""
    
    def __init__(self, session_id: str, timeout: int = 30):
        """
        初始化会话锁
        
        Args:
            session_id: 会话ID
            timeout: 锁超时时间（秒）
        """
        self.session_id = session_id
        self.timeout = timeout
        self.redis_key = f"session_lock:{session_id}"
        self.lock_value = None
        self.logger = app_logger
    
    async def acquire(self) -> bool:
        """
        获取锁
        
        Returns:
            是否获取成功
        """
        try:
            redis = await get_redis_client()
            
            # 生成唯一的锁值
            import time
            self.lock_value = f"{time.time()}:{id(self)}"
            
            # 尝试获取锁
            acquired = redis.set(
                self.redis_key,
                self.lock_value,
                nx=True,
                ex=self.timeout
            )
            
            if acquired:
                self.logger.debug(f"获取会话锁成功: {self.session_id}")
                return True
            else:
                self.logger.debug(f"获取会话锁失败: {self.session_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"获取锁失败: {e}", exc_info=True)
            return False
    
    async def release(self) -> bool:
        """
        释放锁
        
        Returns:
            是否释放成功
        """
        try:
            redis = await get_redis_client()
            
            # 使用Lua脚本确保只释放自己持有的锁
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            
            result = redis.eval(
                lua_script,
                1,
                self.redis_key,
                self.lock_value
            )
            
            if result:
                self.logger.debug(f"释放会话锁成功: {self.session_id}")
                return True
            else:
                self.logger.warning(f"释放会话锁失败，锁已过期: {self.session_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"释放锁失败: {e}", exc_info=True)
            return False
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        acquired = await self.acquire()
        if not acquired:
            raise Exception(f"无法获取会话锁: {self.session_id}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.release()