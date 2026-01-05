"""
角色卡管理器（协调各服务）
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

from ..core.logging import app_logger
from ..core.exceptions import ValidationError, NotFoundError
from ..models.character_creation_models import (
    CharacterCreationFormResponse,
    CharacterCreationRequest,
    CharacterCreationResponse,
    CharacterData,
    CalculatedCharacterData
)
from ..models.rulebook_models import CompleteRulebookData
from ..models.dynamic_entity import Entity


class CharacterManager:
    """角色卡管理器"""
    
    def __init__(
        self,
        rulebook_manager,
        entity_repository,
        creation_generator,
        validator,
        calculator
    ):
        """
        初始化角色卡管理器
        
        Args:
            rulebook_manager: 规则书管理器
            entity_repository: 实体仓库
            creation_generator: 角色卡创建表单生成器
            validator: 角色卡数据验证器
            calculator: 规则计算器
        """
        self.rulebook_manager = rulebook_manager
        self.entity_repository = entity_repository
        self.creation_generator = creation_generator
        self.validator = validator
        self.calculator = calculator
        self.logger = app_logger
    
    async def get_creation_form(
        self,
        schema_id: str,
        user_id: str,
        entity_type: str = "Character"
    ) -> Dict[str, Any]:
        """
        获取角色卡创建表单
        
        Args:
            schema_id: 规则书Schema ID
            user_id: 用户ID
            entity_type: 实体类型（默认为Character）
            
        Returns:
            Dict: 创建表单数据
        """
        try:
            # 使用创建表单生成器获取表单
            form_data = await self.creation_generator.get_creation_form(schema_id)
            
            self.logger.info(f"创建表单生成成功: {schema_id}")
            return form_data
            
        except Exception as e:
            self.logger.error(f"获取创建表单失败: {schema_id}, 错误: {e}", exc_info=True)
            raise ValidationError(f"获取创建表单失败: {str(e)}")
    
    async def create_character(
        self,
        schema_id: str,
        user_id: str,
        character_data: Dict[str, Any]
    ) -> CharacterCreationResponse:
        """
        创建角色卡
        
        Args:
            schema_id: 规则书Schema ID
            user_id: 用户ID
            character_data: 角色数据
            
        Returns:
            CharacterCreationResponse: 角色卡创建响应
        """
        try:
            # 生成角色ID
            character_id = self._generate_character_id(schema_id, user_id)
            character_data['character_id'] = character_id
            character_data['schema_id'] = schema_id
            character_data['user_id'] = user_id
            
            # 获取规则书数据
            rulebook_data = await self.rulebook_manager.download_schema(schema_id)
            if not rulebook_data:
                raise NotFoundError(f"规则书不存在: {schema_id}", "规则书")
            
            # 设置验证器和计算器
            creation_model = rulebook_data.get('character_creation_model')
            if creation_model:
                self.validator.set_character_creation_model(creation_model)
                self.calculator.set_character_creation_model(creation_model)
            
            # 验证角色数据
            validation_result = await self.validator.validate_character_data(character_data)
            if not validation_result.valid:
                errors = validation_result.errors or []
                warnings = validation_result.warnings or []
                self.logger.warning(f"角色数据验证失败: {', '.join(errors)}")
                return CharacterCreationResponse(
                    character_id=character_id,
                    character_data=character_data,
                    calculated_properties={},
                    warnings=warnings
                )
            
            # 计算角色属性
            calculated_data = await self.calculator.calculate_character_properties(
                schema_id,
                character_data
            )
            
            # 合并用户数据和计算数据
            final_properties = {**character_data, **calculated_data.calculated_properties}
            
            # 创建实体
            entity = Entity(
                id=character_id,
                entity_type="Character",
                properties=final_properties,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # 保存到数据库
            await self.entity_repository.create(entity)
            
            # 创建用户与角色的关系
            await self._create_user_relationship(character_id, user_id)
            
            self.logger.info(f"角色卡创建成功: {character_id}")
            return CharacterCreationResponse(
                character_id=character_id,
                character_data=final_properties,
                calculated_properties=calculated_data.derived_values,
                warnings=validation_result.warnings or []
            )
            
        except NotFoundError:
            raise
        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"创建角色卡失败: {schema_id}, 错误: {e}", exc_info=True)
            raise ValidationError(f"创建角色卡失败: {str(e)}")
    
    async def get_character(
        self,
        character_id: str
    ) -> CharacterData:
        """
        获取角色卡
        
        Args:
            character_id: 角色ID
            
        Returns:
            CharacterData: 角色数据
        """
        try:
            entity = await self.entity_repository.get_by_id(character_id)
            
            if not entity:
                raise NotFoundError(f"角色不存在: {character_id}", "角色")
            
            self.logger.info(f"获取角色卡成功: {character_id}")
            return CharacterData(
                character_id=entity.id,
                entity_type=entity.entity_type,
                properties=entity.properties,
                relationships={},
                schema_id=entity.properties.get('schema_id', ''),
                user_id=entity.properties.get('user_id', ''),
                created_at=entity.created_at,
                updated_at=entity.updated_at
            )
            
        except NotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"获取角色卡失败: {character_id}, 错误: {e}", exc_info=True)
            raise ValidationError(f"获取角色卡失败: {str(e)}")
    
    async def update_character(
        self,
        character_id: str,
        character_data: Dict[str, Any]
    ) -> CharacterData:
        """
        更新角色卡
        
        Args:
            character_id: 角色ID
            character_data: 新的角色数据
            
        Returns:
            CharacterData: 更新后的角色数据
        """
        try:
            # 获取现有角色
            existing = await self.entity_repository.get_by_id(character_id)
            if not existing:
                raise NotFoundError(f"角色不存在: {character_id}", "角色")
            
            schema_id = existing.properties.get('schema_id', '')
            character_data['character_id'] = character_id
            character_data['schema_id'] = schema_id
            character_data['user_id'] = existing.properties.get('user_id', '')
            
            # 获取规则书数据
            rulebook_data = await self.rulebook_manager.download_schema(schema_id)
            if not rulebook_data:
                raise NotFoundError(f"规则书不存在: {schema_id}", "规则书")
            
            # 设置验证器和计算器
            creation_model = rulebook_data.get('character_creation_model')
            if creation_model:
                self.validator.set_character_creation_model(creation_model)
                self.calculator.set_character_creation_model(creation_model)
            
            # 验证新数据
            validation_result = await self.validator.validate_character_data(character_data)
            if not validation_result.valid:
                errors = validation_result.errors or []
                warnings = validation_result.warnings or []
                self.logger.warning(f"角色数据验证失败: {', '.join(errors)}")
                raise ValidationError(f"角色数据验证失败: {', '.join(errors)}")
            
            # 计算角色属性
            calculated_data = await self.calculator.calculate_character_properties(
                schema_id,
                character_data
            )
            
            # 合并用户数据和计算数据
            final_properties = {**character_data, **calculated_data.calculated_properties}
            
            # 更新实体
            entity = Entity(
                id=character_id,
                entity_type="Character",
                properties=final_properties,
                created_at=existing.created_at,
                updated_at=datetime.now()
            )
            
            await self.entity_repository.update(entity)
            
            self.logger.info(f"角色卡更新成功: {character_id}")
            return CharacterData(
                character_id=entity.id,
                entity_type=entity.entity_type,
                properties=entity.properties,
                relationships={},
                schema_id=entity.properties.get('schema_id', ''),
                user_id=entity.properties.get('user_id', ''),
                created_at=entity.created_at,
                updated_at=entity.updated_at
            )
            
        except NotFoundError:
            raise
        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"更新角色卡失败: {character_id}, 错误: {e}", exc_info=True)
            raise ValidationError(f"更新角色卡失败: {str(e)}")
    
    async def delete_character(self, character_id: str) -> bool:
        """
        删除角色卡
        
        Args:
            character_id: 角色ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            # 检查角色是否存在
            existing = await self.entity_repository.get_by_id(character_id)
            if not existing:
                raise NotFoundError(f"角色不存在: {character_id}", "角色")
            
            # 删除角色及其关系
            await self.entity_repository.delete(character_id)
            
            self.logger.info(f"角色卡删除成功: {character_id}")
            return True
            
        except NotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"删除角色卡失败: {character_id}, 错误: {e}", exc_info=True)
            raise ValidationError(f"删除角色卡失败: {str(e)}")
    
    async def list_characters(
        self,
        user_id: Optional[str] = None,
        schema_id: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        列出角色卡
        
        Args:
            user_id: 用户ID（可选）
            schema_id: 规则书Schema ID（可选）
            page: 页码（默认1）
            limit: 每页数量（默认20）
            
        Returns:
            Dict: 角色列表
        """
        try:
            # TODO: 实现分页查询逻辑
            from ..data_storage.repositories.entity_repository import EntityFilter
            
            # 构建过滤条件
            filters = EntityFilter(
                entity_types=["Character"],
                offset=(page - 1) * limit,
                limit=limit
            )
            
            # 查询角色
            result = await self.entity_repository.find(filters)
            
            # 转换为响应格式
            characters = []
            for entity in result.items:
                characters.append({
                    'character_id': entity.id,
                    'name': entity.properties.get('name', ''),
                    'schema_id': entity.properties.get('schema_id', ''),
                    'user_id': entity.properties.get('user_id', ''),
                    'created_at': entity.created_at.isoformat() if entity.created_at else '',
                    'updated_at': entity.updated_at.isoformat() if entity.updated_at else ''
                })
            
            self.logger.info(f"列出角色卡成功: {len(characters)}个角色")
            return {
                'characters': characters,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': result.total_count,
                    'has_more': result.has_more
                }
            }
            
        except Exception as e:
            self.logger.error(f"列出角色卡失败: {e}", exc_info=True)
            raise ValidationError(f"列出角色卡失败: {str(e)}")
    
    def _generate_character_id(self, schema_id: str, user_id: str) -> str:
        """生成角色ID"""
        return f"char_{schema_id}_{user_id}_{uuid.uuid4().hex[:8]}"
    
    async def _create_user_relationship(
        self,
        character_id: str,
        user_id: str
    ) -> None:
        """
        创建用户与角色的关系
        
        Args:
            character_id: 角色ID
            user_id: 用户ID
        """
        try:
            # TODO: 实现用户关系创建
            # 通过EntityRepository创建关系
            pass
        except Exception as e:
            self.logger.warning(f"创建用户关系失败: {e}")


# 工厂函数
def create_character_manager(rulebook_manager, entity_repository, creation_generator, validator, calculator) -> CharacterManager:
    """创建角色卡管理器"""
    return CharacterManager(
        rulebook_manager=rulebook_manager,
        entity_repository=entity_repository,
        creation_generator=creation_generator,
        validator=validator,
        calculator=calculator
    )


# 导出函数
__all__ = [
    "CharacterManager",
    "create_character_manager"
]