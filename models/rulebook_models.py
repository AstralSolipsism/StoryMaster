"""
规则书数据模型（修订版）

包含完整规则书Schema和角色卡创建模型的数据结构
"""

from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from .character_creation_models import CharacterCreationModel


class CompleteRulebookData(BaseModel):
    """完整的规则书数据（包含Schema和创建模型）"""
    
    # 规则书基本信息
    schema_id: str = Field(..., description="规则书Schema ID")
    name: str = Field(..., description="规则书名称")
    version: str = Field(..., description="规则书版本")
    author: str = Field(..., description="作者")
    game_system: str = Field(..., description="游戏系统")
    description: str = Field(default="", description="描述")
    
    # 完整的规则书Schema（用于系统内部）
    rulebook_schema: Dict[str, Any] = Field(..., description="完整的规则书Schema")
    
    # 角色卡创建模型（用于角色创建）
    character_creation_model: Optional[CharacterCreationModel] = Field(
        None, 
        description="角色卡创建模型（由智能体生成）"
    )
    
    # 其他实体类型的创建模型（可选）
    entity_creation_models: Optional[Dict[str, Any]] = Field(
        None, 
        description="其他实体的创建模型"
    )
    
    # 元数据
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    is_active: bool = Field(default=False, description="是否激活")
    has_creation_model: bool = Field(default=False, description="是否包含创建模型")


class RulebookUploadResponse(BaseModel):
    """规则书上传统一响应（修订版）"""
    schema_id: str = Field(..., description="规则书ID")
    status: str = Field(..., description="处理状态")
    message: str = Field(..., description="响应消息")
    has_creation_model: bool = Field(default=False, description="是否包含创建模型")