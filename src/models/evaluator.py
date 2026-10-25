"""성능 평가, 잔차 진단 및 리포트 생성 모듈."""

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, accuracy_score, roc_auc_score, log_loss, brier_score_loss

class ModelEvaluator:
    """회귀 및 분류 모델의 성능을 평가하고 잔차 진단 리포트를 생성하는 클래스."""

    @staticmethod
    def evaluate_regression(y_true: np.ndarray, y_pred: np.ndarray, name: str = "Reg") -> dict:
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        return {f"{name}_MAE": mae, f"{name}_RMSE": rmse}

    @staticmethod
    def evaluate_classification(y_true: np.ndarray, y_prob: np.ndarray) -> dict:
        y_pred = (y_prob >= 0.5).astype(int)
        acc = accuracy_score(y_true, y_pred)
        try:
            auc = roc_auc_score(y_true, y_prob)
        except Exception:
            auc = 0.5
        ll = log_loss(y_true, np.clip(y_prob, 1e-15, 1.0 - 1e-15))
        brier = brier_score_loss(y_true, y_prob)
        return {"Accuracy": acc, "ROC-AUC": auc, "LogLoss": ll, "Brier": brier}

    @staticmethod
    def residual_diagnostics(residuals: np.ndarray) -> dict:
        mean_res = float(np.mean(residuals))
        std_res = float(np.std(residuals))
        # 1-sigma 커버리지 비율
        cov_1sigma = float(np.mean(np.abs(residuals) <= std_res))
        return {
            "bias": mean_res,
            "std": std_res,
            "coverage_1sigma": cov_1sigma
        }
