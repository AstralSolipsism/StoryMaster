"""
Data structure converter (修订版)
Handles both rulebook schema and character creation model
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.logging import app_logger
from ..core.exceptions import ValidationError
from ..models.parsing_models import ValidationResult
from ..models.character_creation_models import (
    CharacterCreationModel,
    CreationFormField,
    CreationFieldGroup,
    CreationValidationRule,
    CreationCalculationRule
)
from ..models.rulebook_models import CompleteRulebookData


class SchemaConverter:
    """Convert AI parsing results to system rulebook schema and character creation model"""
    
    def __init__(self):
        self.logger = app_logger
    
    async def convert_to_rulebook_schema(
        self, 
        parsing_result: Dict[str, Any],
        file_info: Dict[str, Any],
        user_id: str
    ) -> CompleteRulebookData:
        """
        Convert parsing results to complete rulebook data
        
        Args:
            parsing_result: AI parsing results (contains schema and creation_model)
            file_info: File metadata
            user_id: User ID
            
        Returns:
            CompleteRulebookData: Complete rulebook data with both schema and creation model
        """
        try:
            # Generate Schema ID
            file_name = file_info.get('file_name', 'unknown')
            base_name = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
            schema_id = f"{base_name}_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Process rulebook schema
            schema_payload = parsing_result.get('rulebook_schema') or parsing_result or {}
            rulebook_schema = await self._process_rulebook_schema(
                schema_payload,
                schema_id
            )
            
            # Process character creation model
            character_creation_model = None
            has_creation_model = False
            
            if 'character_creation_model' in parsing_result:
                try:
                    character_creation_model = await self._process_character_creation_model(
                        parsing_result['character_creation_model'],
                        schema_id
                    )
                    has_creation_model = True
                    self.logger.info(f"Character creation model extracted successfully for {schema_id}")
                except Exception as e:
                    self.logger.warning(f"Failed to process character creation model: {e}")
                    character_creation_model = None
            
            # Build complete data
            complete_data = CompleteRulebookData(
                schema_id=schema_id,
                name=file_info.get('name', base_name),
                version="1.0.0",
                author=user_id,
                description=f"Auto-generated rulebook from file {file_name}",
                game_system=self._detect_game_system(rulebook_schema, file_info),
                rulebook_schema=rulebook_schema,
                character_creation_model=character_creation_model,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                is_active=False,
                has_creation_model=has_creation_model
            )
            
            self.logger.info(f"Complete rulebook data conversion successful: {schema_id}")
            return complete_data
            
        except Exception as e:
            self.logger.error(f"Failed to convert rulebook data: {e}", exc_info=True)
            raise ValidationError(f"Failed to convert rulebook data: {str(e)}")
    
    async def _process_rulebook_schema(
        self,
        schema_data: Dict[str, Any],
        schema_id: str
    ) -> Dict[str, Any]:
        """Process rulebook schema (existing logic)"""
        # Validate schema structure
        errors = await self._validate_schema_structure(schema_data)
        if errors:
            raise ValidationError(f"Schema validation failed: {', '.join(errors)}")
        
        # Normalize schema format
        return await self._normalize_schema(schema_data, schema_id)
    
    async def _process_character_creation_model(
        self,
        creation_model_data: Dict[str, Any],
        schema_id: str
    ) -> CharacterCreationModel:
        """Process character creation model (new)"""
        try:
            # Validate creation model structure
            await self._validate_creation_model_structure(creation_model_data)
            
            # Parse field definitions
            fields = {}
            for field_name, field_data in creation_model_data.get('fields', {}).items():
                fields[field_name] = self._parse_field_definition(field_name, field_data)
            
            # Parse field groups
            field_groups = []
            for group_data in creation_model_data.get('field_groups', []):
                field_groups.append(CreationFieldGroup(**group_data))
            
            # Parse validation rules
            validation_rules = []
            for rule_data in creation_model_data.get('validation_rules', []):
                validation_rules.append(CreationValidationRule(**rule_data))
            
            # Parse calculation rules
            calculation_rules = []
            for rule_data in creation_model_data.get('calculation_rules', []):
                calculation_rules.append(CreationCalculationRule(**rule_data))
            
            # Create creation model
            return CharacterCreationModel(
                model_id=f"char_creation_{schema_id}",
                model_name=creation_model_data.get('model_name', 'Character Creation'),
                model_description=creation_model_data.get('model_description', ''),
                fields=fields,
                field_groups=field_groups,
                validation_rules=validation_rules,
                calculation_rules=calculation_rules,
                templates=creation_model_data.get('templates'),
                metadata=creation_model_data.get('metadata', {}),
                schema_compatibility=creation_model_data.get('schema_compatibility', {})
            )
            
        except Exception as e:
            raise ValidationError(f"Failed to process character creation model: {str(e)}")
    
    def _parse_field_definition(self, field_name: str, field_data: Dict[str, Any]) -> CreationFormField:
        """Parse field definition"""
        return CreationFormField(
            name=field_name,
            type=field_data.get('type', 'string'),
            label=field_data.get('label', field_name),
            description=field_data.get('description', ''),
            required=field_data.get('required', True),
            default=field_data.get('default'),
            min_value=field_data.get('min_value'),
            max_value=field_data.get('max_value'),
            min_length=field_data.get('min_length'),
            max_length=field_data.get('max_length'),
            pattern=field_data.get('pattern'),
            enum_options=field_data.get('enum_options'),
            display_order=field_data.get('display_order', 0),
            ui_type=field_data.get('ui_type'),
            ui_options=field_data.get('ui_options'),
            depends_on=field_data.get('depends_on'),
            conditional_display=field_data.get('conditional_display'),
            read_only=field_data.get('read_only', False),
            hidden=field_data.get('hidden', False)
        )
    
    async def _validate_schema_structure(self, schema_data: Dict[str, Any]) -> List[str]:
        """Validate schema data"""
        errors = []
        
        # Check entity definitions
        entities = schema_data.get('entities', {})
        if entities is None:
            entities = {}
        if isinstance(entities, list):
            self.logger.warning("Schema entities is a list; normalizing to empty dict")
            entities = {}
        if not entities:
            self.logger.warning("Schema has no entities; continuing with empty entities")
            return errors
        
        for entity_id, entity_def in entities.items():
            entity_errors = await self._validate_entity(entity_id, entity_def, entities.keys())
            errors.extend(entity_errors['errors'])
        
        # Check circular references
        reference_errors = await self._check_circular_references(entities)
        errors.extend(reference_errors)
        
        return errors
    
    async def _validate_creation_model_structure(self, creation_model_data: Dict[str, Any]) -> List[str]:
        """Validate character creation model structure"""
        errors = []
        
        # Check required fields
        required_fields = ['model_id', 'model_name', 'fields']
        for field in required_fields:
            if field not in creation_model_data:
                errors.append(f"Missing required field: {field}")
        
        # Check fields definition
        if 'fields' not in creation_model_data:
            errors.append("Creation model must define fields field")
        elif not creation_model_data['fields']:
            errors.append("Creation model has no defined fields")
        else:
            for field_name, field_data in creation_model_data['fields'].items():
                if 'name' not in field_data or 'type' not in field_data:
                    errors.append(f"Field {field_name} missing name or type")
                
                # Check enum type fields
                if field_data.get('type') == 'enum':
                    if 'enum_options' not in field_data:
                        errors.append(f"Enum field {field_name} must define enum_options")
                    elif not isinstance(field_data.get('enum_options'), list):
                        errors.append(f"Field {field_name} enum_options must be a list")
        
        return errors
    
    async def _normalize_schema(self, schema_data: Dict[str, Any], schema_id: str) -> Dict[str, Any]:
        """Normalize schema format"""
        return {
            'schema_id': schema_id,
            'name': schema_data.get('name', schema_id),
            'version': schema_data.get('version', '1.0.0'),
            'author': schema_data.get('author', ''),
            'description': schema_data.get('description', ''),
            'game_system': schema_data.get('game_system', 'dnd_5e'),
            'entities': schema_data.get('entities', {}),
            'rules': schema_data.get('rules', {}),
            'functions': schema_data.get('functions', {})
        }

    def _detect_game_system(self, rulebook_schema: Dict[str, Any], file_info: Dict[str, Any]) -> str:
        file_name = (file_info.get('file_name') or file_info.get('name') or '').lower()
        description = (rulebook_schema.get('description') or '').lower()
        name = (rulebook_schema.get('name') or '').lower()
        content = f"{file_name} {name} {description}"
        if 'dnd' in content or 'd&d' in content or '龙与地下城' in content:
            return 'dnd_5e'
        return rulebook_schema.get('game_system', 'generic')
    
    async def _validate_entity(self, entity_type: str, entity_def: Dict[str, Any], all_entities: List[str]) -> Dict[str, List[str]]:
        """Validate single entity definition"""
        errors = []
        warnings = []
        
        # Check required fields
        if 'properties' not in entity_def:
            errors.append(f"Entity {entity_type} missing properties field")
        
        # Validate properties
        properties = entity_def.get('properties', {})
        for prop_name, prop_def in properties.items():
            if 'type' not in prop_def:
                warnings.append(f"Entity {entity_type} property {prop_name} missing type field")
        
        # Validate relationships
        relationships = entity_def.get('relationships', {})
        for rel_name, rel_def in relationships.items():
            target = rel_def.get('target') or rel_def.get('target_entity_type')
            if target and target not in all_entities:
                errors.append(f"Relationship {rel_name} references non-existent entity: {target}")
        
        return {'errors': errors, 'warnings': warnings}
    
    async def _check_circular_references(self, entities: Dict[str, Any]) -> List[str]:
        """Check circular references"""
        errors = []
        
        # Build entity relationship graph
        entity_graph = {entity_type: set() for entity_type in entities.keys()}
        
        for entity_type, entity_def in entities.items():
            relationships = entity_def.get('relationships', {})
            for rel_name, rel_def in relationships.items():
                target = rel_def.get('target') or rel_def.get('target_entity_type')
                if target and target in entity_graph:
                    entity_graph[entity_type].add(target)
        
        # Check circular references
        for entity_type in entity_graph:
            visited = set()
            if self._has_cycle(entity_type, entity_graph, visited):
                errors.append(f"Entity {entity_type} has circular reference")
        
        return errors
    
    def _has_cycle(self, entity_type: str, graph: Dict[str, set], visited: set) -> bool:
        """Check if there's a circular reference"""
        if entity_type in visited:
            return True
        
        visited.add(entity_type)
        
        for neighbor in graph.get(entity_type, set()):
            if self._has_cycle(neighbor, graph, visited.copy()):
                return True
        
        return False


# 导出函数
__all__ = [
    "SchemaConverter",
    "CompleteRulebookData",
    "CharacterCreationModel",
    "CreationFormField",
    "CreationFieldGroup",
    "CreationValidationRule",
    "CreationCalculationRule"
]