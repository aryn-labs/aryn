# Studio visual and performance evidence

Audit baseline: `3a8ddb69b855ea37d1a33721c6c57a02f14ad881`. Source implementation and exact-SHA CI are recorded in [delivery evidence](../../studio-redesign-progress.md).

`baseline-390.png`, `baseline-768.png`, `baseline-1440.png` show the existing built Studio before edits. `overview-*`, `projects-*`, `divisions-*` show the implemented workspace at 390/768/1440 px in both dark/light themes, captured by the passing isolated Playwright suite. Empty states are actual empty fixture state; no customer data or credential appears. Screenshots were visually reviewed alongside automated axe, keyboard and reflow checks.

`workspace-performance.json` and `workspace-performance-optimized.json` are reproducible API measurements before/after retaining strong ORM references during legacy snapshot verification. `browser-performance.json` is the performance attachment extracted from the 25/25 passing Playwright report. Their source_modified flags explicitly identify pre-commit working-tree measurements, rather than attributing the implementation to the old baseline commit. See delivery evidence for sample counts, environment, thresholds, limitations and final source revision.
