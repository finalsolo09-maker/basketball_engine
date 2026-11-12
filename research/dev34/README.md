# dev34 retrospective NBA/KBL audit (2026-11-12)

Status: **RESEARCH_AUDIT_ONLY — NOT PRODUCTION APPROVED**

- Original dev33 private SQLite is preserved. The dev34 candidate was created from the user's dev33 research DB with 140 source tables and 165 triggers unchanged. The new candidate has 150 tables, 185 triggers, and zero FK violations, and passed 42 targeted local tests.
- 8 NBA finals crosschecked on 2026-11-12 KST, 8 P1 score picks settled (winner 3/8; margin MAE 12.125; total MAE 12.875). P3 expert picks on Utah/Orlando and Houston/Golden State 2/2; sample too small to approve any model weights.
- Second Portland/OKC fixture (native game ID `0022600226`) has a single postgame recap showing POR 118:108 OKC versus a stale live scoreboard showing POR 88:85 near Q4, so it remains **PROVISIONAL, NOT SETTLED/NOT TRAINING** pending official game ID final recheck.
- New Orleans/Nets first-half source contradiction: NBA Pelicans and AP/CBS: NOP 66–BKN 83; one syndicated report printed 55–83. Store both and use authoritative team+box score.
- 2026-11-12 KBL KOGAS/SONO 19:00 was not started at the 14:49 KST snapshot and 14 dev33 2026-11-14/15 future forecasts remain untouched.
- A restored player must not be counted as out without injury snapshot time; a player injured **during** the match must not be tagged as missing pregame information. Preserve all `POSTGAME_ONLY` events for future fixture research, not the same match.
- Use `audit_gate.py` to quarantine source conflicts, incomplete games, malformed halves, retrospective leaks and unapproved production promotion. 
- Scoring model remains dev30 **RESEARCH_ACTIVE**. No new weights were fit; no production pointer was changed; P0/P1/P3 files retain SHA-256.

The full private SQLite, exported source evidence, original audit hashes, scorecards, tests and report are in the user's private Library path:
`/NBA·KBL 예측 엔진/Candidates/NBA_KBL_DEV34_POSTGAME_AUDIT_ENGINE_DB_20261112.zip`.
This public repo must never receive the private SQLite, personal data or original frozen predictions.
