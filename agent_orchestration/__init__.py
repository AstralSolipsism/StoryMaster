"""
智能体编排框架

提供智能体管理、工具调用、ReAct执行和智能体间通信等核心能力。
"""

from .interfaces import (
    IAgent,
    ITool,
    IOrchestrator,
    ICommunicator,
    ToolSchema,
    ToolParameter,
    AgentMessage,
    AgentCapabilities,
    ExecutionContext,
    ReActStep,
    ReActResult,
    # 新增的接口
    IConfigurationManager,
    IReasoningEngine,
    IReasoningEngineFactory,
    IExecutionEngine,
    IResourceManager,
    IPerformanceMonitor,
    IToolManager,
    IToolRegistry,
    IMonitoringScheduler,
    # 新增的数据结构
    AgentConfig,
    ValidationResult,
    ReasoningMode,
    EngineInfo,
    ReasoningResult,
    ThoughtNode,
    ExecutionConfig,
    AgentTask,
    ExecutionResult,
    ToolRegistration,
    ToolInfo,
    ToolExecutionStats,
    PerformanceMetrics,
    ResourceAllocation,
    TaskPriority
)

from .core import (
    BaseAgent,
    Orchestrator,
    create_agent,
    create_orchestrator
)

from .config import (
    ConfigurationManager,
    DynamicConfigLoader,
    create_config_manager,
    create_dynamic_loader
)

from .reasoning import (
    ReasoningEngineFactory,
    BaseReasoningEngine,
    ChainOfThoughtEngine,
    TreeOfThoughtEngine,
    GraphOfThoughtEngine,
    AlgorithmOfThoughtsEngine,
    SkeletonOfThoughtEngine,
    ReactReasoningEngine,
    ThoughtTree,
    get_reasoning_engine_factory,
    create_reasoning_engine
)

from .execution import (
    ExecutionEngine,
    ResourceManager,
    PerformanceMonitor,
    WorkerPool,
    get_execution_engine,
    create_execution_engine
)

from .tools import (
    BaseTool,
    CalculatorTool,
    SearchTool,
    WeatherTool,
    FileSystemTool,
    TimeTool,
    RandomTool,
    ToolFactory,
    # 新增的工具管理
    ToolManager,
    ToolRegistry,
    ToolIntegration,
    VersionManager,
    EnhancedCalculatorTool,
    EnhancedFileSystemTool,
    EnhancedToolFactory,
    create_tool_manager,
    create_tool_registry,
    create_tool_integration
)

from .monitoring import (
    MonitoringScheduler,
    PerformanceAnalyzer,
    TaskScheduler,
    LoadBalancer,
    SchedulingStrategy,
    ScheduledTask,
    LoadBalancingInfo,
    get_monitoring_scheduler,
    create_monitoring_scheduler
)

from .react import (
    ReActExecutor,
    ReActConfig,
    ReActParser
)

from .communication import (
    AgentCommunicator,
    MessageQueue,
    Subscription,
    create_communicator
)

__version__: str = "2.0.0"
# 按功能分组组织__all__列表，提高可维护性
_core_interfaces = [
    "IAgent", "ITool", "IOrchestrator", "ICommunicator",
    "ToolSchema", "ToolParameter", "AgentMessage", "AgentCapabilities",
    "ExecutionContext", "ReActStep", "ReActResult"
]

_extended_interfaces = [
    "IConfigurationManager", "IReasoningEngine", "IReasoningEngineFactory",
    "IExecutionEngine", "IResourceManager", "IPerformanceMonitor",
    "IToolManager", "IToolRegistry", "IMonitoringScheduler"
]

_data_structures = [
    "AgentConfig", "ValidationResult", "ReasoningMode", "EngineInfo",
    "ReasoningResult", "ThoughtNode", "ExecutionConfig", "AgentTask",
    "ExecutionResult", "ToolRegistration", "ToolInfo", "ToolExecutionStats",
    "PerformanceMetrics", "ResourceAllocation", "TaskPriority"
]

_core_implementations = [
    "BaseAgent", "AgentCommunicator", "Orchestrator",
    "create_agent", "create_orchestrator"
]

_config_management = [
    "ConfigurationManager", "DynamicConfigLoader",
    "create_config_manager", "create_dynamic_loader"
]

_reasoning_engines = [
    "ReasoningEngineFactory", "BaseReasoningEngine", "ChainOfThoughtEngine",
    "TreeOfThoughtEngine", "GraphOfThoughtEngine", "AlgorithmOfThoughtsEngine",
    "SkeletonOfThoughtEngine", "ReactReasoningEngine", "ThoughtTree",
    "get_reasoning_engine_factory", "create_reasoning_engine"
]

_execution_engines = [
    "ExecutionEngine", "ResourceManager", "PerformanceMonitor", "WorkerPool",
    "get_execution_engine", "create_execution_engine"
]

_tool_management = [
    "BaseTool", "CalculatorTool", "SearchTool", "WeatherTool", "FileSystemTool",
    "TimeTool", "RandomTool", "ToolFactory", "ToolManager", "ToolRegistry",
    "ToolIntegration", "VersionManager", "EnhancedCalculatorTool",
    "EnhancedFileSystemTool", "EnhancedToolFactory",
    "create_tool_manager", "create_tool_registry", "create_tool_integration"
]

_monitoring_scheduling = [
    "MonitoringScheduler", "PerformanceAnalyzer", "TaskScheduler", "LoadBalancer",
    "SchedulingStrategy", "ScheduledTask", "LoadBalancingInfo",
    "get_monitoring_scheduler", "create_monitoring_scheduler"
]

_react_communication = [
    "ReActExecutor", "ReActConfig", "ReActParser", "MessageQueue",
    "Subscription", "create_communicator"
]

__all__ = (
    _core_interfaces + _extended_interfaces + _data_structures +
    _core_implementations + _config_management + _reasoning_engines +
    _execution_engines + _tool_management + _monitoring_scheduling +
    _react_communication
)