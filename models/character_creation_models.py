"""
角色卡创建相关数据模型（修订版）

由智能体在解析规则书时生成的角色卡创建模型数据结构
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field


class CreationFormField(BaseModel):
    """角色卡创建表单字段"""
    name: str = Field(..., description="字段名称")
    type: str = Field(..., description="字段类型：string/integer/number/boolean/array/object/enum")
    label: str = Field(..., description="显示标签")
    description: str = Field(default="", description="字段描述/帮助文本")
    required: bool = Field(default=True, description="是否必填")
    default: Any = Field(None, description="默认值")
    
    # 约束条件
    min_value: Optional[Union[int, float]] = Field(None, description="最小值")
    max_value: Optional[Union[int, float]] = Field(None, description="最大值")
    min_length: Optional[int] = Field(None, description="最小长度")
    max_length: Optional[int] = Field(None, description="最大长度")
    pattern: Optional[str] = Field(None, description="正则表达式模式")
    
    # 枚举类型专用
    enum_options: Optional[List[Dict[str, Any]]] = Field(None, description="枚举选项列表")
    
    # UI相关
    display_order: int = Field(default=0, description="显示顺序")
    ui_type: Optional[str] = Field(None, description="UI组件类型：input/select/textarea/checkbox/radio等")
    ui_options: Optional[Dict[str, Any]] = Field(None, description="UI组件选项")
    
    # 逻辑相关
    depends_on: Optional[List[str]] = Field(None, description="依赖的字段列表")
    conditional_display: Optional[Dict[str, Any]] = Field(None, description="条件显示逻辑")
    read_only: bool = Field(default=False, description="是否只读（自动计算字段）")
    hidden: bool = Field(default=False, description="是否隐藏")


class CreationFieldGroup(BaseModel):
    """字段分组"""
    name: str = Field(..., description="分组名称")
    label: str = Field(..., description="分组显示标签")
    description: str = Field(default="", description="分组描述")
    display_order: int = Field(default=0, description="显示顺序")
    collapsible: bool = Field(default=False, description="是否可折叠")
    collapsed_by_default: bool = Field(default=False, description="默认是否折叠")
    fields: List[str] = Field(..., description="包含的字段名称列表")


class CreationValidationRule(BaseModel):
    """创建验证规则"""
    name: str = Field(..., description="规则名称")
    type: str = Field(..., description="规则类型：custom/cross_field/aggregate")
    description: str = Field(..., description="规则描述")
    error_message: str = Field(..., description="错误提示信息")
    expression: str = Field(..., description="验证表达式")
    applicable_fields: List[str] = Field(..., description="适用的字段列表")
    severity: str = Field(default="error", description="严重程度：error/warning/info")


class CreationCalculationRule(BaseModel):
    """创建计算规则"""
    name: str = Field(..., description="计算规则名称")
    output_field: str = Field(..., description="输出字段名称")
    description: str = Field(..., description="计算描述")
    formula: str = Field(..., description="计算公式")
    input_fields: List[str] = Field(..., description="输入字段列表")
    auto_apply: bool = Field(default=True, description="是否自动应用")
    display_formula: Optional[str] = Field(None, description="显示公式（用于前端展示）")


class CharacterCreationModel(BaseModel):
    """角色卡创建模型（由智能体生成）"""
    model_id: str = Field(..., description="模型唯一标识")
    model_name: str = Field(..., description="模型名称")
    model_description: str = Field(default="", description="模型描述")
    
    # 字段定义
    fields: Dict[str, CreationFormField] = Field(..., description="字段定义字典")
    
    # 字段分组
    field_groups: List[CreationFieldGroup] = Field(default_factory=list, description="字段分组")
    
    # 验证规则
    validation_rules: List[CreationValidationRule] = Field(default_factory=list, description="验证规则")
    
    # 计算规则
    calculation_rules: List[CreationCalculationRule] = Field(default_factory=list, description="计算规则")
    
    # 模板数据
    templates: Optional[Dict[str, Any]] = Field(None, description="预设模板数据")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="其他元数据")
    
    # 兼容性信息
    schema_compatibility: Dict[str, str] = Field(default_factory=dict, description="与完整Schema的映射关系")


# API请求/响应模型


class CharacterCreationFormRequest(BaseModel):
    """获取角色卡创建表单请求"""
    schema_id: str = Field(..., description="规则书Schema ID")
    user_id: str = Field(..., description="用户ID")
    entity_type: str = Field(default="Character", description="实体类型")


class CharacterCreationFormResponse(BaseModel):
    """角色卡创建表单响应"""
    schema_id: str = Field(..., description="规则书Schema ID")
    model_id: str = Field(..., description="创建模型ID")
    model_name: str = Field(..., description="模型名称")
    model_description: str = Field(default="", description="模型描述")
    
    # 字段定义（按显示顺序排序）
    fields: List[Dict[str, Any]] = Field(..., description="字段定义列表")
    
    # 字段分组
    field_groups: List[Dict[str, Any]] = Field(default_factory=list, description="字段分组")
    
    # 验证规则
    validation_rules: List[Dict[str, Any]] = Field(default_factory=list, description="验证规则")
    
    # 计算规则
    calculation_rules: List[Dict[str, Any]] = Field(default_factory=list, description="计算规则")
    
    # 模板数据
    templates: Dict[str, Any] = Field(default_factory=dict, description="预设模板")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    # 警告信息
    warnings: List[str] = Field(default_factory=list, description="警告信息")


class CharacterCreationRequest(BaseModel):
    """角色卡创建请求"""
    schema_id: str = Field(..., description="规则书Schema ID")
    user_id: str = Field(..., description="用户ID")
    character_data: Dict[str, Any] = Field(..., description="角色数据")


class CharacterCreationResponse(BaseModel):
    """角色卡创建响应"""
    character_id: str = Field(..., description="角色ID")
    character_data: Dict[str, Any] = Field(..., description="完整的角色数据（包含用户输入和计算结果）")
    calculated_properties: Dict[str, Any] = Field(default_factory=dict, description="计算后的属性（派生值）")
    warnings: List[str] = Field(default_factory=list, description="警告信息")


class CharacterData(BaseModel):
    """角色数据"""
    character_id: str = Field(..., description="角色ID")
    entity_type: str = Field(default="Character", description="实体类型")
    properties: Dict[str, Any] = Field(..., description="角色属性")
    relationships: Dict[str, Any] = Field(default_factory=dict, description="角色关系")
    schema_id: str = Field(..., description="规则书Schema ID")
    user_id: str = Field(..., description="用户ID")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class CalculatedCharacterData(BaseModel):
    """计算后的角色数据"""
    character_id: str = Field(..., description="角色ID")
    base_properties: Dict[str, Any] = Field(..., description="基础属性（用户输入）")
    calculated_properties: Dict[str, Any] = Field(..., description="计算属性（所有属性）")
    derived_values: Dict[str, Any] = Field(default_factory=dict, description="派生值（仅计算的）")
    validation_warnings: List[str] = Field(default_factory=list, description="验证警告")