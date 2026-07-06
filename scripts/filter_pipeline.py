#!/usr/bin/env python3
"""V2 filter pipeline — reconstructed and adapted for multi-year corpus.

Filter logic (5-stage):
  1. Title/abstract SNN drop — pure spiking neural network engineering
  2. Bio keyword hit counting across 9 domain groups + high-specificity title terms
  3. Primary_area-based layered filter (only for OpenReview papers with primary_area)
     - health_medicine: unconditional
     - chemistry/physics: needs bio-word hit
     - neuroscience_cognitive: needs neurobio-word hit
     - other ML areas: needs high-specificity title term + 2+ bio group hits
  4. For non-OpenReview papers (PMLR/NIPS): full title+abstract match instead of primary_area
     - Requires title OR abstract to match at least one keyword group
     - AND either title match high-specificity term OR 2+ different bio groups hit
  5. Tag rebuild — 10 tag rules, max 3 tags per paper

Input:  master paper record with title, abstract (if fetched), authors, venue, year,
        keywords (optional), primary_area (optional), invitation
Output: same record + _tags, _hit_terms, _hits, _keep_reason, _area
"""

import json
import re
from collections import defaultdict


# ============================================================
# SNN drop patterns (from ICML 2026 v2 filter, preserved verbatim in docs)
# ============================================================
SNN_TITLE = re.compile(
    r"\b(spik(?:e|ing|es)|snn[s]?|neuromorphic|LIF|integrate.and.fire|"
    r"time.to.first.spike|ann.snn|spike.based)\b",
    re.I,
)
BRAIN_BIO = re.compile(
    r"\b(brain|eeg|fmri|meg|neurodegener|psychiatric|hippocamp|entorhinal|"
    r"cortex|cortical|calcium\s+imag\w*|neuroimag\w*|neural\s+decod|neurophysiolog|"
    r"visual\s+prosthesis|neuronal\s+microenv|multineuron|electroencephal|"
    r"epilepsy|parkinson|alzheimer|neurostimulation|neurosci)\b",
    re.I,
)
BIO_INSPIRED_ML = re.compile(
    r"\b(bio.?inspired|biologically.?plausible|bio.?vision)\b",
    re.I,
)


def is_snn_drop(paper: dict) -> bool:
    """Drop if title matches SNN keywords AND lacks any real biology context."""
    title = paper.get("title", "") or ""
    abstract = paper.get("abstract", "") or ""
    text = f"{title}\n{abstract}"
    if not SNN_TITLE.search(title):
        return False
    # Keep if it also has real brain-bio or bio-inspired context
    if BRAIN_BIO.search(text) or BIO_INSPIRED_ML.search(text):
        return False
    return True


# ============================================================
# Bio keyword groups (9 groups) + high-specificity title terms
# ============================================================

BIO_GROUPS = {
    "protein": re.compile(
        r"\b(protein[s]?|peptide[s]?|antibod(?:y|ies)|enzyme[s]?|kinase[s]?|"
        r"allosteric|binder[s]?|residue[s]?|TCR|MHC|epitope[s]?|"
        r"cryo.?em|alphafold|boltz|esmfold|foldseek|proteomics)\b",
        re.I,
    ),
    "molecule": re.compile(
        r"\b(molecule[s]?|small\s+molecule|drug[s]?|drug\s+(?:discover|design)|"
        r"ligand[s]?|SMILES|pharmacophore|ADMET|SBDD|docking)\b",
        re.I,
    ),
    "md_structbio": re.compile(
        r"\b(molecular\s+dynamic|force\s+field|MLIP|interatomic\s+potential|"
        r"conformation[s]?|hamiltonian\s+flow|boltzmann\s+generator|"
        r"schnet|nequip|mace)\b",
        re.I,
    ),
    "single_cell": re.compile(
        r"\b(single.?cell|scRNA(?:-seq)?|scDNA|spatial\s+transcriptomic|"
        r"gene\s+expression|gene\s+regulator|cell\s+type|cell\s+state|"
        r"perturbation|scGPT|scFoundation|geneformer)\b",
        re.I,
    ),
    "genomics": re.compile(
        r"\b(DNA|RNA|genom(?:e|ic|ics)|gene[s]?|CRISPR|chromatin|"
        r"epigenetic[s]?|epigenom|transcript(?:omic)?|nucleotide[s]?|"
        r"promoter[s]?|enhancer[s]?|regulatory\s+element|variant\s+calling)\b",
    ),
    "medical_imaging": re.compile(
        r"\b(medical\s+imag|medical\s+image|radiolog|histopathology|pathology|"
        r"whole.?slide|CT\s+scan|MRI|X.?ray|chest\s+x.?ray|ultrasound|OCT|"
        r"radiograph)\b",
        re.I,
    ),
    "clinical": re.compile(
        r"\b(clinical|EHR|electronic\s+health|diagnos(?:is|tic)|prognos(?:is|tic)|"
        r"survival\s+analysis|hospital|patient[s]?|ICU|healthcare|health\s+care|"
        r"disease[s]?)\b",
        re.I,
    ),
    "neuro": re.compile(
        r"\b(brain[s]?|EEG|fMRI|MEG|cortex|cortical|hippocamp(?:us|al)|"
        r"neural\s+(?:decod|encod|record|activit)|neurodegener|psychiatric|"
        r"calcium\s+imag\w*|"
        r"neurostimulation|neuroimag\w*|BCI|brain.computer|"
        r"neuronal|electrophysiolog|spike\s+train)\b",
        re.I,
    ),
    "immuno_disease": re.compile(
        r"\b(immune|immunolog|immunotherap|vaccine|virus|viral|"
        r"microbiome|microbial|pathogen|cancer|tumor|tumour|oncolog|"
        r"metastas|carcinoma|leukemia|lymphoma)\b",
        re.I,
    ),
}

# High-specificity terms (very unlikely to be false positive in non-bio ML paper)
HIGH_SPEC_TITLE = re.compile(
    r"\b(protein|peptide|antibod|drug\s+discover|drug\s+design|molecule|ligand|"
    r"single.?cell|scRNA|CRISPR|genome|genomic|clinical|patient|EHR|electronic\s+health|"
    r"radiology|histopath|MRI|CT\s+scan|EEG|fMRI|brain|neuron|cancer|tumor|"
    r"cryo.?em|alphafold|SMILES|SBDD|docking|SNP|GWAS|proteomic|transcriptomic|"
    r"biology|biomedical|bioinformatic|molecular\s+dynamic|interatomic)\b",
    re.I,
)


# ============================================================
# TITLE_STRONG_BIO — overrides area filter, always keep if title matches
# ============================================================
TITLE_STRONG_BIO = re.compile(
    r"\b(antibod|immuno|biolog\w*|"
    r"medical(?:\s|-)|medic(?:ine|al)|pathology|"
    r"scRNA|scDNA|sc(?:Foundation|GPT|Dataset)|"
    r"[-\s]omics\b|omics\s+|transcript|proteomic|"
    r"gene(?:tic|s)?\s+(?:circuit|regulatory|expression)|"
    r"carcinom|leukemia|lymphoma|metastas|oncolog|"
    r"EHR|electronic\s+health|"
    r"radiolog|histopath|whole.?slide|"
    r"CRISPR|"
    r"boltzmann\s+gener|"
    r"drug\s+(?:discover|design)|SBDD|SMILES|"
    r"alphafold|esmfold|"
    r"microbiome|microbial)\b",
    re.I,
)


# ============================================================
# BRAIN_FALSE_POSITIVES — Optimal Brain [Damage/Surgeon] is technique name, not bio
# ============================================================
BRAIN_FP = re.compile(
    r"\b(optimal\s+brain|brain\s+(?:kv\s+cache|damage|surgeon)|"
    r"brainless|brainstorm)\b",
    re.I,
)



# ============================================================
# Tag rules (priority order preserved from ICML 2026 v2 filter)
# ============================================================
TAG_RULES = [
    ("oncology", re.compile(
        r"\b(cancer|oncolog|tumor|tumour|metastas|carcinom|leukemia|lymphoma)\b",
        re.I,
    )),
    ("immuno", re.compile(
        r"\b(immune|immuno|antibod|antigen|vaccine|epitope|TCR|MHC|"
        r"B\s?cell|T\s?cell|virus|microb)\b",
        re.I,
    )),
    ("protein", re.compile(
        r"\bprotein|\bpeptide|\bbinder|\bantibod|\bTCR|enzyme|kinase|allosteric",
        re.I,
    )),
    ("molecule", re.compile(
        r"\bmolecule|small\s+molecule|\bdrug\b|\bligand\b|pharmac|SMILES|"
        r"docking|SBDD",
        re.I,
    )),
    ("md_structbio", re.compile(
        r"boltzmann|molecular\s+dynamic|force\s+field|MLIP|interatomic|"
        r"conformation|hamiltonian",
        re.I,
    )),
    ("genomics", re.compile(
        r"\bDNA\b|\bRNA\b|genom|\bgene\b|CRISPR|transcript|plasmid|"
        r"nucleotide|chromatin",
        re.I,
    )),
    ("single_cell", re.compile(
        r"single.?cell|scRNA|scDNA|cell\s+type|cell\s+state|perturbation|scGPT",
        re.I,
    )),
    ("medical_imaging", re.compile(
        r"\bCT\b|\bMRI\b|X.?ray|histopath|pathology|radiolog|segmentation|"
        r"whole.?slide",
        re.I,
    )),
    ("clinical", re.compile(
        r"clinical|hospital|patient|diagnos|prognos|survival|EHR|"
        r"electronic\s+health|disease",
        re.I,
    )),
    ("neuro", re.compile(
        r"\bbrain\b|\bEEG\b|\bfMRI\b|\bMEG\b|cortex|cortical|hippocamp|"
        r"neural\s+decod|neurostim",
        re.I,
    )),
]

MAX_TAGS_PER_PAPER = 3


# ============================================================
# Primary area categorization (for OpenReview papers)
# ============================================================
def classify_area(primary_area: str) -> str:
    """Classify OpenReview primary_area field into filter buckets."""
    if not primary_area:
        return "no_area"
    pa = primary_area.lower()
    if "health" in pa or "medic" in pa:
        return "health_medicine"
    if "chemistry" in pa or "physics" in pa or "materials" in pa:
        return "chem_bio"
    if "neuroscience" in pa or "cognitive" in pa:
        return "neuro_bio"
    return "generic_area"


# ============================================================
# Main filter
# ============================================================
def compute_hits(paper: dict) -> tuple:
    """Returns (hits_by_group, hit_terms, high_spec_title_match)."""
    title = paper.get("title", "") or ""
    abstract = paper.get("abstract", "") or ""
    keywords_field = paper.get("keywords", []) or []
    if isinstance(keywords_field, list):
        kw_str = " ".join(str(k) for k in keywords_field)
    else:
        kw_str = str(keywords_field)
    haystack = f"{title}\n{abstract}\n{kw_str}"

    hits_by_group = {}
    hit_terms = []
    for group_name, pat in BIO_GROUPS.items():
        matches = pat.findall(haystack)
        if matches:
            hits_by_group[group_name] = len(matches)
            # Grab distinct match strings (lowercased)
            distinct = list(dict.fromkeys(m.lower() if isinstance(m, str) else str(m).lower() for m in matches))
            hit_terms.extend(distinct[:3])  # first 3 per group

    high_spec = bool(HIGH_SPEC_TITLE.search(title))
    return hits_by_group, hit_terms, high_spec


def should_keep(paper: dict) -> tuple:
    """Returns (keep: bool, keep_reason: str, area: str)."""
    # Stage 1: SNN drop
    if is_snn_drop(paper):
        return False, "snn_dropped", "snn"

    hits_by_group, hit_terms, high_spec = compute_hits(paper)
    n_groups = len(hits_by_group)
    total_hits = sum(hits_by_group.values())

    title = paper.get("title", "") or ""
    
    # Stage 1.5: Brain false-positive filter (e.g. "Optimal Brain KV Cache", "Optimal Brain Damage")
    # These are LLM/ML technique names, not biology. Drop unless title has an INDEPENDENT bio signal.
    if BRAIN_FP.search(title):
        # Check for real bio signal outside the BRAIN_FP match
        title_ex_fp = BRAIN_FP.sub("", title)
        real_bio_title = re.search(
            r"\b(protein|antibod|drug|patient|clinical|cancer|tumou?r|"
            r"cortex|cortical|hippocamp|fMRI|EEG|MEG|"
            r"neural\s+(?:activ|decod|encod|record)|neuron|"
            r"medical|biolog|genom|CRISPR|gene\s+expression)\b",
            title_ex_fp, re.I,
        )
        if not real_bio_title:
            return False, "brain_false_positive", "no_area"

    # Stage 2: TITLE_STRONG_BIO override — catches clear bio titles regardless of area
    if TITLE_STRONG_BIO.search(title):
        return True, "title_strong_bio", "override"

    # Stage 3 (OpenReview branch) — if primary_area available
    primary_area = paper.get("primary_area", "")
    if primary_area:
        area = classify_area(primary_area)
        if area == "health_medicine":
            # Reject if title is pose estimation, surgical video, mmWave WITHOUT clinical/patient context
            if re.search(r"\b(human\s+pose|surgical\s+data)\b", title, re.I) and not re.search(r"\b(patient|clinical|diagnos|prognos)\b", title + " " + (paper.get("abstract", "") or ""), re.I):
                return False, "health_medicine_generic", area
            return True, "health_medicine", area
        if area == "chem_bio":
            # chem/physics primary area — bio-adjacent by default in AI×science community
            # Include if: any bio-group hit, high-spec title, or chem-adjacent term (molecul/chem/etc)
            # EXCLUDE pure crystal/materials/PDE/weather (no molecular content at all)
            title = paper.get("title", "") or ""
            abstract = paper.get("abstract", "") or ""
            text = f"{title} {abstract}"
            # Pure materials/PDE/weather patterns — DROP these
            pure_materials = re.compile(
                r"(?:\bcrystal[s]?(?:line)?\b|\bMOF\b|\bmetal.organic\s+framework|\bzeolite|"
                r"\bcatalyst\s+screening|\bcatalyst\s+design|"
                r"\bweather\b|\bclimate\b|\bprecipitation\b|\batmospher\w*|"
                r"\bneural\s+(?:operator|solver)s?\b|\bPDEs?\b|"
                r"\bsymbolic\s+regression|"
                r"\bslab.adsorbate|\bsurface\s+cataly\w*|"
                r"\batomistic\s+GNN|\bmany.body\b|\bchemical\s+reaction\s+network\w*|"
                r"\bstructure.preserving\s+dynamic\w*|"
                r"\bpermutation.invariant\s+macroscopic\w*|"
                r"\brunge.kutta\w*|\binteratomic\s+potentials?\b|"
                r"\benergy.force\s+predictor\w*|"
                r"\bHamiltonians?\s+are\s+(?:Accurate|Learned)|"
                r"\btensor\s+prediction\w*|"
                r"\battention.based\s+ML\s+potential\w*|"
                r"\bforce.field\s+(?:generator|network|neural)|"
                r"\bshake\s+solver|\bsimple\s+neural\s+solver)",
                re.I,
            )
            has_pure_materials = pure_materials.search(text)
            # Bio-adjacent chem terms
            chem_terms = re.compile(
                r"\b(molecul|chemi|synthesi|retrosynth|reaction[s]?|catalys|"
                r"pharmac|nmr|chirality|electronic\s+structur|dft|hamiltonian|"
                r"interatomic|MLIP|conformer|potential\s+energy|boltzmann|"
                r"force\s+field|equivariant|foldable)\b", re.I,
            )
            # Count non-materials-ambiguous bio groups (exclude md_structbio which is bio-adjacent)
            bio_groups_strict = {k: v for k, v in hits_by_group.items() if k != "md_structbio"}
            has_strict_bio = len(bio_groups_strict) >= 1
            # Bio-specific title terms — expanded to catch bio hints in abstracts
            bio_specific = re.compile(
                r"\b(drug|pharm|ligand|protein|peptide|antibod|enzyme|kinase|"
                r"allosteric|residue|amino\s+acid|nucleic\s+acid|"
                r"single.?cell|scRNA|scDNA|"
                r"gene(?:tic)?[s]?\b|genome|genomic|CRISPR|"
                r"clinical|patient|EHR|electronic\s+health|medical|hospital|"
                r"radiolog|histopath|MRI|CT\s+scan|"
                r"EEG|fMRI|brain|neuron|cortex|hippocamp|"
                r"cancer|tumo(?:u)?r|carcinom|leukemia|lymphoma|"
                r"biomolec\w*|biochemi\w*|biophysi\w*|biolog\w*)\b", re.I,
            )
            has_bio_specific = bool(bio_specific.search(text))
            if has_pure_materials and not has_strict_bio and not has_bio_specific:
                # Pure materials/PDE/weather with no bio grounding → drop
                return False, "chem_pure_materials", area
            if n_groups >= 1 or high_spec or chem_terms.search(text):
                return True, "chem_bio", area
            return False, "chem_bio_no_bio", area
        if area == "neuro_bio":
            # Bio-context required for neuroscience_cognitive_science area
            # Keep if: neuro/clinical hit, high_spec title, OR abstract mentions neuroscience/brain/neuron
            title = paper.get("title", "") or ""
            abstract = paper.get("abstract", "") or ""
            neuro_abstract = re.search(
                r"\b(neuroscien\w*|neur(?:al|ons?|ophysio|onal)|brain|cortex|cortical|"
                r"hippocamp|electrophysio|BCI|EEG|fMRI|MEG|spike|firing\s+rate|"
                r"population\s+(?:activit|coding|dynami|geometry))\b",
                abstract, re.I,
            )
            if hits_by_group.get("neuro",0) >= 1 or hits_by_group.get("clinical",0) >= 1 or high_spec or neuro_abstract:
                return True, "neuro_bio", area
            return False, "neuro_no_neurobio", area
        # generic ML area
        if high_spec and n_groups >= 2:
            return True, "generic_area_strong_hit", area
        # Also keep if a single strong group has multiple hits (2+) and title is high-spec
        if high_spec and n_groups >= 1 and total_hits >= 2:
            return True, "generic_area_focused", area
        # Also keep for KAST-BAR style: heavy bio-group hits AND title has any bio hint
        # This avoids false positives from ML methodology papers with "diagnostic" in abstract
        title = paper.get("title", "") or ""
        title_bio_hint = re.search(
            r"\b(brain\w*|EEG|fMRI|neur(?:al|ons?|ophysio|onal)|cortex|cortical|hippocamp\w*|"
            r"protein\w*|peptide\w*|antibod\w*|drug\w*|molecul\w*|ligand\w*|"
            r"patient\w*|clinical\w*|medic\w*|"
            r"cardiac|cardio(?![a-mo-z])|vector.?cardio|comorbid\w*|"
            r"diabet\w*|retinopath\w*|survival\w*|onco\w*|tumo\w*|cancer\w*|"
            r"PPG|physiolog\w*|BCI\b|Video.?BCI|MRI|CT\b|"
            r"gene[s]?\b|genetic\w*|genome\w*|omics|CRISPR)\b", title, re.I,
        )
        if title_bio_hint and (hits_by_group.get("neuro", 0) >= 3 or hits_by_group.get("clinical", 0) >= 3 or hits_by_group.get("protein", 0) >= 3):
            return True, "generic_area_heavy_bio", area
        return False, "generic_area_weak", area

    # Stage 4 (non-OpenReview branch) — no primary_area, use pure text signal
    # Rule: high-spec title match OR 2+ different groups hit
    if high_spec and n_groups >= 2:
        return True, "text_strong_hit", "no_area"
    if high_spec and n_groups >= 1 and total_hits >= 2:
        return True, "text_high_spec_focused", "no_area"
    if n_groups >= 3:
        return True, "text_multi_group", "no_area"
    # A single strong specialized group with multiple hits is also OK for medical/clinical dominant papers
    if any(hits_by_group.get(g, 0) >= 2 for g in ("medical_imaging", "clinical", "neuro", "single_cell", "protein", "molecule")):
        return True, "text_specialized", "no_area"
    return False, "no_bio_signal", "no_area"


def apply_tags(paper: dict) -> list:
    """Assign 0-3 tags following priority order."""
    title = paper.get("title", "") or ""
    abstract = paper.get("abstract", "") or ""
    kw = paper.get("keywords", []) or []
    if isinstance(kw, list):
        kw_str = " ".join(str(k) for k in kw)
    else:
        kw_str = str(kw)
    haystack = f"{title}\n{abstract}\n{kw_str}"
    tags = []
    for tag_name, pat in TAG_RULES:
        if pat.search(haystack):
            tags.append(tag_name)
            if len(tags) >= MAX_TAGS_PER_PAPER:
                break
    return tags


def filter_papers(papers: list) -> list:
    """Run full filter on paper list."""
    kept = []
    stats = defaultdict(int)
    for p in papers:
        keep, reason, area = should_keep(p)
        stats[reason] += 1
        if not keep:
            continue
        hits_by_group, hit_terms, high_spec = compute_hits(p)
        tags = apply_tags(p)
        p_out = dict(p)
        p_out["_tags"] = tags
        p_out["_hit_terms"] = hit_terms
        p_out["_hits"] = hits_by_group
        p_out["_keep_reason"] = reason
        p_out["_area"] = area
        kept.append(p_out)
    return kept, dict(stats)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: filter_pipeline.py <input.json> [output.json]")
        sys.exit(1)
    in_f = sys.argv[1]
    out_f = sys.argv[2] if len(sys.argv) > 2 else in_f.replace(".json", ".filtered.json")
    papers = json.load(open(in_f))
    if isinstance(papers, dict):
        papers = list(papers.values())
    kept, stats = filter_papers(papers)
    with open(out_f, "w") as f:
        json.dump(kept, f, ensure_ascii=False)
    print(f"Input: {len(papers)}, Kept: {len(kept)} → {out_f}")
    print(f"Stats: {stats}")
