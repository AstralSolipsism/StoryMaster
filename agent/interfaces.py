"""
智能体编排框架核心接口和数据结构
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, AsyncIterable, Union, Type, TYPE_CHECKING, Tuple
from enum import Enum
from datetime import datetime

if TYPE_CHECKING:
    # 前向引用的类型
    pass

# ==================== 基础枚举 ====================

class MessageType(Enum):
    """消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"

class ReActStepType(Enum):
    """ReAct步骤类型"""
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    FINAL_ANSWER = "final_answer"

class AgentStatus(Enum):
    """智能体状态"""
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING = "waiting"
    ERROR = "error"

class ReasoningMode(Enum):
    """推理模式"""
    COT = "chain_of_thought"  # 思维链
    TOT = "tree_of_thought"   # 思维树
    GOT = "graph_of_thought"  # 思维图
    AOT = "algorithm_of_thoughts"  # 算法化思维
    SOT = "skeleton_of_thought"    # 框架式思维
    REACT = "react"            # ReAct模式

class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

# ==================== 工具相关数据结构 ====================

@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str  # 'string', 'number', 'boolean', 'array', 'object'
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None  # 可选值列表

@dataclass
class ToolSchema:
    """工具模式定义"""
    name: str
    description: str
    parameters: List[ToolParameter]
    returns: Optional[str] = None  # 返回值类型描述

@dataclass
class ToolCall:
    """工具调用"""
    tool_name: str
    parameters: Dict[str, Any]
    call_id: Optional[str] = None
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

@dataclass
class ToolResult:
    """工具执行结果"""
    tool_name: str
    result: Any
    success: bool = True
    error_message: Optional[str] = None
    call_id: Optional[str] = None
    execution_time: float = 0.0

# ==================== 智能体相关数据结构 ====================

@dataclass
class AgentCapabilities:
    """智能体能力描述"""
    can_use_tools: bool = True
    can_communicate: bool = True
    can_execute_tasks: bool = True
    supported_task_types: List[str] = field(default_factory=list)
    max_concurrent_tasks: int = 1

@dataclass
class AgentMessage:
    """智能体间消息"""
    sender_id: str
    receiver_id: str
    message_type: MessageType
    content: Any
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExecutionContext:
    """执行上下文"""
    task_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=lambda: datetime.now().timestamp())
    max_iterations: int = 10
    timeout: float = 300.0  # 5分钟

# ==================== Agent配置相关数据结构 ====================

@dataclass
class AgentConfig:
    """Agent配置"""
    # 基础配置
    agent_id: str
    agent_type: str
    version: str
    
    # 推理配置
    reasoning_mode: ReasoningMode
    reasoning_config: Dict[str, Any]
    
    # 工具配置
    enabled_tools: List[str]
    tool_config: Dict[str, Dict[str, Any]]
    
    # 性能配置
    max_execution_time: float
    max_memory_usage: int
    concurrency_limit: int
    
    # 模型配置
    max_tokens: int = 2000
    temperature: float = 0.7
    system_prompt: Optional[str] = None
    
    # 个性化配置
    personality: Optional[Dict[str, float]] = None
    behavior_patterns: Optional[Dict[str, str]] = None

@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

# ==================== 推理引擎相关数据结构 ====================

@dataclass
class EngineInfo:
    """引擎信息"""
    name: str
    version: str
    description: str
    supported_modes: List[ReasoningMode]
    capabilities: List[str]

@dataclass
class ReasoningResult:
    """推理结果"""
    thoughts: List[Any]
    final_answer: str
    reasoning_path: List[str]
    execution_time: float
    success: bool = True
    error_message: Optional[str] = None

@dataclass
class ThoughtNode:
    """思考节点"""
    content: str
    confidence: float
    children: List['ThoughtNode'] = field(default_factory=list)
    parent: Optional['ThoughtNode'] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

# ==================== 执行引擎相关数据结构 ====================

@dataclass
class ExecutionConfig:
    """执行配置"""
    resource_requirements: Dict[str, Any]
    priority: TaskPriority = TaskPriority.NORMAL
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 300.0

@dataclass
class AgentTask:
    """Agent任务"""
    agent: 'IAgent'
    context: ExecutionContext
    config: ExecutionConfig
    resources: Optional[Dict[str, Any]] = None

@dataclass
class ExecutionResult:
    """执行结果"""
    task_id: str
    success: bool
    result: Any
    execution_time: float
    resource_usage: Dict[str, Any]
    error_message: Optional[str] = None

# ==================== 工具相关数据结构 ====================

@dataclass
class ToolRegistration:
    """工具注册信息"""
    tool_info: 'ToolSchema'
    version: str
    dependencies: List[str]
    registration_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_tool(cls, tool: 'ITool') -> 'ToolRegistration':
        """从工具创建注册信息"""
        schema = tool.get_schema()
        return cls(
            tool_info=schema,
            version="1.0.0",
            dependencies=[],
            registration_time=datetime.now().timestamp()
        )

@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    description: str
    parameters: List['ToolParameter']
    category: str
    version: str
    author: Optional[str] = None
    
    @classmethod
    def from_tool(cls, tool: 'ITool', category: str = "general") -> 'ToolInfo':
        """从工具创建信息"""
        schema = tool.get_schema()
        return cls(
            name=schema.name,
            description=schema.description,
            parameters=schema.parameters,
            category=category,
            version="1.0.0"
        )

@dataclass
class ToolExecutionStats:
    """工具执行统计"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_execution_time: float = 0.0
    average_execution_time: float = 0.0
    
    async def record_success(self, tool_name: str, execution_time: float, result: Any) -> None:
        """记录成功执行"""
        self.total_calls += 1
        self.successful_calls += 1
        self.total_execution_time += execution_time
        self.average_execution_time = self.total_execution_time / self.total_calls
    
    async def record_failure(self, tool_name: str, execution_time: float, error: Exception) -> None:
        """记录失败执行"""
        self.total_calls += 1
        self.failed_calls += 1
        self.total_execution_time += execution_time
        self.average_execution_time = self.total_execution_time / self.total_calls

# ==================== 监控相关数据结构 ====================

@dataclass
class PerformanceMetrics:
    """性能指标"""
    cpu_usage: float
    memory_usage: float
    active_tasks: int
    completed_tasks: int
    failed_tasks: int
    average_response_time: float
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

@dataclass
class ResourceAllocation:
    """资源分配"""
    cpu_cores: float
    memory_mb: int
    gpu_memory: Optional[int] = None
    network_bandwidth: Optional[float] = None
    custom_resources: Dict[str, Any] = field(default_factory=dict)

# ==================== ReAct相关数据结构 ====================

@dataclass
class ReActStep:
    """ReAct执行步骤"""
    step_type: ReActStepType
    content: str
    tool_call: Optional[ToolCall] = None
    tool_result: Optional[ToolResult] = None
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

@dataclass
class ReActResult:
    """ReAct执行结果"""
    success: bool
    final_answer: Optional[str] = None
    steps: List[ReActStep] = field(default_factory=list)
    total_iterations: int = 0
    total_time: float = 0.0
    error_message: Optional[str] = None

# ==================== 核心接口 ====================

class ITool(ABC):
    """工具接口"""
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """执行工具"""
        pass
    
    @abstractmethod
    def get_schema(self) -> ToolSchema:
        """获取工具模式"""
        pass
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """验证参数"""
        # 添加对None值和空值的验证逻辑
        if parameters is None:
            return False, "参数不能为None"
        
        if not isinstance(parameters, dict):
            return False, "参数必须是字典类型"
        
        schema = self.get_schema()
        for param in schema.parameters:
            if param.required and param.name not in parameters:
                return False, f"缺少必需参数: {param.name}"
            
            if param.name in parameters:
                value = parameters[param.name]
                # 基本类型检查
                if param.type == "number" and not isinstance(value, (int, float)):
                    return False, f"参数 {param.name} 必须是数字"
                elif param.type == "string" and not isinstance(value, str):
                    return False, f"参数 {param.name} 必须是字符串"
                elif param.type == "boolean" and not isinstance(value, bool):
                    return False, f"参数 {param.name} 必须是布尔值"
                elif param.type == "array" and not isinstance(value, list):
                    return False, f"参数 {param.name} 必须是数组"
                elif param.type == "object" and not isinstance(value, dict):
                    return False, f"参数 {param.name} 必须是对象"
                
                # 枚举值检查
                if param.enum and value not in param.enum:
                    return False, f"参数 {param.name} 的值不在允许范围内"
        
        return True, None

class IAgent(ABC):
    """智能体接口"""
    
    @property
    @abstractmethod
    def agent_id(self) -> str:
        """智能体唯一标识"""
        pass
    
    @property
    @abstractmethod
    def capabilities(self) -> AgentCapabilities:
        """智能体能力"""
        pass
    
    @property
    @abstractmethod
    def status(self) -> AgentStatus:
        """当前状态"""
        pass
    
    @abstractmethod
    async def process_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """处理接收到的消息"""
        pass
    
    @abstractmethod
    async def execute_task(
        self,
        task: str,
        context: Optional[ExecutionContext] = None,
        llm_request: Optional[Any] = None,
    ) -> Any:
        """执行任务"""
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """初始化智能体"""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """关闭智能体"""
        pass

class ICommunicator(ABC):
    """通信器接口"""
    
    @abstractmethod
    async def send_message(self, message: AgentMessage) -> None:
        """发送消息"""
        pass
    
    @abstractmethod
    async def receive_message(self, agent_id: str, timeout: float = 30.0) -> Optional[AgentMessage]:
        """接收消息"""
        pass
    
    @abstractmethod
    async def broadcast_message(self, message: AgentMessage, exclude_agents: Optional[List[str]] = None) -> None:
        """广播消息"""
        pass
    
    @abstractmethod
    async def register_agent(self, agent_id: str) -> None:
        """注册智能体"""
        pass
    
    @abstractmethod
    async def unregister_agent(self, agent_id: str) -> None:
        """注销智能体"""
        pass

class IOrchestrator(ABC):
    """编排器接口"""
    
    @abstractmethod
    async def register_agent(self, agent: IAgent) -> None:
        """注册智能体"""
        pass
    
    @abstractmethod
    async def unregister_agent(self, agent_id: str) -> None:
        """注销智能体"""
        pass
    
    @abstractmethod
    async def get_agent(self, agent_id: str) -> Optional[IAgent]:
        """获取智能体"""
        pass
    
    @abstractmethod
    async def list_agents(self) -> List[IAgent]:
        """列出所有智能体"""
        pass
    
    @abstractmethod
    async def coordinate_agents(self, task: str, agent_ids: List[str], context: Optional[ExecutionContext] = None) -> Any:
        """协调多个智能体执行任务"""
        pass
    
    @abstractmethod
    async def execute_workflow(self, workflow: Dict[str, Any], context: Optional[ExecutionContext] = None) -> Any:
        """执行工作流"""
        pass

# ==================== 配置管理接口 ====================

class IConfigurationManager(ABC):
    """配置管理器接口"""
    
    @abstractmethod
    async def load_config(self, config_id: str) -> AgentConfig:
        """加载配置"""
        pass
    
    @abstractmethod
    async def save_config(self, config: AgentConfig) -> str:
        """保存配置"""
        pass
    
    @abstractmethod
    async def validate_config(self, config: AgentConfig) -> ValidationResult:
        """验证配置"""
        pass
    
    @abstractmethod
    async def update_config(self, config_id: str, updates: Dict[str, Any]) -> AgentConfig:
        """更新配置"""
        pass
    
    @abstractmethod
    async def list_configs(self, filters: Optional[Dict[str, Any]] = None) -> List[AgentConfig]:
        """列出配置"""
        pass

# ==================== 推理引擎接口 ====================

class IReasoningEngine(ABC):
    """推理引擎接口"""
    
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化推理引擎"""
        pass
    
    @abstractmethod
    async def process(
        self, 
        agent: IAgent, 
        context: ExecutionContext, 
        tools: 'IToolManager'
    ) -> ReasoningResult:
        """执行推理过程"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """清理资源"""
        pass
    
    @property
    @abstractmethod
    def engine_info(self) -> EngineInfo:
        """返回引擎信息"""
        pass

class IReasoningEngineFactory(ABC):
    """推理引擎工厂接口"""
    
    @abstractmethod
    def register_engine(self, name: str, engine_class: Type[IReasoningEngine]) -> None:
        """注册推理引擎"""
        pass
    
    @abstractmethod
    def create_engine(self, mode: ReasoningMode, config: Dict[str, Any]) -> IReasoningEngine:
        """创建推理引擎实例"""
        pass
    
    @abstractmethod
    def list_available_engines(self) -> List[str]:
        """列出可用的推理引擎"""
        pass

# ==================== 执行引擎接口 ====================

class IExecutionEngine(ABC):
    """执行引擎接口"""
    
    @abstractmethod
    async def execute_agent(
        self, 
        agent: IAgent, 
        context: ExecutionContext, 
        config: ExecutionConfig
    ) -> ExecutionResult:
        """执行智能体任务"""
        pass
    
    @abstractmethod
    async def batch_execute(self, tasks: List[AgentTask]) -> List[ExecutionResult]:
        """批量执行智能体任务"""
        pass

class IResourceManager(ABC):
    """资源管理器接口"""
    
    @abstractmethod
    async def allocate(self, requirements: Dict[str, Any]) -> ResourceAllocation:
        """分配资源"""
        pass
    
    @abstractmethod
    async def release(self, allocation: ResourceAllocation) -> None:
        """释放资源"""
        pass
    
    @abstractmethod
    async def get_available_resources(self) -> Dict[str, Any]:
        """获取可用资源"""
        pass

class IPerformanceMonitor(ABC):
    """性能监控器接口"""
    
    @abstractmethod
    async def start_execution(self, task: AgentTask) -> str:
        """开始执行监控"""
        pass
    
    @abstractmethod
    async def record_success(self, execution_id: str, result: ExecutionResult) -> None:
        """记录成功执行"""
        pass
    
    @abstractmethod
    async def record_failure(self, execution_id: str, error: Exception) -> None:
        """记录失败执行"""
        pass
    
    @abstractmethod
    async def get_metrics(self) -> PerformanceMetrics:
        """获取性能指标"""
        pass

# ==================== 工具管理接口 ====================

class IToolManager(ABC):
    """工具管理器接口"""
    
    @abstractmethod
    async def register_tool(self, tool: ITool, category: str = "general") -> None:
        """注册工具"""
        pass
    
    @abstractmethod
    async def unregister_tool(self, tool_name: str) -> None:
        """注销工具"""
        pass
    
    @abstractmethod
    async def call_tool(
        self, 
        tool_name: str, 
        parameters: Dict[str, Any],
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """调用工具"""
        pass
    
    @abstractmethod
    def list_tools(self, filters: Optional[Dict[str, Any]] = None) -> List[ToolInfo]:
        """列出可用工具"""
        pass

class IToolRegistry(ABC):
    """工具注册中心接口"""
    
    @abstractmethod
    async def register(self, tool: ITool) -> None:
        """注册工具"""
        pass
    
    @abstractmethod
    async def unregister(self, tool_name: str) -> None:
        """注销工具"""
        pass
    
    @abstractmethod
    async def get_tool_info(self, tool_name: str) -> ToolInfo:
        """获取工具信息"""
        pass
    
    @abstractmethod
    async def discover_tools(self, search_paths: List[str]) -> None:
        """自动发现工具"""
        pass

# ==================== 监控与调度接口 ====================

class IMonitoringScheduler(ABC):
    """监控与调度接口"""
    
    @abstractmethod
    async def collect_metrics(self) -> Dict[str, Any]:
        """收集指标"""
        pass
    
    @abstractmethod
    async def analyze_performance(self, metrics: Dict[str, Any]) -> Any:
        """分析性能"""
        pass
    
    @abstractmethod
    async def schedule_task(self, task: AgentTask, priority: TaskPriority = TaskPriority.NORMAL) -> str:
        """调度任务"""
        pass
    
    @abstractmethod
    async def get_scheduling_status(self) -> Dict[str, Any]:
        """获取调度状态"""
        pass