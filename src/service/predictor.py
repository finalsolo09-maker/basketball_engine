"""예측 서비스 및 아티팩트 관리 모듈 (PredictionService)."""

import json
from pathlib import Path
import pandas as pd
import numpy as np
import joblib
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

        # 모델 로드 (XGBoost Native JSON format - pickle보다 버전 호환성에 안전함)
        self.reg_home = XGBRegressor()
        self.reg_home.load_model(self.model_dir / "regressor_home.json")

        self.reg_away = XGBRegressor()
        self.reg_away.load_model(self.model_dir / "regressor_away.json")

        self.classifier = XGBClassifier()
        self.classifier.load_model(self.model_dir / "classifier_xgb.json")

        cal_path = self.model_dir / "calibrator.joblib"
        if cal_path.exists():
            self.calibrator = joblib.load(cal_path)
        else:
            self.calibrator = None

        self.sigma_margin = self.metadata.get("sigma_margin", 10.0)
        self.sigma_total = self.metadata.get("sigma_total", 15.0)
        self.ensemble_w = self.metadata.get("ensemble_w", 0.5)

    @classmethod
    def from_artifacts(cls, model_dir: str | Path, history_df: pd.DataFrame, config: dict) -> "PredictionService":
        return cls(model_dir, history_df, config)

    def predict_game(self, home_team: str, away_team: str, game_date: str, ou_line: float = None) -> dict:
        """경기 시작 전 정보만을 활용하여 홈/원정 득점, 승률, O/U를 예측합니다."""
        if home_team == away_team:
            raise ValueError("홈팀과 원정팀이 같을 수 없습니다.")

        dt = pd.to_datetime(game_date)
        
        # 1. 추론을 위한 미래 행 구성 및 히스토리 결합
        dummy_game_id = f"PREDICT_{home_team}_{away_team}_{dt.strftime('%Y%m%d')}"
        future_row = {
            "game_id": dummy_game_id, "date": dt, "season": "2023-2024", "league": self.league,
            "game_type": "regular", "team": home_team, "opponent": away_team, "is_home": 1,
            "pts": np.nan, "opp_pts": np.nan, "fgm": np.nan, "fga": np.nan, "fg3m": np.nan, "fg3a": np.nan,
            "ftm": np.nan, "fta": np.nan, "oreb": np.nan, "dreb": np.nan, "tov": np.nan, "ast": np.nan,
            "stl": np.nan, "blk": np.nan, "game_minutes": 48 if self.league == "NBA" else 40
        }
        future_away_row = future_row.copy()
        future_away_row["team"] = away_team
        future_away_row["opponent"] = home_team
        future_away_row["is_home"] = 0

        combined_df = pd.concat([self.history_df, pd.DataFrame([future_row, future_away_row])], ignore_index=True)
        combined_df = combined_df.sort_values("date").reset_index(drop=True)

        # 2. 파이프라인 통과하여 피처 생성
        built_df = self.builder.build_features(combined_df, is_future=True)
        target_row = built_df[built_df["game_id"] == dummy_game_id].iloc[0]

        # 3. 모델 추론
        features = target_row[self.builder.feature_columns].values.reshape(1, -1)
        
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
            "home_win_prob": round(p_final, 2),
            "consistency_flag": False,
            "warnings": []
        }

        if ou_line is not None:
            ou_results = EnsemblePredictor.calculate_over_under(predicted_total, self.sigma_total, ou_line)
            result.update({k: round(v, 2) for k, v in ou_results.items()})

        return result
