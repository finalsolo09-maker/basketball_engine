"""Read-only dev30 NBA/KBL model gate. For a local authorized user DB only.

The model artifact directory belongs to the user; no API keys or private data stored here.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(db_path: str, artifacts_dir: str, league: str,
           requested_scope: str = "RESEARCH_REPLAY") -> dict:
    if requested_scope != "RESEARCH_REPLAY":
        raise PermissionError("Live P0/production inference is blocked: no verified FULL_ASOF and roster cutoff.")
    if league not in ("NBA", "KBL"):
        raise ValueError("Unsupported league")
    db = Path(db_path).expanduser().resolve()
    root = Path(artifacts_dir).expanduser().resolve()
    if not db.is_file() or not root.is_dir():
        raise FileNotFoundError("Authenticated DB and artifact files are required")
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as con:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity failed")
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign key violations")
        rows = con.execute(
            """SELECT artifact_name,artifact_sha256,feature_schema_sha256,feature_count,
                      training_cutoff,evaluation_games,production_approved,full_asof_approved
               FROM dev30_model_registry
               WHERE league=? AND task='SCORE_REGRESSION' AND status='RESEARCH_ACTIVE'""",
            (league,),
        ).fetchall()
        if len(rows) != 1 or rows[0][6] != 0 or rows[0][7] != 0:
            raise ValueError("Research pointer is not uniquely valid or is falsely approved")
        name, digest, schema_digest, count, cutoff, n, *_ = rows[0]
        p = root / name
        if p.parent.resolve() != root or not p.is_file() or sha256(p) != digest:
            raise ValueError("Invalid file or SHA256")
        model = json.loads(p.read_text(encoding="utf-8"))
        names = model["features"]
        source = json.dumps(names, ensure_ascii=False, separators=(",", ":")).encode()
        if hashlib.sha256(source).hexdigest() != schema_digest or len(names) != count:
            raise ValueError("Feature schema mismatch")
        if model.get("status") != "RESEARCH_DATE_ONLY_NOT_LIVE":
            raise ValueError("Unapproved model state")
        if model.get("train_cutoff_exclusive") != cutoff:
            raise ValueError("Training cutoff mismatch")
        return {
            "league": league, "artifact": str(p),
            "artifact_sha256": digest, "features": count,
            "historical_holdout_games": n, "status": "RESEARCH_REPLAY_ONLY",
            "production_eligible": False,
        }
