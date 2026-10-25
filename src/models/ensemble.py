"""앙상블, 일관성 정책 및 O/U 확률 계산 모듈."""

import numpy as np
from scipy.stats import norm

class EnsemblePredictor:
    """분류 확률과 회귀 기반 정규분포 확률을 결합하고 O/U를 계산하는 클래스."""

    @staticmethod
    def calc_regression_win_prob(margin_pred: float, sigma_margin: float) -> float:
        """회귀 마진 예측값과 잔차 표준편차를 바탕으로 정규분포 누적 분포 함수(CDF)로 승리 확률 산출."""
        sigma = max(sigma_margin, 1e-5)
        return float(norm.cdf(margin_pred / sigma))

    @staticmethod
    def combine_probabilities(p_clf: float, p_reg: float, w: float) -> float:
        """분류 확률과 회귀 확률을 앙상블 가중치 w로 결합합니다."""
        return float(w * p_clf + (1.0 - w) * p_reg)

    @staticmethod
    def calculate_over_under(mu_total: float, sigma_total: float, ou_line: float) -> dict:
        """총점 정규분포를 기반으로 Over/Under/Push 확률을 계산합니다."""
        sigma = max(sigma_total, 1e-5)
        # ou_line이 소수점(.5)인지 정수인지 판별
        is_half = (ou_line % 1 != 0)

        if is_half:
            over_prob = float(1.0 - norm.cdf((ou_line - mu_total) / sigma))
            return {
                "over_prob": over_prob,
                "under_prob": 1.0 - over_prob
            }
        else:
            # 정수 라인인 경우 push(무승부) 확률 고려
            over_prob = float(1.0 - norm.cdf((ou_line + 0.5 - mu_total) / sigma))
            under_prob = float(norm.cdf((ou_line - 0.5 - mu_total) / sigma))
            push_prob = float(1.0 - (over_prob + under_prob))
            return {
                "over_prob": over_prob,
                "under_prob": under_prob,
                "push_prob": max(0.0, push_prob)
            }
