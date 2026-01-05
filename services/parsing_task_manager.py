"""
解析任务管理器
负责管理规则书解析任务的整个生命周期
"""

import asyncio
import uuid
import json
import re
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from fastapi import UploadFile

from ..core.logging import app_logger
from ..core.exceptions import StoryMasterValidationError, NotFoundError
from ..models.parsing_models import (
    ProcessedFile,
    ParsingTaskStatus,
    RulebookParsingResult,
    RulebookConfirmationRequest
)
from ..services.file_processor import FileProcessor
from ..services.schema_converter import SchemaConverter
from ..services.integrations.rulebook_parser_integration import RulebookParserIntegration
from ..agent_orchestration.core import create_agent, create_orchestrator
from ..agent_orchestration.interfaces import ExecutionContext, AgentConfig, ReasoningMode
from ..model_adapter.scheduler import ModelScheduler
from ..data_storage.rulebook_manager import RulebookManager


class ParsingTask:
    """解析任务"""
    
    def __init__(self, task_id: str, request_data: Dict[str, Any]):
        self.task_id = task_id
        self.request_data = request_data
        self.status = "pending"
        self.progress = 0.0
        self.message = "任务已创建"
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.estimated_completion = None
        self.current_step = "初始化"
        
        # 任务结果
        self.processed_file: Optional[ProcessedFile] = None
        self.parsing_result: Optional[Dict[str, Any]] = None
        self.converted_schema: Optional[Dict[str, Any]] = None
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def update_status(self, status: str, progress: float, message: str, step: str = None):
        """更新任务状态"""
        self.status = status
        self.progress = progress
        self.message = message
        self.updated_at = datetime.now()
        if step:
            self.current_step = step
        
        # 估算完成时间（简单线性估算）
        if progress > 0 and status != "completed" and status != "failed":
            elapsed = (self.updated_at - self.created_at).total_seconds()
            if elapsed > 0:
                estimated_total = elapsed / progress
                self.estimated_completion = self.created_at + timedelta(seconds=estimated_total)
    
    def to_status_model(self) -> ParsingTaskStatus:
        """转换为状态模型"""
        return ParsingTaskStatus(
            task_id=self.task_id,
            status=self.status,
            progress=self.progress,
            message=self.message,
            created_at=self.created_at,
            updated_at=self.updated_at,
            estimated_completion=self.estimated_completion,
            current_step=self.current_step
        )
    
    def to_result_model(self) -> RulebookParsingResult:
        """转换为结果模型"""
        return RulebookParsingResult(
            task_id=self.task_id,
            status=self.status,
            rulebook_data=self.converted_schema,
            parsing_errors=self.errors,
            validation_warnings=self.warnings,
            preview_sections=self._generate_preview(),
            file_metadata=self.processed_file.metadata if self.processed_file else None
        )
    
    def _generate_preview(self) -> List[Dict[str, Any]]:
        """生成预览数据"""
        if not self.converted_schema or 'entities' not in self.converted_schema:
            return []
        
        preview_sections = []
        entities = self.converted_schema.get('entities', {})
        
        # 为每个实体类型生成预览
        for entity_type, entity_def in list(entities.items())[:5]:  # 最多5个实体类型
            preview_sections.append({
                "type": "entity",
                "name": entity_type,
                "label": entity_def.get('label', entity_type),
                "property_count": len(entity_def.get('properties', {})),
                "relationship_count": len(entity_def.get('relationships', {}))
            })
        
        # 规则预览
        rules = self.converted_schema.get('rules', {})
        if rules:
            rule_names = list(rules.keys())[:10]  # 最多10个规则
            preview_sections.append({
                "type": "rules",
                "count": len(rule_names),
                "names": rule_names
            })
        
        return preview_sections


class ParsingTaskManager:
    """解析任务管理器"""
    
    def __init__(
        self,
        file_processor: FileProcessor = None,
        schema_converter: SchemaConverter = None,
        rulebook_manager: RulebookManager = None,
        model_scheduler: ModelScheduler = None
    ):
        self.file_processor = file_processor or FileProcessor()
        self.schema_converter = schema_converter or SchemaConverter()
        self.rulebook_manager = rulebook_manager
        self.model_scheduler = model_scheduler
        
        # 活跃任务存储
        self.active_tasks: Dict[str, ParsingTask] = {}
        
        # 初始化智能体编排器
        self.orchestrator = None
        self.parser_agent = None
        
        app_logger.info("解析任务管理器初始化完成")
    
    async def _initialize_agents(self):
        """初始化智能体"""
        if self.orchestrator is None:
            self.orchestrator = await create_orchestrator()
            
            # 创建规则书解析智能体
            agent_config = AgentConfig(
                agent_id="rulebook_parser",
                agent_type="rulebook_parser",
                version="1.0.0",
                reasoning_mode=ReasoningMode.REACT,
                reasoning_config={"max_iterations": 10},
                enabled_tools=["rulebook_parser", "schema_validation"],
                tool_config={},
                max_execution_time=1800.0,  # 30分钟
                max_memory_usage=1024 * 1024 * 1024,  # 1GB
                concurrency_limit=1,
                system_prompt="""你是一个专业的桌上角色扮演游戏规则书解析专家。
你的任务是分析规则书内容，提取其中的游戏规则、实体定义和关系信息。
请确保提取的数据结构完整且符合系统要求。"""
            )
            
            self.parser_agent = await create_agent(
                agent_id="rulebook_parser",
                config=agent_config,
                model_scheduler=self.model_scheduler,
                orchestrator=self.orchestrator
            )
            
            await self.orchestrator.register_agent(self.parser_agent)
            
            app_logger.info("规则书解析智能体初始化完成")
    
    async def create_parsing_task(self, request_data: Dict[str, Any]) -> str:
        """
        创建解析任务
        
        Args:
            request_data: 请求数据，包含file_name, file_type, parser_model, user_id等
            
        Returns:
            str: 任务ID
        """
        task_id = str(uuid.uuid4())
        
        # 创建任务
        task = ParsingTask(task_id, request_data)
        self.active_tasks[task_id] = task
        
        app_logger.info(f"创建解析任务: {task_id}, 文件: {request_data.get('file_name')}")
        
        return task_id
    
    async def process_parsing_task(self, task_id: str, file: UploadFile) -> None:
        """
        处理解析任务
        
        Args:
            task_id: 任务ID
            file: 上传的文件
        """
        if task_id not in self.active_tasks:
            app_logger.error(f"解析任务不存在: {task_id}")
            return
        
        task = self.active_tasks[task_id]
        
        try:
            # 初始化智能体
            await self._initialize_agents()
            
            # 1. 文件处理阶段 (0%-20%)
            task.update_status("processing", 0.05, "开始处理文件", "文件处理")
            
            # 读取文件内容
            file_content = await file.read()
            file_name = task.request_data['file_name']
            file_type = task.request_data['file_type']
            
            # 处理文件
            processed_file = await self.file_processor.process_uploaded_file(
                file_content, file_name, file_type
            )
            task.processed_file = processed_file
            
            task.update_status("processing", 0.2, "文件处理完成", "文件处理")
            
            # 2. 内容解析阶段 (20%-70%)
            task.update_status("processing", 0.2, "开始解析规则书内容", "内容解析")
            
            # 使用智能体解析内容
            parsing_result = await self._parse_with_agent(
                task.processed_file.content,
                task.request_data.get('parser_model', 'gpt-4'),
                task.processed_file.metadata
            )
            
            task.parsing_result = parsing_result
            
            task.update_status("processing", 0.7, "内容解析完成", "内容解析")
            
            # 3. 数据转换阶段 (70%-90%)
            task.update_status("processing", 0.7, "开始转换数据结构", "数据转换")
            
            # 转换为规则书Schema
            converted_schema = await self.schema_converter.convert_to_rulebook_schema(
                parsing_result,
                task.processed_file.metadata,
                task.request_data['user_id']
            )
            
            task.converted_schema = converted_schema
            
            task.update_status("processing", 0.9, "数据结构转换完成", "数据转换")
            
            # 4. 验证阶段 (90%-100%)
            task.update_status("processing", 0.9, "开始验证解析结果", "结果验证")
            
            # 验证解析结果
            validation_result = await self.schema_converter.validate_parsed_schema(converted_schema)
            
            if validation_result.get('errors'):
                task.errors.extend(validation_result['errors'])
            
            if validation_result.get('warnings'):
                task.warnings.extend(validation_result['warnings'])
            
            # 任务完成
            task.update_status("completed", 1.0, "解析任务完成", "完成")
            
            app_logger.info(f"解析任务完成: {task_id}")
            
        except Exception as e:
            app_logger.error(f"解析任务失败: {task_id}, 错误: {e}", exc_info=True)
            task.errors.append(str(e))
            task.update_status("failed", task.progress, f"解析失败: {str(e)}", "失败")
    
    async def _parse_with_agent(
        self, 
        content: str, 
        model_name: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用智能体解析内容"""
        if not self.parser_agent:
            raise StoryMasterValidationError("解析智能体未初始化")
        
        # 准备解析上下文
        context = ExecutionContext(
            task_id=str(uuid.uuid4()),
            metadata={
                "model_name": model_name,
                "file_metadata": metadata,
                "content_length": len(content)
            }
        )
        
        # 构建解析任务
        file_type = metadata.get('file_type', 'txt')
        is_preformatted = metadata.get('is_preformatted', False)
        
        if is_preformatted and file_type == 'json':
            task_prompt = f"请分析以下JSON格式的规则书数据，验证其结构完整性，并确保所有实体定义和规则都符合系统要求：\n\n{content}"
        else:
            # 截取内容以避免超过token限制
            max_content_length = 8000
            content_preview = content[:max_content_length]
            
            if len(content) > max_content_length:
                content_preview += f"\n\n[注意：内容已截断，共{len(content)}字符，只显示前{max_content_length}字符]"
            
            task_prompt = f"""请分析以下规则书内容，提取其中的游戏规则、实体定义和关系信息。

文件类型: {file_type}
内容长度: {len(content)} 字符

要求：
1. 识别实体类型（如角色、技能、物品、法术等）
2. 提取每个实体的属性和属性类型
3. 识别实体间的关系
4. 提取游戏规则和计算公式
5. 识别验证规则和约束条件

规则书内容：
{content_preview}

请严格按照要求的JSON格式输出解析结果，不要添加任何额外的解释或说明。只返回JSON数据。"""
        
        # 执行解析
        result = await self.parser_agent.execute_task(task_prompt, context)
        
        # 尝试解析JSON结果
        try:
            if isinstance(result, str):
                # 尝试从结果中提取JSON
                json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
                if json_match:
                    result = json_match.group(1)
                elif result.strip().startswith('{'):
                    result = result.strip()
                else:
                    # 尝试找到第一个 { 和最后一个 }
                    start_idx = result.find('{')
                    end_idx = result.rfind('}')
                    if start_idx != -1 and end_idx != -1:
                        result = result[start_idx:end_idx+1]
                    else:
                        raise ValueError("无法从解析结果中提取JSON")
                
                return json.loads(result)
            elif isinstance(result, dict):
                return result
            else:
                raise ValueError(f"解析结果类型错误: {type(result)}")
                
        except (json.JSONDecodeError, ValueError) as e:
            app_logger.error(f"解析结果JSON转换失败: {e}, 原始结果: {str(result)[:500]}")
            raise StoryMasterValidationError(f"解析结果格式错误: {str(e)}")
    
    async def get_task_status(self, task_id: str) -> Optional[ParsingTaskStatus]:
        """获取任务状态"""
        task = self.active_tasks.get(task_id)
        if not task:
            return None
        
        return task.to_status_model()
    
    async def get_task_result(self, task_id: str) -> Optional[RulebookParsingResult]:
        """获取任务结果"""
        task = self.active_tasks.get(task_id)
        if not task:
            return None
        
        return task.to_result_model()
    
    async def confirm_and_save_rulebook(
        self, 
        task_id: str, 
        user_id: str,
        modifications: Optional[Dict[str, Any]] = None
    ) -> str:
        """确认并保存解析后的规则书"""
        task = self.active_tasks.get(task_id)
        if not task:
            raise NotFoundError(f"解析任务不存在: {task_id}", "解析任务")
        
        if task.status != "completed":
            raise StoryMasterValidationError(f"解析任务未完成: {task.status}")
        
        if not task.converted_schema:
            raise StoryMasterValidationError("解析结果为空")
        
        # 应用用户修改
        if modifications:
            task.converted_schema.update(modifications)
            app_logger.info(f"应用用户修改到规则书: {task_id}")
        
        try:
            # 保存规则书
            integration = RulebookParserIntegration(self.rulebook_manager)
            rulebook_id = await integration.save_parsed_rulebook(
                task.converted_schema, user_id
            )
            
            app_logger.info(f"规则书保存成功: 任务ID={task_id}, 规则书ID={rulebook_id}")
            
            # 可选：清理任务数据
            # del self.active_tasks[task_id]
            
            return rulebook_id
            
        except Exception as e:
            app_logger.error(f"保存规则书失败: {task_id}, 错误: {e}", exc_info=True)
            raise StoryMasterValidationError(f"保存规则书失败: {str(e)}")
    
    async def list_active_tasks(self) -> List[ParsingTaskStatus]:
        """列出所有活跃任务"""
        return [task.to_status_model() for task in self.active_tasks.values()]
    
    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """
        清理旧任务
        
        Args:
            max_age_hours: 任务最大保留时间（小时）
            
        Returns:
            int: 清理的任务数量
        """
        now = datetime.now()
        max_age = timedelta(hours=max_age_hours)
        
        tasks_to_remove = []
        for task_id, task in self.active_tasks.items():
            age = now - task.created_at
            if age > max_age or task.status in ["completed", "failed"]:
                tasks_to_remove.append(task_id)
        
        for task_id in tasks_to_remove:
            del self.active_tasks[task_id]
        
        if tasks_to_remove:
            app_logger.info(f"清理了 {len(tasks_to_remove)} 个旧任务")
        
        return len(tasks_to_remove)