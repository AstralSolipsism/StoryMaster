"""
规则书上传和管理API端点
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...core.exceptions import StoryMasterValidationError, NotFoundError
from ...core.config import settings
from ...services.parsing_task_manager import ParsingTaskManager
from ...services.file_processor import FileProcessor
from ...models.parsing_models import (
    RulebookUploadRequest,
    RulebookUploadResponse,
    ParsingTaskStatus,
    RulebookParsingResult,
    RulebookConfirmationRequest
)
from ...core.logging import app_logger

router = APIRouter(prefix="/rulebooks", tags=["rulebooks"])

# 全局任务管理器实例（在应用启动时初始化）
_parsing_task_manager: Optional[ParsingTaskManager] = None

def get_parsing_task_manager(request: Request) -> ParsingTaskManager:
    """获取解析任务管理器实例"""
    global _parsing_task_manager
    provider_manager = getattr(request.app.state, "provider_manager", None)

    if _parsing_task_manager is None:
        # 延迟导入以避免循环依赖
        from ...services.parsing_task_manager import ParsingTaskManager as PTM
        from ...services.file_processor import FileProcessor as FP
        from ...services.schema_converter import SchemaConverter as SC
        from ...services.integrations.rulebook_parser_integration import RulebookParserIntegration

        try:
            from ...data_storage.rulebook_manager import RulebookManager as RM
            rulebook_manager = RM()
        except Exception:
            rulebook_manager = None

        _parsing_task_manager = PTM(
            file_processor=FP(),
            schema_converter=SC(),
            rulebook_manager=rulebook_manager,
            model_scheduler=provider_manager,
        )
    elif provider_manager and _parsing_task_manager.model_scheduler is None:
        _parsing_task_manager.model_scheduler = provider_manager

    return _parsing_task_manager


@router.post("/upload", response_model=RulebookUploadResponse)
async def upload_rulebook(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None, description="规则书文件（单文件上传）"),
    files: Optional[List[UploadFile]] = File(None, description="规则书文件列表（多文件上传）"),
    parser_model: Optional[str] = Form(None),
    user_id: str = Form(...),
    task_manager: ParsingTaskManager = Depends(get_parsing_task_manager)
):
    """
    上传规则书文件并启动解析任务（单文件/多文件统一入口）

    - **file**: 规则书文件 (支持PDF, Word, TXT, JSON, Markdown)
    - **files**: 规则书文件列表 (多文件时重复使用同名字段)
    - **parser_model**: 用于解析的AI模型 (gpt-4, gpt-3.5-turbo, claude-3, etc.)
    - **user_id**: 用户ID

    **支持的文件格式**:
    - PDF (.pdf)
    - Word (.docx)
    - 文本 (.txt)
    - JSON (.json)
    - Markdown (.md)
    """
    try:
        # 组装文件列表
        upload_files: List[UploadFile] = []
        if files:
            upload_files.extend(files)
        if file:
            upload_files.append(file)
        if not upload_files:
            raise StoryMasterValidationError("未提供文件")

        supported_formats = getattr(settings, 'supported_rulebook_formats', ['pdf', 'docx', 'txt', 'json', 'md'])
        max_size = getattr(settings, 'max_rulebook_file_size', 50)  # MB

        file_names = []
        file_types = []
        for upload_file in upload_files:
            if not upload_file.filename:
                raise StoryMasterValidationError("未提供文件名")
            file_ext = os.path.splitext(upload_file.filename)[1].lower().lstrip('.')
            if file_ext not in supported_formats:
                raise StoryMasterValidationError(
                    f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(supported_formats)}"
                )
            upload_file.file.seek(0, os.SEEK_END)
            file_size = upload_file.file.tell() / (1024 * 1024)
            upload_file.file.seek(0)
            if file_size > max_size:
                raise StoryMasterValidationError(
                    f"文件大小超出限制。最大允许: {max_size}MB，当前: {file_size:.2f}MB"
                )
            file_names.append(upload_file.filename)
            file_types.append(file_ext)

        effective_parser_model = parser_model or getattr(settings, "default_parser_model", None)
        provider_model = None
        provider_manager = getattr(task_manager, "model_scheduler", None)
        if provider_manager and hasattr(provider_manager, "provider_configs"):
            provider_config = provider_manager.provider_configs.get(
                provider_manager.config.default_provider
            ) or {}
            provider_model = provider_config.get("model")
        if provider_model and not parser_model:
            effective_parser_model = provider_model

        upload_request = RulebookUploadRequest(
            file_names=file_names if len(file_names) > 1 else None,
            file_types=file_types if len(file_types) > 1 else None,
            file_name=file_names[0],
            file_type=file_types[0],
            parser_model=effective_parser_model,
            user_id=user_id
        )

        task_id = await task_manager.create_parsing_task(upload_request.dict())

        if len(upload_files) == 1:
            background_tasks.add_task(task_manager.process_parsing_task, task_id, upload_files[0])
        else:
            background_tasks.add_task(task_manager.process_parsing_task_multi, task_id, upload_files)

        app_logger.info(f"规则书上传成功: {file_names}, 任务ID: {task_id}")

        return RulebookUploadResponse(
            task_id=task_id,
            status="pending",
            message=f"文件上传成功，已创建解析任务。任务ID: {task_id}",
            file_count=len(upload_files)
        )
        
    except StoryMasterValidationError:
        raise
    except Exception as e:
        app_logger.error(f"上传规则书失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get("/upload/tasks/{task_id}", response_model=ParsingTaskStatus)
async def get_parsing_task_status(
    task_id: str,
    task_manager: ParsingTaskManager = Depends(get_parsing_task_manager)
):
    """
    获取解析任务状态
    
    - **task_id**: 解析任务ID
    
    **任务状态**:
    - `pending`: 任务已创建，等待处理
    - `processing`: 任务正在处理中
    - `completed`: 任务处理完成
    - `failed`: 任务处理失败
    """
    try:
        status = await task_manager.get_task_status(task_id)
        if not status:
            raise NotFoundError(f"解析任务不存在: {task_id}", "解析任务")
        
        return status
        
    except NotFoundError:
        raise
    except Exception as e:
        app_logger.error(f"获取任务状态失败: {task_id}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务状态失败: {str(e)}")


@router.get("/upload/tasks/{task_id}/result", response_model=RulebookParsingResult)
async def get_parsing_result(
    task_id: str,
    task_manager: ParsingTaskManager = Depends(get_parsing_task_manager)
):
    """
    获取解析结果
    
    - **task_id**: 解析任务ID
    
    **返回内容**:
    - 解析后的规则书数据（JSON格式）
    - 解析错误列表
    - 验证警告列表
    - 规则书预览部分
    - 文件元数据
    """
    try:
        result = await task_manager.get_task_result(task_id)
        if not result:
            raise NotFoundError(f"解析任务不存在: {task_id}", "解析任务")
        
        return result
        
    except NotFoundError:
        raise
    except Exception as e:
        app_logger.error(f"获取解析结果失败: {task_id}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取解析结果失败: {str(e)}")


@router.post("/confirm")
async def confirm_rulebook(
    request: RulebookConfirmationRequest,
    task_manager: ParsingTaskManager = Depends(get_parsing_task_manager)
):
    """
    确认并保存解析后的规则书
    
    - **request**: 包含任务ID、用户ID和可选的修改内容的请求
    
    **请求体示例**:
    ```json
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "user_123",
        "modifications": {
            "name": "自定义规则书名称",
            "description": "自定义描述"
        }
    }
    ```
    """
    try:
        rulebook_id = await task_manager.confirm_and_save_rulebook(
            task_id=request.task_id,
            user_id=request.user_id,
            modifications=request.modifications
        )
        
        app_logger.info(f"规则书确认保存成功: 任务ID={request.task_id}, 规则书ID={rulebook_id}")
        
        return {
            "success": True,
            "message": "规则书保存成功",
            "rulebook_id": rulebook_id
        }
        
    except Exception as e:
        app_logger.error(f"确认规则书失败: {request.task_id}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"确认规则书失败: {str(e)}")


@router.get("/tasks", response_model=List[ParsingTaskStatus])
async def list_parsing_tasks(
    task_manager: ParsingTaskManager = Depends(get_parsing_task_manager)
):
    """
    列出所有活跃的解析任务
    
    **返回内容**:
    - 所有活跃任务的状态列表
    """
    try:
        tasks = await task_manager.list_active_tasks()
        return tasks
        
    except Exception as e:
        app_logger.error(f"列出任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"列出任务失败: {str(e)}")


@router.delete("/tasks/{task_id}")
async def delete_parsing_task(
    task_id: str,
    task_manager: ParsingTaskManager = Depends(get_parsing_task_manager)
):
    """
    删除解析任务
    
    - **task_id**: 解析任务ID
    """
    try:
        if task_id in task_manager.active_tasks:
            del task_manager.active_tasks[task_id]
            app_logger.info(f"删除解析任务: {task_id}")
            return {
                "success": True,
                "message": f"任务 {task_id} 已删除"
            }
        else:
            raise NotFoundError(f"解析任务不存在: {task_id}", "解析任务")
            
    except NotFoundError:
        raise
    except Exception as e:
        app_logger.error(f"删除任务失败: {task_id}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")


@router.get("/supported-formats")
async def get_supported_formats():
    """
    获取支持的文件格式
    
    **返回内容**:
    - 支持的文件格式列表
    - 支持的AI模型列表
    """
    try:
        supported_formats = getattr(settings, 'supported_rulebook_formats', ['pdf', 'docx', 'txt', 'json', 'md'])
        
        # 支持的AI模型（从配置中获取）
        supported_models = []
        if hasattr(settings, 'openai_api_key') and settings.openai_api_key:
            supported_models.extend(["gpt-4", "gpt-3.5-turbo", "gpt-3.5"])
        if hasattr(settings, 'anthropic_api_key') and settings.anthropic_api_key:
            supported_models.extend(["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"])
        if hasattr(settings, 'ollama_base_url'):
            supported_models.append("ollama-local")
        
        return {
            "supported_formats": supported_formats,
            "supported_models": supported_models,
            "max_file_size_mb": getattr(settings, 'max_rulebook_file_size', 50),
            "description": {
                "pdf": "PDF文档格式",
                "docx": "Microsoft Word文档",
                "txt": "纯文本文件",
                "json": "JSON数据格式",
                "md": "Markdown格式"
            }
        }
        
    except Exception as e:
        app_logger.error(f"获取支持格式失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取支持格式失败: {str(e)}")