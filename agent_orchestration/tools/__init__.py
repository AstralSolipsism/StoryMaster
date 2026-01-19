"""
智能体工具包
注意：此目录包含规则书解析工具。
基础工具类和工具管理器通过 tools.py 文件提供。
"""

# 导入规则书解析工具（从子目录）
from .rulebook_parser import (
    RulebookParserTool,
    SchemaValidationTool,
    ContentExtractionTool,
    register_rulebook_parser_tools
)

# 从 tools.py 文件导入基础工具和管理器
import sys
import os
import importlib.util

# 获取 tools.py 的完整路径
current_dir = os.path.dirname(os.path.abspath(__file__))
tools_py_path = os.path.join(os.path.dirname(current_dir), 'tools.py')

# 动态导入 tools.py 模块
spec = importlib.util.spec_from_file_location("agent_orchestration._tools_impl", tools_py_path)
if spec and spec.loader:
    _tools_impl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_tools_impl)
    
    # 导出所有工具类和管理器
    BaseTool = _tools_impl.BaseTool
    CalculatorTool = _tools_impl.CalculatorTool
    SearchTool = _tools_impl.SearchTool
    WeatherTool = _tools_impl.WeatherTool
    FileSystemTool = _tools_impl.FileSystemTool
    TimeTool = _tools_impl.TimeTool
    RandomTool = _tools_impl.RandomTool
    ToolManager = _tools_impl.ToolManager
    ToolRegistry = _tools_impl.ToolRegistry
    ToolFactory = _tools_impl.ToolFactory
    ToolIntegration = _tools_impl.ToolIntegration
    EnhancedCalculatorTool = _tools_impl.EnhancedCalculatorTool
    EnhancedFileSystemTool = _tools_impl.EnhancedFileSystemTool
    EnhancedToolFactory = _tools_impl.EnhancedToolFactory
    create_tool_manager = _tools_impl.create_tool_manager
    create_tool_registry = _tools_impl.create_tool_registry
    create_tool_integration = _tools_impl.create_tool_integration
    PathSecurityValidator = _tools_impl.PathSecurityValidator
else:
    raise ImportError(f"无法加载 tools.py: {tools_py_path}")

__all__ = [
    # 基础工具类
    "BaseTool",
    "CalculatorTool",
    "SearchTool",
    "WeatherTool",
    "FileSystemTool",
    "TimeTool",
    "RandomTool",
    # 工具管理器
    "ToolManager",
    "ToolRegistry",
    "ToolFactory",
    "ToolIntegration",
    # 增强工具
    "EnhancedCalculatorTool",
    "EnhancedFileSystemTool",
    "EnhancedToolFactory",
    # 便捷函数
    "create_tool_manager",
    "create_tool_registry",
    "create_tool_integration",
    # 工具类
    "PathSecurityValidator",
    # 规则书解析工具
    "RulebookParserTool",
    "SchemaValidationTool",
    "ContentExtractionTool",
    "register_rulebook_parser_tools",
]