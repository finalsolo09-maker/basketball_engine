"""파이프라인 테스트에만 사용하는 합성 점수/박스스코어.

생성된 데이터는 실제 NBA/KBL 경기 실측값이나 실전 성능의 근거가 아니다.
"""

import numpy as np
import pandas as pd


class SampleDataGenerator:
    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def _stat_line(self, pts: int, pace: float) -> dict:
        """득점 항등식과 슈팅 부분집합 제약을 지키는 합성 기록."""
        fga = max(48, int(round(pace * 0.91)))
        fg3a = int(round(fga * 0.37))
        fg3m = min(fg3a, max(1, int(round(fg3a * 0.34))))
        ftm = min(42, max(6, int(round(pts * 0.19))))
        if (pts - 3 * fg3m - ftm) % 2:
            ftm += 1
        fg2m = max(0, (pts - 3 * fg3m - ftm) // 2)
        if fg2m > fga - fg3a:
            fga = fg2m + fg3a + 8
        fgm = fg2m + fg3m
        ftm = pts - 2 * fg2m - 3 * fg3m
        fta = max(ftm, int(round(ftm / 0.76)))
        oreb = max(0, int(round((fga - fgm) * 0.28)))
        dreb = max(0, int(round(pace * 0.34)))
        tov = int(round(pace * 0.13))
        return dict(
            fgm=fgm, fga=fga, fg3m=fg3m, fg3a=fg3a,
            ftm=ftm, fta=fta, oreb=oreb, dreb=dreb,
            tov=tov, ast=int(round(fgm * 0.59)),
            stl=max(1, int(round(pace * 0.06))), blk=4,
        )

    def generate(
        self, league: str = "NBA", n_seasons: int = 2
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if league not in {"NBA", "KBL"}:
            raise ValueError("NBA와 KBL 합성 경기만 지원합니다.")
        num_teams = 30 if league == "NBA" else 10
        games_per_team = 82 if league == "NBA" else 54
        reg_mins = 48 if league == "NBA" else 40
        avg_ortg = 114.0 if league == "NBA" else 108.0
        avg_pace = 99.0 if league == "NBA" else 72.0
        teams = [f"{league}_Team_{i:02d}" for i in range(num_teams)]
        records, oracle = [], []
        base_date = pd.Timestamp("2023-10-01")

        for season in range(1, n_seasons + 1):
            season_str = f"20{22+season}-{23+season}"
            strength = {
                team: (
                    avg_ortg + self.rng.normal(0, 5),
                    avg_ortg + self.rng.normal(0, 5),
                    avg_pace + self.rng.normal(0, 3),
                )
                for team in teams
            }
            dates = pd.date_range(
                base_date + pd.Timedelta(days=(season - 1) * 365),
                periods=games_per_team, freq="3D"
            )
            for date in dates:
                shuffled = self.rng.permutation(teams)
                for i in range(0, num_teams, 2):
                    home, away = shuffled[i], shuffled[i + 1]
                    game_id = f"{league}_{season_str}_{date:%Y%m%d}_{home}_{away}"
                    h_off, h_def, h_pace = strength[home]
                    a_off, a_def, a_pace = strength[away]
                    pace = max(45.0, (h_pace + a_pace) / 2 + self.rng.normal(0, 2))
                    home_eff = (h_off + 2 * avg_ortg - a_def) / 2
                    away_eff = (a_off + 2 * avg_ortg - h_def) / 2
                    mu_home = pace * home_eff / 100 + 2.6
                    mu_away = pace * away_eff / 100
                    h_pts = max(40, int(round(self.rng.normal(mu_home, 11))))
                    a_pts = max(40, int(round(self.rng.normal(mu_away, 11))))
                    ot = int(h_pts == a_pts)
                    if ot:
                        h_pts += 5
                        a_pts += 3
                    minutes = reg_mins + 5 * ot
                    for is_home, team, opponent, pts, opp_pts in (
                        (1, home, away, h_pts, a_pts),
                        (0, away, home, a_pts, h_pts),
                    ):
                        row = dict(
                            game_id=game_id, date=date, season=season_str,
                            league=league, game_type="regular",
                            team=team, opponent=opponent, is_home=is_home,
                            pts=pts, opp_pts=opp_pts, game_minutes=minutes,
                            overtime_count=ot,
                        )
                        row.update(self._stat_line(pts, pace))
                        records.append(row)
                    oracle.append(dict(
                        game_id=game_id, true_expected_margin=mu_home - mu_away,
                        # 합성 잠재 분포에서만 쓰는 근사치
                        true_home_win_prob=float(
                            1.0 / (1.0 + np.exp(-(mu_home - mu_away) / 16.0))
                        ),
                    ))
        return pd.DataFrame(records), pd.DataFrame(oracle)
