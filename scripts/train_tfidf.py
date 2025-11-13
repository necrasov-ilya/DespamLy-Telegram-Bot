#!/usr/bin/env python3
"""Training script for TF-IDF classifier"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, classification_report
from joblib import dump

def main():
    print("=" * 60)
    print("TF-IDF Classifier Training")
    print("=" * 60)
    
    data_path = PROJECT_ROOT / "data" / "messages.csv"
    output_dir = PROJECT_ROOT / "models"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    vectorizer_path = output_dir / "tfidf_vectorizer.pkl"
    classifier_path = output_dir / "tfidf_classifier.pkl"
    
    print(f"\n📂 Loading dataset from {data_path}...")
    df = pd.read_csv(data_path)
    print(f"✅ Loaded {len(df)} samples")
    print(f"   Spam: {df['label'].sum()} | Ham: {len(df) - df['label'].sum()}")
    
    df = df.drop_duplicates(subset='message', keep='first')
    print(f"✅ After deduplication: {len(df)} samples")
    
    X = df['message']
    y = df['label']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    print(f"\n🔀 Train: {len(X_train)}, Test: {len(X_test)}")
    
    print("\n🔤 Training TF-IDF Vectorizer (char-level, 1-4 grams)...")
    vectorizer = TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 4),
        analyzer='char_wb',
        sublinear_tf=True,
        min_df=2
    )
    
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)
    print(f"✅ Vocabulary: {len(vectorizer.vocabulary_)} features")
    
    print("\n🤖 Training LogisticRegression...")
    base_clf = LogisticRegression(C=1.0, max_iter=1000, solver='liblinear', class_weight='balanced', random_state=42)
    base_clf.fit(X_train_vec, y_train)
    
    print("📊 Calibrating...")
    calibrated_clf = CalibratedClassifierCV(base_clf, method='isotonic', cv='prefit')
    calibrated_clf.fit(X_train_vec, y_train)
    
    print("\n📈 Evaluating...")
    y_pred = calibrated_clf.predict(X_test_vec)
    y_proba = calibrated_clf.predict_proba(X_test_vec)[:, 1]
    
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_proba)
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1-score:  {f1:.4f}")
    print(f"ROC-AUC:   {roc_auc:.4f}")
    print("\n" + classification_report(y_test, y_pred, target_names=['Ham', 'Spam']))
    
    print(f"\n💾 Saving models...")
    dump(vectorizer, vectorizer_path)
    dump(calibrated_clf, classifier_path)
    print(f"✅ Saved to {output_dir}")
    print("\n🎉 Training complete!")

if __name__ == "__main__":
    main()
