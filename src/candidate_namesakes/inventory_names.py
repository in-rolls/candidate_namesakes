"""Write docs/names.md: what the name fields carry besides a name, by source.

Every pinned input (local candidate tables and TCPD) is parsed with
``parse.parse_name``; the page reports, per source, the share of distinct
printed names from which each kind of material was taken out, with examples.

    python -m candidate_namesakes.inventory_names
"""

import json
from pathlib import Path

import pandas as pd

from candidate_namesakes.count_namesakes import update_readme
from candidate_namesakes.parse import parse_name

FIELDS = {
    "title": "Title (DR, SHRI, SMT, KUMARI, श्रीमती, TMT)",
    "relation": "Relation and relative (S/O, W/O, पत्नी)",
    "aliases": "Alias (URF, ALIAS, @, उर्फ, (எ), A/B)",
    "sec_number": "SEC numbering of namesakes ((1), -2, II)",
    "notes": "Bracketed or other notes (nickname, caste, symbol, number)",
    "repairs": "Repaired typing slip (zero for O, comma-reversed order)",
    "initials": "Has initials",
    "is_placeholder": "Placeholder, not a name (VACANT, NOTA)",
}
PAGE = Path("docs/names.md")


def sources(source):
    for item in source["inputs"]:
        names = pd.read_parquet(item["path"], columns=["candidate_name"]).candidate_name
        yield item["state"], names, item["numbering"]
    for item in source["tcpd"]:
        names = pd.read_csv(item["path"], usecols=["Candidate"], low_memory=False)
        yield f"TCPD {item['election'].replace('_', ' ')}", names.Candidate, False


def filled(value):
    if isinstance(value, (tuple, list)):
        return bool(value)
    return bool(value) and not pd.isna(value)


def main():
    source = json.loads(Path("data/source.json").read_text())
    shares, examples = {}, {}
    for label, names, numbering in sources(source):
        distinct = names.dropna().astype(str).unique()
        parsed = [parse_name(raw, numbering) for raw in distinct]
        frame = pd.DataFrame([p.__dict__ for p in parsed])
        hits = {f: frame[frame[f].map(filled)] for f in FIELDS}
        shares[label] = {f: 100 * len(h) / len(frame) for f, h in hits.items()}
        shares[label]["distinct names"] = len(frame)
        for field, hit in hits.items():
            sample = hit.sample(min(2, len(hit)), random_state=1) if len(hit) else hit
            examples.setdefault(field, []).extend(
                f"`{r.raw}` → name `{r.name}`" for r in sample.itertuples()
            )
    table = pd.DataFrame(shares).rename(
        index={**FIELDS, "distinct names": "Distinct printed names"}
    )
    order = ["Distinct printed names", *FIELDS.values()]
    lines = [
        table.loc[order]
        .reset_index(names="Material")
        .to_markdown(index=False, floatfmt=".2f")
    ]
    lines.append("")
    lines.append("Examples (two per source where any):")
    lines.append("")
    for field, label in FIELDS.items():
        lines.append(f"- **{label}**: " + "; ".join(examples.get(field, [])[:8]))
    update_readme("\n".join(lines), marker="inventory", path=PAGE)
    print(lines[0])


if __name__ == "__main__":
    main()
