from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
}
SENSITIVE_QUERY_KEY = re.compile(
    r"(?:token|auth|authorization|session|sid|email|e-mail|phone|name|address|code|key|password|passwd|secret|jwt|sso|user|uid|idfa|ga_client_id)",
    re.I,
)
COMMON_MULTI_LABEL_SUFFIXES = {
    "co.uk", "org.uk", "gov.uk", "ac.uk", "com.au", "net.au", "org.au",
    "co.nz", "com.br", "com.mx", "co.jp", "co.kr", "co.in", "com.sg",
    "com.hk", "com.cn", "com.tw", "co.za", "com.tr", "com.ar", "com.co",
    "com.pl", "com.ua", "com.my", "com.ph", "com.vn", "com.sa", "com.eg",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str, max_len: int = 80) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value or "site")[:max_len].rstrip("-")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def redacted_value(value: Any) -> str:
    text = "" if value is None else str(value)
    return f"[REDACTED len={len(text)} sha256={short_hash(text)}]"


def sanitize_cookie_header(value: str) -> str:
    parts: list[str] = []
    for item in value.split(";"):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            name, raw = item.split("=", 1)
            parts.append(f"{name.strip()}={redacted_value(raw)}")
        else:
            parts.append(item)
    return "; ".join(parts)


def sanitize_set_cookie_header(value: str) -> str:
    first, *attributes = value.split(";")
    if "=" in first:
        name, raw = first.split("=", 1)
        first = f"{name.strip()}={redacted_value(raw)}"
    return ";".join([first, *attributes])


def sanitize_url(url: str, redact_all_query_values: bool = True) -> str:
    try:
        parts = urlsplit(url)
        if not parts.query:
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        output: list[tuple[str, str]] = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if redact_all_query_values or SENSITIVE_QUERY_KEY.search(key):
                output.append((key, redacted_value(value)))
            else:
                output.append((key, value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(output), ""))
    except Exception:
        return "[UNPARSEABLE URL REDACTED]"


def sanitize_headers(headers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for header in headers or []:
        item = dict(header)
        name = str(item.get("name", ""))
        value = str(item.get("value", ""))
        lower = name.lower()
        if lower == "cookie":
            item["value"] = sanitize_cookie_header(value)
        elif lower == "set-cookie":
            item["value"] = sanitize_set_cookie_header(value)
        elif lower in SENSITIVE_HEADER_NAMES:
            item["value"] = redacted_value(value)
        sanitized.append(item)
    return sanitized


def sanitize_cookie_list(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for cookie in cookies or []:
        item = dict(cookie)
        if "value" in item:
            item["value"] = redacted_value(item.get("value"))
        output.append(item)
    return output


def sanitize_har_data(har: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(har)
    log = output.get("log", {})
    for entry in log.get("entries", []) or []:
        request = entry.get("request", {})
        response = entry.get("response", {})
        if "url" in request:
            request["url"] = sanitize_url(str(request["url"]))
        request["headers"] = sanitize_headers(request.get("headers", []))
        request["cookies"] = sanitize_cookie_list(request.get("cookies", []))
        if isinstance(request.get("queryString"), list):
            for param in request["queryString"]:
                if "value" in param:
                    param["value"] = redacted_value(param.get("value"))
        post_data = request.get("postData")
        if isinstance(post_data, dict):
            if "text" in post_data:
                post_data["text"] = redacted_value(post_data.get("text"))
            if isinstance(post_data.get("params"), list):
                for param in post_data["params"]:
                    if "value" in param:
                        param["value"] = redacted_value(param.get("value"))
                    if "fileName" in param:
                        param["fileName"] = "[REDACTED FILE NAME]"
        response["headers"] = sanitize_headers(response.get("headers", []))
        response["cookies"] = sanitize_cookie_list(response.get("cookies", []))
        content = response.get("content")
        if isinstance(content, dict) and "text" in content:
            content["text"] = "[RESPONSE BODY OMITTED]"
            content.pop("encoding", None)
    return output


def sanitize_har_file(raw_path: Path, output_path: Path) -> None:
    har = read_json(raw_path)
    write_json(output_path, sanitize_har_data(har))


def redact_storage_state(state: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(state)
    output["cookies"] = sanitize_cookie_list(output.get("cookies", []))
    for origin in output.get("origins", []) or []:
        for item in origin.get("localStorage", []) or []:
            if "value" in item:
                item["value"] = redacted_value(item.get("value"))
        for database in origin.get("indexedDB", []) or []:
            for store in database.get("stores", []) or []:
                if "records" in store:
                    store["records"] = f"[REDACTED {len(store.get('records') or [])} RECORDS]"
    return output


def sanitize_event_log(events: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(events)
    for kind in ("requests", "responses", "request_failures"):
        for item in output.get(kind, []) or []:
            if "url" in item:
                item["url"] = sanitize_url(str(item["url"]))
            if "redirected_from" in item and item["redirected_from"]:
                item["redirected_from"] = sanitize_url(str(item["redirected_from"]))
    return output


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_hash_manifest(root: Path, output_name: str = "manifest.sha256") -> Path:
    output = root / output_name
    lines: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != output_name):
        relative = path.relative_to(root).as_posix()
        lines.append(f"{sha256_file(path)}  {relative}")
    write_text(output, "\n".join(lines) + "\n")
    return output


def run_fingerprint(metadata: dict[str, Any]) -> str:
    """Stable hash over the parameters that must match for two runs to compare.

    Deliberately excludes timestamps, output paths, and anything else that
    changes every run: two audits are comparable when the *conditions* match,
    not when they happen to have been run at the same time.
    """
    material = {
        key: metadata.get(key)
        for key in (
            "target_url", "pages", "wait_ms", "locale", "timezone", "viewport",
            "egress_region", "profile", "headless", "browser_version",
            "tool_version", "classification_reference_version",
        )
    }
    payload = json.dumps(material, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


ZIP_README = """COOKIE BANNER AUDIT EVIDENCE BUNDLE - CONTAINS RAW EVIDENCE
===========================================================

READ THIS BEFORE FORWARDING THIS ARCHIVE.

This archive intentionally contains the COMPLETE evidence bundle, including
evidence-private/, which holds RAW, UNREDACTED material:

  - raw HAR files with full request and response headers
  - Cookie and Set-Cookie headers with their actual values
  - Authorization headers and other credential-bearing material, if any was sent
  - Query strings and request bodies that may contain personal information
  - Raw browser storage state

Treat this archive as confidential evidence:

  - Do not email it or upload it to a third-party service.
  - Do not attach it to a ticket, chat message, or shared drive without a
    deliberate privilege and data-minimisation review.
  - Transfer it the way you would transfer any other sensitive evidence file.

For routine collaboration, generate a redacted archive instead:

    python scripts/audit_site.py ... --zip-shareable-only

That variant contains the reports, inventories, screenshots, and sanitized HAR,
with cookie values, sensitive headers, and request bodies replaced by hashes.

CONTENTS
--------
audit-report.pdf / .html / .md   The report, same content in three formats.
audit-data.json                  Structured results, schema_version 2.0.
findings.json                    Reported findings.
suppressed-findings.json         Findings WITHHELD as unsupported - read this.
cookie-inventory.csv             Every cookie observation.
request-inventory.csv            Every request with evidence-strength grading.
evidence-shareable/              Sanitized HAR, redacted state, screenshots.
evidence-private/                RAW SENSITIVE HAR AND STATE.
manifest.sha256                  Integrity hashes.

This bundle is technical evidence and legal issue spotting, not a compliance
certification.
"""


def build_zip_bundle(
    root: Path,
    output_path: Path,
    include_raw: bool = True,
    readme: str | None = None,
) -> dict[str, Any]:
    """Package the bundle into a single archive.

    Defaults to including raw evidence, because an evidence bundle that omits
    the HAR is not much use as evidence. The filename and an embedded README
    carry the warning instead, so the risk is visible rather than silent.
    """
    import zipfile

    skipped: list[str] = []
    written = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("READ-ME-FIRST.txt", readme or ZIP_README)
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            relative = path.relative_to(root).as_posix()
            if relative == output_path.name or relative.endswith(".zip"):
                continue
            if not include_raw and relative.startswith("evidence-private/"):
                skipped.append(relative)
                continue
            archive.write(path, relative)
            written += 1
    return {
        "path": str(output_path),
        "files": written,
        "raw_included": include_raw,
        "skipped": len(skipped),
        "size_bytes": output_path.stat().st_size if output_path.exists() else 0,
    }


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def registrable_domain(hostname: str | None) -> str:
    if not hostname:
        return ""
    host = hostname.strip(".").lower()
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host) or ":" in host or host == "localhost":
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    suffix2 = ".".join(labels[-2:])
    if suffix2 in COMMON_MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def same_site(host_a: str | None, host_b: str | None) -> bool:
    return bool(host_a and host_b and registrable_domain(host_a) == registrable_domain(host_b))


def discover_browser_executable(explicit: str | None = None) -> str | None:
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(f"Browser executable not found: {candidate}")

    env_candidate = os.environ.get("COOKIE_AUDIT_BROWSER")
    if env_candidate and Path(env_candidate).expanduser().is_file():
        return str(Path(env_candidate).expanduser())

    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates.extend([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ])
    elif os.name == "nt":
        roots = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        for root in [r for r in roots if r]:
            candidates.extend([
                str(Path(root) / "Google/Chrome/Application/chrome.exe"),
                str(Path(root) / "Microsoft/Edge/Application/msedge.exe"),
                str(Path(root) / "Chromium/Application/chrome.exe"),
            ])
    else:
        candidates.extend([
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ])

    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate

    for name in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser", "msedge"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def host_from_url(url: str) -> str:
    return (urlsplit(url).hostname or "site").lower()


def origin_from_url(url: str) -> str:
    parts = urlsplit(url)
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}"


def endpoint_key(url: str) -> str | None:
    """The `host+path` identity of one request, or None if there is no endpoint.

    Single definition shared by the repeat-baseline stability check
    (`capture._endpoint_set`) and the run comparison (`compare_runs._endpoints`).
    Those two previously extracted this independently and disagreed at the
    edges - one required a hostname, the other only a non-empty key - so a URL
    could count as an endpoint when deciding whether a tag was unstable but not
    when diffing two runs, or the reverse. Both questions are "which network
    endpoints were contacted", so they must count the same things.

    A hostname is required: a `data:`, `blob:`, or `file:` URL is not a network
    endpoint and must not appear in either answer. The query string is
    deliberately excluded, since cache busters and per-request identifiers
    would otherwise make every run look entirely different from every other.
    """
    try:
        parts = urlsplit(str(url))
    except Exception:
        return None
    if not parts.hostname:
        return None
    key = f"{parts.hostname}{parts.path or ''}"
    return key if key.strip("/") else None


def escape_markdown_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


# --------------------------------------------------------------------------
# Minimal Markdown rendering
# --------------------------------------------------------------------------
# The report is authored once in Markdown and rendered to HTML (and from there
# to PDF) so the three artefacts cannot drift apart. This handles only the
# subset the report generator emits; it is not a general-purpose converter.

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")


def _inline_markdown(text: str) -> str:
    import html as _html

    out = _html.escape(text)
    out = _IMAGE.sub(lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}">', out)
    out = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', out)
    out = _INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    # Bold before italic, so ** is not consumed by the single-asterisk rule.
    out = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", out)
    return out


def markdown_to_html(markdown: str) -> str:
    """Convert the report's Markdown subset to HTML."""
    lines = markdown.splitlines()
    out: list[str] = []
    index = 0
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            close_list()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            import html as _html
            out.append(f"<pre><code>{_html.escape(chr(10).join(block))}</code></pre>")
            continue

        # Table: a header row followed by a |---|---| separator.
        if stripped.startswith("|") and index + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[index + 1]):
            close_list()
            def cells(row: str) -> list[str]:
                return [c.strip() for c in row.strip().strip("|").split("|")]

            header = cells(stripped)
            index += 2
            body: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                body.append(cells(lines[index].strip()))
                index += 1
            head_html = "".join(f"<th>{_inline_markdown(c)}</th>" for c in header)
            rows_html = "".join(
                "<tr>" + "".join(f"<td>{_inline_markdown(c)}</td>" for c in row) + "</tr>" for row in body
            )
            out.append(f'<div class="table-wrap"><table><thead><tr>{head_html}</tr></thead><tbody>{rows_html}</tbody></table></div>')
            continue

        if not stripped:
            close_list()
            index += 1
            continue

        if stripped.startswith("#"):
            close_list()
            level = len(stripped) - len(stripped.lstrip("#"))
            level = min(max(level, 1), 4)
            out.append(f"<h{level}>{_inline_markdown(stripped[level:].strip())}</h{level}>")
            index += 1
            continue

        if stripped.startswith(">"):
            close_list()
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip(">").strip())
                index += 1
            rendered = []
            for entry in quote:
                if entry.startswith("##"):
                    rendered.append(f"<strong>{_inline_markdown(entry.lstrip('#').strip())}</strong>")
                elif entry.startswith("- "):
                    rendered.append(f"<li>{_inline_markdown(entry[2:])}</li>")
                elif entry:
                    rendered.append(_inline_markdown(entry))
            body_html = "<br>".join(r for r in rendered if not r.startswith("<li>"))
            items = "".join(r for r in rendered if r.startswith("<li>"))
            out.append(f'<blockquote>{body_html}{f"<ul>{items}</ul>" if items else ""}</blockquote>')
            continue

        if re.match(r"^(-{3,}|\*{3,})$", stripped):
            close_list()
            out.append("<hr>")
            index += 1
            continue

        list_match = re.match(r"^(?:[-*]|\d+\.)\s+(.*)$", stripped)
        if list_match:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline_markdown(list_match.group(1))}</li>")
            index += 1
            continue

        close_list()
        out.append(f"<p>{_inline_markdown(stripped)}</p>")
        index += 1

    close_list()
    return "\n".join(out)
