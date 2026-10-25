"""Walk-Forward CV 및 XGBoost 모델 학습 모듈."""

import numpy as np
import pandas as pd
from xgboost import XGBRegressor, XGBClassifier
from sklearn.model_selection import TimeSeriesSplit
from src.models.calibrator import CalibratedProbModel
from src.models.evaluator import ModelEvaluator
from src.exceptions import InsufficientDataError

class ModelTrainer:
    """Walk-Forward CV를 수행하고 XGBRegressor, XGBClassifier를 학습하는 클래스."""

    def __init__(self, config: dict, league_config: dict):
        self.config = config
        self.league_config = league_config
        self.training_config = config["training"]

    def walk_forward_cv(self, df: pd.DataFrame, feature_cols: list[str]) -> dict:
        """시간 순서를 보장하는 Walk-Forward CV를 실행하고 OOF 예측값을 수집합니다."""
        # 홈 행만 필터링 (경기 단위 예측 대상)
        home_df = df[df["is_home"] == 1].copy().sort_values("date").reset_index(drop=True)
        
        min_games = self.training_config.get("min_train_games", 100)
        if len(home_df) < min_games:
            raise InsufficientDataError(f"학습 데이터가 부족합니다. (현재: {len(home_df)}, 최소 요구: {min_games})")

        X = home_df[feature_cols].values
        y_home = home_df["pts"].values
        # 원정팀 득점 추출을 위해 매핑
        away_pts_map = df[df["is_home"] == 0].set_index("game_id")["pts"].to_dict()
        home_df["away_pts"] = home_df["game_id"].map(away_pts_map)
        y_away = home_df["away_pts"].values
        y_margin = y_home - y_away
        y_win = (y_home > y_away).astype(int)

        n_splits = self.training_config.get("n_splits", 5)
        tscv = TimeSeriesSplit(n_splits=n_splits)

        oof_home_pred = np.zeros(len(home_df))
        oof_away_pred = np.zeros(len(home_df))
        oof_raw_prob = np.zeros(len(home_df))

        indices = np.arange(len(home_df))

        for fold, (train_idx, val_idx) in enumerate(tscv.split(indices)):
            if len(train_idx) < 50:
                continue

            X_train, X_val = X[train_idx], X[val_idx]
            
            # 모델 정의 (XGBoost 2.x API)
            reg_h = XGBRegressor(n_estimators=100, tree_method="hist", objective="reg:squarederror", random_state=self.config["seed"])
            reg_a = XGBRegressor(n_estimators=100, tree_method="hist", objective="reg:squarederror", random_state=self.config["seed"])
            clf = XGBClassifier(n_estimators=100, tree_method="hist", objective="binary:logistic", random_state=self.config["seed"])

            reg_h.fit(X_train, y_home[train_idx])
            reg_a.fit(X_train, y_away[train_idx])
            clf.fit(X_train, y_win[train_idx])

            oof_home_pred[val_idx] = reg_h.predict(X_val)
            oof_away_pred[val_idx] = reg_a.predict(X_val)
            oof_raw_prob[val_idx] = clf.predict_proba(X_val)[:, 1]

        # 확률 보정기 학습 (OOF 기반 단일 경로)
        calibrator = CalibratedProbModel(method=self.training_config.get("calibration_method", "sigmoid"))
        valid_mask = oof_raw_prob > 0
        if valid_mask.sum() > 10:
            calibrator.fit(oof_raw_prob[valid_mask], y_win[valid_mask])

        # 잔차 표준편차 산출
        margin_residuals = (y_home - y_away) - (oof_home_pred - oof_away_pred)
        sigma_margin = float(np.std(margin_residuals))
        total_residuals = (y_home + y_away) - (oof_home_pred + oof_away_pred)
        sigma_total = float(np.std(total_residuals))

        return {
            "sigma_margin": max(sigma_margin, 1.0),
            "sigma_total": max(sigma_total, 1.0),
            "calibrator": calibrator,
            "oof_metrics": ModelEvaluator.evaluate_classification(y_win, calibrator.predict_proba(oof_raw_prob))
        }
@staticmethod
    def optimize_ensemble_weight(y_true: np.ndarray, p_clf: np.ndarray, p_reg_prob: np.ndarray) -> float:
        """OOF 예측 결과에서 LogLoss를 최소화하는 앙상블 가중치 w를 탐색합니다."""
        best_w = 0.5
        best_loss = float("inf")
        
        for w in np.linspace(0, 1, 21):
            p_blend = w * p_clf + (1 - w) * p_reg_prob
            p_blend = np.clip(p_blend, 1e-15, 1.0 - 1e-15)
            from sklearn.metrics import log_loss
            loss = log_loss(y_true, p_blend)
            if loss < best_loss:
                best_loss = loss
                best_w = float(w)
        return best_w
