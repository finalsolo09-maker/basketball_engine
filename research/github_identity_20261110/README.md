# GitHub NBA ID crosswalk (2026-11-10)

Source: [swar/nba_api static data.py](https://github.com/swar/nba_api/blob/e077ba5fd381f50bf97c3e834f7eedf56a9c5f52/src/nba_api/stats/library/data.py) at commit `e077ba5fd381f50bf97c3e834f7eedf56a9c5f52`, GitHub blob SHA `a025cc1691419adb41884384226278de387675f6`. Its internal header states `Data last updated: Oct, 21 2026`.

NBA static IDs link the name to an NBA numeric identifier. They **do not verify the player's 2026–27 team roster, date of trade, injury, registration, original publication time, license to use game statistics, or pregame feature eligibility**. For safety all crosswalk entries set `team_2026_27_verified=false`, `pregame_asof_verified=false`, `model_use_approved=false`.

One duplicate full name, Brandon Williams, was disambiguated with [NBA official GSW profile](https://www.nba.com/player/1630314/brandon-williams); the unrelated historical same-name ID must not be auto used.

Use this candidate mapping to join *identity only* into a new SQLite shadow table without updating the old live P0, `player_inputs`, `asof_player_season_final`, or promoted model. Missing or conflict rows fail closed. When new official roster-by-season snapshot and published time is obtained, append a new independent evidence event rather than retroactively approving these rows.

The KBL crawler source `eagle0526/Basketball-League-Crawler` currently contains only notebook & README; no validated current 2026–27 roster file was imported. KBL 2026–27 foreign-player substitution rules can be consulted at https://kbl.or.kr/rule/player but remain research context pending pregame verification and model validation.
