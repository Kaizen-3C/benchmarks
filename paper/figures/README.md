# Paper Figures

## Figure 1 — Value-Add Fingerprint Heatmap

**Generator:** [`figure1_fingerprint_heatmap.py`](figure1_fingerprint_heatmap.py)
**Outputs:** `figure1.pdf` (vector, publication-quality), `figure1.png` (300 DPI raster)
**First rendered:** 2026-04-25 (Day 3)

### What it shows

Two-panel figure. Rows: 16 commit0-lite libraries (floor libs in **bold + asterisk**). Columns: 6 (architecture × provider) cells.

- **Panel A (Value-add):** color = pass-rate Δ vs. single-shot baseline (`value_add_pp`). Diverging RdBu_r centered at zero. Each cell annotated with pass-rate (top) and value-add (bottom).
- **Panel B (LLM-lean):** color = log₁₀ of cost ratio vs. single-shot baseline. Sequential YlOrRd. Annotated with the multiplier (e.g., `1.9×`, `100×`).
- **Hatched grey cells** = not run (OH-Sonnet covered only 6 of 16 libs).
- **Red "no" cells** = OH ran but did not resolve.

### Key visual readings

| Reading | Where to look |
|---|---|
| KD-Sonnet on `deprecated` is cheaper than baseline at +38pp | Panel A upper-left, blue cell; Panel B same cell at 0.5× |
| OH-GPT cracks cross-import floor libs (+100pp) | Panel A right column, deep blue on voluptuous/marshmallow/jinja/simpy/imapclient |
| Reflexion regressed Sonnet | Panel A B3-S column, mostly red |
| OH unbounded-cost failure on pyjwt-Sonnet | Panel B `pyjwt × OH-S` cell at 100× |
| Bounded vs. unbounded cost asymmetry | Panel B KD/B3 columns (cool tones) vs. OH columns (hot tones) |

### Regeneration

```bash
py -3.12 benchmarks/paper/figures/figure1_fingerprint_heatmap.py
```

Reads from `benchmarks/commit0/results/`. No arguments. Idempotent.

### Phase 1 extension (planned 2026-05-22)

When Aider and smolagents land per [PHASE1_COST_REVIEW.md](../PHASE1_COST_REVIEW.md), edit the `COLS` list in `figure1_fingerprint_heatmap.py`:

```python
COLS = [
    ("KD-S",  "kd",  "anthropic"),
    ("KD-G",  "kd",  "openai"),
    ("B3-S",  "b3",  "anthropic"),
    ("B3-G",  "b3",  "openai"),
    ("Aid-S", "aider",      "anthropic"),    # NEW
    ("Aid-G", "aider",      "openai"),       # NEW
    ("Sm-S",  "smolagents", "anthropic"),    # NEW
    ("Sm-G",  "smolagents", "openai"),       # NEW
    ("OH-S",  "oh",  "anthropic"),
    ("OH-G",  "oh",  "openai"),
]
```

The `cell_for()` function will need a new branch per architecture (mirror the `kd` / `b3` branches). Per-library JSONs at `benchmarks/commit0/results/{lib}_aider_{provider}.json` etc. are expected (matches the KD naming convention).

The figure size will widen from 13" to ~17" once 4 columns are added; adjust `figsize` accordingly.

### Cell coverage (current state, 2026-04-25)

| Status | Count | % |
|---|---:|---:|
| Populated (rate + value-add) | 76 | 79% |
| OH unresolved (`no`) | 8 | 8% |
| Not run (`n/r`) | 12 | 13% |
| **Total** | **96** | **100%** |

After Phase 1 extension: 16 libs × 10 cells = 160 cells; expected populated ≥ 75%.

### Top extremes (2026-04-25 data)

**Strongest positive cells (all OH-G floor-lib unlocks):**
- OH-G voluptuous +100pp
- OH-G simpy +100pp
- OH-G imapclient +100pp
- OH-G marshmallow +100pp
- OH-G jinja +100pp

**Strongest negative cells (all B3 — Reflexion's weakness signature):**
- B3-S tinydb −88pp
- B3-G wcwidth −79pp
- B3-S wcwidth −74pp
- B3-S pyjwt −63pp
- B3-G portalocker −50pp

These two extreme lists, side-by-side, are the headline reading: each architecture's weakness is a different architecture's strength. The §5.2 paper section ("complementary-weakness cells") cites this figure directly.

### Anonymization note

For the ICLR 2027 D&B double-blind submission version (per [PLAN.md](../PLAN.md) §5):
- `KD-S` / `KD-G` labels stay (not brand-identifying — "per-file Kaizen-delta decompose" can be relabeled "PFD-S / PFD-G" — Per-File Decompose).
- Architecture descriptions in the paper body can describe the technique without naming Kaizen-3C.
- The arXiv version retains the KD labels and brand attribution.

Tracked under [`anonymization-checklist.md`](../anonymization-checklist.md) (created at Phase 2).
