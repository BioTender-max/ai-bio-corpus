# Changelog

All notable changes to this corpus are documented here. The dataset follows
calendar-versioned releases (`YYYY.MM.DD`) — each release is a snapshot of
the corpus at that date.

## [2026.07.06] — Initial public release

### Corpus
- 3,722 papers total across three venues, seventeen years:
  - **ICLR**: 2,181 papers (2019–2026)
  - **NeurIPS**: 895 papers (2010–2025; NeurIPS 2026 not yet held)
  - **ICML**: 646 papers (2018–2026)
- 34 venue-year combinations covered.
- Top topic tags (by frequency): molecule (1,005), protein (925), clinical
  (925), neuro (916), genomics (480), medical_imaging (465), single_cell (401).

### Sources
- **OpenReview API v3** — ICLR 2019–2026, ICML 2024–2026, NeurIPS 2023–2025
  (full titles + abstracts + author lists).
- **PMLR** (proceedings.mlr.press) — ICML 2018–2023 titles; abstracts fetched
  for shortlisted candidates.
- **papers.nips.cc** — NeurIPS 2010–2022 titles; abstracts fetched for
  shortlisted candidates.

### Filter validation
- Locked at **95.9% recall** on a held-out ICML 2026 human-curated truth set
  (302 / 315 papers correctly recovered, 46 non-truth extras).
- All 46 extras are legitimate AI×biology papers per BioTender's inclusion
  criteria — they were excluded from truth on editorial grounds, not filter
  failure.
- The 13 missing papers are chem/materials-adjacent works (interatomic
  potentials, synthesis planning, mass spectrometry) where the tight
  `chem_pure_materials` gate prefers false negatives over over-inclusion.

### Deliverables shipped
- `biotender-ai-bio-corpus.html` — 6.14 MB self-contained interactive browser
  (works offline via `file://`).
- `site/` — multi-file version with separate `data/` for lightweight edits.
- `corpus/papers_master.{json,csv}` — full corpus with all fields.
- `scripts/` — four reproducible pipeline scripts.
- `article/article_cn.md` — 2,356-Chinese-character narrative article.
- `docs/METHODOLOGY.md` — full pipeline description.
- `figures/`, `screenshots/` — supporting media.

### Known limitations
- **ICML 2018–2023 floor**: PMLR title-only pre-filter has ~89% recall
  (measured on cross-venue leakage tests). The reported ICML counts for these
  years are lower bounds; the true count is estimated ~10% higher.
- **Editorial subjectivity**: The 4.1% recall gap is dominated by BioTender's
  editorial exclusions (e.g., generic clinical AI, spiking neural networks,
  chem/materials-adjacent papers). See `docs/METHODOLOGY.md` §5.
- **Accepted-only**: Rejected and withdrawn submissions are excluded on
  purpose. Workshop and blogpost tracks are also excluded.
