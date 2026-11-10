"""411 NBA season played-team identity evidence from pinned GitHub stat logs.

No inference about unplayed roster members. ESPN roster observed on Nov 10
is independently linked by normalized name+team; never called official NBA.
"""
import csv,collections,datetime as dt,hashlib,io,json,pathlib,re,unicodedata,urllib.request
ROOT=pathlib.Path("research/dev29_source_ingest")
ref="4ef70fbc66425e48090656dcf6ddde2ddc18938d"
paths={
"2024-25":("NBA_players_game_log_2024-25_as_of_2026-11-09.csv","496e6305e9da38b12d887f0f6e4cd8b333873d67"),
"2025-26":("NBA_players_game_log_2025-26_as_of_2026-11-09.csv","0c3d4e594329cda6b48b7b4c16d7a26ef2262278"),
"2026-27":("NBA_players_game_log_2026-27_as_of_2026-11-09.csv","fb0156fe6e924929041d95738d6ff56f5ca3c99e")}
def norm(s):
    s=unicodedata.normalize("NFD",str(s))
    s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub("[^a-z0-9]","",s.lower())
refrows=list(csv.DictReader((pathlib.Path("research/github_identity_20261110")/"nba_411_internal_to_official_candidates.csv").open(encoding="utf8")))
assert len(refrows)==411
played=collections.defaultdict(list); sources=[];bad_stats=collections.Counter()
for season,(filename,blob) in paths.items():
    url=f"https://raw.githubusercontent.com/xtheredshirtx/fanduel-player-data/{ref}/NBA/csv/{filename}"
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"NBA-KBL-Research/1.0"}),timeout=40) as resp:
        content=resp.read(5000000)
    sha=hashlib.sha1(b"blob "+str(len(content)).encode()+b"\\0"+content).hexdigest()
    # NOTE code string escape below uses literal escaped separator; convert
    sha=hashlib.sha1(b"blob "+str(len(content)).encode()+bytes([0])+content).hexdigest()
    if sha!=blob:raise ValueError(f"pinned git blob SHA mismatch: {season}: {sha}")
    records=list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    sources.append({"season":season,"url":url,"git_blob_sha1":sha,"sha256":hashlib.sha256(content).hexdigest(),"rows":len(records)})
    for r in records:
        pid=str(r.get("ID") or "")
        try:
            p=int(float(r.get("Points") or 0))
            fgm=int(float(r.get("FGM") or 0)); tpm=int(float(r.get("3PM") or 0)); ftm=int(float(r.get("FTM") or 0))
            if p!=2*fgm+tpm+ftm:bad_stats[season]+=1
        except ValueError:bad_stats[season]+=1
        if pid.isdigit() and r.get("Team"):
            played[(pid,season)].append((r["Date"],r["Team"],r["Player"]))
espn=list(csv.DictReader((ROOT/"espn_2026_27_roster_observed.csv").open(encoding="utf8")))
observed=collections.defaultdict(set)
for r in espn:
    observed[norm(r["name"])].add(r["team"].upper())
output=[];counts=collections.Counter()
for item in refrows:
    pid=str(item.get("nba_official_id") or "")
    name=item["player_name"];key=norm(name)
    es=sorted(observed.get(key,set()))
    for season in paths:
        s=played.get((pid,season),[])
        teams=sorted(set(t for d,t,n in s))
        stats=collections.Counter(t for d,t,n in s)
        row={"source_row":item["source_row"],"nba_player_id":pid,"player_name":name,
             "original_team_internal":item["team"],"season":season,
             "teams_with_game_logs":";".join(teams),
             "team_game_rows":len(s),"per_team_game_rows_json":json.dumps(stats,sort_keys=True),
             "first_game_date":min((d for d,t,n in s),default=""),
             "last_game_date":max((d for d,t,n in s),default=""),
             "espn_current_team_observed":";".join(es) if season=="2026-27" else "",
             "internal_team_in_season_game_log":int(item["team"] in teams),
             "internal_team_in_espn_current":int(item["team"] in es) if season=="2026-27" else "",
             "identity_status":item["identity_status"],
             "official_2026_27_roster_approved":0,
             "pregame_asof_approved":0,
             "evidence_class":"DATE_ONLY_PLAYED_TEAM" if s else "NO_OBSERVED_GAME_LOG"}
        output.append(row)
        counts[(season,"with_game_log")]+=int(bool(s))
        if season=="2026-27":
            counts[("espn","matched_any_team")]+=int(bool(es))
            counts[("espn","same_as_internal")]+=int(item["team"] in es)
            counts[("espn","different_from_internal")]+=int(bool(es) and item["team"] not in es)
            counts[("espn","no_name_match")]+=int(not es)
csvpath=ROOT/"NBA_411_SEASON_TEAM_AS_PLAYED_CROSSWALK.csv"
with csvpath.open("w",newline="",encoding="utf8") as f:
    w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
report={"collected_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"source_logs":sources,
        "people":len(refrows),"season_rows":len(output),"counts":{f"{a}_{b}":v for (a,b),v in counts.items()},
        "stat_identity_mismatch_rows":dict(bad_stats),
        "current_espn_roster_rows":len(espn),
        "interpretation":"season played-team evidence, not current official registration; ESPN observed status only",
        "allow_in_live_training":False,"source":"third_party_player_game_logs",
        "roster_evidence":"ESPN 2026-11-10 observation, not official NBA asof on past games"}
(ROOT/"NBA_411_SEASON_TEAM_CROSSWALK_SUMMARY.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"seasons":report["counts"],"source_rows":sources,"stat_errors":dict(bad_stats)},ensure_ascii=False))
