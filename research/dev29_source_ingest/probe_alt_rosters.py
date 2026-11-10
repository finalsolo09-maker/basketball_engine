"""Research-only ESPN roster and NBA CDN availability probe.
Do not backdate the observed membership or overwrite official team rows.
"""
import urllib.request,urllib.error,json,hashlib,pathlib,datetime,time,csv
base=pathlib.Path("research/dev29_source_ingest");base.mkdir(exist_ok=True,parents=True)
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def fetch(url):
    h={"User-Agent":"Mozilla/5.0 (compatible; NBA-KBL-research/1.0)","Accept":"application/json"}
    with urllib.request.urlopen(urllib.request.Request(url,headers=h),timeout=13) as r:
        return r.status,r.read(2000000)
out={"started":now(),"queries":[]}
queries=[("espn_nba_teams","https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"),
("nba_cdnscores","https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"),
("kbl_player_directory","https://api.kbl.or.kr/players")]
rosters=[]
for key,url in queries:
    record={"key":key,"url":url,"observed_at":now(),"usable":False}
    try:
        status,body=fetch(url)
        record.update(http=status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
        d=json.loads(body);record["usable"]=True
        if key=="espn_nba_teams":
            groups=d.get("sports",[{}])[0].get("leagues",[{}])[0].get("teams",[])
            codes=[(e.get("team") or {}).get("id") for e in groups]
            codes=[c for c in codes if c]
            record["team_ids"]=codes
            if len(codes)==30:
                for cid in codes:
                    url2=f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{cid}/roster"
                    try:
                        st,b=fetch(url2);j=json.loads(b)
                        team=j.get("team") or {}; abbr=team.get("abbreviation")
                        athletes=j.get("athletes",[])
                        for a in athletes:
                            if "items" in a and "group" in a: entries=a["items"]
                            else:entries=[a]
                            for p in entries:
                                name=p.get("fullName") or p.get("displayName")
                                if name and abbr:rosters.append({"team":abbr,"name":name,"espn_id":str(p.get("id","")),"as_observed":now()})
                        time.sleep(.12)
                    except Exception as e:
                        record.setdefault("failed_teams",[]).append({"id":cid,"error":repr(e)[:90]})
                record["mapped_athletes"]=len(rosters)
    except Exception as e:record["error"]=repr(e)[:200]
    out["queries"].append(record)
    time.sleep(.7)
if rosters:
    with (base/"espn_2026_27_roster_observed.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rosters[0]));w.writeheader();w.writerows(rosters)
(base/"ALT_FETCH_RESULTS.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"result":[{k:x.get(k) for k in ("key","usable","http","mapped_athletes","error","failed_teams")} for x in out["queries"]]},ensure_ascii=False))
