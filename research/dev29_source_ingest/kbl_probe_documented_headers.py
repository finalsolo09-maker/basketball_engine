"""KBL documented public endpoint single sample, declared mandatory Channel/TeamCode headers."""
import json,urllib.request,urllib.error,hashlib,datetime,pathlib,csv,time
folder=pathlib.Path("research/dev29_source_ingest"); folder.mkdir(exist_ok=True,parents=True)
tasks=[("players","https://api.kbl.or.kr/players"),
("box_2025","https://api.kbl.or.kr/match/S47G01N49/player-stat"),
("match_2025","https://api.kbl.or.kr/match/S47G01N49"),
("box_2026","https://api.kbl.or.kr/match/S49G01N57/player-stat")]
results=[]
for key,url in tasks:
    info={"task":key,"endpoint":url,"observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        req=urllib.request.Request(url,headers={
            "Channel":"WEB","TeamCode":"XX","Accept":"application/json",
            "User-Agent":"sports-data-validation/1.0 (public documented API; 1req/s)"
        })
        with urllib.request.urlopen(req,timeout=22) as res:
            b=res.read(4000000);info.update(http=res.status,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
        val=json.loads(b)
        if isinstance(val,list):
            items=val
        elif isinstance(val,dict):
            items=val.get("data") or val.get("list") or val.get("result") or []
        else:items=[]
        if isinstance(items,dict):
            items=items.get("list") or items.get("data") or items.get("items") or []
        if key=="players" and isinstance(items,list):
            rows=[{"pcode":str(v.get("pcode") or ""),"player_name":v.get("pname") or "",
                   "team_code":str(v.get("tcode") or ""),"player_name_en":v.get("ename") or "",
                   "position":v.get("pos") or "", "player_flag":v.get("playerFlag") or ""} for v in items if isinstance(v,dict) and v.get("pcode")]
            if rows:
                with (folder/"kbl_pcode_directory_20261110.csv").open("w",encoding="utf8",newline="") as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
                info.update(usable=len(rows),sample=rows[:3])
            else: info["schema_keys"]=list(val.keys()) if isinstance(val,dict) else "list"
        elif key.startswith("box") and isinstance(items,list):
            rows=[]
            for obj in items:
                p=obj.get("player") or {};r=obj.get("records") or {}
                if p.get("pcode"):
                    rows.append(dict(pcode=str(p["pcode"]),name=p.get("pname"),
                        team_code=str(p.get("tcode","")),home_away=obj.get("homeAway"),
                        started=obj.get("startFlag"),points=r.get("score"),min=r.get("playMin"),
                        sec=r.get("playSec"),two_point_made=r.get("fg"),two_point_attempts=r.get("fgA"),
                        fg3m=r.get("threep"),fg3a=r.get("threepA"),
                        ftm=r.get("ft"),fta=r.get("ftA"),reb=r.get("rb"),ast=r.get("ast"),
                        tov=r.get("to"),offrtg=r.get("offrtg"),defrtg=r.get("defrtg"),
                        usage=r.get("usgRt")))
            if rows:
                with (folder/(key+"_player_box_20261110.csv")).open("w",encoding="utf8",newline="") as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            info.update(usable=len(rows),sample=rows[:1])
        else:
            info["type"]=str(type(items));info["schema_keys"]=list(val.keys()) if isinstance(val,dict) else "list";info["preview"]=str(val)[:300]
    except Exception as e:info["error"]=repr(e)[:250]
    results.append(info);time.sleep(1.2)
(folder/"KBL_REQUIRED_HEADER_FETCH_RESULTS.json").write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
print(json.dumps([{k:r.get(k) for k in ("task","http","usable","error","schema_keys")} for r in results],ensure_ascii=False))
