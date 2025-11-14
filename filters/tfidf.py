from __future__ import annotations

from pathlib import Path

import pandas as pd
from joblib import dump, load
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline

from core.types import FilterResult
from filters.base import BaseFilter
from utils.logger import get_logger

LOGGER = get_logger(__name__)


class TfidfFilter(BaseFilter):
    def __init__(
        self,
        model_path: Path | str | None = None,
        dataset_path: Path | str | None = None,
    ):
        super().__init__("tfidf")
        
        root_dir = Path(__file__).resolve().parents[1]
        self.vectorizer_path = Path(model_path).parent / "tfidf_vectorizer.pkl" if model_path else root_dir / "models" / "tfidf_vectorizer.pkl"
        self.classifier_path = Path(model_path).parent / "tfidf_classifier.pkl" if model_path else root_dir / "models" / "tfidf_classifier.pkl"
        self.dataset_path = Path(dataset_path) if dataset_path else root_dir / "data" / "messages.csv"
        
        self.vectorizer: TfidfVectorizer | None = None
        self.classifier: CalibratedClassifierCV | None = None
        self._new_samples = 0
        self._load_models()
    
    def _load_models(self) -> None:
        """Загружает vectorizer и classifier из отдельных файлов"""
        try:
            if self.vectorizer_path.exists() and self.classifier_path.exists():
                self.vectorizer = load(self.vectorizer_path)
                self.classifier = load(self.classifier_path)
                LOGGER.info(f"Loaded TF-IDF models from {self.vectorizer_path.parent}")
            else:
                LOGGER.warning(f"Models not found, need training via scripts/train_tfidf.py")
        except Exception as e:
            LOGGER.error(f"Failed to load models: {e}")
            self.vectorizer = None
            self.classifier = None
    
    def train(self) -> None:
        """
        DEPRECATED: Используйте scripts/train_tfidf.py для обучения.
        Новая архитектура требует char-level n-grams и калибровку.
        """
        LOGGER.error(
            "Direct training deprecated. Use 'python scripts/train_tfidf.py' instead. "
            "New architecture uses char-level n-grams (1-4) and calibrated LogisticRegression."
        )
    
    async def analyze(self, text: str) -> FilterResult:
        if not self.vectorizer or not self.classifier:
            LOGGER.warning("Models not loaded, returning neutral score")
            return FilterResult(
                filter_name=self.name,
                score=0.5,
                confidence=0.0,
                details={"error": "Models not loaded"}
            )
        
        try:
            features = self.vectorizer.transform([text])
            proba = self.classifier.predict_proba(features)[0]
            spam_proba = float(proba[1]) if len(proba) > 1 else 0.5
            prediction = int(spam_proba > 0.5)
            
            return FilterResult(
                filter_name=self.name,
                score=spam_proba,
                confidence=max(proba),
                details={
                    "prediction": prediction,
                    "probabilities": proba.tolist()
                }
            )
        except Exception as e:
            LOGGER.error(f"Prediction failed: {e}")
            return FilterResult(
                filter_name=self.name,
                score=0.5,
                confidence=0.0,
                details={"error": str(e)}
            )
    
    def is_ready(self) -> bool:
        return self.vectorizer is not None and self.classifier is not None
    
    def update_dataset(self, message: str, label: int) -> bool:
        if label not in (0, 1):
            raise ValueError("Label must be 0 or 1")
        
        if not self.dataset_path.exists():
            LOGGER.error(f"Dataset not found: {self.dataset_path}")
            return False
        
        try:
            df = pd.read_csv(self.dataset_path)
            duplicate_mask = (df["message"] == message) & (df["label"] == label)
            if duplicate_mask.any():
                LOGGER.debug("Sample already exists in dataset")
                return False
            
            df.loc[len(df)] = [message, label]
            df.to_csv(self.dataset_path, index=False)
            LOGGER.info(f"Added new sample to dataset: {message[:50]}... | label={label}")
            
            self._new_samples += 1
            return True
        except Exception as e:
            LOGGER.error(f"Failed to update dataset: {e}")
            return False
    
    def should_retrain(self, threshold: int = 100) -> bool:
        return self._new_samples >= threshold
