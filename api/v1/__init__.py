"""
API v1 版本路由模块

这是API的第一个版本，包含所有的v1端点。
每个功能模块都有独立的路由文件，然后在这里汇总。
"""

from fastapi import APIRouter

# 导入各个功能模块的路由
from .health import router as health_router
from .rulebooks import router as rulebooks_router
# from .auth import router as auth_router
# from .characters import router as characters_router
# from .sessions import router as sessions_router
# from .agents import router as agents_router

# 创建v1 API路由器
api_router = APIRouter(prefix="/api/v1", tags=["v1"])

# 注册各个模块的路由
api_router.include_router(health_router, tags=["health"])
api_router.include_router(rulebooks_router, tags=["rulebooks"])
# api_router.include_router(auth_router, prefix="/auth", tags=["authentication"])
# api_router.include_router(characters_router, prefix="/characters", tags=["characters"])
# api_router.include_router(sessions_router, prefix="/sessions", tags=["game sessions"])
# api_router.include_router(agents_router, prefix="/agents", tags=["AI agents"])

__all__ = ["api_router"]