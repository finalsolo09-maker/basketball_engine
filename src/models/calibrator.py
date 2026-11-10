"""안전한 JSON 직렬화만 허용하는 확률 보정기."""

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit
from sklearn.isotonic import IsotonicRegression


class CalibratedProbModel:
    def __init__(self, method: str = "sigmoid"):
        self.method = method.lower()
        if self.method not in {"sigmoid", "isotonic"}:
            raise ValueError("지원하지 않는 보정 방법")
        self.calibrator = None
        self.parameters = None

    def fit(self, raw_probs: np.ndarray, y_true: np.ndarray):
        p = np.clip(np.asarray(raw_probs, dtype=float), 1e-6, 1.0 - 1e-6)
        y = np.asarray(y_true, dtype=int)
        if len(p) < 10 or not np.isfinite(p).all() or set(np.unique(y)) != {0, 1}:
            raise ValueError("확률 보정에는 10개 이상의 양 클래스 관측값이 필요합니다.")
        if self.method == "sigmoid":
            x = logit(p)
            def objective(params):
                probs = np.clip(expit(params[0] * x + params[1]), 1e-9, 1 - 1e-9)
                return float(-np.mean(y * np.log(probs) + (1 - y) * np.log1p(-probs)))
            res = minimize(objective, x0=[1.0, 0.0], method="L-BFGS-B",
                           bounds=[(1e-3, None), (None, None)])
            if not res.success or not np.isfinite(res.x).all():
                raise ValueError("Platt 보정 최적화 실패")
            self.parameters = {"a": float(res.x[0]), "b": float(res.x[1])}
        else:
            model = IsotonicRegression(out_of_bounds="clip")
            model.fit(p, y)
            self.parameters = {
                "x": model.X_thresholds_.astype(float).tolist(),
                "y": model.y_thresholds_.astype(float).tolist(),
            }
        # 기존 코드의 학습 여부 검사와 호환
        self.calibrator = True
        return self

    def predict_proba(self, raw_probs: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(raw_probs, dtype=float), 1e-6, 1.0 - 1e-6)
        if self.parameters is None:
            raise ValueError("보정 파라미터를 불러오거나 학습해야 합니다.")
        if self.method == "sigmoid":
            return expit(self.parameters["a"] * logit(p) + self.parameters["b"])
        return np.interp(p, self.parameters["x"], self.parameters["y"])

    def to_dict(self) -> dict:
        if self.parameters is None:
            raise ValueError("미학습 보정기는 저장할 수 없습니다.")
        return {"schema_version": 1, "method": self.method, "parameters": self.parameters}

    @classmethod
    def from_dict(cls, payload: dict) -> "CalibratedProbModel":
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("지원하지 않는 보정기 JSON 스키마")
        obj = cls(payload.get("method", ""))
        p = payload.get("parameters")
        if not isinstance(p, dict):
            raise ValueError("보정기 파라미터 누락")
        if obj.method == "sigmoid":
            a, b = float(p["a"]), float(p["b"])
            if not np.isfinite([a, b]).all() or a <= 0:
                raise ValueError("보정기 계수가 잘못되었습니다.")
            obj.parameters = {"a": a, "b": b}
        else:
            x, y = np.asarray(p["x"], dtype=float), np.asarray(p["y"], dtype=float)
            if (len(x) < 2 or len(x) != len(y)
                or not np.isfinite(x).all() or not np.isfinite(y).all()
                or not np.all(np.diff(x) > 0)
                or not np.all(np.diff(y) >= 0)
                or not np.all((y >= 0) & (y <= 1))):
                raise ValueError("Isotonic 보정기 분포가 잘못되었습니다.")
            obj.parameters = {"x": x.tolist(), "y": y.tolist()}
        obj.calibrator = True
        return obj
