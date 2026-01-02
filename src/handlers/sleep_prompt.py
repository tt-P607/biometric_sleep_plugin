"""
Biometric Sleep System - 提示词注入组件 v2

根据状态和唤醒度注入对应的提示词：
- DROWSY: 困倦提示词
- SLEEPING (唤醒度 < 阈值): 睡眠提示词
- SLEEPING (唤醒度 >= 阈值): 被吵醒提示词
"""

from src.plugin_system import BasePrompt
from src.plugin_system.base.component_types import InjectionRule, InjectionType
from src.common.logger import get_logger
from ..core.sleep_manager import SleepState, SleepStateManager

logger = get_logger("sleep_prompt")


class SleepStatusPrompt(BasePrompt):
    prompt_name = "sleep_status_prompt"
    prompt_description = "根据睡眠状态注入特定的语气提示词"
    
    # 注入到主提示词中 - 同时支持 KFC（私聊）和 AFC（群聊）
    # 参考 period_plugin 的实现，使用正确的提示词目标名称
    injection_rules = [
        # AFC 群聊场景 - s4u 模式（注：normal 模式已弃用）
        InjectionRule(
            target_prompt="s4u_style_prompt",
            injection_type=InjectionType.PREPEND,
            priority=200
        ),
        # KFC 私聊场景 - 主提示词
        InjectionRule(
            target_prompt="kfc_main",
            injection_type=InjectionType.PREPEND,
            priority=200
        ),
        # KFC 私聊场景 - 回复提示词
        InjectionRule(
            target_prompt="kfc_replyer",
            injection_type=InjectionType.PREPEND,
            priority=200
        ),
        # KFC 私聊场景 - 统一提示词（新版KFC使用）
        InjectionRule(
            target_prompt="kfc_unified_prompt",
            injection_type=InjectionType.PREPEND,
            priority=200
        ),
    ]

    manager: SleepStateManager = None  # type: ignore

    def __init__(self, params, plugin_config: dict, target_prompt_name: str | None = None):
        super().__init__(params, plugin_config, target_prompt_name)

    async def execute(self) -> str:
        if not self.get_config("prompt.enable_injection", True):
            logger.debug("[SleepPrompt] 提示词注入已禁用")
            return ""

        # 获取 session_id
        session_id = self._extract_session_id()
        
        # 获取当前状态
        state = self.manager.get_current_state(session_id)
        
        logger.debug(f"[SleepPrompt] execute 被调用: session_id={session_id}, state={state}")
        
        # 根据状态和唤醒度选择提示词
        prompt = self._select_prompt(state, session_id)
        
        if prompt:
            logger.info(f"[SleepPrompt] 注入提示词: {prompt[:50]}...")
            return f"\n[状态感应: {prompt}]\n"
        
        logger.debug("[SleepPrompt] 无需注入提示词（AWAKE状态）")
        return ""
    
    def _extract_session_id(self) -> str | None:
        """从 params 中提取 session_id"""
        session_id = None
        
        params = self.params
        if not params:
            params = getattr(self, "context", {})

        if not params:
            return None

        # 兼容字典和对象访问
        if isinstance(params, dict):
            user_id = params.get("user_id")
            chat_id = params.get("chat_id")
            is_group_chat = params.get("is_group_chat", False)
        else:
            user_id = getattr(params, "user_id", None)
            chat_id = getattr(params, "chat_id", None)
            is_group_chat = getattr(params, "is_group_chat", False)

        # 构建 session_id
        if is_group_chat:
            if chat_id:
                session_id = chat_id if chat_id.startswith("group_") else f"group_{chat_id}"
            elif user_id:
                session_id = f"group_unknown_{user_id}"
        else:
            if user_id:
                session_id = f"private_{user_id}"
            elif chat_id:
                session_id = chat_id if chat_id.startswith("private_") else f"private_{chat_id}"

        return session_id
    
    def _select_prompt(self, state: SleepState, session_id: str | None) -> str | None:
        """
        根据状态和唤醒度选择合适的提示词
        
        - AWAKE: 无提示词
        - DROWSY: 困倦提示词
        - SLEEPING + 唤醒度 < 阈值: 睡眠提示词
        - SLEEPING + 唤醒度 >= 阈值: 被吵醒提示词
        """
        if state == SleepState.AWAKE:
            return None
        
        if state == SleepState.DROWSY:
            prompt = self.get_config('prompt.drowsy_prompt')
            logger.debug(f"[SleepPrompt] 状态=DROWSY, 返回困倦提示词")
            return prompt
        
        if state == SleepState.SLEEPING:
            # 判断是否处于被吵醒状态
            if session_id and self.manager.is_woken(session_id):
                prompt = self.get_config('prompt.woken_prompt')
                logger.debug(f"[SleepPrompt] 状态=SLEEPING(被吵醒), 返回被吵醒提示词")
                return prompt
            else:
                prompt = self.get_config('prompt.sleeping_prompt')
                logger.debug(f"[SleepPrompt] 状态=SLEEPING, 返回睡眠提示词")
                return prompt
        
        return None