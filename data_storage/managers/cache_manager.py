"""
缓存管理器实现

提供统一的缓存管理功能，支持多级缓存和缓存策略。
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from enum import Enum

from ..interfaces import (
    ICacheManager,
    IStorageAdapter,
    CacheConfig,
    CacheStats,
    DataStorageError
)

logger = logging.getLogger(__name__)


class CacheStrategy(Enum):
    """缓存策略枚举"""
    LRU = "lru"  # 最近最少使用
    LFU = "lfu"  # 最少使用频率
    TTL = "ttl"  # 基于时间
    WRITE_THROUGH = "write_through"  # 写透
    WRITE_BACK = "write_back"  # 写回


class CacheManager(ICacheManager):
    """缓存管理器实现"""
    
    def __init__(
        self,
        storage_adapter: IStorageAdapter,
        config: Optional[CacheConfig] = None
    ):
        """
        初始化缓存管理器
        
        Args:
            storage_adapter: 存储适配器
            config: 缓存配置
        """
        self._storage = storage_adapter
        self._config = config or CacheConfig()
        
        # 内存缓存存储
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        
        # 缓存统计信息
        self._stats = CacheStats()
        
        # 缓存索引（用于LRU等策略）
        self._access_index: Dict[str, datetime] = {}
        self._frequency_index: Dict[str, int] = {}
        
        logger.info("缓存管理器初始化完成")
    
    async def initialize(self) -> None:
        """初始化缓存管理器"""
        try:
            # 如果配置了持久化缓存，从存储加载缓存数据
            if self._config.persistent_cache:
                await self._load_persistent_cache()
            
            logger.info("缓存管理器初始化成功")
        except Exception as e:
            logger.error(f"缓存管理器初始化失败: {e}")
            raise DataStorageError(f"缓存管理器初始化失败: {e}")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值或None
        """
        try:
            # 先从内存缓存获取
            if key in self._memory_cache:
                cache_item = self._memory_cache[key]
                
                # 检查TTL
                if self._is_expired(cache_item):
                    await self.delete(key)
                    self._stats.misses += 1
                    return None
                
                # 更新访问信息
                self._update_access_info(key)
                self._stats.hits += 1
                
                logger.debug(f"缓存命中: {key}")
                # 反序列化缓存值，确保数据格式一致
                return self._deserialize_value(cache_item['value'])
            
            # 如果启用了持久化缓存，从存储获取
            if self._config.persistent_cache:
                value = await self._get_from_persistent_cache(key)
                if value is not None:
                    # 加载到内存缓存
                    await self.set(key, value, self._config.default_ttl)
                    self._stats.hits += 1
                    return value
            
            self._stats.misses += 1
            return None
            
        except Exception as e:
            logger.error(f"获取缓存失败: {e}")
            self._stats.errors += 1
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
            
        Returns:
            是否设置成功
        """
        try:
            # 检查缓存容量
            if len(self._memory_cache) >= self._config.max_memory_items:
                await self._evict_items()
            
            # 计算过期时间
            ttl = ttl or self._config.default_ttl
            expires_at = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
            
            # 序列化值（如果需要）
            serialized_value = self._serialize_value(value)
            
            # 存储到内存缓存
            cache_item = {
                'value': serialized_value,
                'created_at': datetime.now(),
                'expires_at': expires_at,
                'ttl': ttl,
                'size': len(str(serialized_value))
            }
            
            self._memory_cache[key] = cache_item
            
            # 更新访问信息
            self._update_access_info(key)
            
            # 如果启用了持久化缓存，同时存储到持久化层
            if self._config.persistent_cache:
                await self._set_to_persistent_cache(key, value, ttl)
            
            self._stats.sets += 1
            self._stats.current_size = len(self._memory_cache)
            
            logger.debug(f"设置缓存: {key}")
            return True
            
        except Exception as e:
            logger.error(f"设置缓存失败: {e}")
            self._stats.errors += 1
            return False
    
    async def delete(self, key: str) -> bool:
        """
        删除缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            是否删除成功
        """
        try:
            # 从内存缓存删除
            deleted = False
            if key in self._memory_cache:
                del self._memory_cache[key]
                deleted = True
            
            # 从访问索引删除
            if key in self._access_index:
                del self._access_index[key]
            
            # 从频率索引删除
            if key in self._frequency_index:
                del self._frequency_index[key]
            
            # 从持久化缓存删除
            if self._config.persistent_cache:
                await self._delete_from_persistent_cache(key)
            
            if deleted:
                self._stats.deletes += 1
                self._stats.current_size = len(self._memory_cache)
            
            logger.debug(f"删除缓存: {key}")
            return deleted
            
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")
            self._stats.errors += 1
            return False
    
    async def exists(self, key: str) -> bool:
        """
        检查缓存键是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在
        """
        try:
            # 检查内存缓存
            if key in self._memory_cache:
                cache_item = self._memory_cache[key]
                if not self._is_expired(cache_item):
                    return True
                else:
                    await self.delete(key)
                    return False
            
            # 检查持久化缓存
            if self._config.persistent_cache:
                return await self._exists_in_persistent_cache(key)
            
            return False
            
        except Exception as e:
            logger.error(f"检查缓存存在性失败: {e}")
            return False
    
    async def clear(self) -> bool:
        """
        清空所有缓存
        
        Returns:
            是否清空成功
        """
        try:
            # 清空内存缓存
            self._memory_cache.clear()
            self._access_index.clear()
            self._frequency_index.clear()
            
            # 清空持久化缓存
            if self._config.persistent_cache:
                await self._clear_persistent_cache()
            
            # 重置统计信息
            self._stats = CacheStats()
            
            logger.info("清空所有缓存")
            return True
            
        except Exception as e:
            logger.error(f"清空缓存失败: {e}")
            return False
    
    async def get_stats(self) -> CacheStats:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计信息
        """
        # 更新命中率
        total_requests = self._stats.hits + self._stats.misses
        if total_requests > 0:
            self._stats.hit_rate = self._stats.hits / total_requests
        
        # 更新当前大小
        self._stats.current_size = len(self._memory_cache)
        
        return self._stats
    
    async def cleanup(self) -> None:
        """清理资源"""
        try:
            # 清理过期项
            await self._cleanup_expired_items()
            
            # 如果是写回策略，确保数据持久化
            if self._config.write_strategy == CacheStrategy.WRITE_BACK:
                await self._flush_write_back_cache()
            
            logger.info("缓存管理器清理完成")
            
        except Exception as e:
            logger.error(f"缓存管理器清理失败: {e}")
    
    def _is_expired(self, cache_item: Dict[str, Any]) -> bool:
        """检查缓存项是否过期"""
        if cache_item.get('expires_at') is None:
            return False
        
        return datetime.now() > cache_item['expires_at']
    
    def _update_access_info(self, key: str) -> None:
        """更新访问信息"""
        now = datetime.now()
        
        # 更新访问时间（用于LRU）
        self._access_index[key] = now
        
        # 更新访问频率（用于LFU）
        self._frequency_index[key] = self._frequency_index.get(key, 0) + 1
    
    def _serialize_value(self, value: Any) -> Any:
        """序列化值"""
        # 如果值已经是可序列化的基本类型，直接返回
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        
        # 尝试JSON序列化
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            # 如果无法序列化，转换为字符串
            return str(value)
    
    def _deserialize_value(self, serialized_value: Any) -> Any:
        """反序列化值"""
        # 如果是字符串，尝试反序列化
        if isinstance(serialized_value, str):
            try:
                return json.loads(serialized_value)
            except (TypeError, ValueError):
                return serialized_value
        
        return serialized_value
    
    async def _evict_items(self) -> None:
        """根据策略驱逐缓存项"""
        if not self._memory_cache:
            return
        
        # 计算需要驱逐的数量
        evict_count = max(1, len(self._memory_cache) // 10)  # 驱逐10%
        
        # 根据策略选择驱逐项
        if self._config.eviction_strategy == CacheStrategy.LRU:
            keys_to_evict = self._get_lru_keys(evict_count)
        elif self._config.eviction_strategy == CacheStrategy.LFU:
            keys_to_evict = self._get_lfu_keys(evict_count)
        else:
            # 默认使用LRU
            keys_to_evict = self._get_lru_keys(evict_count)
        
        # 执行驱逐
        for key in keys_to_evict:
            await self.delete(key)
        
        logger.debug(f"驱逐了 {len(keys_to_evict)} 个缓存项")
    
    def _get_lru_keys(self, count: int) -> List[str]:
        """获取最近最少使用的键"""
        # 按访问时间排序
        sorted_items = sorted(
            self._access_index.items(),
            key=lambda x: x[1]
        )
        
        return [key for key, _ in sorted_items[:count]]
    
    def _get_lfu_keys(self, count: int) -> List[str]:
        """获取最少使用频率的键"""
        # 按访问频率排序
        sorted_items = sorted(
            self._frequency_index.items(),
            key=lambda x: x[1]
        )
        
        return [key for key, _ in sorted_items[:count]]
    
    async def _cleanup_expired_items(self) -> None:
        """清理过期项"""
        expired_keys = []
        
        for key, cache_item in self._memory_cache.items():
            if self._is_expired(cache_item):
                expired_keys.append(key)
        
        for key in expired_keys:
            await self.delete(key)
        
        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期缓存项")
    
    async def _load_persistent_cache(self) -> None:
        """从持久化存储加载缓存"""
        try:
            # 这里应该从存储适配器加载缓存数据
            # 具体实现取决于存储适配器的接口设计
            logger.debug("从持久化存储加载缓存")
            
        except Exception as e:
            logger.error(f"加载持久化缓存失败: {e}")
    
    async def _get_from_persistent_cache(self, key: str) -> Optional[Any]:
        """从持久化缓存获取值"""
        try:
            # 这里应该通过存储适配器获取缓存数据
            # 具体实现取决于存储适配器的接口设计
            return None
            
        except Exception as e:
            logger.error(f"从持久化缓存获取失败: {e}")
            return None
    
    async def _set_to_persistent_cache(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """设置值到持久化缓存"""
        try:
            # 这里应该通过存储适配器设置缓存数据
            # 具体实现取决于存储适配器的接口设计
            logger.debug(f"设置持久化缓存: {key}")
            
        except Exception as e:
            logger.error(f"设置持久化缓存失败: {e}")
    
    async def _delete_from_persistent_cache(self, key: str) -> None:
        """从持久化缓存删除值"""
        try:
            # 这里应该通过存储适配器删除缓存数据
            # 具体实现取决于存储适配器的接口设计
            logger.debug(f"删除持久化缓存: {key}")
            
        except Exception as e:
            logger.error(f"删除持久化缓存失败: {e}")
    
    async def _exists_in_persistent_cache(self, key: str) -> bool:
        """检查持久化缓存中是否存在键"""
        try:
            # 这里应该通过存储适配器检查缓存存在性
            # 具体实现取决于存储适配器的接口设计
            return False
            
        except Exception as e:
            logger.error(f"检查持久化缓存存在性失败: {e}")
            return False
    
    async def _clear_persistent_cache(self) -> None:
        """清空持久化缓存"""
        try:
            # 这里应该通过存储适配器清空缓存数据
            # 具体实现取决于存储适配器的接口设计
            logger.debug("清空持久化缓存")
            
        except Exception as e:
            logger.error(f"清空持久化缓存失败: {e}")
    
    async def _flush_write_back_cache(self) -> None:
        """刷新写回缓存"""
        try:
            # 这里应该实现写回策略的刷新逻辑
            # 确保内存中的修改都持久化到存储层
            logger.debug("刷新写回缓存")
            
        except Exception as e:
            logger.error(f"刷新写回缓存失败: {e}")
    
    async def get_or_set(self, key: str, fetch_func, ttl: Optional[int] = None) -> Any:
        """
        获取缓存，如果不存在则调用fetch_func获取并缓存
        
        Args:
            key: 缓存键
            fetch_func: 获取数据的函数
            ttl: 过期时间（秒）
            
        Returns:
            缓存值或fetch_func的结果
        """
        try:
            # 先尝试从缓存获取
            cached_value = await self.get(key)
            if cached_value is not None:
                return cached_value
            
            # 缓存未命中，调用fetch_func
            if callable(fetch_func):
                if asyncio.iscoroutinefunction(fetch_func):
                    new_value = await fetch_func()
                else:
                    new_value = fetch_func()
                
                if new_value is not None:
                    await self.set(key, new_value, ttl)
                return new_value
            
            return None
            
        except Exception as e:
            logger.error(f"get_or_set操作失败: {e}")
            self._stats.errors += 1
            return None
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """
        根据模式批量删除缓存
        
        Args:
            pattern: 匹配模式
            
        Returns:
            删除的键数量
        """
        try:
            deleted_count = 0
            
            # 遍历内存缓存，匹配模式
            keys_to_delete = []
            for key in self._memory_cache.keys():
                if self._match_pattern(key, pattern):
                    keys_to_delete.append(key)
            
            # 删除匹配的键
            for key in keys_to_delete:
                if await self.delete(key):
                    deleted_count += 1
            
            # 如果启用了持久化缓存，也需要从那里删除
            if self._config.persistent_cache:
                # 这里应该通过存储适配器删除匹配模式的键
                # 具体实现取决于存储适配器的接口设计
                pass
            
            logger.debug(f"批量删除缓存，模式: {pattern}, 删除数量: {deleted_count}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"批量删除缓存失败: {e}")
            self._stats.errors += 1
            return 0
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """
        简单的模式匹配
        
        Args:
            key: 键名
            pattern: 模式（支持*通配符）
            
        Returns:
            是否匹配
        """
        import fnmatch
        return fnmatch.fnmatch(key, pattern)