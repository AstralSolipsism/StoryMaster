"""
ReAct（推理-行动）框架实现
"""

import json
import re
import time
import asyncio
import ast
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .interfaces import (
    ITool, IAgent, ReActStep, ReActResult, ReActStepType,
    ToolCall, ToolResult, ExecutionContext, AgentStatus
)
from model_adapter import ModelScheduler, RequestContext, ChatMessage

# ReAct提示模板
REACT_PROMPT_TEMPLATE = """
你是一个智能助手，可以使用工具来帮助解决问题。

可用工具:
{tool_schemas}

当前任务: {task}
历史对话: {history}

请按照以下格式思考:
Thought: 你的思考过程
Action: 工具名称
Action Input: 工具参数(JSON格式)
Observation: 工具执行结果
... (重复Thought-Action-Observation循环)
Thought: 我现在知道最终答案了
Final Answer: 最终答案

开始!
Thought: {initial_thought}
"""

REACT_EXAMPLES = """
示例1:
任务: 计算 123 + 456 的结果
Thought: 我需要计算两个数字的和，可以使用计算器工具
Action: calculator
Action Input: {{"expression": "123 + 456"}}
Observation: 579
Thought: 我已经得到了计算结果
Final Answer: 123 + 456 = 579

示例2:
任务: 查询北京今天的天气
Thought: 我需要查询北京的天气信息，可以使用天气工具
Action: weather
Action Input: {{"location": "北京"}}
Observation: 北京今天晴，温度25°C，湿度60%
Thought: 我已经获得了北京的天气信息
Final Answer: 北京今天晴，温度25°C，湿度60%
"""

# ==================== 常量定义 ====================
DEFAULT_MAX_ITERATIONS = 10
DEFAULT_TIMEOUT = 300.0  # 5分钟
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TEMPERATURE = 0.1
TOOL_RESULT_PREFIX = "工具执行结果: "

@dataclass
class ReActConfig:
    """ReAct配置"""
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    timeout: float = DEFAULT_TIMEOUT
    enable_examples: bool = True
    initial_thought: str = "让我分析一下这个任务，看看需要使用什么工具来解决问题。"
    stop_phrases: List[str] = None
    DEFAULT_MAX_TOKENS: int = DEFAULT_MAX_TOKENS  # 添加常量属性
    DEFAULT_TEMPERATURE: float = DEFAULT_TEMPERATURE  # 添加温度常量
    
    def __post_init__(self):
        if self.stop_phrases is None:
            self.stop_phrases = [
                "我现在知道最终答案了",
                "我已经解决了这个问题",
                "任务完成"
            ]

class ReActParser:
    """ReAct响应解析器"""
    
    # 预编译正则表达式提高性能
    THOUGHT_PATTERN = re.compile(r'Thought:\s*(.*?)(?=\n\s*(?:Action|Final Answer)|$)', re.DOTALL | re.IGNORECASE)
    ACTION_PATTERN = re.compile(r'Action:\s*(.*?)(?=\n|$)', re.DOTALL | re.IGNORECASE)
    ACTION_INPUT_PATTERN = re.compile(r'Action Input:\s*(.*?)(?=\n\s*(?:Thought|Action|Final Answer|Observation)|$)', re.DOTALL | re.IGNORECASE)
    FINAL_ANSWER_PATTERN = re.compile(r'Final Answer:\s*(.*?)(?=\n|$)', re.DOTALL | re.IGNORECASE)
    
    @classmethod
    def parse_response(cls, response: str) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]], Optional[str]]:
        """
        解析模型响应，提取思考、行动、行动输入和最终答案
        
        Returns:
            (thought, action, action_input, final_answer)
        """
        # 使用预编译的正则表达式提高性能
        thought_match = cls.THOUGHT_PATTERN.search(response)
        thought = thought_match.group(1).strip() if thought_match else None
        
        # 提取行动
        action_match = cls.ACTION_PATTERN.search(response)
        action = action_match.group(1).strip() if action_match else None
        
        # 提取行动输入
        action_input_match = cls.ACTION_INPUT_PATTERN.search(response)
        action_input = None
        if action_input_match:
            try:
                action_input = json.loads(action_input_match.group(1).strip())
            except json.JSONDecodeError:
                # 尝试修复常见的JSON格式问题，但使用更安全的方法
                input_str = action_input_match.group(1).strip()
                try:
                    # 使用ast.literal_eval作为更安全的替代方案
                    action_input = ast.literal_eval(input_str)
                    # 确保结果是字典类型
                    if not isinstance(action_input, dict):
                        action_input = {"raw_input": input_str}
                except (ValueError, SyntaxError):
                    # 如果ast.literal_eval也失败，则返回原始输入
                    action_input = {"raw_input": input_str}
        
        # 提取最终答案
        final_answer_match = cls.FINAL_ANSWER_PATTERN.search(response)
        final_answer = final_answer_match.group(1).strip() if final_answer_match else None
        
        return thought, action, action_input, final_answer

class ReActExecutor:
    """ReAct执行器"""
    
    def __init__(self, 
                 model_scheduler: ModelScheduler,
                 tools: Dict[str, ITool],
                 config: Optional[ReActConfig] = None):
        self.model_scheduler = model_scheduler
        self.tools = tools
        self.config = config or ReActConfig()
        self.parser = ReActParser()
    
    async def execute(self,
                     task: str,
                     context: Optional[ExecutionContext] = None,
                     history: Optional[List[str]] = None) -> ReActResult:
        """执行ReAct循环"""
        start_time = time.time()
        steps = []
        history = history or []
        iteration = 0  # 在循环前初始化iteration变量
        
        # 构建工具模式描述
        tool_schemas = self._build_tool_schemas()
        
        # 构建初始提示
        prompt = self._build_prompt(task, tool_schemas, history)
        
        try:
            for iteration in range(self.config.max_iterations):
                # 检查超时
                if time.time() - start_time > self.config.timeout:
                    return ReActResult(
                        success=False,
                        error_message="执行超时",
                        steps=steps,
                        total_iterations=iteration,
                        total_time=time.time() - start_time
                    )
                
                # 调用模型
                request_context = RequestContext(
                    messages=[ChatMessage(role='user', content=prompt)],
                    max_tokens=self.config.DEFAULT_MAX_TOKENS,
                    temperature=getattr(self.config, 'DEFAULT_TEMPERATURE', DEFAULT_TEMPERATURE)
                )
                
                response = await self.model_scheduler.chat(request_context)
                if not response.choices or not response.choices[0].message.content:
                    return ReActResult(
                        success=False,
                        error_message="模型响应为空",
                        steps=steps,
                        total_iterations=iteration,
                        total_time=time.time() - start_time
                    )
                
                model_response = response.choices[0].message.content
                
                # 解析响应
                thought, action, action_input, final_answer = self.parser.parse_response(model_response)
                
                # 记录思考步骤
                if thought:
                    steps.append(ReActStep(
                        step_type=ReActStepType.THOUGHT,
                        content=thought
                    ))
                
                # 检查是否有最终答案
                if final_answer:
                    steps.append(ReActStep(
                        step_type=ReActStepType.FINAL_ANSWER,
                        content=final_answer
                    ))
                    return ReActResult(
                        success=True,
                        final_answer=final_answer,
                        steps=steps,
                        total_iterations=iteration + 1,
                        total_time=time.time() - start_time
                    )
                
                # 执行行动
                if action and action_input:
                    # 记录行动步骤
                    tool_call = ToolCall(
                        tool_name=action,
                        parameters=action_input
                    )
                    steps.append(ReActStep(
                        step_type=ReActStepType.ACTION,
                        content=f"调用工具: {action}",
                        tool_call=tool_call
                    ))
                    
                    # 执行工具
                    tool_result = await self._execute_tool(action, action_input)
                    
                    # 记录观察步骤
                    observation = f"{TOOL_RESULT_PREFIX}{tool_result.result if tool_result.success else tool_result.error_message}"
                    steps.append(ReActStep(
                        step_type=ReActStepType.OBSERVATION,
                        content=observation,
                        tool_result=tool_result
                    ))
                    
                    # 更新提示，添加观察结果
                    prompt += f"\nObservation: {observation}\nThought: "
                else:
                    # 如果没有行动，继续思考
                    prompt += f"\nThought: "
                    # 如果没有最终答案，添加提示
                    if not final_answer:
                        prompt += "请继续思考，如果需要使用工具，请使用Action格式。如果已经有最终答案，请使用Final Answer格式。"
            
            # 达到最大迭代次数
            return ReActResult(
                success=False,
                error_message="达到最大迭代次数未找到最终答案",
                steps=steps,
                total_iterations=self.config.max_iterations,
                total_time=time.time() - start_time
            )
            
        except Exception as e:
            return ReActResult(
                success=False,
                error_message=f"ReAct执行失败: {str(e)}",
                steps=steps,
                total_iterations=iteration + 1,  # 使用实际的迭代次数
                total_time=time.time() - start_time
            )
    
    def _build_tool_schemas(self) -> str:
        """构建工具模式描述"""
        schemas = []
        for tool_name, tool in self.tools.items():
            schema = tool.get_schema()
            param_desc = []
            for param in schema.parameters:
                required_str = "必需" if param.required else "可选"
                enum_str = f" (可选值: {', '.join(map(str, param.enum))})" if param.enum else ""
                default_str = f" (默认值: {param.default})" if param.default is not None else ""
                param_desc.append(f"  - {param.name} ({param.type}): {param.description} [{required_str}]{enum_str}{default_str}")
            
            schemas.append(f"- {tool_name}: {schema.description}\n参数:\n" + "\n".join(param_desc))
        
        return "\n\n".join(schemas)
    
    def _build_prompt(self, task: str, tool_schemas: str, history: List[str]) -> str:
        """构建初始提示"""
        history_str = "\n".join(history) if history else "无"
        
        prompt = REACT_PROMPT_TEMPLATE.format(
            tool_schemas=tool_schemas,
            task=task,
            history=history_str,
            initial_thought=self.config.initial_thought
        )
        
        if self.config.enable_examples:
            prompt = REACT_EXAMPLES + "\n\n" + prompt
        
        return prompt
    
    async def _execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        if tool_name not in self.tools:
            return ToolResult(
                tool_name=tool_name,
                result=None,
                success=False,
                error_message=f"工具 '{tool_name}' 不存在"
            )
        
        tool = self.tools[tool_name]
        
        # 验证参数
        is_valid, error_message = tool.validate_parameters(parameters) if hasattr(tool, 'validate_parameters') else (True, None)
        if not is_valid:
            return ToolResult(
                tool_name=tool_name,
                result=None,
                success=False,
                error_message=f"参数验证失败: {error_message}"
            )
        
        try:
            start_time = time.time()
            result = await tool.execute(**parameters)
            execution_time = time.time() - start_time
            
            return ToolResult(
                tool_name=tool_name,
                result=result,
                success=True,
                execution_time=execution_time
            )
        except Exception as e:
            return ToolResult(
                tool_name=tool_name,
                result=None,
                success=False,
                error_message=f"工具执行失败: {str(e)}"
            )