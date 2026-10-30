#!/usr/bin/env python3
"""NBA V2.5.1-dev10 BALLDONTLIE free API staging adapter.

No writes to the existing engine database. No historical as-of claims.
Raw payloads and observations are append-only, with provenance.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid

import requests

BASE_URL = "https://api.balldontlie.io"
API_KEY_NAMES = ("BDL_API_KEY", "BALLDONTLIE_API_KEY")
FREE_PATHS = {"teams": "/v1/teams", "players": "/v1/players", "games": "/v1/games"}
MIN_GAP_SECONDS = 12.5
MAX_PAGE_BYTES = 5_000_000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class GateError(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def api_key_from_environment() -> str:
    vals = [os.environ[k].strip() for k in API_KEY_NAMES if os.environ.get(k, "").strip()]
    if not vals:
        raise GateError("API_KEY_MISSING: PowerShell 환경변수 BDL_API_KEY를 먼저 설정하세요.")
    if len(set(vals)) != 1:
        raise GateError("API_KEY_CONFLICT: 두 환경변수의 값이 서로 다릅니다.")
    if any(c in vals[0] for c in "\r\n"):
        raise GateError("API_KEY_INVALID: 줄바꿈이 포함되어 있습니다.")
    return vals[0]


def validate_date(value: str) -> str:
    if not DATE_RE.fullmatch(value):
        raise GateError("DATE_INVALID: YYYY-MM-DD 형식이 아닙니다.")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise GateError("DATE_INVALID: 잘못된 날짜입니다.") from exc
    return value


def params_for(kind: str, day: str | None = None, season: int | None = None,
               per_page: int = 100) -> dict:
    if kind not in FREE_PATHS:
        raise GateError("ENDPOINT_NOT_FREE_OR_UNKNOWN")
    if not 1 <= per_page <= 100:
        raise GateError("PER_PAGE_OUT_OF_RANGE")
    if (day or season is not None) and kind != "games":
        raise GateError("FILTER_ONLY_FOR_GAMES")
    p = {"per_page": per_page} if kind != "teams" else {}
    if day:
        p["dates[]"] = validate_date(day)
    if season is not None:
        if not 1946 <= season <= 2100:
            raise GateError("SEASON_OUT_OF_RANGE")
        p["seasons[]"] = season
    return p


def safe_integer(value, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GateError(f"{name}_INVALID")
    return value


def record_quality(kind: str, item: object) -> tuple[str, list[str], dict]:
    errors: list[str] = []
    normalized: dict = {}
    if not isinstance(item, dict):
        return "HOLD", ["NOT_OBJECT"], normalized
    rid = item.get("id")
    try:
        rid = safe_integer(rid, "id", 1)
        normalized["source_id"] = rid
    except GateError:
        errors.append("INVALID_ID")
    if kind == "teams":
        for field in ("full_name", "abbreviation"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append("MISSING_" + field.upper())
        normalized.update({"name": item.get("full_name"), "abbreviation": item.get("abbreviation")})
    elif kind == "players":
        for field in ("first_name", "last_name"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append("MISSING_" + field.upper())
        team = item.get("team")
        team_id = team.get("id") if isinstance(team, dict) else item.get("team_id")
        if team_id is not None and (not isinstance(team_id, int) or isinstance(team_id, bool) or team_id <= 0):
            errors.append("INVALID_TEAM_ID")
        normalized.update({"name": (str(item.get("first_name") or "") + " " + str(item.get("last_name") or "")).strip(),
                           "team_id": team_id, "position": item.get("position")})
    elif kind == "games":
        try:
            normalized["game_date"] = validate_date(item.get("date", ""))
        except (TypeError, GateError):
            errors.append("INVALID_GAME_DATE")
        try:
            normalized["season"] = safe_integer(item.get("season"), "season", 1946)
        except GateError:
            errors.append("INVALID_SEASON")
        home = item.get("home_team")
        away = item.get("visitor_team")
        hid = home.get("id") if isinstance(home, dict) else item.get("home_team_id")
        aid = away.get("id") if isinstance(away, dict) else item.get("visitor_team_id")
        if not isinstance(hid, int) or isinstance(hid, bool) or hid < 1:
            errors.append("INVALID_HOME_TEAM")
        if not isinstance(aid, int) or isinstance(aid, bool) or aid < 1 or aid == hid:
            errors.append("INVALID_AWAY_TEAM")
        normalized.update({"home_team_id": hid, "away_team_id": aid})
        state = item.get("status_state", "unknown")
        normalized["status_state"] = state
        if state not in {"scheduled", "in_progress", "final", "postponed", "canceled", "delayed", "suspended", "abandoned", "unknown"}:
            errors.append("UNKNOWN_LIFECYCLE")
        homepts = item.get("home_team_score")
        awaypts = item.get("visitor_team_score")
        normalized.update({"home_score": homepts, "away_score": awaypts,
                           "scheduled_start_utc": item.get("datetime"),
                           "season_type": "playoffs" if item.get("postseason") else "not_playoffs"})
        if state == "final":
            for n, value in (("HOME_SCORE", homepts), ("AWAY_SCORE", awaypts)):
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append("INVALID_FINAL_" + n)
            if isinstance(homepts, int) and isinstance(awaypts, int) and homepts == awaypts:
                errors.append("FINAL_TIE_NOT_SUPPORTED")
        if state == "unknown":
            errors.append("STATUS_UNVERIFIED")
    else:
        errors.append("UNSUPPORTED_KIND")
    return ("HOLD" if errors else "VALID"), errors, normalized


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS bdl_runs (
      run_id TEXT PRIMARY KEY, started_at_utc TEXT NOT NULL,
      kind TEXT NOT NULL CHECK(kind IN ('teams','players','games')),
      request_json TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode='LIVE_API'),
      grade TEXT NOT NULL CHECK(grade='OBSERVED_NOT_FULL_ASOF')
    );
    CREATE TABLE IF NOT EXISTS bdl_pages (
      page_sha256 TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES bdl_runs(run_id),
      page_number INTEGER NOT NULL, endpoint TEXT NOT NULL, params_json TEXT NOT NULL,
      observed_at_utc TEXT NOT NULL, response_sha256 TEXT NOT NULL,
      raw_rel_path TEXT NOT NULL, record_count INTEGER NOT NULL, next_cursor TEXT,
      UNIQUE(run_id,page_number)
    );
    CREATE TABLE IF NOT EXISTS bdl_observations (
      obs_id TEXT PRIMARY KEY, page_sha256 TEXT NOT NULL REFERENCES bdl_pages(page_sha256),
      kind TEXT NOT NULL, source_id INTEGER, record_sha256 TEXT NOT NULL,
      validation_state TEXT NOT NULL CHECK(validation_state IN ('VALID','HOLD')),
      issues_json TEXT NOT NULL, normalized_json TEXT NOT NULL, raw_json TEXT NOT NULL,
      observed_at_utc TEXT NOT NULL, asof_grade TEXT NOT NULL
       CHECK(asof_grade='DATE_ONLY_REPLAY_NOT_FULL_ASOF'),
      official_fixture_uid TEXT, approved_for_live INTEGER NOT NULL DEFAULT 0 CHECK(approved_for_live=0),
      approved_for_model_training INTEGER NOT NULL DEFAULT 0 CHECK(approved_for_model_training=0)
    );
    CREATE INDEX IF NOT EXISTS idx_bdl_obs_lookup ON bdl_observations(kind,source_id,observed_at_utc);
    CREATE TABLE IF NOT EXISTS bdl_rejections (
      reject_id TEXT PRIMARY KEY, page_sha256 TEXT NOT NULL REFERENCES bdl_pages(page_sha256),
      record_index INTEGER NOT NULL, reason_json TEXT NOT NULL,
      observed_at_utc TEXT NOT NULL
    );
    """)
    for t in ("bdl_runs", "bdl_pages", "bdl_observations", "bdl_rejections"):
        conn.execute(f"CREATE TRIGGER IF NOT EXISTS {t}_no_update BEFORE UPDATE ON {t} BEGIN SELECT RAISE(ABORT,'append_only'); END")
        conn.execute(f"CREATE TRIGGER IF NOT EXISTS {t}_no_delete BEFORE DELETE ON {t} BEGIN SELECT RAISE(ABORT,'append_only'); END")
    conn.commit()
    return conn


def persist_page(conn: sqlite3.Connection, workdir: Path, run_id: str, kind: str,
                 page_number: int, params: dict, response_bytes: bytes,
                 observed_at: str) -> dict:
    if not response_bytes or len(response_bytes) > MAX_PAGE_BYTES:
        raise GateError("RESPONSE_EMPTY_OR_OVERSIZE")
    try:
        payload = json.loads(response_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GateError("RESPONSE_NOT_JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise GateError("RESPONSE_SCHEMA_INVALID")
    next_cursor = payload.get("meta", {}).get("next_cursor") if isinstance(payload.get("meta", {}), dict) else None
    if next_cursor is not None and (isinstance(next_cursor, bool) or not isinstance(next_cursor, (str, int))):
        raise GateError("CURSOR_INVALID")
    if len(payload["data"]) > 100:
        raise GateError("TOO_MANY_ROWS_PER_PAGE")
    raw_hash = sha256(response_bytes)
    page_id = sha256(canonical([run_id, kind, page_number, raw_hash]))
    rawdir = workdir / "raw" / run_id
    rawdir.mkdir(parents=True, exist_ok=True)
    relative = Path("raw") / run_id / f"{kind}_{page_number:03d}_{raw_hash[:12]}.json"
    target = workdir / relative
    temp = target.with_suffix(".part")
    with temp.open("xb") as f:
        f.write(response_bytes)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, target)
    valid = held = 0
    with conn:
        conn.execute("""INSERT INTO bdl_pages VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     (page_id,run_id,page_number,FREE_PATHS[kind],json.dumps(params,ensure_ascii=False,sort_keys=True),
                      observed_at,raw_hash,relative.as_posix(),len(payload["data"]),
                      str(next_cursor) if next_cursor is not None else None))
        seen_on_page = set()
        for idx,item in enumerate(payload["data"]):
            state, issues, normalized = record_quality(kind,item)
            uid = normalized.get("source_id")
            if uid is not None and uid in seen_on_page:
                state = "HOLD"
                issues.append("DUPLICATE_ID_IN_PAGE")
            seen_on_page.add(uid)
            record_blob = canonical(item)
            conn.execute("""INSERT INTO bdl_observations (
              obs_id,page_sha256,kind,source_id,record_sha256,validation_state,issues_json,
              normalized_json,raw_json,observed_at_utc,asof_grade)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (sha256(canonical([page_id,idx])), page_id,kind,uid,sha256(record_blob),state,
               json.dumps(issues,ensure_ascii=False),json.dumps(normalized,ensure_ascii=False,sort_keys=True),
               record_blob.decode("utf-8"), observed_at,"DATE_ONLY_REPLAY_NOT_FULL_ASOF"))
            if state == "VALID": valid += 1
            else:
                held += 1
                conn.execute("INSERT INTO bdl_rejections VALUES(?,?,?,?,?)",
                             (uuid.uuid4().hex,page_id,idx,json.dumps(issues,ensure_ascii=False),observed_at))
    return {"page":page_number,"raw_sha256":raw_hash,"records":len(payload["data"]),"valid":valid,"held":held,"next_cursor":next_cursor}


@contextlib.contextmanager
def portable_lock(lockfile: Path, wait_seconds: float = 30):
    started = time.monotonic()
    while True:
        try:
            fd = os.open(str(lockfile),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.write(fd,str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic()-started >= wait_seconds:
                raise GateError(f"LOCKED: {lockfile} / 이전 프로세스 종료 여부를 확인하세요.")
            time.sleep(0.25)
    try:
        yield
    finally:
        lockfile.unlink(missing_ok=True)


def fetch_one(session: requests.Session, kind: str, params: dict, key: str,
              workdir: Path, minimum_gap: float = MIN_GAP_SECONDS) -> tuple[bytes,str]:
    # Across processes the lock covers both waiting and the request.
    with portable_lock(workdir/".bdl_api.lock"):
        stamp = workdir/".bdl_last_request.txt"
        if stamp.exists():
            try:
                delay = minimum_gap - (time.time() - float(stamp.read_text()))
            except ValueError:
                raise GateError("RATE_STATE_INVALID")
            if delay > 0:
                time.sleep(delay)
        stamp.write_text(str(time.time()),encoding="ascii")
        response = session.get(BASE_URL + FREE_PATHS[kind], params=params,
                               headers={"Authorization":key, "Accept":"application/json"},
                               timeout=30,allow_redirects=False)
        timestamp=now_utc()
    if response.status_code in (401,403):
        raise GateError(f"HTTP_{response.status_code}: 키 또는 요금제 접근권한 확인")
    if response.status_code == 429:
        raise GateError("HTTP_429: 요청 한도 초과. 자동 재시도하지 않았습니다.")
    if response.status_code != 200:
        raise GateError(f"HTTP_{response.status_code}: API 중단 (응답 본문과 키 비출력)")
    return response.content,timestamp


def collect(kind: str, workdir: Path, day: str | None, season: int | None,
            pages: int, per_page: int, execute: bool) -> dict:
    if pages < 1 or pages > 100:
        raise GateError("PAGES_OUT_OF_RANGE")
    params=params_for(kind,day,season,per_page)
    plan={"endpoint": FREE_PATHS[kind], "params":params,"max_pages":pages,
          "minimum_request_gap_seconds":MIN_GAP_SECONDS,
          "operating_db_modified":False,"mode":"LIVE_API" if execute else "DRY_RUN"}
    if not execute:
        return plan
    key=api_key_from_environment()
    workdir.mkdir(parents=True,exist_ok=True)
    con=init_db(workdir/"nba_bdl_free_staging.sqlite")
    run_id=uuid.uuid4().hex
    results=[]
    try:
        with con:
            con.execute("INSERT INTO bdl_runs VALUES (?,?,?,?,?,?)",
                        (run_id,now_utc(),kind,json.dumps(params,ensure_ascii=False,sort_keys=True),"LIVE_API","OBSERVED_NOT_FULL_ASOF"))
        cursor = None
        seen_cursors=set()
        with requests.Session() as session:
            for page in range(1,pages+1):
                current=dict(params)
                if cursor is not None:current["cursor"]=cursor
                content,stamp=fetch_one(session,kind,current,key,workdir)
                result=persist_page(con,workdir,run_id,kind,page,current,content,stamp)
                results.append(result)
                nxt=result["next_cursor"]
                if nxt is None:
                    break
                if str(nxt) in seen_cursors:
                    raise GateError("REPEATED_CURSOR_BLOCKED")
                seen_cursors.add(str(nxt))
                cursor=nxt
    finally:
        con.close()
    return {**plan,"run_id":run_id,"pages_saved":len(results),"results":results,
            "source_grade":"DATE_ONLY_REPLAY_NOT_FULL_ASOF", "model_promotion": "BLOCKED"}


def audit_engine(engine_path: Path) -> dict:
    if not engine_path.is_file():
        return {"status":"BLOCKED_ENGINE_DB_MISSING","path":str(engine_path)}
    digest=hashlib.sha256()
    with engine_path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            digest.update(chunk)
    with sqlite3.connect(f"file:{engine_path.resolve().as_posix()}?mode=ro",uri=True) as con:
        structural=con.execute("PRAGMA integrity_check").fetchall()
        fk=con.execute("PRAGMA foreign_key_check").fetchall()
        tables=con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return {"status":"PASS" if structural==[("ok",)] and not fk else "BLOCKED_INTEGRITY",
            "size_bytes":engine_path.stat().st_size,"sha256":digest.hexdigest(),
            "integrity":structural[:3],"foreign_key_violations":len(fk),
            "table_count":len(tables),"no_engine_writes":True,
            "runtime_compatibility":"NOT_TESTED"}


def staging_status(workdir: Path) -> dict:
    f=workdir/"nba_bdl_free_staging.sqlite"
    if not f.is_file():
        return {"status":"NO_STAGING_DB","live_api_rows":0}
    with sqlite3.connect(f"file:{f.resolve().as_posix()}?mode=ro",uri=True) as con:
        integrity=con.execute("PRAGMA integrity_check").fetchall()
        foreign=con.execute("PRAGMA foreign_key_check").fetchall()
        rows=con.execute("SELECT kind,validation_state,COUNT(*) FROM bdl_observations GROUP BY kind,validation_state").fetchall()
        count_pages=con.execute("SELECT COUNT(*) FROM bdl_pages").fetchone()[0]
    return {"status":"OK" if integrity==[("ok",)] and not foreign else "BLOCKED",
            "integrity_check":integrity[:3],"foreign_key_violations":len(foreign),
            "pages":count_pages,"by_kind_state":[list(t) for t in rows],
            "live_promotion":"NOT_APPROVED"}


def export_valid(workdir:Path, kind:str, out:Path)->dict:
    if kind not in FREE_PATHS: raise GateError("UNSUPPORTED_KIND")
    db=workdir/"nba_bdl_free_staging.sqlite"
    if not db.is_file():raise GateError("STAGING_DB_MISSING")
    # Export does not imply live eligibility; use late/replay research only.
    with sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro",uri=True) as con:
        rows=con.execute("""SELECT source_id,normalized_json,observed_at_utc,record_sha256,asof_grade
                              FROM bdl_observations WHERE kind=? AND validation_state='VALID'
                              ORDER BY observed_at_utc,obs_id""",(kind,)).fetchall()
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix(out.suffix+".tmp")
    with tmp.open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.writer(f)
        writer.writerow(["provider","provider_id","normalized_json","first_observed_at_utc",
                         "record_sha256","evidence_grade","live_approved","model_train_approved"])
        for rid,normalized,stamp,h,grade in rows:
            writer.writerow(["NBA_BALLDONTLIE",rid,normalized,stamp,h,grade,0,0])
    os.replace(tmp,out)
    return {"path":str(out),"exported_observations":len(rows),"live_approved":0,
            "model_train_approved":0,"fixture_mapping":"UNLINKED"}


def main() -> int:
    p=argparse.ArgumentParser(description="NBA V2.5.1 dev10 BALLDONTLIE free data adapter")
    p.add_argument("--workdir",type=Path,default=Path("bdl_free_staging"))
    sp=p.add_subparsers(dest="command",required=True)
    collect_p=sp.add_parser("collect")
    collect_p.add_argument("--kind",choices=list(FREE_PATHS),required=True)
    collect_p.add_argument("--date")
    collect_p.add_argument("--season",type=int)
    collect_p.add_argument("--pages",type=int,default=1)
    collect_p.add_argument("--per-page",type=int,default=100)
    collect_p.add_argument("--execute",action="store_true")
    sp.add_parser("status")
    ex=sp.add_parser("export")
    ex.add_argument("--kind",choices=list(FREE_PATHS),required=True)
    ex.add_argument("--out",type=Path,required=True)
    e=sp.add_parser("inspect-engine")
    e.add_argument("--db",type=Path,required=True)
    args=p.parse_args()
    try:
        if args.command=="collect":
            result=collect(args.kind,args.workdir,args.date,args.season,args.pages,args.per_page,args.execute)
        elif args.command=="status": result=staging_status(args.workdir)
        elif args.command=="export": result=export_valid(args.workdir,args.kind,args.out)
        else: result=audit_engine(args.db)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result.get("status") not in {"BLOCKED","BLOCKED_INTEGRITY","BLOCKED_ENGINE_DB_MISSING"} else 2
    except (GateError,sqlite3.Error,requests.RequestException,OSError) as exc:
        # Do not print request headers, response bodies, or API keys.
        if isinstance(exc,GateError):msg=str(exc)
        elif isinstance(exc,requests.RequestException):msg="NETWORK_REQUEST_FAILED (토큰 비출력)"
        else:msg=type(exc).__name__
        print(json.dumps({"status":"BLOCKED","reason":msg},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=="__main__":
    sys.exit(main())