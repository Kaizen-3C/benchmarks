# Architectural context — mirrored ADRs

The three ADRs in this directory are **mirrored from the private `kaizen-delta` dev monorepo** so this benchmarks repo is self-explanatory. They document the architectural decisions that produced the benchmark protocols you'll find in `commit0/`, `round_trip/`, and `realworld/`.

| ADR | Subject | Authoritative source |
|---|---|---|
| [`ADR-0059-realworld-dr-benchmark.md`](ADR-0059-realworld-dr-benchmark.md) | Real-world disaster-recovery benchmark — protocol and rationale | kaizen-delta `.architecture/decisions/` |
| [`ADR-0060-commit0-greenfield-benchmark.md`](ADR-0060-commit0-greenfield-benchmark.md) | commit0 adoption + amendments — gate criteria, lite-first decision, post-AAR findings | kaizen-delta `.architecture/decisions/` |
| [`ADR-0063-round-trip-fidelity-benchmark.md`](ADR-0063-round-trip-fidelity-benchmark.md) | Code → ADR → Code round-trip benchmark — Q1–Q4 metrics, 5 gates, remediation engine | kaizen-delta `.architecture/decisions/` |

## On mirroring

These files are **kept verbatim** — same content as the source. The authoritative versions live in the `kaizen-delta` private repo, where they're integrated with the rest of the architectural record (60+ ADRs spanning the full Kaizen platform). When the source ADRs are amended, the copies here are updated as part of the same release.

If you find a discrepancy between a copy here and the source (e.g., links pointing into kaizen-delta's wider docs that don't exist in this repo), please open an issue — we'll fix it.

## Why mirror at all

This benchmarks repo is designed to stand alone — usable by anyone evaluating any agent architecture, with no dependency on kaizen-delta's broader documentation. The ADRs explain *why* the benchmark protocols are shaped the way they are: which alternatives we considered, which we rejected, which gate criteria we set, and which amendments we made after running campaigns. That context is essential for anyone trying to extend the matrix or critique the methodology.
