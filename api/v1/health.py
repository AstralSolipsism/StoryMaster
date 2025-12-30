"""
健康检查API路由

提供应用健康状态检查功能，包括：
- 基本应用信息
- 数据库连接状态
- 系统资源状态
- 服务依赖检查
"""

import platform
import psutil
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.config import settings
from core.database import db_manager

# 创建路由器
router = APIRouter()


class HealthStatus(BaseModel):
    """健康状态响应模型"""
    status: str
    timestamp: datetime
    version: str
    environment: str
    uptime: Optional[float] = None
    system: Dict[str, Any] = {}
    database: Dict[str, Any] = {}
    services: Dict[str, Any] = {}


class ComponentStatus(BaseModel):
    """组件状态模型"""
    status: str  # healthy, degraded, error
    message: str
    details: Optional[Dict[str, Any]] = None


# 应用启动时间（在main.py中设置）
app_start_time = datetime.now()


def set_app_start_time(time: datetime) -> None:
    """设置应用启动时间"""
    global app_start_time
    app_start_time = time


@router.get("/health", response_model=HealthStatus, tags=["health"])
async def health_check() -> HealthStatus:
    """
    健康检查端点
    
    返回应用的整体健康状态，包括系统信息和数据库状态。
    
    Returns:
        HealthStatus: 包含健康状态的响应对象
        
    Raises:
        HTTPException: 当关键服务不可用时
    """
    try:
        # 计算运行时间
        uptime = (datetime.now() - app_start_time).total_seconds()
        
        # 获取系统信息
        system_info = get_system_info()
        
        # 获取数据库健康状态
        database_status = await db_manager.health_check()
        
        # 获取服务状态
        services_status = await get_services_status()
        
        # 确定整体状态
        overall_status = determine_overall_status(database_status, services_status)
        
        return HealthStatus(
            status=overall_status,
            timestamp=datetime.now(),
            version="0.1.0",
            environment=settings.environment,
            uptime=uptime,
            system=system_info,
            database=database_status,
            services=services_status,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"健康检查失败: {str(e)}"
        )


@router.get("/health/simple", tags=["health"])
async def simple_health_check() -> Dict[str, str]:
    """
    简单健康检查端点
    
    用于负载均衡器等的简单健康检查，只返回基本状态。
    
    Returns:
        Dict[str, str]: 简单的状态信息
    """
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0"
    }


@router.get("/health/database", tags=["health"])
async def database_health_check() -> Dict[str, Any]:
    """
    数据库健康检查端点
    
    返回所有数据库的详细健康状态。
    
    Returns:
        Dict[str, Any]: 数据库健康状态信息
    """
    try:
        return await db_manager.health_check()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"数据库健康检查失败: {str(e)}"
        )


def get_system_info() -> Dict[str, Any]:
    """
    获取系统信息
    
    Returns:
        Dict[str, Any]: 系统信息字典
    """
    try:
        # CPU信息
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # 内存信息
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_total = memory.total
        memory_available = memory.available
        
        # 磁盘信息
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        disk_total = disk.total
        disk_free = disk.free
        
        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu": {
                "percent": round(cpu_percent, 2),
                "count": cpu_count,
            },
            "memory": {
                "percent": round(memory_percent, 2),
                "total_mb": round(memory_total / (1024 * 1024), 2),
                "available_mb": round(memory_available / (1024 * 1024), 2),
            },
            "disk": {
                "percent": round(disk_percent, 2),
                "total_gb": round(disk_total / (1024 * 1024 * 1024), 2),
                "free_gb": round(disk_free / (1024 * 1024 * 1024), 2),
            },
        }
        
    except Exception as e:
        return {
            "error": f"获取系统信息失败: {str(e)}",
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        }


async def get_services_status() -> Dict[str, Any]:
    """
    获取服务状态
    
    Returns:
        Dict[str, Any]: 服务状态字典
    """
    services = {}
    
    # 检查AI模型服务
    services.update(await check_ai_services())
    
    return services


async def check_ai_services() -> Dict[str, Any]:
    """
    检查AI模型服务状态
    
    Returns:
        Dict[str, Any]: AI服务状态
    """
    ai_services = {}
    
    # 检查OpenAI
    if settings.openai_api_key:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.openai_base_url}/models",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"}
                )
                if response.status_code == 200:
                    ai_services["openai"] = {
                        "status": "healthy",
                        "message": "API可访问"
                    }
                else:
                    ai_services["openai"] = {
                        "status": "error",
                        "message": f"API返回状态码: {response.status_code}"
                    }
        except Exception as e:
            ai_services["openai"] = {
                "status": "error",
                "message": str(e)
            }
    else:
        ai_services["openai"] = {
            "status": "disabled",
            "message": "未配置API密钥"
        }
    
    # 检查Ollama
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                ai_services["ollama"] = {
                    "status": "healthy",
                    "message": f"发现{len(models)}个模型",
                    "models": [model["name"] for model in models[:5]]  # 只显示前5个
                }
            else:
                ai_services["ollama"] = {
                    "status": "error",
                    "message": f"API返回状态码: {response.status_code}"
                }
    except Exception as e:
        ai_services["ollama"] = {
            "status": "error",
            "message": str(e)
        }
    
    return ai_services


def determine_overall_status(database_status: Dict[str, Any], services_status: Dict[str, Any]) -> str:
    """
    确定整体健康状态
    
    Args:
        database_status: 数据库状态
        services_status: 服务状态
        
    Returns:
        str: 整体状态（healthy, degraded, error）
    """
    # 检查关键服务状态
    critical_errors = []
    warnings = []
    
    # 检查数据库
    for db_name, status in database_status.items():
        if status["status"] == "error":
            critical_errors.append(f"{db_name}数据库错误")
        elif status["status"] != "healthy":
            warnings.append(f"{db_name}数据库状态异常")
    
    # 检查其他服务
    for service_name, status in services_status.items():
        if isinstance(status, dict) and status.get("status") == "error":
            critical_errors.append(f"{service_name}服务错误")
        elif isinstance(status, dict) and status.get("status") not in ["healthy", "disabled"]:
            warnings.append(f"{service_name}服务状态异常")
    
    # 确定整体状态
    if critical_errors:
        return "error"
    elif warnings:
        return "degraded"
    else:
        return "healthy"


# 导出路由器和函数
__all__ = ["router", "set_app_start_time"]