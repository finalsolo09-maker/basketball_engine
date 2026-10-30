#!/usr/bin/env python3
"""Guarded, free-tier NBA data updater for NBA/KBL V2.5.1 dev10.

Never writes operational engine DB or KBL DB. NBA source only; no scraping.
Initial output is a provenance-backed staging DB, not an approved prediction DB.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid
from typing import Any

import requests
import bdl_v251_free_ingest as bdl

BASE = Path(__file__).resolve().parent
DEFAULT_WORK = BASE / 'data'
CATALOG = BASE / 'config' / 'sources.json'


def atomic_json(dst: Path, obj: Any) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8')
    tmp = dst.with_name(dst.name + '.new')
    with tmp.open('wb') as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dst)


def catalog() -> dict:
    c = json.loads(CATALOG.read_text(encoding='utf-8'))
    assert c['NBA_BALLDONTLIE']['state'] == 'ENABLED_STAGING'
    assert c['KBL_UNOFFICIAL_API']['state'] == 'HOLD_RIGHTS'
    return c


def guarded_source(kind: str) -> None:
    c = catalog()
    if kind not in ('teams','players','games') or kind not in c['NBA_BALLDONTLIE']['free_endpoints']:
        raise bdl.GateError('ENDPOINT_NOT_IN_APPROVED_FREE_ALLOWLIST')


def ensure_state(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS collector_cursor_state (
        scope TEXT PRIMARY KEY, next_cursor TEXT, updated_at_utc TEXT NOT NULL)''')
    con.commit()


def collect_players_incremental(workdir: Path, page_budget: int, session: requests.Session | None = None) -> dict:
    guarded_source('players')
    if not 0 < page_budget <= 10:
        raise bdl.GateError('PLAYER_PAGE_BUDGET_MUST_BE_1_TO_10')
    key = bdl.api_key_from_environment()
    workdir.mkdir(parents=True,exist_ok=True)
    con = bdl.init_db(workdir / 'nba_bdl_free_staging.sqlite')
    ensure_state(con)
    row = con.execute('SELECT next_cursor FROM collector_cursor_state WHERE scope=?',('players',)).fetchone()
    cursor = row[0] if row else None
    run_id = uuid.uuid4().hex
    with con:
        con.execute('INSERT INTO bdl_runs VALUES (?,?,?,?,?,?)',
                    (run_id,bdl.now_utc(),'players',json.dumps({'cursor': cursor}),'LIVE_API','OBSERVED_NOT_FULL_ASOF'))
    outcomes=[]
    own_session=session is None
    sess=session or requests.Session()
    try:
        for page in range(1,page_budget+1):
            params={'per_page':100}
            if cursor is not None:
                params['cursor']=cursor
            content,ts=bdl.fetch_one(sess,'players',params,key,workdir)
            result=bdl.persist_page(con,workdir,run_id,'players',page,params,content,ts)
            outcomes.append(result)
            next_cursor=result['next_cursor']
            if next_cursor is not None and str(next_cursor)==str(cursor):
                raise bdl.GateError('CURSOR_NOT_ADVANCING')
            cursor=str(next_cursor) if next_cursor is not None else None
            with con:
                con.execute('''INSERT INTO collector_cursor_state(scope,next_cursor,updated_at_utc)
                  VALUES(?,?,?) ON CONFLICT(scope) DO UPDATE SET next_cursor=excluded.next_cursor,
                  updated_at_utc=excluded.updated_at_utc''',('players',cursor,bdl.now_utc()))
            if cursor is None:
                break
    finally:
        if own_session:sess.close()
        con.close()
    return {'run_id':run_id,'pages_saved':len(outcomes),'next_cursor':cursor,
            'valid':sum(r['valid'] for r in outcomes),'held':sum(r['held'] for r in outcomes)}


def audit_raw(workdir:Path) -> dict:
    db=workdir/'nba_bdl_free_staging.sqlite'
    if not db.exists():
        return {'status':'NO_STAGING_DB','pages':0}
    problems=[]
    con=sqlite3.connect(f'file:{db.resolve().as_posix()}?mode=ro',uri=True)
    try:
        integrity=con.execute('PRAGMA integrity_check').fetchall()
        fk=con.execute('PRAGMA foreign_key_check').fetchall()
        for rel,exp in con.execute('SELECT raw_rel_path,response_sha256 FROM bdl_pages'):
            p=(workdir/rel).resolve()
            if not p.is_relative_to(workdir.resolve()):
                problems.append('OUTSIDE_RAW_DIR');continue
            if not p.is_file():
                problems.append(f'MISSING_RAW:{rel}');continue
            with p.open('rb') as f:
                h=hashlib.sha256()
                for chunk in iter(lambda:f.read(1024*1024),b''):
                    h.update(chunk)
            if h.hexdigest()!=exp:problems.append(f'RAW_HASH_MISMATCH:{rel}')
        obs=con.execute('SELECT kind,validation_state,COUNT(*) FROM bdl_observations GROUP BY kind,validation_state').fetchall()
        pages=con.execute('SELECT COUNT(*) FROM bdl_pages').fetchone()[0]
    finally:con.close()
    ok=integrity==[('ok',)] and not fk and not problems
    return {'status':'PASS' if ok else 'BLOCKED','integrity_check':integrity[:2],
        'foreign_key_violations':len(fk),'pages':pages,'observations':[list(x) for x in obs],
        'raw_errors':problems[:30],'raw_errors_total':len(problems),
        'live_model_approved':False,'full_asof_verified':False}


def snapshot(workdir:Path, outdir:Path) -> dict:
    status=audit_raw(workdir)
    if status['status']!='PASS':
        raise bdl.GateError('SNAPSHOT_BLOCKED_BY_INTEGRITY_OR_RAW_HASH')
    outdir.mkdir(parents=True,exist_ok=True)
    src=workdir/'nba_bdl_free_staging.sqlite'
    # Source may be in WAL mode. SQLite backup() is safer than raw copying.
    suffix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target=outdir / f'NBA_V251_RESEARCH_CANDIDATE_{suffix}.sqlite'
    with sqlite3.connect(f'file:{src.resolve().as_posix()}?mode=ro',uri=True) as source:
        with sqlite3.connect(target) as dest:
            source.backup(dest)
    with sqlite3.connect(f'file:{target.resolve().as_posix()}?mode=ro',uri=True) as con:
        if con.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or con.execute('PRAGMA foreign_key_check').fetchall():
            target.unlink(missing_ok=True)
            raise bdl.GateError('BACKUP_INTEGRITY_FAILURE')
    h=bdl.sha256(target.read_bytes())
    manifest={**status,'candidate_db':str(target),'candidate_sha256':h,
        'snapshot_created_utc':bdl.now_utc(),'nba_only':True,
        'operational_db_modified':False,'p0_modified':False,'model_promoted':False,
        'kbl_modified':False,'football_modified':False}
    atomic_json(outdir/'LATEST_CANDIDATE.json',manifest)
    return manifest


def run_daily(workdir:Path, outdir:Path, execute:bool, days_back:int,
              players_pages:int, season:int) -> dict:
    if days_back not in range(1,8) or players_pages not in range(0,11):
        raise bdl.GateError('DAILY_BUDGET_OUT_OF_RANGE')
    plan={'mode':'LIVE_FREE_API' if execute else 'DRY_RUN','nba_sources':['NBA_BALLDONTLIE'],
          'kbl_sources_enabled':[],'request_limit_per_minute':5,'minimum_gap_seconds':12.5,
          'days_back':days_back,'players_pages':players_pages,'season':season,
          'estimated_max_calls':1+days_back+players_pages}
    if not execute:
        return {**plan,'state':'DRY_RUN_NO_API_NO_DB_MUTATION'}
    # Never make any API requests without the key.
    bdl.api_key_from_environment()
    results={};problems=[]
    with bdl.portable_lock(workdir.parent/'.nba_daily_job.lock',wait_seconds=0):
        today=datetime.now(timezone.utc).date()
        try:
            results['teams']=bdl.collect('teams',workdir,None,None,1,100,True)
            if players_pages:
                results['players']=collect_players_incremental(workdir,players_pages)
            for d in range(days_back):
                day=(today-timedelta(days=d)).isoformat()
                results[f'games_{day}']=bdl.collect('games',workdir,day,season,1,100,True)
        except (requests.RequestException,bdl.GateError) as e:
            problems.append(str(e) if isinstance(e,bdl.GateError) else 'NETWORK_ERROR_NO_SECRET_OUTPUT')
        verification=audit_raw(workdir)
        if verification['status']=='PASS':
            snap=snapshot(workdir,outdir)
        else:
            snap=None
        summary={**plan,'result':'PASS' if not problems and snap else 'PARTIAL_OR_BLOCKED',
            'errors':problems,'collect':results,'verification':verification,'snapshot':snap,
            'no_automatic_operational_promotion':True}
        atomic_json(outdir/'LAST_RUN_REPORT.json',summary)
        return summary


def cli()->int:
    p=argparse.ArgumentParser(description='NBA 무료 DB 안전 자동 갱신 (KBL 및 축구 분리)')
    p.add_argument('--workdir',type=Path,default=DEFAULT_WORK)
    p.add_argument('--outdir',type=Path,default=BASE/'candidates')
    sub=p.add_subparsers(dest='cmd',required=True)
    daily=sub.add_parser('daily')
    daily.add_argument('--execute',action='store_true')
    daily.add_argument('--days-back',type=int,default=3)
    daily.add_argument('--players-pages',type=int,default=2)
    daily.add_argument('--season',type=int,default=2026)
    sub.add_parser('audit')
    sub.add_parser('sources')
    sub.add_parser('snapshot')
    args=p.parse_args()
    try:
        if args.cmd=='daily':
            result=run_daily(args.workdir,args.outdir,args.execute,args.days_back,args.players_pages,args.season)
        elif args.cmd=='audit':result=audit_raw(args.workdir)
        elif args.cmd=='snapshot':result=snapshot(args.workdir,args.outdir)
        else:result={'sources':catalog()}
        print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
        return 2 if result.get('status')=='BLOCKED' or result.get('result')=='PARTIAL_OR_BLOCKED' else 0
    except (bdl.GateError,sqlite3.Error,OSError,requests.RequestException,ValueError) as e:
        why=str(e) if isinstance(e,bdl.GateError) else type(e).__name__
        print(json.dumps({'status':'BLOCKED','reason':why},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':sys.exit(cli())