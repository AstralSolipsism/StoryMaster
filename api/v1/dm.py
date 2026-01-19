"""
DM模块API路由
提供DM智能体的RESTful API和WebSocket接口
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, WebSocketException, status, HTTPException
from fastapi.responses import JSONResponse

from ...models.dm_models import (
    DMConfig,
    DMStyle,
    NarrativeTone,
    CombatDetail,
    PlayerInput,
    DMResponse,
    CustomDMStyleRequest,
    get_predefined_dm_style
)
from ...services.dm import (
    DMAgent,
    create_dm_agent
)
from ...core.logging import app_logger


router = APIRouter(prefix="/dm", tags=["dungeon-master"])

# 全局DM智能体实例
_dm_agents: Dict[str, DMAgent] = {}

# 全局DM智能体管理器实例
_dm_manager: Optional[Any] = None


# ==================== 依赖注入 ====================

async def get_dm_agent(
    dm_id: str = "default"
) -> DMAgent:
    """
    获取DM智能体实例（延迟初始化）
    
    Args:
        dm_id: DM ID
        
    Returns:
        DMAgent: DM智能体实例
    """
    global _dm_agents, _dm_manager
    
    if dm_id not in _dm_agents:
        # 延迟初始化
        from ...model_adapter import ModelScheduler
        from ...data_storage.repositories.entity_repository import EntityRepository
        from ...data_storage.managers.cache_manager import CacheManager
        from ...data_storage.adapters.neo4j_adapter import Neo4jAdapter
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
        
        # TODO: 创建IGameRecordRepository
        class MockGameRecordRepository:
            async def save_record(self, record):
                pass
            async def get_records(self, session_id, start_date, end_date, limit):
                return []
        
        game_record_repository = MockGameRecordRepository()
        
        # 创建模型调度器
        from ...model_adapter import create_model_scheduler
        model_scheduler = create_model_scheduler()
        
        # 创建DM配置
        from ...models.dm_models import create_dm_config
        config = create_dm_config(
            agent_id=dm_id,
            dm_style=DMStyle.BALANCED,
            narrative_tone=NarrativeTone.DESCRIPTIVE,
            combat_detail=CombatDetail.NORMAL
        )
        
        # 创建DM智能体
        dm_agent = await create_dm_agent(
            agent_id=dm_id,
            config=config,
            model_scheduler=model_scheduler,
            entity_repository=entity_repository,
            game_record_repository=game_record_repository
        )
        
        _dm_agents[dm_id] = dm_agent
        app_logger.info(f"DM智能体初始化完成: {dm_id}")
    
    return _dm_agents[dm_id]


# ==================== 会话管理 ====================

@router.post("/sessions")
async def create_session(
    dm_id: str = "default",
    name: str = ...,
    description: str = ...,
    campaign_id: Optional[str] = None,
    initial_scene_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    创建游戏会话
    
    - **dm_id**: DM ID
    - **name**: 会话名称
    - **description**: 会话描述
    - **campaign_id**: 战役ID（可选）
    - **initial_scene_id**: 初始场景ID（可选）
    
    **响应体示例**：
    ```json
    {
      "session_id": "session_123",
      "name": "地下城探索",
      "dm_id": "default",
      "created_at": "2024-01-01T12:00:00Z"
    }
    ```
    """
    try:
        # 获取DM智能体
        dm_agent = await get_dm_agent(dm_id)
        
        # 生成会话ID
        import uuid
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        
        # 初始化会话
        from ...models.dm_models import create_game_session
        session = await dm_agent.initialize_session(
            session_id=session_id,
            dm_id=dm_id,
            name=name,
            description=description,
            campaign_id=campaign_id
        )
        
        return {
            "session_id": session_id,
            "name": session.name,
            "description": session.description,
            "dm_id": dm_id,
            "created_at": session.created_at.isoformat(),
            "dm_style": session.dm_style.value,
            "narrative_tone": session.narrative_tone.value,
            "combat_detail": session.combat_detail.value
        }
        
    except Exception as e:
        app_logger.error(f"创建会话失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"创建会话失败: {str(e)}"
        )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    获取会话详情
    
    - **session_id**: 会话ID
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "session_id": "session_123",
      "name": "地下城探索",
      "description": "探索古老地下城的冒险",
      "current_time": "2024-01-01T12:30:00Z",
      "player_characters": [],
      "active_npcs": []
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # 获取会话状态
        status = await dm_agent.get_session_status(session_id)
        
        return status
        
    except Exception as e:
        app_logger.error(f"获取会话失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=404,
            detail=f"会话不存在: {str(e)}"
        )


@router.post("/sessions/{session_id}/process")
async def process_player_turn(
    session_id: str,
    request: Dict[str, Any],
    dm_id: str = "default"
) -> DMResponse:
    """
    处理玩家回合
    
    - **session_id**: 会话ID
    - **dm_id**: DM ID
    - **request**: 处理请求
      - task_id: 任务ID
      - inputs: 玩家输入列表
      - advance_time: 是否推进时间（默认true）
    
    **请求体示例**：
    ```json
    {
      "task_id": "turn_123",
      "inputs": [
        {
          "character_id": "char_1",
          "character_name": "Player1",
          "content": "我对商人说：请问这把剑多少钱？",
          "timestamp": "2024-01-01T12:00:00Z"
        }
      ],
      "advance_time": true
    }
    ```
    
    **响应体示例**：
    ```json
    {
      "content": "商人看了看你的剑，说：\"这把剑品质不错，只要50金币。\"",
      "timestamp": "2024-01-01T12:00:05Z",
      "style": "balanced",
      "tone": "descriptive",
      "metadata": {}
    }
    ```
    """
    try:
        # 验证请求
        if "inputs" not in request or not request["inputs"]:
            raise HTTPException(
                status_code=400,
                detail="缺少输入数据"
            )
        
        # 获取DM智能体
        dm_agent = await get_dm_agent(dm_id)
        
        # 构建玩家输入
        player_inputs = []
        for input_data in request["inputs"]:
            player_input = PlayerInput(
                character_id=input_data.get("character_id"),
                character_name=input_data.get("character_name"),
                content=input_data.get("content"),
                timestamp=datetime.now()
            )
            player_inputs.append(player_input)
        
        # 构建执行上下文
        from ...agent_orchestration.interfaces import ExecutionContext
        context = ExecutionContext(
            task_id=request.get("task_id"),
            session_id=session_id
        )
        
        # 处理玩家回合
        response = await dm_agent.process_player_turn(
            session_id=session_id,
            player_inputs=player_inputs,
            context=context
        )
        
        return response
        
    except Exception as e:
        app_logger.error(f"处理玩家回合失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"处理失败: {str(e)}"
        )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    删除会话
    
    - **session_id**: 会话ID
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "success": true,
      "message": "会话 session_123 已删除"
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # 清理会话
        await dm_agent.cleanup_session(session_id)
        
        return {
            "success": True,
            "message": f"会话 {session_id} 已删除"
        }
        
    except Exception as e:
        app_logger.error(f"删除会话失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"删除会话失败: {str(e)}"
        )


# ==================== NPC管理 ====================

@router.post("/sessions/{session_id}/npcs")
async def add_npc_to_session(
    session_id: str,
    npc_id: str,
    initial_state: Optional[Dict[str, Any]] = None,
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    添加NPC到会话
    
    - **session_id**: 会话ID
    - **npc_id**: NPC ID
    - **initial_state**: 初始状态（可选）
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "success": true,
      "message": "NPC已添加到会话",
      "npc_id": "npc_123"
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # 激活NPC到会话
        await dm_agent.npc_pool.activate_npc(npc_id, session_id)
        
        # TODO: 应用初始状态
        
        return {
            "success": True,
            "message": "NPC已添加到会话",
            "npc_id": npc_id
        }
        
    except Exception as e:
        app_logger.error(f"添加NPC到会话失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"添加NPC失败: {str(e)}"
        )


@router.delete("/sessions/{session_id}/npcs/{npc_id}")
async def remove_npc_from_session(
    session_id: str,
    npc_id: str,
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    从会话移除NPC
    
    - **session_id**: 会话ID
    - **npc_id**: NPC ID
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "success": true,
      "message": "NPC已从会话移除",
      "npc_id": "npc_123"
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # 从会话停用NPC
        await dm_agent.npc_pool.deactivate_npc(npc_id, session_id)
        
        return {
            "success": True,
            "message": "NPC已从会话移除",
            "npc_id": npc_id
        }
        
    except Exception as e:
        app_logger.error(f"从会话移除NPC失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"移除NPC失败: {str(e)}"
        )


# ==================== DM风格管理 ====================

@router.get("/sessions/{session_id}/style")
async def get_dm_style(
    session_id: str,
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    获取DM风格设置
    
    - **session_id**: 会话ID
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "dm_style": "balanced",
      "narrative_tone": "descriptive",
      "combat_detail": "normal",
      "custom_dm_style": "黑暗史诗",
      "custom_system_prompt": "你是..."
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # 获取会话配置
        # 需要实现get_session方法返回完整会话对象
        status = await dm_agent.get_session_status(session_id)
        
        # 获取自定义DM风格
        custom_styles = await dm_agent.get_custom_dm_styles() if hasattr(dm_agent, 'get_custom_dm_styles') else {}
        
        result = {
            "dm_style": "balanced",
            "narrative_tone": "descriptive",
            "combat_detail": "normal"
        }
        
        if "dm_style" in status:
            result["dm_style"] = status["dm_style"]
        if "narrative_tone" in status:
            result["narrative_tone"] = status["narrative_tone"]
        if "combat_detail" in status:
            result["combat_detail"] = status["combat_detail"]
        if "custom_dm_style" in status:
            result["custom_dm_style"] = status["custom_dm_style"]
        if "custom_system_prompt" in status:
            result["custom_system_prompt"] = status["custom_system_prompt"]
        
        if custom_styles:
            result["custom_styles"] = custom_styles
        
        return result
        
    except Exception as e:
        app_logger.error(f"获取DM风格失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取风格失败: {str(e)}"
        )


@router.put("/sessions/{session_id}/style")
async def update_dm_style(
    session_id: str,
    request: Dict[str, str],
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    更新DM风格设置
    
    - **session_id**: 会话ID
    - **dm_id**: DM ID
    - **request**: 风格设置
      - dm_style: DM风格（可选）
      - narrative_tone: 叙述基调（可选）
      - combat_detail: 战斗细节程度（可选）
    
    **请求体示例**：
    ```json
    {
      "dm_style": "horror",
      "narrative_tone": "detailed",
      "combat_detail": "detailed"
    }
    ```
    
    **响应体示例**：
    ```json
    {
      "success": true,
      "message": "DM风格已更新",
      "style": {
        "dm_style": "horror",
        "narrative_tone": "detailed",
        "combat_detail": "detailed"
      }
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # 验证风格值
        dm_style = request.get("dm_style")
        narrative_tone = request.get("narrative_tone")
        combat_detail = request.get("combat_detail")
        
        if dm_style:
            try:
                DMStyle(dm_style)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"无效的DM风格值: {str(e)}"
                )
        
        if narrative_tone:
            try:
                NarrativeTone(narrative_tone)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"无效的叙述基调值: {str(e)}"
                )
        
        if combat_detail:
            try:
                CombatDetail(combat_detail)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"无效的战斗细节值: {str(e)}"
                )
        
        # 更新DM风格
        await dm_agent.update_dm_style(
            dm_style=dm_style,
            narrative_tone=narrative_tone,
            combat_detail=combat_detail
        )
        
        result = {
            "dm_style": dm_style or "balanced",
            "narrative_tone": narrative_tone or "descriptive",
            "combat_detail": combat_detail or "normal"
        }
        
        return {
            "success": True,
            "message": "DM风格已更新",
            "style": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"更新DM风格失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"更新风格失败: {str(e)}"
        )


# ==================== 自定义DM风格管理 ====================

@router.get("/dm/styles/predefined")
async def get_predefined_dm_styles(
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    获取预定义的DM风格
    
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "predefined_styles": {
        "黑暗史诗": {
          "style_name": "黑暗史诗",
          "style_description": "采用史诗般的叙事风格...",
          "narrative_tone": "descriptive",
          "combat_detail": "detailed",
          "temperature": 0.6
        },
        "轻松幽默": {
          "style_name": "轻松幽默",
          "style_description": "采用轻松幽默的叙事风格...",
          "narrative_tone": "concise",
          "combat_detail": "minimal",
          "temperature": 0.9
        },
        "悬疑推理": {
          "style_name": "悬疑推理",
          "style_description": "采用悬疑推理的叙事风格...",
          "narrative_tone": "concise",
          "combat_detail": "normal",
          "temperature": 0.5
        },
        "沉浸式恐怖": {
          "style_name": "沉浸式恐怖",
          "style_description": "采用沉浸式恐怖的叙事风格...",
          "narrative_tone": "detailed",
          "combat_detail": "detailed",
          "temperature": 0.6
        }
      }
    }
    ```
    """
    predefined_styles = {
        "黑暗史诗": {
            "style_name": "黑暗史诗",
            "style_description": "采用史诗般的叙事风格，营造宏大、庄严的氛围。语言庄严，充满戏剧张力。",
            "system_prompt": "你是一个采用史诗叙事风格的DM。你的语言应该庄严、宏大，充满戏剧性和史诗感。在描述场景和事件时，要强调历史感、英雄气概和命运的庄严感。",
            "narrative_tone": "descriptive",
            "combat_detail": "detailed",
            "temperature": 0.6
        },
        "轻松幽默": {
            "style_name": "轻松幽默",
            "style_description": "采用轻松幽默的叙事风格，营造愉快、有趣的氛围。语言轻松，充满幽默和机智。",
            "system_prompt": "你是一个采用轻松幽默风格的DM。你的语言应该轻松、愉快，充满幽默和机智。在描述场景和事件时，要加入一些幽默元素，让玩家感到轻松愉快。适度使用网络流行语和梗，但不要过度。",
            "narrative_tone": "concise",
            "combat_detail": "minimal",
            "temperature": 0.9
        },
        "悬疑推理": {
            "style_name": "悬疑推理",
            "style_description": "采用悬疑推理的叙事风格，营造神秘、紧张的氛围。语言简洁，充满线索和谜题。",
            "system_prompt": "你是一个采用悬疑推理风格的DM。你的语言应该简洁、充满线索和谜题，营造神秘和紧张的氛围。在描述场景和事件时，要提供详细的线索，引导玩家进行推理和解谜。不要直接揭示答案，让玩家自己发现真相。",
            "narrative_tone": "concise",
            "combat_detail": "normal",
            "temperature": 0.5
        },
        "沉浸式恐怖": {
            "style_name": "沉浸式恐怖",
            "style_description": "采用沉浸式恐怖的叙事风格，营造真实、恐怖的氛围。语言细腻，充满感官描述。",
            "system_prompt": "你是一个采用沉浸式恐怖风格的DM。你的语言应该细腻、充满感官描述（视觉、听觉、嗅觉、触觉），营造真实、恐怖的氛围。在描述场景和事件时，要强调恐怖元素，让玩家感到真正的恐惧。使用克苏鲁式恐怖小说的描述风格，注重细节和氛围。",
            "narrative_tone": "detailed",
            "combat_detail": "detailed",
            "temperature": 0.6
        }
    }
    
    return {
        "predefined_styles": predefined_styles
    }


@router.post("/sessions/{session_id}/styles/custom")
async def register_custom_dm_style(
    session_id: str,
    request: Dict[str, Any],
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    注册自定义DM风格
    
    - **session_id**: 会话ID
    - **dm_id**: DM ID
    - **request**: 自定义风格请求
      - style_name: 风格名称
      - style_description: 风格描述
      - system_prompt: 自定义系统提示词（可选）
      - narrative_tone: 叙述基调（可选）
      - combat_detail: 战斗细节（可选）
      - temperature: 温度参数（可选）
      - examples: 示例描述列表（可选）
    
    **请求体示例**：
    ```json
    {
      "style_name": "赛博朋克",
      "style_description": "采用赛博朋克风格的叙事风格，强调高科技、低生活、霓虹灯、反乌托邦。",
      "system_prompt": "你是一个采用赛博朋克风格的DM。你的语言应该充满科技感、霓虹灯意象、反乌托邦色彩。在描述场景时，要强调高科技、人工智能、企业统治、社会分化和虚拟现实。",
      "narrative_tone": "descriptive",
      "combat_detail": "detailed",
      "temperature": 0.7,
      "examples": [
        "霓虹灯闪烁，照亮了这个混乱的城市。",
        "公司的广告全息投影在空中浮动，显示着'生活在虚拟现实'的承诺。",
        "你的神经植入体提示你：'距离目标还有50米'。"
      ]
    }
    ```
    
    **响应体示例**：
    ```json
    {
      "success": true,
      "message": "自定义DM风格已注册",
      "style": {
        "style_name": "赛博朋克",
        "style_description": "采用赛博朋克风格的叙事风格...（用户输入）"
      }
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # 验证请求
        if "style_name" not in request:
            raise HTTPException(
                status_code=400,
                detail="缺少风格名称"
            )
        
        style_name = request["style_name"]
        style_description = request.get("style_description", "")
        
        # 构建自定义风格请求
        from ...models.dm_models import CustomDMStyleRequest, create_custom_dm_style_request, NarrativeTone, CombatDetail
        
        narrative_tone_value = request.get("narrative_tone", "descriptive")
        try:
            narrative_tone = NarrativeTone(narrative_tone_value)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"无效的叙述基调: {narrative_tone_value}"
            )
        
        combat_detail_value = request.get("combat_detail", "normal")
        try:
            combat_detail = CombatDetail(combat_detail_value)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"无效的战斗细节: {combat_detail_value}"
            )
        
        temperature = request.get("temperature", 0.7)
        if not isinstance(temperature, (int, float)) or not 0.0 <= temperature <= 1.0:
            raise HTTPException(
                status_code=400,
                detail="温度参数必须在0.0-1.0之间"
            )
        
        examples = request.get("examples", [])
        
        custom_style_request = CustomDMStyleRequest(
            style_name=style_name,
            style_description=style_description,
            system_prompt=request.get("system_prompt"),
            narrative_tone=narrative_tone,
            combat_detail=combat_detail,
            temperature=temperature,
            examples=examples
        )
        
        # 注册自定义风格
        if hasattr(dm_agent, 'register_custom_dm_style'):
            await dm_agent.register_custom_dm_style(style_name, custom_style_request)
        
        return {
            "success": True,
            "message": f"自定义DM风格 '{style_name}' 已注册",
            "style": custom_style_request.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"注册自定义DM风格失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"注册风格失败: {str(e)}"
        )


@router.delete("/sessions/{session_id}/styles/custom/{style_name}")
async def delete_custom_dm_style(
    session_id: str,
    style_name: str,
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    删除自定义DM风格
    
    - **session_id**: 会话ID
    - **dm_id**: DM ID
    - **style_name**: 风格名称
    
    **响应体示例**：
    ```json
    {
      "success": true,
      "message": "自定义DM风格 '赛博朋克' 已删除"
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # 删除自定义风格
        if hasattr(dm_agent, 'remove_custom_dm_style'):
            success = await dm_agent.remove_custom_dm_style(style_name)
        else:
            success = False
        
        if success:
            return {
                "success": True,
                "message": f"自定义DM风格 '{style_name}' 已删除"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"未找到自定义DM风格: {style_name}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"删除自定义DM风格失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"删除风格失败: {str(e)}"
        )


@router.get("/sessions/{session_id}/styles/custom")
async def get_custom_dm_styles(
    session_id: str,
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    获取所有自定义DM风格
    
    - **session_id**: 会话ID
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "custom_styles": {
        "赛博朋克": {
          "style_name": "赛博朋克",
          "style_description": "采用赛博朋克风格的叙事风格...",
          "system_prompt": "你是一个采用赛博朋克风格的DM...（用户输入）",
          "narrative_tone": "descriptive",
          "combat_detail": "detailed",
          "temperature": 0.7,
          "examples": ["霓虹灯闪烁..."]
        }
      }
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # 获取自定义风格
        custom_styles = {}
        if hasattr(dm_agent, 'get_custom_dm_styles'):
            custom_styles_dict = await dm_agent.get_custom_dm_styles()
            custom_styles = {k: v.to_dict() for k, v in custom_styles_dict.items()}
        
        return {
            "custom_styles": custom_styles
        }
        
    except Exception as e:
        app_logger.error(f"获取自定义DM风格失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取风格失败: {str(e)}"
        )


# ==================== 查询接口 ====================

@router.get("/sessions/{session_id}/entities")
async def get_session_entities(
    session_id: str,
    entity_type: Optional[str] = None,
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    获取会话中的实体
    
    - **session_id**: 会话ID
    - **entity_type**: 实体类型（可选）
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "entities": [
        {
          "entity_id": "npc_123",
          "entity_type": "NPCInstance",
          "name": "商人"
        }
      ],
      "total": 1
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # TODO: 实现实体查询
        # 这里需要从会话中获取实体列表
        
        return {
            "entities": [],
            "total": 0
        }
        
    except Exception as e:
        app_logger.error(f"获取会话实体失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取实体失败: {str(e)}"
        )


@router.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    dm_id: str = "default"
) -> Dict[str, Any]:
    """
    获取会话历史
    
    - **session_id**: 会话ID
    - **limit**: 返回数量（默认100）
    - **offset**: 偏移量（默认0）
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "records": [],
      "total": 0,
      "pagination": {
        "limit": 100,
        "offset": 0
      }
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        # TODO: 实现历史记录查询
        # 这里需要从数据库获取历史记录
        
        return {
            "records": [],
            "total": 0,
            "pagination": {
                "limit": limit,
                "offset": offset
            }
        }
        
    except Exception as e:
        app_logger.error(f"获取会话历史失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取历史失败: {str(e)}"
        )


# ==================== 健康检查 ====================

@router.get("/health")
async def dm_health_check(dm_id: str = "default") -> Dict[str, Any]:
    """
    DM模块健康检查
    
    - **dm_id**: DM ID
    
    **响应体示例**：
    ```json
    {
      "status": "healthy",
      "dm_agent": {
        "status": "idle",
        "agent_id": "default"
      },
      "npc_pool": {
        "total_agents": 0,
        "active_sessions": 0
      },
      "timestamp": "2024-01-01T12:00:00Z"
    }
    ```
    """
    try:
        dm_agent = await get_dm_agent(dm_id)
        
        return {
            "status": "healthy",
            "dm_agent": {
                "status": str(dm_agent.status.value),
                "agent_id": dm_agent.agent_id
            },
            "npc_pool": dm_agent.npc_pool.get_pool_status(),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }