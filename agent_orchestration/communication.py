"""
智能体通信机制实现
"""

import asyncio
import time
import uuid
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import logging

from .interfaces import (
    ICommunicator, IAgent, AgentMessage, MessageType,
    AgentStatus
)

@dataclass
class MessageQueue:
    """消息队列"""
    messages: deque = field(default_factory=deque)
    max_size: int = 1000
    last_access: float = field(default_factory=time.time)
    drop_oldest: bool = False  # 队列满时是否丢弃最旧的消息
    
    def add_message(self, message: AgentMessage) -> bool:
        """添加消息到队列"""
        if len(self.messages) >= self.max_size:
            if self.drop_oldest:
                # 队列已满，移除最旧的消息并添加新消息
                self.messages.popleft()
            else:
                # 队列已满，拒绝新消息
                return False
        
        self.messages.append(message)
        self.last_access = time.time()
        return True
    
    def get_message(self) -> Optional[AgentMessage]:
        """获取队列中的第一条消息"""
        if self.messages:
            self.last_access = time.time()
            return self.messages.popleft()
        return None
    
    def peek_message(self) -> Optional[AgentMessage]:
        """查看队列中的第一条消息但不移除"""
        if self.messages:
            return self.messages[0]
        return None
    
    def size(self) -> int:
        """获取队列大小"""
        return len(self.messages)

@dataclass
class Subscription:
    """消息订阅"""
    agent_id: str
    message_types: Set[MessageType]
    filter_func: Optional[Callable[[AgentMessage], bool]] = None
    created_at: float = field(default_factory=time.time)

class AgentCommunicator(ICommunicator):
    """智能体通信器实现"""
    
    def __init__(self, max_queue_size: int = 1000, message_timeout: float = 300.0,
                 enable_history: bool = True, sanitize_history: bool = True):
        self.max_queue_size = max_queue_size
        self.message_timeout = message_timeout
        
        # 智能体注册表 - 使用集合跟踪已注册的ID
        self.registered_agents: Dict[str, IAgent] = {}
        self.registered_agent_ids: Set[str] = set()
        
        # 消息队列 (每个智能体一个队列)
        self.message_queues: Dict[str, MessageQueue] = defaultdict(
            lambda: MessageQueue(max_size=max_queue_size, drop_oldest=True)
        )
        
        # 订阅管理
        self.subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        
        # 消息历史 (用于调试和追踪)
        self.message_history: List[AgentMessage] = []
        self.max_history_size = 10000
        # 配置选项：是否启用历史记录
        self.enable_history = enable_history
        # 配置选项：是否对敏感信息进行脱敏
        self.sanitize_history = sanitize_history
        
        # 统计信息
        self.stats = {
            'messages_sent': 0,
            'messages_delivered': 0,
            'messages_expired': 0,
            'broadcast_count': 0
        }
        
        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        self.logger = logging.getLogger(__name__)
    
    async def start(self) -> None:
        """启动通信器"""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info("AgentCommunicator started")
    
    async def stop(self) -> None:
        """停止通信器"""
        if not self._running:
            return
        
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("AgentCommunicator stopped")
    
    async def register_agent(self, agent_id: str, agent: Optional[IAgent] = None) -> None:
        """注册智能体"""
        if agent_id not in self.registered_agent_ids:
            # 创建消息队列
            self.message_queues[agent_id] = MessageQueue(max_size=self.max_queue_size, drop_oldest=True)
            # 将代理添加到注册表
            self.registered_agents[agent_id] = agent
            # 添加到ID集合
            self.registered_agent_ids.add(agent_id)
            self.logger.info(f"Agent {agent_id} registered")
    
    async def unregister_agent(self, agent_id: str) -> None:
        """注销智能体"""
        # 清理消息队列
        if agent_id in self.message_queues:
            del self.message_queues[agent_id]
        
        # 清理订阅
        if agent_id in self.subscriptions:
            del self.subscriptions[agent_id]
        
        # 从注册表中移除
        if agent_id in self.registered_agents:
            del self.registered_agents[agent_id]
        
        # 从ID集合中移除
        self.registered_agent_ids.discard(agent_id)
        
        self.logger.info(f"Agent {agent_id} unregistered")
    
    async def send_message(self, message: AgentMessage) -> None:
        """发送消息"""
        # 验证消息
        if not message.receiver_id:
            raise ValueError("Message receiver_id is required")
        
        # 添加时间戳
        if not message.timestamp:
            message.timestamp = time.time()
        
        # 添加关联ID（如果没有）
        if not message.correlation_id:
            message.correlation_id = str(uuid.uuid4())
        
        # 检查接收者是否存在
        if message.receiver_id not in self.message_queues:
            self.logger.warning(f"Receiver {message.receiver_id} not found, message discarded")
            return
        
        # 检查订阅过滤
        if not self._should_deliver_message(message):
            return
        
        # 添加到接收者队列
        queue = self.message_queues[message.receiver_id]
        success = queue.add_message(message)
        
        if success:
            self.stats['messages_sent'] += 1
            self._add_to_history(message)
            self.logger.debug(f"Message sent from {message.sender_id} to {message.receiver_id}")
        else:
            self.logger.warning(f"Failed to send message to {message.receiver_id}: queue full")
    
    async def receive_message(self, agent_id: str, timeout: float = 30.0) -> Optional[AgentMessage]:
        """接收消息"""
        if agent_id not in self.message_queues:
            self.logger.warning(f"Agent {agent_id} not registered")
            return None
        
        queue = self.message_queues[agent_id]
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            message = queue.get_message()
            if message:
                self.stats['messages_delivered'] += 1
                self.logger.debug(f"Message delivered to {agent_id}")
                return message
            
            # 短暂等待
            await asyncio.sleep(0.1)
        
        self.logger.debug(f"Receive timeout for agent {agent_id}")
        return None
    
    async def broadcast_message(self, message: AgentMessage, exclude_agents: Optional[List[str]] = None) -> None:
        """广播消息"""
        exclude_agents = exclude_agents or []
        exclude_set = set(exclude_agents)
        exclude_set.add(message.sender_id)  # 不发送给自己
        
        delivered_count = 0
        for agent_id in self.message_queues:
            if agent_id not in exclude_set:
                # 创建消息副本
                broadcast_msg = AgentMessage(
                    sender_id=message.sender_id,
                    receiver_id=agent_id,
                    message_type=message.message_type,
                    content=message.content,
                    timestamp=message.timestamp,
                    correlation_id=message.correlation_id,
                    metadata=message.metadata.copy()
                )
                
                # 直接添加到历史记录，不通过send_message（避免重复记录）
                self._add_to_history(broadcast_msg)
                
                # 检查订阅过滤
                if not self._should_deliver_message(broadcast_msg):
                    continue
                
                # 添加到接收者队列
                queue = self.message_queues[agent_id]
                success = queue.add_message(broadcast_msg)
                
                if success:
                    self.stats['messages_sent'] += 1
                    delivered_count += 1
                else:
                    self.logger.warning(f"Failed to broadcast message to {agent_id}: queue full")
        
        self.stats['broadcast_count'] += 1
        self.logger.info(f"Broadcast message from {message.sender_id} to {delivered_count} agents")
    
    async def subscribe(self, agent_id: str, message_types: List[MessageType], 
                       filter_func: Optional[Callable[[AgentMessage], bool]] = None) -> None:
        """订阅消息类型"""
        subscription = Subscription(
            agent_id=agent_id,
            message_types=set(message_types),
            filter_func=filter_func
        )
        
        self.subscriptions[agent_id].append(subscription)
        self.logger.info(f"Agent {agent_id} subscribed to {[mt.value for mt in message_types]}")
    
    async def unsubscribe(self, agent_id: str, message_types: Optional[List[MessageType]] = None) -> None:
        """取消订阅"""
        if agent_id not in self.subscriptions:
            return
        
        if message_types is None:
            # 取消所有订阅
            del self.subscriptions[agent_id]
            self.logger.info(f"Agent {agent_id} unsubscribed from all message types")
        else:
            # 取消特定类型的订阅
            message_type_set = set(message_types)
            original_count = len(self.subscriptions[agent_id])
            
            # 从每个订阅中移除特定的消息类型
            new_subscriptions = []
            for sub in self.subscriptions[agent_id]:
                # 计算移除特定类型后的消息类型集合
                remaining_types = sub.message_types - message_type_set
                
                # 如果还有剩余的消息类型，保留这个订阅
                if remaining_types:
                    # 创建新的订阅对象，只包含剩余的消息类型
                    new_sub = Subscription(
                        agent_id=sub.agent_id,
                        message_types=remaining_types,
                        filter_func=sub.filter_func,
                        created_at=sub.created_at
                    )
                    new_subscriptions.append(new_sub)
            
            self.subscriptions[agent_id] = new_subscriptions
            
            new_count = len(self.subscriptions[agent_id])
            if new_count < original_count:
                self.logger.info(f"Agent {agent_id} unsubscribed from {[mt.value for mt in message_types]}")
    
    def get_message_history(self, agent_id: Optional[str] = None,
                           message_type: Optional[MessageType] = None,
                           limit: int = 100) -> List[AgentMessage]:
        """获取消息历史"""
        history = self.message_history.copy()
        
        # 过滤条件
        if agent_id:
            history = [msg for msg in history
                      if msg.sender_id == agent_id or msg.receiver_id == agent_id]
        
        if message_type:
            history = [msg for msg in history if msg.message_type == message_type]
        
        # 按时间倒序排列，返回最新的
        history.sort(key=lambda x: x.timestamp, reverse=True)
        return history[:limit]
    
    def get_queue_status(self, agent_id: str) -> Dict[str, Any]:
        """获取队列状态"""
        if agent_id not in self.message_queues:
            return {"error": "Agent not found"}
        
        queue = self.message_queues[agent_id]
        return {
            "queue_size": queue.size(),
            "last_access": queue.last_access,
            "max_size": queue.max_size
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "registered_agents": len(self.registered_agent_ids),
            "active_queues": len(self.message_queues),
            "total_subscriptions": sum(len(subs) for subs in self.subscriptions.values()),
            "history_size": len(self.message_history)
        }
    
    def is_agent_registered(self, agent_id: str) -> bool:
        """检查智能体是否已注册"""
        return agent_id in self.registered_agent_ids
    
    def get_registered_agent(self, agent_id: str) -> Optional[IAgent]:
        """获取已注册的智能体对象"""
        return self.registered_agents.get(agent_id)
    
    def _should_deliver_message(self, message: AgentMessage) -> bool:
        """检查是否应该投递消息"""
        # 检查接收者的订阅
        if message.receiver_id not in self.subscriptions:
            return True  # 没有订阅设置，接收所有消息
        
        subscriptions = self.subscriptions[message.receiver_id]
        for sub in subscriptions:
            # 检查消息类型
            if message.message_type in sub.message_types:
                # 检查自定义过滤函数
                if sub.filter_func is None or sub.filter_func(message):
                    return True
        
        return False
    
    def _add_to_history(self, message: AgentMessage) -> None:
        """添加消息到历史记录"""
        # 检查是否启用历史记录
        if not self.enable_history:
            return
            
        # 对敏感信息进行脱敏处理
        if self.sanitize_history:
            message = self._sanitize_message(message)
            
        self.message_history.append(message)
        
        # 限制历史记录大小
        if len(self.message_history) > self.max_history_size:
            self.message_history = self.message_history[-self.max_history_size:]
    
    def _sanitize_message(self, message: AgentMessage) -> AgentMessage:
        """对消息进行脱敏处理，隐藏敏感信息"""
        import re
        
        # 创建消息副本
        sanitized_content = message.content
        
        # 如果内容是字符串，进行脱敏处理
        if isinstance(sanitized_content, str):
            # 脱敏API密钥模式
            sanitized_content = re.sub(r'(sk-[a-zA-Z0-9]{20,})', 'sk-***', sanitized_content)
            # 脱敏密码模式
            sanitized_content = re.sub(r'(["\']?password["\']?\s*[:=]\s*["\']?)([^"\']\s]+)', r'\1***', sanitized_content, flags=re.IGNORECASE)
            # 脱敏邮箱
            sanitized_content = re.sub(r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'***@\2', sanitized_content)
            # 脱敏IP地址
            sanitized_content = re.sub(r'\b(\d{1,3}\.){3}\d{1,3}\b', '***.***.***.***', sanitized_content)
            # 脱敏URL中的敏感参数
            sanitized_content = re.sub(r'([?&](api_key|token|password)=)[^&\s]+', r'\1***', sanitized_content, flags=re.IGNORECASE)
        
        # 创建脱敏后的消息
        return AgentMessage(
            sender_id=message.sender_id,
            receiver_id=message.receiver_id,
            message_type=message.message_type,
            content=sanitized_content,
            timestamp=message.timestamp,
            correlation_id=message.correlation_id,
            metadata=message.metadata.copy()
        )
    
    def set_history_config(self, enable_history: bool = None, sanitize_history: bool = None) -> None:
        """设置历史记录配置"""
        if enable_history is not None:
            self.enable_history = enable_history
            self.logger.info(f"消息历史记录已{'启用' if enable_history else '禁用'}")
            
        if sanitize_history is not None:
            self.sanitize_history = sanitize_history
            self.logger.info(f"消息历史脱敏已{'启用' if sanitize_history else '禁用'}")
    
    def clear_history(self) -> None:
        """清空消息历史记录"""
        self.message_history.clear()
        self.logger.info("消息历史记录已清空")
    
    async def _cleanup_loop(self) -> None:
        """清理循环"""
        while self._running:
            try:
                await self._cleanup_expired_messages()
                await asyncio.sleep(60)  # 每分钟清理一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Cleanup loop error: {e}")
    
    async def _cleanup_expired_messages(self) -> None:
        """清理过期消息"""
        current_time = time.time()
        expired_count = 0
        
        for agent_id, queue in self.message_queues.items():
            # 直接从队列头部检查过期消息
            while queue.messages:
                oldest_message = queue.messages[0]
                age = current_time - oldest_message.timestamp
                if age > self.message_timeout:
                    queue.messages.popleft()
                    expired_count += 1
                    self.logger.debug(f"Removed expired message from {agent_id}: age={age:.2f}s, timeout={self.message_timeout}s")
                else:
                    break  # 消息按时间顺序排列，后面的消息更新
        
        if expired_count > 0:
            self.stats['messages_expired'] += expired_count
            self.logger.debug(f"Cleaned up {expired_count} expired messages")

# 便捷函数
async def create_communicator(max_queue_size: int = 1000, message_timeout: float = 300.0) -> AgentCommunicator:
    """创建并启动通信器"""
    communicator = AgentCommunicator(max_queue_size, message_timeout)
    await communicator.start()
    return communicator