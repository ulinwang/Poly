import json, glob, os
import pandas as pd
import numpy as np

# Roman Roy resolved NO -> winning_idx=1 -> YES pays 0. signal_mu prior=0.15.
# "direction correct" = yes_mid moved toward 0 (down from seed ~0.155).
ROWS=[]
for suite in ['b2','b3','b4']:
    idx=json.load(open(f'output/v13/{suite}/index.json'))
    for r in idx['runs']:
        eid=r.get('exp_id')
        if not eid: continue
        base=f'output/v13/{suite}/{eid}'
        act=pd.read_parquet(f'{base}/raw/agent_actions.parquet')
        # action mix
        n=len(act)
        mix=act['action_type'].value_counts(normalize=True).to_dict() if 'action_type' in act else {}
        # yes_mid trajectory: column yes_mid_after
        ymcol = 'yes_mid_after' if 'yes_mid_after' in act else None
        yf = float(act.sort_values('tick_idx')[ymcol].iloc[-1]) if ymcol and len(act) else float('nan')
        # seed yes_mid from meta
        m=json.load(open(f'{base}/meta.json'))
        smu=m.get('priors_summary',{}).get('signal_mu',float('nan'))
        ROWS.append(dict(
            suite=suite, name=r['name'], n_act=n,
            yes_mid_final=round(yf,4),
            signal_mu=smu,
            dir_correct=bool(yf<0.15) if yf==yf else None,
            cancel_pct=round(100*mix.get('CANCEL',0),1),
            limit_pct=round(100*mix.get('LIMIT',0),1),
            market_pct=round(100*mix.get('MARKET',0),1),
            hold_pct=round(100*mix.get('HOLD',0),1),
            belief_pct=round(100*mix.get('UPDATE_BELIEF',0),1),
        ))
df=pd.DataFrame(ROWS)
pd.set_option('display.width',200); pd.set_option('display.max_rows',40)
print(df.to_string(index=False))
df.to_csv('output/v13/v13_metrics.csv',index=False)
print("\n--- B2 seed variance (yes_mid_final) ---")
b2=df[df.suite=='b2']['yes_mid_final']
print(f"mean={b2.mean():.4f} std={b2.std():.4f} range=[{b2.min():.4f},{b2.max():.4f}]")
print("\n--- B3 persona ablation (mean yes_mid_final, mean cancel%) ---")
for grp in ['archetype','marginal','uniform']:
    g=df[df.name.str.contains(grp)]
    print(f"{grp:10s} yes_mid={g.yes_mid_final.mean():.4f}±{g.yes_mid_final.std():.4f}  cancel%={g.cancel_pct.mean():.1f}  dir_correct={g.dir_correct.sum()}/{len(g)}")
print("\n--- B4 belief ablation ---")
for grp in ['belief_off','belief_on']:
    g=df[df.name.str.contains(grp)]
    print(f"{grp:11s} cancel%={g.cancel_pct.mean():.1f}  belief%={g.belief_pct.mean():.1f}  yes_mid={g.yes_mid_final.mean():.4f}  dir_correct={g.dir_correct.sum()}/{len(g)}")
