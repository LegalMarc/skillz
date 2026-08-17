# Desktop browser setup and evidence handling

## Preferred architecture

Use two coordinated layers:

1. Use ChatGPT Desktop's built-in browser for the interview, visible page review, permission prompts, and any manual interaction that the user should observe.
2. Use `scripts/audit_site.py` for reproducible evidence capture. The script opens separate, pristine browser contexts for baseline, denial, GPC, and optional accept-control runs. Those contexts do not share cookies or cache with one another.

Do not attempt to clean or modify the user's ordinary Chrome profile for the default audit. Isolation is more reliable and less destructive than deleting the user's site data.

## ChatGPT Desktop

In the ChatGPT desktop app on macOS or Windows, open a chat in Work or Codex, then open the built-in browser from the toolbar or press Command-Shift-B on macOS or Ctrl-Shift-B on Windows. Approve access to the target host when prompted. The built-in browser uses its own browser state. It can be cleared from desktop Settings when a visual-only rerun is needed.

Use the built-in browser for public pages and for observing the banner. Use an existing Chrome profile only when an authenticated session is necessary and specifically authorized. Credentials belong in the browser, never in chat.

Official OpenAI instructions: https://help.openai.com/en/articles/20001277-using-the-built-in-browser-in-the-chatgpt-desktop-app

## Runner installation

From the skill's `scripts` directory:

```bash
python -m pip install -r requirements.txt
python audit_site.py --url https://example.com --out ./audit-example --headed --manual
```

The runner uses installed Chrome, Edge, or Chromium when possible. If none is available:

```bash
python -m playwright install chromium
```

For an unattended run, omit `--manual` and use `--headless`. For a visible, reviewable run, use `--headed --manual` so a person can complete a denial if the CMP uses a custom control the automation cannot reliably operate.

## Clean-state rule

Each scenario must begin in a new browser context. Do not run baseline, denial, and GPC sequentially in the same context. A new context avoids inherited cookies, cache, local storage, IndexedDB, and service-worker state. Close the context cleanly so HAR data flushes to disk.

Playwright documents that new browser contexts do not share cookies or cache and should be closed before the browser so HAR and video artifacts are saved: https://playwright.dev/docs/api/class-browser#browser-new-context

## HAR handling

A raw HAR may contain cookie values, Set-Cookie headers, authorization material, identifiers, query parameters, request bodies, and personal information. The runner creates:

- `evidence-private`: raw HAR and raw browser state; keep local and access-restricted.
- `evidence-shareable`: sanitized HAR, redacted state, screenshots, and event logs.

Chrome's default sanitized HAR omits sensitive Cookie, Set-Cookie, and Authorization headers. A full evidentiary HAR can be exported with sensitive data, but it must be handled as confidential evidence. Official Chrome instructions: https://developer.chrome.com/docs/devtools/network/reference/#save-all-as-har

## Manual DevTools fallback

Use this only when the runner cannot execute. Label the report as a manual, limited capture.

1. Open a new browser profile or guest/isolated session.
2. Open DevTools before navigating to the target page.
3. In Network, enable Preserve log and Disable cache.
4. Clear site data for the target host.
5. Start recording, navigate to the page, wait for delayed tags, and screenshot the initial banner.
6. Export a raw HAR with sensitive data for local evidence and a sanitized HAR for sharing.
7. Click the most privacy-protective choice, wait, refresh, and visit two safe same-origin pages while preserving the log.
8. Repeat in a fresh context with GPC enabled.
9. Hash and retain the evidence files.

A DevTools panel opened after page load can miss early requests; reload after opening it. Preserve log must remain enabled across refreshes and navigation.

## Geographic and authenticated variants

Record the egress region. CMP behavior can vary by IP, language, browser, account status, and page path. A Connecticut office connection does not prove what a California consumer sees. Run additional authorized tests through relevant regional egress points when legal conclusions depend on geography.

Authenticated testing is higher risk because raw evidence may include account identifiers and authorization tokens. Require explicit authorization, use a dedicated test account, minimize access, and keep raw artifacts out of chat and ordinary email.
