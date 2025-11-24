"""
推理引擎工厂和多种推理模式实现
"""

import asyncio
import time
import uuid
from typing import Dict, List, Optional, Any, Type
from dataclasses import dataclass, field
import logging

from .interfaces import (
    IReasoningEngine, IReasoningEngineFactory, IAgent, IToolManager,
    ReasoningMode, ReasoningResult, EngineInfo, ExecutionContext,
    ThoughtNode
)
from model_adapter import ModelScheduler, RequestContext, ChatMessage

class ReasoningEngineFactory(IReasoningEngineFactory):
    """推理引擎工厂实现"""
    
    def __init__(self):
        self._engines: Dict[str, Type[IReasoningEngine]] = {}
        self.logger = logging.getLogger(__name__)
        
        # 注册默认引擎
        self._register_default_engines()
    
    def register_engine(self, name: str, engine_class: Type[IReasoningEngine]) -> None:
        """注册推理引擎"""
        self._engines[name] = engine_class
        self.logger.info(f"推理引擎 {name} 注册成功")
    
    def create_engine(self, mode: ReasoningMode, config: Dict[str, Any]) -> IReasoningEngine:
        """创建推理引擎实例"""
        engine_name = mode.value
        if engine_name not in self._engines:
            raise ValueError(f"不支持的推理模式: {engine_name}")
        
        engine_class_or_path = self._engines[engine_name]
        
        # 处理字符串路径导入
        if isinstance(engine_class_or_path, str):
            # 动态导入类
            module_path, class_name = engine_class_or_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            engine_class = getattr(module, class_name)
        else:
            engine_class = engine_class_or_path
        
        engine = engine_class()
        
        # 使用公共方法设置配置，遵循封装原则
        engine.set_config(config)
        
        self.logger.info(f"创建推理引擎: {engine_name}")
        return engine
    
    def list_available_engines(self) -> List[str]:
        """列出可用的推理引擎"""
        return list(self._engines.keys())
    
    def _register_default_engines(self) -> None:
        """注册默认推理引擎"""
        # 使用字符串延迟导入，避免前向引用问题
        self.register_engine("chain_of_thought", "agent_orchestration.reasoning.ChainOfThoughtEngine")
        self.register_engine("tree_of_thought", "agent_orchestration.reasoning.TreeOfThoughtEngine")
        self.register_engine("graph_of_thought", "agent_orchestration.reasoning.GraphOfThoughtEngine")
        self.register_engine("algorithm_of_thoughts", "agent_orchestration.reasoning.AlgorithmOfThoughtsEngine")
        self.register_engine("skeleton_of_thought", "agent_orchestration.reasoning.SkeletonOfThoughtEngine")
        self.register_engine("react", "agent_orchestration.reasoning.ReactReasoningEngine")

class BaseReasoningEngine(IReasoningEngine):
    """基础推理引擎"""
    
    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.model_scheduler: Optional[ModelScheduler] = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self._initialized = False
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """设置引擎配置"""
        self.config = config
    
    async def initialize(self, config: Dict[str, Any] = None) -> None:
        """初始化推理引擎"""
        if self._initialized:
            return
        
        if config is None:
            config = self.config
            
        self.config = config
        # 这里可以根据需要初始化模型调度器
        self._initialized = True
        self.logger.info(f"{self.__class__.__name__} 初始化完成")
    
    async def cleanup(self) -> None:
        """清理资源"""
        self.logger.info(f"{self.__class__.__name__} 清理完成")
    
    @property
    def engine_info(self) -> EngineInfo:
        """返回引擎信息"""
        return EngineInfo(
            name=self.__class__.__name__,
            version="1.0.0",
            description=self.__doc__ or "",
            supported_modes=self._get_supported_modes(),
            capabilities=self._get_capabilities()
        )
    
    def _get_supported_modes(self) -> List[ReasoningMode]:
        """获取支持的推理模式"""
        return []
    
    def _get_capabilities(self) -> List[str]:
        """获取引擎能力"""
        return ["basic_reasoning"]

class ChainOfThoughtEngine(BaseReasoningEngine):
    """思维链推理引擎"""
    
    async def process(
        self, 
        agent: IAgent, 
        context: ExecutionContext, 
        tools: IToolManager
    ) -> ReasoningResult:
        """执行思维链推理"""
        start_time = time.time()
        thoughts = []
        
        try:
            # 获取初始思考
            current_thought = await self._initial_thought(context)
            thoughts.append(current_thought)
            
            max_steps = self.config.get("max_steps", 10)
            step_timeout = self.config.get("step_timeout", 30)
            
            for step in range(max_steps):
                # 检查是否为最终思考
                if self._is_final_thought(current_thought):
                    break
                
                # 记录每步的开始时间
                step_start_time = time.time()
                
                # 生成下一步思考
                next_thought = await self._generate_next_thought(
                    agent, current_thought, tools, context
                )
                
                thoughts.append(next_thought)
                current_thought = next_thought
                
                # 检查每步的执行时间是否超过step_timeout
                if time.time() - step_start_time > step_timeout:
                    self.logger.warning(f"步骤 {step+1} 超时，停止推理")
                    break
            
            # 构建最终答案
            final_answer = await self._generate_final_answer(thoughts, context)
            reasoning_path = [f"步骤{i+1}: {thought}" for i, thought in enumerate(thoughts)]
            
            return ReasoningResult(
                thoughts=thoughts,
                final_answer=final_answer,
                reasoning_path=reasoning_path,
                execution_time=time.time() - start_time,
                success=True
            )
            
        except Exception as e:
            return ReasoningResult(
                thoughts=thoughts,
                final_answer="",
                reasoning_path=[],
                execution_time=time.time() - start_time,
                success=False,
                error_message=str(e)
            )
    
    def _get_supported_modes(self) -> List[ReasoningMode]:
        return [ReasoningMode.COT]
    
    def _get_capabilities(self) -> List[str]:
        return ["linear_reasoning", "step_by_step"]
    
    async def _initial_thought(self, context: ExecutionContext) -> str:
        """生成初始思考"""
        return f"让我分析这个任务: {context.task_id}"
    
    async def _generate_next_thought(
        self, 
        agent: IAgent, 
        current_thought: str, 
        tools: IToolManager,
        context: ExecutionContext
    ) -> str:
        """生成下一步思考"""
        # 这里应该调用模型生成下一步思考
        # 暂时返回模拟思考
        return f"基于 '{current_thought}'，我需要进一步分析..."
    
    def _is_final_thought(self, thought: str) -> bool:
        """判断是否为最终思考"""
        # 从配置中获取最终判断关键词，如果没有配置则使用默认值
        final_keywords = self.config.get("final_keywords", ["最终答案", "结论", "完成", "解决"])
        return any(keyword in thought for keyword in final_keywords)
    
    async def _generate_final_answer(self, thoughts: List[str], context: ExecutionContext) -> str:
        """生成最终答案"""
        return f"基于以上思考，我的结论是: {thoughts[-1] if thoughts else '无法得出结论'}"

class TreeOfThoughtEngine(BaseReasoningEngine):
    """思维树推理引擎"""
    
    async def process(
        self, 
        agent: IAgent, 
        context: ExecutionContext, 
        tools: IToolManager
    ) -> ReasoningResult:
        """执行思维树推理"""
        start_time = time.time()
        
        try:
            # 创建思考树
            thought_tree = ThoughtTree()
            root_thought = await self._initial_thought(context)
            thought_tree.add_root(root_thought)
            
            max_depth = self.config.get("max_depth", 5)
            max_branches = self.config.get("max_branches", 3)
            
            current_level = [root_thought]
            
            for depth in range(max_depth):
                next_level = []
                
                for thought in current_level:
                    # 生成多个分支
                    branches = await self._generate_branches(
                        agent, thought, tools, context, max_branches
                    )
                    
                    for branch in branches:
                        thought_tree.add_child(thought, branch)
                        next_level.append(branch)
                
                # 评估和剪枝
                current_level = await self._evaluate_and_prune(next_level)
                
                if self._should_stop(current_level):
                    break
            
            # 找到最佳路径
            best_path = thought_tree.find_best_path()
            final_answer = await self._generate_final_answer(best_path, context)
            reasoning_path = [node.content for node in best_path]
            
            return ReasoningResult(
                thoughts=reasoning_path,
                final_answer=final_answer,
                reasoning_path=reasoning_path,
                execution_time=time.time() - start_time,
                success=True
            )
            
        except Exception as e:
            return ReasoningResult(
                thoughts=[],
                final_answer="",
                reasoning_path=[],
                execution_time=time.time() - start_time,
                success=False,
                error_message=str(e)
            )
    
    def _get_supported_modes(self) -> List[ReasoningMode]:
        return [ReasoningMode.TOT]
    
    def _get_capabilities(self) -> List[str]:
        return ["branching_reasoning", "parallel_exploration"]
    
    async def _initial_thought(self, context: ExecutionContext) -> ThoughtNode:
        """生成初始思考节点"""
        content = f"分析任务: {context.task_id}"
        return ThoughtNode(content=content, confidence=0.8)
    
    async def _generate_branches(
        self, 
        agent: IAgent, 
        parent_thought: ThoughtNode, 
        tools: IToolManager,
        context: ExecutionContext,
        max_branches: int
    ) -> List[ThoughtNode]:
        """生成思考分支"""
        branches = []
        for i in range(max_branches):
            content = f"基于 '{parent_thought.content}' 的分支思考 {i+1}"
            confidence = 0.7 - (i * 0.1)  # 递减置信度
            branches.append(ThoughtNode(content=content, confidence=confidence))
        return branches
    
    async def _evaluate_and_prune(self, thoughts: List[ThoughtNode]) -> List[ThoughtNode]:
        """评估和剪枝"""
        # 按置信度排序并保留前N个
        thoughts.sort(key=lambda x: x.confidence, reverse=True)
        # 重命名为confidence_threshold，更准确地反映其用途
        max_keep = self.config.get("confidence_threshold", 0.3)
        return [t for t in thoughts if t.confidence >= max_keep]
    
    def _should_stop(self, thoughts: List[ThoughtNode]) -> bool:
        """判断是否应该停止"""
        if not thoughts:
            return True
        return thoughts[0].confidence >= 0.9
    
    async def _generate_final_answer(self, path: List[ThoughtNode], context: ExecutionContext) -> str:
        """生成最终答案"""
        if not path:
            return "无法得出结论"
        return f"基于最佳路径分析: {path[-1].content}"

class ThoughtTree:
    """思考树"""
    
    def __init__(self):
        self.nodes: Dict[str, ThoughtNode] = {}
        self.root: Optional[ThoughtNode] = None
    
    def add_root(self, root: ThoughtNode) -> None:
        """添加根节点"""
        # 为节点生成唯一ID
        root.id = str(uuid.uuid4())
        self.root = root
        self.nodes[root.id] = root
        # 同时使用内容作为键，方便测试查找
        self.nodes[root.content] = root
    
    def add_child(self, parent: ThoughtNode, child: ThoughtNode) -> None:
        """添加子节点"""
        # 为节点生成唯一ID
        child.id = str(uuid.uuid4())
        child.parent = parent
        parent.children.append(child)
        self.nodes[child.id] = child
        # 同时使用内容作为键，方便测试查找
        self.nodes[child.content] = child
    
    def find_best_path(self) -> List[ThoughtNode]:
        """找到最佳路径"""
        if not self.root:
            return []
        
        def dfs(node: ThoughtNode, path: List[ThoughtNode]) -> List[ThoughtNode]:
            path.append(node)
           
            if not node.children:
                return path.copy()
           
            best_child = max(node.children, key=lambda x: x.confidence)
            return dfs(best_child, path)
        
        return dfs(self.root, [])

class GraphOfThoughtEngine(BaseReasoningEngine):
    """思维图推理引擎"""
    
    def _get_supported_modes(self) -> List[ReasoningMode]:
        return [ReasoningMode.GOT]
    
    def _get_capabilities(self) -> List[str]:
        return ["graph_reasoning", "complex_dependencies"]
    
    async def process(
        self, 
        agent: IAgent, 
        context: ExecutionContext, 
        tools: IToolManager
    ) -> ReasoningResult:
        """执行思维图推理"""
        # 简化实现，实际应该构建图结构
        return await super().process(agent, context, tools)

class AlgorithmOfThoughtsEngine(BaseReasoningEngine):
    """算法化思维推理引擎"""
    
    def _get_supported_modes(self) -> List[ReasoningMode]:
        return [ReasoningMode.AOT]
    
    def _get_capabilities(self) -> List[str]:
        return ["algorithmic_reasoning", "deterministic"]
    
    async def process(
        self, 
        agent: IAgent, 
        context: ExecutionContext, 
        tools: IToolManager
    ) -> ReasoningResult:
        """执行算法化思维推理"""
        # 简化实现，实际应该执行算法化推理
        return await super().process(agent, context, tools)

class SkeletonOfThoughtEngine(BaseReasoningEngine):
    """框架式思维推理引擎"""
    
    def _get_supported_modes(self) -> List[ReasoningMode]:
        return [ReasoningMode.SOT]
    
    def _get_capabilities(self) -> List[str]:
        return ["structured_reasoning", "outline_first"]
    
    async def process(
        self, 
        agent: IAgent, 
        context: ExecutionContext, 
        tools: IToolManager
    ) -> ReasoningResult:
        """执行框架式思维推理"""
        start_time = time.time()
        thoughts = []
        
        try:
            # 1. 构建大纲
            outline = await self._build_outline(context)
            thoughts.append(f"大纲: {outline}")
            
            # 2. 填充细节
            details = await self._fill_details(outline, context)
            thoughts.append(f"细节: {details}")
            
            # 3. 生成最终答案
            final_answer = await self._generate_final_answer(outline, details, context)
            
            return ReasoningResult(
                thoughts=thoughts,
                final_answer=final_answer,
                reasoning_path=thoughts,
                execution_time=time.time() - start_time,
                success=True
            )
            
        except Exception as e:
            return ReasoningResult(
                thoughts=thoughts,
                final_answer="",
                reasoning_path=[],
                execution_time=time.time() - start_time,
                success=False,
                error_message=str(e)
            )
    
    async def _build_outline(self, context: ExecutionContext) -> str:
        """构建大纲"""
        outline_depth = self.config.get("outline_depth", 3)
        return f"1. 问题分析\n2. 解决方案\n3. 结论"
    
    async def _fill_details(self, outline: str, context: ExecutionContext) -> str:
        """填充细节"""
        detail_ratio = self.config.get("detail_ratio", 0.7)
        return f"基于大纲的详细分析..."
    
    async def _generate_final_answer(self, outline: str, details: str, context: ExecutionContext) -> str:
        """生成最终答案"""
        return f"综合大纲和细节的最终答案: {outline} + {details}"

class ReactReasoningEngine(BaseReasoningEngine):
    """ReAct推理引擎"""
    
    def _get_supported_modes(self) -> List[ReasoningMode]:
        return [ReasoningMode.REACT]
    
    def _get_capabilities(self) -> List[str]:
        return ["react_reasoning", "tool_integration"]
    
    async def process(
        self, 
        agent: IAgent, 
        context: ExecutionContext, 
        tools: IToolManager
    ) -> ReasoningResult:
        """执行ReAct推理"""
        # 这里可以集成现有的ReAct实现
        # 暂时返回基本实现
        return await super().process(agent, context, tools)

# 全局推理引擎工厂实例（使用单例模式避免状态污染）
_reasoning_engine_factory = None

def get_reasoning_engine_factory() -> ReasoningEngineFactory:
    """获取推理引擎工厂实例（单例模式）"""
    global _reasoning_engine_factory
    if _reasoning_engine_factory is None:
        _reasoning_engine_factory = ReasoningEngineFactory()
    return _reasoning_engine_factory

async def create_reasoning_engine(mode: ReasoningMode, config: Dict[str, Any]) -> IReasoningEngine:
    """创建推理引擎"""
    factory = get_reasoning_engine_factory()
    return factory.create_engine(mode, config)