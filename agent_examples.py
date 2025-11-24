"""
智能体编排框架使用示例
"""

import asyncio
import os
from typing import Dict, Any

from model_adapter import (
    ModelScheduler,
    SchedulerConfig,
    RequestContext,
    ChatMessage,
    ProviderConfig,
)

from agent_orchestration import (
    BaseAgent,
    ToolManager,
    Orchestrator,
    AgentCommunicator,
    AgentCapabilities,
    ExecutionContext,
    ToolFactory
)
from agent_orchestration.tools import BaseTool, ToolSchema, ToolParameter
from agent_orchestration.react import ReActExecutor, ReActConfig

# 配置信息
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# 验证API密钥
def validate_api_keys():
    """验证API密钥是否存在且有效"""
    missing_keys = []
    
    if not ANTHROPIC_API_KEY:
        missing_keys.append("ANTHROPIC_API_KEY")
    elif not ANTHROPIC_API_KEY.startswith('sk-ant-'):
        print("警告: ANTHROPIC_API_KEY格式可能不正确，应以'sk-ant-'开头")
    
    if not OPENROUTER_API_KEY:
        missing_keys.append("OPENROUTER_API_KEY")
    elif len(OPENROUTER_API_KEY) < 20:
        print("警告: OPENROUTER_API_KEY长度可能不正确")
    
    if missing_keys:
        print(f"错误: 缺少以下API密钥: {', '.join(missing_keys)}")
        print("请设置相应的环境变量后再运行示例")
        return False
    
    return True

# 提供商配置
provider_configs = {
    "anthropic": ProviderConfig(api_key=ANTHROPIC_API_KEY),
    "openrouter": ProviderConfig(api_key=OPENROUTER_API_KEY),
    "ollama": ProviderConfig(base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")),
}

async def example_1_basic_agent():
    """示例1: 基础智能体使用"""
    print("\n=== 示例1: 基础智能体使用 ===")
    
    # 创建模型调度器
    scheduler_config = SchedulerConfig(
        default_provider='anthropic',
        fallback_providers=['openrouter', 'ollama'],
        max_retries=2,
        cost_threshold=0.10
    )
    
    scheduler = ModelScheduler(scheduler_config, provider_configs)
    await scheduler.initialize()
    
    # 创建工具管理器并注册工具
    tool_manager = ToolManager()
    tools = ToolFactory.create_default_tools()
    for tool_name, tool in tools.items():
        tool_manager.register_tool(tool, "general")
    
    # 创建智能体
    agent = BaseAgent(
        agent_id="assistant_1",
        model_scheduler=scheduler,
        tool_manager=tool_manager,
        system_prompt="你是一个有用的助手，可以使用各种工具来帮助用户解决问题。"
    )
    
    await agent.initialize()
    
    try:
        # 执行任务
        task = "计算 123 + 456 的结果，然后查询北京的天气"
        print(f"任务: {task}")
        
        result = await agent.execute_task(task)
        print(f"结果: {result}")
        
        # 查看执行历史
        history = agent.get_execution_history()
        print(f"执行历史: {len(history)} 条记录")
        
    finally:
        await agent.shutdown()

async def example_2_agent_communication():
    """示例2: 智能体间通信"""
    print("\n=== 示例2: 智能体间通信 ===")
    
    # 创建模型调度器
    scheduler_config = SchedulerConfig(
        default_provider='anthropic',
        fallback_providers=['openrouter'],
        max_retries=2
    )
    
    scheduler = ModelScheduler(scheduler_config, provider_configs)
    await scheduler.initialize()
    
    # 创建通信器
    communicator = AgentCommunicator()
    await communicator.start()
    
    # 创建工具管理器
    tool_manager = ToolManager()
    tools = ToolFactory.create_default_tools()
    for tool_name, tool in tools.items():
        tool_manager.register_tool(tool, "general")
    
    # 创建两个智能体
    agent1 = BaseAgent(
        agent_id="agent_1",
        model_scheduler=scheduler,
        tool_manager=tool_manager,
        communicator=communicator,
        system_prompt="你是智能体1，专门负责数学计算。"
    )
    
    agent2 = BaseAgent(
        agent_id="agent_2",
        model_scheduler=scheduler,
        tool_manager=tool_manager,
        communicator=communicator,
        system_prompt="你是智能体2，专门负责天气查询。"
    )
    
    try:
        await agent1.initialize()
        await agent2.initialize()
        
        # agent1 向 agent2 发送消息
        await agent1.send_message(
            receiver_id="agent_2",
            content="请帮我查询上海的天气",
            message_type="request"
        )
        
        # 等待一段时间让消息处理（使用常量）
        MESSAGE_PROCESSING_WAIT_TIME = 5
        await asyncio.sleep(MESSAGE_PROCESSING_WAIT_TIME)
        
        # 查看通信统计
        stats = communicator.get_stats()
        print(f"通信统计: {stats}")
        
    finally:
        await agent1.shutdown()
        await agent2.shutdown()
        await communicator.stop()

async def example_3_orchestration():
    """示例3: 智能体编排"""
    print("\n=== 示例3: 智能体编排 ===")
    
    # 创建模型调度器
    scheduler_config = SchedulerConfig(
        default_provider='anthropic',
        fallback_providers=['openrouter'],
        max_retries=2
    )
    
    scheduler = ModelScheduler(scheduler_config, provider_configs)
    await scheduler.initialize()
    
    # 创建编排器
    orchestrator = Orchestrator()
    
    # 创建工具管理器
    tool_manager = ToolManager()
    tools = ToolFactory.create_default_tools()
    for tool_name, tool in tools.items():
        tool_manager.register_tool(tool, "general")
    
    # 创建专门化的智能体
    math_agent = BaseAgent(
        agent_id="math_expert",
        model_scheduler=scheduler,
        tool_manager=tool_manager,
        system_prompt="你是数学专家，专门解决数学问题。",
        capabilities=AgentCapabilities(
            can_use_tools=True,
            supported_task_types=["math", "calculation"]
        )
    )
    
    weather_agent = BaseAgent(
        agent_id="weather_expert",
        model_scheduler=scheduler,
        tool_manager=tool_manager,
        system_prompt="你是天气专家，专门查询天气信息。",
        capabilities=AgentCapabilities(
            can_use_tools=True,
            supported_task_types=["weather", "forecast"]
        )
    )
    
    try:
        # 注册智能体到编排器
        await orchestrator.register_agent(math_agent)
        await orchestrator.register_agent(weather_agent)
        
        # 协调多个智能体执行任务
        task = "计算圆的面积（半径为5），然后查询北京的天气"
        print(f"协调任务: {task}")
        
        result = await orchestrator.coordinate_agents(
            task=task,
            agent_ids=["math_expert", "weather_expert"]
        )
        
        print(f"协调结果: {result}")
        
        # 执行工作流
        workflow = {
            "steps": [
                {"agent": "math_expert", "task": "计算 15 * 8 的结果"},
                {"agent": "weather_expert", "task": "查询深圳的天气"},
                {"agent": "math_expert", "task": "计算前面两个结果的和"}
            ]
        }
        
        print(f"执行工作流: {workflow}")
        workflow_results = await orchestrator.execute_workflow(workflow)
        print(f"工作流结果: {workflow_results}")
        
    finally:
        await orchestrator.unregister_agent("math_expert")
        await orchestrator.unregister_agent("weather_expert")

async def example_4_custom_tool():
    """示例4: 自定义工具"""
    print("\n=== 示例4: 自定义工具 ===")
    
    # 创建自定义工具
    class EmailTool(BaseTool):
        def __init__(self):
            super().__init__(
                name="email_sender",
                description="发送邮件工具"
            )
        
        async def execute(self, to: str, subject: str, body: str) -> str:
            """模拟发送邮件"""
            # 模拟发送延迟（使用常量）
            EMAIL_SEND_DELAY = 0.5
            await asyncio.sleep(EMAIL_SEND_DELAY)
            
            # 模拟发送结果
            print(f"模拟发送邮件:")
            print(f"  收件人: {to}")
            print(f"  主题: {subject}")
            print(f"  内容: {body}")
            
            return f"邮件已成功发送到 {to}"
        
        def get_schema(self) -> ToolSchema:
            return ToolSchema(
                name=self.name,
                description=self.description,
                parameters=[
                    ToolParameter(
                        name="to",
                        type="string",
                        description="收件人邮箱地址",
                        required=True
                    ),
                    ToolParameter(
                        name="subject",
                        type="string",
                        description="邮件主题",
                        required=True
                    ),
                    ToolParameter(
                        name="body",
                        type="string",
                        description="邮件内容",
                        required=True
                    )
                ],
                returns="发送结果消息"
            )
    
    # 创建模型调度器
    scheduler_config = SchedulerConfig(
        default_provider='anthropic',
        fallback_providers=['openrouter'],
        max_retries=2
    )
    
    scheduler = ModelScheduler(scheduler_config, provider_configs)
    await scheduler.initialize()
    
    # 创建工具管理器并注册自定义工具
    tool_manager = ToolManager()
    
    # 注册默认工具
    default_tools = ToolFactory.create_default_tools()
    for tool_name, tool in default_tools.items():
        tool_manager.register_tool(tool, "general")
    
    # 注册自定义工具
    email_tool = EmailTool()
    tool_manager.register_tool(email_tool, "communication")
    
    # 创建智能体
    agent = BaseAgent(
        agent_id="email_assistant",
        model_scheduler=scheduler,
        tool_manager=tool_manager,
        system_prompt="你是一个邮件助手，可以帮助用户发送邮件。"
    )
    
    try:
        await agent.initialize()
        
        # 执行任务
        task = "发送一封邮件到 test@example.com，主题是'会议提醒'，内容是'明天下午2点有重要会议，请准时参加。'"
        print(f"任务: {task}")
        
        result = await agent.execute_task(task)
        print(f"结果: {result}")
        
    finally:
        await agent.shutdown()

async def example_5_react_debugging():
    """示例5: ReAct调试"""
    print("\n=== 示例5: ReAct调试 ===")
    
    # 创建模型调度器
    scheduler_config = SchedulerConfig(
        default_provider='anthropic',
        fallback_providers=['openrouter'],
        max_retries=2
    )
    
    scheduler = ModelScheduler(scheduler_config, provider_configs)
    await scheduler.initialize()
    
    # 创建工具管理器
    tool_manager = ToolManager()
    tools = ToolFactory.create_default_tools()
    for tool_name, tool in tools.items():
        tool_manager.register_tool(tool, "general")
    
    # 创建ReAct执行器
    react_config = ReActConfig(
        max_iterations=5,
        timeout=60.0,
        enable_examples=True,
        initial_thought="让我分析这个任务，看看需要使用什么工具。"
    )
    
    react_executor = ReActExecutor(
        model_scheduler=scheduler,
        tools=tool_manager.tools,
        config=react_config
    )
    
    try:
        # 执行ReAct任务
        task = "计算圆的面积（半径为5），然后获取当前时间"
        print(f"ReAct任务: {task}")
        
        result = await react_executor.execute(task)
        
        print(f"ReAct执行结果:")
        print(f"  成功: {result.success}")
        print(f"  最终答案: {result.final_answer}")
        print(f"  总迭代次数: {result.total_iterations}")
        print(f"  总耗时: {result.total_time:.2f}秒")
        
        if not result.success:
            print(f"  错误信息: {result.error_message}")
        
        print(f"\n执行步骤:")
        for i, step in enumerate(result.steps):
            print(f"  步骤 {i+1}: {step.step_type.value}")
            print(f"    内容: {step.content}")
            if step.tool_call:
                print(f"    工具调用: {step.tool_call.tool_name}({step.tool_call.parameters})")
            if step.tool_result:
                print(f"    工具结果: {step.tool_result.result}")
        
    finally:
        pass  # ReActExecutor不需要显式关闭

async def main():
    """主函数，运行所有示例"""
    print("智能体编排框架示例")
    print("=" * 50)
    
    # 验证API密钥
    if not validate_api_keys():
        print("由于API密钥验证失败，程序退出")
        return
    
    try:
        # 运行示例
        await example_1_basic_agent()
        await example_2_agent_communication()
        await example_3_orchestration()
        await example_4_custom_tool()
        await example_5_react_debugging()
        
    except Exception as e:
        print(f"示例执行出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n所有示例执行完成")

if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())