"""
StoryMaster 应用启动脚本

提供便捷的开发和生产环境启动功能，包括：
- 开发环境热重载
- 生产环境优化配置
- 环境检查
- 依赖验证
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn

# 修复Windows控制台编码问题
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())


def check_python_version() -> bool:
    """
    检查Python版本是否满足要求
    
    Returns:
        bool: 版本是否满足要求
    """
    required_version = (3, 9)
    current_version = sys.version_info[:2]
    
    if current_version < required_version:
        print(f"❌ Python版本过低: {'.'.join(map(str, current_version))}")
        print(f"   需要Python版本: {'.'.join(map(str, required_version))} 或更高")
        return False
    
    print(f"✅ Python版本检查通过: {'.'.join(map(str, current_version))}")
    return True


def check_env_file() -> bool:
    """
    检查环境变量文件是否存在
    
    Returns:
        bool: 环境文件是否存在
    """
    env_dir = Path(__file__).resolve().parent
    env_file = env_dir / ".env"
    env_example = env_dir / ".env.example"
    
    if not env_file.exists():
        if env_example.exists():
            print("⚠️  未找到.env文件，但存在.env.example")
            print("   请复制.env.example为.env并配置相应的环境变量")
            
            # 询问是否自动复制
            try:
                response = input("   是否自动复制.env.example到.env? (y/n): ").lower().strip()
                if response in ['y', 'yes', '是']:
                    import shutil
                    shutil.copy(env_example, env_file)
                    os.chdir(env_dir)
                    print("✅ 已复制.env.example到.env")
                    print("   请编辑.env文件配置您的环境变量")
                    return True
                else:
                    print("   请手动创建.env文件")
                    return False
            except KeyboardInterrupt:
                print("\n操作已取消")
                return False
        else:
            print("❌ 未找到.env和.env.example文件")
            print("   请创建.env文件配置环境变量")
            return False
    
    print("✅ 环境变量文件检查通过")
    return True


def check_dependencies() -> List[str]:
    """
    检查关键依赖是否已安装
    
    Returns:
        List[str]: 缺失的依赖列表
    """
    missing_deps = []
    
    # 检查关键依赖
    try:
        import fastapi
        print("✅ FastAPI已安装")
    except ImportError:
        missing_deps.append("fastapi")
    
    try:
        import uvicorn
        print("✅ Uvicorn已安装")
    except ImportError:
        missing_deps.append("uvicorn")
    
    try:
        import pydantic
        print("✅ Pydantic已安装")
    except ImportError:
        missing_deps.append("pydantic")
    
    try:
        import neo4j
        print("✅ Neo4j驱动已安装")
    except ImportError:
        missing_deps.append("neo4j")
    
    try:
        import redis
        print("✅ Redis客户端已安装")
    except ImportError:
        missing_deps.append("redis")
    
    if missing_deps:
        print(f"❌ 缺失依赖: {', '.join(missing_deps)}")
        print("   请运行: pip install -r requirements.txt")
    
    return missing_deps


def start_dev_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = True) -> None:
    """
    启动开发服务器
    
    Args:
        host: 监听主机
        port: 监听端口
        reload: 是否启用热重载
    """
    print(f"🚀 启动开发服务器: http://{host}:{port}")
    print("   开发模式启用热重载")
    
    uvicorn.run(
        "StoryMaster.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        access_log=True,
        use_colors=True,
    )


def start_prod_server(host: str = "0.0.0.0", port: int = 8000, workers: int = 4) -> None:
    """
    启动生产服务器
    
    Args:
        host: 监听主机
        port: 监听端口
        workers: 工作进程数
    """
    print(f"🚀 启动生产服务器: http://{host}:{port}")
    print(f"   工作进程数: {workers}")
    
    uvicorn.run(
        "StoryMaster.main:app",
        host=host,
        port=port,
        workers=workers,
        log_level="warning",
        access_log=False,
        use_colors=False,
        limit_concurrency=1000,
        limit_max_requests=1000,
        limit_max_requests_jitter=100,
        timeout_keep_alive=5,
    )


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(description="StoryMaster D&D AI跑团应用启动脚本")
    
    # 环境参数
    parser.add_argument(
        "--env", 
        choices=["dev", "development", "prod", "production"],
        default="dev",
        help="运行环境 (默认: dev)"
    )
    
    # 服务器参数
    parser.add_argument("--host", default="0.0.0.0", help="监听主机 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认: 8000)")
    
    # 开发环境参数
    parser.add_argument("--no-reload", action="store_true", help="禁用热重载")
    
    # 生产环境参数
    parser.add_argument("--workers", type=int, default=4, help="工作进程数 (默认: 4)")
    
    # 检查参数
    parser.add_argument("--check-only", action="store_true", help="仅运行环境检查，不启动服务器")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("StoryMaster D&D AI跑团应用启动检查")
    print("=" * 60)
    
    # 运行环境检查
    checks_passed = True
    
    checks_passed &= check_python_version()
    checks_passed &= check_env_file()
    
    missing_deps = check_dependencies()
    if missing_deps:
        checks_passed = False
    
    print("=" * 60)
    
    if not checks_passed:
        print("❌ 环境检查失败，请修复后重试")
        sys.exit(1)
    
    if args.check_only:
        print("✅ 环境检查通过")
        return
    
    # 设置环境
    env = args.env.lower()
    if env in ["dev", "development"]:
        os.environ["ENVIRONMENT"] = "development"
        
        print("🔧 开发环境配置:")
        print(f"   主机: {args.host}")
        print(f"   端口: {args.port}")
        print(f"   热重载: {not args.no_reload}")
        print()
        
        start_dev_server(
            host=args.host,
            port=args.port,
            reload=not args.no_reload
        )
        
    elif env in ["prod", "production"]:
        os.environ["ENVIRONMENT"] = "production"
        
        print("🏭 生产环境配置:")
        print(f"   主机: {args.host}")
        print(f"   端口: {args.port}")
        print(f"   工作进程: {args.workers}")
        print()
        
        start_prod_server(
            host=args.host,
            port=args.port,
            workers=args.workers
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        sys.exit(1)