"""Rate-limited KBL official public historical game box ingestion.

Only factual normalized rows are persisted in this research branch; original
JSON remains in memory and its SHA-256 is recorded for each response.
Public API may limit access: stop at HTTP 403/429, never circumvent limits.
No P0 or promoted weights touched.
"""
import csv,datetime as dt,hashlib,json,pathlib,time,urllib.request,urllib.error

ROOT=pathlib.Path("research/dev29_source_ingest")
ROOT.mkdir(exist_ok=True,parents=True)
START=dt.datetime.now(dt.timezone.utc)
OBS=lambda:dt.datetime.now(dt.timezone.utc).isoformat()
HEAD={"Channel":"WEB","TeamCode":"XX","Accept":"application/json",
      "User-Agent":"NBA-KBL-Research-Audit/1.0 (rate-limited public read)"}
LAST=[0.0]
def pull(url):
    delay=1.08-(time.monotonic()-LAST[0])
    if delay>0: time.sleep(delay)
    LAST[0]=time.monotonic()
    with urllib.request.urlopen(urllib.request.Request(url,headers=HEAD),timeout=18) as r:
        b=r.read(2_000_000)
        if not b or r.status!=200:raise ValueError("not200")
    return json.loads(b),hashlib.sha256(b).hexdigest(),len(b)
windows=[("20251001","20251231","2025-26"),("20260101","20260531","2025-26"),
         ("20261001","20261109","2026-27")]
games={};fetches=[]; errors=[]
for fr,to,season in windows:
    url=f"https://api.kbl.or.kr/match/list?fromDate={fr}&toDate={to}"
    try:
        arr,digest,nb=pull(url)
        assert isinstance(arr,list)
        for rec in arr:
            gmkey=str(rec.get("gmkey",""))
            if (season=="2025-26" and not gmkey.startswith("S47G01N")) or (season=="2026-27" and not gmkey.startswith("S49G01N")):
                continue
            if int(rec.get("isEnded",0))!=1:continue
            games[gmkey]=rec
        fetches.append({"url":url,"sha256":digest,"bytes":nb,"observed_at_utc":OBS(),"matched_games":len(games)})
    except Exception as exc:
        errors.append({"endpoint":url,"error":repr(exc)})
if len([g for g in games if g.startswith("S47")])<200:errors.append({"severity":"HARD","reason":"2025_26_SCHEDULE_LT_200"})
cols=["gmkey","season","game_date","home_code","away_code","home_points","away_points","team_code","pcode","player_name","started","minutes","score","fg2m","fg2a","fg3m","fg3a","ftm","fta","oreb","dreb","reb","ast","tov","fouls","usg_pct","offrtg","defrtg","s_source_sha256","s_observed_at_utc"]
rows=[];game_evidence=[];completed=[]
for gmkey,g in sorted(games.items(), key=lambda e:(e[1].get("gameDate") or "",e[0])):
    url=f"https://api.kbl.or.kr/match/{gmkey}/player-stat"
    try:
        ans,digest,nb=pull(url)
        if not isinstance(ans,list) or not ans:raise ValueError("invalid_or_empty_list")
        parsed=[]
        for entry in ans:
            p=entry.get("player") or {};r=entry.get("records") or {}
            code=str(p.get("pcode") or "")
            if len(code)!=6:continue
            pmin=float(r.get("playMin") or 0)+float(r.get("playSec") or 0)/60
            row={
                "gmkey":gmkey,"season":"2025-26" if gmkey.startswith("S47") else "2026-27",
                "game_date":str(g["gameDate"]),"home_code":str(g["tcodeH"]),"away_code":str(g["tcodeA"]),
                "home_points":int(g["scoreH"]),"away_points":int(g["scoreA"]),
                "team_code":str(p.get("tcode") or ""), "pcode":code,
                "player_name":p.get("pname") or "","started":int(entry.get("startFlag") or 0),
                "minutes":round(pmin,4),"score":int(r.get("score") or 0),
                "fg2m":int(r.get("fg") or 0),"fg2a":int(r.get("fgA") or 0),
                "fg3m":int(r.get("threep") or 0),"fg3a":int(r.get("threepA") or 0),
                "ftm":int(r.get("ft") or 0),"fta":int(r.get("ftA") or 0),
                "oreb":int(r.get("offr") or 0),"dreb":int(r.get("defr") or 0),
                "reb":int(r.get("rb") or 0),"ast":int(r.get("ast") or 0),
                "tov":int(r.get("to") or 0),"fouls":int(r.get("foul") or 0),
                "usg_pct":r.get("usgRt"),"offrtg":r.get("offrtg"),
                "defrtg":r.get("defrtg"),"s_source_sha256":digest,"s_observed_at_utc":OBS(),
            }
            if row["team_code"] not in {row["home_code"],row["away_code"]}:
                raise ValueError("unknown_team")
            if 2*row["fg2m"]+3*row["fg3m"]+row["ftm"]!=row["score"]:
                raise ValueError("player_score_identity")
            parsed.append(row)
        if len(parsed)<10:raise ValueError("less_than_10_players")
        h=sum(x["score"] for x in parsed if x["team_code"]==str(g["tcodeH"]))
        a=sum(x["score"] for x in parsed if x["team_code"]==str(g["tcodeA"]))
        if (h,a)!=(int(g["scoreH"]),int(g["scoreA"])):
            raise ValueError(f"score_sum_mismatch home={h} away={a}")
        rows.extend(parsed); completed.append(gmkey)
        game_evidence.append({"gmkey":gmkey,"date":g.get("gameDate"),"players":len(parsed),
            "sha256":digest,"observed_at_utc":OBS(),"status":"SCORE_AND_TEAM_CHECKED"})
    except urllib.error.HTTPError as exc:
        errors.append({"gmkey":gmkey,"error":f"HTTP_{exc.code}"})
        if exc.code in (403,429):break
    except Exception as exc:errors.append({"gmkey":gmkey,"error":repr(exc)[:160]})
with (ROOT/"kbl_2025_26_2026_27_player_game_research.csv").open("w",newline="",encoding="utf-8") as f:
    writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader();writer.writerows(rows)
(ROOT/"kbl_game_box_evidence.json").write_text(json.dumps(game_evidence,ensure_ascii=False,indent=1)+"\n",encoding="utf-8")
summary={"started":START.isoformat(),"finished":OBS(),"api_docs":"https://py.sportsdataverse.org/docs/kbl/reference/kbl",
         "source_dates":windows,"schedule_hits":len(games),
         "scheduled_2025_26":sum(x.startswith("S47") for x in games),
         "scheduled_2026_27":sum(x.startswith("S49") for x in games),
         "games_passed":len(completed),"games_passed_2025_26":sum(x.startswith("S47") for x in completed),
         "games_passed_2026_27":sum(x.startswith("S49") for x in completed),
         "player_game_rows":len(rows),
         "distinct_pcode":len({x["pcode"] for x in rows}),
         "errors":errors,"schedule_sources":fetches,
         "grade":"POSTGAME_SNAPSHOT_AT_2026_11_10_REPLAY_PREGAME_SHOULD_FILTER_DATE",
         "licensing":"RESEARCH_ONLY_NO_LIVE_REUSE_APPROVAL",
         "no_original_p0_modified":True,
         "game_score_check":"REQUIRED_FOR_ALL_ACCEPTED_GAMES"}
(ROOT/"KBL_BULK_COLLECTION_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({k:summary[k] for k in ("schedule_hits","scheduled_2025_26","scheduled_2026_27","games_passed","games_passed_2025_26","games_passed_2026_27","player_game_rows","distinct_pcode")}))
