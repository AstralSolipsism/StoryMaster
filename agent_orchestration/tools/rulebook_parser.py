"""
规则书解析工具（修订版）
为智能体编排框架提供规则书解析功能，包含角色卡创建模型提取
"""

import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..interfaces import ITool, ToolSchema, ToolParameter, ToolResult
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.logging import app_logger
from core.exceptions import StoryMasterValidationError


class RulebookParserTool(ITool):
    """规则书解析工具"""
    
    def __init__(self):
        self.logger = app_logger
        self._initialize_prompt_template()
    
    def _initialize_prompt_template(self):
        """初始化解析提示模板"""
        self.base_prompt = """你是一个专业的桌上角色扮演游戏规则书解析专家。

你的任务是仔细分析规则书内容，提取其中的游戏规则、实体定义和关系信息，以及角色卡创建所需的信息。

### 任务要求分为两部分：

#### 第一部分：提取完整规则书Schema

1. 识别实体类型（如角色、技能、物品、法术、阵营等）
2. 提取每个实体的属性和属性类型
3. 识别实体间的关系（如角色拥有技能、物品等）
4. 提取游戏规则和计算公式
5. 识别验证规则和约束条件

实体类型识别指南：
- Character: 角色类实体，包含角色基本信息、属性值、技能等
- Skill: 技能类实体，包含技能名称、相关属性、熟练度等
- Item: 物品类实体，包含物品名称、类型、属性等
- Spell: 法术类实体，包含法术名称、等级、学派等
- Class: 职业类实体，包含职业名称、特点、能力等
- Race: 种族类实体，包含种族名称、特点、加值等
- Ability: 属性类实体，如力量、敏捷、智力等
- Background: 背景类实体
- Faction: 阵营类实体
- Location: 地点类实体

属性类型规范：
- string: 文本类型
- integer: 整数类型
- number: 数值类型（包括小数）
- boolean: 布尔类型
- array: 数组类型
- object: 对象类型

关系类型规范：
- one_to_one: 一对一关系
- one_to_many: 一对多关系
- many_to_one: 多对一关系
- many_to_many: 多对多关系

规则类型规范：
- formula: 计算公式（如属性修正值计算）
- validation: 验证规则（如数值范围检查）
- constraint: 约束条件
- calculation: 复杂计算

#### 第二部分：提取角色卡创建模型（重要）

**这是玩家创建角色时需要填写表单的简化模型，不是完整的角色实体定义。请分析规则书中的角色创建规则，提取以下内容：**

1. **基础信息字段**（玩家必须选择/输入的）：
   - 角色名称（文本输入）
   - 种族（下拉选择，提供选项）
   - 职业（下拉选择，提供选项）
   - 等级（数字输入，有范围限制）
   - 背景/阵营等（根据规则书）

2. **属性字段**（玩家需要分配的）：
   - 六项属性（力量、敏捷、体质等）
   - 属性分配方式（点数分配、随机生成等）
   - 属性值范围限制

3. **选择类字段**（玩家需要选择的）：
   - 技能选择（技能列表，熟练度标记）
   - 特性选择（根据种族/职业）
   - 专长选择（根据等级）
   - 法术选择（如果有）

4. **自动计算字段**（标记为只读，显示计算结果）：
   - 属性修正值（strength_modifier = floor((strength-10)/2)）
   - 熟练度加值（proficiency_bonus = floor((level-1)/4)+2）
   - 生命值、护甲等级等
   - 技能加值

5. **字段分组和UI设计**：
   - 基本信息、属性值、战斗属性、技能、装备等分组
   - 推荐的UI组件类型（input、select、textarea、checkbox等）
   - 字段显示顺序
   - 条件显示逻辑（如某些职业才显示的字段）

6. **验证规则**（角色创建时的业务规则）：
   - 属性总和限制
   - 种族与职业的兼容性
   - 等级限制
   - 其他规则书特定的约束

7. **计算规则**（自动计算的字段及其公式）：
   - 属性修正值计算
   - 熟练度加值计算
   - 生命值计算
   - 其他派生属性

"""
    
    def get_schema(self) -> ToolSchema:
        """返回工具模式定义"""
        return ToolSchema(
            name="rulebook_parser",
            description="解析规则书文件内容，提取游戏规则、实体定义和角色创建模型。支持PDF、Word、TXT、JSON、Markdown等格式。",
            parameters=[
                ToolParameter(
                    name="content",
                    type="string",
                    description="规则书文本内容或内容块",
                    required=True
                ),
                ToolParameter(
                    name="file_type",
                    type="string",
                    description="文件类型（pdf/docx/txt/json/md）",
                    required=False
                ),
                ToolParameter(
                    name="metadata",
                    type="object",
                    description="文件元数据信息",
                    required=False
                ),
                ToolParameter(
                    name="is_preformatted",
                    type="boolean",
                    description="内容是否已经格式化为规则书Schema",
                    required=False,
                    default=False
                )
            ],
            returns="解析后的规则书数据结构，包含rulebook_schema和character_creation_model两部分（JSON格式）"
        )
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行规则书解析
        
        Args:
            content: 规则书文本内容
            file_type: 文件类型（可选）
            metadata: 文件元数据（可选）
            is_preformatted: 是否已格式化（可选）
            
        Returns:
            Dict: 解析后的规则书数据结构
        """
        try:
            content = kwargs.get('content', '')
            file_type = kwargs.get('file_type', 'txt')
            is_preformatted = kwargs.get('is_preformatted', False)
            metadata = kwargs.get('metadata', {})
            
            if not content:
                raise StoryMasterValidationError("内容不能为空")
            
            # 如果内容已经是格式化的规则书Schema，直接返回
            if is_preformatted and file_type == 'json':
                try:
                    result = json.loads(content)
                    self.logger.info("内容已为格式化规则书Schema，直接返回")
                    return result
                except json.JSONDecodeError as e:
                    self.logger.warning(f"JSON解析失败，尝试重新解析: {e}")
            
            # 构建完整的解析提示
            full_prompt = self._build_parsing_prompt(content, file_type, metadata)
            
            self.logger.info(f"开始解析规则书内容，长度: {len(content)} 字符，类型: {file_type}")
            
            # 返回提示和内容，由智能体框架处理
            return {
                "action": "parse_with_ai",
                "prompt": full_prompt,
                "content": content,
                "metadata": metadata
            }
            
        except Exception as e:
            self.logger.error(f"规则书解析失败: {e}", exc_info=True)
            raise StoryMasterValidationError(f"规则书解析失败: {str(e)}")
    
    def _build_parsing_prompt(self, content: str, file_type: str, metadata: Dict[str, Any]) -> str:
        """构建完整的解析提示"""
        # 截取内容以避免超过token限制
        max_content_length = 8000
        content_preview = content[:max_content_length]
        
        if len(content) > max_content_length:
            content_preview += f"\n\n[注意：内容已截断，共{len(content)}字符，只显示前{max_content_length}字符]"
        
        prompt = f"""{self.base_prompt}

文件信息：
- 文件类型: {file_type}
- 内容长度: {len(content)} 字符

"""
        
        # 添加元数据信息
        if metadata:
            prompt += "\n文件元数据：\n"
            for key, value in metadata.items():
                if key not in ['file_path', 'processed_at', 'file_hash', 'mime_type']:
                    prompt += f"- {key}: {value}\n"
        
        prompt += f"""

规则书内容：
```
{content_preview}
```

### 输出格式要求（包含两部分）

请严格按照以下JSON格式输出结果（包含两部分：rulebook_schema和character_creation_model）：

```json
{{
  "rulebook_schema": {{
    "schema_id": "<生成的schema_id>",
    "name": "<规则书名称>",
    "version": "1.0.0",
    "author": "system",
    "game_system": "<游戏系统>",
    "description": "<规则书描述>",
    "created_at": "{datetime}",
    "updated_at": "{datetime}",
    "is_active": false,
    
    "entities": {{
      "Character": {{
        "label": "Character",
        "plural_label": "Characters",
        "properties": {{
          "name": {{
            "type": "string",
            "required": true,
            "description": "角色名称"
          }},
          "level": {{
            "type": "integer",
            "required": true,
            "description": "角色等级",
            "min_value": 1,
            "max_value": 20,
            "default": 1
          }},
          "ability_scores": {{
            "type": "object",
            "required": true,
            "description": "六项属性值",
            "properties": {{
              "strength": {{
                "type": "integer",
                "description": "力量",
                "default": 10
              }},
              "dexterity": {{
                "type": "integer",
                "description": "敏捷",
                "default": 10
              }}
            }}
          }}
        }},
        "relationships": {{
          "has_skills": {{
            "target": "Skill",
            "relationship_type": "many_to_many",
            "description": "角色拥有的技能"
          }},
          "has_equipment": {{
            "target": "Item",
            "relationship_type": "many_to_many",
            "description": "角色拥有的装备"
          }}
        }},
        "validation_rules": {{
          "level_range": {{
            "type": "validation",
            "description": "等级范围验证",
            "applicable_to": ["level"],
            "expression": "1 <= level <= 20"
          }}
        }}
      }}
    }},
    
    "rules": {{
      "ability_modifier": {{
        "type": "formula",
        "description": "属性修正值计算",
        "expression": "floor((ability_score - 10) / 2)",
        "applicable_to": ["ability_scores"],
        "output_property": "modifier"
      }},
      "proficiency_bonus": {{
        "type": "formula",
        "description": "熟练度加值计算",
        "expression": "floor((level - 1) / 4) + 2",
        "applicable_to": ["level"],
        "output_property": "proficiency_bonus"
      }}
    }},
    
    "functions": {{
      "validate_level_range": {{
        "description": "验证等级范围",
        "parameters": ["level"],
        "expression": "return 1 <= level <= 20"
      }}
    }}
  }},
  
  "character_creation_model": {{
    "model_id": "char_creation_<schema_id>",
    "model_name": "D&D 5e角色创建",
    "model_description": "D&D 5e规则书的角色创建流程",
    
    "fields": {{
      "name": {{
        "name": "name",
        "type": "string",
        "label": "角色名称",
        "description": "为你的角色起一个名字",
        "required": true,
        "default": "",
        "display_order": 1,
        "ui_type": "input",
        "ui_options": {{
          "placeholder": "输入角色名称",
          "max_length": 100
        }}
      }},
      "race": {{
        "name": "race",
        "type": "enum",
        "label": "种族",
        "description": "选择角色的种族",
        "required": true,
        "enum_options": [
          {{"value": "Human", "label": "人类", "description": "人类种族"}},
          {{"value": "Elf", "label": "精灵", "description": "精灵种族"}},
          {{"value": "Dwarf", "label": "矮人", "description": "矮人种族"}}
        ],
        "display_order": 2,
        "ui_type": "select",
        "ui_options": {{
          "searchable": true
        }}
      }},
      "class": {{
        "name": "class",
        "type": "enum",
        "label": "职业",
        "description": "选择角色的职业",
        "required": true,
        "enum_options": [
          {{"value": "Fighter", "label": "战士", "description": "战斗专家"}},
          {{"value": "Wizard", "label": "法师", "description": "奥术施法者"}}
        ],
        "display_order": 3,
        "ui_type": "select",
        "ui_options": {{
          "searchable": true
        }}
      }},
      "level": {{
        "name": "level",
        "type": "integer",
        "label": "等级",
        "description": "角色等级（1-20）",
        "required": true,
        "min_value": 1,
        "max_value": 20,
        "default": 1,
        "display_order": 4,
        "ui_type": "input",
        "ui_options": {{
          "step": 1
        }}
      }},
      "strength": {{
        "name": "strength",
        "type": "integer",
        "label": "力量",
        "description": "力量属性（1-30）",
        "required": true,
        "min_value": 1,
        "max_value": 30,
        "default": 10,
        "display_order": 10,
        "ui_type": "input",
        "ui_options": {{
          "step": 1
        }}
      }},
      "strength_modifier": {{
        "name": "strength_modifier",
        "type": "integer",
        "label": "力量修正值",
        "description": "自动计算的力量修正值",
        "required": false,
        "default": 0,
        "display_order": 11,
        "ui_type": "input",
        "read_only": true,
        "depends_on": ["strength"]
      }}
    }},
    
    "field_groups": [
      {{
        "name": "basic_info",
        "label": "基本信息",
        "description": "角色基础信息",
        "display_order": 1,
        "collapsible": false,
        "fields": ["name", "race", "class", "level"]
      }},
      {{
        "name": "ability_scores",
        "label": "属性值",
        "description": "六项属性值",
        "display_order": 2,
        "collapsible": true,
        "collapsed_by_default": false,
        "fields": ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
      }}
    ],
    
    "validation_rules": [
      {{
        "name": "ability_score_sum_limit",
        "type": "cross_field",
        "description": "属性值总和不能超过80",
        "error_message": "属性值总和超过限制（最大80）",
        "expression": "sum(ability_scores.values()) <= 80",
        "applicable_fields": ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"],
        "severity": "error"
      }},
      {{
        "name": "required_fields",
        "type": "custom",
        "description": "检查必填字段",
        "error_message": "请填写所有必填字段",
        "expression": "name != '' && race != '' && class != '' && level >= 1",
        "applicable_fields": ["name", "race", "class", "level"],
        "severity": "error"
      }}
    ],
    
    "calculation_rules": [
      {{
        "name": "strength_modifier_calculation",
        "output_field": "strength_modifier",
        "description": "力量修正值计算",
        "formula": "floor((strength - 10) / 2)",
        "input_fields": ["strength"],
        "auto_apply": true,
        "display_formula": "⌊(力量 - 10) / 2⌋"
      }},
      {{
        "name": "proficiency_bonus_calculation",
        "output_field": "proficiency_bonus",
        "description": "熟练度加值计算",
        "formula": "floor((level - 1) / 4) + 2",
        "input_fields": ["level"],
        "auto_apply": true,
        "display_formula": "⌊(等级 - 1) / 4⌋ + 2"
      }}
    ],
    
    "templates": {{
      "standard": {{
        "label": "标准角色",
        "description": "使用标准点数分配",
        "data": {{
          "strength": 10,
          "dexterity": 10,
          "constitution": 10,
          "intelligence": 10,
          "wisdom": 10,
          "charisma": 10
        }}
      }}
    }},
    
    "metadata": {{
      "creation_style": "point_buy",
      "point_buy_limits": {{
        "total": 27,
        "min_per_ability": 8,
        "max_per_ability": 15
      }},
      "supports_rolling": true
    }},
    
    "schema_compatibility": {{
      "character_properties": "name, race, class, level, ability_scores",
      "character_relationships": "has_skills, has_equipment, belongs_to_user"
    }}
  }}
}}
```

### 重要提示

#### 第一部分：完整规则书Schema
1. 所有实体都包含完整的属性定义
2. 关系的target字段必须引用已定义的实体类型
3. 规则的applicable_to字段必须引用已定义的属性或实体
4. 所有必要字段都已填写
5. JSON格式正确且可以解析

#### 第二部分：角色卡创建模型（新增）
1. **区分系统数据和用户输入**：
   - 完整Schema包含所有系统需要的字段
   - 创建模型只包含玩家需要输入/选择的部分
   - 自动计算的字段在创建模型中标记为read_only

2. **优先考虑用户体验**：
   - 字段分组要合理（基本信息、属性、技能、装备等）
   - 推荐合适的UI组件类型（input、select、textarea、checkbox等）
   - 提供清晰的描述和帮助文本
   - 提供合理的默认值

3. **提取真实的创建流程**：
   - 分析规则书中实际的角色创建步骤
   - 不要只是列出所有可能的字段
   - 关注玩家在创建时真正需要做的选择

4. **包含规则书特定的逻辑**：
   - 不同规则书有不同的创建流程
   - 提取规则书独特的验证规则
   - 包含规则书特定的计算公式

5. **字段定义要求**：
   - 每个字段必须有name、type、label
   - 如果是枚举类型，必须提供enum_options列表
   - 对于计算字段，必须标记read_only和depends_on
   - 合理设置display_order

6. **验证规则要求**：
   - 提供清晰的error_message
   - 合理设置severity（error/warning/info）
   - 表达式要能正确评估
   - 适用于相关的字段列表

7. **计算规则要求**：
   - 提供清晰的description
   - 表达式要能正确计算
   - 指定input_fields和output_field
   - 可选提供display_formula用于前端展示

8. **字段分组要求**：
   - 分组名称要简洁明了
   - 提供分组描述
   - 合理设置display_order
   - 可以设置collapsible和collapsed_by_default

9. **元数据**：
   - 包含创建相关的元信息
   - 如creation_style（点数分配、随机生成等）
   - 提供模板数据
   - 包含schema_compatibility映射关系

10. **输出格式**：
    - JSON格式必须正确且可解析
    - 不要添加任何额外的解释或说明
    - 只返回JSON数据

11. **示例参考**：
    请参考示例中的JSON结构，确保输出格式正确
    - 确保包含rulebook_schema和character_creation_model两部分
    - 确保每个部分的字段都完整

请严格按照要求的JSON格式输出解析结果，不要添加任何额外的解释或说明。只返回JSON数据。

现在开始分析以下规则书内容："""
        
        return prompt
 

class SchemaValidationTool(ITool):
    """模式验证工具"""
    
    def __init__(self):
        self.logger = app_logger
    
    def get_schema(self) -> ToolSchema:
        """返回工具模式定义"""
        return ToolSchema(
            name="schema_validation",
            description="验证规则书Schema和角色卡创建模型的完整性和正确性",
            parameters=[
                ToolParameter(
                    name="schema_data",
                    type="object",
                    description="规则书数据（包含rulebook_schema和character_creation_model）",
                    required=True
                )
            ],
            returns="验证结果，包含错误和警告信息"
        )
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行模式验证
        
        Args:
            schema_data: 规则书数据
            
        Returns:
            Dict: 验证结果
        """
        try:
            schema_data = kwargs.get('schema_data', {})
            
            if not schema_data:
                raise StoryMasterValidationError("Schema数据不能为空")
            
            # 执行验证
            validation_result = await self._validate_schema(schema_data)
            
            self.logger.info(f"Schema验证完成: {validation_result['valid']}, 错误: {len(validation_result['errors'])}, 警告: {len(validation_result['warnings'])}")
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"Schema验证失败: {e}", exc_info=True)
            raise StoryMasterValidationError(f"Schema验证失败: {str(e)}")
    
    async def _validate_schema(self, schema_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证Schema数据（支持两部分）"""
        errors = []
        warnings = []
        
        # 验证第一部分：完整规则书Schema
        if 'rulebook_schema' not in schema_data:
            errors.append("缺少必需字段: rulebook_schema")
        else:
            rulebook_errors = await self._validate_rulebook_schema(schema_data['rulebook_schema'])
            errors.extend(rulebook_errors['errors'])
            warnings.extend(rulebook_errors['warnings'])
        
        # 验证第二部分：角色卡创建模型（可选）
        if 'character_creation_model' in schema_data:
            creation_errors = await self._validate_character_creation_model(schema_data['character_creation_model'])
            errors.extend(creation_errors['errors'])
            warnings.extend(creation_errors['warnings'])
        else:
            warnings.append("缺少角色卡创建模型，角色创建功能可能受限")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    async def _validate_rulebook_schema(self, schema_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """验证完整规则书Schema"""
        errors = []
        warnings = []
        
        # 检查必需字段
        required_fields = ['schema_id', 'name', 'game_system', 'entities']
        for field in required_fields:
            if field not in schema_data:
                errors.append(f"缺少必需字段: {field}")
        
        # 检查实体定义
        entities = schema_data.get('entities', {})
        if not entities:
            errors.append("必须定义至少一个实体")
        else:
            for entity_type, entity_def in entities.items():
                entity_errors = await self._validate_entity(entity_type, entity_def, entities.keys())
                errors.extend(entity_errors['errors'])
                warnings.extend(entity_errors['warnings'])
        
        # 检查规则定义
        rules = schema_data.get('rules', {})
        for rule_name, rule_def in rules.items():
            if 'type' not in rule_def:
                errors.append(f"规则 {rule_name} 缺少类型字段")
            
            if 'applicable_to' not in rule_def:
                warnings.append(f"规则 {rule_name} 缺少适用范围字段")
            
            # 检查规则引用的实体是否存在
            applicable_to = rule_def.get('applicable_to', [])
            for ref in applicable_to:
                if ref in entities:
                    warnings.append(f"规则 {rule_name} 直接引用实体 {ref}，应该引用属性")
        
        return {'errors': errors, 'warnings': warnings}
    
    async def _validate_character_creation_model(self, creation_model: Dict[str, Any]) -> Dict[str, List[str]]:
        """验证角色卡创建模型"""
        errors = []
        warnings = []
        
        # 检查必需字段
        required_fields = ['model_id', 'model_name', 'fields']
        for field in required_fields:
            if field not in creation_model:
                errors.append(f"创建模型缺少必需字段: {field}")
        
        # 验证字段定义
        fields = creation_model.get('fields', {})
        if not fields:
            errors.append("创建模型必须定义fields字段")
        else:
            for field_name, field_def in fields.items():
                if 'name' not in field_def or 'type' not in field_def or 'label' not in field_def:
                    errors.append(f"字段 {field_name} 缺少必要定义（name, type, label）")
                
                # 验证枚举类型字段
                if field_def.get('type') == 'enum':
                    if 'enum_options' not in field_def:
                        errors.append(f"枚举字段 {field_name} 必须定义enum_options")
                    elif not isinstance(field_def.get('enum_options'), list):
                        errors.append(f"字段 {field_name} 的 enum_options 必须是列表")
        
        # 验证字段分组
        field_groups = creation_model.get('field_groups', [])
        for group_def in field_groups:
            if 'name' not in group_def or 'fields' not in group_def:
                warnings.append(f"字段组 {group_def.get('name')} 可能不完整")
        
        # 验证验证规则
        validation_rules = creation_model.get('validation_rules', [])
        for rule_def in validation_rules:
            if 'name' not in rule_def or 'expression' not in rule_def or 'error_message' not in rule_def:
                warnings.append(f"验证规则 {rule_def.get('name')} 可能不完整")
        
        # 验证计算规则
        calculation_rules = creation_model.get('calculation_rules', [])
        for rule_def in calculation_rules:
            if 'name' not in rule_def or 'formula' not in rule_def or 'output_field' not in rule_def:
                warnings.append(f"计算规则 {rule_def.get('name')} 可能不完整")
        
        return {'errors': errors, 'warnings': warnings}
    
    async def _validate_entity(self, entity_type: str, entity_def: Dict[str, Any], all_entities: List[str]) -> Dict[str, List[str]]:
        """验证单个实体定义"""
        errors = []
        warnings = []
        
        # 检查必需字段
        if 'properties' not in entity_def:
            errors.append(f"实体 {entity_type} 缺少 properties 字段")
        elif not entity_def['properties']:
            warnings.append(f"实体 {entity_type} 没有定义任何属性")
        
        # 验证属性
        properties = entity_def.get('properties', {})
        for prop_name, prop_def in properties.items():
            if 'type' not in prop_def:
                errors.append(f"实体 {entity_type} 的属性 {prop_name} 缺少类型字段")
            
            # 检查枚举值
            if 'enum_values' in prop_def and prop_def['enum_values']:
                if not isinstance(prop_def['enum_values'], list):
                    errors.append(f"属性 {prop_name} 的 enum_values 必须是列表")
        
        # 验证关系
        relationships = entity_def.get('relationships', {})
        for rel_name, rel_def in relationships.items():
            target = rel_def.get('target') or rel_def.get('target_entity_type')
            if not target:
                warnings.append(f"关系 {rel_name} 缺少目标实体类型字段")
            elif target not in all_entities:
                errors.append(f"关系 {rel_name} 引用了不存在的实体: {target}")
        
        return {'errors': errors, 'warnings': warnings}


class ContentExtractionTool(ITool):
    """内容提取工具（保留用于向后兼容）"""
    
    def __init__(self):
        self.logger = app_logger
    
    def get_schema(self) -> ToolSchema:
        """返回工具模式定义"""
        return ToolSchema(
            name="content_extraction",
            description="从规则书内容中提取特定类型的信息（如属性、技能、物品等）",
            parameters=[
                ToolParameter(
                    name="content",
                    type="string",
                    description="规则书文本内容",
                    required=True
                ),
                ToolParameter(
                    name="extract_type",
                    type="string",
                    description="提取类型（attributes/skills/items/spells/classes/races/abilities/backgrounds/factions/locations）",
                    required=True
                )
            ],
            returns="提取到的特定类型信息"
        )
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行内容提取
        
        Args:
            content: 规则书文本内容
            extract_type: 提取类型
            
        Returns:
            Dict: 提取到的信息
        """
        try:
            content = kwargs.get('content', '')
            extract_type = kwargs.get('extract_type', '').lower()
            
            if not content:
                raise StoryMasterValidationError("内容不能为空")
            
            # 根据提取类型执行不同的提取逻辑
            extracted_data = await self._extract_by_type(content, extract_type)
            
            self.logger.info(f"内容提取完成: 类型={extract_type}, 提取数量={len(extracted_data)}")
            
            return {
                'extract_type': extract_type,
                'data': extracted_data,
                'count': len(extracted_data)
            }
            
        except Exception as e:
            self.logger.error(f"内容提取失败: {e}", exc_info=True)
            raise StoryMasterValidationError(f"内容提取失败: {str(e)}")
    
    async def _extract_by_type(self, content: str, extract_type: str) -> List[Dict[str, Any]]:
        """根据类型提取内容（占位实现）"""
        # 注意：这是一个简化的实现，实际应该使用AI模型进行智能提取
        # 这里我们返回空列表，让AI智能体处理实际的提取工作
        
        return []


# 工具注册函数
async def register_rulebook_parser_tools(tool_manager):
    """注册所有规则书解析工具"""
    await tool_manager.register_tool(RulebookParserTool(), category="rulebook")
    await tool_manager.register_tool(SchemaValidationTool(), category="rulebook")
    await tool_manager.register_tool(ContentExtractionTool(), category="rulebook")