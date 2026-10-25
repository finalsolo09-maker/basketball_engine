"""엔드투엔드 스모크 테스트 (학습 -> 추론 전체 흐름 검증)."""

import subprocess
import sys
from pathlib import Path

def test_e2e_pipeline():
    # 1. 학습 실행 테스트
    train_res = subprocess.run([
        sys.executable, "main.py", "train", "--league", "KBL"
    ], capture_output=True, text=True)
    assert train_res.returncode == 0, f"학습 실패: {train_res.stderr}"

    # 2. 추론 실행 테스트
    predict_res = subprocess.run([
        sys.executable, "main.py", "predict",
        "--league", "KBL",
        "--home", "KBL_Team_00",
        "--away", "KBL_Team_01",
        "--date", "2024-02-01",
        "--ou", "165.5"
    ], capture_output=True, text=True)
    assert predict_res.returncode == 0, f"추론 실패: {predict_res.stderr}"
    assert "home_expected_pts" in predict_res.stdout
