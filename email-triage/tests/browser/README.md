# Synthetic browser check

Optional development-only dependency: Playwright for Node (not required by the renderer). Use a local installation or `NODE_PATH` pointing to it; Chrome must be installed. `CHROME_PATH` overrides the macOS Chrome default. Do not substitute a real review export for these synthetic fixtures.

From the skill directory:

```sh
python3 tests/browser/prepare.py
node tests/browser/check.cjs
python3 scripts/review.py validate-edits tests/browser/source.json tests/browser/synthetic-export.json
python3 scripts/review.py validate-assignments tests/browser/source.json tests/browser/synthetic-assignments.json
python3 scripts/review.py validate-refresh tests/browser/source.json tests/browser/synthetic-refresh.json
```

The check uses headless Chrome on a synthetic local HTML file, exercises controls and import rejection, and fails on external requests, page errors, or active mail HTML. It writes fixture/export/screenshot evidence beside itself; generated files are ignored. No Mail API or real email is accessed.


Responsive verification (after prepare.py):

```sh
node tests/browser/responsive.cjs
```

This checks numeric Size sorting and viewports 320–1920px on synthetic data. To verify an existing private review's layout without changing it, pass that HTML path; real-data mode saves no screenshots by default. An optional second argument explicitly selects a private screenshot directory. Screenshots are created owner-only (0600) using an atomic write. Keep real-data evidence outside the skill source tree. Real-data mode does not test synthetic sort expectations or edit messages; it only inspects the supplied local review HTML and its layout. It never opens linked message sources or attachments or calls Mail.

Help overlay checks (after prepare.py): `node tests/browser/help.cjs`. An optional local HTML argument checks the actual report without editing it or creating screenshots. This verifies the compact header, build timestamp, Help content, keyboard focus, independent scrolling, Close/Escape/backdrop behavior, unchanged edits, and 320–1440px layouts.
