from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from joblib import load

from core.types import FilterResult
from filters.base import BaseFilter
from utils.logger import get_logger

if TYPE_CHECKING:
    from core.types import MessageMetadata

LOGGER = get_logger(__name__)


class PatternClassifier(BaseFilter):
    """
    Pattern-based classifier using LightGBM with 20 engineered features.
    
    Features (20 total):
    - Scores (2): keyword_score, tfidf_score
    - Text patterns (12): has_phone, has_url, has_email, has_money, money_count, 
                         has_age, has_cta, has_dm, has_remote, has_legal, 
                         has_casino, obfuscation_ratio
    - Context flags (4): reply_to_staff, is_forwarded, author_is_admin, is_channel_announcement
    - Whitelist hits (2): whitelist_keywords, brand_keywords
    """
    
    def __init__(
        self,
        model_dir: Path | str | None = None,
    ):
        super().__init__("pattern")
        
        root_dir = Path(__file__).resolve().parents[1]
        self.model_dir = Path(model_dir) if model_dir else root_dir / "models"
        
        self.lgbm_path = self.model_dir / "pattern_lgbm.pkl"
        self.calibrator_path = self.model_dir / "pattern_calibrator.pkl"
        
        self.lgbm = None
        self.calibrator = None
        self._load_models()
        
        # Regex patterns для извлечения признаков
        self._compile_patterns()
    
    def _load_models(self) -> None:
        """Загружает LightGBM и isotonic calibrator"""
        try:
            if self.lgbm_path.exists() and self.calibrator_path.exists():
                self.lgbm = load(self.lgbm_path)
                self.calibrator = load(self.calibrator_path)
                LOGGER.info(f"Loaded PatternClassifier from {self.model_dir}")
            else:
                LOGGER.warning(
                    f"Models not found at {self.model_dir}. "
                    "Run 'python scripts/train_pattern.py' to train."
                )
        except Exception as e:
            LOGGER.error(f"Failed to load models: {e}")
            self.lgbm = None
            self.calibrator = None
    
    def _compile_patterns(self) -> None:
        """Компилирует regex паттерны для извлечения признаков"""
        self.patterns = {
            'phone': re.compile(r'\+?\d[\d\s\-\(\)]{9,}'),
            'url': re.compile(r'https?://|bit\.ly|t\.me/|\.rf\.gd|\.xo\.je'),
            'email': re.compile(r'[\w\.-]+@[\w\.-]+\.\w+'),
            'money': re.compile(r'[\$₽€]\s*\d+|\d+\s*[\$₽€руб]|доллар|рубл'),
            'age': re.compile(r'(?:от|с|старше|возраст)\s*\d{2}[+\s]|18\+|21\+|2[01]\s*\+'),
            'cta': re.compile(r'пиш[иу]|жми|переход|кликай|тык|регистр|получ[аи]|забир|напиши\s*[+«]', re.I),
            'dm': re.compile(r'в\s+личк|в\s+лс|в\s+директ|в\s+дм|пиши\s+в', re.I),
            'remote': re.compile(r'удалённ|удаленн|дистанцион|онлайн.{0,10}работ|из\s+дома|с\s+телефон', re.I),
            'legal': re.compile(r'легальн|белая\s+ниша|официальн|документ', re.I),
            'casino': re.compile(r'казино|казик|каз[иь]|слот|ставк|bet|выигр|занос|депозит|rtp', re.I),
            'obfuscation': re.compile(r'[@#$%&*]+[а-яa-z]+|[а-я]{2,}[@#$%&*]+|з@р@б|дοхοд|зaрaб', re.I),
        }
        
        # Whitelist keywords (легитимные слова)
        self.whitelist_keywords = [
            'доставка', 'заказ', 'магазин', 'товар', 'продукт', 'цена', 
            'скидка', 'акция', 'спасибо', 'благодарю', 'получил'
        ]
        
        # Brand keywords (известные бренды)
        self.brand_keywords = [
            'lifemart', 'ozon', 'wildberries', 'wb', 'яндекс', 'сбер'
        ]
    
    def _extract_features(
        self,
        text: str,
        metadata: MessageMetadata | None,
        keyword_score: float,
        tfidf_score: float
    ) -> np.ndarray:
        """
        Извлекает 20 признаков из текста и метаданных.
        
        Returns:
            numpy array shape (20,)
        """
        text_lower = text.lower()
        
        # Scores from other filters (2)
        feat_keyword = keyword_score
        feat_tfidf = tfidf_score
        
        # Text patterns (12)
        feat_has_phone = bool(self.patterns['phone'].search(text))
        feat_has_url = bool(self.patterns['url'].search(text))
        feat_has_email = bool(self.patterns['email'].search(text))
        
        money_matches = self.patterns['money'].findall(text_lower)
        feat_has_money = len(money_matches) > 0
        feat_money_count = min(len(money_matches), 5)  # cap at 5
        
        feat_has_age = bool(self.patterns['age'].search(text))
        feat_has_cta = bool(self.patterns['cta'].search(text))
        feat_has_dm = bool(self.patterns['dm'].search(text))
        feat_has_remote = bool(self.patterns['remote'].search(text))
        feat_has_legal = bool(self.patterns['legal'].search(text))
        feat_has_casino = bool(self.patterns['casino'].search(text))
        
        # Obfuscation ratio
        obf_matches = len(self.patterns['obfuscation'].findall(text))
        feat_obfuscation_ratio = min(obf_matches / max(len(text.split()), 1), 1.0)
        
        # Context flags (4)
        if metadata:
            feat_reply_to_staff = metadata.reply_to_staff
            feat_is_forwarded = metadata.is_forwarded
            feat_author_is_admin = metadata.author_is_admin
            feat_is_channel = metadata.is_channel_announcement
        else:
            feat_reply_to_staff = False
            feat_is_forwarded = False
            feat_author_is_admin = False
            feat_is_channel = False
        
        # Whitelist hits (2)
        whitelist_hits = sum(1 for kw in self.whitelist_keywords if kw in text_lower)
        brand_hits = sum(1 for kw in self.brand_keywords if kw in text_lower)
        feat_whitelist = min(whitelist_hits, 5)
        feat_brand = min(brand_hits, 3)
        features = np.array([
            # Scores (2)
            feat_keyword,
            feat_tfidf,
            # Text patterns (12)
            float(feat_has_phone),
            float(feat_has_url),
            float(feat_has_email),
            float(feat_has_money),
            float(feat_money_count),
            float(feat_has_age),
            float(feat_has_cta),
            float(feat_has_dm),
            float(feat_has_remote),
            float(feat_has_legal),
            float(feat_has_casino),
            float(feat_obfuscation_ratio),
            # Context flags (4)
            float(feat_reply_to_staff),
            float(feat_is_forwarded),
            float(feat_author_is_admin),
            float(feat_is_channel),
            # Whitelist (2)
            float(feat_whitelist),
            float(feat_brand),
        ], dtype=np.float32)
        
        return features
    
    async def analyze(
        self,
        text: str,
        metadata: MessageMetadata | None = None,
        keyword_score: float = 0.0,
        tfidf_score: float = 0.0
    ) -> FilterResult:
        """
        Анализирует сообщение и возвращает вероятность спама.
        
        Args:
            text: текст сообщения
            metadata: метаданные сообщения (контекстные флаги)
            keyword_score: оценка от KeywordFilter
            tfidf_score: оценка от TfidfFilter
            
        Returns:
            FilterResult с calibrated вероятностью спама
        """
        if not self.lgbm or not self.calibrator:
            LOGGER.warning("Models not loaded, returning neutral score")
            return FilterResult(
                filter_name=self.name,
                score=0.5,
                confidence=0.0,
                details={"error": "Models not loaded"}
            )
        
        try:
            features = self._extract_features(text, metadata, keyword_score, tfidf_score)
            raw_proba = self.lgbm.predict_proba([features])[0, 1]
            calibrated_proba = float(self.calibrator.predict([raw_proba])[0])
            calibrated_proba = np.clip(calibrated_proba, 0.0, 1.0)
            
            return FilterResult(
                filter_name=self.name,
                score=calibrated_proba,
                confidence=1.0,  # LightGBM всегда уверен в своих предсказаниях
                details={
                    "raw_proba": float(raw_proba),
                    "features_count": len(features),
                    "has_metadata": metadata is not None
                }
            )
        except Exception as e:
            LOGGER.error(f"Prediction failed: {e}", exc_info=True)
            return FilterResult(
                filter_name=self.name,
                score=0.5,
                confidence=0.0,
                details={"error": str(e)}
            )
    
    def is_ready(self) -> bool:
        return self.lgbm is not None and self.calibrator is not None
