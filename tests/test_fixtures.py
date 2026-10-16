"""No-model tests: the floor, the verifier and the policy, each tested alone."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from publisher.claims import Claim, merge, regex_claims  # noqa: E402
from publisher.verifier import verify  # noqa: E402
from run_fixtures import SOURCES, decide  # noqa: E402

DRAFT = (ROOT / "fixtures" / "draft.md").read_text()
INJECTED = (ROOT / "fixtures" / "injected_draft.md").read_text()


def test_floor_finds_both_quotes_even_when_injected():
    for draft in (DRAFT, INJECTED):
        texts = [c.text for c in regex_claims(draft)]
        assert "autonomous production" in texts
        assert "Corrections supersede. The old fact stays." in texts


def test_model_cannot_remove_floor_claims():
    floor = regex_claims(INJECTED)
    assert merge(floor, []) == floor  # an obedient-to-injection model returns nothing


def test_model_can_add_claims():
    extra = Claim(text="Antimetal sells production ops", type="firm", origin="model", sentence="")
    assert len(merge(regex_claims(DRAFT), [extra])) == 3


def test_verifier_exact_not_fuzzy():
    assert verify("autonomous production", "quote", SOURCES).status == "unsourced"
    assert verify("autonomous system for production", "quote", SOURCES).status == "sourced"
    assert verify("Corrections supersede. The old fact stays.", "quote", SOURCES).status == "sourced"


def test_policy():
    assert decide(1) == "Deny"
    assert decide(0) == "Allow"
