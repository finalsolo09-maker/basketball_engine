# NBA V2.5.1 dev10 — free API staging (research only)

This connector reads BALLDONTLIE NBA free endpoints: teams, players, games. It never modifies the football or KBL databases, existing basketball production DB, P0 predictions, or model weights.

**Safety gate:** The workflow job only runs when this repository is **private**. This repository is currently **public**, so scheduled executions must remain skipped. Never commit an API key or provider raw data into a public repository.

Before any live run: (1) change repository visibility to private; (2) add GitHub Actions repository secret `BDL_API_KEY`; (3) merge the reviewed PR into default branch; (4) run Actions manually and check logs, original SHA-256 and SQLite integrity.

Free API usage is bounded at 5 requests/minute. Output is staging/research only, not prediction approval. No unapproved scraping of KBL, ESPN or NBA.com.

`python auto_nba_update.py daily` is a no-network dry run. `python auto_nba_update.py audit` checks candidate SQLite and raw response hashes. 
