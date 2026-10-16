# Fixtures

Public text only. The event recording and transcript never enter this repo.

- `draft.md`: line 1 is verbatim from the LinkedIn post published 2026-10-12 (the misquote: nobody said or wrote "autonomous production"). Line 3 is a **positive control**: a quote that SurrealDB's page does contain, so the verifier must pass it.
- `injected_draft.md`: the same draft plus a hidden instruction telling the extractor to drop every claim. The regex floor must still produce both quotes.
- `sources/`: page text fetched through Anchor, with `url` and `fetched_at` headers. Antimetal's homepage has changed twice since the post: 10-12 "It diagnoses. It fixes. It prevents." → 10-15 "Production that runs itself." → 10-16 "Production should run itself." None of them ever said "autonomous production."
