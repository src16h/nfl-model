"""
Nov 5 2026: how weather moves a team's passing and running (the numbers behind config.WX_PLAYER).
Opponent-adjusted team-game residuals from 2014-25 outdoor regular-season games, regressed on wind over
10 mph, real rain, light rain, snow and cold. Run: python tools/nfl_weather_fit.py [cache_dir]
"""
import sys, os, pandas as pd, numpy as np, nflreadpy as nfl
SP=sys.argv[1] if len(sys.argv) > 1 else "/tmp/nfl_wx"
os.makedirs(SP, exist_ok=True)
if not os.path.exists(f'{SP}/pbp.parquet'):
    cols=["game_id","season","week","season_type","home_team","away_team","posteam","defteam","pass","rush","qb_dropback","qb_scramble","sack","pass_attempt","complete_pass","interception","yards_gained","xpass","wp","qtr","down","two_point_attempt","weather"]
    pd.concat([nfl.load_pbp([y]).select(cols).to_pandas() for y in range(2014, 2026)]).to_parquet(f'{SP}/pbp.parquet')
    nfl.load_schedules(list(range(2014, 2026))).to_pandas().to_parquet(f'{SP}/sched.parquet')
p=pd.read_parquet(f'{SP}/pbp.parquet'); p=p[(p.season_type=='REG')&(p.two_point_attempt!=1)]
s=pd.read_parquet(f'{SP}/sched.parquet'); s=s[s.game_type=='REG']
for c in ['pass','rush','qb_dropback','qb_scramble','sack','pass_attempt','complete_pass','interception','yards_gained','xpass','wp']:
    p[c]=pd.to_numeric(p[c],errors='coerce')
p=p[p.posteam.notna()]
pa=p[(p.pass_attempt==1)&(p.sack!=1)]; dr=p[(p.rush==1)&(p.qb_scramble!=1)]
neu=p[(p.wp.between(.2,.8))&(p.down<=3)&(p.qtr<=3)&p.xpass.notna()&((p['pass']==1)|(p.rush==1))]
g=pd.DataFrame({
 'att':pa.groupby(['game_id','posteam']).size(),
 'cmp':pa.groupby(['game_id','posteam']).complete_pass.sum(),
 'pyds':pa.groupby(['game_id','posteam']).yards_gained.sum(),
 'int':pa.groupby(['game_id','posteam']).interception.sum(),
 'car':dr.groupby(['game_id','posteam']).size(),
 'ryds':dr.groupby(['game_id','posteam']).yards_gained.sum(),
 'proe':neu.groupby(['game_id','posteam']).apply(lambda x:(x['pass']-x.xpass).mean()),
}).reset_index()
d=p.groupby(['game_id','posteam']).defteam.first().reset_index(); g=g.merge(d,on=['game_id','posteam'])
g['season']=g.game_id.str[:4].astype(int)
g['ypa']=g.pyds/g.att; g['cmpp']=g.cmp/g.att; g['ypc']=g.ryds/g.car; g['passshare']=g.att/(g.att+g.car)
# opponent-adjusted residuals: stat - (offense season avg + defense season avg - league season avg), leave-one-out-ish via season means
stats=['att','cmp','pyds','int','car','ryds','ypa','cmpp','ypc','passshare','proe']
for st in stats:
    lg=g.groupby('season')[st].transform('mean')
    off=g.groupby(['season','posteam'])[st].transform('mean'); de=g.groupby(['season','defteam'])[st].transform('mean')
    g['r_'+st]=g[st]-(off+de-lg)
w=p.groupby('game_id')['weather'].first().astype(str).str.lower()
wet=w.str.contains('rain|snow|shower|drizzle|sleet|storm|flurr') & ~w.str.contains('no chance|0% chance|indoor|dome')
snow=w.str.contains('snow|sleet|flurr'); light=w.str.contains('light|drizzle|flurr|chance')
wx=pd.DataFrame({'wet':wet,'snow':snow,'light':light}).reset_index()
s2=s[['game_id','roof','temp','wind']].merge(wx,on='game_id',how='left')
g=g.merge(s2,on='game_id',how='left')
g=g[~g.roof.isin(['dome','closed'])].copy()
g['wind']=pd.to_numeric(g.wind,errors='coerce').fillna(0); g['temp']=pd.to_numeric(g.temp,errors='coerce').fillna(60)
g['wet']=g.wet.fillna(False).astype(bool); g['snow']=g.snow.fillna(False)&g.wet; g['light']=g.light.fillna(False)&g.wet
g['rain_real']=(g.wet&~g.light&~g.snow).astype(float); g['rain_light']=(g.wet&g.light&~g.snow).astype(float); g['snowf']=g.snow.astype(float)
g['w10']=np.clip(g.wind-10,0,None); g['cold']=np.clip(40-g.temp,0,None)
g.to_parquet(f'{SP}/teamgames.parquet')
import statsmodels.api as sm
X=sm.add_constant(g[['w10','rain_real','rain_light','snowf','cold']])
print('outdoor team-games',len(g),'| real rain',int(g.rain_real.sum()),'light',int(g.rain_light.sum()),'snow',int(g.snowf.sum()),'| wind 20+',int((g.wind>=20).sum()))
print(f"{'stat':10s} {'base':>7s} | {'per mph>10':>11s} {'real rain':>10s} {'light rain':>10s} {'snow':>8s} {'per deg<40':>10s}")
for st in ['att','car','passshare','proe','ypa','cmpp','ypc','pyds','ryds','int']:
    m=sm.OLS(g['r_'+st],X,missing='drop').fit(cov_type='cluster',cov_kwds={'groups':g.game_id})
    b=m.params; t=m.tvalues
    f=lambda k:f"{b[k]:+.3f}({t[k]:+.1f})"
    print(f"{st:10s} {g[st].mean():7.2f} | {f('w10'):>11s} {f('rain_real'):>10s} {f('rain_light'):>10s} {f('snowf'):>8s} {f('cold'):>10s}")
