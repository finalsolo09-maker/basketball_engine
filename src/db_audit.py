"""SQLite read-only 무결성 감사. 원본 DB를 수정하지 않는다."""

import json
import sqlite3
from pathlib import Path


REQUIRED_TABLES = (
    "fixtures", "source_game_keys", "fixture_events", "predictions",
    "ou_queries", "result_revisions", "audits", "eligibility_events",
    "promotion_events", "hash_chain_heads", "schema_version",
)


def audit_database(db_path: str | Path) -> dict:
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {path}")
    report = {
        "database": str(path),
        "integrity": "UNKNOWN",
        "foreign_keys": "UNKNOWN",
        "missing_tables": [],
        "duplicate_live_p0": None,
        "warnings": [],
        "status": "UNVERIFIED",
    }
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchall()
        report["integrity"] = "OK" if integrity == [("ok",)] else "FAIL"
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        report["foreign_keys"] = "OK" if not violations else "FAIL"
        report["foreign_key_violations"] = len(violations)
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        report["missing_tables"] = sorted(set(REQUIRED_TABLES) - tables)
        if "predictions" in tables:
            cols = {
                row[1] for row in conn.execute("PRAGMA table_info(predictions)")
            }
            if {"fixture_uid", "namespace", "revision"}.issubset(cols):
                sql = """
                    SELECT fixture_uid, COUNT(*) AS n
                    FROM predictions
                    WHERE namespace='live' AND revision=0
                    GROUP BY fixture_uid
                    HAVING COUNT(*) > 1
                """
                report["duplicate_live_p0"] = len(conn.execute(sql).fetchall())
            else:
                report["warnings"].append("P0 중복 점검용 컬럼 누락")
        else:
            report["warnings"].append("predictions 원장이 없습니다.")
        if report["integrity"] != "OK" or report["foreign_keys"] != "OK":
            report["status"] = "FAIL"
        elif report["duplicate_live_p0"] and report["duplicate_live_p0"] > 0:
            report["status"] = "FAIL"
        elif report["missing_tables"] or report["duplicate_live_p0"] is None:
            report["status"] = "BLOCKED_INCOMPLETE_SCHEMA"
        else:
            # DB 자체가 정상이어도 시간 누수·결과 근거·체인 검증은 별도 필요
            report["status"] = "STRUCTURAL_CHECK_PASSED"
            report["warnings"].append(
                "append-only 트리거, 해시체인, as-of 시각은 별도 감사 필요"
            )
        return report
    finally:
        conn.close()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="NBA/KBL SQLite 읽기 전용 점검")
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    print(json.dumps(audit_database(args.db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
