"""
项目验证脚本

验证项目结构和配置是否正确，包括：
- Python版本检查
- 依赖检查
- 模块导入检查
- 配置文件验证
- 基本功能测试
"""

import sys
import os
import importlib
from pathlib import Path
from typing import List, Tuple, Dict, Any


def check_python_version() -> Tuple[bool, str]:
    """检查Python版本"""
    required_version = (3, 9)
    current_version = sys.version_info[:2]
    
    if current_version >= required_version:
        return True, f"✅ Python版本: {'.'.join(map(str, current_version))} (满足要求)"
    else:
        return False, f"❌ Python版本过低: {'.'.join(map(str, current_version))} (需要 >= 3.9)"


def check_file_structure() -> List[Tuple[bool, str]]:
    """检查项目文件结构"""
    results = []
    
    required_files = [
        "main.py",
        "requirements.txt",
        "pyproject.toml",
        ".env.example",
        "README.md",
        "core/__init__.py",
        "core/config.py",
        "core/logging.py",
        "core/database.py",
        "core/exceptions.py",
        "api/__init__.py",
        "api/v1/__init__.py",
        "api/v1/health.py",
        "schemas/__init__.py",
        "services/__init__.py",
        "logs/.gitkeep",
    ]
    
    for file_path in required_files:
        if Path(file_path).exists():
            results.append((True, f"✅ {file_path}"))
        else:
            results.append((False, f"❌ {file_path} (缺失)"))
    
    return results


def check_module_imports() -> List[Tuple[bool, str]]:
    """检查关键模块是否可以正常导入"""
    results = []
    
    modules_to_check = [
        ("main", "主模块"),
        ("core.config", "配置模块"),
        ("core.logging", "日志模块"),
        ("core.database", "数据库模块"),
        ("core.exceptions", "异常处理模块"),
        ("api", "API模块"),
        ("api.v1.health", "健康检查模块"),
    ]
    
    for module_name, description in modules_to_check:
        try:
            importlib.import_module(module_name)
            results.append((True, f"✅ {description} ({module_name})"))
        except ImportError as e:
            results.append((False, f"❌ {description} ({module_name}): {e}"))
    
    return results


def check_dependencies() -> List[Tuple[bool, str]]:
    """检查关键依赖是否已安装"""
    results = []
    
    dependencies_to_check = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("pydantic", "Pydantic"),
        ("pydantic_settings", "Pydantic Settings"),
        ("structlog", "Structlog"),
        ("neo4j", "Neo4j"),
        ("redis", "Redis"),
        ("psutil", "Psutil"),
    ]
    
    for module_name, description in dependencies_to_check:
        try:
            importlib.import_module(module_name)
            results.append((True, f"✅ {description}"))
        except ImportError:
            results.append((False, f"❌ {description} ({module_name})"))
    
    return results


def check_configuration() -> List[Tuple[bool, str]]:
    """检查配置文件"""
    results = []
    
    # 检查.env.example文件
    env_example = Path(".env.example")
    if env_example.exists():
        results.append((True, "✅ .env.example文件存在"))
        
        # 检查.env.example内容
        content = env_example.read_text(encoding='utf-8')
        required_vars = [
            "ENVIRONMENT",
            "SECRET_KEY",
            "NEO4J_URI",
            "NEO4J_USER",
            "NEO4J_PASSWORD",
            "REDIS_URL",
            "LOG_LEVEL",
        ]
        
        missing_vars = []
        for var in required_vars:
            if var not in content:
                missing_vars.append(var)
        
        if missing_vars:
            results.append((False, f"❌ .env.example缺少变量: {', '.join(missing_vars)}"))
        else:
            results.append((True, "✅ .env.example包含必需的环境变量"))
    else:
        results.append((False, "❌ .env.example文件不存在"))
    
    # 检查.env文件（可选）
    env_file = Path(".env")
    if env_file.exists():
        results.append((True, "✅ .env文件存在"))
    else:
        results.append((False, "⚠️  .env文件不存在（可以运行时创建）"))
    
    return results


def validate_syntax() -> List[Tuple[bool, str]]:
    """验证Python文件语法"""
    results = []
    
    python_files = [
        "main.py",
        "run.py",
        "validate.py",
        "core/config.py",
        "core/logging.py",
        "core/database.py",
        "core/exceptions.py",
        "api/v1/health.py",
    ]
    
    for file_path in python_files:
        if Path(file_path).exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    compile(f.read(), file_path, 'exec')
                results.append((True, f"✅ {file_path} 语法正确"))
            except SyntaxError as e:
                results.append((False, f"❌ {file_path} 语法错误: {e}"))
    
    return results


def run_basic_functionality_test() -> List[Tuple[bool, str]]:
    """运行基本功能测试"""
    results = []
    
    try:
        # 测试配置加载
        from core.config import settings
        results.append((True, "✅ 配置模块加载成功"))
        
        # 测试日志系统
        from core.logging import setup_logging, get_logger
        setup_logging()
        logger = get_logger("test")
        results.append((True, "✅ 日志系统初始化成功"))
        
        # 测试异常处理
        from core.exceptions import StoryMasterException
        test_exception = StoryMasterException("测试异常")
        results.append((True, "✅ 异常处理模块正常"))
        
        # 测试API路由
        from api import get_api_router
        router = get_api_router()
        if router:
            results.append((True, "✅ API路由加载成功"))
        else:
            results.append((False, "❌ API路由加载失败"))
        
    except Exception as e:
        results.append((False, f"❌ 基本功能测试失败: {e}"))
    
    return results


def print_section(title: str, results: List[Tuple[bool, str]]) -> None:
    """打印检查结果部分"""
    print(f"\n{'='*60}")
    print(title)
    print('='*60)
    
    all_passed = True
    for passed, message in results:
        print(message)
        if not passed:
            all_passed = False
    
    if all_passed:
        print(f"✅ {title} - 全部通过")
    else:
        print(f"❌ {title} - 存在问题")
    
    return all_passed


def main() -> None:
    """主验证函数"""
    print("StoryMaster D&D AI跑团应用 - 项目验证")
    print("验证项目结构和配置是否正确...")
    
    all_checks_passed = True
    
    # 运行各项检查
    all_checks_passed &= print_section(
        "Python版本检查",
        [check_python_version()]
    )
    
    all_checks_passed &= print_section(
        "文件结构检查",
        check_file_structure()
    )
    
    all_checks_passed &= print_section(
        "模块导入检查",
        check_module_imports()
    )
    
    all_checks_passed &= print_section(
        "依赖检查",
        check_dependencies()
    )
    
    all_checks_passed &= print_section(
        "配置文件检查",
        check_configuration()
    )
    
    all_checks_passed &= print_section(
        "语法验证",
        validate_syntax()
    )
    
    all_checks_passed &= print_section(
        "基本功能测试",
        run_basic_functionality_test()
    )
    
    # 总结
    print(f"\n{'='*60}")
    if all_checks_passed:
        print("🎉 所有验证检查通过！项目已准备就绪。")
        print("\n下一步操作:")
        print("1. 复制 .env.example 到 .env 并配置环境变量")
        print("2. 启动Neo4j和Redis服务（如果尚未运行）")
        print("3. 运行: python run.py")
    else:
        print("❌ 验证检查发现问题，请修复后重试。")
    
    print('='*60)
    
    return 0 if all_checks_passed else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n验证已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n验证过程出错: {e}")
        sys.exit(1)