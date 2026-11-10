"""날짜 단위 Walk-Forward 연구용 검증기.

TUNE/META_A/META_B/HOLDOUT을 분리한 승인 검증기는 아님.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier, XGBRegressor

from src.exceptions import InsufficientDataError
from src.models.calibrator import CalibratedProbModel
from src.models.evaluator import ModelEvaluator


class ModelTrainer:
    """검증에 사용된 OOF 행만 성능·잔차 표준편차에 사용한다."""

    def __init__(self, config: dict, league_config: dict):
        self.config = config
        self.league_config = league_config
        self.training_config = config["training"]

    def walk_forward_cv(self, df: pd.DataFrame, feature_cols: list[str]) -> dict:
        home = df[df["is_home"] == 1].copy().sort_values(
            ["date", "game_id"]
        ).reset_index(drop=True)
        min_games = int(self.training_config.get("min_train_games", 100))
        if len(home) < min_games:
            raise InsufficientDataError(
                f"학습 데이터가 부족합니다. (현재: {len(home)}, 최소 요구: {min_games})"
            )

        away = df[df["is_home"] == 0][["game_id", "pts"]].rename(
            columns={"pts": "away_pts"}
        )
        home = home.merge(away, on="game_id", validate="one_to_one")
        home["date"] = pd.to_datetime(home["date"])
        y_home = home["pts"].to_numpy(dtype=float)
        y_away = home["away_pts"].to_numpy(dtype=float)
        if np.isnan(y_home).any() or np.isnan(y_away).any():
            raise InsufficientDataError("FINAL 결측 점수가 학습 데이터에 있습니다.")
        y_win = (y_home > y_away).astype(int)
        if len(np.unique(y_win)) != 2:
            raise InsufficientDataError("승패 두 클래스가 모두 필요합니다.")

        X = home[feature_cols].to_numpy(dtype=float)
        dates = np.array(sorted(home["date"].unique()))
        n_splits = int(self.training_config.get("n_splits", 5))
        if len(dates) <= n_splits:
            raise InsufficientDataError("고유 경기일 수가 Walk-Forward 분할보다 적습니다.")
        gap_days = max(0, int(self.training_config.get("gap_days", 0)))
        oof_home = np.full(len(home), np.nan)
        oof_away = np.full(len(home), np.nan)
        oof_prob = np.full(len(home), np.nan)
        used_folds = 0

        for tr_days, va_days in TimeSeriesSplit(n_splits=n_splits).split(dates):
            first_val = pd.Timestamp(dates[va_days[0]])
            train_dates = dates[tr_days]
            train_dates = train_dates[
                train_dates < np.datetime64(first_val - pd.Timedelta(days=gap_days))
            ]
            tr = np.flatnonzero(home["date"].isin(train_dates).to_numpy())
            va = np.flatnonzero(home["date"].isin(dates[va_days]).to_numpy())
            if len(tr) < 20 or len(va) == 0 or len(np.unique(y_win[tr])) != 2:
                continue
            assert home.loc[tr, "date"].max() < home.loc[va, "date"].min()
            common = dict(
                n_estimators=100, tree_method="hist", n_jobs=1,
                random_state=int(self.config.get("seed", 42))
            )
            reg_h = XGBRegressor(objective="reg:squarederror", **common)
            reg_a = XGBRegressor(objective="reg:squarederror", **common)
            clf = XGBClassifier(objective="binary:logistic", **common)
            reg_h.fit(X[tr], y_home[tr])
            reg_a.fit(X[tr], y_away[tr])
            clf.fit(X[tr], y_win[tr])
            oof_home[va] = reg_h.predict(X[va])
            oof_away[va] = reg_a.predict(X[va])
            oof_prob[va] = clf.predict_proba(X[va])[:, 1]
            used_folds += 1

        valid = np.isfinite(oof_home) & np.isfinite(oof_away) & np.isfinite(oof_prob)
        if valid.sum() < 20 or len(np.unique(y_win[valid])) != 2:
            raise InsufficientDataError("누수 없는 OOF 검증 표본이 부족합니다.")

        calibrator = CalibratedProbModel(
            method=self.training_config.get("calibration_method", "sigmoid")
        )
        calibrator.fit(oof_prob[valid], y_win[valid])
        resid_margin = (y_home[valid] - y_away[valid]) - (
            oof_home[valid] - oof_away[valid]
        )
        resid_total = (y_home[valid] + y_away[valid]) - (
            oof_home[valid] + oof_away[valid]
        )
        sigma_margin = float(np.std(resid_margin, ddof=1))
        sigma_total = float(np.std(resid_total, ddof=1))
        if min(sigma_margin, sigma_total) <= 0:
            raise InsufficientDataError("유효한 잔차 분산이 없습니다.")
        return {
            "sigma_margin": sigma_margin,
            "sigma_total": sigma_total,
            "calibrator": calibrator,
            "oof_metrics": ModelEvaluator.evaluate_classification(
                y_win[valid], calibrator.predict_proba(oof_prob[valid])
            ),
            "oof_n": int(valid.sum()),
            "n_folds_used": used_folds,
            "validation_mode": "RESEARCH_OOF_NOT_HOLDOUT",
        }

    @staticmethod
    def optimize_ensemble_weight(
        y_true: np.ndarray, p_clf: np.ndarray, p_reg_prob: np.ndarray
    ) -> float:
        """독립 META_B용. 이 OOF와 동일 레이블로 튜닝하면 승격 근거가 아니다."""
        best_w, best_loss = 0.5, float("inf")
        for w in np.linspace(0.0, 1.0, 21):
            blended = np.clip(
                w * p_clf + (1.0 - w) * p_reg_prob, 1e-15, 1.0 - 1e-15
            )
            loss = float(log_loss(y_true, blended))
            if loss < best_loss:
                best_w, best_loss = float(w), loss
        return best_w
