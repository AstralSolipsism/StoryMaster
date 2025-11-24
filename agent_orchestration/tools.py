"""
基础工具实现和工具管理器重构
"""

import asyncio
import json
import math
import time
import random
import importlib
import importlib.util
import inspect
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from .interfaces import (
    ITool, IToolManager, IToolRegistry, ToolSchema, ToolParameter,
    ToolResult, ToolRegistration, ToolInfo, ToolExecutionStats,
    ExecutionContext, ValidationResult
)

class BaseTool(ITool):
    """基础工具类"""
    
    def __init__(self, name: str, description: str):
        self._name = name
        self._description = description
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    async def execute(self, **kwargs) -> Any:
        """执行工具（子类必须实现）"""
        raise NotImplementedError
    
    def get_schema(self) -> ToolSchema:
        """获取工具模式（子类必须实现）"""
        raise NotImplementedError

class CalculatorTool(BaseTool):
    """计算器工具"""
    
    def __init__(self):
        super().__init__(
            name="calculator",
            description="执行数学计算，支持基本运算、函数和表达式求值"
        )
    
    async def execute(self, expression: str) -> str:
        """执行数学计算"""
        try:
            # 安全地评估数学表达式
            # 只允许数学相关的操作
            allowed_names = {
                k: v for k, v in math.__dict__.items() 
                if not k.startswith("_")
            }
            allowed_names.update({
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "sum": sum
            })
            
            # 编译并执行表达式
            code = compile(expression, "<string>", "eval")
            
            # 检查是否只使用了允许的变量
            for name in code.co_names:
                if name not in allowed_names:
                    raise NameError(f"不允许使用 '{name}'")
            
            result = eval(code, {"__builtins__": {}}, allowed_names)
            return str(result)
            
        except Exception as e:
            return f"计算错误: {str(e)}"
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="expression",
                    type="string",
                    description="数学表达式，例如: '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)'",
                    required=True
                )
            ],
            returns="计算结果的字符串表示"
        )

class SearchTool(BaseTool):
    """搜索工具（模拟）"""
    
    def __init__(self):
        super().__init__(
            name="search",
            description="搜索信息，返回相关结果"
        )
        # 模拟搜索数据库
        self.search_db = {
            "python": "Python是一种高级编程语言，由Guido van Rossum创建。",
            "javascript": "JavaScript是一种动态编程语言，主要用于网页开发。",
            "machine learning": "机器学习是人工智能的一个分支，让计算机能够从数据中学习。",
            "artificial intelligence": "人工智能是计算机科学的一个领域，致力于创建智能机器。",
            "weather": "天气是指大气在特定时间和地点的状态。",
            "news": "新闻是关于最近事件的信息，通常通过媒体传播。"
        }
    
    async def execute(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """执行搜索"""
        query = query.lower().strip()
        results = []
        
        # 模拟搜索延迟
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # 查找匹配的结果
        for key, value in self.search_db.items():
            if query in key or key in query:
                results.append({
                    "title": key.title(),
                    "content": value,
                    "source": "模拟搜索引擎"
                })
        
        # 如果没有精确匹配，返回相关结果
        if not results:
            for key, value in self.search_db.items():
                if any(word in key for word in query.split()):
                    results.append({
                        "title": key.title(),
                        "content": value,
                        "source": "模拟搜索引擎"
                    })
        
        return results[:max_results]
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="搜索查询词",
                    required=True
                ),
                ToolParameter(
                    name="max_results",
                    type="number",
                    description="最大返回结果数",
                    required=False,
                    default=5
                )
            ],
            returns="搜索结果列表，每个结果包含title、content和source字段"
        )

class WeatherTool(BaseTool):
    """天气查询工具（模拟）"""
    
    def __init__(self):
        super().__init__(
            name="weather",
            description="查询指定位置的天气信息"
        )
        # 模拟天气数据
        self.weather_db = {
            "北京": {"temp": 25, "condition": "晴", "humidity": 60, "wind": "东北风3级"},
            "上海": {"temp": 28, "condition": "多云", "humidity": 70, "wind": "东南风2级"},
            "广州": {"temp": 32, "condition": "晴", "humidity": 80, "wind": "南风1级"},
            "深圳": {"temp": 30, "condition": "小雨", "humidity": 85, "wind": "西南风2级"},
            "成都": {"temp": 22, "condition": "阴", "humidity": 75, "wind": "西北风1级"},
            "杭州": {"temp": 26, "condition": "晴", "humidity": 65, "wind": "东风2级"},
            "南京": {"temp": 24, "condition": "多云", "humidity": 68, "wind": "北风2级"},
            "武汉": {"temp": 27, "condition": "晴", "humidity": 72, "wind": "南风1级"}
        }
    
    async def execute(self, location: str) -> str:
        """查询天气"""
        location = location.strip()
        
        # 模拟网络延迟
        await asyncio.sleep(random.uniform(0.2, 0.5))
        
        # 查找天气数据
        if location in self.weather_db:
            weather = self.weather_db[location]
            return f"{location}今天{weather['condition']}，温度{weather['temp']}°C，湿度{weather['humidity']}%，{weather['wind']}"
        
        # 如果没有找到，生成模拟数据
        conditions = ["晴", "多云", "阴", "小雨", "中雨"]
        winds = ["北风", "东北风", "东风", "东南风", "南风", "西南风", "西风", "西北风"]
        
        temp = random.randint(15, 35)
        condition = random.choice(conditions)
        humidity = random.randint(40, 90)
        wind_level = random.randint(1, 5)
        wind_dir = random.choice(winds)
        
        return f"{location}今天{condition}，温度{temp}°C，湿度{humidity}%，{wind_dir}{wind_level}级"
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="location",
                    type="string",
                    description="要查询的城市名称，例如: '北京', '上海', '广州'",
                    required=True
                )
            ],
            returns="天气信息的字符串描述"
        )

class FileSystemTool(BaseTool):
    """文件系统工具"""
    
    def __init__(self):
        super().__init__(
            name="filesystem",
            description="文件系统操作工具，支持读取、写入和列出文件"
        )
    
    async def execute(self, operation: str, path: str, content: Optional[str] = None) -> Any:
        """执行文件系统操作"""
        operation = operation.lower()
        
        try:
            if operation == "read":
                # 读取文件
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            elif operation == "write":
                # 写入文件
                if content is None:
                    return "错误: 写入操作需要提供content参数"
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return f"文件 {path} 写入成功"
            
            elif operation == "list":
                # 列出目录
                import os
                if os.path.isdir(path):
                    files = os.listdir(path)
                    return {
                        "path": path,
                        "files": files,
                        "is_directory": True
                    }
                else:
                    return {
                        "path": path,
                        "error": "路径不是目录",
                        "is_directory": False
                    }
            
            elif operation == "exists":
                # 检查文件是否存在
                import os
                return os.path.exists(path)
            
            else:
                return f"不支持的操作: {operation}"
        
        except Exception as e:
            return f"文件操作错误: {str(e)}"
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="operation",
                    type="string",
                    description="操作类型: 'read' (读取), 'write' (写入), 'list' (列出), 'exists' (检查存在)",
                    required=True,
                    enum=["read", "write", "list", "exists"]
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="文件或目录路径",
                    required=True
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="写入文件的内容（仅write操作需要）",
                    required=False
                )
            ],
            returns="操作结果，根据操作类型返回不同格式的数据"
        )

class TimeTool(BaseTool):
    """时间工具"""
    
    def __init__(self):
        super().__init__(
            name="time",
            description="获取当前时间信息"
        )
    
    async def execute(self, format: str = "%Y-%m-%d %H:%M:%S", timezone: str = "UTC") -> str:
        """获取当前时间"""
        try:
            if timezone.upper() == "UTC":
                from datetime import timezone as tz
                current_time = datetime.now(tz.utc)
            else:
                current_time = datetime.now()
            
            return current_time.strftime(format)
        except Exception as e:
            return f"时间格式化错误: {str(e)}"
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="format",
                    type="string",
                    description="时间格式字符串，例如: '%Y-%m-%d %H:%M:%S'",
                    required=False,
                    default="%Y-%m-%d %H:%M:%S"
                ),
                ToolParameter(
                    name="timezone",
                    type="string",
                    description="时区，例如: 'UTC', 'local'",
                    required=False,
                    default="UTC"
                )
            ],
            returns="格式化的时间字符串"
        )

class RandomTool(BaseTool):
    """随机数工具"""
    
    def __init__(self):
        super().__init__(
            name="random",
            description="生成随机数"
        )
    
    async def execute(self, type: str = "int", min_value: float = 0, max_value: float = 100) -> float:
        """生成随机数"""
        try:
            if type == "int":
                return random.randint(int(min_value), int(max_value))
            elif type == "float":
                return random.uniform(min_value, max_value)
            else:
                raise ValueError(f"不支持的随机数类型: {type}")
        except Exception as e:
            raise Exception(f"随机数生成错误: {str(e)}")
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="type",
                    type="string",
                    description="随机数类型: 'int' (整数) 或 'float' (浮点数)",
                    required=False,
                    default="int",
                    enum=["int", "float"]
                ),
                ToolParameter(
                    name="min_value",
                    type="number",
                    description="最小值",
                    required=False,
                    default=0
                ),
                ToolParameter(
                    name="max_value",
                    type="number",
                    description="最大值",
                    required=False,
                    default=100
                )
            ],
            returns="生成的随机数"
        )

# 工具工厂
class ToolFactory:
    """工具工厂，用于创建常用工具"""
    
    @staticmethod
    def create_default_tools() -> Dict[str, ITool]:
        """创建默认工具集合"""
        return {
            "calculator": CalculatorTool(),
            "search": SearchTool(),
            "weather": WeatherTool(),
            "filesystem": FileSystemTool(),
            "time": TimeTool(),
            "random": RandomTool()
        }
    
    @staticmethod
    def create_tool(tool_name: str) -> Optional[ITool]:
        """根据名称创建工具"""
        tools = ToolFactory.create_default_tools()
        return tools.get(tool_name)

# ==================== 工具管理器实现 ====================

class ToolManager(IToolManager):
    """工具管理器实现"""
    
    def __init__(self):
        self._tools: Dict[str, ITool] = {}
        self._tool_registry = ToolRegistry()
        self._execution_stats = ToolExecutionStats()
        self.logger = logging.getLogger(__name__)
    
    async def register_tool(self, tool: ITool, category: str = "general") -> None:
        """注册工具"""
        await self._tool_registry.register(tool)
        self._tools[tool.get_schema().name] = tool
        self.logger.info(f"工具 {tool.get_schema().name} 注册成功")
    
    async def unregister_tool(self, tool_name: str) -> None:
        """注销工具"""
        if tool_name in self._tools:
            await self._tool_registry.unregister(tool_name)
            del self._tools[tool_name]
            self.logger.info(f"工具 {tool_name} 注销成功")
    
    async def call_tool(
        self, 
        tool_name: str, 
        parameters: Dict[str, Any],
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """调用工具"""
        if tool_name not in self._tools:
            return ToolResult(
                tool_name=tool_name,
                result=None,
                success=False,
                error_message=f"工具 {tool_name} 不存在"
            )
        
        tool = self._tools[tool_name]
        
        # 参数验证
        is_valid, error_message = tool.validate_parameters(parameters)
        if not is_valid:
            return ToolResult(
                tool_name=tool_name,
                result=None,
                success=False,
                error_message=f"参数验证失败: {error_message}"
            )
        
        # 执行统计
        start_time = time.time()
        
        try:
            result = await tool.execute(**parameters)
            execution_time = time.time() - start_time
            
            await self._execution_stats.record_success(
                tool_name, execution_time, result
            )
            
            return ToolResult(
                tool_name=tool_name,
                result=result,
                success=True,
                execution_time=execution_time
            )
        except Exception as e:
            execution_time = time.time() - start_time
            await self._execution_stats.record_failure(tool_name, execution_time, e)
            
            return ToolResult(
                tool_name=tool_name,
                result=None,
                success=False,
                error_message=f"工具执行失败: {str(e)}",
                execution_time=execution_time
            )
    
    def list_tools(self, filters: Optional[Dict[str, Any]] = None) -> List[ToolInfo]:
        """列出可用工具"""
        tools = list(self._tools.values())
        
        if filters:
            tools = self._apply_filters(tools, filters)
        
        return [ToolInfo.from_tool(tool) for tool in tools]
    
    def _apply_filters(self, tools: List[ITool], filters: Dict[str, Any]) -> List[ITool]:
        """应用过滤器"""
        filtered_tools = []
        
        for tool in tools:
            schema = tool.get_schema()
            
            # 按名称过滤
            if "name" in filters and filters["name"] not in schema.name:
                continue
            
            # 按描述过滤
            if "description" in filters and filters["description"] not in schema.description:
                continue
            
            # 按类别过滤
            if "category" in filters:
                # 这里需要扩展工具接口以支持类别
                pass
            
            filtered_tools.append(tool)
        
        return filtered_tools

class ToolRegistry(IToolRegistry):
    """工具注册中心实现"""
    
    def __init__(self):
        self._registered_tools: Dict[str, ToolRegistration] = {}
        self._dependencies: Dict[str, List[str]] = {}
        self._version_manager = VersionManager()
        self.logger = logging.getLogger(__name__)
    
    async def register(self, tool: ITool) -> None:
        """注册工具"""
        registration = ToolRegistration.from_tool(tool)
        
        # 检查依赖
        await self._check_dependencies(tool)
        
        # 版本检查
        await self._version_manager.check_compatibility(tool)
        
        # 注册工具
        self._registered_tools[tool.get_schema().name] = registration
        self.logger.info(f"工具 {tool.get_schema().name} 注册到注册中心")
    
    async def unregister(self, tool_name: str) -> None:
        """注销工具"""
        if tool_name in self._registered_tools:
            del self._registered_tools[tool_name]
            self.logger.info(f"工具 {tool_name} 从注册中心注销")
    
    async def get_tool_info(self, tool_name: str) -> ToolInfo:
        """获取工具信息"""
        if tool_name not in self._registered_tools:
            raise ValueError(f"工具 {tool_name} 未找到")
        
        registration = self._registered_tools[tool_name]
        return ToolInfo(
            name=registration.tool_info.name,
            description=registration.tool_info.description,
            parameters=registration.tool_info.parameters,
            category="general",  # 需要从注册信息中获取
            version=registration.version
        )
    
    async def discover_tools(self, search_paths: List[str]) -> None:
        """自动发现工具"""
        for path in search_paths:
            tools = await self._scan_directory(path)
            for tool_class in tools:
                try:
                    tool = tool_class()
                    await self.register(tool)
                except Exception as e:
                    self.logger.error(f"注册工具 {tool_class.__name__} 失败: {e}")
    
    async def _check_dependencies(self, tool: ITool) -> None:
        """检查工具依赖"""
        # 这里可以实现依赖检查逻辑
        pass
    
    async def _scan_directory(self, path: str) -> List[type]:
        """扫描目录中的工具"""
        tools = []
        path_obj = Path(path)
        
        if not path_obj.exists():
            self.logger.warning(f"工具搜索路径不存在: {path}")
            return tools
        
        # 扫描Python文件
        for py_file in path_obj.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            
            try:
                # 动态导入模块
                module_name = py_file.stem
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # 查找工具类
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, ITool) and 
                        obj != ITool):
                        tools.append(obj)
                        
            except Exception as e:
                self.logger.error(f"扫描文件 {py_file} 失败: {e}")
        
        return tools

class VersionManager:
    """版本管理器"""
    
    def __init__(self):
        self.compatibility_matrix = {
            "1.0.0": ["1.0.0", "1.1.0"],
            "1.1.0": ["1.1.0", "1.2.0"]
        }
    
    async def check_compatibility(self, tool: ITool) -> None:
        """检查工具版本兼容性"""
        # 这里可以实现版本兼容性检查
        pass

class ToolIntegration:
    """工具集成类"""
    
    def __init__(self, tool_manager: ToolManager):
        self.tool_manager = tool_manager
    
    async def call_tool(
        self, 
        tool_name: str, 
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> Any:
        """统一的工具调用接口"""
        result = await self.tool_manager.call_tool(tool_name, parameters, context)
        if result.success:
            return result.result
        else:
            raise Exception(f"工具调用失败: {result.error_message}")
    
    async def batch_call_tools(
        self, 
        tool_calls: List[Dict[str, Any]]
    ) -> List[Any]:
        """批量工具调用"""
        tasks = []
        for call in tool_calls:
            task = self.call_tool(
                call["tool_name"], 
                call["parameters"], 
                call.get("context")
            )
            tasks.append(task)
        
        return await asyncio.gather(*tasks)
    
    async def chain_tools(
        self, 
        tool_chain: List[Dict[str, Any]]
    ) -> Any:
        """工具链调用"""
        result = None
        for call in tool_chain:
            if result is not None:
                # 将前一个工具的结果作为下一个工具的参数
                call["parameters"]["previous_result"] = result
            
            result = await self.call_tool(
                call["tool_name"], 
                call["parameters"], 
                call.get("context")
            )
        
        return result

# ==================== 增强的工具实现 ====================

class EnhancedCalculatorTool(CalculatorTool):
    """增强的计算器工具"""
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="expression",
                    type="string",
                    description="数学表达式，例如: '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)'",
                    required=True
                ),
                ToolParameter(
                    name="precision",
                    type="number",
                    description="结果精度（小数位数）",
                    required=False,
                    default=2
                )
            ],
            returns="计算结果的字符串表示"
        )
    
    async def execute(self, expression: str, precision: int = 2) -> str:
        """执行数学计算"""
        try:
            # 安全地评估数学表达式
            allowed_names = {
                k: v for k, v in math.__dict__.items() 
                if not k.startswith("_")
            }
            allowed_names.update({
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "sum": sum
            })
            
            # 编译并执行表达式
            code = compile(expression, "<string>", "eval")
            
            # 检查是否只使用了允许的变量
            for name in code.co_names:
                if name not in allowed_names:
                    raise NameError(f"不允许使用 '{name}'")
            
            result = eval(code, {"__builtins__": {}}, allowed_names)
            
            # 应用精度
            if isinstance(result, float):
                result = round(result, precision)
            
            return str(result)
            
        except Exception as e:
            return f"计算错误: {str(e)}"

class EnhancedFileSystemTool(FileSystemTool):
    """增强的文件系统工具"""
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="operation",
                    type="string",
                    description="操作类型: 'read' (读取), 'write' (写入), 'list' (列出), 'exists' (检查存在), 'copy' (复制), 'move' (移动)",
                    required=True,
                    enum=["read", "write", "list", "exists", "copy", "move"]
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="文件或目录路径",
                    required=True
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="文件内容（仅write操作需要）",
                    required=False
                ),
                ToolParameter(
                    name="destination",
                    type="string",
                    description="目标路径（copy和move操作需要）",
                    required=False
                )
            ],
            returns="操作结果，根据操作类型返回不同格式的数据"
        )
    
    async def execute(self, operation: str, path: str, content: Optional[str] = None, destination: Optional[str] = None) -> Any:
        """执行文件系统操作"""
        operation = operation.lower()
        
        try:
            if operation == "read":
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            elif operation == "write":
                if content is None:
                    return "错误: 写入操作需要提供content参数"
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return f"文件 {path} 写入成功"
            
            elif operation == "list":
                import os
                if os.path.isdir(path):
                    files = os.listdir(path)
                    return {
                        "path": path,
                        "files": files,
                        "is_directory": True
                    }
                else:
                    return {
                        "path": path,
                        "error": "路径不是目录",
                        "is_directory": False
                    }
            
            elif operation == "exists":
                import os
                return os.path.exists(path)
            
            elif operation == "copy":
                import shutil
                if destination is None:
                    return "错误: 复制操作需要提供destination参数"
                
                shutil.copy2(path, destination)
                return f"文件 {path} 复制到 {destination} 成功"
            
            elif operation == "move":
                import shutil
                if destination is None:
                    return "错误: 移动操作需要提供destination参数"
                
                shutil.move(path, destination)
                return f"文件 {path} 移动到 {destination} 成功"
            
            else:
                return f"不支持的操作: {operation}"
        
        except Exception as e:
            return f"文件操作错误: {str(e)}"

# 更新工具工厂
class EnhancedToolFactory(ToolFactory):
    """增强的工具工厂"""
    
    @staticmethod
    def create_default_tools() -> Dict[str, ITool]:
        """创建默认工具集合"""
        return {
            "calculator": EnhancedCalculatorTool(),
            "search": SearchTool(),
            "weather": WeatherTool(),
            "filesystem": EnhancedFileSystemTool(),
            "time": TimeTool(),
            "random": RandomTool()
        }
    
    @staticmethod
    def create_enhanced_tools() -> Dict[str, ITool]:
        """创建增强工具集合"""
        tools = EnhancedToolFactory.create_default_tools()
        
        # 可以添加更多增强工具
        return tools

# 便捷函数
async def create_tool_manager() -> ToolManager:
    """创建工具管理器"""
    return ToolManager()

async def create_tool_registry() -> ToolRegistry:
    """创建工具注册中心"""
    return ToolRegistry()

def create_tool_integration(tool_manager: ToolManager) -> ToolIntegration:
    """创建工具集成"""
    return ToolIntegration(tool_manager)