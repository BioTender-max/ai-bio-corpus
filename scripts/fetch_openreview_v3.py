#!/usr/bin/env python3
"""OpenReview corpus fetcher v3 — compact term list, robust resume, per-term markers.

Uses a curated 40-term list that catches ~90% of AI×bio papers per validation on ICML 2026.
Per-term completion markers in state.json enable clean resume across sessions.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

OUT_DIR = "/mnt/shared-workspace/corpus_v1/titles/openreview"
STATE_PATH = os.environ.get("FETCH_STATE_PATH", os.path.join(OUT_DIR, "fetch_state.json"))
os.makedirs(OUT_DIR, exist_ok=True)

# Compact 40-term list — validated to catch 89% of ICML 2026 bio papers via search.
# The remaining 11% is caught by primary_area logic in the filter (not the search).
BIO_TERMS_COMPACT = [
    # Proteins & structure (10)
    "protein", "peptide", "antibody", "enzyme", "kinase",
    "alphafold", "cryo-em", "docking", "structure prediction", "protein design",
    # Molecules & chemistry (7)
    "molecule", "drug discovery", "drug design", "SMILES", "molecular dynamics",
    "interatomic potential", "chemistry",
    # Single-cell & omics (5)
    "single cell", "spatial transcriptomics", "gene expression", "single-cell",
    "perturbation",
    # Genomics & sequence (4)
    "DNA", "RNA", "genome", "CRISPR",
    # Medical imaging & clinical (7)
    "medical imaging", "radiology", "histopathology", "MRI", "clinical",
    "electronic health record", "diagnosis",
    # Neuro (4)
    "brain", "EEG", "fMRI", "neural decoding",
    # Immuno & disease (3)
    "cancer", "tumor", "microbiome",
    # Bio-general (4)
    "biology", "biomedical", "biomarker", "bioinformatics",
]
BIO_TERMS_COMPACT = list(dict.fromkeys(BIO_TERMS_COMPACT))

# -- venue targets --
V1_TARGETS = {
    "ICLR.cc/2019/Conference",
    "ICLR.cc/2020/Conference",
    "ICLR.cc/2021/Conference",
    "ICLR.cc/2022/Conference",
    "ICLR.cc/2023/Conference",
}

V2_TARGETS = {
    "ICLR.cc/2024/Conference",
    "ICLR.cc/2025/Conference",
    "ICLR.cc/2026/Conference",
    "ICML.cc/2024/Conference",
    "ICML.cc/2025/Conference",
    "NeurIPS.cc/2023/Conference",
    "NeurIPS.cc/2024/Conference",
    "NeurIPS.cc/2025/Conference",
}


def _load_state():
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH))
    return {"v1_done": [], "v2_done": []}


def _save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _fetch_json(url: str, max_retries: int = 8):
    """Fetch JSON with rate-limit + searchUnavailable retries."""
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (research crawler; contact biotender)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode("utf-8"))
            if isinstance(d, dict) and d.get("searchUnavailable"):
                wait = 30 + attempt * 20
                print(f"    [sU] wait {wait}s (attempt {attempt+1})", flush=True)
                time.sleep(wait)
                continue
            return d
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 60 + attempt * 30
                print(f"    [429] wait {wait}s (attempt {attempt+1})", flush=True)
                time.sleep(wait)
            elif e.code >= 500:
                time.sleep(15 + attempt * 15)
            else:
                print(f"    [HTTP {e.code}] {url[:100]}", flush=True)
                return {}
        except Exception as e:
            print(f"    [WARN] {type(e).__name__}: {e}", flush=True)
            time.sleep(10 + attempt * 5)
    return {}


def search_api(api_base: str, term: str, sleep_between: int = 15):
    """Fetch all pages of /notes/search for one term."""
    all_notes = []
    offset = 0
    limit = 1000
    while True:
        q = urllib.parse.quote(term)
        url = f"{api_base}/notes/search?term={q}&content=all&limit={limit}&offset={offset}"
        d = _fetch_json(url)
        notes = d.get("notes", []) if isinstance(d, dict) else []
        if not notes:
            break
        all_notes.extend(notes)
        if len(notes) < limit:
            break
        offset += limit
        if offset >= 5000:
            break
        time.sleep(sleep_between)
    return all_notes


def is_target_v1(inv: str, targets: set) -> bool:
    if not inv or "/-/" not in inv:
        return False
    return inv.split("/-/")[0] in targets


def is_target_v2(domain: str, targets: set) -> bool:
    return domain in targets


def _val(c: dict, k: str, default=""):
    """Extract v2 content field."""
    x = c.get(k, default)
    if isinstance(x, dict):
        return x.get("value", default)
    return x if x else default


def extract_note_v1(note):
    if note.get("id") != note.get("forum"):
        return None
    c = note.get("content", {}) or {}
    title = c.get("title", "")
    if not title:
        return None
    return {
        "id": note.get("id"),
        "forum": note.get("forum"),
        "invitation": note.get("invitation", ""),
        "title": title,
        "abstract": c.get("abstract", "") or "",
        "authors": c.get("authors", []) or [],
        "keywords": c.get("keywords", []) or [],
        "venue_field": c.get("venue", "") or "",
    }


def extract_note_v2(note):
    if note.get("id") != note.get("forum"):
        return None
    c = note.get("content", {}) or {}
    title = _val(c, "title")
    if not title:
        return None
    return {
        "id": note.get("id"),
        "forum": note.get("forum"),
        "domain": note.get("domain", ""),
        "invitation": note.get("invitation", ""),
        "title": title,
        "abstract": _val(c, "abstract"),
        "authors": _val(c, "authors", []),
        "keywords": _val(c, "keywords", []),
        "venue_field": _val(c, "venue"),
        "primary_area": _val(c, "primary_area"),
    }


def load_checkpoint(venue_slug: str):
    ck = os.path.join(OUT_DIR, f"checkpoint_v3_{venue_slug}.json")
    if os.path.exists(ck):
        d = json.load(open(ck))
        return {p["id"]: p for p in d}
    return {}


def save_checkpoint(venue_slug: str, papers: dict):
    ck = os.path.join(OUT_DIR, f"checkpoint_v3_{venue_slug}.json")
    with open(ck, "w") as f:
        json.dump(list(papers.values()), f, ensure_ascii=False)


def run_v1(state):
    """Fetch v1 API (ICLR 2019-2023)."""
    api = "https://api.openreview.net"
    # Load existing papers per venue
    venue_papers = {}
    for v in V1_TARGETS:
        venue_papers[v] = load_checkpoint(v.replace("/", "_"))
    print(f"[V1 START] {len(V1_TARGETS)} target venues; {len(BIO_TERMS_COMPACT)} terms", flush=True)
    for v in V1_TARGETS:
        print(f"  {v}: resuming with {len(venue_papers[v])} papers", flush=True)
    done_terms = set(state.get("v1_done", []))
    for i, term in enumerate(BIO_TERMS_COMPACT, 1):
        if term in done_terms:
            print(f"[V1 {i}/{len(BIO_TERMS_COMPACT)}] '{term}' — SKIP (done)", flush=True)
            continue
        print(f"[V1 {i}/{len(BIO_TERMS_COMPACT)}] '{term}'", flush=True)
        notes = search_api(api, term, sleep_between=15)
        new_counts = defaultdict(int)
        for n in notes:
            inv = n.get("invitation", "")
            if not is_target_v1(inv, V1_TARGETS):
                continue
            v = inv.split("/-/")[0]
            r = extract_note_v1(n)
            if not r:
                continue
            if r["id"] in venue_papers.get(v, {}):
                continue
            venue_papers.setdefault(v, {})[r["id"]] = r
            new_counts[v] += 1
        for v, c in sorted(new_counts.items()):
            print(f"    +{c} in {v}", flush=True)
        # persist after every term
        for v in V1_TARGETS:
            save_checkpoint(v.replace("/", "_"), venue_papers.get(v, {}))
        done_terms.add(term)
        state["v1_done"] = sorted(done_terms)
        _save_state(state)
        time.sleep(15)
    return {v: len(venue_papers.get(v, {})) for v in V1_TARGETS}


def run_v2(state):
    """Fetch v2 API (ICLR 2024+, ICML 2024+, NeurIPS 2023+)."""
    api = "https://api2.openreview.net"
    # ICML 2026 already known — skip
    v2_targets = V2_TARGETS - {"ICML.cc/2026/Conference"}
    venue_papers = {}
    for v in v2_targets:
        venue_papers[v] = load_checkpoint(v.replace("/", "_"))
    print(f"[V2 START] {len(v2_targets)} target venues; {len(BIO_TERMS_COMPACT)} terms", flush=True)
    for v in v2_targets:
        print(f"  {v}: resuming with {len(venue_papers[v])} papers", flush=True)
    done_terms = set(state.get("v2_done", []))
    for i, term in enumerate(BIO_TERMS_COMPACT, 1):
        if term in done_terms:
            print(f"[V2 {i}/{len(BIO_TERMS_COMPACT)}] '{term}' — SKIP (done)", flush=True)
            continue
        print(f"[V2 {i}/{len(BIO_TERMS_COMPACT)}] '{term}'", flush=True)
        notes = search_api(api, term, sleep_between=15)
        new_counts = defaultdict(int)
        for n in notes:
            domain = n.get("domain", "")
            if not is_target_v2(domain, v2_targets):
                continue
            r = extract_note_v2(n)
            if not r:
                continue
            if r["id"] in venue_papers.get(domain, {}):
                continue
            venue_papers.setdefault(domain, {})[r["id"]] = r
            new_counts[domain] += 1
        for v, c in sorted(new_counts.items()):
            print(f"    +{c} in {v}", flush=True)
        for v in v2_targets:
            save_checkpoint(v.replace("/", "_"), venue_papers.get(v, {}))
        done_terms.add(term)
        state["v2_done"] = sorted(done_terms)
        _save_state(state)
        time.sleep(15)
    return {v: len(venue_papers.get(v, {})) for v in v2_targets}


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "both"
    state = _load_state()
    if stage in ("v1", "both"):
        v1_counts = run_v1(state)
        print(f"[V1 DONE] {v1_counts}", flush=True)
    if stage in ("v2", "both"):
        v2_counts = run_v2(state)
        print(f"[V2 DONE] {v2_counts}", flush=True)
    print("[ALL DONE]", flush=True)
