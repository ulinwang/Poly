# `src/thesis/` — Step 8: Paper helpers

Markdown + LaTeX table generators consumed by the paper outline at
`docs/PAPER.md`. Pure ClickHouse + JSON readers; no compute beyond
formatting.

| File | Purpose |
|---|---|
| `tables.py` | `render_wallet_population`, `render_serd_roles`, `render_vs_baseline`, `render_priors_summary` — each returns `(markdown_str, latex_str)` |

## Public API

```python
from src.thesis.tables import (
    render_wallet_population, render_serd_roles,
    render_vs_baseline, render_priors_summary,
)
```

## CLI

```bash
python -m src.thesis.tables --slug <slug> --sim-id <hex>
python -m src.thesis.tables --slug <slug> --output-dir tables/
```

Outputs `tab1`-`tab4` as `.md` + `.tex` pairs. The LaTeX wrapper uses
`booktabs` (`\toprule`, `\midrule`, `\bottomrule`) and `\caption` /
`\label` for direct `\input{...}` into the thesis manuscript.
