#!/usr/bin/env python3
"""Training script for Pattern Classifier"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
import asyncio
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, classification_report
from joblib import dump

from filters.keyword import KeywordFilter
from filters.tfidf import TfidfFilter
from filters.pattern import PatternClassifier
from core.types import MessageMetadata

async def extract_features(df, keyword_filter, tfidf_filter, pattern_clf):
    print(f"\n🔍 Extracting features from {len(df)} messages...")
    features_list = []
    
    for idx, row in df.iterrows():
        text = row['message']
        keyword_result = await keyword_filter.analyze(text)
        tfidf_result = await tfidf_filter.analyze(text)
        
        metadata = MessageMetadata(
            message_id=idx, user_id=0, user_name="Unknown",
            chat_id=0, timestamp=0.0
        )
        
        features = pattern_clf._extract_features(text, metadata, keyword_result.score, tfidf_result.score)
        features_list.append(features)
        
        if (idx + 1) % 500 == 0:
            print(f"   Processed {idx + 1}/{len(df)}...")
    
    return np.array(features_list)

def main():
    print("=" * 60)
    print("Pattern Classifier Training (LightGBM)")
    print("=" * 60)
    
    data_path = PROJECT_ROOT / "data" / "messages.csv"
    output_dir = PROJECT_ROOT / "models"
    
    print(f"\n📂 Loading dataset...")
    df = pd.read_csv(data_path)
    df = df.drop_duplicates(subset='message', keep='first')
    print(f"✅ Loaded {len(df)} unique samples")
    
    print("\n📦 Loading filters...")
    keyword_filter = KeywordFilter()
    tfidf_filter = TfidfFilter()
    
    if not tfidf_filter.is_ready():
        print("❌ TF-IDF not trained! Run train_tfidf.py first.")
        return 1
    
    pattern_clf = PatternClassifier()
    print("✅ Filters loaded")
    
    print("\n🔧 Extracting 20 features...")
    X = asyncio.run(extract_features(df, keyword_filter, tfidf_filter, pattern_clf))
    y = df['label'].values
    print(f"✅ Features shape: {X.shape}")
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    print(f"\n🔀 Train: {len(X_train)}, Test: {len(X_test)}")
    
    print("\n🌳 Training LightGBM...")
    lgbm_clf = lgb.LGBMClassifier(
        n_estimators=100, max_depth=5, learning_rate=0.1,
        num_leaves=31, class_weight='balanced', random_state=42, verbose=-1
    )
    lgbm_clf.fit(X_train, y_train)
    print("✅ LightGBM trained")
    
    print("📊 Calibrating...")
    train_proba = lgbm_clf.predict_proba(X_train)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds='clip')
    calibrator.fit(train_proba, y_train)
    
    print("\n📈 Evaluating...")
    test_proba_raw = lgbm_clf.predict_proba(X_test)[:, 1]
    test_proba = calibrator.predict(test_proba_raw)
    y_pred = (test_proba > 0.5).astype(int)
    
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, test_proba)
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1-score:  {f1:.4f}")
    print(f"ROC-AUC:   {roc_auc:.4f}")
    print("\n" + classification_report(y_test, y_pred, target_names=['Ham', 'Spam']))
    
    print("\n🔝 Top 10 Features:")
    feature_names = ['keyword_score', 'tfidf_score', 'has_phone', 'has_url', 'has_email', 
                     'has_money', 'money_count', 'has_age', 'has_cta', 'has_dm', 'has_remote',
                     'has_legal', 'has_casino', 'obfuscation_ratio', 'reply_to_staff',
                     'is_forwarded', 'author_is_admin', 'is_channel', 'whitelist_hits', 'brand_hits']
    importance = lgbm_clf.feature_importances_
    for i, (name, imp) in enumerate(sorted(zip(feature_names, importance), key=lambda x: x[1], reverse=True)[:10], 1):
        print(f"   {i:2d}. {name:20s} {imp:8.1f}")
    
    print(f"\n💾 Saving models...")
    dump(lgbm_clf, output_dir / "pattern_lgbm.pkl")
    dump(calibrator, output_dir / "pattern_calibrator.pkl")
    print(f"✅ Saved to {output_dir}")
    print("\n🎉 Training complete!")

if __name__ == "__main__":
    main()
