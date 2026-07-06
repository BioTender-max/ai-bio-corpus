#!/usr/bin/env python3
"""Stage 4: Apply full filter to all sources → papers_master.csv

Sources:
- PMLR ICML 2018-2023 (via prefilter → abstracts)  
- NIPS 2010-2025 (via prefilter → abstracts)
- OpenReview ICLR 2019-2026, ICML 2024-2026, NeurIPS 2023-2025 (with primary_area)
"""

import json
import os
import csv
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filter_pipeline import filter_papers, compute_hits

CORPUS = "/mnt/shared-workspace/corpus_v1/titles"
PREFILTER = "/mnt/shared-workspace/corpus_v1/prefilter"
OUT_DIR = "/mnt/shared-workspace/corpus_v1/master"
os.makedirs(OUT_DIR, exist_ok=True)


def load_pmlr_nips_with_abstracts():
    """Load PMLR + NIPS papers with fetched abstracts."""
    path = f"{PREFILTER}/candidates_with_abstracts.json"
    if not os.path.exists(path):
        print(f"[SKIP] No abstracts file yet at {path}", flush=True)
        return []
    return json.load(open(path))


def load_openreview():
    """Load all OpenReview checkpoints (ICLR 2019-2026, ICML 2024-2026, NeurIPS 2023-2025)."""
    all_papers = []
    src = f"{CORPUS}/openreview"
    # ICML 2026 (special — separate file)
    for fname in os.listdir(src):
        if not fname.endswith(".json"):
            continue
        if fname == "icml_2026.json":
            data = json.load(open(f"{src}/{fname}"))
            for p in data:
                venue_field = p.get("venue_field", "") or p.get("venue", "")
                if "Submitted" in venue_field:
                    continue  # skip submitted for ICML 2026
                p2 = dict(p)
                p2["venue"] = "ICML"
                p2["year"] = 2026
                p2["source"] = "openreview_v2"
                all_papers.append(p2)
        elif fname.startswith("checkpoint_v3_") or fname.startswith("checkpoint_v2_"):
            # Extract venue-year from filename: checkpoint_v3_ICLR.cc_2024_Conference.json
            base = fname.replace("checkpoint_v3_", "").replace("checkpoint_v2_", "").replace(".json", "")
            # e.g. "ICLR.cc_2024_Conference" → venue=ICLR, year=2024
            parts = base.split("_")
            venue = parts[0].split(".")[0]  # ICLR
            year = int(parts[1])
            data = json.load(open(f"{src}/{fname}"))
            for p in data:
                # Check we have needed fields (id, forum, title)
                if not p.get("title"):
                    continue
                p2 = dict(p)
                p2["venue"] = venue
                p2["year"] = year
                p2["source"] = "openreview_v1" if year <= 2023 else "openreview_v2"
                all_papers.append(p2)
    return all_papers


def normalize_paper(p: dict) -> dict:
    """Normalize schema across sources.
    
    Common fields: title, abstract, authors, keywords, venue, year, source, paper_page, forum_id
    """
    # Common fields
    title = p.get("title", "")
    abstract = p.get("abstract", "")
    authors = p.get("authors", [])
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(",")]
    keywords = p.get("keywords", []) or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",")]
    venue = p.get("venue", "")
    year = p.get("year", None)
    source = p.get("source", "")
    
    # Source-specific fields
    if source == "pmlr":
        paper_page = p.get("paper_page", "")
        pdf_url = p.get("pdf_url", "")
        forum_id = ""
        primary_area = ""
    elif source == "nips":
        paper_page = p.get("paper_page", "")
        pdf_url = ""
        forum_id = ""
        primary_area = ""
    else:  # openreview
        forum_id = p.get("id", "") or p.get("forum", "")
        paper_page = f"https://openreview.net/forum?id={forum_id}" if forum_id else ""
        pdf_url = f"https://openreview.net/pdf?id={forum_id}" if forum_id else ""
        primary_area = p.get("primary_area", "")

    return {
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "keywords": keywords,
        "venue": venue,
        "year": year,
        "source": source,
        "primary_area": primary_area,
        "forum_id": forum_id,
        "paper_page": paper_page,
        "pdf_url": pdf_url,
    }


def main():
    print("[STAGE 4] Build master corpus", flush=True)
    
    # Load all sources
    pmlr_nips = load_pmlr_nips_with_abstracts()
    openreview = load_openreview()
    
    print(f"  PMLR/NIPS with abstracts: {len(pmlr_nips)}")
    print(f"  OpenReview: {len(openreview)}")
    
    # Normalize
    all_papers = [normalize_paper(p) for p in pmlr_nips + openreview]
    print(f"  Total normalized: {len(all_papers)}")
    
    # Deduplicate by (venue, year, title) — same paper may appear in multiple OR searches
    seen = {}
    for p in all_papers:
        key = (p["venue"], p["year"], p["title"].lower()[:200])
        if key not in seen:
            seen[key] = p
    dedup = list(seen.values())
    print(f"  After dedup: {len(dedup)}")
    
    # Apply filter
    kept, stats = filter_papers(dedup)
    print(f"\n  Kept: {len(kept)}")
    print(f"  Stats: {dict(stats)}")
    
    # Distribution by venue-year
    by_vy = defaultdict(int)
    for p in kept:
        by_vy[(p["venue"], p["year"])] += 1
    print("\n  Venue-year distribution:")
    for (v, y), c in sorted(by_vy.items()):
        print(f"    {v} {y}: {c}")
    
    # Save master corpus
    out_json = f"{OUT_DIR}/papers_master.json"
    with open(out_json, "w") as f:
        json.dump(kept, f, ensure_ascii=False, indent=1)
    print(f"\n[WRITE] {out_json} ({os.path.getsize(out_json)/1e6:.1f} MB)")
    
    # Save CSV for easy viewing
    out_csv = f"{OUT_DIR}/papers_master.csv"
    if kept:
        fields = ["venue", "year", "title", "authors", "tags", "primary_area", "source", "forum_id", "paper_page", "keep_reason", "hit_terms"]
        with open(out_csv, "w") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader()
            for p in kept:
                w.writerow({
                    "venue": p.get("venue", ""),
                    "year": p.get("year", ""),
                    "title": p.get("title", ""),
                    "authors": "; ".join(p.get("authors", []) if isinstance(p.get("authors"), list) else []),
                    "tags": ",".join(p.get("_tags", [])),
                    "primary_area": p.get("primary_area", ""),
                    "source": p.get("source", ""),
                    "forum_id": p.get("forum_id", ""),
                    "paper_page": p.get("paper_page", ""),
                    "keep_reason": p.get("_keep_reason", ""),
                    "hit_terms": ",".join(p.get("_hit_terms", [])),
                })
        print(f"[WRITE] {out_csv} ({os.path.getsize(out_csv)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
