"""
智能体编排框架核心实现
"""

import asyncio
import time
import uuid
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
import logging

from .interfaces import (
    IAgent, ITool, IOrchestrator, ICommunicator,
    AgentMessage, MessageType, AgentCapabilities, AgentStatus,
    ExecutionContext, ToolSchema, ToolParameter, AgentConfig,
    ReasoningMode, ExecutionConfig, ExecutionResult,
    IReasoningEngine, IToolManager, IExecutionEngine,
    IConfigurationManager, IReasoningEngineFactory
)
from .react import ReActExecutor, ReActConfig
from .communication import AgentCommunicator
from .config import ConfigurationManager
from .reasoning import ReasoningEngineFactory
from .execution import ExecutionEngine
from .tools import ToolManager
from model_adapter import ModelScheduler, RequestContext, ChatMessage

class BaseAgent(IAgent):
    """基础智能体实现"""
    
    def __init__(self,
                 agent_id: str,
                 config: Optional[AgentConfig] = None,
                 model_scheduler: Optional[ModelScheduler] = None,
                 tool_manager: Optional[ToolManager] = None,
                 reasoning_engine_factory: Optional[IReasoningEngineFactory] = None,
                 execution_engine: Optional[IExecutionEngine] = None,
                 config_manager: Optional[IConfigurationManager] = None,
                 communicator: Optional[ICommunicator] = None,
                 capabilities: Optional[AgentCapabilities] = None,
                 system_prompt: Optional[str] = None):
        self._agent_id = agent_id
        self.config = config
        self.model_scheduler = model_scheduler
        self.tool_manager = tool_manager
        self.reasoning_engine_factory = reasoning_engine_factory
        self.execution_engine = execution_engine
        self.config_manager = config_manager
        self.communicator = communicator
        self._capabilities = capabilities or AgentCapabilities()
        self._status = AgentStatus.IDLE
        
        # 初始化各个组件
        self._init_system_prompt(system_prompt, agent_id)
        self._init_reasoning_engine()
        self._init_react_executor(model_scheduler, tool_manager)
        self._init_execution_history()
        self._init_message_processing()
        
        self.logger = logging.getLogger(f"{__name__}.{agent_id}")
    
    def _init_system_prompt(self, system_prompt: Optional[str], agent_id: str) -> None:
        """初始化系统提示"""
        if system_prompt:
            self.system_prompt = system_prompt
        elif self.config and hasattr(self.config, 'system_prompt'):
            self.system_prompt = self.config.system_prompt
        else:
            self.system_prompt = f"你是一个智能助手，ID为 {agent_id}。"
    
    def _init_reasoning_engine(self) -> None:
        """初始化推理引擎"""
        self.reasoning_engine: Optional[IReasoningEngine] = None
    
    def _init_react_executor(self, model_scheduler: Optional[ModelScheduler],
                           tool_manager: Optional[ToolManager]) -> None:
        """初始化ReAct执行器"""
        self.react_executor = None
        if model_scheduler and tool_manager:
            # 获取工具字典
            tools_dict = self._get_tools_dict(tool_manager)
            
            self.react_executor = ReActExecutor(
                model_scheduler=model_scheduler,
                tools=tools_dict,
                config=ReActConfig()
            )
    
    def _get_tools_dict(self, tool_manager: IToolManager) -> Dict[str, ITool]:
        """获取工具字典"""
        tools_dict = {}
        if hasattr(tool_manager, 'tools'):
            # 确保返回的是工具对象而不是字典
            for tool_name, tool_info in tool_manager.tools.items():
                if isinstance(tool_info, dict) and 'tool' in tool_info:
                    tools_dict[tool_name] = tool_info['tool']
                else:
                    tools_dict[tool_name] = tool_info
        elif hasattr(tool_manager, '_tools'):
            # 确保返回的是工具对象而不是字典
            for tool_name, tool_info in tool_manager._tools.items():
                if isinstance(tool_info, dict) and 'tool' in tool_info:
                    tools_dict[tool_name] = tool_info['tool']
                else:
                    tools_dict[tool_name] = tool_info
        else:
            # 尝试通过list_tools方法获取工具
            try:
                tool_infos = tool_manager.list_tools()
                for tool_info in tool_infos:
                    if hasattr(tool_info, 'name') and hasattr(tool_info, 'tool'):
                        tools_dict[tool_info.name] = tool_info.tool
                    elif hasattr(tool_info, 'name'):
                        # 如果tool_info本身就是工具对象
                        tools_dict[tool_info.name] = tool_info
            except Exception as e:
                self.logger.warning(f"Failed to get tools from tool_manager: {e}")
        return tools_dict
    
    def _init_execution_history(self) -> None:
        """初始化执行历史"""
        self.execution_history: List[Dict[str, Any]] = []
    
    def _init_message_processing(self) -> None:
        """初始化消息处理"""
        self._message_task: Optional[asyncio.Task] = None
        self._running = False
    
    @property
    def agent_id(self) -> str:
        return self._agent_id
    
    @property
    def capabilities(self) -> AgentCapabilities:
        return self._capabilities
    
    @property
    def status(self) -> AgentStatus:
        return self._status
    
    async def initialize(self) -> None:
        """初始化智能体"""
        if self._running:
            return
        
        self._running = True
        self._status = AgentStatus.IDLE
        
        # 从配置管理器加载配置
        if self.config_manager and not self.config:
            try:
                self.config = await self.config_manager.load_config(self._agent_id)
                self.logger.info(f"从配置管理器加载配置: {self._agent_id}")
            except Exception as e:
                self.logger.warning(f"加载配置失败，使用默认配置: {e}")
        
        # 初始化推理引擎
        if self.config and self.reasoning_engine_factory:
            reasoning_mode = self.config.reasoning_mode
            reasoning_config = self.config.reasoning_config
            self.reasoning_engine = self.reasoning_engine_factory.create_engine(
                reasoning_mode, reasoning_config
            )
            self.logger.info(f"初始化推理引擎: {reasoning_mode.value}")
        
        # 注册到通信器
        if self.communicator:
            await self.communicator.register_agent(self.agent_id)
            
            # 订阅相关消息类型
            await self.communicator.subscribe(
                self.agent_id,
                [MessageType.REQUEST, MessageType.RESPONSE, MessageType.NOTIFICATION]
            )
            
            # 启动消息处理任务
            self._message_task = asyncio.create_task(self._message_processing_loop())
        
        self.logger.info(f"Agent {self.agent_id} initialized")
    
    async def shutdown(self) -> None:
        """关闭智能体"""
        if not self._running:
            return
        
        self._running = False
        self._status = AgentStatus.IDLE
        
        # 停止消息处理任务
        if self._message_task:
            self._message_task.cancel()
            try:
                await self._message_task
            except asyncio.CancelledError:
                pass
        
        # 从通信器注销
        if self.communicator:
            await self.communicator.unregister_agent(self.agent_id)
        
        self.logger.info(f"Agent {self.agent_id} shutdown")
    
    async def process_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """处理接收到的消息"""
        try:
            self._status = AgentStatus.PROCESSING
            
            if message.message_type == MessageType.REQUEST:
                # 处理请求消息
                result = await self.execute_task(
                    task=str(message.content),
                    context=ExecutionContext(
                        task_id=message.correlation_id or str(uuid.uuid4()),
                        metadata=message.metadata
                    )
                )
                
                # 返回响应
                response = AgentMessage(
                    sender_id=self.agent_id,
                    receiver_id=message.sender_id,
                    message_type=MessageType.RESPONSE,
                    content=result,
                    correlation_id=message.correlation_id
                )
                
                return response
            
            elif message.message_type == MessageType.NOTIFICATION:
                # 处理通知消息
                self.logger.info(f"Received notification: {message.content}")
                return None
            
            else:
                self.logger.warning(f"Unhandled message type: {message.message_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            
            # 返回错误消息
            error_response = AgentMessage(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                message_type=MessageType.ERROR,
                content=f"处理消息时发生错误: {str(e)}",
                correlation_id=message.correlation_id
            )
            
            return error_response
        
        finally:
            self._status = AgentStatus.IDLE
    
    async def execute_task(self, task: str, context: Optional[ExecutionContext] = None) -> Any:
        """执行任务"""
        start_time = time.time()
        
        try:
            self._status = AgentStatus.PROCESSING
            
            # 创建执行上下文
            if not context:
                context = ExecutionContext(
                    task_id=str(uuid.uuid4()),
                    metadata={"task": task}
                )
            
            # 记录执行开始
            execution_record = {
                "task": task,
                "context": context,
                "start_time": start_time,
                "status": "running"
            }
            
            # 选择执行策略
            if self.reasoning_engine and self.tool_manager and self._capabilities.can_use_tools:
                # 使用新的推理引擎
                result = await self._execute_with_reasoning_engine(task, context)
            elif self.react_executor and self.tool_manager and self._capabilities.can_use_tools:
                # 使用ReAct执行器（向后兼容）
                result = await self._execute_with_react(task, context)
            elif self.execution_engine:
                # 使用执行引擎
                execution_config = ExecutionConfig(
                    resource_requirements=self._get_resource_requirements(),
                    timeout=self.config.max_execution_time if self.config else 300.0
                )
                execution_result = await self.execution_engine.execute_agent(
                    self, context, execution_config
                )
                result = execution_result.result if execution_result.success else execution_result.error_message
            else:
                # 基本执行
                result = await self._execute_without_tools(task, context)
            
            # 记录执行结果
            execution_record.update({
                "end_time": time.time(),
                "duration": time.time() - start_time,
                "status": "completed",
                "result": result
            })
            
            self.execution_history.append(execution_record)
            self.logger.info(f"Task completed in {time.time() - start_time:.2f}s")
            
            # 重置状态为IDLE
            self._status = AgentStatus.IDLE
            
            return result
            
        except Exception as e:
            # 记录执行失败
            execution_record.update({
                "end_time": time.time(),
                "duration": time.time() - start_time,
                "status": "failed",
                "error": str(e)
            })
            
            self.execution_history.append(execution_record)
            self.logger.error(f"Task failed: {e}")
            raise
    
    async def _execute_with_reasoning_engine(self, task: str, context: ExecutionContext) -> Any:
        """使用推理引擎执行任务"""
        if not self.reasoning_engine:
            raise RuntimeError("推理引擎未初始化")
        
        reasoning_result = await self.reasoning_engine.process(
            self, context, self.tool_manager
        )
        
        if reasoning_result.success:
            return reasoning_result.final_answer
        else:
            raise Exception(f"推理引擎执行失败: {reasoning_result.error_message}")
    
    async def _execute_with_react(self, task: str, context: Optional[ExecutionContext]) -> Any:
        """使用ReAct执行任务"""
        if not self.react_executor:
            raise RuntimeError("ReAct执行器未初始化")
        
        history = []
        if context and context.parent_task_id:
            # 获取相关历史记录
            history = [record["result"] for record in self.execution_history
                      if record.get("context", {}).get("task_id") == context.parent_task_id
                      and record.get("status") == "completed"]
        
        result = await self.react_executor.execute(task, context, history)
        
        if result.success:
            return result.final_answer
        else:
            raise Exception(f"ReAct执行失败: {result.error_message}")
    
    def _get_resource_requirements(self) -> Dict[str, Any]:
        """获取资源需求"""
        if self.config:
            return {
                "cpu_cores": 1.0,
                "memory_mb": self.config.max_memory_usage // 4,  # 使用1/4的内存
                "timeout": self.config.max_execution_time
            }
        else:
            return {
                "cpu_cores": 1.0,
                "memory_mb": 512,
                "timeout": 300.0
            }
    
    async def _execute_without_tools(self, task: str, context: Optional[ExecutionContext]) -> Any:
        """不使用工具执行任务"""
        messages = []
        
        # 添加系统提示
        if self.system_prompt:
            messages.append(ChatMessage(role='system', content=self.system_prompt))
        
        # 添加任务
        messages.append(ChatMessage(role='user', content=task))
        
        # 调用模型
        request_context = RequestContext(
            messages=messages,
            max_tokens=self.config.max_tokens if self.config else 2000,
            temperature=self.config.temperature if self.config else 0.7
        )
        
        response = await self.model_scheduler.chat(request_context)
        
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
        else:
            raise Exception("模型响应为空")
    
    async def send_message(self, receiver_id: str, content: Any, 
                          message_type: MessageType = MessageType.REQUEST,
                          metadata: Optional[Dict[str, Any]] = None) -> None:
        """发送消息"""
        if not self.communicator:
            raise RuntimeError("Communicator not available")
        
        message = AgentMessage(
            sender_id=self.agent_id,
            receiver_id=receiver_id,
            message_type=message_type,
            content=content,
            metadata=metadata or {}
        )
        
        await self.communicator.send_message(message)
    
    async def broadcast_message(self, content: Any, 
                               message_type: MessageType = MessageType.NOTIFICATION,
                               metadata: Optional[Dict[str, Any]] = None) -> None:
        """广播消息"""
        if not self.communicator:
            raise RuntimeError("Communicator not available")
        
        message = AgentMessage(
            sender_id=self.agent_id,
            receiver_id="*",  # 广播标识
            message_type=message_type,
            content=content,
            metadata=metadata or {}
        )
        
        await self.communicator.broadcast_message(message)
    
    async def _message_processing_loop(self) -> None:
        """消息处理循环"""
        while self._running:
            try:
                if self.communicator:
                    message = await self.communicator.receive_message(self.agent_id, timeout=1.0)
                    if message:
                        # 异步处理消息，添加异常处理
                        task = asyncio.create_task(self._handle_message_async(message))
                        task.add_done_callback(self._handle_message_exception)
                
                # 使用更短的等待时间提高响应速度
                await asyncio.sleep(0.01)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Message processing loop error: {e}")
                await asyncio.sleep(1.0)
    
    async def _handle_message_async(self, message: AgentMessage) -> None:
        """异步处理消息"""
        try:
            response = await self.process_message(message)
            if response and self.communicator:
                await self.communicator.send_message(response)
        except Exception as e:
            self.logger.error(f"Async message handling error: {e}")
    
    def _handle_message_exception(self, task: asyncio.Task) -> None:
        """处理异步消息任务的异常"""
        if not task.cancelled() and task.exception():
            try:
                # 重新抛出异常以记录详细信息
                task.result()
            except Exception as e:
                self.logger.error(f"Unhandled exception in async message task: {e}")
    
    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self.execution_history[-limit:]

class Orchestrator(IOrchestrator):
    """编排器实现"""
    
    def __init__(self, communicator: Optional[ICommunicator] = None):
        self.agents: Dict[str, IAgent] = {}
        self.communicator = communicator or AgentCommunicator()
        self.logger = logging.getLogger(__name__)
    
    async def register_agent(self, agent: IAgent) -> None:
        """注册智能体"""
        await agent.initialize()
        self.agents[agent.agent_id] = agent
        self.logger.info(f"Agent {agent.agent_id} registered with orchestrator")
    
    async def unregister_agent(self, agent_id: str) -> None:
        """注销智能体"""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            await agent.shutdown()
            del self.agents[agent_id]
            self.logger.info(f"Agent {agent_id} unregistered from orchestrator")
    
    async def get_agent(self, agent_id: str) -> Optional[IAgent]:
        """获取智能体"""
        return self.agents.get(agent_id)
    
    async def list_agents(self) -> List[IAgent]:
        """列出所有智能体"""
        return list(self.agents.values())
    
    async def coordinate_agents(self, task: str, agent_ids: List[str], 
                               context: Optional[ExecutionContext] = None) -> Any:
        """协调多个智能体执行任务"""
        if not agent_ids:
            raise ValueError("No agent IDs provided")
        
        # 验证智能体存在
        missing_agents = [aid for aid in agent_ids if aid not in self.agents]
        if missing_agents:
            raise ValueError(f"Agents not found: {missing_agents}")
        
        # 简单的协调策略：第一个智能体执行主任务，其他智能体作为辅助
        primary_agent_id = agent_ids[0]
        primary_agent = self.agents[primary_agent_id]
        
        # 创建执行上下文
        if not context:
            context = ExecutionContext(
                task_id=str(uuid.uuid4()),
                metadata={"coordinated_agents": agent_ids}
            )
        
        # 执行主任务
        result = await primary_agent.execute_task(task, context)
        
        return result
    
    async def execute_workflow(self, workflow: Dict[str, Any], 
                              context: Optional[ExecutionContext] = None) -> Any:
        """执行工作流"""
        # 简单的工作流实现
        # 工作流格式: {"steps": [{"agent": "agent_id", "task": "task_description"}, ...]}
        
        steps = workflow.get("steps", [])
        if not steps:
            raise ValueError("Workflow has no steps")
        
        results = []
        
        for i, step in enumerate(steps):
            agent_id = step.get("agent")
            task = step.get("task")
            
            if not agent_id or not task:
                raise ValueError(f"Invalid step {i}: missing agent or task")
            
            agent = await self.get_agent(agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")
            
            # 创建步骤上下文
            step_context = ExecutionContext(
                task_id=f"{context.task_id if context else 'workflow'}_step_{i}",
                parent_task_id=context.task_id if context else None,
                metadata={"step_index": i, "total_steps": len(steps)}
            )
            
            # 执行步骤
            result = await agent.execute_task(task, step_context)
            results.append(result)
        
        return results

# 便捷函数
async def create_agent(
    agent_id: str,
    config: Optional[AgentConfig] = None,
    model_scheduler: Optional[ModelScheduler] = None,
    tool_manager: Optional[IToolManager] = None,
    reasoning_engine_factory: Optional[IReasoningEngineFactory] = None,
    execution_engine: Optional[IExecutionEngine] = None,
    config_manager: Optional[IConfigurationManager] = None,
    communicator: Optional[ICommunicator] = None,
    capabilities: Optional[AgentCapabilities] = None,
    system_prompt: Optional[str] = None
) -> BaseAgent:
    """创建智能体实例"""
    return BaseAgent(
        agent_id=agent_id,
        config=config,
        model_scheduler=model_scheduler,
        tool_manager=tool_manager,
        reasoning_engine_factory=reasoning_engine_factory,
        execution_engine=execution_engine,
        config_manager=config_manager,
        communicator=communicator,
        capabilities=capabilities,
        system_prompt=system_prompt
    )

async def create_orchestrator(communicator: Optional[ICommunicator] = None) -> Orchestrator:
    """创建编排器实例"""
    return Orchestrator(communicator)