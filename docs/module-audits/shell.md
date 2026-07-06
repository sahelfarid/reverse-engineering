# Shell Audit

Files: `adb/shell.py`, `routes/shell.py`, `static/js/shell.js`

Coverage: backend 100%, route 93% (unchanged); frontend now covered by `tests/frontend/shell.test.js` (Vitest + jsdom).

Full implementation notes, API reference, and permanent known limitations now live in the module
documentation: [`docs/modules/shell.md`](../modules/shell.md). This file tracks only what is still
open from the original audit pass.

## Resolved This Pass

Added a minimal JS test harness (`package.json`, `vitest.config.js`, `tests/frontend/`) and
`tests/frontend/shell.test.js`, which loads the real `static/js/app.js` and `static/js/shell.js`
into a jsdom window (as classic scripts, same as the browser -- no bundler) and exercises terminal
rendering directly: successful-command stdout + green exit badge, failing-command stderr + red exit
badge, an API-level error surfacing as a toast, and HTML-escaping of both the command and its output.
This closes the last open item for this module.

## Remaining Items

- None. Every gap and recommended test identified in the original audit has been closed -- either fixed in code (with a regression test proving the bug existed) or closed with test coverage where the gap was purely a testing hole. See the module documentation's Known Limitations section for the permanent, accepted tradeoffs that remain by design (not bugs).
