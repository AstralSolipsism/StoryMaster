"""
响应生成器
生成最终的DM响应，支持自定义DM风格
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from ...models.dm_models import (
    DMResponse,
    DMStyle,
    NarrativeTone,
    CombatDetail,
    PerceptibleInfo,
    NPCResponse,
    CustomDMStyleRequest
)
from ...provider import ProviderManager, ProviderRequest, ChatMessage
from ...core.logging import app_logger


class DMStylesConfig:
    """DM风格配置"""
    
    # 系统提示模板
    STYLE_PROMPTS = {
        DMStyle.BALANCED: """你是一个平衡的DM，兼顾剧情推进和玩家体验。你会根据玩家的行动给出合理的响应，既不会过于严格也不会过于宽松。保持游戏的流畅性和趣味性。""",
        
        DMStyle.SERIOUS: """你是一个严肃的DM，注重规则严谨和逻辑一致。你会严格遵循D&D规则，确保所有检定、法术、战斗都符合规则书的规定。剧情推进要合理且有逻辑性。""",
        
        DMStyle.HUMOROUS: """你是一个幽默的DM，喜欢在叙述中加入幽默元素。你会用轻松愉快的语气描述场景，适时加入一些幽默的评论和描述，但不会破坏游戏的沉浸感。""",
        
        DMStyle.HORROR: """你是一个营造恐怖氛围的DM，擅长制造紧张和惊悚感。你会使用压抑、黑暗的语言风格，强调环境的诡异和危险，让玩家感受到真正的恐惧。""",
        
        DMStyle.DRAMATIC: """你是一个戏剧性的DM，喜欢使用戏剧化的描述和表达。你会使用夸张、富有感染力的语言，让每个场景都充满戏剧张力，增强游戏的史诗感。"""
    }
    
    # 叙述基调指令
    TONE_INSTRUCTIONS = {
        NarrativeTone.DESCRIPTIVE: """使用详细描述，让玩家能够生动地想象场景。描述要包括视觉、听觉、嗅觉、触觉等多个感官维度，营造沉浸式的游戏体验。""",
        
        NarrativeTone.CONCISE: """使用简洁描述，快速推进剧情。描述要简明扼要，直接传达关键信息，避免冗长的描述，保持游戏的节奏感。""",
        
        NarrativeTone.DETAILED: """使用极度详细的描述，注重每个细节。描述要包括所有可见和可感知的细节，从细微的环境变化到角色的表情动作，给玩家最完整的场景信息。"""
    }
    
    # 战斗细节指令
    COMBAT_INSTRUCTIONS = {
        CombatDetail.MINIMAL: """战斗描述要最小化，只报告结果和关键信息。避免详细的动作描述，快速完成战斗，让玩家知道结果即可。""",
        
        CombatDetail.NORMAL: """战斗描述要适中，平衡动作细节和战斗节奏。描述主要攻击和受伤情况，保持战斗的紧张感和流畅性。""",
        
        CombatDetail.DETAILED: """战斗描述要极其详细，描述每个动作、招式、伤害效果。包括武器的轨迹、法术的效果、角色的反应等，让战斗充满视觉冲击力。"""
    }
    
    # 温度设置
    STYLE_TEMPERATURES = {
        DMStyle.BALANCED: 0.7,
        DMStyle.SERIOUS: 0.5,
        DMStyle.HUMOROUS: 0.8,
        DMStyle.HORROR: 0.6,
        DMStyle.DRAMATIC: 0.75
    }


class ResponseGenerator:
    """响应生成器"""
    
    def __init__(
        self,
        model_scheduler: ProviderManager,
        dm_style: DMStyle = DMStyle.BALANCED,
        narrative_tone: NarrativeTone = NarrativeTone.DESCRIPTIVE,
        combat_detail: CombatDetail = CombatDetail.NORMAL,
        custom_style_request: Optional[CustomDMStyleRequest] = None
    ):
        """
        初始化响应生成器
        
        Args:
            model_scheduler: 模型调度器
            dm_style: DM风格
            narrative_tone: 叙述基调
            combat_detail: 战斗细节程度
            custom_style_request: 自定义风格请求（可选）
        """
        self.model_scheduler = model_scheduler
        self.dm_style = dm_style
        self.narrative_tone = narrative_tone
        self.combat_detail = combat_detail
        self.custom_style_request = custom_style_request
        self.logger = app_logger
    
    def update_style(
        self,
        dm_style: Optional[DMStyle] = None,
        narrative_tone: Optional[NarrativeTone] = None,
        combat_detail: Optional[CombatDetail] = None,
        custom_style_request: Optional[CustomDMStyleRequest] = None
    ) -> None:
        """
        更新DM风格配置
        
        Args:
            dm_style: DM风格（可选）
            narrative_tone: 叙述基调（可选）
            combat_detail: 战斗细节程度（可选）
            custom_style_request: 自定义风格请求（可选）
        """
        if dm_style:
            self.dm_style = dm_style
        if narrative_tone:
            self.narrative_tone = narrative_tone
        if combat_detail:
            self.combat_detail = combat_detail
        if custom_style_request:
            self.custom_style_request = custom_style_request
        
        self.logger.info(
            f"更新DM风格: {self.dm_style.value}, "
            f"{self.narrative_tone.value}, "
            f"{self.combat_detail.value}, "
            f"custom={self.custom_style_request is not None}"
        )
    
    def get_effective_system_prompt(self) -> str:
        """
        获取有效的系统提示词
        
        Returns:
            str: 系统提示词
        """
        # 优先使用自定义风格
        if self.custom_style_request and self.custom_style_request.system_prompt:
            return self.custom_style_request.system_prompt
        
        # 否则使用预定义风格
        style_prompt = DMStylesConfig.STYLE_PROMPTS.get(self.dm_style, "")
        return style_prompt
    
    def get_effective_temperature(self) -> float:
        """
        获取有效的温度参数
        
        Returns:
            float: 温度参数
        """
        # 优先使用自定义风格
        if self.custom_style_request and self.custom_style_request.temperature is not None:
            return self.custom_style_request.temperature
        
        # 否则使用预定义风格
        return DMStylesConfig.STYLE_TEMPERATURES.get(self.dm_style, 0.7)
    
    async def generate(
        self,
        perceptible_info: PerceptibleInfo,
        context: Optional[Dict[str, Any]] = None
    ) -> DMResponse:
        """
        生成DM响应
        
        Args:
            perceptible_info: 可感知信息
            context: 执行上下文（可选）
            
        Returns:
            DMResponse: DM响应
        """
        try:
            # 构建提示词
            prompt = self._build_response_prompt(perceptible_info)
            
            # 获取温度参数
            temperature = self.get_effective_temperature()
            
            # 调用LLM生成响应
            request_context = ProviderRequest(
                messages=[
                    ChatMessage(
                        role='system',
                        content=self._get_system_prompt()
                    ),
                    ChatMessage(
                        role='user',
                        content=prompt
                    )
                ],
                max_tokens=2000,
                temperature=temperature
            )
            
            response = await self.model_scheduler.chat(request_context)
            
            # 解析响应
            dm_response = DMResponse(
                content=response.choices[0].message.content,
                timestamp=datetime.now(),
                style=self.dm_style,
                tone=self.narrative_tone,
                metadata=context or {}
            )
            
            self.logger.info(
                f"生成DM响应: {len(dm_response.content)}字符, "
                f"风格: {self.dm_style.value}"
            )
            
            return dm_response
            
        except Exception as e:
            self.logger.error(f"DM响应生成失败: {e}", exc_info=True)
            # 返回错误响应
            return await self.generate_error_response(str(e))
    
    def _get_system_prompt(self) -> str:
        """
        获取系统提示
        
        Returns:
            str: 系统提示
        """
        effective_prompt = self.get_effective_system_prompt()
        
        # 添加叙述基调指令
        tone_instruction = DMStylesConfig.TONE_INSTRUCTIONS.get(
            self.narrative_tone, ""
        )
        
        # 添加战斗细节指令
        combat_instruction = DMStylesConfig.COMBAT_INSTRUCTIONS.get(
            self.combat_detail, ""
        )
        
        # 构建完整的系统提示
        system_prompt = f"""{effective_prompt}

{tone_instruction}

{combat_instruction}

作为DM，你需要：
1. 根据玩家行动，描述场景的变化
2. 整合NPC的回应
3. 说明行动的结果和影响
4. 提示下一步的可能行动
5. 保持叙事的连贯性和沉浸感

重要规则：
- 响应要符合D&D游戏逻辑
- 保持角色和场景的一致性
- 适时给出玩家选择的提示
- 如果涉及战斗，描述战斗过程和结果
- 保持你的DM风格和叙述基调
"""
        
        return system_prompt
    
    def _build_response_prompt(
        self,
        perceptible_info: PerceptibleInfo
    ) -> str:
        """
        构建响应提示
        
        Args:
            perceptible_info: 可感知信息
            
        Returns:
            str: 提示词
        """
        prompt_parts = []
        
        # 添加玩家行动
        if perceptible_info.player_actions:
            prompt_parts.append("玩家行动:")
            for i, action in enumerate(perceptible_info.player_actions):
                prompt_parts.append(f"{i+1}. {action}")
        
        # 添加NPC回应
        if perceptible_info.npc_responses:
            prompt_parts.append("\nNPC回应:")
            for npc_id, response in perceptible_info.npc_responses.items():
                prompt_parts.append(
                    f"- {npc_id}: {response.response}"
                )
                if response.action:
                    prompt_parts.append(f"  行动: {response.action}")
        
        # 添加事件
        if perceptible_info.events:
            prompt_parts.append("\n发生的事件:")
            for event in perceptible_info.events:
                prompt_parts.append(f"- {event.description}")
                if event.effects:
                    prompt_parts.append(f"  效果: {event.effects}")
        
        # 添加场景状态
        if perceptible_info.scene_description:
            prompt_parts.append(
                f"\n当前场景:\n{perceptible_info.scene_description}"
            )
        
        # 添加指令
        prompt_parts.append("\n请生成DM叙述，回应玩家的行动。")
        
        return "\n".join(prompt_parts)
    
    async def generate_simple_response(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> DMResponse:
        """
        生成简单的DM响应（不使用LLM）
        
        Args:
            message: 消息内容
            context: 执行上下文（可选）
            
        Returns:
            DMResponse: DM响应
        """
        return DMResponse(
            content=message,
            timestamp=datetime.now(),
            style=self.dm_style,
            tone=self.narrative_tone,
            metadata=context or {}
        )
    
    async def generate_error_response(
        self,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> DMResponse:
        """
        生成错误响应
        
        Args:
            error_message: 错误消息
            context: 执行上下文（可选）
            
        Returns:
            DMResponse: DM响应
        """
        return DMResponse(
            content=f"⚠️ {error_message}",
            timestamp=datetime.now(),
            style=self.dm_style,
            tone=self.narrative_tone,
            metadata={'error': error_message, **(context or {})}
        )
    
    async def generate_system_notification(
        self,
        notification: str,
        context: Optional[Dict[str, Any]] = None
    ) -> DMResponse:
        """
        生成系统通知响应
        
        Args:
            notification: 通知内容
            context: 执行上下文（可选）
            
        Returns:
            DMResponse: DM响应
        """
        return DMResponse(
            content=f"📢 {notification}",
            timestamp=datetime.now(),
            style=self.dm_style,
            tone=self.narrative_tone,
            metadata={'notification': notification, **(context or {})}
        )


# ==================== 工厂函数 ====================

def create_response_generator(
    model_scheduler: ProviderManager,
    dm_style: DMStyle = DMStyle.BALANCED,
    narrative_tone: NarrativeTone = NarrativeTone.DESCRIPTIVE,
    combat_detail: CombatDetail = CombatDetail.NORMAL
) -> ResponseGenerator:
    """
    创建响应生成器实例
    
    Args:
        model_scheduler: 模型调度器
        dm_style: DM风格
        narrative_tone: 叙述基调
        combat_detail: 战斗细节程度
        
    Returns:
        ResponseGenerator: 响应生成器实例
    """
    return ResponseGenerator(
        model_scheduler=model_scheduler,
        dm_style=dm_style,
        narrative_tone=narrative_tone,
        combat_detail=combat_detail
    )


def create_custom_response_generator(
    model_scheduler: ProviderManager,
    custom_style_request: CustomDMStyleRequest
) -> ResponseGenerator:
    """
    创建自定义风格响应生成器实例
    
    Args:
        model_scheduler: 模型调度器
        custom_style_request: 自定义风格请求
        
    Returns:
        ResponseGenerator: 响应生成器实例
    """
    return ResponseGenerator(
        model_scheduler=model_scheduler,
        dm_style=DMStyle.CUSTOM,
        narrative_tone=custom_style_request.narrative_tone,
        combat_detail=custom_style_request.combat_detail,
        custom_style_request=custom_style_request
    )