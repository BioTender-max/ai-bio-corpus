# AI×Biology Corpus — Methodology

## Overview

3,722 AI×biology papers from ICLR (2019-2026), ICML (2018-2026), and NeurIPS (2010-2025), curated using a two-stage keyword-based filter pipeline.

Validated against a 315-paper manual reference for ICML 2026: **95.9% recall**.

## Data sources

| Venue | Years | Source | Method |
|---|---|---|---|
| ICLR | 2019-2026 | OpenReview API | Full metadata (title, abstract, keywords, primary_area) |
| ICML | 2018-2023 | PMLR (proceedings.mlr.press) | Titles only, then per-candidate abstract fetch |
| ICML | 2024-2026 | OpenReview API | Full metadata |
| NeurIPS | 2010-2022 | papers.nips.cc | Titles only, then per-candidate abstract fetch |
| NeurIPS | 2023-2025 | OpenReview API | Full metadata |

## Pipeline

### Stage 1: Title harvest

- **OpenReview** paths use a 44-term compact keyword list. The OpenReview `/notes/search` API is queried per term per venue, with searchUnavailable / 429 backoff (30-90s exponential).
- **PMLR / papers.nips.cc** paths scrape each year's landing page for title + author + DOI.

### Stage 2: Title-level pre-filter

For PMLR/NIPS titles only. The same 44-term compact keyword list is applied to titles. Any title matching at least one term is a candidate. On ICML 2026 held-out data, this pre-filter has **~89% recall** vs a longer 151-term list.

Compact term list (44):

- **Core biology**: protein, molecule, drug, ligand, biology, biomedical
- **Cell**: single cell, gene expression, spatial transcriptomics, perturbation
- **Genomics**: DNA, RNA, genome, CRISPR
- **Structure**: molecular dynamics, structure prediction, protein language model, protein design
- **Chemistry-adjacent**: SMILES, chemistry, force field, boltzmann generator
- **Clinical & medical**: medical imaging, radiology, histopathology, MRI, clinical, electronic health record, diagnosis
- **Neuroscience**: brain, EEG, fMRI, neural decoding
- **Immune & disease**: cancer, tumor, microbiome, biomarker, bioinformatics

### Stage 3: Abstract fetch

For PMLR/NIPS candidates only. Each candidate's paper page is fetched to extract the abstract. This turned 6,722 PMLR + 26,749 NIPS titles into 1,183 candidates with full abstracts (a ~30x reduction that made the abstract fetch tractable).

### Stage 4: Full filter classifier

Applied to `title + abstract + keywords + primary_area`. See `filter_pipeline.py`. Key logic:

1. **Grouped keyword hits**: 12 groups (protein, molecule, single_cell, genomics, md_structbio, clinical, neuro, medical_imaging, oncology, immuno, drug_discovery, health_medicine). Each hit records the group and matched term.

2. **Area classification**:
   - `text_specialized`: 3+ groups hit + 5+ total terms → **keep**
   - `text_multi_group`: 2 groups → **keep**
   - `text_high_spec_focused`: 1 group + high-spec term + focused → **keep**
   - `text_strong_hit`: strong signal from a single group → **keep**
   - `chem_bio`: chemistry-adjacent → requires strict-bio signal or specific chem-adjacent-with-bio terms
   - `neuro_bio`: neuro-adjacent → requires neuro/clinical group hit or `high_spec`
   - `health_medicine`: primary_area is applications/health-medicine → **keep** unless pure pose/surgical
   - `generic_area_strong_hit`: 2+ groups in generic ML area → **keep**
   - `generic_area_focused`: 1 group + high-spec + 2+ total hits → **keep**
   - `generic_area_heavy_bio`: title has bio hint + one group ≥3 hits → **keep**

3. **Title-strong bio override**: unambiguous title terms (`alphafold`, `CRISPR`, `biomarker`, `retinopathy`, `carcinom`, `SMILES`, `EHR`, `microbiome`, `boltzmann generator`, ...) → **keep** regardless of other signals.

4. **False-positive drops**:
   - `pure_materials`: crystals, MOF, weather, PDE solvers, interatomic potentials without any bio signal
   - `brain_false_positive`: "Optimal Brain Surgeon" (model pruning), "brain KV cache", brainstorm
   - `snn_dropped`: spiking neural network implementation papers (no biology, just neuromorphic ML)

### Stage 5: Tag assignment

Every kept paper is tagged with up to 6 topic labels from the same grouped-keyword system. The tag order preserves group priority.

## Validation

Reference: ICML 2026 manually curated corpus of 315 papers.

| Metric | Value |
|---|---|
| Papers kept from ICML 2026 | 348 |
| Overlap with reference | 302 |
| Recall | **95.9%** |
| Missing | 13 |
| Extras | 46 |

Missing papers: mostly chem/materials-adjacent titles (Interatomic Potentials, Molecular Design methods) where the reference is more permissive than our chemistry filter. Recovering them would over-catch pure materials-ML papers.

Extras: nearly all legitimately AI×biology papers that the reference curator manually excluded on editorial grounds (CryoACE, brain-inspired methodology papers, medical AI methodology). Not filter false positives.

## Deduplication

Papers are deduplicated by `(venue, year, title.lower()[:200])`. This handles cases where a paper appears under multiple search terms in the OpenReview index.

## Reproducibility

Complete source code:

- `fetch_openreview_v3.py` — OpenReview search API fetcher with rate-limit handling
- `filter_pipeline.py` — locked filter classifier
- `build_master.py` — deduplication and full-pipeline runner
- `build_site_data.py` — compact JSON export for the site

Raw data (candidate lists with abstracts, OpenReview checkpoints) and outputs (`papers_master.json`, `papers_master.csv`) are shipped with the corpus. The filter runs deterministically on the raw data.

## Caveats

1. **PMLR ICML 2018-2023 are floors.** Only title-level prefilter was applied here; true count is ~10% higher.
2. **OpenReview covers accepted papers only.** Withdrawn/rejected submissions not included.
3. **No workshop papers.** Main-track only.
4. **Editorial boundary is inherent.** Bio-inspired methodology vs "real" AI-biology is a judgment call; our filter is permissive on the boundary.
5. **NeurIPS 2026 not held yet.** Corpus stops at NeurIPS 2025 for that venue.

## Corpus statistics

### By venue
- ICLR: 2181 (58.6%)
- NeurIPS: 895 (24.0%)
- ICML: 646 (17.4%)

### Top tags
- molecule: 1005
- protein: 925
- clinical: 925
- neuro: 916
- genomics: 480
- medical_imaging: 465
- single_cell: 401
- md_structbio: 286
- oncology: 188
- immuno: 91

### Year totals
- 2010: 10, 2011: 5, 2012: 13, 2013: 7, 2014: 9, 2015: 6, 2016: 14, 2017: 18
- 2018: 25, 2019: 60, 2020: 130, 2021: 132, 2022: 220
- 2023: 397, 2024: 532, 2025: 909, 2026: 1235

