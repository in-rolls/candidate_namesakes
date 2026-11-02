"""Parse archived ECI constituency pages into the india-votes-data CSV layout.

Reads data/raw/wayback/*.jsonl.gz only, never the network. Each page holds
one table (S.N., Candidate, Party, EVM Votes, Postal Votes, Total Votes, % of
Votes) ending in a NOTA row and a Total row; the header names the
constituency ("1 - Ichchapuram") and the counting status ("Round 22/22").
Checks, per page: the final round is reached, the Total row equals the sum of
the rows, and NOTA is present; per state: every seat is present once.

    python -m candidate_namesakes.parse_wayback
"""

import gzip
import json
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from candidate_namesakes.fetch_wayback import ELECTIONS, RAW

EXTRACTED = Path("data/extracted/wayback")
CONSTITUENCY = re.compile(r"Assembly Constituency\s*(\d+)\s*-\s*(.+?)\s*\(")
ROUNDS = re.compile(r"Round,?\s*(\d+)\s*/\s*(\d+)")
STATE_ABBREVIATIONS = {"S01": "AP", "S02": "AR", "S18": "OD", "S21": "SK"}


def number(text):
    text = text.replace(",", "").strip()
    return int(text) if text.isdigit() else None


def parse_page(html):
    """(constituency_no, constituency, rows, checks) for one page."""
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ").split())
    match = CONSTITUENCY.search(text)
    rounds = ROUNDS.search(text)
    rows, total = [], None
    for tr in soup.find("table").find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if any(cell.lower() == "total" for cell in cells[:2]):
            # The Total row: EVM, postal, total; the largest number is the total.
            numbers = [n for n in map(number, cells) if n is not None]
            total = max(numbers) if numbers else total
            continue
        if len(cells) < 6:
            continue
        if not cells[0].isdigit():
            continue
        rows.append(
            {
                "serial_no": int(cells[0]),
                "candidate": cells[1],
                "party": cells[2],
                "evm_votes": number(cells[3]),
                "postal_votes": number(cells[4]),
                "total_votes": number(cells[5]),
            }
        )
    # An uncontested seat (Arunachal Pradesh, 2024) lists its one candidate
    # with no NOTA row and no vote count.
    uncontested = len(rows) == 1 and rows[0]["total_votes"] is None
    checks = {
        "final_round": bool(rounds) and rounds.group(1) == rounds.group(2),
        "has_nota": uncontested or any(r["candidate"].upper() == "NOTA" for r in rows),
        "total_matches": uncontested
        or total == sum(r["total_votes"] or 0 for r in rows),
    }
    return (
        (int(match.group(1)) if match else None),
        (match.group(2) if match else None),
        rows,
        checks,
    )


def main():
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    for folder, code, seats, state in ELECTIONS:
        path = RAW / f"{folder}_{code}.jsonl.gz"
        pages = {}
        with gzip.open(path, "rt", encoding="utf-8") as lines:
            for line in lines:
                record = json.loads(line)
                if record["ok"]:
                    pages[record["url"]] = record
        frames, failed = [], []
        for url, record in pages.items():
            number_, name, rows, checks = parse_page(record["html"])
            if not rows or not all(checks.values()):
                failed.append((url, checks, len(rows)))
            frame = pd.DataFrame(rows)
            frame["constituency_no"], frame["constituency"] = number_, name
            frame["snapshot"] = record["snapshot"]
            frames.append(frame)
        table = pd.concat(frames, ignore_index=True)
        table.insert(0, "election_state", STATE_ABBREVIATIONS[code])
        table.insert(0, "election_type", "Assembly")
        table.insert(0, "election_year", 2024)
        seats_found = table.constituency_no.nunique()
        print(
            f"{state}: {seats_found}/{seats} seats, {len(table)} rows, "
            f"{len(failed)} pages failing a check"
        )
        for url, checks, n in failed[:5]:
            print("   ", url, checks, n)
        out = EXTRACTED / f"2024Assembly-{STATE_ABBREVIATIONS[code]}.csv"
        columns = ["election_year", "election_type", "election_state", "constituency"]
        columns += ["constituency_no", "serial_no", "candidate", "party", "evm_votes"]
        columns += ["postal_votes", "total_votes", "snapshot"]
        table[columns].sort_values(["constituency_no", "serial_no"]).to_csv(
            out, index=False
        )


if __name__ == "__main__":
    main()
