#!/usr/bin/env python3
"""Convert papers_master.json to compact papers.json + stats.json for the site."""
import json
import os
from collections import Counter
from datetime import datetime

CORPUS_MASTER = "/mnt/shared-workspace/corpus_v1/master/papers_master.json"
SITE_DATA_DIR = "/workspace/site_dev/data"

os.makedirs(SITE_DATA_DIR, exist_ok=True)


def compact_paper(p):
    """Shrink schema for JSON payload:
    t=title, a=abstract, au=authors, y=year, v=venue, g=tags,
    u=paper_page, d=pdf_url, i=forum_id
    """
    return {
        "t": p.get("title", ""),
        "a": (p.get("abstract", "") or "").strip(),
        "au": p.get("authors", [])[:12] if isinstance(p.get("authors", []), list) else [],
        "y": p.get("year", None),
        "v": p.get("venue", ""),
        "g": p.get("_tags", [])[:6] if p.get("_tags") else [],
        "u": p.get("paper_page", "") or "",
        "d": p.get("pdf_url", "") or "",
    }


def main():
    data = json.load(open(CORPUS_MASTER))
    print(f"Loaded {len(data)} papers from master")

    compact = [compact_paper(p) for p in data]

    # Sort by year desc, then title
    compact.sort(key=lambda x: (-1 * (x["y"] or 0), x["t"]))

    out_papers = f"{SITE_DATA_DIR}/papers.json"
    with open(out_papers, "w") as f:
        json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[WRITE] {out_papers} ({os.path.getsize(out_papers)/1e6:.2f} MB)")

    # Build stats
    by_venue = Counter(p["v"] for p in compact if p["v"])
    by_year = Counter(p["y"] for p in compact if p["y"])
    tag_counter = Counter()
    for p in compact:
        for t in p.get("g", []):
            tag_counter[t] += 1
    tags_sorted = tag_counter.most_common()
    by_venue_year = Counter()
    for p in compact:
        if p["v"] and p["y"]:
            by_venue_year[f"{p['v']}_{p['y']}"] += 1

    stats = {
        "built_at": datetime.now().strftime("%Y-%m-%d"),
        "n_papers": len(compact),
        "by_venue": dict(by_venue),
        "by_year": {str(k): v for k, v in sorted(by_year.items())},
        "by_venue_year": dict(by_venue_year),
        "tags": tags_sorted,
    }
    out_stats = f"{SITE_DATA_DIR}/stats.json"
    with open(out_stats, "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"[WRITE] {out_stats} ({os.path.getsize(out_stats)} bytes)")

    print(f"\nSite build summary:")
    print(f"  Total: {len(compact)}")
    print(f"  By venue: {dict(by_venue)}")
    print(f"  Top tags: {tags_sorted[:10]}")


if __name__ == "__main__":
    main()
