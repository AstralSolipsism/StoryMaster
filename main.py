"""
StoryMaster D&D AI跑团应用后端API主入口

这是FastAPI应用的主入口文件，负责：
- 初始化FastAPI应用实例
- 配置中间件
- 注册路由
- 设置应用生命周期事件
- 集成现有模块（agent_orchestration、data_storage、model_adapter）
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

# 导入现有模块（这些将在后续步骤中完成集成）
# from agent_orchestration import setup_agent_orchestration
# from data_storage import setup_data_storage
# from model_adapter import setup_model_adapter

# 导入路由和配置
from api import get_api_router
from core.config import settings
from core.logging import setup_logging, app_logger
from core.database import db_manager
from core.exceptions import setup_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理
    
    处理应用启动和关闭时的初始化和清理工作：
    - 启动时初始化数据库连接
    - 启动时加载AI模型配置
    - 关闭时清理资源
    """
    # 启动时的初始化工作
    app_logger.info("🚀 StoryMaster API 正在启动...")
    
    try:
        # 设置日志系统
        setup_logging()
        app_logger.info("日志系统初始化完成")
        
        # 初始化数据库连接
        await db_manager.initialize()
        app_logger.info("数据库连接初始化完成")
        
        # 初始化数据存储层
        # await setup_data_storage()
        
        # 初始化智能体编排系统
        # await setup_agent_orchestration()
        
        # 初始化模型适配器
        # await setup_model_adapter()
        
        app_logger.info("✅ StoryMaster API 启动完成")
        
        yield
        
    except Exception as e:
        app_logger.error(f"❌ StoryMaster API 启动失败: {e}", exc_info=True)
        raise
    
    finally:
        # 关闭时的清理工作
        app_logger.info("🔄 StoryMaster API 正在关闭...")
        
        try:
            # 清理数据库连接
            await db_manager.close()
            app_logger.info("数据库连接已关闭")
            
            # 清理AI模型资源
            # await cleanup_model_adapter()
            
            app_logger.info("✅ StoryMaster API 已安全关闭")
        except Exception as e:
            app_logger.error(f"关闭应用时出错: {e}", exc_info=True)


def create_application() -> FastAPI:
    """
    创建并配置FastAPI应用实例
    
    Returns:
        FastAPI: 配置好的应用实例
    """
    # 创建FastAPI应用实例
    app = FastAPI(
        title="StoryMaster API",
        description="StoryMaster D&D AI跑团应用后端API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # 配置CORS中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # 从配置文件读取
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count"],  # 暴露自定义头部
    )
    
    # 配置受信任主机中间件（生产环境）
    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts
        )
    
    # 设置异常处理器
    setup_exception_handlers(app)
    app_logger.info("异常处理器已配置")
    
    # 注册API路由
    api_router = get_api_router()
    if api_router:
        app.include_router(api_router)
        app_logger.info("API路由已注册")
    
    # 设置应用启动时间（用于健康检查）
    from api.v1.health import set_app_start_time
    set_app_start_time(datetime.now())
    
    # 添加基础信息端点
    @app.get("/")
    async def root():
        return {
            "message": "StoryMaster API is running",
            "version": "0.1.0",
            "environment": settings.environment,
            "docs": "/docs",
            "health": "/api/v1/health",
            "openapi": "/openapi.json"
        }
    
    return app


# 创建应用实例
app = create_application()


if __name__ == "__main__":
    import uvicorn
    
    # 开发环境运行配置
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,  # 开发时启用热重载
        log_level=settings.log_level.lower(),
    )