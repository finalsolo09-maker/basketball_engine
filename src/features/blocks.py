"""개별 피처 공학 블록 구현 모듈."""

import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)

from src.features.base import FeatureBlock
from src.features.elo import EloCalculator
import logging

class ScheduleFeatureBlock(FeatureBlock):
    """일정 및 피로도 관련 피처 블록."""

    @property
    def columns(self) -> list[str]:
        return ["rest_days", "is_back_to_back", "games_last_7d", "season_game_number"]

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = df.sort_values(["team", "date", "game_id"]).reset_index(drop=True)

        rest_default = self.config.get("rest_days_default", 3)
        rest_cap = self.config.get("rest_days_cap", 7)

        rest_days_list = []
        b2b_list = []
        games_7d_list = []
        season_game_num_list = []

        for team, group in df.groupby("team"):
            dates = group["date"].tolist()
            prev_date = None
            team_games = 0

            for i, d in enumerate(dates):
                team_games += 1
                season_game_num_list.append(team_games)

                if prev_date is None:
                    rest = rest_default
                else:
                    rest = (d - prev_date).days
                rest = min(rest, rest_cap)
                rest_days_list.append(rest)
                b2b_list.append(1 if rest <= 1 else 0)

                # 최근 7일 내 경기 수
                window_start = d - pd.Timedelta(days=7)
                count_7d = sum(1 for pd_dt in dates[:i+1] if window_start <= pd_dt <= d)
                games_7d_list.append(count_7d)

                prev_date = d

        df["rest_days"] = rest_days_list
        df["is_back_to_back"] = b2b_list
        df["games_last_7d"] = games_7d_list
        df["season_game_number"] = season_game_num_list
        return df


class RollingStatsFeatureBlock(FeatureBlock):
    """기본 박스스코어 및 효율성 지표 롤링/EWMA 피처 블록."""

    @property
    def columns(self) -> list[str]:
        cols = []
        windows = self.config.get("rolling_windows", [5, 10])
        metrics = ["pace", "ortg", "drtg", "net_rtg", "efg_pct", "tov_pct", "orb_pct", "ft_rate"]
        for m in metrics:
            for w in windows:
                cols.append(f"{m}_roll_{w}")
            cols.append(f"{m}_ewma")
        return cols

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        reg_mins = self.config.get("regulation_minutes", 48)
        k = self.config.get("shrinkage_k", 5)
        windows = self.config.get("rolling_windows", [5, 10])
        ewma_span = self.config.get("ewma_span", 10)
        league_priors = self.config.get("league_priors", {"pace": 99.0, "ortg": 114.0, "pts": 112.0})

        # 경기별 소스 계산
        team_poss = df["fga"] - df["oreb"] + df["tov"] + 0.44 * df["fta"]
        # 상대 행 결합을 위한 임시 테이블 구성
        # 각 game_id에서 홈/원정 상대방 정보를 매핑
        opp_df = df[["game_id", "team", "dreb", "team_poss"]].copy()
        opp_df.columns = ["game_id", "opponent", "opp_dreb", "opp_team_poss"]
        
        merged = pd.merge(df, opp_df, on=["game_id", "opponent"], how="left")
        merged["game_poss"] = (team_poss + merged["opp_team_poss"]) / 2
        merged["pace"] = reg_mins * merged["game_poss"] / merged["game_minutes"]
        merged["ortg"] = 100 * merged["pts"] / team_poss.replace(0, 1)
        merged["drtg"] = 100 * merged["opp_pts"] / merged["opp_team_poss"].replace(0, 1)
        merged["net_rtg"] = merged["ortg"] - merged["drtg"]
        merged["efg_pct"] = (merged["fgm"] + 0.5 * merged["fg3m"]) / merged["fga"].replace(0, 1)
        merged["tov_pct"] = merged["tov"] / (merged["fga"] + 0.44 * merged["fta"] + merged["tov"]).replace(0, 1)
        merged["orb_pct"] = merged["oreb"] / (merged["oreb"] + merged["opp_dreb"]).replace(0, 1)
        merged["ft_rate"] = merged["fta"] / merged["fga"].replace(0, 1)

        metrics = ["pace", "ortg", "drtg", "net_rtg", "efg_pct", "tov_pct", "orb_pct", "ft_rate"]
        
        sorted_df = merged.sort_values(["team", "season", "date", "game_id"]).reset_index(drop=True)

        transformed_groups = []
        prior_map = {} # 시즌별/팀별 직전 시즌 최종값 저장

        for (team, season), group in sorted_df.groupby(["team", "season"]):
            g = group.copy()
            # shift(1) 적용하여 데이터 누수 방지
            shifted = g[metrics].shift(1)

            # 시즌 내 경기 수 누적 (n)
            n_games = np.arange(len(g))

            # Prior 결정: 직전 시즌 최종값 또는 리그 프리어
            prior_val = {}
            for m in metrics:
                default_prior = league_priors.get(m, league_priors.get("ortg", 100.0))
                prior_val[m] = prior_map.get((team, m), default_prior)

            for w in windows:
                for m in metrics:
                    roll_col = shifted[m].rolling(w, min_periods=1).mean()
                    # 슈링크리지 보간: n / (n + k) * current + k / (n + k) * prior
                    shrinked = (n_games / (n_games + k)) * roll_col + (k / (n_games + k)) * prior_val[m]
                    g[f"{m}_roll_{w}"] = shrinked.fillna(prior_val[m])

            for m in metrics:
                ewma_col = shifted[m].ewm(span=ewma_span, min_periods=1).mean()
                shrinked_ewma = (n_games / (n_games + k)) * ewma_col + (k / (n_games + k)) * prior_val[m]
                g[f"{m}_ewma"] = shrinked_ewma.fillna(prior_val[m])

            # 현재 시즌 마지막 값을 다음 시즌 prior로 저장하기 위해 기록
            for m in metrics:
                if not g[m].dropna().empty:
                    prior_map[(team, m)] = g[m].iloc[-1]

            transformed_groups.append(g)

        result_df = pd.concat(transformed_groups).sort_values("date").reset_index(drop=True)
        return result_df


class MatchupFeatureBlock(FeatureBlock):
    """매치업 및 예상 득점 기반 피처 블록."""

    @property
    def columns(self) -> list[str]:
        return ["matchup_ortg_diff", "matchup_drtg_diff", "expected_pace", "naive_home_pts"]

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # 홈/원정 매치업 피처 계산을 위해 홈 행 기준 상대방 값을 가져옴
        # 이미 롤링 피처가 계산되어 있다고 가정
        return df
