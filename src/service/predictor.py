"""예측 서비스 및 아티팩트 관리 모듈 (PredictionService)."""

import json
import hashlib
from pathlib import Path
import pandas as pd
import numpy as np
from xgboost import XGBRegressor, XGBClassifier

from src.features.builder import FeatureBuilder
from src.models.ensemble import EnsemblePredictor
from src.models.calibrator import CalibratedProbModel
from src.exceptions import ArtifactMismatchError, ArtifactVersionError, InsufficientHistoryError

class PredictionService:
    """학습된 모델 아티팩트를 로드하고 단건/배치 예측을 수행하는 서비스 클래스."""

    def __init__(self, model_dir: str | Path, loader_data: pd.DataFrame, config: dict):
        self.model_dir = Path(model_dir)
        self.history_df = loader_data.copy()
        self.config = config
        self.league = self.model_dir.name.upper()
        
        # 설정 로드
        league_cfg = config["league_configs"].get(self.league, config["league_configs"]["NBA"])
        self.builder = FeatureBuilder(league_cfg, config)
        
        self._load_artifacts()

    def _load_artifacts(self):
        """저장된 모델 아티팩트 및 메타데이터를 로드합니다."""
        meta_path = self.model_dir / "metadata.json"
        if not meta_path.exists():
            raise ArtifactMismatchError(f"메타데이터 파일이 존재하지 않습니다: {meta_path}")

        with open(meta_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        if self.metadata.get("league") != self.league:
            raise ArtifactMismatchError("모델 리그 메타데이터 불일치")
        if self.metadata.get("feature_columns") != self.builder.feature_columns:
            raise ArtifactMismatchError("학습/추론 피처 스키마 불일치")
        expected = self.metadata.get("artifact_sha256")
        if not isinstance(expected, dict):
            raise ArtifactMismatchError("아티팩트 해시 목록이 없습니다.")
        for name in (
            "regressor_home.json", "regressor_away.json",
            "classifier_xgb.json", "calibrator.json"
        ):
            path = self.model_dir / name
            if not path.is_file() or (
                hashlib.sha256(path.read_bytes()).hexdigest() != expected.get(name)
            ):
                raise ArtifactMismatchError(f"모델 아티팩트 SHA-256 검증 실패: {name}")

        self.reg_home = XGBRegressor()
        self.reg_home.load_model(self.model_dir / "regressor_home.json")
        self.reg_away = XGBRegressor()
        self.reg_away.load_model(self.model_dir / "regressor_away.json")
        self.classifier = XGBClassifier()
        self.classifier.load_model(self.model_dir / "classifier_xgb.json")

        with open(self.model_dir / "calibrator.json", "r", encoding="utf-8") as f:
            self.calibrator = CalibratedProbModel.from_dict(json.load(f))
        self.sigma_margin = float(self.metadata["sigma_margin"])
        self.sigma_total = float(self.metadata["sigma_total"])
        self.ensemble_w = float(self.metadata["ensemble_w"])
        if (
            not np.isfinite([self.sigma_margin, self.sigma_total, self.ensemble_w]).all()
            or min(self.sigma_margin, self.sigma_total) <= 0
            or not 0 <= self.ensemble_w <= 1
        ):
            raise ArtifactMismatchError("모델 확률 분포 파라미터가 잘못됐습니다.")

    @classmethod
    def from_artifacts(cls, model_dir: str | Path, history_df: pd.DataFrame, config: dict) -> "PredictionService":
        return cls(model_dir, history_df, config)

    def predict_game(self, home_team: str, away_team: str, game_date: str, ou_line: float = None, namespace: str = "synthetic") -> dict:
        """경기 시작 전 정보만을 활용하여 홈/원정 득점, 승률, O/U를 예측합니다."""
        if home_team == away_team:
            raise ValueError("홈팀과 원정팀이 같을 수 없습니다.")

        if namespace != "synthetic":
            raise ValueError("실제 데이터 승인·시각 검증 원장이 없어 live 예측 불가")
        if self.metadata.get("data_evidence_grade") != "SYNTHETIC":
            raise ArtifactMismatchError("허용되지 않은 데이터 증거 등급")
        dt = pd.to_datetime(game_date)
        year = dt.year if dt.month >= 10 else dt.year - 1
        season = f"{year}-{year + 1}"
        
        # 1. 추론을 위한 미래 행 구성 및 히스토리 결합
        dummy_game_id = f"PREDICT_{home_team}_{away_team}_{dt.strftime('%Y%m%d')}"
        known_history = self.history_df[
            pd.to_datetime(self.history_df["date"]) < dt
        ].copy()
        if known_history.empty:
            raise InsufficientHistoryError("대상일 이전 경기 기록이 없습니다.")
        future_row = {
            "game_id": dummy_game_id, "date": dt, "season": season, "league": self.league,
            "game_type": "regular", "team": home_team, "opponent": away_team, "is_home": 1,
            "pts": np.nan, "opp_pts": np.nan, "fgm": np.nan, "fga": np.nan, "fg3m": np.nan, "fg3a": np.nan,
            "ftm": np.nan, "fta": np.nan, "oreb": np.nan, "dreb": np.nan, "tov": np.nan, "ast": np.nan,
            "stl": np.nan, "blk": np.nan, "game_minutes": 48 if self.league == "NBA" else 40
        }
        future_away_row = future_row.copy()
        future_away_row["team"] = away_team
        future_away_row["opponent"] = home_team
        future_away_row["is_home"] = 0

        combined_df = pd.concat([known_history, pd.DataFrame([future_row, future_away_row])], ignore_index=True)
        combined_df = combined_df.sort_values("date").reset_index(drop=True)

        # 2. 파이프라인 통과하여 피처 생성
        built_df = self.builder.build_features(combined_df, is_future=True)
        selected = built_df[
            (built_df["game_id"] == dummy_game_id) & (built_df["is_home"] == 1)
        ]
        if len(selected) != 1:
            raise ValueError("예측 홈 경기 식별이 모호합니다.")
        target_row = selected.iloc[0]

        # 3. 모델 추론
        features = target_row[self.builder.feature_columns].to_numpy(dtype=float).reshape(1, -1)
        if not np.isfinite(features).all():
            raise ValueError("미확정·결측 피처가 있습니다.")
        
        pred_home_pts = float(self.reg_home.predict(features)[0])
        pred_away_pts = float(self.reg_away.predict(features)[0])
        predicted_margin = pred_home_pts - pred_away_pts
        predicted_total = pred_home_pts + pred_away_pts

        raw_prob = float(self.classifier.predict_proba(features)[0, 1])
        cal_prob = float(self.calibrator.predict_proba(np.array([raw_prob]))[0]) if self.calibrator else raw_prob

        p_reg = EnsemblePredictor.calc_regression_win_prob(predicted_margin, self.sigma_margin)
        p_final = EnsemblePredictor.combine_probabilities(cal_prob, p_reg, self.ensemble_w)

        result = {
            "league": self.league,
            "home_expected_pts": round(pred_home_pts, 1),
            "away_expected_pts": round(pred_away_pts, 1),
            "predicted_margin": round(predicted_margin, 1),
            "predicted_total": round(predicted_total, 1),
            "home_win_prob": p_final,
            "consistency_flag": (predicted_margin > 0) != (p_final > 0.5),
            "model_status": self.metadata["model_status"],
            "data_evidence_grade": "SYNTHETIC",
            "eligible_live_p0": False,
            "warnings": ["합성 데이터 기반 연구 테스트이며 실제 예측 성능이 아닙니다.",
                         "선수·부상·확정 선발과 실시간 공식 결과가 반영되지 않았습니다."]
        }

        if ou_line is not None:
            ou_results = EnsemblePredictor.calculate_over_under(predicted_total, self.sigma_total, ou_line)
            result.update({k: round(v, 2) for k, v in ou_results.items()})

        return result
