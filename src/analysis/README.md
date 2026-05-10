# `src/analysis/` — Step 5: SERD validation + plotting

Read-only post-hoc analysis on persisted sim data. Nothing here
mutates the simulator; everything reads from ClickHouse and emits
either a numerical report (SERD) or a figure (plots).

| File | Purpose |
|---|---|
| `serd.py` | Structural-Entropy Role Discovery (Gomez-Cram et al. 2026): build maker→taker net-flow network from `agent_fills`, assign quartile roles, compute ROI per role, head-to-head vs DBSCAN+KMeans baseline |
| `comparison.py` | Sim-vs-real price-path comparison metrics |
| `plots.py` | matplotlib + seaborn — 6 paper figures, headless (`Agg`), saves PNG + PDF to `figures/` |

## Public API

```python
from src.analysis.serd import (
    analyze_sim, build_network, node_strengths,
    assign_quartile_roles, roi_by_role, monotonic_descending,
    delta_roi, ENV_MAKER_AGENT_ID, ROLES,
)
from src.analysis.comparison import (
    pearson, real_price_path, compare_paths, direction_correct,
)
```

## CLI

```bash
python -m src.analysis.serd --sim-id <hex>      # SERD report
python -m src.analysis.plots --sim-id <hex>     # 6 figures (Stage D)
```

See `tests/test_analysis_serd.py` for the executable contract.
SERD's filter against (a) the synthetic env-maker (`agent_id =
999_999`) and (b) self-loops (m == t) is part of the contract.
