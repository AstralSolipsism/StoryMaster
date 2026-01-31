"""
自定义异常类和全局异常处理器

提供：
- 自定义异常类
- 全局异常处理器
- 统一错误响应格式
- 异常日志记录
"""

import traceback
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
from pydantic import ValidationError as PydanticValidationError
import pydantic

from .logging import app_logger, log_exception_alert


class StoryMasterException(Exception):
    """
    StoryMaster基础异常类
    
    所有自定义异常的基类。
    """
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class StoryMasterValidationError(StoryMasterException):
    """数据验证错误"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class AuthenticationError(StoryMasterException):
    """认证错误"""
    def __init__(self, message: str = "认证失败"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class AuthorizationError(StoryMasterException):
    """授权错误"""
    def __init__(self, message: str = "权限不足"):
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            status_code=status.HTTP_403_FORBIDDEN
        )


class NotFoundError(StoryMasterException):
    """资源未找到错误"""
    def __init__(self, message: str, resource_type: str = "资源"):
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource_type": resource_type}
        )


class ConflictError(StoryMasterException):
    """资源冲突错误"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details
        )


class DatabaseError(StoryMasterException):
    """数据库操作错误"""
    def __init__(self, message: str, operation: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"operation": operation} if operation else {}
        )


class ExternalServiceError(StoryMasterException):
    """外部服务错误"""
    def __init__(
        self, 
        message: str, 
        service_name: str, 
        status_code: int = status.HTTP_503_SERVICE_UNAVAILABLE
    ):
        super().__init__(
            message=message,
            error_code="EXTERNAL_SERVICE_ERROR",
            status_code=status_code,
            details={"service_name": service_name}
        )


class RateLimitError(StoryMasterException):
    """速率限制错误"""
    def __init__(self, message: str = "请求过于频繁", retry_after: Optional[int] = None):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after": retry_after} if retry_after else {}
        )


class ErrorResponse:
    """标准错误响应格式"""
    
    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        self.request_id = request_id
    
    def dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        response = {
            "error": {
                "message": self.message,
                "code": self.error_code,
                "status_code": self.status_code,
                "details": self.details
            }
        }
        
        if self.request_id:
            response["request_id"] = self.request_id
        
        return response


def setup_exception_handlers(app: FastAPI) -> None:
    """
    设置全局异常处理器
    
    Args:
        app: FastAPI应用实例
    """
    
    @app.exception_handler(StoryMasterException)
    async def storymaster_exception_handler(
        request: Request, 
        exc: StoryMasterException
    ) -> JSONResponse:
        """处理StoryMaster自定义异常"""
        request_id = getattr(request.state, "request_id", None)
        
        # 记录异常日志
        app_logger.error(
            f"StoryMaster异常: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "status_code": exc.status_code,
                "details": exc.details,
                "request_id": request_id,
                "path": str(request.url),
                "method": request.method
            }
        )
        if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            log_exception_alert(
                app_logger,
                "StoryMaster异常告警",
                alert_code=exc.error_code,
                severity="error",
                request_id=request_id,
                path=str(request.url),
                method=request.method,
            )
        
        # 返回标准错误响应
        error_response = ErrorResponse(
            message=exc.message,
            error_code=exc.error_code,
            status_code=exc.status_code,
            details=exc.details,
            request_id=request_id
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.dict()
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, 
        exc: HTTPException
    ) -> JSONResponse:
        """处理FastAPI HTTPException"""
        request_id = getattr(request.state, "request_id", None)
        
        # 记录HTTP异常日志
        app_logger.warning(
            f"HTTP异常: {exc.detail}",
            extra={
                "status_code": exc.status_code,
                "request_id": request_id,
                "path": str(request.url),
                "method": request.method
            }
        )
        if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            log_exception_alert(
                app_logger,
                "HTTP异常告警",
                alert_code="HTTP_ERROR",
                severity="error",
                request_id=request_id,
                path=str(request.url),
                method=request.method,
            )
        
        # 返回标准错误响应
        error_response = ErrorResponse(
            message=str(exc.detail),
            error_code="HTTP_ERROR",
            status_code=exc.status_code,
            details={"headers": dict(exc.headers)} if exc.headers else {},
            request_id=request_id
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.dict(),
            headers=exc.headers
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, 
        exc: RequestValidationError
    ) -> JSONResponse:
        """处理请求数据验证错误"""
        request_id = getattr(request.state, "request_id", None)
        
        # 提取验证错误详情
        validation_errors = []
        for error in exc.errors():
            validation_errors.append({
                "field": ".".join(str(x) for x in error["loc"]),
                "message": error["msg"],
                "type": error["type"]
            })
        
        # 记录验证错误日志
        app_logger.warning(
            f"请求验证错误: {len(validation_errors)}个字段验证失败",
            extra={
                "validation_errors": validation_errors,
                "request_id": request_id,
                "path": str(request.url),
                "method": request.method
            }
        )
        
        # 返回标准错误响应
        error_response = ErrorResponse(
            message="请求数据验证失败",
            error_code="REQUEST_VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"validation_errors": validation_errors},
            request_id=request_id
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response.dict()
        )
    
    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_exception_handler(
        request: Request,
        exc: PydanticValidationError
    ) -> JSONResponse:
        """处理Pydantic验证错误"""
        request_id = getattr(request.state, "request_id", None)
        
        # 记录验证错误日志
        app_logger.error(
            f"Pydantic验证错误: {exc}",
            extra={
                "request_id": request_id,
                "path": str(request.url),
                "method": request.method
            }
        )
        log_exception_alert(
            app_logger,
            "Pydantic验证异常告警",
            alert_code="PYDANTIC_VALIDATION_ERROR",
            severity="error",
            request_id=request_id,
            path=str(request.url),
            method=request.method,
        )
        
        # 返回标准错误响应
        error_response = ErrorResponse(
            message="数据验证失败",
            error_code="PYDANTIC_VALIDATION_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"validation_errors": exc.errors()},
            request_id=request_id
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.dict()
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, 
        exc: Exception
    ) -> JSONResponse:
        """处理未捕获的通用异常"""
        request_id = getattr(request.state, "request_id", None)
        
        # 获取异常堆栈
        stack_trace = traceback.format_exc()
        
        # 记录未捕获异常
        app_logger.error(
            f"未捕获异常: {type(exc).__name__}: {exc}",
            extra={
                "exception_type": type(exc).__name__,
                "stack_trace": stack_trace,
                "request_id": request_id,
                "path": str(request.url),
                "method": request.method
            }
        )
        log_exception_alert(
            app_logger,
            "未捕获异常告警",
            alert_code="UNHANDLED_EXCEPTION",
            severity="critical",
            exception_type=type(exc).__name__,
            request_id=request_id,
            path=str(request.url),
            method=request.method,
        )
        
        # 返回通用错误响应（不暴露内部错误详情）
        error_response = ErrorResponse(
            message="服务器内部错误",
            error_code="INTERNAL_SERVER_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={},  # 生产环境不暴露内部错误
            request_id=request_id
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.dict()
        )


# 导出异常类和函数
ValidationError = StoryMasterValidationError

__all__ = [
    "StoryMasterException",
    "StoryMasterValidationError",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ConflictError",
    "DatabaseError",
    "ExternalServiceError",
    "RateLimitError",
    "ErrorResponse",
    "setup_exception_handlers",
]