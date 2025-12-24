"""
API路由模块

这个模块包含所有的API路由定义，按版本组织。
主要版本为v1，包含所有的RESTful API端点。
"""

# 延迟导入以避免循环依赖
def get_api_router():
    from .v1 import api_router
    return api_router

# 为了向后兼容，直接导入（如果可能）
try:
    from .v1 import api_router
except ImportError:
    api_router = None

__all__ = ["api_router", "get_api_router"]