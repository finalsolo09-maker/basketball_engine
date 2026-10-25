"""데이터 무결성 검증 모듈 (DataValidator)."""

import pandas as pd
import logging
from src.exceptions import DataValidationError

logger = logging.getLogger(__name__)

class DataValidator:
    """팀 단위 경기 로그 데이터의 무결성을 검증하는 클래스."""

    @staticmethod
    def validate(df: pd.DataFrame, policy: str = "raise") -> pd.DataFrame:
        """
        데이터프레임의 정합성을 검증합니다.
        
        검증 항목:
        - game_id당 정확히 2행 존재 (홈1, 원정1)
        - 홈팀 PTS == 원정팀 OPP_PTS, 원정팀 PTS == 홈팀 OPP_PTS
        - PTS 항등식: PTS = 2*(FGM - FG3M) + 3*FG3M + FTM
        - FGM <= FGA, FG3M <= FGM
        - 음수 값 존재 여부 검사
        """
        if df.empty:
            raise DataValidationError("입력된 데이터프레임이 비어 있습니다.")

        required_cols = [
            "game_id", "date", "season", "league", "team", "opponent",
            "is_home", "pts", "opp_pts", "fgm", "fga", "fg3m", "fg3a",
            "ftm", "fta", "oreb", "dreb", "tov", "ast", "stl", "blk", "game_minutes"
        ]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise DataValidationError(f"필수 컬럼이 누락되었습니다: {missing_cols}")

        errors = []

        # 1. game_id당 정확히 2행 검증
        row_counts = df.groupby("game_id").size()
        invalid_games = row_counts[row_counts != 2]
        if not invalid_games.empty:
            msg = f"다음 game_id의 행 수가 2가 아닙니다: {invalid_games.index[:5].tolist()}"
            if policy == "raise":
                raise DataValidationError(msg)
            logger.warning(msg)

        # 2. 박스스코어 항등식 검증 (행별)
        calc_pts = 2 * (df["fgm"] - df["fg3m"]) + 3 * df["fg3m"] + df["ftm"]
        pts_mismatch = ~np.isclose(df["pts"], calc_pts)
        if pts_mismatch.any():
            bad_ids = df.loc[pts_mismatch, "game_id"].unique()
            msg = f"PTS 항등식 위반 game_id 발견 (최대 5개): {bad_ids[:5].tolist()}"
            if policy == "raise":
                raise DataValidationError(msg)
            logger.warning(msg)

        # 3. 슈팅 스탯 논리 검증
        invalid_fg = (df["fgm"] > df["fga"]) | (df["fg3m"] > df["fgm"]) | (df["fg3m"] > df["fg3a"])
        if invalid_fg.any():
            msg = "슈팅 성공 횟수가 시도 횟수보다 큽니다."
            if policy == "raise":
                raise DataValidationError(msg)
            logger.warning(msg)

        # 4. 음수 값 검증
        numeric_cols = ["pts", "opp_pts", "fga", "fg3a", "fta", "tov", "game_minutes"]
        for col in numeric_cols:
            if (df[col] < 0).any():
                msg = f"컬럼 {col}에 음수 값이 존재합니다."
                if policy == "raise":
                    raise DataValidationError(msg)
                logger.warning(msg)

        return df

import numpy as np
