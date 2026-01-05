"""
规则书解析相关数据模型
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, validator


class RulebookUploadRequest(BaseModel):
    """规则书上傳請求"""
    file_name: str = Field(..., description="文件名")
    file_type: str = Field(..., description="文件类型")
    parser_model: str = Field(default="gpt-4", description="解析模型")
    parsing_options: Dict[str, Any] = Field(default_factory=dict, description="解析选项")
    user_id: str = Field(..., description="用户ID")
    
    @validator('file_type')
    def validate_file_type(cls, v):
        allowed_types = ['pdf', 'docx', 'txt', 'json', 'md']
        if v.lower() not in allowed_types:
            raise ValueError(f"不支持的文件类型: {v}")
        return v.lower()


class RulebookUploadResponse(BaseModel):
    """规则书上傳響應"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    message: str = Field(..., description="响应消息")


class ParsingTaskStatus(BaseModel):
    """解析任务状态"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="状态: pending, processing, completed, failed")
    progress: float = Field(..., ge=0.0, le=1.0, description="进度: 0.0-1.0")
    message: str = Field(..., description="状态消息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    estimated_completion: Optional[datetime] = Field(None, description="预计完成时间")
    current_step: Optional[str] = Field(None, description="当前步骤")


class RulebookParsingResult(BaseModel):
    """规则书解析结果"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="解析状态")
    rulebook_data: Optional[Dict[str, Any]] = Field(None, description="解析后的规则书数据")
    parsing_errors: List[str] = Field(default_factory=list, description="解析错误列表")
    validation_warnings: List[str] = Field(default_factory=list, description="验证警告列表")
    preview_sections: List[Dict[str, Any]] = Field(default_factory=list, description="预览部分")
    file_metadata: Optional[Dict[str, Any]] = Field(None, description="文件元数据")


class RulebookConfirmationRequest(BaseModel):
    """规则书确认请求"""
    task_id: str = Field(..., description="任务ID")
    user_id: str = Field(..., description="用户ID")
    modifications: Optional[Dict[str, Any]] = Field(None, description="用户修改内容")


class ProcessedFile(BaseModel):
    """处理后的文件"""
    file_path: str = Field(..., description="文件路径")
    file_name: str = Field(..., description="文件名")
    file_type: str = Field(..., description="文件类型")
    file_size: int = Field(..., description="文件大小（字节）")
    content: str = Field(..., description="提取的文本内容")
    content_chunks: List[str] = Field(default_factory=list, description="内容分块")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="文件元数据")
    created_at: datetime = Field(default_factory=datetime.now)


class ValidationResult(BaseModel):
    """验证结果"""
    valid: bool = Field(..., description="是否有效")
    errors: List[str] = Field(default_factory=list, description="错误列表")
    warnings: List[str] = Field(default_factory=list, description="警告列表")