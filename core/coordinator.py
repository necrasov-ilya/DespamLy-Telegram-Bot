from __future__ import annotations

from typing import Optional

from telegram import Message

from core.types import AnalysisResult, MessageMetadata
from filters.base import BaseFilter
from filters.pattern import PatternClassifier
from utils.logger import get_logger

LOGGER = get_logger(__name__)


class FilterCoordinator:
    """
    Упрощённый координатор фильтров без эмбеддингов и истории.
    
    Новая архитектура:
    1. KeywordFilter - явные паттерны (телефоны, URL, CTA)
    2. TfidfFilter - char-level n-grams (1-4) + LogisticRegression
    3. PatternClassifier - 20 признаков + LightGBM + calibration
    
    Убрано:
    - История сообщений по чатам (_chat_history)
    - История по пользователям (_user_history)
    - Капсулы (context_capsule, user_capsule)
    - Эмбеддинги (embedding_filter)
    - Graceful degradation
    """
    
    def __init__(
        self,
        keyword_filter: BaseFilter,
        tfidf_filter: BaseFilter,
        pattern_filter: PatternClassifier
    ):
        self.keyword_filter = keyword_filter
        self.tfidf_filter = tfidf_filter
        self.pattern_filter = pattern_filter
    
    def _extract_metadata(self, message: Message) -> MessageMetadata:
        """
        Извлекает метаданные из Telegram Message.
        
        Args:
            message: telegram.Message объект
            
        Returns:
            MessageMetadata с контекстными флагами
        """
        metadata = MessageMetadata(
            message_id=message.message_id,
            user_id=message.from_user.id if message.from_user else 0,
            user_name=message.from_user.full_name if message.from_user else "Unknown",
            chat_id=message.chat_id,
            timestamp=message.date.timestamp() if message.date else 0.0,
        )
        is_reply = message.reply_to_message is not None
        reply_to_user_id = None
        reply_to_staff = False
        
        from storage.bootstrap import get_storage
        storage = get_storage()
        chat_config = storage.chat_configs.get_by_chat_id(message.chat_id)
        whitelist = chat_config.whitelist if chat_config and chat_config.whitelist else []
        
        if is_reply and message.reply_to_message.from_user:
            reply_to_user_id = message.reply_to_message.from_user.id
            reply_to_staff = reply_to_user_id in whitelist
        
        is_forwarded = message.forward_origin is not None
        
        author_is_admin = False
        if message.from_user:
            author_is_admin = message.from_user.id in whitelist
        
        is_channel_announcement = (
            message.sender_chat is not None and 
            message.sender_chat.type == "channel"
        )
        from dataclasses import replace
        metadata = replace(
            metadata,
            is_reply=is_reply,
            reply_to_user_id=reply_to_user_id,
            reply_to_staff=reply_to_staff,
            is_forwarded=is_forwarded,
            author_is_admin=author_is_admin,
            is_channel_announcement=is_channel_announcement
        )
        
        return metadata
    
    async def analyze(
        self,
        text: str,
        message: Optional[Message] = None
    ) -> AnalysisResult:
        """
        Анализ сообщения через упрощённую архитектуру.
        
        Pipeline:
        1. Извлечь метаданные (если есть message)
        2. Keyword filter
        3. TF-IDF filter
        4. Pattern classifier (использует scores из keyword и tfidf)
        
        Args:
            text: текст сообщения
            message: telegram.Message для извлечения метаданных (опционально)
            
        Returns:
            AnalysisResult с оценками всех трёх фильтров
        """
        metadata = None
        if message:
            metadata = self._extract_metadata(message)
            LOGGER.debug(
                f"Metadata: reply_to_staff={metadata.reply_to_staff}, "
                f"is_forwarded={metadata.is_forwarded}, "
                f"author_is_admin={metadata.author_is_admin}"
            )
        keyword_result = await self.keyword_filter.analyze(text)
        LOGGER.debug(f"Keyword: {keyword_result.score:.3f}")
        
        tfidf_result = await self.tfidf_filter.analyze(text)
        LOGGER.debug(f"TF-IDF: {tfidf_result.score:.3f}")
        pattern_result = await self.pattern_filter.analyze(
            text=text,
            metadata=metadata,
            keyword_score=keyword_result.score,
            tfidf_score=tfidf_result.score
        )
        LOGGER.debug(f"Pattern: {pattern_result.score:.3f}")
        result = AnalysisResult(
            keyword_result=keyword_result,
            tfidf_result=tfidf_result,
            pattern_result=pattern_result,
            metadata=metadata
        )
        
        LOGGER.info(
            f"Analysis complete: avg={result.average_score:.3f}, "
            f"max={result.max_score:.3f}"
        )
        
        return result
    
    def is_ready(self) -> bool:
        """Проверка готовности всех фильтров"""
        return (
            self.keyword_filter.is_ready() and
            self.tfidf_filter.is_ready() and
            self.pattern_filter.is_ready()
        )


# Singleton instance
_coordinator_instance: Optional[FilterCoordinator] = None


def get_coordinator() -> FilterCoordinator:
    """
    Получить singleton-экземпляр FilterCoordinator.
    
    Инициализирует все фильтры при первом вызове.
    
    Returns:
        FilterCoordinator с загруженными моделями
    """
    global _coordinator_instance
    
    if _coordinator_instance is None:
        from filters.keyword import KeywordFilter
        from filters.tfidf import TfidfFilter
        
        LOGGER.info("Инициализация FilterCoordinator...")
        
        keyword_filter = KeywordFilter()
        tfidf_filter = TfidfFilter()
        pattern_filter = PatternClassifier()
        
        _coordinator_instance = FilterCoordinator(
            keyword_filter=keyword_filter,
            tfidf_filter=tfidf_filter,
            pattern_filter=pattern_filter
        )
        
        if _coordinator_instance.is_ready():
            LOGGER.info("✅ FilterCoordinator готов к работе")
        else:
            LOGGER.warning("⚠️ FilterCoordinator не полностью готов (некоторые модели не загружены)")
    
    return _coordinator_instance
