# Contributing to Kaizen-3C / benchmarks

Thanks for considering a contribution. This benchmark suite is designed to be **architecture-agnostic** — we welcome additions from any agent stack (Aider, smolagents, OpenHands, Cursor, custom in-house systems), and we welcome new metrics, new libraries, and reproductions of our published numbers.

## License

By contributing to this repository, you agree that your contributions will be licensed under the **MIT License** (the same license that covers the rest of this repository — see [`LICENSE`](LICENSE)). You retain copyright in your contributions; you are granting the project and its users an MIT-license grant.

## Developer Certificate of Origin (DCO)

We use the **Developer Certificate of Origin** (DCO) to attest that contributors have the right to submit their work under the project's license. The DCO is a lightweight, sign-your-commits convention used by the Linux kernel, Docker, Kubernetes, and many other major OSS projects.

The full text is at <https://developercertificate.org>. In summary, by signing off on a commit you are certifying that:

1. The contribution was created by you, OR
2. The contribution is based on previous work that, to the best of your knowledge, is covered under an appropriate open-source license that allows you to submit it under this project's license, OR
3. The contribution was provided directly to you by some other person who certified (1), (2), or (3), and you have not modified it.

**To sign off**, add `-s` to your git commit:

```bash
git commit -s -m "feat: add foo benchmark adapter"
```

Git will append a `Signed-off-by: Your Name <you@example.com>` trailer to your commit message. PRs without DCO sign-off will be asked to amend before merge.

## What we welcome

### New architectures in the matrix

The simplest path:

1. Add `commit0/baselines/<your_arch>.py` — a runner that produces a per-library JSON matching the schema in [`commit0/CAMPAIGN_README.md`](commit0/CAMPAIGN_README.md#result-schema).
2. Add `commit0/baselines/run_lite_<your_arch>.py` — sweeps the 16 lite libs.
3. Run the four analysis scripts (`value_add_fingerprint.py`, `compare_baselines.py`, `cache_analysis.py`, `value_add_table.py`). They auto-pick up your results.
4. Open a PR with: your runner, your results JSONs in `commit0/results/`, and a short note in the PR description on what your architecture's value-add fingerprint looks like vs. the existing baselines.

We will help you debug if the numbers look off — open a draft PR early and we will engage.

### New libraries beyond the commit0 lite split

The harness is library-agnostic. Most contributions just modify the sweep script's `LITE_ORDER` list or add a `--only` argument. Open an issue first if the library has unusual dependencies (e.g., requires GPU, requires a non-Python toolchain) so we can advise on test-runner plumbing.

### New metrics

Open an issue with: the proposed metric, why it surfaces an architectural dimension the existing metrics don't, and a sketch of how it would be computed from the existing per-lib JSON output. We prefer metrics that are computable from the *existing* result schema rather than requiring a re-run.

### Reproductions of our published numbers

If you re-run the campaign and your numbers diverge significantly from [`commit0/CAMPAIGN_README.md`](commit0/CAMPAIGN_README.md#expected-aggregate-numbers-within-sampling-noise), please open an issue with:

- Your environment (WSL2 vs native Linux vs macOS, Python version, Docker version, commit0 version)
- Your provider model strings (the slugs differ between litellm and raw API)
- Your spend per architecture
- The sweep wall-time

We will help debug and update the reproducibility doc with whatever we learn.

### New sub-benchmarks

If you have a benchmark that fits the value-add-fingerprint frame (measurable per-cell, comparable across architectures, bounded budget), open an issue describing it before opening a PR. Sub-benchmarks are a larger commitment to maintain — we want to make sure the protocol holds up before we accept it into the repo.

## What we may decline

- **Cosmetic-only PRs** (whitespace, README typos that don't affect meaning, "fixed grammar" sweeps). We will fix typos when we see them ourselves; please save your effort for substantive contributions.
- **Architecture-specific tuning** in the shared scripts. If a runner needs special handling for one architecture, that handling lives in the architecture's own runner, not in shared infrastructure.
- **Removal of named architectural blockers.** If you find a way past one of our published architectural ceilings (e.g., the marshmallow attribute-access ceiling at [`commit0/AAR_2026-04-22_B3_ADDENDUM.md`](commit0/AAR_2026-04-22_B3_ADDENDUM.md) blocker #7), we want to *add* your finding to the literature, not silently delete the ceiling claim.

## Code style

- Python: PEP 8; 4-space indent; type hints encouraged but not required for benchmark scripts.
- Markdown: 80-char soft wrap; ATX-style headings (`#`, not underlines).
- Commit messages: imperative mood; conventional-commit prefixes (`feat:`, `fix:`, `docs:`, `chore:`) preferred but not enforced.

## Where to ask questions

- **General:** GitHub Discussions (when enabled) or open an issue with the `question` label.
- **Methodology:** open an issue with the `methodology` label; cite the specific document, table row, or analysis script you have questions about.
- **Reproducibility issues:** see the "Reproductions" section above.
- **Anything else:** hello@kaizen-3c.dev.

## Code of conduct

Be civil. Disagree with ideas, not people. Assume good faith. If you encounter behavior that violates this principle, contact the maintainers at hello@kaizen-3c.dev.

We may adopt a more formal code of conduct (Contributor Covenant or similar) as the contributor base grows. Until then: be kind, be specific, and remember that everyone is doing their best.

---

Thank you for contributing.
