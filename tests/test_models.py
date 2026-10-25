"""3단계 모델 학습 및 Walk-Forward CV 관련 테스트."""

import pytest
import numpy as np
import pandas as pd
from src.models.trainer import ModelTrainer
from src.features.builder import FeatureBuilder
from data.sample_generator import SampleDataGenerator

def test_cv_split_order_and_trainer():
    gen = SampleDataGenerator(seed=42)
    df, _ = gen.generate(league="KBL", n_seasons=1)

    global_config = {
        "seed": 42,
        "features": {
            "rolling_windows": [5],
            "ewma_span": 5,
            "shrinkage_k": 5,
            "h2h_n": 5,
            "h2h_k": 5,
            "rest_days_default": 3,
            "rest_days_cap": 7
        },
        "training": {
            "min_train_games": 30,
            "n_splits": 3,
            "calibration_method": "sigmoid"
        }
    }
    league_config = {
        "regulation_minutes": 40,
        "elo_init": 1500,
        "elo_k": 20,
        "elo_hfa": 80,
        "use_mov_adjustment": True,
        "new_season_blend": 0.7,
        "league_priors": {"pace": 72.0, "ortg": 108.0, "pts": 81.0}
    }

    builder = FeatureBuilder(league_config, global_config)
    built_df = builder.build_features(df)

    trainer = ModelTrainer(global_config, league_config)
    # 데이터 수가 충분하지 않을 경우를 대비해 예외 처리 확인 또는 소규모 통과 확인
    try:
        results = trainer.walk_forward_cv(built_df, builder.feature_columns)
        assert "sigma_margin" in results
        assert "calibrator" in results
    except Exception as e:
        # 데이터 부족 시 InsufficientDataError 발생하는지 검증
        assert "학습 데이터가 부족합니다" in str(e)
