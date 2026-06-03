# Thesis / Research Artifact Decoupling

> **Status:** Decoupling prepared — `.gitignore` updated, files NOT deleted yet.
> **Next steps:** A future pass will run `git filter-repo` or `git rm --cached` to remove thesis blobs from Git history.

---

## 1. What was decoupled

The following directories and file patterns are now excluded from the code repository. They belong in a **separate thesis/research-data repository**.

| Path / Pattern | Size (approx.) | Contents |
|---|---|---|
| `docs/` | 3.3 GB | LaTeX thesis source, compiled PDFs, publication figures, tables, TIFFs |
| `data/clustering/` | 2.8 GB | Clustering intermediate matrices, wallet feature parquet files, cluster profiles JSON |
| `output/` | 1.7 GB | Per-experiment output trees (parquet dumps, per-run figures, summaries, run logs) |
| `comparison/` `comparison_*/` | 1.6 MB+ | Cross-run comparison reports and artifacts |
| `figures/` `tables/` | varies | Legacy v7-era artifact directories |
| `*.pdf`, `*.png`, `*.tiff`, `*.svg` | - | Publication-ready raster/vector images |
| `*.parquet` | - | Any remaining data exports |
| `data/wallet_features_*.parquet` | - | Feature-engineering exports from ClickHouse |
| `data/wallet_clusters_*.parquet` | - | Cluster-assignment exports |

### Regenerable experiment artifacts (also excluded)

These are produced by experiment suites and can be regenerated on demand:

- `data/priors_*.json`
- `data/personas_*.json`
- `data/runs/`

---

## 2. Why decouple?

1. **Repository size** — The thesis artifacts add ~7.5 GB to the working tree and inflate clone times.
2. **Open-source focus** — The code repo (agent/, environment/, experiments/, webapp/) should remain lean and focused on the simulation platform.
3. **Access control & versioning** — Thesis content (drafts, figures, reviewer feedback) has different collaboration needs than production code.
4. **Clean history** — Removing large binaries from Git history will shrink the `.git` object database significantly.

---

## 3. Where thesis content lives now

- **Physical files:** Still present locally in `/Users/moonshot/Projects/Poly/polymetl/` (not deleted).
- **Git tracking:** The updated `.gitignore` prevents *new* commits of these files.
- **Future home:** A separate repository (name TBD, e.g. `poly-thesis` or `polymetl-research`) will host:
  - `docs/` — LaTeX source + compiled PDFs
  - `data/clustering/` — Frozen clustering results
  - `output/` — Tagged experiment snapshots
  - `figures/` `tables/` — Publication assets

---

## 4. How to link the two repos (if someone wants both)

### Option A — Sibling directories (recommended for development)

```text
Poly/
├── polymetl/          ← code repo (this repo)
├── poly-thesis/       ← thesis repo (future)
│   ├── docs/
│   ├── output/
│   └── figures/
```

Symlink from thesis repo into code repo (optional):

```bash
cd /path/to/polymetl
ln -s ../poly-thesis/docs docs
ln -s ../poly-thesis/output output
```

*(Remember to keep the symlinks in `.gitignore` so they are not committed.)*

### Option B — Git submodules (if you need pinned versions)

```bash
cd /path/to/polymetl
git submodule add https://github.com/<user>/poly-thesis.git thesis
```

This is heavier; use only if you need reproducible paper snapshots tied to specific code versions.

---

## 5. Current tracked-file impact

As of the decoupling date, Git still tracks these thesis files:

- **123 files** under `docs/`, `data/clustering/`, `output/`
- **57 files** matching `*.pdf`, `*.png`, `*.tiff`, `*.svg`, `*.parquet`

These will disappear from the *index* (not from working tree) once a maintainer runs:

```bash
cd /Users/moonshot/Projects/Poly/polymetl
# Remove from index only (working tree untouched)
git rm -r --cached docs/ data/clustering/ output/ comparison/ figures/ tables/
# Or, for a full history rewrite (shrinks .git/):
# git filter-repo --path docs/ --path data/clustering/ --path output/ --invert-paths
```

> **Note:** `git filter-repo` requires the `git-filter-repo` tool (`pip install git-filter-repo`).

---

## 6. Checklist before running history rewrite

- [ ] Back up the repo (or push all branches to a remote).
- [ ] Inform collaborators so they can re-clone or rebase after the force-push.
- [ ] Decide whether to move files to the new thesis repo *before* or *after* the rewrite.
- [ ] Update CI / docs references if any hardcoded paths point to `docs/` or `output/`.

---

*Prepared by: Git cleanup pass*
