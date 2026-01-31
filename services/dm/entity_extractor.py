"""
实体抽取器
从玩家输入中抽取实体并与图数据库匹配
"""

import json
import logging
from typing import Dict, Any, List, Optional

from ...models.dm_models import (
    ClassifiedInput,
    ExtractedEntity,
    EntityExtraction,
    MatchedEntity,
    InputType
)
from ...data_storage.interfaces import Entity
from ...data_storage.interfaces import EntityFilter, IEntityRepository
from ...data_storage.managers.cache_manager import CacheManager
from ...data_storage.adapters.redis_adapter import RedisAdapter
from ...provider import ProviderManager, ProviderRequest, ChatMessage
from ...core.logging import app_logger


class EntityExtractor:
    """实体抽取器"""
    
    def __init__(
        self,
        model_scheduler: ProviderManager,
        entity_repository: IEntityRepository,
        cache_manager: Optional[CacheManager] = None,
        temperature: float = 0.3
    ):
        """
        初始化实体抽取器
        
        Args:
            model_scheduler: 模型调度器
            entity_repository: 实体仓库
            cache_manager: 缓存管理器（可选）
            temperature: 温度参数
        """
        self.model_scheduler = model_scheduler
        self.entity_repository = entity_repository
        self.cache_manager = cache_manager
        self.temperature = temperature
        self.logger = app_logger
        
        # 实体类型映射
        self.entity_type_mapping = {
            'SPELL': 'SpellTemplate',
            'SKILL': 'Skill',
            'ITEM': 'ItemTemplate',
            'NPC': 'NPCInstance',
            'PLAYER': 'Character',
            'LOCATION': 'Location',
            'MONSTER': 'MonsterTemplate'
        }
    
    async def extract(
        self,
        classified_input: ClassifiedInput
    ) -> ExtractedEntity:
        """
        抽取并匹配实体
        
        实体类型：
        - SPELL: 法术名称
        - SKILL: 技能名称
        - ITEM: 物品装备
        - NPC: NPC名称
        - PLAYER: 玩家角色名称
        - LOCATION: 地理位置
        - MONSTER: 怪物名称
        
        Args:
            classified_input: 分类后的输入
            
        Returns:
            ExtractedEntity: 抽取的实体集合
        """
        try:
            # 1. 使用LLM抽取实体
            extractions = await self._extract_with_llm(classified_input)
            
            # 2. 与图数据库匹配
            matched_entities = []
            for extraction in extractions:
                matched = await self._match_entity(extraction)
                matched_entities.append(matched)
            
            # 3. 记录新实体
            new_entities = [e for e in matched_entities if e.is_new]
            if new_entities:
                self.logger.info(
                    f"发现{len(new_entities)}个新实体: "
                    f"{[e.extraction.name for e in new_entities]}"
                )
            
            return ExtractedEntity(
                original_input=classified_input,
                entities=matched_entities
            )
            
        except Exception as e:
            self.logger.error(f"实体抽取失败: {e}", exc_info=True)
            # 返回空实体集合
            return ExtractedEntity(
                original_input=classified_input,
                entities=[]
            )
    
    async def _extract_with_llm(
        self,
        classified_input: ClassifiedInput
    ) -> List[EntityExtraction]:
        """
        使用LLM抽取实体
        
        Args:
            classified_input: 分类后的输入
            
        Returns:
            List[EntityExtraction]: 实体抽取结果列表
        """
        # 检查缓存
        cache_key = self._get_cache_key(classified_input)
        if self.cache_manager:
            cached = await self.cache_manager.get(cache_key)
            if cached:
                return [EntityExtraction(**e) for e in cached]
        
        # 构建抽取提示词
        prompt = self._build_extraction_prompt(classified_input)
        
        # 调用LLM
        request_context = ProviderRequest(
            messages=[
                ChatMessage(
                    role='system',
                    content='你是一个专业的D&D游戏实体抽取器。请准确从玩家输入中识别实体，并以JSON格式返回结果。'
                ),
                ChatMessage(
                    role='user',
                    content=prompt
                )
            ],
            max_tokens=800,
            temperature=self.temperature
        )
        
        response = await self.model_scheduler.chat(request_context)
        
        if not response.choices or not response.choices[0].message.content:
            raise ValueError("LLM响应为空")
        
        # 解析JSON响应
        try:
            result = json.loads(response.choices[0].message.content)
            extractions = []
            for item in result.get('entities', []):
                extractions.append(EntityExtraction(
                    entity_type=item.get('type'),
                    name=item.get('name'),
                    context=item.get('context', ''),
                    confidence=item.get('confidence', 0.8)
                ))
            
            # 缓存结果
            if self.cache_manager:
                cache_data = [e.to_dict() for e in extractions]
                await self.cache_manager.set(
                    cache_key,
                    cache_data,
                    ttl=1800  # 30分钟
                )
            
            self.logger.info(
                f"LLM抽取到{len(extractions)}个实体"
            )
            
            return extractions
            
        except json.JSONDecodeError as e:
            self.logger.warning(f"LLM返回的JSON格式错误: {e}")
            return []
    
    async def _match_entity(
        self,
        extraction: EntityExtraction
    ) -> MatchedEntity:
        """
        与图数据库匹配实体
        
        Args:
            extraction: 实体抽取结果
            
        Returns:
            MatchedEntity: 匹配后的实体
        """
        try:
            # 映射实体类型
            entity_type = self.entity_type_mapping.get(
                extraction.entity_type,
                extraction.entity_type
            )
            
            # 在数据库中搜索
            filters = EntityFilter(
                entity_types=[entity_type],
                name_pattern=f"*{extraction.name}*",
                limit=5
            )
            
            results = await self.entity_repository.search(filters)
            
            if results:
                # 使用LLM选择最佳匹配
                best_match = await self._select_best_match(extraction, results)
                return MatchedEntity(
                    extraction=extraction,
                    matched_entity=best_match,
                    confidence=best_match.get('match_confidence', 0.8),
                    is_new=False
                )
            else:
                # 未找到匹配，返回新实体标记
                self.logger.debug(
                    f"未找到匹配实体: {extraction.entity_type} - {extraction.name}"
                )
                return MatchedEntity(
                    extraction=extraction,
                    matched_entity=None,
                    confidence=0.0,
                    is_new=True
                )
                
        except Exception as e:
            self.logger.error(f"实体匹配失败: {e}", exc_info=True)
            return MatchedEntity(
                extraction=extraction,
                matched_entity=None,
                confidence=0.0,
                is_new=True
            )
    
    async def _select_best_match(
        self,
        extraction: EntityExtraction,
        candidates: List[Entity]
    ) -> Entity:
        """
        使用LLM选择最佳匹配
        
        Args:
            extraction: 实体抽取结果
            candidates: 候选实体列表
            
        Returns:
            Entity: 最佳匹配实体
        """
        # 如果只有一个候选，直接返回
        if len(candidates) == 1:
            return candidates[0]
        
        # 构建候选列表
        candidates_list = []
        for i, candidate in enumerate(candidates):
            candidates_list.append(
                f"{i+1}. {candidate.entity_type}: {candidate.properties.get('name', 'Unknown')} - "
                f"{candidate.properties.get('description', '')}"
            )
        
        prompt = f"""请从以下候选实体中选择最佳匹配：

抽取实体: {extraction.name}
实体类型: {extraction.entity_type}
上下文: {extraction.context}

候选实体:
{chr(10).join(candidates_list)}

请选择最匹配的实体（编号），并返回JSON格式：
{{
    "selected_index": 编号,
    "match_confidence": 0.0-1.0,
    "reason": 选择原因
}}
"""
        
        request_context = ProviderRequest(
            messages=[
                ChatMessage(
                    role='system',
                    content='你是实体匹配专家，请选择最符合上下文的实体。'
                ),
                ChatMessage(
                    role='user',
                    content=prompt
                )
            ],
            max_tokens=300,
            temperature=0.2
        )
        
        try:
            response = await self.model_scheduler.chat(request_context)
            result = json.loads(response.choices[0].message.content)
            
            selected_index = result.get('selected_index', 1) - 1
            confidence = result.get('match_confidence', 0.8)
            
            # 将置信度添加到实体属性中
            best_match = candidates[selected_index]
            best_match.properties['match_confidence'] = confidence
            
            return best_match
            
        except Exception as e:
            self.logger.warning(f"最佳匹配选择失败，使用第一个候选: {e}")
            return candidates[0]
    
    def _build_extraction_prompt(
        self,
        classified_input: ClassifiedInput
    ) -> str:
        """
        构建抽取提示词
        
        Args:
            classified_input: 分类后的输入
            
        Returns:
            str: 提示词
        """
        input_type = classified_input.input_type.value
        
        return f"""请从以下玩家输入中抽取实体：

玩家角色: {classified_input.original_input.character_name}
输入类型: {input_type}
输入内容: {classified_input.original_input.content}

实体类型：
- SPELL: 法术名称（如：火球术、治疗术、魔法飞弹）
- SKILL: 技能名称（如：鉴定、潜行、观察）
- ITEM: 物品装备（如：长剑、魔法护甲、药水）
- NPC: NPC名称（如：村长、商人、守卫）
- PLAYER: 玩家角色名称
- LOCATION: 地理位置（如：王城、森林、地下城）
- MONSTER: 怪物名称（如：哥布林、龙、骷髅）

请以JSON格式返回，包含以下字段：
- entities: 实体列表
  - type: 实体类型（SPELL/SKILL/ITEM/NPC/PLAYER/LOCATION/MONSTER）
  - name: 实体名称
  - context: 实体出现的短语或上下文
  - confidence: 置信度（0.0-1.0）

示例：
输入: "我对商人说：请问这把剑多少钱？"
输出: {{"entities": [{"type": "NPC", "name": "商人", "context": "对商人说", "confidence": 0.95}]}}

输入: "我施放火球术攻击哥布林"
输出: {{"entities": [{"type": "SPELL", "name": "火球术", "context": "施放火球术", "confidence": 0.9}, {"type": "MONSTER", "name": "哥布林", "context": "攻击哥布林", "confidence": 0.95}]}}

现在请抽取：
"""
    
    def _get_cache_key(self, classified_input: ClassifiedInput) -> str:
        """
        生成缓存键
        
        Args:
            classified_input: 分类后的输入
            
        Returns:
            str: 缓存键
        """
        import hashlib
        content = classified_input.original_input.content
        return f"entity_extraction:{hashlib.md5(content.encode()).hexdigest()}"
    
    async def create_new_entity(
        self,
        extraction: EntityExtraction,
        session_id: str
    ) -> Entity:
        """
        创建新实体
        
        Args:
            extraction: 实体抽取结果
            session_id: 会话ID
            
        Returns:
            Entity: 创建的实体
        """
        from datetime import datetime
        
        # 映射实体类型
        entity_type = self.entity_type_mapping.get(
            extraction.entity_type,
            extraction.entity_type
        )
        
        # 创建实体
        entity = Entity(
            id=self._generate_entity_id(entity_type, session_id),
            entity_type=entity_type,
            properties={
                'name': extraction.name,
                'description': f'自动创建于{datetime.now().isoformat()}',
                'source': 'player_input',
                'extraction_confidence': extraction.confidence
            },
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # 保存到数据库
        await self.entity_repository.create(entity.__dict__)
        
        self.logger.info(
            f"创建新实体: {entity.id} - {extraction.name}"
        )
        
        return entity
    
    def _generate_entity_id(
        self,
        entity_type: str,
        session_id: str
    ) -> str:
        """
        生成实体ID
        
        Args:
            entity_type: 实体类型
            session_id: 会话ID
            
        Returns:
            str: 实体ID
        """
        import uuid
        import re
        # 转换为小写并移除空格
        type_clean = re.sub(r'\s+', '_', entity_type.lower())
        return f"{type_clean}_{session_id}_{uuid.uuid4().hex[:8]}"


# ==================== 工厂函数 ====================

def create_entity_extractor(
    model_scheduler: ProviderManager,
    entity_repository: IEntityRepository,
    redis_adapter: Optional[RedisAdapter] = None,
    temperature: float = 0.3
) -> EntityExtractor:
    """
    创建实体抽取器实例
    
    Args:
        model_scheduler: 模型调度器
        entity_repository: 实体仓库
        redis_adapter: Redis适配器（可选）
        temperature: 温度参数
        
    Returns:
        EntityExtractor: 实体抽取器实例
    """
    cache_manager = None
    if redis_adapter:
        cache_manager = CacheManager(redis_adapter)
    
    return EntityExtractor(
        model_scheduler=model_scheduler,
        entity_repository=entity_repository,
        cache_manager=cache_manager,
        temperature=temperature
    )