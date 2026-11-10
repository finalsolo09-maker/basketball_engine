"""One-pass official public-source probe, bounded and not an authorized bulk scraper.
Only derives IDs and factual box-score fields; keeps raw SHA and fetch timestamps.
Research evidence only: observation != publication at P0 cutoff.
"""
import csv, datetime as dt, hashlib, json, os, pathlib, time
import urllib.request, urllib.error

OUT=pathlib.Path("research/dev29_source_ingest");OUT.mkdir(parents=True,exist_ok=True)
NOW=lambda:dt.datetime.now(dt.timezone.utc).isoformat()
tasks=[
("kbl_directory","https://api.kbl.or.kr/players"),
("kbl_box_2025_26","https://api.kbl.or.kr/match/S47G01N49/player-stat"),
("kbl_box_2026_27","https://api.kbl.or.kr/match/S49G01N57/player-stat"),
("nba_current_roster","https://stats.nba.com/stats/commonallplayers?LeagueID=00&Season=2026-27&IsOnlyCurrentSeason=1"),
("nba_player_list","https://www.nba.com/players"),
]
results=[]
def extract_rows(value,labels=("list","players","data","items","records","player","rowSet")):
    if isinstance(value,list):
        return value
    if isinstance(value,dict):
        for key in labels:
            inner=value.get(key)
            if isinstance(inner,list): return inner
            if isinstance(inner,dict):
                got=extract_rows(inner,labels)
                if got:return got
        for v in value.values():
            if isinstance(v,dict):
                got=extract_rows(v,labels)
                if got:return got
    return []
def write_csv(path,rows,fields):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader()
        for row in rows:w.writerow({k:row.get(k) for k in fields})
def get(url):
    headers={"User-Agent":"NBA-KBL-Research-Audit/1.0 (public factual data; capped requests)","Accept":"application/json,text/html;q=0.9"}
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=18) as r:
        return r.status,dict(r.headers),r.read(4_000_000)
for key,url in tasks:
    record={"task":key,"url":url,"observed_at_utc":NOW(),"status":"UNFETCHED","http_status":None,"rows_usable":0}
    try:
        status,h,b=get(url); record.update(http_status=status,sha256=hashlib.sha256(b).hexdigest(),response_bytes=len(b),headers={"last_modified":h.get("Last-Modified"),"date":h.get("Date"),"etag":h.get("ETag")})
        if status!=200 or not b:raise ValueError("empty/non-200")
        if key=="nba_player_list":
            record["status"]="HTML_SNAPSHOT_ONLY_NOT_SCHEMA_MAPPED"
        else:
            d=json.loads(b)
            # kbl vendor response may wrap payload as dict(data={...},response={...})
            rows=extract_rows(d)
            if key=="nba_current_roster" and isinstance(d,dict):
                sets=d.get("resultSets") or d.get("resultSet") or []
                if isinstance(sets,dict):sets=[sets]
                for s in sets:
                    hds=s.get("headers") or s.get("Headers") or []
                    body=s.get("rowSet") or s.get("rowset") or []
                    if body and hds:
                        rows=[dict(zip(hds,x)) for x in body]
                        break
            if key=="kbl_directory":
                mapped=[]
                for v in rows:
                    if not isinstance(v,dict):continue
                    rec={k:(v.get(k) or v.get(k.replace("_","")) or "") for k in ("pcode","player_name","player_name_en","team_code")}
                    rec["pcode"]=str(rec["pcode"]) if rec["pcode"] else str(v.get("pcode") or "")
                    rec["player_name"]=rec["player_name"] or v.get("pname") or ""
                    rec["team_code"]=rec["team_code"] or v.get("tcode") or ""
                    if len(rec["pcode"])==6 and rec["player_name"]: mapped.append(rec)
                if mapped:
                    write_csv(OUT/"kbl_pcode_directory_candidates.csv",mapped,["pcode","player_name","player_name_en","team_code"])
                    record["status"]="MAPPED_RESEARCH_PCODE_ONLY";record["rows_usable"]=len(mapped)
                else:record["status"]="RESPONSE_SCHEMA_NOT_MAPPED"
            elif key.startswith("kbl_box"):
                mapped=[]
                for v in rows:
                    if not isinstance(v,dict):continue
                    code=str(v.get("pcode") or v.get("playerNo") or "")
                    if len(code)!=6:continue
                    m={"gmkey":key.replace("kbl_box_",""),"pcode":code,"team_code":str(v.get("tcode") or v.get("team_code") or ""),"player_name":str(v.get("pname") or v.get("player_name") or ""),"started":v.get("started") or v.get("start_flag"),"points":v.get("score"),"fg3m":v.get("threep") or v.get("three_p"),"fg3a":v.get("threep_a") or v.get("three_pa"),"rebounds":v.get("reb") or v.get("reb_total"),"assists":v.get("ast"),"turnovers":v.get("tov")}
                    mapped.append(m)
                if mapped:
                    write_csv(OUT/(key+"_box_candidates.csv"),mapped,list(mapped[0]))
                    record["status"]="MAPPED_POSTGAME_ONLY";record["rows_usable"]=len(mapped)
                else:record["status"]="RESPONSE_SCHEMA_NOT_MAPPED"
            elif key=="nba_current_roster":
                mapped=[]
                for v in rows:
                    if not isinstance(v,dict):continue
                    pid=v.get("PERSON_ID") or v.get("person_id")
                    tid=v.get("TEAM_ID") or v.get("team_id")
                    name=v.get("DISPLAY_FIRST_LAST") or v.get("PLAYER_NAME")
                    if pid and tid and int(tid)>0:
                        mapped.append({"player_id":pid,"team_id":tid,"player_name":name or "","rosterstatus":v.get("ROSTERSTATUS"),"team_abbr":v.get("TEAM_ABBREVIATION")})
                if mapped:
                    write_csv(OUT/"nba_2026_27_team_player_candidates.csv",mapped,list(mapped[0]))
                    record["status"]="MAPPED_CURRENT_TEAM_CANDIDATES";record["rows_usable"]=len(mapped)
                else:record["status"]="RESPONSE_SCHEMA_NOT_MAPPED"
    except Exception as e:
        record["status"]="BLOCKED_FETCH_OR_SCHEMA";record["error"]=repr(e)[:300]
    results.append(record)
    time.sleep(0.8)
(OUT/"FETCH_RESULTS.json").write_text(json.dumps({"created":NOW(),"no_secrets":True,"no_full_asof_claim":True,"sources":results},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps({x["task"]:{k:x.get(k) for k in ("status","http_status","rows_usable","error")} for x in results},ensure_ascii=False))
