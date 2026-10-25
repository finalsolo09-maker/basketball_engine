"""1단계 DataValidator 및 샘플 생성기 테스트."""

import pytest
import pandas as pd
from src.validator import DataValidator
from src.exceptions import DataValidationError
from data.sample_generator import SampleDataGenerator

def test_sample_generator_and_validator():
    gen = SampleDataGenerator(seed=42)
    df, oracle_df = gen.generate(league="KBL", n_seasons=1)
    
    # 샘플 데이터가 DataValidator를 통과하는지 검증
    validated_df = DataValidator.validate(df, policy="raise")
    assert not validated_df.empty
    assert "game_id" in validated_df.columns
    assert len(oracle_df) > 0

def test_validator_raises_on_identity_mismatch():
    gen = SampleDataGenerator(seed=42)
    df, _ = gen.generate(league="KBL", n_seasons=1)
    
    # 의도적으로 PTS 항등식 위반 조작
    df.loc[0, "pts"] += 10
    
    with pytest.raises(DataValidationError):
        DataValidator.validate(df, policy="raise")

def test_validator_raises_on_row_count():
    gen = SampleDataGenerator(seed=42)
    df, _ = gen.generate(league="KBL", n_seasons=1)
    
    # 첫 번째 행 제거하여 game_id당 1행으로 만들기
    df_broken = df.iloc[1:].reset_index(drop=True)
    
    with pytest.raises(DataValidationError):
        DataValidator.validate(df_broken, policy="raise")
