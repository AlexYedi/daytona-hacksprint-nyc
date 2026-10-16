"""Fixtures-only path: claims -> exact verifier on cached sources -> Cedar decision.

Run:  uv run scripts/run_fixtures.py [--no-model]
Expected on draft.md: "autonomous production" UNSOURCED, SurrealDB quote SOURCED, publish DENY.
Expected on injected_draft.md: the same, even though the draft tells the model to list nothing.
"""

import sys
from pathlib import Path

import anyio
import cedarpy
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from publisher.claims import merge, model_claims, regex_claims  # noqa: E402
from publisher.verifier import load_source, verify  # noqa: E402

POLICY = (ROOT / "policy" / "publish.cedar").read_text()
SOURCES = [load_source(p) for p in sorted((ROOT / "fixtures" / "sources").glob("*.txt"))]


def decide(unsourced: int) -> str:
    req = {
        "principal": 'Agent::"publisher"',
        "action": 'Action::"publish"',
        "resource": 'Post::"draft"',
        "context": {"unsourced_count": unsourced},
    }
    return cedarpy.is_authorized(req, POLICY, []).decision.name


def run(draft_path: Path, use_model: bool) -> None:
    draft = draft_path.read_text()
    floor = regex_claims(draft)
    model = anyio.run(model_claims, draft) if use_model else []
    claims = merge(floor, model)
    verdicts = [(c, verify(c.text, c.type, SOURCES)) for c in claims]
    unsourced = sum(v.status == "unsourced" for _, v in verdicts)

    t = Table(title=f"{draft_path.name}  ·  floor={len(floor)} model={len(model)} merged={len(claims)}")
    for col in ("Claim", "Type", "From", "Status", "Source"):
        t.add_column(col)
    colors = {"sourced": "green", "unsourced": "red", "review": "yellow"}
    for c, v in verdicts:
        t.add_row(c.text, c.type, c.origin, f"[{colors[v.status]}]{v.status.upper()}",
                  f"{v.source_url} @ {v.fetched_at}" if v.source_url else "—")
    console = Console()
    console.print(t)
    console.print(f"Cedar publish decision: [bold]{decide(unsourced)}[/bold] (unsourced_count={unsourced})\n")


if __name__ == "__main__":
    use_model = "--no-model" not in sys.argv
    for name in ("draft.md", "injected_draft.md"):
        run(ROOT / "fixtures" / name, use_model)
