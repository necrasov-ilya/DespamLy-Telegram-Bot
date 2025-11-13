from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Action(str, Enum):
    APPROVE = "approve"
    NOTIFY = "notify"
    DELETE = "delete"
    KICK = "kick"


@dataclass(frozen=True)
class FilterResult:
    filter_name: str
    score: float
    confidence: float = 1.0
    details: dict[str, any] | None = None


@dataclass(frozen=True)
class MessageMetadata:
    """Метаданные сообщения для контекстного анализа"""
    message_id: int
    user_id: int
    user_name: str
    chat_id: int
    timestamp: float
    is_reply: bool = False
    reply_to_user_id: int | None = None
    reply_to_staff: bool = False  # Ответ модератору/админу
    is_forwarded: bool = False
    author_is_admin: bool = False
    is_channel_announcement: bool = False  # Пост из канала


@dataclass(frozen=True)
class AnalysisResult:
    """
    Результат анализа сообщения через упрощённую архитектуру.
    
    Новая архитектура: Keyword → TF-IDF → Pattern (LightGBM)
    Убраны: эмбеддинги, капсулы, история чатов/пользователей
    """
    keyword_result: FilterResult
    tfidf_result: FilterResult
    pattern_result: FilterResult  # НОВОЕ: PatternClassifier (20 признаков + LightGBM)
    metadata: MessageMetadata | None = None
    applied_downweights: List[str] = field(default_factory=list)  # Примененные множители
    
    @property
    def average_score(self) -> float:
        """
        Взвешенная оценка из трёх фильтров.
        
        Новая архитектура:
        - Keyword: 20% (явные паттерны)
        - TF-IDF: 40% (статистика char-grams)
        - Pattern: 40% (20 признаков + LightGBM)
        """
        return (
            self.keyword_result.score * 0.20 +
            self.tfidf_result.score * 0.40 +
            self.pattern_result.score * 0.40
        )
    
    @property
    def max_score(self) -> float:
        """Максимальная оценка среди всех фильтров"""
        return max(
            self.keyword_result.score,
            self.tfidf_result.score,
            self.pattern_result.score
        )
    
    @property
    def all_high(self) -> bool:
        """Проверка что все фильтры дали высокую оценку (>= 0.7)"""
        threshold = 0.7
        return (
            self.keyword_result.score >= threshold and
            self.tfidf_result.score >= threshold and
            self.pattern_result.score >= threshold
        )
