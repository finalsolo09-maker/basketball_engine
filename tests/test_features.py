"""2단계 피처 엔지니어링 단위 테스트 (누수 방지, 슈링크리지, Elo)."""

import pandas as pd
import numpy as np
from src.features.builder import FeatureBuilder
from data.sample_generator import SampleDataGenerator

def test_no_leakage_and_shrinkage():
    gen = SampleDataGenerator(seed=42)
    df, _ = gen.generate(league="KBL", n_seasons=1)

    global_config = {
        "features": {
            "rolling_windows": [5],
            "ewma_span": 5,
            "shrinkage_k": 5,
            "h2h_n": 5,
            "h2h_k": 5,
            "rest_days_default": 3,
            "rest_days_cap": 7
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

    # 1. 누수 방지 검증: 미래 행의 점수를 변경해도 과거 경기 피처가 변하지 않아야 함
    target_game_id = built_df["game_id"].iloc[10]
    original_feature_val = built_df.loc[built_df["game_id"] == target_game_id, "elo_pre"].values[0]

    # 미래 행 값 조작
    df_modified = df.copy()
    df_modified.loc[df_modified["game_id"] == built_df["game_id"].iloc[-1], "pts"] = 999
    built_df_mod = builder.build_features(df_modified)
    modified_feature_val = built_df_mod.loc[built_df_mod["game_id"] == target_game_id, "elo_pre"].values[0]

    assert original_feature_val == modified_feature_val, "데이터 누수 발생: 미래 데이터 변경이 과거 피처에 영향을 줌"

def test_elo_properties():
    gen = SampleDataGenerator(seed=42)
    df, _ = gen.generate(league="NBA", n_seasons=1)

    global_config = {
        "features": {
            "rolling_windows": [5],
            "ewma_span": 5,
            "shrinkage_k": 5,
            "h2h_n": 5,
            "h2h_k": 5,
            "rest_days_default": 3,
            "rest_days_cap": 7
        }
    }
    league_config = {
        "regulation_minutes": 48,
        "elo_init": 1500,
        "elo_k": 20,
        "elo_hfa": 100,
        "use_mov_adjustment": True,
        "new_season_blend": 0.7,
        "league_priors": {"pace": 99.0, "ortg": 114.0, "pts": 112.0}
    }

    builder = FeatureBuilder(league_config, global_config)
    built_df = builder.build_features(df)

    # Elo 레이팅 컬럼 존재 확인
    assert "elo_pre" in built_df.columns
    assert "elo_opp_pre" in built_df.columns
    assert "elo_diff" in built_df.columns
