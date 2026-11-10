"""핵심 오류 재현/회귀 테스트. 합성자료는 실전 성능 검증 자료가 아니다."""

import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from data.sample_generator import SampleDataGenerator
from src.db_audit import audit_database
from src.features.builder import FeatureBuilder
from src.features.elo import EloCalculator
from src.models.calibrator import CalibratedProbModel
from src.validator import DataValidator
from src.exceptions import DataValidationError


def _config():
    league = {
        "regulation_minutes": 40, "elo_init": 1500,
        "elo_k": 20, "elo_hfa": 80, "use_mov_adjustment": True,
        "new_season_blend": 0.7,
        "league_priors": {"pace": 72, "ortg": 108, "pts": 81},
    }
    global_cfg = {
        "features": {
            "rolling_windows": [5], "ewma_span": 5, "shrinkage_k": 5,
            "rest_days_default": 3, "rest_days_cap": 7,
        }
    }
    return league, global_cfg


def test_synthetic_data_have_real_score_variability_and_valid_boxscore():
    data, oracle = SampleDataGenerator(seed=42).generate("KBL", 1)
    assert len(data) == 540
    assert len(oracle) == 270
    assert len(DataValidator.validate(data)) == len(data)
    assert data["pts"].std() > 6
    home = data.loc[data["is_home"] == 1]
    wins = home["pts"].to_numpy() > home["opp_pts"].to_numpy()
    assert 0.10 < wins.mean() < 0.90


def test_validator_reciprocal_score_and_fga_subset():
    data, _ = SampleDataGenerator(seed=42).generate("KBL", 1)
    wrong = data.copy()
    wrong.loc[0, "opp_pts"] += 1
    with pytest.raises(DataValidationError):
        DataValidator.validate(wrong)
    wrong = data.copy()
    wrong.loc[0, "fg3a"] = wrong.loc[0, "fga"] + 1
    with pytest.raises(DataValidationError):
        DataValidator.validate(wrong)


def test_same_date_elo_snapshot_and_past_state():
    rows = []
    for date, fixture, h, a, hp, ap in [
        ("2026-11-01", "a", "A", "B", 90, 70),
        ("2026-11-01", "b", "A", "C", 50, 100),
        ("2026-11-02", "c", "A", "D", 80, 75),
    ]:
        for home, team, opp, pts, opp_pts in [
            (1, h, a, hp, ap), (0, a, h, ap, hp)
        ]:
            rows.append(dict(
                date=pd.Timestamp(date), game_id=fixture, season="2026-2027",
                is_home=home, team=team, opponent=opp, pts=pts, opp_pts=opp_pts
            ))
    elo = EloCalculator(_config()[0]).calculate_elo_features(pd.DataFrame(rows))
    first = elo[(elo["game_id"] == "a") & (elo["is_home"] == 1)].iloc[0]
    same = elo[(elo["game_id"] == "b") & (elo["is_home"] == 1)].iloc[0]
    next_day = elo[(elo["game_id"] == "c") & (elo["is_home"] == 1)].iloc[0]
    assert first["elo_pre"] == same["elo_pre"] == 1500
    assert next_day["elo_pre"] != 1500


def test_feature_builder_symmetry_and_no_null_overwrite():
    data, _ = SampleDataGenerator(seed=42).generate("KBL", 1)
    builder = FeatureBuilder(*_config())
    built = builder.build_features(data)
    assert np.isfinite(built.loc[built["is_home"] == 1, builder.feature_columns].to_numpy(dtype=float)).all()
    first_fixture = built["game_id"].iloc[0]
    pair = built.loc[built["game_id"] == first_fixture]
    assert len(pair) == 2
    home = pair[pair["is_home"] == 1].iloc[0]
    away = pair[pair["is_home"] == 0].iloc[0]
    assert home["expected_pace"] == pytest.approx(away["expected_pace"])


def test_calibrator_json_roundtrip_and_reject_unsafe_coef():
    p = np.linspace(0.1, 0.9, 100)
    y = (p > 0.5).astype(int)
    c = CalibratedProbModel("sigmoid").fit(p, y)
    restored = CalibratedProbModel.from_dict(json.loads(json.dumps(c.to_dict())))
    assert np.allclose(c.predict_proba(p), restored.predict_proba(p))
    bad = c.to_dict()
    bad["parameters"]["a"] = -10.0
    with pytest.raises(ValueError):
        CalibratedProbModel.from_dict(bad)


def test_sqlite_audit_read_only_and_missing_schema(tmp_path):
    db = tmp_path / "audit.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE fixtures (fixture_uid TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO fixtures VALUES ('a')")
    result = audit_database(db)
    assert result["integrity"] == "OK"
    assert result["foreign_keys"] == "OK"
    assert result["status"] == "BLOCKED_INCOMPLETE_SCHEMA"
