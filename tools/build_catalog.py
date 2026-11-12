#!/usr/bin/env python3
"""Build a machine-readable provider catalog from the Free-LLM README tables.

Reads README.md (Quick Reference + Permanent/Renewable/Trial tables) and the
per-provider code-examples/ directories, then writes providers.json next to
this script. Pure stdlib, read-only with respect to the README.

Usage: python3 tools/build_catalog.py [--readme README.md] [--out providers.json]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = {
    "PERMANENT": "permanent",
    "RENEWABLE": "renewable",
    "TRIAL": "trial",
}


def _split_row(line: str) -> list[str]:
    """Split a markdown table row on unescaped pipes."""
    cells, buf, i = [], [], 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if c == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _cell_links(cell: str) -> tuple[str, list[str]]:
    """Return (plain text, [urls]) for a markdown table cell."""
    urls = re.findall(r"\((https?://[^)]+)\)", cell)
    text = re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)", r"\1", cell)
    text = text.replace("\\", "").strip()
    return text, urls


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(end, i)
    return text[i:j] if j >= 0 else text[i:]


def _table_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = _split_row(line)
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if not cells:
            continue
        if all(set(c) <= set(":- ") and c for c in cells):
            continue  # header separator
        rows.append(cells)
    return rows


def parse_quickref(readme: str) -> dict[str, dict]:
    block = _between(readme, "<!--TABLE:QUICKREF:START-->", "<!--TABLE:QUICKREF:END-->")
    out = {}
    for cells in _table_rows(block):
        if len(cells) < 3:
            continue
        name_text, _ = _cell_links(cells[0])
        base_text, _ = _cell_links(cells[1])
        key_text, key_urls = _cell_links(cells[2])
        base = base_text.strip("`").strip()
        out[name_text.lower()] = {
            "name": name_text,
            "base_url": base,
            "key_url": key_urls[0] if key_urls else "",
        }
    return out


def parse_categories(readme: str) -> dict[str, dict]:
    out = {}
    for marker, category in CATEGORIES.items():
        block = _between(readme, f"<!--TABLE:{marker}:START-->", f"<!--TABLE:{marker}:END-->")
        for cells in _table_rows(block):
            if len(cells) < 2:
                continue
            name_text, name_urls = _cell_links(cells[0])
            if not name_text or name_text.lower() == "provider":
                continue
            card = cells[1].strip().lower()
            rec = out.setdefault(name_text.lower(), {"name": name_text, "categories": []})
            rec["categories"].append(category)
            rec["provider_url"] = name_urls[0] if name_urls else rec.get("provider_url", "")
            rec["card_required"] = card not in ("no", "none", "")
            if category == "permanent" and len(cells) >= 6:
                rec["rate_limit"] = cells[2]
                rec["daily_limit"] = cells[3]
                rec["monthly_limit"] = cells[4]
                rec["models"] = [m.strip() for m in cells[5].split(",") if m.strip()]
            elif category == "renewable" and len(cells) >= 5:
                rec["rate_limit"] = cells[2]
                rec["free_offer"] = cells[3]
                rec["models"] = [m.strip() for m in cells[4].split(",") if m.strip()]
            elif category == "trial" and len(cells) >= 5:
                rec["credit_amount"] = cells[2]
                rec["expiry"] = cells[3]
                rec["models"] = [m.strip() for m in cells[4].split(",") if m.strip()]
    return out


def _example_model(slug: str) -> tuple[str | None, str | None]:
    """Extract (base_url, model) from a provider's curl.sh example."""
    curl = ROOT / "code-examples" / slug / "curl.sh"
    if not curl.exists():
        return None, None
    text = curl.read_text(encoding="utf-8", errors="replace")
    url = re.search(r"curl\s+\"?((https?://[^ \"\\?]+))", text)
    model = re.search(r'"model"\s*:\s*"([^"]+)"', text)
    return (url.group(1) if url else None), (model.group(1) if model else None)


def _slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _match_slug(name: str, by_norm: dict) -> str:
    """Prefer the code-examples directory slug over a synthesized one."""
    n = re.sub(r"[^a-z0-9]", "", name.lower())
    if n in by_norm:
        return by_norm[n]
    for norm, slug in by_norm.items():
        if norm.startswith(n) or n.startswith(norm):
            return slug
    return _slugify(name)


def build(readme_path: Path) -> dict:
    readme = readme_path.read_text(encoding="utf-8", errors="replace")
    quickref = parse_quickref(readme)
    categories = parse_categories(readme)

    # Index code-example slugs by normalized name for matching.
    example_dirs = {p.name for p in (ROOT / "code-examples").iterdir() if p.is_dir()}
    by_norm = {}
    for slug in example_dirs:
        by_norm[re.sub(r"[^a-z0-9]", "", slug.lower())] = slug

    providers = []
    seen = set()
    for key, cat in categories.items():
        name = cat["name"]
        slug = _match_slug(name, by_norm)
        qr = quickref.get(key, {})
        base_url = qr.get("base_url", "")
        ex_base, ex_model = _example_model(slug)
        models = cat.get("models", [])
        if ex_model and ex_model not in models:
            models.append(ex_model)
        rec = {
            "slug": slug,
            "name": name,
            "categories": cat["categories"],
            "card_required": cat.get("card_required"),
            "provider_url": cat.get("provider_url", ""),
            "base_url": base_url,
            "key_url": qr.get("key_url", ""),
            "models": models,
            "example_model": ex_model or (models[0] if models else None),
            "openai_compatible": bool(base_url and "generativelanguage" not in base_url
                                      and "cohere.ai/v2" not in base_url
                                      and "api.cloudflare.com" not in base_url),
            "rate_limit": cat.get("rate_limit"),
            "daily_limit": cat.get("daily_limit"),
            "monthly_limit": cat.get("monthly_limit"),
            "free_offer": cat.get("free_offer"),
            "credit_amount": cat.get("credit_amount"),
            "expiry": cat.get("expiry"),
            "code_examples": f"code-examples/{slug}" if slug in example_dirs else None,
        }
        providers.append(rec)
        seen.add(key)

    # Quick Reference entries with no category table (local tools etc.).
    for key, qr in quickref.items():
        if key in seen:
            continue
        slug = _match_slug(qr["name"], by_norm)
        ex_base, ex_model = _example_model(slug)
        providers.append({
            "slug": slug,
            "name": qr["name"],
            "categories": [],
            "card_required": None,
            "provider_url": "",
            "base_url": qr["base_url"],
            "key_url": qr["key_url"],
            "models": [ex_model] if ex_model else [],
            "example_model": ex_model,
            "openai_compatible": bool(qr["base_url"]),
            "rate_limit": None, "daily_limit": None, "monthly_limit": None,
            "free_offer": None, "credit_amount": None, "expiry": None,
            "code_examples": f"code-examples/{slug}" if slug in example_dirs else None,
        })

    providers.sort(key=lambda r: (r["categories"] == [], r["name"].lower()))
    return {
        "source": "https://github.com/nejib1/Free-LLM",
        "source_readme": str(readme_path),
        "provider_count": len(providers),
        "providers": providers,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--readme", default=str(ROOT / "README.md"))
    ap.add_argument("--out", default=str(ROOT / "providers.json"))
    args = ap.parse_args()
    catalog = build(Path(args.readme))
    Path(args.out).write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    counts: dict[str, int] = {}
    for p in catalog["providers"]:
        for c in p["categories"] or ["uncategorized"]:
            counts[c] = counts.get(c, 0) + 1
    print(f"wrote {args.out}: {catalog['provider_count']} providers {counts}")


if __name__ == "__main__":
    main()
