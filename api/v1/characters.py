"""
角色卡创建和管理API端点
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from ...core.logging import app_logger
from ...core.exceptions import ValidationError, NotFoundError
from ...services.character_manager import CharacterManager
from ...models.character_creation_models import (
    CharacterCreationFormRequest,
    CharacterCreationFormResponse,
    CharacterCreationRequest,
    CharacterCreationResponse,
    CharacterData
)


router = APIRouter(prefix="/characters", tags=["characters"])

# 全局角色卡管理器实例
_character_manager: Optional[CharacterManager] = None

def get_character_manager() -> CharacterManager:
    """获取角色卡管理器实例"""
    global _character_manager
    if _character_manager is None:
        # 延迟初始化
        from ...services.schema_converter import SchemaConverter
        from ...services.character_creation_generator import create_character_creation_generator
        from ...services.character_creation_validator import CharacterCreationValidator
        from ...services.rule_calculator import create_rule_calculator
        from ...data_storage.repositories.entity_repository import EntityRepository
        from ...data_storage.adapters.neo4j_adapter import Neo4jAdapter
        from ...data_storage.managers.cache_manager import CacheManager
        from ...data_storage.adapters.redis_adapter import RedisAdapter
        from ...core.config import settings
        
        # 获取配置
        neo4j_uri = settings.neo4j_uri
        neo4j_user = settings.neo4j_user
        neo4j_password = settings.neo4j_password
        
        # 初始化组件
        neo4j_adapter = Neo4jAdapter(neo4j_uri, neo4j_user, neo4j_password)
        redis_adapter = RedisAdapter(settings.redis_url)
        cache_manager = CacheManager(redis_adapter)
        entity_repository = EntityRepository(neo4j_adapter, cache_manager)
        schema_converter = SchemaConverter()
        
        # 创建管理器
        _character_manager = CharacterManager(
            rulebook_manager=None,  # 将通过依赖注入设置
            entity_repository=entity_repository,
            creation_generator=create_character_creation_generator(None),  # 临时设置
            validator=None,
            calculator=None
        )
        
        app_logger.info("角色卡管理器初始化完成")
    
    return _character_manager


@router.post("/creation-form")
async def get_character_creation_form(
    request: CharacterCreationFormRequest
) -> CharacterCreationFormResponse:
    """
    获取角色卡创建表单
    
    - **schema_id**: 规则书Schema ID
    - **user_id**: 用户ID
    - **entity_type**: 实体类型（默认为Character）
    
    **请求体示例**：
    ```json
    {
      "schema_id": "dnd_5e_2024",
      "user_id": "user_123",
      "entity_type": "Character"
    }
    ```
    
    **响应体示例**：
    ```json
    {
      "schema_id": "dnd_5e_2024",
      "form_schema": {
        "model_id": "char_creation_dnd_5e_2024",
        "model_name": "D&D 5e角色创建",
        "fields": [...],
        "field_groups": [...],
        "validation_rules": [...],
        "calculation_rules": [...]
      },
      "warnings": []
    }
    ```
    """
    try:
        manager = get_character_manager()
        response = await manager.get_creation_form(
            schema_id=request.schema_id,
            user_id=request.user_id,
            entity_type=request.entity_type
        )
        return CharacterCreationFormResponse(**response)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        app_logger.error(f"获取创建表单失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取创建表单失败: {str(e)}")


@router.post("/create")
async def create_character(
    request: CharacterCreationRequest
) -> CharacterCreationResponse:
    """
    创建角色卡
    
    - **schema_id**: 规则书Schema ID
    - **user_id**: 用户ID
    - **character_data**: 角色数据
    
    **请求体示例**：
    ```json
    {
      "schema_id": "dnd_5e_2024",
      "user_id": "user_123",
      "character_data": {
        "name": "艾登·风暴使者",
        "race": "Human",
        "class": "Fighter",
        "level": 5,
        "ability_scores": {
          "strength": 16,
          "dexterity": 14,
          "constitution": 15,
          "intelligence": 12,
          "wisdom": 13,
          "charisma": 14
        }
      }
    }
    ```
    
    **响应体示例**：
    ```json
    {
      "character_id": "char_dnd_5e_2024_user_123_a1b2c3d4",
      "character_data": {
        "name": "艾登·风暴使者",
        "race": "Human",
        "class": "Fighter",
        "level": 5,
        "ability_scores": {
          "strength": 16,
          "dexterity": 14,
          "constitution": 15,
          "intelligence": 12,
          "wisdom": 13,
          "charisma": 14
        },
        "strength_modifier": 3,
        "dexterity_modifier": 2,
        "constitution_modifier": 2,
        "intelligence_modifier": 1,
        "wisdom_modifier": 1,
        "charisma_modifier": 2,
        "proficiency_bonus": 3
      },
      "calculated_properties": {
        "strength_modifier": {
          "formula": "floor((strength - 10) / 2)",
          "description": "力量修正值",
          "value": 3,
          "input_fields": ["strength"],
          "rule_name": "strength_modifier_calculation"
        },
        "proficiency_bonus": {
          "formula": "floor((level - 1) / 4) + 2",
          "description": "熟练度加值",
          "value": 3,
          "input_fields": ["level"],
          "rule_name": "proficiency_bonus_calculation"
        }
      },
      "warnings": []
    }
    ```
    """
    try:
        manager = get_character_manager()
        response = await manager.create_character(
            schema_id=request.schema_id,
            user_id=request.user_id,
            character_data=request.character_data
        )
        return CharacterCreationResponse(**response)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        app_logger.error(f"创建角色卡失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建角色卡失败: {str(e)}")


@router.get("/{character_id}")
async def get_character(
    character_id: str
) -> CharacterData:
    """
    获取角色卡详情
    
    - **character_id**: 角色ID
    
    **响应体示例**：
    ```json
    {
      "character_id": "char_dnd_5e_2024_user_123_a1b2c3d4",
      "entity_type": "Character",
      "properties": {
        "name": "艾登·风暴使者",
        "race": "Human",
        "class": "Fighter",
        "level": 5
      },
      "relationships": {},
      "schema_id": "dnd_5e_2024",
      "user_id": "user_123",
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-01T12:00:00Z"
    }
    ```
    """
    try:
        manager = get_character_manager()
        character = await manager.get_character(character_id)
        return CharacterData(**character)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        app_logger.error(f"获取角色卡失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取角色卡失败: {str(e)}")


@router.put("/{character_id}")
async def update_character(
    character_id: str,
    request: CharacterCreationRequest
) -> CharacterData:
    """
    更新角色卡
    
    - **character_id**: 角色ID
    - **schema_id**: 规则书Schema ID
    - **user_id**: 用户ID
    - **character_data**: 新的角色数据
    """
    try:
        manager = get_character_manager()
        character = await manager.update_character(character_id, request.character_data)
        return CharacterData(**character)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        app_logger.error(f"更新角色卡失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新角色卡失败: {str(e)}")


@router.delete("/{character_id}")
async def delete_character(
    character_id: str
) -> dict:
    """
    删除角色卡
    
    - **character_id**: 角色ID
    
    **响应体示例**：
    ```json
    {
      "success": true,
      "message": "角色 char_dnd_5e_2024_user_123_a1b2c3d4 已删除"
    }
    ```
    """
    try:
        manager = get_character_manager()
        success = await manager.delete_character(character_id)
        if not success:
            raise NotFoundError(f"角色不存在: {character_id}", "角色")
        return {
            "success": True,
            "message": f"角色 {character_id} 已删除"
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        app_logger.error(f"删除角色卡失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除角色卡失败: {str(e)}")


@router.get("/")
async def list_characters(
    user_id: str,
    schema_id: Optional[str] = None,
    page: int = Query(1, ge=1, description="页码（默认1）"),
    limit: int = Query(20, ge=1, le=100, description="每页数量（默认20，最大100）")
) -> dict:
    """
    列出角色卡
    
    - **user_id**: 用户ID
    - **schema_id**: 规则书Schema ID（可选）
    - **page**: 页码（默认1）
    - **limit**: 每页数量（默认20，最大100）
    
    **响应体示例**：
    ```json
    {
      "characters": [
        {
          "character_id": "char_001",
          "name": "艾登·风暴使者",
          "schema_id": "dnd_5e_2024",
          "user_id": "user_123",
          "created_at": "2024-01-01T12:00:00Z",
          "updated_at": "2024-01-01T12:00:00Z"
        }
      ],
      "pagination": {
        "page": 1,
        "limit": 20,
        "total": 45,
        "has_more": true
      }
    }
    ```
    """
    try:
        manager = get_character_manager()
        result = await manager.list_characters(
            user_id=user_id,
            schema_id=schema_id,
            page=page,
            limit=limit
        )
        return result
    except Exception as e:
        app_logger.error(f"列出角色卡失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"列出角色卡失败: {str(e)}")