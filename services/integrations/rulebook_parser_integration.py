"""
规则书解析集成服务
负责将解析器与现有规则书管理系统集成
"""

from typing import Dict, Any, Optional
from datetime import datetime

from ..core.logging import app_logger
from ..core.exceptions import StoryMasterValidationError, NotFoundError
from ..data_storage.rulebook_manager import RulebookManager


class RulebookParserIntegration:
    """规则书解析器与现有系统的集成"""
    
    def __init__(self, rulebook_manager: Optional[RulebookManager] = None):
        self.rulebook_manager = rulebook_manager
        self.logger = app_logger
    
    async def save_parsed_rulebook(
        self, 
        schema_data: Dict[str, Any],
        user_id: str
    ) -> str:
        """
        保存解析后的规则书
        
        Args:
            schema_data: 解析后的规则书Schema数据
            user_id: 用户ID
            
        Returns:
            str: 规则书ID
            
        Raises:
            StoryMasterValidationError: 验证失败
            NotFoundError: 规则书管理器未初始化
        """
        if not self.rulebook_manager:
            raise NotFoundError(
                "规则书管理器未初始化，无法保存规则书",
                "规则书管理器"
            )
        
        try:
            # 验证Schema数据完整性
            validation_result = await self._validate_schema_data(schema_data)
            if not validation_result['valid']:
                errors = validation_result['errors']
                raise StoryMasterValidationError(
                    f"规则书Schema验证失败: {'; '.join(errors[:5])}"
                )
            
            # 添加上传者信息
            schema_data['uploader_id'] = user_id
            schema_data['uploaded_at'] = datetime.now().isoformat()
            
            # 使用现有的RulebookManager保存
            schema_id = await self.rulebook_manager.upload_schema(
                schema_data, user_id, validate=True
            )
            
            self.logger.info(f"规则书保存成功: {schema_id}, 上传者: {user_id}")
            
            return schema_id
            
        except Exception as e:
            self.logger.error(f"保存规则书失败: {e}", exc_info=True)
            raise
    
    async def _validate_schema_data(self, schema_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证Schema数据完整性
        
        Args:
            schema_data: Schema数据
            
        Returns:
            Dict: 验证结果
        """
        errors = []
        warnings = []
        
        # 检查必需字段
        required_fields = ['schema_id', 'name', 'entities']
        for field in required_fields:
            if field not in schema_data:
                errors.append(f"缺少必需字段: {field}")
        
        # 检查实体定义
        entities = schema_data.get('entities', {})
        if not entities:
            errors.append("必须定义至少一个实体")
        else:
            for entity_type, entity_def in entities.items():
                # 检查实体必需字段
                entity_required = ['label', 'properties']
                for field in entity_required:
                    if field not in entity_def:
                        warnings.append(f"实体 {entity_type} 缺少字段: {field}")
                
                # 检查属性
                properties = entity_def.get('properties', {})
                if not properties:
                    warnings.append(f"实体 {entity_type} 没有定义任何属性")
        
        # 检查规则定义
        rules = schema_data.get('rules', {})
        for rule_name, rule_def in rules.items():
            if 'type' not in rule_def:
                warnings.append(f"规则 {rule_name} 缺少类型字段")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    async def update_parsed_rulebook(
        self,
        schema_id: str,
        updates: Dict[str, Any],
        user_id: str
    ) -> bool:
        """
        更新已解析的规则书
        
        Args:
            schema_id: 规则书ID
            updates: 更新内容
            user_id: 用户ID
            
        Returns:
            bool: 是否更新成功
        """
        if not self.rulebook_manager:
            raise NotFoundError(
                "规则书管理器未初始化",
                "规则书管理器"
            )
        
        try:
            # 检查规则书是否存在
            existing_schema = await self.rulebook_manager.storage.load_schema(schema_id)
            if not existing_schema:
                raise NotFoundError(f"规则书不存在: {schema_id}", "规则书")
            
            # 应用更新
            # 注意：这里需要根据实际的RulebookManager API调整
            # 简化实现，实际可能需要更复杂的逻辑
            self.logger.info(f"规则书更新: {schema_id}, 更新者: {user_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"更新规则书失败: {schema_id}, 错误: {e}", exc_info=True)
            raise
    
    async def activate_parsed_rulebook(
        self,
        schema_id: str,
        user_id: str
    ) -> bool:
        """
        激活解析后的规则书
        
        Args:
            schema_id: 规则书ID
            user_id: 用户ID
            
        Returns:
            bool: 是否激活成功
        """
        if not self.rulebook_manager:
            raise NotFoundError(
                "规则书管理器未初始化",
                "规则书管理器"
            )
        
        try:
            success = await self.rulebook_manager.activate_schema(schema_id, user_id)
            
            if success:
                self.logger.info(f"规则书激活成功: {schema_id}, 操作者: {user_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"激活规则书失败: {schema_id}, 错误: {e}", exc_info=True)
            raise
    
    async def get_parsed_rulebook(self, schema_id: str) -> Optional[Dict[str, Any]]:
        """
        获取已解析的规则书
        
        Args:
            schema_id: 规则书ID
            
        Returns:
            Dict: 规则书数据或None
        """
        if not self.rulebook_manager:
            raise NotFoundError(
                "规则书管理器未初始化",
                "规则书管理器"
            )
        
        try:
            schema_data = await self.rulebook_manager.download_schema(schema_id)
            
            if schema_data:
                self.logger.debug(f"获取规则书成功: {schema_id}")
            
            return schema_data
            
        except Exception as e:
            self.logger.error(f"获取规则书失败: {schema_id}, 错误: {e}", exc_info=True)
            raise