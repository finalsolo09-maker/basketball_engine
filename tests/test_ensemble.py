"""4단계 앙상블 수학 및 O/U 확률 테스트."""

import pytest
import numpy as np
from src.models.ensemble import EnsemblePredictor

def test_ensemble_math():
    # w=1이면 P_clf, w=0이면 P_reg와 동일한지 확인
    p_clf = 0.7
    p_reg = 0.4
    
    assert EnsemblePredictor.combine_probabilities(p_clf, p_reg, w=1.0) == p_clf
    assert EnsemblePredictor.combine_probabilities(p_clf, p_reg, w=0.0) == p_reg

def test_ou_prob():
    mu_total = 220.0
    sigma_total = 10.0
    ou_line = 220.5
    
    res = EnsemblePredictor.calculate_over_under(mu_total, sigma_total, ou_line)
    assert "over_prob" in res
    assert "under_prob" in res
    assert abs((res["over_prob"] + res["under_prob"]) - 1.0) < 1e-5
