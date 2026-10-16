"""Smoke test: one live call per sponsor, pass/fail table, no secrets printed.

Run:  uv run scripts/smoke.py
Rule from the build plan: any red goes to cache/stub immediately; no second attempt before lunch.
"""

import os
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

import certifi

# uv's standalone Python can't see the macOS keychain; the Daytona SDK then fails TLS.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
OUT = ROOT / "smoke_out"
OUT.mkdir(exist_ok=True)

DEMO_URL = "https://antimetal.com"
DEMO_PHRASE = "autonomous system for production"


def check_daytona():
    """Quarantine sandbox: no network, upload text, run a verifier, prove egress is blocked."""
    from daytona import CreateSandboxFromSnapshotParams, Daytona

    d = Daytona()  # reads DAYTONA_API_KEY
    sb = d.create(CreateSandboxFromSnapshotParams(network_block_all=True))
    try:
        sb.fs.upload_file(b"Antimetal is the autonomous system for production.", "/tmp/page.txt")
        r = sb.process.code_run(
            "print('autonomous system for production' in open('/tmp/page.txt').read())"
        )
        found = r.result.strip()
        probe = sb.process.code_run(
            "import urllib.request\n"
            "try:\n    urllib.request.urlopen('https://example.com', timeout=5); print('OPEN')\n"
            "except Exception as e:\n    print('BLOCKED')"
        )
        egress = probe.result.strip()
        ok = found == "True" and egress == "BLOCKED"
        return ok, f"verifier={found} egress={egress}"
    finally:
        d.delete(sb)


def check_anchor():
    """Fetch the demo page through Anchor and look for the exact phrase."""
    import httpx

    r = httpx.post(
        "https://api.anchorbrowser.io/v1/tools/fetch-webpage",
        headers={"anchor-api-key": os.environ["ANCHOR_API_KEY"]},
        json={"url": DEMO_URL, "format": "markdown"},
        timeout=90,
    )
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:120]}"
    text = r.text
    (OUT / "antimetal.md").write_text(text)
    found = DEMO_PHRASE in text.lower()
    return found, f"{len(text)} chars, phrase found={found}"


def check_surrealdb():
    """Write one fact, then recall it; the trace id is the provenance hook."""
    import httpx

    base = os.environ["SPECTRON_URL"].rstrip("/")
    ctx = os.environ["SPECTRON_CONTEXT_ID"]
    h = {"Authorization": f"Bearer {os.environ['SPECTRON_API_KEY']}"}
    w = httpx.post(
        f"{base}/api/v1/{ctx}/facts",
        headers=h,
        json={"text": "Smoke test: the Fact-Checked Publisher verifies quotes before publishing."},
        timeout=60,
    )
    if w.status_code >= 300:
        return False, f"write HTTP {w.status_code}: {w.text[:120]}"
    q = httpx.post(
        f"{base}/api/v1/{ctx}/query",
        headers=h,
        json={"query": "What does the Fact-Checked Publisher do?"},
        timeout=60,
    )
    if q.status_code >= 300:
        return False, f"query HTTP {q.status_code}: {q.text[:120]}"
    body = q.json()
    trace_id = (body.get("trace") or {}).get("traceId")
    return bool(trace_id), f"write {w.status_code}, hits={len(body.get('hits', []))}, trace={trace_id}"


def check_claude_and_arize():
    """One Agent SDK call on the subscription login, traced into Arize AX."""
    from arize.otel import register

    tp = register(
        space_id=os.environ["ARIZE_SPACE_ID"],
        api_key=os.environ["ARIZE_API_KEY"],
        project_name=os.environ.get("ARIZE_PROJECT_NAME", "fact-checked-publisher"),
    )
    from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor

    ClaudeAgentSDKInstrumentor().instrument(tracer_provider=tp)

    import anyio
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    env_key = os.environ.pop("ANTHROPIC_API_KEY", None)  # force the subscription path
    result = {}

    async def run():
        async for m in query(
            prompt="Reply with exactly: SMOKE OK",
            options=ClaudeAgentOptions(max_turns=1, model="claude-haiku-5-5", allowed_tools=[]),
        ):
            if isinstance(m, ResultMessage):
                result["text"] = m.result
                result["error"] = m.is_error

    anyio.run(run)
    tp.force_flush()
    if env_key:
        os.environ["ANTHROPIC_API_KEY"] = env_key
    ok = not result.get("error") and "SMOKE OK" in (result.get("text") or "")
    return ok, f"claude='{result.get('text')}' · span flushed; check project in AX UI"


def check_elevenlabs():
    """Short TTS line; draws on subscription credits."""
    if not os.environ.get("ELEVENLABS_API_KEY"):
        return False, "ELEVENLABS_API_KEY empty"
    from elevenlabs.client import ElevenLabs

    el = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    voice = el.voices.get_all().voices[0]
    audio = el.text_to_speech.convert(
        voice_id=voice.voice_id,
        text="Publish denied. One claim is unsourced.",
        model_id="eleven_flash_v2_5",
    )
    path = OUT / "smoke.mp3"
    path.write_bytes(b"".join(audio))
    return path.stat().st_size > 1000, f"voice={voice.name}, {path.stat().st_size} bytes"


def check_cedar():
    """The publish policy, evaluated outside any model: one deny, one permit."""
    import cedarpy

    policy = (ROOT / "policy" / "publish.cedar").read_text()

    def decide(unsourced):
        req = {
            "principal": 'Agent::"publisher"',
            "action": 'Action::"publish"',
            "resource": 'Post::"draft-10-12"',
            "context": {"unsourced_count": unsourced},
        }
        return cedarpy.is_authorized(req, policy, []).decision.name

    deny, allow = decide(1), decide(0)
    return (deny, allow) == ("Deny", "Allow"), f"unsourced=1 → {deny}, unsourced=0 → {allow}"


CHECKS = [
    ("Cedar policy", check_cedar),
    ("Daytona quarantine", check_daytona),
    ("Anchor fetch", check_anchor),
    ("SurrealDB memory", check_surrealdb),
    ("Claude (subscription) + Arize", check_claude_and_arize),
    ("ElevenLabs TTS", check_elevenlabs),
]


def main():
    t = Table(title="Smoke test")
    for col in ("Check", "Result", "Secs", "Detail"):
        t.add_column(col)
    for name, fn in CHECKS:
        start = time.time()
        try:
            ok, detail = fn()
        except Exception as e:  # report, don't retry
            ok, detail = False, f"{type(e).__name__}: {str(e)[:160]}"
            (OUT / f"{name.split()[0].lower()}_error.txt").write_text(traceback.format_exc())
        t.add_row(name, "[green]PASS" if ok else "[red]FAIL", f"{time.time() - start:.1f}", detail)
    Console().print(t)


if __name__ == "__main__":
    main()
