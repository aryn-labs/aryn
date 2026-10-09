# Studio visual and performance evidence

`agent-ci.json` records completed-success of all 14 jobs on final implementation source `2ca9dca575a2cfcc95505547e4426fe95e7e97b4` and the validated review artifact metadata. It contains public workflow facts, not raw logs or credentials. The final report also verifies the evidence-only closure commit's exact SHA/workflow.

`agent-api-performance.json` records the 20-sample repetition from clean implementation source `2ca9dca575a2cfcc95505547e4426fe95e7e97b4`, source_modified=false. The synthetic fixture includes one actual golden lifecycle plus the stated historical inventory. It stresses run/audit history, not thousands of published versions; see delivery evidence for all metrics and limits.

Current Agent editing audit source is `40df9d1f894b257df3a277c4623466d6d03541dc`. `agent-builder-{dark,light}-{390,768,1440}.png` capture the passing typed-editor browser test on synthetic research input. They were reviewed visually alongside all-field roundtrip, keyboard form completion, axe and overflow assertions. Saved layout/viewport are personal metadata, so a zoomed mobile canvas may require its fit control; the complete section buttons/form remain accessible.

`agent-browser-performance.json` contains sanitized attachments and 27/27 suite statistics extracted from the actual Playwright HTML report. Its explicit modified-source provenance distinguishes local measurements from exact-SHA CI. Large fixture is 200 blueprints / 1,000 runs / 5,000 signed audits / 200 divisions; navigation has 10 samples, summary 20, and the five additional resource routes have one observed navigation each. No full-snapshot requests occur on those canonical resource routes. Current clean-source API benchmark and terminal implementation CI metadata are recorded separately in delivery evidence. Prior workspace artifacts below remain historical.

Audit baseline: `3a8ddb69b855ea37d1a33721c6c57a02f14ad881`. Source implementation and exact-SHA CI are recorded in [delivery evidence](../../studio-redesign-progress.md).

`baseline-390.png`, `baseline-768.png`, `baseline-1440.png` show the existing built Studio before edits. `overview-*`, `projects-*`, `divisions-*` show the implemented workspace at 390/768/1440 px in both dark/light themes, captured by the passing isolated Playwright suite. Empty states are actual empty fixture state; no customer data or credential appears. Screenshots were visually reviewed alongside automated axe, keyboard and reflow checks.

`workspace-performance.json` and `workspace-performance-optimized.json` are reproducible API measurements before/after retaining strong ORM references during legacy snapshot verification. `browser-performance.json` is the performance attachment extracted from the 25/25 passing Playwright report. Their source_modified flags explicitly identify pre-commit working-tree measurements, rather than attributing the implementation to the old baseline commit. See delivery evidence for sample counts, environment, thresholds, limitations and final source revision.

`workspace-performance-committed.json` repeats the API benchmark from clean source `80bac7dfa59bd27a6ac1e7e5493f11285b625b2d` (source_modified=false), after other local suites finished. The latest performance numbers distinguish this run from concurrent-suite measurements.

`ci-implementation.json` records terminal SUCCESS of 14 jobs on implementation source, including collection coverage and validated artifact gates; it contains public workflow metadata only, not raw logs or credentials.
