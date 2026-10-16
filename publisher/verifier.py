"""Verifier: exact match only, pure Python, no network, no model.

Quoted words are a claim that someone said or wrote exactly these words, so
fuzzy matching is wrong here: "autonomous production" would pass against
"autonomous system for production" at a high fuzzy score. This module is the
code that later runs inside the Daytona quarantine sandbox.
"""

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class Source(BaseModel):
    url: str
    fetched_at: str
    text: str


class Verdict(BaseModel):
    claim: str
    type: str
    status: Literal["sourced", "unsourced", "review"]
    source_url: str | None = None
    fetched_at: str | None = None
    excerpt: str | None = None


def normalize(s: str) -> str:
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = re.sub(r"[*_#`>\[\]]", " ", s)  # markdown punctuation from the fetch
    return re.sub(r"\s+", " ", s).strip().lower()


def load_source(path: Path) -> Source:
    raw = path.read_text()
    head, _, body = raw.partition("\n---\n")
    meta = dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)
    return Source(url=meta["url"], fetched_at=meta["fetched_at"], text=body)


def verify(claim_text: str, claim_type: str, sources: list[Source]) -> Verdict:
    if claim_type != "quote":
        # Firm/person statements need judgment; flagged for Alex, not auto-passed.
        return Verdict(claim=claim_text, type=claim_type, status="review")
    needle = normalize(claim_text).strip(" .")
    for src in sources:
        hay = normalize(src.text)
        i = hay.find(needle)
        if i != -1:
            return Verdict(
                claim=claim_text, type=claim_type, status="sourced",
                source_url=src.url, fetched_at=src.fetched_at,
                excerpt=hay[max(0, i - 60): i + len(needle) + 60],
            )
    return Verdict(claim=claim_text, type=claim_type, status="unsourced")
