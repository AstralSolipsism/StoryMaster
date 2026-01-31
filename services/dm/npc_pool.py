"""
NPC智能体池
管理所有NPC智能体实例
"""

import logging
from typing import Dict, List, Optional, Any

from ...models.dm_models import DispatchedTask, NPCResponse
from ...data_storage.interfaces import Entity, IEntityRepository
from ...provider import ProviderManager
from ...core.logging import app_logger

from .npc_agent import NPCAgent, create_npc_agent


class NPCAgentPool:
    """NPC智能体池"""
    
    def __init__(
        self,
        entity_repository: IEntityRepository,
        model_scheduler: ProviderManager
    ):
        """
        初始化NPC智能体池
        
        Args:
            entity_repository: 实体仓库
            model_scheduler: 模型调度器
        """
        self.entity_repository = entity_repository
        self.model_scheduler = model_scheduler
        
        # 存储所有NPC智能体
        self.agents: Dict[str, NPCAgent] = {}  # npc_id -> NPCAgent
        
        # 存储会话中的激活NPC
        self.active_agents: Dict[str, Dict[str, NPCAgent]] = {}
        # session_id -> {npc_id: NPCAgent}
        
        self.logger = app_logger
    
    async def initialize_npc(
        self,
        npc_id: str,
        session_id: Optional[str] = None
    ) -> NPCAgent:
        """
        初始化NPC智能体
        
        Args:
            npc_id: NPC ID
            session_id: 会话ID（可选）
            
        Returns:
            NPCAgent: NPC智能体实例
        """
        # 检查是否已存在
        if npc_id in self.agents:
            agent = self.agents[npc_id]
            self.logger.info(f"NPC智能体已存在: {npc_id}")
            
            # 如果提供了会话ID，激活到会话
            if session_id:
                await self.activate_npc(npc_id, session_id)
            
            return agent
        
        # 从数据库加载NPC数据
        npc_data = await self.entity_repository.get_by_id(npc_id)
        if not npc_data:
            raise ValueError(f"NPC不存在: {npc_id}")
        
        # 创建智能体
        agent = await create_npc_agent(
            npc_id=npc_id,
            npc_data=npc_data,
            model_scheduler=self.model_scheduler
        )
        
        # 存储智能体
        self.agents[npc_id] = agent
        
        # 激活到会话
        if session_id:
            await self.activate_npc(npc_id, session_id)
        
        self.logger.info(
            f"初始化NPC智能体: {npc_id} -> {agent.agent_id}"
        )
        
        return agent
    
    async def activate_npc(
        self,
        npc_id: str,
        session_id: str
    ) -> None:
        """
        激活NPC到会话
        
        Args:
            npc_id: NPC ID
            session_id: 会话ID
        """
        # 确保NPC已初始化
        if npc_id not in self.agents:
            await self.initialize_npc(npc_id)
        
        # 初始化会话字典
        if session_id not in self.active_agents:
            self.active_agents[session_id] = {}
        
        # 激活NPC到会话
        self.active_agents[session_id][npc_id] = self.agents[npc_id]
        
        self.logger.debug(
            f"激活NPC到会话: {npc_id} -> {session_id}"
        )
    
    async def deactivate_npc(
        self,
        npc_id: str,
        session_id: str
    ) -> None:
        """
        从会话停用NPC
        
        Args:
            npc_id: NPC ID
            session_id: 会话ID
        """
        if session_id in self.active_agents:
            self.active_agents[session_id].pop(npc_id, None)
            
            self.logger.debug(
                f"从会话停用NPC: {npc_id} <- {session_id}"
            )
    
    async def get_agent(
        self,
        npc_id: str
    ) -> Optional[NPCAgent]:
        """
        获取NPC智能体
        
        Args:
            npc_id: NPC ID
            
        Returns:
            Optional[NPCAgent]: NPC智能体实例
        """
        return self.agents.get(npc_id)
    
    async def get_session_npcs(
        self,
        session_id: str
    ) -> List[NPCAgent]:
        """
        获取会话中的所有NPC
        
        Args:
            session_id: 会话ID
            
        Returns:
            List[NPCAgent]: NPC智能体列表
        """
        return list(self.active_agents.get(session_id, {}).values())
    
    async def batch_initialize_npcs(
        self,
        npc_ids: List[str],
        session_id: str
    ) -> List[NPCAgent]:
        """
        批量初始化NPC
        
        Args:
            npc_ids: NPC ID列表
            session_id: 会话ID
            
        Returns:
            List[NPCAgent]: NPC智能体列表
        """
        import asyncio
        
        tasks = [
            self.initialize_npc(npc_id, session_id)
            for npc_id in npc_ids
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤异常
        agents = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(
                    f"第{i}个NPC初始化失败: {npc_ids[i]} - {result}"
                )
            else:
                agents.append(result)
        
        self.logger.info(
            f"批量初始化NPC: {len(agents)}/{len(npc_ids)} 成功"
        )
        
        return agents
    
    async def process_npc_interactions(
        self,
        session_id: str,
        tasks: List[DispatchedTask]
    ) -> Dict[str, NPCResponse]:
        """
        处理所有NPC交互
        
        Args:
            session_id: 会话ID
            tasks: 分发的任务列表
            
        Returns:
            Dict[str, NPCResponse]: NPC响应字典
        """
        import asyncio
        
        # 筛选需要NPC响应的任务
        npc_tasks = [
            task for task in tasks
            if task.requires_npc_response and task.target_npc_id
        ]
        
        if not npc_tasks:
            return {}
        
        # 获取会话中的NPC智能体
        session_npcs = await self.get_session_npcs(session_id)
        npc_agents_dict = {
            agent.npc_id: agent
            for agent in session_npcs
        }
        
        # 并发处理NPC交互
        npc_results = {}
        processing_tasks = []
        
        for task in npc_tasks:
            npc_id = task.target_npc_id
            if npc_id in npc_agents_dict:
                npc_agent = npc_agents_dict[npc_id]
                processing_tasks.append(
                    npc_agent.process_interaction(task)
                )
            else:
                self.logger.warning(
                    f"NPC智能体未找到: {npc_id}"
                )
        
        # 等待所有NPC响应
        results = await asyncio.gather(*processing_tasks, return_exceptions=True)
        
        # 收集结果
        for i, task in enumerate(npc_tasks):
            npc_id = task.target_npc_id
            if i < len(results):
                result = results[i]
                if isinstance(result, Exception):
                    self.logger.error(
                        f"NPC {npc_id} 交互处理失败: {result}"
                    )
                else:
                    npc_results[npc_id] = result
        
        self.logger.info(
            f"处理NPC交互: {len(npc_results)} 个响应"
        )
        
        return npc_results
    
    async def update_npc_memories(
        self,
        session_id: str,
        tasks: List[DispatchedTask],
        npc_responses: Dict[str, NPCResponse]
    ) -> None:
        """
        更新所有NPC记忆
        
        Args:
            session_id: 会话ID
            tasks: 分发的任务列表
            npc_responses: NPC响应字典
        """
        import asyncio
        
        # 获取会话中的NPC智能体
        session_npcs = await self.get_session_npcs(session_id)
        npc_agents_dict = {
            agent.npc_id: agent
            for agent in session_npcs
        }
        
        # 并发更新记忆
        update_tasks = []
        for npc_id, response in npc_responses.items():
            if npc_id in npc_agents_dict:
                npc_agent = npc_agents_dict[npc_id]
                update_tasks.append(
                    npc_agent.update_memory([], tasks, response)
                )
        
        if update_tasks:
            await asyncio.gather(*update_tasks, return_exceptions=True)
        
        self.logger.debug(
            f"更新NPC记忆: {len(update_tasks)} 个NPC"
        )
    
    async def cleanup_session(self, session_id: str) -> None:
        """
        清理会话
        
        Args:
            session_id: 会话ID
        """
        if session_id not in self.active_agents:
            return
        
        # 停止所有NPC
        session_npcs = self.active_agents[session_id]
        save_tasks = []
        
        for npc_agent in session_npcs.values():
            # 保存NPC记忆到数据库
            save_tasks.append(
                npc_agent.save_memory_to_database()
            )
        
        import asyncio
        await asyncio.gather(*save_tasks, return_exceptions=True)
        
        # 从会话移除
        del self.active_agents[session_id]
        
        self.logger.info(
            f"清理会话: {session_id} - "
            f"保存了{len(session_npcs)}个NPC的记忆"
        )
    
    async def shutdown_npc(self, npc_id: str) -> None:
        """
        关闭NPC智能体
        
        Args:
            npc_id: NPC ID
        """
        if npc_id not in self.agents:
            return
        
        # 关闭智能体
        agent = self.agents[npc_id]
        await agent.shutdown()
        
        # 从池中移除
        del self.agents[npc_id]
        
        # 从所有会话中移除
        for session_id, session_npcs in self.active_agents.items():
            if npc_id in session_npcs:
                del session_npcs[npc_id]
        
        self.logger.info(f"关闭NPC智能体: {npc_id}")
    
    async def shutdown_all(self) -> None:
        """关闭所有NPC智能体"""
        import asyncio
        
        # 保存所有NPC记忆
        save_tasks = []
        for agent in self.agents.values():
            save_tasks.append(agent.save_memory_to_database())
        
        if save_tasks:
            await asyncio.gather(*save_tasks, return_exceptions=True)
        
        # 关闭所有智能体
        shutdown_tasks = []
        for agent in self.agents.values():
            shutdown_tasks.append(agent.shutdown())
        
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        
        # 清空池
        self.agents.clear()
        self.active_agents.clear()
        
        self.logger.info("关闭所有NPC智能体")
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        获取池状态
        
        Returns:
            Dict: 池状态信息
        """
        return {
            'total_agents': len(self.agents),
            'active_sessions': len(self.active_agents),
            'session_details': {
                session_id: {
                    'npc_count': len(npcs),
                    'npc_ids': list(npcs.keys())
                }
                for session_id, npcs in self.active_agents.items()
            }
        }


# ==================== 工厂函数 ====================

def create_npc_pool(
    entity_repository: IEntityRepository,
    model_scheduler: ProviderManager
) -> NPCAgentPool:
    """
    创建NPC智能体池实例
    
    Args:
        entity_repository: 实体仓库
        model_scheduler: 模型调度器
        
    Returns:
        NPCAgentPool: NPC智能体池实例
    """
    return NPCAgentPool(
        entity_repository=entity_repository,
        model_scheduler=model_scheduler
    )