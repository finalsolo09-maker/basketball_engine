"""KBL actual player box -> team tactical and lineup features -> date-only train/holdout.
Research only. No pregame release-time proof, live prediction, or P0 overwrites.
"""
import csv,json,math,statistics,datetime,hashlib,collections,pathlib
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from scipy.special import ndtr

ROOT=pathlib.Path("research/dev29_source_ingest")
DATA=ROOT/"kbl_2025_26_2026_27_player_game_research.csv"
rows=list(csv.DictReader(DATA.open(encoding="utf8")))
assert len(rows)>=5000,"Incomplete verified player box cohort"
games=collections.defaultdict(list)
byteam=collections.defaultdict(list)
for x in rows:
    games[x["gmkey"]].append(x)
    byteam[(x["gmkey"],x["team_code"])].append(x)
summary=json.loads((ROOT/"KBL_BULK_COLLECTION_SUMMARY.json").read_text())
assert len(games)==summary["games_passed"]
ordered=sorted(games,key=lambda k:(games[k][0]["game_date"],k))
hist=collections.defaultdict(list)
feature_rows=[]
def xnum(v,default=0.0):
    try:return float(v)
    except(TypeError,ValueError):return default
def mean(vals,default=np.nan):
    return float(np.mean(vals)) if vals else default
def last(a,k,n=5,default=np.nan):
    return mean([v[k] for v in a[-n:]],default)
for gmkey in ordered:
    batch=games[gmkey]; g=batch[0]
    for team,opp,flag in [(g["home_code"],g["away_code"],1),(g["away_code"],g["home_code"],0)]:
        players=byteam[(gmkey,team)]
        other=byteam[(gmkey,opp)]
        assert players and other
        h=hist[team]
        date=datetime.datetime.strptime(g["game_date"],"%Y%m%d")
        prev=[p for p in h if p["date"]<date]
        past5=prev[-5:];past10=prev[-10:]
        played_codes={p["pcode"] for p in players}
        starters={p["pcode"] for p in players if int(p["started"])==1}
        points=int(sum(xnum(p["score"]) for p in players))
        allowed=int(sum(xnum(p["score"]) for p in other))
        assert points==int(g["home_points"] if flag else g["away_points"])
        pg=dict(date=date,team=team,opp=opp,season=g["season"],game=gmkey,points=points,allowed=allowed,
            three_pa=sum(xnum(p["fg3a"]) for p in players),three_pm=sum(xnum(p["fg3m"]) for p in players),
            two_pa=sum(xnum(p["fg2a"]) for p in players),two_pm=sum(xnum(p["fg2m"]) for p in players),
            fta=sum(xnum(p["fta"]) for p in players),ftm=sum(xnum(p["ftm"]) for p in players),
            reb=sum(xnum(p["reb"]) for p in players),oreb=sum(xnum(p["oreb"]) for p in players),
            tov=sum(xnum(p["tov"]) for p in players),ast=sum(xnum(p["ast"]) for p in players),
            max_pts=max(xnum(p["score"]) for p in players),
            top2_pts=sum(sorted((xnum(p["score"]) for p in players),reverse=True)[:2]),
            top5_minutes=sum(sorted((xnum(p["minutes"]) for p in players),reverse=True)[:5]),
            starters=starters,played_codes=played_codes,
            n_players=len(players))
        pg["poss_est"]=pg["two_pa"]+pg["three_pa"]+0.44*pg["fta"]-pg["oreb"]+pg["tov"]
        pg["top2_scoring_share"]=pg["top2_pts"]/max(1,pg["points"])
        pg["three_attempt_rate"]=pg["three_pa"]/max(1,pg["two_pa"]+pg["three_pa"])
        pg["turnover_poss_rate"]=pg["tov"]/max(1,pg["poss_est"])
        pg["oreb_poss_rate"]=pg["oreb"]/max(1,pg["poss_est"])
        pg["off_eff"]=100*pg["points"]/max(1,pg["poss_est"])
        pg["starters_retention"]=len(starters & prev[-1]["starters"])/max(1,len(starters|prev[-1]["starters"])) if prev else np.nan
        f={"gmkey":gmkey,"date":g["game_date"],"season":g["season"],
           "home":g["home_code"],"away":g["away_code"],
           "team":team,"side":"H" if flag else "A",
           "points":pg["points"],"allowed":pg["allowed"],
           "prior_team_games":len(prev),
           "rest_days":(date-prev[-1]["date"]).days-1 if prev else np.nan,
           "prev_team_points_5":last(past5,"points"),
           "prev_opp_points_5":last(past5,"allowed"),
           "prev_team_points_10":last(past10,"points",10),
           "prev_opp_points_10":last(past10,"allowed",10),
           "prev_team_points_std_5":float(np.std([p["points"] for p in past5])) if len(past5)>=2 else np.nan,
           "prev_team_threepa_5":last(past5,"three_pa"),
           "prev_team_3par_5":last(past5,"three_attempt_rate"),
           "prev_team_ft_rate_5":mean([p["fta"]/max(1,p["two_pa"]+p["three_pa"]) for p in past5]),
           "prev_team_turnover_5":last(past5,"turnover_poss_rate"),
           "prev_team_oreb_5":last(past5,"oreb_poss_rate"),
           "prev_team_reb_5":last(past5,"reb"),
           "prev_team_ast_5":last(past5,"ast"),
           "prev_team_poss_5":last(past5,"poss_est"),
           "prev_team_offeff_5":last(past5,"off_eff"),
           "prev_top2_scoring_share_5":last(past5,"top2_scoring_share"),
           "prev_top5_minutes_5":last(past5,"top5_minutes"),
           "prev_starters_retention_5":last(past5,"starters_retention"),
           "prev_player_pool_5":len(set().union(*[p["played_codes"] for p in past5])) if past5 else np.nan}
        feature_rows.append(f)
        hist[team].append(pg)
match=collections.defaultdict(dict)
for row in feature_rows:
    item=match[row["gmkey"]]
    for k in ("gmkey","date","season","home","away"): item[k]=row[k]
    tag=row["side"]
    for k,v in row.items():
        if k not in ("gmkey","date","season","home","away","side","team"):
            item[k+"_"+tag]=v
matches=sorted(match.values(),key=lambda r:(r["date"],r["gmkey"]))
assert len(matches)==summary["games_passed"]
tune=[x for x in matches if x["season"]=="2025-26"]
hold=[x for x in matches if x["season"]=="2026-27"]
assert len(tune)==summary["games_passed_2025_26"]
assert len(hold)==summary["games_passed_2026_27"]
train=tune[:int(len(tune)*.75)]
val=tune[int(len(tune)*.75):]
assert max(x["date"] for x in train)<min(x["date"] for x in val)
assert max(x["date"] for x in val)<min(x["date"] for x in hold)
basic=["prior_team_games","rest_days","prev_team_points_5","prev_opp_points_5","prev_team_points_10","prev_opp_points_10"]
measured=["prev_team_points_std_5","prev_team_threepa_5","prev_team_3par_5","prev_team_ft_rate_5","prev_team_turnover_5","prev_team_oreb_5","prev_team_reb_5","prev_team_ast_5","prev_team_poss_5","prev_team_offeff_5"]
player=["prev_top2_scoring_share_5","prev_top5_minutes_5","prev_starters_retention_5","prev_player_pool_5"]
y=lambda dat:np.array([[r["points_H"],r["points_A"]] for r in dat],float)
def xmat(dat,features):
    return np.array([[float(r.get(k+"_"+s,np.nan)) for s in ("H","A") for k in features] for r in dat],float)
def baseline(dat):
    result=[]
    for r in dat:
        h=(r["prev_team_points_5_H"]+r["prev_opp_points_5_A"])/2
        a=(r["prev_team_points_5_A"]+r["prev_opp_points_5_H"])/2
        result.append([h if np.isfinite(h) else 82,a if np.isfinite(a) else 80])
    return np.array(result,float)
def fit(dat,features,alpha):
    X=xmat(dat,features)
    imp=SimpleImputer(strategy="median",keep_empty_features=True)
    z=imp.fit_transform(X)
    scl=StandardScaler();z=scl.fit_transform(z)
    model=Ridge(alpha=float(alpha)).fit(z,y(dat))
    return imp,scl,model
def pred(model,dat,features):
    imp,scl,est=model
    return est.predict(scl.transform(imp.transform(xmat(dat,features))))
def metrics(yt,yp,sigma):
    actual=yt[:,0]-yt[:,1]; predicted=yp[:,0]-yp[:,1]
    a=ndtr((-5.5-predicted)/sigma)
    h=1-ndtr((5.5-predicted)/sigma)
    prob=np.column_stack([a,1-a-h,h]).clip(1e-7,1)
    prob/=prob.sum(axis=1,keepdims=True)
    cats=np.where(actual>5,2,np.where(actual< -5,0,1))
    return {"games":int(len(yt)),"winner_accuracy":float(np.mean((actual>0)==(predicted>0))),
     "margin_MAE":float(np.mean(abs(actual-predicted))),
     "total_MAE":float(np.mean(abs(yt.sum(axis=1)-yp.sum(axis=1)))),
     "win5_accuracy":float(np.mean(np.argmax(prob,axis=1)==cats)),
     "win5_logloss":float(np.mean(-np.log(prob[np.arange(len(yt)),cats]))),
     "win5_brier":float(np.mean(np.sum((prob-np.eye(3)[cats])**2,axis=1)))}
results={}
sigma0=float(np.std(y(train)[:,0]-y(train)[:,1],ddof=1))
results["BASE_RECENT"]= {"holdout":metrics(y(hold),baseline(hold),sigma0),"val":metrics(y(val),baseline(val),sigma0)}
predictions={}
for label,feat in {"TEAM_ONLY":basic,"TEAM_AND_TACTICAL":basic+measured,"TEAM_TACTICAL_PLAYER":basic+measured+player}.items():
    best=None
    for alpha in (1,20,100,400,1000):
        m=fit(train,feat,alpha)
        p=pred(m,val,feat)
        v=metrics(y(val),p,sigma0)
        loss=v["margin_MAE"]+.1*v["total_MAE"]
        if best is None or loss<best[0]:best=(loss,alpha,m,v)
    _,alpha,model,v=best
    p=pred(model,hold,feat)
    sigma=float(np.std((y(train)[:,0]-y(train)[:,1])-(pred(model,train,feat)[:,0]-pred(model,train,feat)[:,1]),ddof=1))
    hm=metrics(y(hold),p,sigma)
    results[label]={"alpha_selected_on_validation":alpha,"features":feat,"val":v,"holdout":hm,"sigma_train":sigma,
     "coefficients":model[2].coef_.tolist(),"intercept":model[2].intercept_.tolist()}
    predictions[label]=p
results["metadata"]={"research_only":True,"asof":"DATE_ONLY_REPLAY","player_identity":"KBL pcode exact game team join",
 "pregame_injury_asof_verified":False,"prospective_holdout":False,
 "train_games":len(train),"validate_games":len(val),"outseason_holdout_games":len(hold),
 "first_holdout":hold[0]["date"],"last_holdout":hold[-1]["date"],
 "no_live_p0_changed":True,"sources":summary.get("api_docs")}
(ROOT/"KBL_DEV29_ACTUAL_PLAYER_TACTICS_ABLATION.json").write_text(json.dumps(results,indent=2,ensure_ascii=False)+"\n")
with (ROOT/"KBL_DEV29_ACTUAL_PLAYER_TACTICS_HOLDOUT.csv").open("w",newline="",encoding="utf8") as f:
    fields=["gmkey","game_date","season","home_code","away_code","actual_home","actual_away","baseline_home","baseline_away"]+[f"{k}_{s}" for k in predictions for s in ("home","away")]
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for i,r in enumerate(hold):
        out=dict(gmkey=r["gmkey"],game_date=r["date"],season=r["season"],home_code=r["home"],away_code=r["away"],actual_home=r["points_H"],actual_away=r["points_A"],
         baseline_home=baseline(hold)[i,0],baseline_away=baseline(hold)[i,1])
        for k,p in predictions.items():out[k+"_home"]=p[i,0];out[k+"_away"]=p[i,1]
        w.writerow(out)
print(json.dumps({"train":len(train),"validate":len(val),"holdout":len(hold),"metrics":{k:v["holdout"] for k,v in results.items() if k!="metadata"}},ensure_ascii=False))
