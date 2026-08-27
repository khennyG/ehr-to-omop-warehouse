# 0004: A synthetic demo population and vocabulary seed

**Status:** Accepted

## Context

This pipeline needs two inputs to run: a Synthea-format patient population, and an
OHDSI vocabulary (SNOMED CT, RxNorm, LOINC — the concept tables `VocabularyMapper`
resolves source codes against). Neither is available without external dependencies I
don't have on hand: real Synthea generation needs a JVM and Synthea's own jar; a real
Athena vocabulary export needs a licensed account at athena.ohdsi.org and can run to
multiple gigabytes.

## Decision

`scripts/generate_demo_data.py` and `scripts/build_demo_vocabulary.py` produce a
synthetic stand-in for both — a demo-scale population and a hand-picked vocabulary
subset — so the pipeline runs against real data and produces real numbers, rather
than staying theoretical. `scripts/generate_synthea_data.py` and
`scripts/download_vocabularies.py` are the actual production paths (real Synthea jar,
real Athena download) and are written to the same standard as everything else here —
I just can't personally run them without a JVM and a licensed account.

Two details worth being specific about, because they're the difference between an
honest demo and a misleading one:

- **The demo vocabulary's source codes are real.** SNOMED CT, RxNorm, and LOINC codes
  in `scripts/demo_codes.py` are genuine, established codes for common conditions,
  drugs, and labs — not invented. What's *not* real is the concept_id each one
  resolves to: matching a source code to its true Athena-assigned concept_id needs
  the actual Athena export. Rather than guess at a number and risk it being read as
  fact, every concept_id in the demo vocabulary is assigned in the range OMOP itself
  reserves for exactly this situation — `concept_id >= 2,000,000,000` is the standing
  convention for concepts that aren't from an Athena release.
- **The vocabulary is deliberately incomplete.** A couple of source codes the
  generator emits — one condition, one drug — have no matching row in the demo
  vocabulary at all, on purpose. Real vocabularies always have coverage gaps; a demo
  where every single code maps successfully would make the mapping-coverage report
  and the vocabulary Sankey diagram trivially uninteresting; a demo with a small, real
  gap gives that reporting something genuine to show.

## Alternatives considered

**Ship the pipeline unexecuted, with a note that it needs Synthea + Athena to run.**
This is roughly where the project started. I moved away from it because a pipeline
that's never been run is a pipeline whose bugs haven't been found — and several were,
this way: a circular vocabulary foreign key, pandas silently corrupting the literal
string `"None"` (OMOP's actual vocabulary_id for concept_id 0) into `NaN` on read, a
NOT NULL violation on open-ended prescriptions, a stray non-OMOP column nearly making
it into a loaded table. None of those would have surfaced without actually running
extract through load against real data.

**A trivially small hand-written fixture (a dozen patients) instead of a generator.**
Would have been faster to build, but wouldn't exercise the pipeline at any real scale
— the 500x-slow vocabulary lookup and the 470x-slow bulk-insert path (see ADR 0001)
only became visible once the demo population was large enough to matter, a few
thousand patients and several hundred thousand observations.

## Consequences

Cloning this repo and running `scripts/build_demo_vocabulary.py` →
`scripts/generate_demo_data.py` → `python -m src.main --stage all` produces a
complete, working OMOP warehouse with no external downloads. The tradeoff is that
none of the demo numbers — cohort sizes, mapping coverage percentages, the DQD
scorecard — represent a real population; they're what this specific synthetic
generator happened to produce with its particular sampling weights and a fixed
random seed. That's the right tradeoff for a portfolio project meant to demonstrate
the pipeline works, and the wrong one to mistake for a real-world finding.
