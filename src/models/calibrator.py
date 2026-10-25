"""확률 보정기 래퍼 모듈 (Platt Scaling & Isotonic Regression)."""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression

class CalibratedProbModel:
    """원시 분류기 확률을 시계열 OOF 기반 보정기로 보정하는 래퍼 클래스."""

    def __init__(self, method: str = "sigmoid"):
        self.method = method.lower()
        self.calibrator = None

    def fit(self, raw_probs: np.ndarray, y_true: np.ndarray):
        p_clipped = np.clip(raw_probs, 1e-6, 1.0 - 1e-6)
        
        if self.method == "sigmoid":
            # Platt Scaling: logit을 입력으로 하는 LogisticRegression
            logits = np.log(p_clipped / (1.0 - p_clipped)).reshape(-1, 1)
            self.calibrator = LogisticRegression()
            self.calibrator.fit(logits, y_true)
        elif self.method == "isotonic":
            self.calibrator = IsotonicRegression(out_of_bounds="clip")
            self.calibrator.fit(p_clipped, y_true)
        else:
            raise ValueError(f"지원하지 않는 보정 방법입니다: {self.method}")

    def predict_proba(self, raw_probs: np.ndarray) -> np.ndarray:
        if self.calibrator is None:
            return raw_probs
        
        p_clipped = np.clip(raw_probs, 1e-6, 1.0 - 1e-6)
        if self.method == "sigmoid":
            logits = np.log(p_clipped / (1.0 - p_clipped)).reshape(-1, 1)
            return self.calibrator.predict_proba(logits)[:, 1]
        elif self.method == "isotonic":
            return self.calibrator.predict(p_clipped)
        return raw_probs
