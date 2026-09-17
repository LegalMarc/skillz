---
name: pandadoc-pdf-download
description: Download a PandaDoc document as PDF from its public view (app.pandadoc.com/document/v2?token=...) — byte-exact source PDF plus a signed reconstruction with signature images and field values stamped in. Use when the user shares a PandaDoc link and wants the PDF, especially when the sender disabled the recipient download button.
---

# PandaDoc PDF download (public view, downloads disabled or not)

Produces two files from a PandaDoc public document view:
1. **Byte-exact source PDF** — PandaDoc's own stored bytes (from their S3 via their content API). NOTE: PandaDoc stores this PDF **unsigned**; signatures/dates are viewer overlays, not in the file.
2. **Signed reconstruction** — the same source PDF stamped with PandaDoc's own signature PNGs and field values at the exact positions the viewer renders them. Visually identical to the official flattened download (which additionally may append a signature-certificate page — that asset is server-side 403 when the sender disabled recipient downloads and cannot be obtained).

Prerequisites: Playwright MCP browser tools. The user must supply the public view URL (its `?token=` is the auth credential — treat it as the user's own document access).

## Quick path

1. **Try the UI first.** Open the URL; if a Download button exists in the viewer chrome, use it and stop.
2. **Run the extractor.** Read `extract-stamped-pdf.js` from this skill directory and pass its whole body to `browser_evaluate` (it is a single async arrow function). `PD_TOKEN` / `PD_DOC_ID` are auto-discovered from the page URL and network log; override the constants at the top only if discovery fails.
   - It fetches a content JWT, pulls the content tree over PandaDoc's WebSocket, downloads the source PDF bytes, scrolls the viewer to measure every rendered field overlay (signature images, date/text values) relative to each page root, rebuilds the signed PDF with pdf-lib (loaded from unpkg), and triggers two blob downloads.
   - Playwright saves downloads into `.playwright-mcp/` under the workspace with sanitized names (brackets/spaces become dashes).
3. **Move/rename** the two PDFs from `.playwright-mcp/` to the workspace root with clean names (Bash: `mv -- "-sanitized-name-.pdf" "Clean Name.pdf"`).
4. **Verify visually.** Re-open the stamped PDF via a blob URL in a new tab and screenshot each signature page; compare against the live viewer. (file:// navigation is blocked; use a blob URL. To land on a specific page, build a one-page PDF with `copyPages` — the `#page=N` anchor and keyboard nav do not reliably work in the Chromium PDF plugin.)

## If something fails

- **Doc id discovery**: regex the performance resource log: `performance.getEntriesByType('resource').map(e=>e.name).join(' ').match(/documents\/([A-Za-z0-9]{22})/)`.
- **content_uuid discovery**: decode the content_token JWT payload (`JSON.parse(atob(jwt.split('.')[1]))`) — the content uuid is in a claim (`content_uuid`/`aud`/first 36-char uuid). The JWT is bound to it; `content_fetch` with any other uuid returns `unauthorized`.
- **content_token returns a bare JSON string**, not `{token: ...}` — `await r.json()` directly.
- **WS protocol**: onopen → `{id:1, endpoint:'authorize', payload:{token, appVersion:'6a66b5d417ba'}, topic:'permissions'}`; on ok → `{id:2, endpoint:'content_fetch', payload:{content_uuid, tag_uuid:null, resolve_s3_links:true}, topic:'events'}`; the content arrives in a message whose `payload.content` exists (an earlier `{ok}` ack may arrive first). Source PDF URL: `payload.content.pdf.items[0].source_pdf` (fresh presigned S3; also `source_url` = original uploaded .docx).
- **Fields dump**: the script stashes measurements in `window.__pdFields` and returns them. If a document has field types the stamper doesn't handle (checkboxes, dropdowns, initials as SVG), inspect the dump and extend — the geometry is always "measure the overlay rect relative to the page's `img[src*=pdf-pages]` rect, scale by pdfPagePt / imgRectPx".
- **Viewer DOM structure (verified 2026-09-17)**: each page is a `div[class*=sectionItemBox]` holding one `img[src*=pdf-pages]` (page number from its src: `%2F<page>%2F<n>.jpg`) plus that page's fields. Fields live in `div[class*=fieldUI]` containers: signatures hold `img[src*=field-storage]`, date/text fields hold leaf text nodes. **`div[class*=pageLayoutRoot]` contains neither the page img nor the fields** — an earlier script version scoped queries to it and collected nothing; the script now enumerates pages from the pdf-pages imgs and assigns fields to pages by center-point containment. Pages/fields can mount lazily, so the script measures during repeated scroll passes until the field count is stable.
- **Font mapping**: Arial→Helvetica, Times→Times-Roman, Courier→Courier (bold/italic variants via weight/style). Baseline = linebox top + (lineHeight−fontSize)/2 + 0.9·fontSize. Verified pixel-exact against Arial 15px → Helvetica 11.25pt.
- **S3 CORS**: in-page `fetch` of the presigned S3 URLs works from the app.pandadoc.com origin. `unpkg.com` fetch + indirect `eval` works (CSP allows `unsafe-eval`); a `<script src>` tag would be blocked.

## Official-channel notes (don't waste time)

When the sender set `download_by_recipients_allowed: false`: sync `/pdf` → 404, async export-tasks → 403, DocVault `api/docvault/documents/{doc}/revisions/{rev}/signing-status` and signed-asset file → 403. All server-side; no client workaround. The one official route is the recipient portal (recipient.pandadoc.com magic link) → "email me a new secure link" → the emailed link can offer the official signed PDF, but it sends email to the recipient address — **ask the user before triggering it**.

Geometry/background reference: see memory `pandadoc-offline-pdf-extraction`.
