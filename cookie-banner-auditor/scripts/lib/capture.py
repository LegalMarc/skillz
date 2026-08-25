from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen
from urllib.robotparser import RobotFileParser

from playwright.sync_api import Browser, BrowserContext, Frame, Locator, Page

from . import checks
from .util import (
    ensure_dir,
    slugify,
    origin_from_url,
    read_json,
    redact_storage_state,
    sanitize_event_log,
    sanitize_har_file,
    sanitize_url,
    short_hash,
    utc_now,
    write_json,
    write_text,
)

REFERENCES_DIR = Path(__file__).resolve().parents[2] / "references"

#: Device profiles a scenario set can be run under.
#:
#: Mobile is not a narrower desktop. CMPs routinely ship a different banner on
#: small screens - more often a full-screen interstitial, frequently with the
#: decline choice moved behind a settings layer that is one tap further away
#: than accept - so symmetry and click-count findings can differ entirely from
#: the desktop result. Most traffic is mobile, which makes the desktop-only
#: default the narrowest part of the audit's coverage.
#:
#: The user agent is pinned rather than derived from the running browser so a
#: Chromium upgrade cannot silently change what the site was told, which would
#: make two runs incomparable without anything in the fingerprint moving. Update
#: it deliberately.
VIEWPORT_PROFILES: dict[str, dict[str, Any]] = {
    "desktop": {
        "viewport": {"width": 1440, "height": 1000},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1.0,
        "user_agent": None,
    },
    "mobile": {
        # Pixel-7-class Android phone: the most common shape of mobile visit,
        # and narrow enough to trigger the small-screen branch in every CMP in
        # the selector table.
        "viewport": {"width": 412, "height": 915},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 2.625,
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
        ),
    },
}


def viewport_profile(label: str) -> dict[str, Any]:
    """Look up a device profile by label, failing loudly on an unknown one.

    A silent fallback to desktop here would produce a bundle labelled `mobile`
    that was captured at 1440px - evidence describing a visit that never
    happened, which is the defect class this tool exists to avoid.
    """
    try:
        return VIEWPORT_PROFILES[label]
    except KeyError:
        raise ValueError(
            f"Unknown viewport profile {label!r}. Known profiles: {', '.join(sorted(VIEWPORT_PROFILES))}."
        ) from None


@dataclass
class ScenarioConfig:
    """Everything a scenario run needs that is not the scenario itself.

    Collected into one object because the runner grew past the point where a
    positional signature stayed readable, and because every new capability
    (exercises, repeats, time budget) adds another knob.
    """

    url: str
    wait_ms: int = 5000
    timeout_ms: int = 30000
    pages: int = 2
    manual: bool = False
    locale: str = "en-US"
    timezone_id: str | None = None
    user_agent: str | None = None
    proxy: str | None = None
    ignore_https_errors: bool = False
    viewport: dict[str, int] = field(default_factory=lambda: {"width": 1440, "height": 1000})
    # Device emulation. A narrow viewport alone is not a mobile visit: CMPs and
    # tag managers branch on the user agent and on touch capability as well as
    # on width, so a 390px-wide context with a desktop UA can still be served
    # the desktop banner - and would then be reported as "mobile" evidence for
    # a layout no phone ever sees. These travel together, set from
    # VIEWPORT_PROFILES.
    viewport_label: str = "desktop"
    is_mobile: bool = False
    has_touch: bool = False
    device_scale_factor: float = 1.0
    device_user_agent: str | None = None
    #: Operator or agent decisions about controls an earlier run refused to
    #: resolve. Each is re-resolved and re-vetoed at the point it would be
    #: acted on (see `apply_control_verdict`), so this can unstick a run and
    #: cannot authorise a control the tool's own rules refuse.
    control_verdicts: list[dict[str, Any]] | None = None
    # Thoroughness profile
    thorough: bool = True
    dwell_ms: int = 15000
    scroll_stages: int = 4
    exercise_forms: bool = True
    submit_forms: bool = False
    exercise_search: bool = True

    def settle_ms(self) -> int:
        """How long to wait after a load before capturing."""
        return max(self.dwell_ms, self.wait_ms) if self.thorough else self.wait_ms


def render_pdf_from_html(html_path: Path, pdf_path: Path, executable: str | None = None) -> dict[str, Any]:
    """Print the HTML report to PDF using the browser already required by this tool.

    Chrome is a hard dependency of the capture step, so printing through it adds
    no new packages. Uses its own short-lived Playwright session because the
    audit browser is closed before reporting begins.
    """
    from playwright.sync_api import sync_playwright

    if not html_path.exists():
        return {"ok": False, "error": f"HTML report not found: {html_path}"}
    try:
        with sync_playwright() as playwright:
            launch_options: dict[str, Any] = {"headless": True}
            if executable:
                launch_options["executable_path"] = executable
            browser = playwright.chromium.launch(**launch_options)
            try:
                page = browser.new_context().new_page()
                page.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=60000)
                page.emulate_media(media="print")
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"},
                    display_header_footer=True,
                    header_template="<div></div>",
                    footer_template=(
                        '<div style="width:100%;font-size:8px;color:#5b6570;padding:0 14mm;'
                        'display:flex;justify-content:space-between">'
                        '<span>Cookie banner audit - technical evidence, not a compliance certification</span>'
                        '<span class="pageNumber"></span>/<span class="totalPages"></span>'
                        "</div>"
                    ),
                )
            finally:
                browser.close()
    except Exception as error:
        return {"ok": False, "error": str(error)[:500]}
    return {"ok": True, "path": str(pdf_path), "size_bytes": pdf_path.stat().st_size if pdf_path.exists() else 0}


def resolve_egress_region(timeout_seconds: float = 6.0) -> dict[str, Any]:
    """Record the public egress region so "region unverified" becomes a fact (E5).

    This describes where the *auditor* connected from. It says nothing about
    where any real visitor is, and consent behaviour often varies by region.
    """
    import urllib.request

    for endpoint, fields in (
        ("https://ipapi.co/json/", ("country_name", "region", "city")),
        ("https://ipinfo.io/json", ("country", "region", "city")),
    ):
        try:
            with urllib.request.urlopen(endpoint, timeout=timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception:
            continue
        parts = [str(data.get(field)) for field in fields if data.get(field)]
        if parts:
            return {"resolved": True, "source": endpoint, "region": ", ".join(parts)}
    return {"resolved": False, "region": None, "note": "Egress region could not be resolved; treat geography as unverified."}


def load_cmp_table(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the known-CMP fingerprint and selector table.

    A missing or malformed table is not fatal: detection falls back to text
    scoring, which is how the tool behaved before the table existed.
    """
    target = path or (REFERENCES_DIR / "cmp-selectors.json")
    try:
        data = read_json(target)
        entries = data.get("cmps") if isinstance(data, dict) else None
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


BANNER_KEYWORDS = re.compile(r"\b(cookie|cookies|consent|privacy|tracking|personal information|sell or share)\b", re.I)
OPTIONAL_CATEGORY = re.compile(
    r"\b(analytics?|statistics?|performance|measurement|advertis(?:e|ing)|marketing|targeting|personalization|personalisation|functional|social media|social|profiling)\b",
    re.I,
)
NECESSARY_CATEGORY = re.compile(r"\b(strictly necessary|necessary|essential|required|security|fraud|authentication|load balancing)\b", re.I)

#: The consent-control label vocabulary (what a button's own text says it does)
#: lives in `checks.CONTROL_PATTERNS`. It is a decision about text rather than a
#: browser operation, and it has to be applied identically to a candidate the
#: CMP selector table produced and one the text scorer produced.

DANGEROUS_LINK = re.compile(
    r"(?:logout|log-out|signout|sign-out|delete|remove|checkout|cart|basket|payment|pay-now|purchase|order|unsubscribe|subscribe|account|profile|admin|wp-login|login|log-in|signin|sign-in|signup|sign-up)",
    re.I,
)
DOWNLOAD_EXTENSION = re.compile(r"\.(?:pdf|zip|rar|7z|docx?|xlsx?|pptx?|dmg|exe|msi|pkg)(?:$|[?#])", re.I)


def _sleep_ms(ms: int) -> None:
    time.sleep(max(ms, 0) / 1000.0)


def _safe_title(page: Page) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def _element_text(locator: Locator) -> str:
    for getter in (
        lambda: locator.inner_text(timeout=750),
        lambda: locator.get_attribute("aria-label", timeout=750),
        lambda: locator.get_attribute("value", timeout=750),
        lambda: locator.get_attribute("title", timeout=750),
    ):
        try:
            value = getter()
            if value and str(value).strip():
                return re.sub(r"\s+", " ", str(value)).strip()
        except Exception:
            pass
    return ""


def _control_metadata(locator: Locator, frame: Frame, index: int) -> dict[str, Any] | None:
    try:
        if not locator.is_visible(timeout=500):
            return None
    except Exception:
        return None
    text = _element_text(locator)
    if not text:
        return None
    try:
        box = locator.bounding_box(timeout=750)
    except Exception:
        box = None
    try:
        extra = locator.evaluate(
            r"""
            (el) => {
              const cs = getComputedStyle(el);
              const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
              const ownText = clean(el.innerText).slice(0, 300);

              // Walk ABOVE the control. Starting at the element itself and
              // keeping the first non-empty innerText would freeze this at the
              // button's own label, which is never the surrounding banner copy.
              let ancestorText = '';
              let hasFixedAncestor = cs.position === 'fixed' || cs.position === 'sticky';
              let node = el.parentElement;
              for (let i = 0; node && i < 6; i++, node = node.parentElement) {
                const style = getComputedStyle(node);
                if (style.position === 'fixed' || style.position === 'sticky') hasFixedAncestor = true;
                const text = clean(node.innerText);
                if (text.length > ancestorText.length) ancestorText = text.slice(0, 1000);
              }

              const tabIndexAttr = el.getAttribute('tabindex');
              const focusableTag = ['button', 'a', 'input', 'select', 'textarea'].includes(el.tagName.toLowerCase());
              const keyboardFocusable = !el.disabled
                && cs.visibility !== 'hidden'
                && cs.display !== 'none'
                && (focusableTag || (tabIndexAttr !== null && Number(tabIndexAttr) > -1));

              return {
                tag: el.tagName.toLowerCase(),
                id: el.id || '',
                className: typeof el.className === 'string' ? el.className.slice(0, 400) : '',
                role: el.getAttribute('role') || '',
                ariaLabel: el.getAttribute('aria-label') || '',
                // `type` and `ariaChecked` exist for the category-toggle veto.
                // A control that flips its own state is not one that performs
                // an action, and clicking it grants or withdraws a consent
                // category. `ariaChecked` is deliberately null (not '') when
                // absent, so "has a checked state" stays distinguishable from
                // "is checked, currently false".
                type: el.getAttribute('type') || '',
                ariaChecked: el.getAttribute('aria-checked'),
                ownText,
                ancestorText,
                hasFixedAncestor,
                tabIndex: el.tabIndex,
                tabIndexAttribute: tabIndexAttr,
                keyboardFocusable,
                disabled: !!el.disabled,
                style: {
                  fontSize: cs.fontSize,
                  fontWeight: cs.fontWeight,
                  color: cs.color,
                  backgroundColor: cs.backgroundColor,
                  borderColor: cs.borderColor,
                  opacity: cs.opacity,
                  display: cs.display,
                  visibility: cs.visibility
                },
                html: el.outerHTML.slice(0, 1200)
              };
            }
            """
        )
    except Exception:
        extra = {}
    return {
        "locator": locator,
        "frame": frame,
        "frame_url": frame.url,
        "index": index,
        "text": text[:300],
        "box": box,
        **(extra or {}),
    }


ANNOTATION_LAYER_ID = "__cba_annotations"

_ANNOTATE_JS = r"""
(payload) => {
  const {marks, layerId} = payload;
  const previous = document.getElementById(layerId);
  if (previous) previous.remove();
  const layer = document.createElement('div');
  layer.id = layerId;
  layer.style.cssText = 'position:fixed;left:0;top:0;right:0;bottom:0;z-index:2147483647;pointer-events:none';
  const drawable = marks.filter(m => m.box && m.box.width > 0 && m.box.height > 0);
  // Two passes so that every label sits above every outline. Interleaving them
  // lets a later control's outline paint over an earlier control's label, which
  // on a stacked accept/decline pair struck through the very text that says
  // which button is which.
  for (const mark of drawable) {
    const box = mark.box;
    const outline = document.createElement('div');
    outline.style.cssText =
      'position:fixed;box-sizing:border-box;pointer-events:none;' +
      `left:${box.x}px;top:${box.y}px;width:${box.width}px;height:${box.height}px;` +
      `border:3px solid ${mark.color};`;
    layer.appendChild(outline);
  }
  for (const mark of drawable) {
    const box = mark.box;
    const tag = document.createElement('div');
    tag.textContent = mark.label;
    tag.style.cssText =
      'position:fixed;pointer-events:none;white-space:nowrap;padding:1px 6px;' +
      'font:bold 12px/16px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;color:#fff;' +
      `left:${box.x}px;top:${Math.max(0, box.y - 18)}px;background:${mark.color};`;
    layer.appendChild(tag);
  }
  const drawn = drawable.length;
  document.documentElement.appendChild(layer);
  return drawn;
}
"""


def annotate_controls(page: Page, marks: list[dict[str, Any]]) -> int:
    """Overlay labelled outlines on the page for the pre-flight screenshot (A7).

    `locator.bounding_box()` reports main-frame viewport coordinates even for an
    element inside an iframe, so fixed-position overlays land correctly on
    iframe-hosted CMPs without walking frame offsets by hand.

    The overlay is drawn into the top document only, is `pointer-events:none`,
    and is removed on the next call. It exists purely to be photographed - it is
    never present during a capture scenario, so it cannot influence what the
    page or its tags observe. Returns how many marks were actually drawn;
    a control with no measurable box is skipped rather than drawn at the origin,
    where it would read as a control sitting in the top-left corner.
    """
    try:
        return int(page.evaluate(_ANNOTATE_JS, {"marks": marks, "layerId": ANNOTATION_LAYER_ID}) or 0)
    except Exception:
        return 0


def annotation_layer_present(page: Page) -> bool:
    """Is the annotation overlay still attached to the document?

    Observed in the wild on a React site: a framework that reconciles the top
    document after hydration can remove an element appended to `<html>`,
    silently and asynchronously. The overlay then vanishes between being drawn
    and being photographed, and the run reports "annotated screenshot" over an
    image with no annotations on it - a caption describing something that is
    not in the picture, which is the defect class this tool exists to avoid.
    Callers re-draw and re-check rather than trusting the first draw.
    """
    try:
        return bool(page.evaluate(
            "(id) => Boolean(document.getElementById(id))", ANNOTATION_LAYER_ID
        ))
    except Exception:
        return False


#: What counts as a candidate control. Shared by the full collector and the
#: cheap prescreen so both walk exactly the same element set in the same order
#: - `_score_controls` addresses prescreened rows by index, and the two would
#: silently disagree about which element index 7 is if they ever diverged.
CONTROL_SELECTOR = "button, [role='button'], a, input[type='button'], input[type='submit']"

#: Fields cheap enough to fetch for every control on the page in one round
#: trip. Deliberately exactly what `veto_control` and `label_score` need and
#: nothing more: geometry and ancestor copy cost a round trip each, and are
#: only worth paying for on a control that already reads as the kind sought.
#:
#: `text` replicates `_element_text`'s ladder (innerText, then aria-label,
#: value, title; first non-empty wins, whitespace collapsed) and its 300-char
#: bound. If the two ever diverge, a control would be scored on one string and
#: recorded with another - so the alignment is asserted by test.
_PRESCREEN_JS = r"""
(els, cap) => els.slice(0, cap).map((el, i) => {
  const clean = v => String(v == null ? '' : v).replace(/\s+/g, ' ').trim();
  let text = '';
  for (const source of [el.innerText, el.getAttribute('aria-label'),
                        el.getAttribute('value'), el.getAttribute('title')]) {
    const cleaned = clean(source);
    if (cleaned) { text = cleaned; break; }
  }
  return {
    index: i,
    text: text.slice(0, 300),
    tag: el.tagName.toLowerCase(),
    role: el.getAttribute('role') || '',
    type: el.getAttribute('type') || '',
    ariaChecked: el.getAttribute('aria-checked'),
  };
})
"""


def collect_visible_controls(page: Page, max_per_frame: int = 220) -> list[dict[str, Any]]:
    """Collect candidate controls across every frame.

    Playwright's CSS engine pierces open shadow roots, so CMPs that render into
    a shadow DOM (Usercentrics, and increasingly others) are covered without
    explicit traversal here; iterating `page.frames` covers iframe-based CMPs
    such as Sourcepoint and TrustArc. Closed shadow roots remain unreachable by
    any automation and are reported as a detection limitation.
    """
    controls: list[dict[str, Any]] = []
    for frame in page.frames:
        try:
            locator = frame.locator(CONTROL_SELECTOR)
            count = min(locator.count(), max_per_frame)
        except Exception:
            continue
        for index in range(count):
            metadata = _control_metadata(locator.nth(index), frame, index)
            if metadata:
                controls.append(metadata)
    return controls


def _public_control(control: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in control.items() if k not in {"locator", "frame"}}


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _untrusted_text(value: Any, limit: int) -> str:
    """Collapse page-authored text to one bounded, single-line string.

    Everything a control carries - its label, its surrounding copy, its markup
    - is written by the audited site. When a resolution conflict is printed for
    a person or an agent to adjudicate, that text is being rendered next to the
    tool's own output, and a site can put anything in it: a fake section break,
    a line claiming to be an instruction, whatever it likes.

    This does not make such text safe, and is not what makes the design safe -
    a verdict is re-resolved and re-vetoed before it can be acted on, so the
    worst a convincing string can achieve is a refusal. What this does is stop
    page text from *impersonating the report's own structure*, by removing the
    control characters and newlines that would let it draw one.
    """
    text = _CONTROL_CHARS.sub("", str(value if value is not None else ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


_CSS_PATH_JS = r"""
(el) => {
  const seg = (n) => {
    if (n.id) return '#' + CSS.escape(n.id);
    let index = 1;
    for (let s = n.previousElementSibling; s; s = s.previousElementSibling) {
      if (s.tagName === n.tagName) index++;
    }
    return n.tagName.toLowerCase() + ':nth-of-type(' + index + ')';
  };
  const parts = [];
  for (let n = el; n && n.nodeType === 1 && parts.length < 8; n = n.parentElement) {
    const s = seg(n);
    parts.unshift(s);
    if (s.charAt(0) === '#') break;
  }
  return parts.join(' > ');
}
"""

# Are these two candidates the same control?
#
# Asked because the CMP table and the text scorer resolve independently, and
# they routinely reach the *same* control by different routes - the table
# naming a `<span>` the scorer reached through its parent `<button>`. Reporting
# that as a disagreement would fail the run closed over nothing.
#
# `isConnected` is checked first and deliberately. A node detached between
# resolution and comparison otherwise reports as `distinct` rather than
# raising, which would record a false conflict as though it were a real one;
# "I could not tell" and "they are different" must stay different answers,
# because only one of them says something about the page.
#
# `getRootNode()` separates shadow roots and frame documents before `contains`
# is consulted, since `contains` does not cross either boundary and would
# answer `false` for reasons that have nothing to do with the two elements.
#
# The blocker walk is what makes containment mean "a click on either lands on
# the same handler": if anything actionable sits between the inner and outer
# element, they are two controls that happen to be nested, not one.
_SAME_CONTROL_JS = r"""
(el, other) => {
  if (!el || !other) return {rel: 'unknown', why: 'missing'};
  if (!el.isConnected || !other.isConnected) return {rel: 'unknown', why: 'detached'};
  if (el === other) return {rel: 'same'};
  if (el.getRootNode() !== other.getRootNode()) return {rel: 'distinct', why: 'different_root'};
  const inner = el.contains(other) ? other : (other.contains(el) ? el : null);
  if (!inner) return {rel: 'distinct', why: 'unrelated'};
  const outer = inner === el ? other : el;
  // Counts the inner candidate itself, not only what sits above it. A
  // <span> inside its own <button> is one control reached two ways; a
  // <button> inside a role="button" anchor is two controls that happen to
  // nest, and clicking the inner one is not the same act as clicking the
  // outer one even though the event reaches both.
  let actionable = 0;
  for (let n = inner; n && n !== outer; n = n.parentElement) {
    if (n.matches('button, a, [role="button"], input')) actionable++;
  }
  return {rel: actionable ? 'distinct' : 'containment', why: actionable ? 'nested_actionable' : ''};
}
"""


def _control_ref(control: dict[str, Any] | None) -> dict[str, Any] | None:
    """A stable, re-resolvable description of one candidate control.

    `_public_control` keeps everything the browser gave us, including a live
    `Locator` the moment the page goes away. This is the form that has to
    survive being written to disk, read by a person or an agent, and turned
    back into a selector on a *later* load - so it carries a `css_path` and
    the element's own identifying attributes rather than a handle.

    `css_path` is a best effort and will not survive a framework reshuffling
    the DOM between one load and the next. That is exactly why a verdict
    naming a selector is re-resolved and re-vetoed at the point it is used,
    instead of being trusted because it once matched.
    """
    if not control:
        return None
    class_tokens = [t for t in str(control.get("className") or "").split() if t][:8]
    css_path = ""
    locator = control.get("locator")
    if locator is not None:
        try:
            css_path = str(locator.evaluate(_CSS_PATH_JS) or "")
        except Exception:
            css_path = ""
    ref = {
        "frame_url": control.get("frame_url"),
        "tag": control.get("tag"),
        "id": control.get("id"),
        "class_tokens": class_tokens,
        "role": control.get("role"),
        "aria_label": _untrusted_text(control.get("ariaLabel"), 120),
        "type": control.get("type"),
        "text": _untrusted_text(control.get("text"), 120),
        "box": control.get("box"),
        "css_path": css_path,
        # Deliberately shorter than the 1200 characters `_control_metadata`
        # captures: enough to see the tag and its attributes when adjudicating,
        # with less room to hide a paragraph addressed to the reader.
        "html_excerpt": _untrusted_text(control.get("html"), 400),
    }
    if control.get("matched_selector") is not None:
        ref["matched_selector"] = control.get("matched_selector")
    if control.get("score") is not None:
        ref["score"] = control.get("score")
    return ref


def _relation_verdict(result: dict[str, Any]) -> tuple[bool | None, str]:
    """Map one `_SAME_CONTROL_JS` answer onto `(verdict, basis)`.

    Split out from `_same_control` so the mapping can be exercised for every
    relation the JS can return. The `unknown` arms are otherwise reachable
    only by winning a race - a node detached in the window between taking its
    handle and evaluating against it - which no test can schedule reliably.
    Anything unrecognised falls through to undetermined rather than to a
    verdict, so a future relation added to the JS fails safe.
    """
    relation = str(result.get("rel") or "")
    why = str(result.get("why") or "")
    if relation == "same":
        return True, "identical"
    if relation == "containment":
        return True, "containment"
    if relation == "distinct":
        return False, why or "distinct"
    return None, why or "unknown"


def _same_control(a: dict[str, Any] | None, b: dict[str, Any] | None) -> tuple[bool | None, str]:
    """Do these two candidates refer to one control? `(verdict, basis)`.

    A `None` verdict means undetermined, and is never quietly folded into
    either answer: the caller treats it the same way it treats a real
    disagreement (refuse to click) but records that it could not tell, which
    is a different sentence in a report than "these are two controls".
    """
    if not a or not b:
        return None, "missing"
    # Two frames are two clickable things even when they look identical, and
    # a handle from one frame cannot be reasoned about inside another.
    if a.get("frame") is not b.get("frame"):
        return False, "different_frame"

    for attempt in range(2):
        result: dict[str, Any] = {}
        handle = None
        try:
            handle = b["locator"].element_handle(timeout=1000)
            if handle is None:
                raise RuntimeError("no element handle")
            result = a["locator"].evaluate(_SAME_CONTROL_JS, handle) or {}
        except Exception as error:
            if attempt == 0:
                _sleep_ms(250)
                continue
            return None, f"error:{str(error)[:120]}"
        finally:
            if handle is not None:
                try:
                    handle.dispose()
                except Exception:
                    pass
        verdict, basis = _relation_verdict(result)
        if verdict is not None:
            return verdict, basis
        # A CMP mid-animation can detach and re-attach a node; one settle and
        # retry distinguishes that from a control that is genuinely gone.
        if attempt == 0:
            _sleep_ms(250)
            continue
        return None, basis
    return None, "unknown"


SCORE_THRESHOLD = 70
BARE_LABELS = {"reject", "decline", "deny", "refuse", "accept", "allow", "agree", "save", "confirm", "ok"}


def _banner_associated(control: dict[str, Any]) -> bool:
    """Is this control plausibly part of a consent banner at all?

    Used to decide whether a bare label like "Accept" is the banner's control or
    an unrelated button elsewhere on the page. Either consent wording nearby or
    a fixed/sticky container counts.
    """
    return bool(BANNER_KEYWORDS.search(str(control.get("ancestorText", "")))) or bool(control.get("hasFixedAncestor"))


def _banner_context_score(control: dict[str, Any]) -> int:
    score = 0
    ancestor = str(control.get("ancestorText", ""))
    if BANNER_KEYWORDS.search(ancestor):
        score += 35
    if control.get("hasFixedAncestor"):
        score += 20
    text = str(control.get("text", ""))
    if BANNER_KEYWORDS.search(text):
        score += 5
    box = control.get("box") or {}
    if box and box.get("width", 0) > 40 and box.get("height", 0) > 20:
        score += 5
    return score


def fingerprint_cmp(page: Page, cmp_table: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Identify the consent platform from DOM markers and loaded script hosts.

    CMP vendors ship stable element ids while button labels vary by site,
    language, and configuration, so a fingerprint match is a far more reliable
    way to reach the controls than reading their text.
    """
    table = cmp_table if cmp_table is not None else load_cmp_table()
    if not table:
        return None

    script_hosts: set[str] = set()
    for frame in page.frames:
        try:
            sources = frame.eval_on_selector_all("script[src]", "els => els.map(e => e.src)")
        except Exception:
            continue
        for source in sources or []:
            try:
                host = (urlsplit(str(source)).hostname or "").lower()
            except Exception:
                continue
            if host:
                script_hosts.add(host)

    for entry in table:
        fingerprint = entry.get("fingerprint") or {}
        for selector in fingerprint.get("selectors") or []:
            for frame in page.frames:
                try:
                    if frame.locator(selector).count() > 0:
                        return {"id": entry.get("id"), "name": entry.get("name"), "matched_by": f"selector:{selector}", "entry": entry}
                except Exception:
                    continue
        for host_fragment in fingerprint.get("script_hosts") or []:
            if any(host_fragment in host for host in script_hosts):
                return {"id": entry.get("id"), "name": entry.get("name"), "matched_by": f"script_host:{host_fragment}", "entry": entry}
    return None


def _locate_by_selectors(page: Page, selectors: list[str] | None) -> dict[str, Any] | None:
    """Resolve the first visible element matching any of `selectors`, any frame.

    A selector can match more than one element - a hidden preference-center
    copy of a control alongside the visible banner one is a real shape (seen
    on CookieYes). Check every match for visibility before moving to the next
    selector, not just the first; `.first` being invisible does not mean the
    selector has no visible match.
    """
    for selector in selectors or []:
        for frame in page.frames:
            try:
                locator = frame.locator(selector)
                count = locator.count()
            except Exception:
                continue
            for index in range(min(count, 10)):
                try:
                    candidate = locator.nth(index)
                    if not candidate.is_visible(timeout=750):
                        continue
                except Exception:
                    continue
                metadata = _control_metadata(candidate, frame, index)
                if metadata:
                    metadata["matched_selector"] = selector
                    return metadata
    return None


def _adjudication_id(
    resolution: dict[str, Any],
    table_control: dict[str, Any] | None,
    scorer_control: dict[str, Any] | None,
) -> str:
    """A stable name for one conflict, so a verdict about it can be matched back.

    Hashes only what survives a reload: the kind and call-site label, the CMP
    id, the selector that matched, and the scorer candidate's normalised text.
    Deliberately *not* the box or the markup - both move between loads, and an
    id derived from them would make every verdict single-use, expiring before
    the re-run it exists to unblock.
    """
    parts = [
        str(resolution.get("kind") or ""),
        str(resolution.get("label") or ""),
        str(resolution.get("cmp") or ""),
        str((table_control or {}).get("matched_selector") or ""),
        _untrusted_text((scorer_control or {}).get("text"), 120).lower(),
    ]
    return short_hash("|".join(parts))


def _score_controls(page: Page, kind: str, max_per_frame: int = 220) -> list[tuple[int, dict[str, Any]]]:
    """Every visible control that reads as `kind`, best first.

    Split out of `find_control` so the generic method can run unconditionally
    - including when the CMP table already produced a candidate, which is the
    whole point of cross-checking.

    Two passes, because running always made the cost matter. Building full
    metadata for every control costs about four round trips each (visibility,
    text, geometry, and a computed-style evaluate), which measured at ~18ms
    per control - and the candidate selector counts every anchor on the page,
    so real sites reach the 220 cap easily. Six find_control calls per denial
    scenario turned that into tens of seconds of pure overhead.

    So the first pass fetches only what disqualifies or recognises a control -
    its label, tag, role, type and checked state - for the whole page in one
    round trip. Only controls that survive the veto *and* read as this kind
    get the expensive treatment. On a real banner that is a handful of
    elements rather than hundreds.

    This is a pure speed change: the surviving set and its scores are
    identical, because a control scoring zero was discarded anyway. The veto
    is applied twice, cheaply, so a divergence between the prescreen's view of
    an element and the full metadata's could never let a vetoed control
    through.
    """
    scored: list[tuple[int, dict[str, Any]]] = []
    for frame in page.frames:
        try:
            rows = frame.eval_on_selector_all(CONTROL_SELECTOR, _PRESCREEN_JS, max_per_frame) or []
        except Exception:
            continue
        shortlist: list[int] = []
        for row in rows:
            # No early-out for a textless control: `label_score` already scores
            # it zero, so skipping it here would only duplicate that decision
            # in a second place, untested, where the two could drift apart.
            #
            # Disqualification first, fitness second. A vetoed candidate is
            # dropped whatever it scores - the two questions are separate, and
            # the same veto polices the CMP table's candidate in find_control.
            if checks.veto_control(kind, row):
                continue
            if checks.label_score(row["text"], kind):
                shortlist.append(int(row["index"]))
        if not shortlist:
            continue
        locator = frame.locator(CONTROL_SELECTOR)
        for index in shortlist:
            control = _control_metadata(locator.nth(index), frame, index)
            if not control or checks.veto_control(kind, control):
                continue
            text = str(control.get("text", "")).strip()
            base = checks.label_score(text, kind)
            if not base:
                continue
            score = base + _banner_context_score(control)
            # Penalise a bare label only when nothing ties it to a consent
            # banner. Applying it whenever the label itself lacks consent
            # wording would reject the plain "Accept"/"Decline" buttons most
            # CMPs actually ship.
            if text.lower() in BARE_LABELS and not _banner_associated(control):
                score -= 80
            scored.append((score, control))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _matching_verdict(resolution: dict[str, Any], verdicts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The verdict addressed to this unresolved control, if any.

    Matched by `adjudication_id` first, which names one conflict exactly. The
    `(kind, label, cmp)` fallback exists because a re-run can legitimately
    produce a differently-hashed conflict - a vendor changed the competing
    label, say - and an operator who has already decided should not have to
    decide again because a string moved.
    """
    conflict_id = (resolution.get("conflict") or {}).get("adjudication_id")
    for verdict in verdicts:
        if conflict_id and verdict.get("adjudication_id") == conflict_id:
            return verdict
    for verdict in verdicts:
        if verdict.get("adjudication_id"):
            continue
        if verdict.get("kind") != resolution.get("kind"):
            continue
        if verdict.get("label") not in (None, resolution.get("label")):
            continue
        if verdict.get("cmp") not in (None, resolution.get("cmp")):
            continue
        return verdict
    return None


def apply_control_verdict(
    page: Page,
    resolution: dict[str, Any],
    verdicts: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Act on an operator's decision about a control this run could not resolve.

    **A verdict is a proposal, never an instruction.** Everything it names is
    re-established here, against the page as it is now:

      1. The selector is re-resolved. A verdict written against an earlier
         load may name an element that has moved or gone.
      2. The resolved element goes through `checks.veto_control` - the same
         gate every other candidate passes. This is the rule that matters: a
         verdict naming the accept button cannot get it clicked as a denial,
         whatever the file says and whoever wrote it.
      3. If the verdict states an expected accessible name, the element has to
         still have it. Cheap check that the page did not change underneath.
      4. The element must not be what the scorer independently reads as an
         incompatible kind. This catches the case rule 2 cannot see: an
         unlabelled control whose own text says nothing, but which the page
         plainly uses as its accept button.

    That ordering is deliberate and is the whole security argument. The text
    an operator or agent read to make this decision came from the audited
    page, and a page can write anything into a label or an aria attribute. A
    successful attempt to mislead can therefore cost a refusal, or a click on
    a semantically clean but wrong control - it can never produce the click
    the page was angling for, because the refusal is enforced here in Python
    rather than requested in a prompt.

    Only ever called for a control that is already not clickable, so a verdict
    can unstick a run and never redirect a working one.
    """
    if not verdicts or resolution.get("clickable"):
        return None
    verdict = _matching_verdict(resolution, verdicts or [])
    if verdict is None:
        return None

    kind = str(resolution.get("kind"))
    record: dict[str, Any] = {
        "applied": False,
        "decision": verdict.get("decision"),
        "selector": verdict.get("selector"),
        "rationale": _untrusted_text(verdict.get("rationale"), 300),
        "matched_by": "adjudication_id" if verdict.get("adjudication_id") else "kind_label_cmp",
        "rejected_reason": None,
    }
    resolution["agent_verdict"] = record

    if verdict.get("decision") == "refuse":
        # "There genuinely is no such control here" is a different statement
        # from "the tool could not tell", and a materially different sentence
        # for a compliance reader. Recorded, still not clicked.
        record["applied"] = True
        resolution["agent_refused"] = True
        return None

    control = _locate_by_selectors(page, [str(verdict.get("selector"))])
    if control is None:
        record["rejected_reason"] = "selector_did_not_resolve"
        return None

    veto = checks.veto_control(kind, control)
    if veto:
        record["rejected_reason"] = veto["reason"]
        record["rejected_detail"] = {"conflicting_kind": veto.get("conflicting_kind"),
                                     "observed_label": veto.get("observed_label")}
        return None

    expected = verdict.get("expected_accessible_name")
    if expected:
        seen = _untrusted_text(control.get("text"), 300).casefold()
        if _untrusted_text(expected, 300).casefold() != seen:
            record["rejected_reason"] = "accessible_name_mismatch"
            record["rejected_detail"] = {"expected": _untrusted_text(expected, 120),
                                         "observed": _untrusted_text(control.get("text"), 120)}
            return None

    # There is deliberately no further check that this element is not the one
    # the scorer reads as an incompatible kind. Such a check would be
    # unreachable: the scorer only ranks an element it recognises, so any
    # element it reads as `accept` has a non-zero accept label score, and
    # `veto_control` above refuses exactly those for `reject`. The rule would
    # be strictly weaker than the veto that already ran, and an unreachable
    # branch is one nothing can prove still works.

    record["applied"] = True
    control["matched_selector"] = str(verdict.get("selector"))
    resolution.update(
        path="agent_verdict",
        decision="agent_verdict",
        clickable=True,
        matched_selector=str(verdict.get("selector")),
    )
    return control


def _verdict_or(
    page: Page,
    resolution: dict[str, Any],
    control_verdicts: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Give an operator's verdict a chance to unstick a refused control.

    Returns the control if one was authorised, `None` otherwise - so a
    refusal with no verdict, a verdict that does not match, and a verdict that
    failed re-checking all collapse to the same safe answer, each having
    recorded a different reason for it.
    """
    return apply_control_verdict(page, resolution, control_verdicts)


def find_control(
    page: Page,
    kind: str,
    cmp_entry: dict[str, Any] | None = None,
    label: str | None = None,
    control_verdicts: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any]]:
    """Resolve a consent control by cross-checking two independent resolvers.

    Returns `(control, candidates, resolution)`.

    The CMP selector table used to be tried first and returned on the first
    match, before the text scorer ever ran. A wrong table entry therefore did
    not degrade to the safer generic path - it pre-empted it, and it also
    bypassed the veto the scorer applies to its own candidates. That is not
    hypothetical: `#onetrust-pc-btn-handler + button` sat in OneTrust's
    `reject` list and resolved to "Allow All" on any site without an optional
    reject button, so a denial scenario clicked accept and reported a
    completed denial.

    Both resolvers now always run. The table is a fast path and a
    corroborating witness, never an authority: it can say *where* an element
    is, which is no evidence at all about *what that element does*.

    `resolution["decision"]` records which of these happened, and
    `resolution["clickable"]` is the single field callers key off so no caller
    can re-derive the safety rule differently:

      corroborated  both resolvers reached the same control
      table_only    the table matched, the scorer recognised nothing, and the
                    candidate is not contradicted - the ordinary case for a
                    CMP whose copy the English pattern lists do not know
      scorer_only   the table missed, or its candidate was vetoed
      vetoed        the table's candidate is disqualified and nothing else
                    resolved
      conflict      both resolvers are confident and disagree, or identity
                    could not be established
      unresolved    neither resolver produced anything

    Only `conflict`, `vetoed` and `unresolved` refuse to click. A conflict is
    deliberately *not* broken by preferring one resolver: this tool produces
    compliance evidence, and a false "we confirmed the reject button" is worse
    than an honest "we could not identify it".
    """
    resolution: dict[str, Any] = {
        "kind": kind,
        "label": label or kind,
        "path": "none",
        "decision": "unresolved",
        "clickable": False,
        "matched_selector": None,
        "cmp": None,
        # Every key is present on every resolution, defaulting to None or
        # False, rather than appearing only when it has something to say. A
        # consumer should never have to distinguish "this run had no conflict"
        # from "this build did not record conflicts", and the schema check in
        # the suite compares key sets exactly - a sometimes-key would make the
        # documented contract unenforceable in the direction that matters.
        "cmp_table_miss": False,
        "score": None,
        "best_score": None,
        "threshold": SCORE_THRESHOLD,
        "veto": None,
        "conflict": None,
        "corroboration": None,
        "agent_verdict": None,
        "agent_refused": False,
    }

    table_control = None
    if cmp_entry:
        resolution["cmp"] = cmp_entry.get("id")
        table_control = _locate_by_selectors(page, cmp_entry.get(kind))
        if table_control is None:
            resolution["cmp_table_miss"] = True
        else:
            veto = checks.veto_control(kind, table_control)
            if veto:
                # Recorded even when the scorer goes on to save the run: a
                # table entry resolving to a contradictory control is a fact
                # about the table worth surfacing before it is an incident.
                resolution["veto"] = {
                    "resolver": "cmp_selector_table",
                    "matched_selector": table_control.get("matched_selector"),
                    "control_ref": _control_ref(table_control),
                    **veto,
                }
                table_control = None

    scored = _score_controls(page, kind)
    best_score = scored[0][0] if scored else None
    scorer_control = scored[0][1] if scored and scored[0][0] >= SCORE_THRESHOLD else None

    candidates: list[dict[str, Any]] = [
        {"score": score, "source": "text_scoring", **_public_control(control)}
        for score, control in scored[:20]
    ]
    if table_control is not None:
        candidates.insert(0, {
            "score": None, "source": "cmp_selector_table", **_public_control(table_control),
        })
    resolution["best_score"] = best_score
    resolution["threshold"] = SCORE_THRESHOLD

    if table_control is not None and scorer_control is not None:
        same, basis = _same_control(table_control, scorer_control)
        resolution["corroboration"] = {
            "scorer_score": scored[0][0],
            "scorer_threshold": SCORE_THRESHOLD,
            "same_canonical_element": same,
            "identity_basis": basis,
        }
        if same is True:
            resolution.update(
                path="cmp_selector_table",
                decision="corroborated",
                clickable=True,
                matched_selector=table_control.get("matched_selector"),
                score=scored[0][0],
            )
            return table_control, candidates, resolution
        # Disagreement, or identity that could not be established. Both refuse
        # to click; `identity_basis` is what tells them apart afterwards.
        resolution.update(path="none", decision="conflict", clickable=False)
        resolution["conflict"] = {
            "table_candidate": _control_ref(table_control),
            "scorer_candidate": _control_ref(scorer_control),
            "identity_basis": basis,
            "adjudication_id": _adjudication_id(resolution, table_control, scorer_control),
        }
        return _verdict_or(page, resolution, control_verdicts), candidates, resolution

    if table_control is not None:
        # The table matched and the scorer recognised nothing above threshold.
        # Not a disagreement - there is only one candidate, and it survived the
        # same veto the scorer applies to its own. Requiring corroboration here
        # would make every CMP whose copy is not English unresolvable; the
        # provenance ratchet, not this function, is what keeps the table honest.
        resolution.update(
            path="cmp_selector_table",
            decision="table_only",
            clickable=True,
            matched_selector=table_control.get("matched_selector"),
        )
        return table_control, candidates, resolution

    if scorer_control is not None:
        resolution.update(
            path="text_scoring", decision="scorer_only", clickable=True, score=scored[0][0]
        )
        return scorer_control, candidates, resolution

    resolution.update(
        path="none",
        decision="vetoed" if resolution["veto"] else "unresolved",
        clickable=False,
    )
    return _verdict_or(page, resolution, control_verdicts), candidates, resolution


def click_control(control: dict[str, Any], action_log: list[dict[str, Any]], kind: str) -> bool:
    locator: Locator = control["locator"]
    record = {
        "time": utc_now(),
        "action": f"click_{kind}",
        "control": _public_control(control),
        "success": False,
    }
    try:
        locator.scroll_into_view_if_needed(timeout=2500)
    except Exception:
        pass
    try:
        locator.click(timeout=7000)
        record["success"] = True
    except Exception as first_error:
        record["first_error"] = str(first_error)[:800]
        try:
            locator.click(timeout=4000, force=True)
            record["success"] = True
            record["forced"] = True
        except Exception as second_error:
            record["second_error"] = str(second_error)[:800]
    action_log.append(record)
    return bool(record["success"])


#: Upper bound on Tab presses when walking real keyboard focus order, so a
#: page with hundreds of focusable elements cannot hang the scenario.
MAX_TAB_PRESSES = 60

_TAB_PROBE_ATTR = "data-cba-tab-probe"

# Reads the currently-focused element's probe label (if any) and a stable
# per-element identity used to detect when Tab traversal has wrapped back
# around to an element it already visited - the signal that a full pass over
# the page's focus order was observed, as distinct from merely running out
# of Tab-press budget. The identity is kept in a JS-side WeakMap rather than
# a DOM attribute so it never touches the page's markup or styling.
#
# When focus is inside a child frame, *this* frame's own `document.activeElement`
# is the `<iframe>`/`<frame>` element itself, not the control that actually has
# focus - the real focus stop lives in the child frame's own document. Reporting
# the frame owner as a focus stop here would wrongly resolve iframe-hosted
# controls (Sourcepoint, TrustArc, and similar CMPs render into an iframe) as
# some other, untagged element, and would derive cycle identity from the
# stable iframe element rather than from whatever is actually focused inside
# it. So a frame owner is flagged and never treated as a real stop; the caller
# keeps scanning the remaining frames for the child frame that reports a real,
# non-frame-owner `activeElement` - deriving both `tag` and `cycleId` from that
# innermost focused element instead.
_ACTIVE_ELEMENT_PROBE_JS = f"""
() => {{
  const el = document.activeElement;
  if (!el || el === document.body) {{
    return {{ tag: null, cycleId: null, isFrameOwner: false }};
  }}
  const ownerTag = el.tagName ? el.tagName.toLowerCase() : '';
  if (ownerTag === 'iframe' || ownerTag === 'frame') {{
    return {{ tag: null, cycleId: null, isFrameOwner: true }};
  }}
  if (!window.__cbaTabCycleMap) {{
    window.__cbaTabCycleMap = new WeakMap();
    window.__cbaTabCycleCounter = 0;
  }}
  let id = window.__cbaTabCycleMap.get(el);
  if (id === undefined) {{
    id = ++window.__cbaTabCycleCounter;
    window.__cbaTabCycleMap.set(el, id);
  }}
  return {{ tag: el.getAttribute('{_TAB_PROBE_ATTR}'), cycleId: String(id), isFrameOwner: false }};
}}
"""

_FOCUS_STYLE_JS = r"""
(el) => {
  const cs = getComputedStyle(el);
  return {
    outlineWidth: cs.outlineWidth,
    outlineStyle: cs.outlineStyle,
    outlineColor: cs.outlineColor,
    boxShadow: cs.boxShadow,
    borderWidth: cs.borderWidth,
    borderStyle: cs.borderStyle,
    borderColor: cs.borderColor,
  };
}
"""


def measure_tab_order(
    page: Page,
    labeled_locators: dict[str, Locator],
    max_presses: int = MAX_TAB_PRESSES,
) -> dict[str, Any]:
    """Walk the page's real keyboard focus order and record the Tab-press
    index at which each labeled control first receives focus.

    This measures the browser's actual focus order - by pressing `Tab` and
    reading `document.activeElement` back out, across every frame - rather
    than inferring it from DOM order or `tabindex` values. A control that
    appears first in markup can still be reached last, or never, depending on
    tabindex and focusability quirks.

    Bounded to `max_presses` so a page with hundreds of focusable elements
    cannot hang the scenario. A missing control is ambiguous on its own: it
    either does not appear anywhere in the page's focus order, or it simply
    sits past the budget. This is resolved by watching for the traversal
    wrapping back around to an element it already visited - proof that a
    full pass over the page's real focus order was observed. When that
    wrap is seen before the budget runs out, any control still missing is
    genuinely absent from the focus order (`cap_hit` is False - the budget
    was never the limiting factor). When the budget is exhausted first, or the
    traversal aborts (a `Tab` press itself raises) before completing a lap,
    `cap_hit` is True and a missing control's reachability is unknown, not
    false "not reachable".
    """
    positions: dict[str, int | None] = {name: None for name in labeled_locators}
    tagged: list[Locator] = []
    budget_exhausted = False
    cycle_observed = False
    aborted = False
    try:
        for name, locator in labeled_locators.items():
            try:
                locator.evaluate(f"(el, name) => el.setAttribute('{_TAB_PROBE_ATTR}', name)", name)
                tagged.append(locator)
            except Exception:
                continue

        for frame in page.frames:
            try:
                frame.evaluate(
                    "() => { const el = document.activeElement; if (el && el !== document.body) el.blur(); }"
                )
            except Exception:
                pass

        # A DOM mutation immediately followed by a Tab press can race the
        # browser's own tabindex-order computation, producing DOM order
        # rather than tabindex order for one keystroke. A short settle avoids
        # measuring that transient state as if it were the page's real order.
        try:
            page.wait_for_timeout(50)
        except Exception:
            pass

        first_cycle_id: str | None = None
        for press in range(1, max_presses + 1):
            try:
                page.keyboard.press("Tab")
            except Exception:
                # The traversal could not even complete this press - it did
                # not measure a full lap, so treat it the same as running out
                # of budget rather than as proof the remaining controls are
                # unreachable.
                aborted = True
                break
            found_name = None
            current_cycle_id = None
            for frame_index, frame in enumerate(page.frames):
                try:
                    probe = frame.evaluate(_ACTIVE_ELEMENT_PROBE_JS)
                except Exception:
                    continue
                if not probe or probe.get("isFrameOwner"):
                    # Focus is inside a child frame (this frame's own
                    # activeElement is the iframe/frame element itself, not a
                    # real focus stop) - keep scanning the remaining frames
                    # for the innermost frame that actually holds focus.
                    continue
                if probe.get("cycleId") is not None:
                    current_cycle_id = f"{frame_index}:{probe['cycleId']}"
                    found_name = probe.get("tag")
                    break
            if found_name and positions.get(found_name) is None:
                positions[found_name] = press
            if all(value is not None for value in positions.values()):
                break
            if current_cycle_id is not None:
                if first_cycle_id is None:
                    first_cycle_id = current_cycle_id
                elif current_cycle_id == first_cycle_id:
                    # The traversal has returned to the first element it
                    # focused this pass: a full lap of the page's real focus
                    # order has been observed without exhausting the budget.
                    cycle_observed = True
                    break
        else:
            budget_exhausted = True
    finally:
        for locator in tagged:
            try:
                locator.evaluate(f"(el) => el.removeAttribute('{_TAB_PROBE_ATTR}')")
            except Exception:
                pass

    all_found = all(value is not None for value in positions.values())
    cap_hit = (budget_exhausted or aborted) and not all_found and not cycle_observed
    return {"positions": positions, "cap_hit": cap_hit, "max_presses": max_presses}


def measure_focus_visibility(locator: Locator) -> dict[str, Any]:
    """Focus a control and compare its computed outline/box-shadow/border
    against the unfocused state.

    A visible indicator is any measurable change across those properties; a
    control that renders identically focused and unfocused has no focus
    indicator regardless of what its CSS claims to declare.
    """
    try:
        unfocused = locator.evaluate(_FOCUS_STYLE_JS)
    except Exception:
        return {"measured": False, "visible": None, "reason": "could not read unfocused style"}

    try:
        locator.focus(timeout=2000)
    except Exception:
        return {"measured": False, "visible": None, "reason": "control could not be focused"}

    try:
        focused = locator.evaluate(_FOCUS_STYLE_JS)
    except Exception:
        return {"measured": False, "visible": None, "reason": "could not read focused style"}
    finally:
        try:
            locator.evaluate("(el) => el.blur()")
        except Exception:
            pass

    changed = sorted(key for key in unfocused if unfocused.get(key) != focused.get(key))
    return {
        "measured": True,
        "visible": bool(changed),
        "changed_properties": changed,
        "unfocused_style": unfocused,
        "focused_style": focused,
    }


COMMON_BANNER_SELECTORS = [
    "[id*='cookie' i][class*='banner' i]",
    "[id*='consent' i]",
    "[class*='cookie-banner' i]",
    "[class*='consent-banner' i]",
    "[aria-label*='cookie' i]",
]


def banner_visible(page: Page, cmp_entry: dict[str, Any] | None = None) -> bool | None:
    """Is a consent banner currently on screen?

    Returns None only when the DOM could not be queried at all. A selector that
    matches nothing means the banner is not present, which is the usual result
    of a successful dismissal - most CMPs remove the container outright, so
    treating "no match" as undetermined would miss every real dismissal.
    """
    selectors = list((cmp_entry or {}).get("container") or []) or COMMON_BANNER_SELECTORS
    queried = False
    for selector in selectors:
        for frame in page.frames:
            try:
                locator = frame.locator(selector).first
                count = locator.count()
                queried = True
                if count == 0:
                    continue
                if locator.is_visible(timeout=500):
                    return True
            except Exception:
                continue
    return False if queried else None


def consent_snapshot(page: Page, context: BrowserContext, cmp_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fingerprint the consent-relevant state so a click can be proved to change it.

    Values are hashed rather than stored, so this is safe to keep in shareable
    evidence while still detecting a change.

    ``cmp_api`` is the compared signal: only fields that actually move when a
    consent choice changes belong here. ``cmp_api_observational`` carries the
    noisy `dataLayer` byte count for evidence purposes only — it grows with
    every unrelated analytics event and must never feed verification.
    """
    snapshot: dict[str, Any] = {
        "time": utc_now(),
        "cookies": {},
        "local_storage": {},
        "cmp_api": {},
        "cmp_api_observational": {},
    }
    try:
        for cookie in context.cookies():
            key = f"{cookie.get('domain', '')}|{cookie.get('name', '')}"
            snapshot["cookies"][key] = short_hash(str(cookie.get("value", "")))
    except Exception as error:
        snapshot["cookies_error"] = str(error)[:300]
    try:
        raw_storage = page.evaluate(
            """() => {
              const out = {};
              try {
                for (let i = 0; i < localStorage.length; i++) {
                  const key = localStorage.key(i);
                  out[key] = localStorage.getItem(key) || '';
                }
              } catch {}
              return out;
            }"""
        )
        snapshot["local_storage"] = {key: short_hash(str(value)) for key, value in (raw_storage or {}).items()}
    except Exception:
        pass
    try:
        cmp_raw = page.evaluate(
            """() => {
              const isConsentEntry = (entry) => {
                try {
                  if (entry && entry[0] === 'consent') return true;
                  if (entry && typeof entry === 'object' && ('ad_storage' in entry || 'analytics_storage' in entry)) return true;
                } catch {}
                return false;
              };
              const dataLayer = window.dataLayer || [];
              let consentEntries = [];
              let stringLength = null;
              try {
                consentEntries = dataLayer.filter(isConsentEntry);
                stringLength = JSON.stringify(dataLayer).length;
              } catch {}
              return {
                hasTCF: typeof window.__tcfapi === 'function',
                hasUSP: typeof window.__uspapi === 'function',
                hasGPP: typeof window.__gpp === 'function',
                oneTrustActiveGroups: window.OneTrustActiveGroups || null,
                consentEntries: consentEntries,
                consentStateLength: stringLength,
                dataLayerEntryCount: dataLayer.length,
              };
            }"""
        ) or {}
        consent_entries = cmp_raw.get("consentEntries") or []
        snapshot["cmp_api"] = {
            "hasTCF": cmp_raw.get("hasTCF"),
            "hasUSP": cmp_raw.get("hasUSP"),
            "hasGPP": cmp_raw.get("hasGPP"),
            "oneTrustActiveGroups": cmp_raw.get("oneTrustActiveGroups"),
            "consentSignature": short_hash(json.dumps(consent_entries, sort_keys=True, default=str)),
        }
        snapshot["cmp_api_observational"] = {
            "consentStateLength": cmp_raw.get("consentStateLength"),
            "dataLayerEntryCount": cmp_raw.get("dataLayerEntryCount"),
        }
    except Exception:
        pass
    snapshot["banner_visible"] = banner_visible(page, cmp_entry)
    return snapshot


def verify_choice_registered(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Confirm a consent click actually changed something.

    A click that Playwright reports as successful but which leaves cookies,
    storage, CMP state, and banner visibility untouched has not registered a
    choice. Treating that as a completed denial is precisely how an audit ends
    up reporting post-denial behaviour it never captured.

    Only ``cmp_api`` feeds this comparison. ``cmp_api_observational`` (the
    noisy `dataLayer` byte count) is deliberately never read here — it grows
    with unrelated analytics events and would invent verifications.
    """
    before_cookies = before.get("cookies") or {}
    after_cookies = after.get("cookies") or {}
    new_cookies = sorted(set(after_cookies) - set(before_cookies))
    changed_cookies = sorted(k for k in set(before_cookies) & set(after_cookies) if before_cookies[k] != after_cookies[k])

    before_storage = before.get("local_storage") or {}
    after_storage = after.get("local_storage") or {}
    new_storage = sorted(set(after_storage) - set(before_storage))
    changed_storage = sorted(k for k in set(before_storage) & set(after_storage) if before_storage[k] != after_storage[k])

    cmp_changed = (before.get("cmp_api") or {}) != (after.get("cmp_api") or {})
    banner_dismissed = bool(before.get("banner_visible")) and after.get("banner_visible") is False

    state_changed = bool(new_cookies or changed_cookies or new_storage or changed_storage or cmp_changed)
    return {
        "new_cookies": new_cookies,
        "changed_cookies": changed_cookies,
        "new_storage_keys": new_storage,
        "changed_storage_keys": changed_storage,
        "cmp_api_changed": cmp_changed,
        "banner_dismissed": banner_dismissed,
        "consent_state_changed": state_changed,
        "verified": bool(state_changed or banner_dismissed),
        "note": (
            "Click registered a state change." if state_changed or banner_dismissed
            else "Click reported success but no cookie, storage, CMP, or banner change was observed."
        ),
    }


def _switch_label(locator: Locator) -> str:
    try:
        return str(
            locator.evaluate(
                r"""
                (el) => {
                  const pieces = [];
                  const push = value => {
                    const clean = String(value || '').replace(/\s+/g, ' ').trim();
                    if (clean && !pieces.includes(clean)) pieces.push(clean);
                  };
                  push(el.getAttribute('aria-label'));
                  const labelledBy = el.getAttribute('aria-labelledby');
                  if (labelledBy) {
                    for (const id of labelledBy.split(/\s+/)) {
                      const node = document.getElementById(id);
                      if (node) push(node.innerText || node.textContent);
                    }
                  }
                  if (el.id) {
                    const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                    if (label) push(label.innerText || label.textContent);
                  }
                  const closestLabel = el.closest('label');
                  if (closestLabel) push(closestLabel.innerText || closestLabel.textContent);
                  if (!pieces.length && el.parentElement) {
                    const directText = Array.from(el.parentElement.childNodes)
                      .filter(node => node.nodeType === Node.TEXT_NODE)
                      .map(node => node.textContent || '')
                      .join(' ');
                    push(directText);
                  }
                  if (!pieces.length && el.nextElementSibling) push(el.nextElementSibling.innerText || el.nextElementSibling.textContent);
                  if (!pieces.length && el.previousElementSibling) push(el.previousElementSibling.innerText || el.previousElementSibling.textContent);
                  return pieces.join(' | ').slice(0, 1000);
                }
                """
            )
        ).strip()
    except Exception:
        return ""


def _switch_state(locator: Locator) -> bool | None:
    try:
        tag = locator.evaluate("el => el.tagName.toLowerCase()")
        if tag == "input":
            return bool(locator.is_checked(timeout=500))
    except Exception:
        pass
    for attr in ("aria-checked", "aria-pressed", "data-checked"):
        try:
            value = locator.get_attribute(attr, timeout=500)
        except Exception:
            value = None
        if value is not None:
            if str(value).lower() in {"true", "1", "checked", "on"}:
                return True
            if str(value).lower() in {"false", "0", "unchecked", "off"}:
                return False
    return None


#: Shared by `read_optional_toggle_states` (read-only) and `disable_optional_toggles`
#: (read + click) so a reload read-back walks the same frames and applies the
#: same `_switch_label` / `OPTIONAL_CATEGORY` / `NECESSARY_CATEGORY` filtering as
#: the original scan. Identical heuristics on both sides of a reload is what
#: makes the read-back comparable to what was originally operated.
_TOGGLE_SELECTOR = "input[type='checkbox'], [role='switch'], button[aria-pressed], [aria-checked]"


def _iter_optional_toggles(page: Page):
    """Yield (frame, index, item, label, state) for every visible optional
    -category toggle across all frames, in a stable order."""
    for frame in page.frames:
        try:
            locator = frame.locator(_TOGGLE_SELECTOR)
            count = min(locator.count(), 250)
        except Exception:
            continue
        for index in range(count):
            item = locator.nth(index)
            try:
                if not item.is_visible(timeout=350):
                    continue
            except Exception:
                continue
            label = _switch_label(item)
            if not label or not OPTIONAL_CATEGORY.search(label) or NECESSARY_CATEGORY.search(label):
                continue
            state = _switch_state(item)
            yield frame, index, item, label, state


def read_optional_toggle_states(page: Page) -> list[dict[str, Any]]:
    """Read-only half of `disable_optional_toggles`: the same frame walk and
    label filtering, with nothing clicked.

    Used to re-observe the optional-category toggles after a reload, so the
    read-back can be compared against what was originally switched off.
    """
    return [
        {"frame_url": frame.url, "index": index, "label": label[:700], "state": state}
        for frame, index, item, label, state in _iter_optional_toggles(page)
    ]


def disable_optional_toggles(page: Page, action_log: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"examined": [], "disabled": [], "unknown": []}
    for frame, index, item, label, state in _iter_optional_toggles(page):
        public = {"frame_url": frame.url, "index": index, "label": label[:700], "state_before": state}
        result["examined"].append(public)
        if state is True:
            try:
                item.click(timeout=5000)
                _sleep_ms(250)
                after = _switch_state(item)
                public["state_after"] = after
                result["disabled"].append(public)
                action_log.append({"time": utc_now(), "action": "disable_optional_toggle", "control": public, "success": after is False or after is None})
            except Exception as error:
                public["error"] = str(error)[:800]
                result["unknown"].append(public)
        elif state is None:
            result["unknown"].append(public)
    return result


def inspect_banner(page: Page) -> dict[str, Any]:
    containers: list[dict[str, Any]] = []
    controls = collect_visible_controls(page)
    for frame in page.frames:
        try:
            candidates = frame.evaluate(
                r"""
                () => {
                  const output = [];
                  const seen = new Set();
                  const selectors = [
                    '[role="dialog"]', '[aria-modal="true"]',
                    '[id*="cookie" i]', '[class*="cookie" i]',
                    '[id*="consent" i]', '[class*="consent" i]',
                    '[id*="privacy" i]', '[class*="privacy" i]',
                    '[id*="cmp" i]', '[class*="cmp" i]'
                  ];
                  function visible(el) {
                    const cs = getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity || 1) > 0 && rect.width > 50 && rect.height > 20;
                  }
                  function add(el) {
                    if (!el || seen.has(el) || !visible(el)) return;
                    seen.add(el);
                    const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                    if (!text || text.length < 15) return;
                    const cs = getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    output.push({
                      text: text.slice(0, 7000),
                      html: el.outerHTML.slice(0, 5000),
                      id: el.id || '',
                      className: typeof el.className === 'string' ? el.className.slice(0, 500) : '',
                      role: el.getAttribute('role') || '',
                      rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                      style: {position: cs.position, zIndex: cs.zIndex, backgroundColor: cs.backgroundColor, color: cs.color}
                    });
                  }
                  function scan(root) {
                    for (const selector of selectors) {
                      for (const el of root.querySelectorAll(selector)) add(el);
                    }
                    for (const el of root.querySelectorAll('*')) {
                      if (el.shadowRoot) scan(el.shadowRoot);
                    }
                  }
                  scan(document);
                  return output.slice(0, 60);
                }
                """
            )
        except Exception:
            candidates = []
        for candidate in candidates or []:
            text = str(candidate.get("text", ""))
            keyword = bool(BANNER_KEYWORDS.search(text))
            position = str((candidate.get("style") or {}).get("position", ""))
            score = (80 if keyword else 0) + (25 if position in {"fixed", "sticky"} else 0)
            rect = candidate.get("rect") or {}
            score += min(int((rect.get("width", 0) * rect.get("height", 0)) / 100000), 20)
            containers.append({"frame_url": frame.url, "score": score, **candidate})
    containers.sort(key=lambda item: item.get("score", 0), reverse=True)
    public_controls = [_public_control(control) for control in controls]
    return {
        "time": utc_now(),
        "page_url": page.url,
        "page_title": _safe_title(page),
        "containers": containers[:20],
        "controls": public_controls[:300],
        "best_text": (containers[0].get("text") if containers else ""),
    }


def _capture_cmp_state(page: Page) -> dict[str, Any]:
    try:
        return page.evaluate(
            """
            async () => {
              const result = {
                gpc: navigator.globalPrivacyControl === true,
                dnt: navigator.doNotTrack || null,
                cookieNames: document.cookie.split(';').map(v => v.trim().split('=')[0]).filter(Boolean),
                localStorage: [], sessionStorage: [], indexedDB: [], caches: [], serviceWorkers: [],
                cmp: {
                  hasTCF: typeof window.__tcfapi === 'function',
                  hasUSP: typeof window.__uspapi === 'function',
                  hasGPP: typeof window.__gpp === 'function',
                  oneTrustActiveGroups: window.OneTrustActiveGroups || null
                }
              };
              async function digest(value) {
                try {
                  const data = new TextEncoder().encode(String(value));
                  const hash = await crypto.subtle.digest('SHA-256', data);
                  return Array.from(new Uint8Array(hash)).map(v => v.toString(16).padStart(2, '0')).join('').slice(0, 16);
                } catch { return null; }
              }
              for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i); const value = localStorage.getItem(key) || '';
                result.localStorage.push({key, length: value.length, sha256: await digest(value)});
              }
              for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i); const value = sessionStorage.getItem(key) || '';
                result.sessionStorage.push({key, length: value.length, sha256: await digest(value)});
              }
              try { result.indexedDB = await indexedDB.databases(); } catch {}
              try { result.caches = await caches.keys(); } catch {}
              try {
                const regs = await navigator.serviceWorker.getRegistrations();
                result.serviceWorkers = regs.map(r => ({scope: r.scope, active: r.active && r.active.scriptURL, waiting: r.waiting && r.waiting.scriptURL}));
              } catch {}
              function withTimeout(executor, ms = 1200) {
                return new Promise(resolve => {
                  let done = false;
                  const timer = setTimeout(() => { if (!done) { done = true; resolve(null); } }, ms);
                  try { executor(value => { if (!done) { done = true; clearTimeout(timer); resolve(value); } }); }
                  catch { if (!done) { done = true; clearTimeout(timer); resolve(null); } }
                });
              }
              if (result.cmp.hasTCF) {
                result.cmp.tcf = await withTimeout(done => window.__tcfapi('getTCData', 2, (data, ok) => {
                  done(ok && data ? {
                    gdprApplies: data.gdprApplies,
                    eventStatus: data.eventStatus,
                    cmpStatus: data.cmpStatus,
                    purposeConsents: data.purpose && data.purpose.consents,
                    purposeLegitimateInterests: data.purpose && data.purpose.legitimateInterests,
                    vendorConsentCount: data.vendor && data.vendor.consents ? Object.values(data.vendor.consents).filter(Boolean).length : null,
                    tcStringLength: data.tcString ? data.tcString.length : 0
                  } : null);
                }));
              }
              if (result.cmp.hasUSP) {
                result.cmp.usp = await withTimeout(done => window.__uspapi('getUSPData', 1, (data, ok) => done(ok ? data : null)));
              }
              if (result.cmp.hasGPP) {
                result.cmp.gpp = await withTimeout(done => window.__gpp('ping', data => done(data)));
              }
              return result;
            }
            """
        )
    except Exception as error:
        return {"error": str(error)[:1000]}


def capture_checkpoint(
    page: Page,
    context: BrowserContext,
    scenario: str,
    checkpoint: str,
    private_dir: Path,
    share_dir: Path,
) -> dict[str, Any]:
    private_scenario = ensure_dir(private_dir / scenario)
    share_scenario = ensure_dir(share_dir / scenario)
    banner = inspect_banner(page)
    metadata = {
        "scenario": scenario,
        "checkpoint": checkpoint,
        "time": utc_now(),
        "url": page.url,
        "title": _safe_title(page),
        "banner": banner,
        "browser_state": _capture_cmp_state(page),
    }
    try:
        cookies = context.cookies()
    except Exception as error:
        cookies = []
        metadata["cookies_error"] = str(error)[:1000]
    try:
        storage_state = context.storage_state(indexed_db=True)
    except Exception:
        try:
            storage_state = context.storage_state()
        except Exception as error:
            storage_state = {"cookies": cookies, "origins": [], "error": str(error)[:1000]}

    raw = {**metadata, "cookies": cookies, "storage_state": storage_state}
    redacted = {**metadata, "cookies": redact_storage_state({"cookies": cookies, "origins": []}).get("cookies", []), "storage_state": redact_storage_state(storage_state)}
    write_json(private_scenario / f"{checkpoint}-state.raw.json", raw)
    write_json(share_scenario / f"{checkpoint}-state.json", redacted)

    screenshot_paths: list[str] = []
    viewport_path = share_scenario / f"{checkpoint}-viewport.png"
    try:
        page.screenshot(path=str(viewport_path), full_page=False, animations="disabled")
        screenshot_paths.append(str(viewport_path))
    except Exception as error:
        metadata.setdefault("screenshot_errors", []).append(str(error)[:1000])
    full_path = share_scenario / f"{checkpoint}-full.png"
    try:
        page.screenshot(path=str(full_path), full_page=True, animations="disabled")
        screenshot_paths.append(str(full_path))
    except Exception as error:
        metadata.setdefault("screenshot_errors", []).append(str(error)[:1000])

    best = (banner.get("containers") or [None])[0]
    if best and best.get("frame_url") == page.main_frame.url:
        rect = best.get("rect") or {}
        try:
            x = max(float(rect.get("x", 0)), 0)
            y = max(float(rect.get("y", 0)), 0)
            width = min(float(rect.get("width", 0)), 1440)
            height = min(float(rect.get("height", 0)), 1200)
            if width > 20 and height > 20:
                crop_path = share_scenario / f"{checkpoint}-banner.png"
                page.screenshot(path=str(crop_path), clip={"x": x, "y": y, "width": width, "height": height}, animations="disabled")
                screenshot_paths.append(str(crop_path))
        except Exception as error:
            metadata.setdefault("screenshot_errors", []).append(str(error)[:1000])

    return {
        "scenario": scenario,
        "checkpoint": checkpoint,
        "time": metadata["time"],
        "url": page.url,
        "title": metadata["title"],
        "cookies": cookies,
        "storage_state": storage_state,
        "banner": banner,
        "browser_state": metadata["browser_state"],
        "screenshots": screenshot_paths,
    }


#: Statuses that represent a consent choice actually being made.
COMPLETED_DENIAL_STATUSES = {
    "direct_reject_clicked",
    "second_layer_reject_clicked",
    "preferences_disabled_and_saved",
    "manual_denial_completed",
    # #7: a settings-path denial with no save control, where a post-reload
    # probe (see `probe_autosave` / `checks.classify_autosave_denial`)
    # affirmatively confirmed the CMP kept the choice - either the toggles
    # read back off, or a namespaced consent-storage write was observed.
    # `toggles_disabled_no_save_control` (below) is the unverified sibling of
    # these two statuses and must never join this set: it is reached when the
    # probe could not confirm the choice persisted, which is exactly the case
    # that must stay an incomplete denial.
    checks.AUTOSAVE_VERIFIED_RELOAD,
    checks.AUTOSAVE_VERIFIED_STORAGE,
}

#: The settings path switched the optional-category toggles off, but no save
#: control could be resolved, and the post-reload probe (`probe_autosave`)
#: could not confirm the choice persisted - either a reload read a toggle
#: back on, or neither the reload nor a namespaced consent-storage write
#: verified it. See `checks.classify_autosave_denial` for the exact truth
#: table this status name and its two verified siblings above are drawn from.
#:
#: Deliberately absent from COMPLETED_DENIAL_STATUSES: an unsaved and
#: unverified preference panel is not a recorded choice, so this scenario
#: stays invalid and cannot support findings about post-denial behaviour. It
#: is nonetheless a distinct status rather than `manual_required`, because
#: page state *was* mutated - reporting it as "no denial control was
#: operated" would describe an interaction that did not happen as described,
#: which is the exact defect this scenario gating exists to prevent.
#:
#: Reachable whenever a CMP's `save` selector list is intentionally empty.
#: Two distinct reasons produce that:
#: - HubSpot, TrustArc, Quantcast Choice: the only candidate save selector
#:   was the *accept* control, which would have converted a denial into an
#:   acceptance - never add one back without confirming it isn't accept.
#: - Termly: live capture found no save control at all in its preference
#:   modal (only Decline All / Allow All) - do not "fix" this by mapping
#:   save to Allow All, which is the same hazard as the first case.
UNSAVED_PREFERENCE_STATUS = checks.AUTOSAVE_NO_SAVE_CONTROL

#: `find_control` decisions that mean "this control was not identified well
#: enough to operate", as distinct from "no such control is on the page".
AMBIGUOUS_DECISIONS = frozenset({"conflict", "vetoed"})

#: A denial control could not be operated because it could not be identified
#: with confidence - the CMP table and the text scorer disagreed, or the
#: table's candidate was disqualified by its own label or role.
#:
#: Deliberately a sibling of `manual_required` rather than a reuse of it.
#: `manual_required` means candidates were visible and none was confident
#: enough; `analysis.py` keys `denial-control-unresolved` off that status and
#: words it as "none reached the confidence threshold", which is simply untrue
#: of a conflict - there the scorer was confident, and so was the table, about
#: different elements. Reporting one as the other would describe the run
#: inaccurately in the very finding meant to explain why it stopped.
#:
#: Absent from COMPLETED_DENIAL_STATUSES, so the scenario is invalid and
#: withholds every finding that depends on it. That is the point: a run that
#: could not identify the denial control must not report a denial.
DENIAL_CONTROL_AMBIGUOUS = "denial_control_ambiguous"

#: The accept scenario's equivalent. Lower stakes - accept is a differential
#: control, not a compliance requirement - but the same rule applies: never
#: report an interaction that was not performed as described.
ACCEPT_CONTROL_AMBIGUOUS = "accept_control_ambiguous"

#: Statuses whose own verification note explains the invalidity better than
#: `_scenario_validity`'s generic "the required <x> did not complete" template.
_STATUSES_WITH_THEIR_OWN_REASON = frozenset({
    checks.AUTOSAVE_NO_SAVE_CONTROL,
    DENIAL_CONTROL_AMBIGUOUS,
    ACCEPT_CONTROL_AMBIGUOUS,
})


def ambiguous_resolution_labels(resolution_map: dict[str, Any] | None) -> list[str]:
    """Call-site labels whose control could not be identified with confidence.

    Reads `decision`, not `clickable`: an unresolved control (nothing on the
    page reads as one) is a fact about the *site* and keeps its existing
    status, while a conflicted or vetoed one is a fact about the *scanner's
    confidence* and needs saying differently.
    """
    return sorted(
        label
        for label, resolution in (resolution_map or {}).items()
        if (resolution or {}).get("decision") in AMBIGUOUS_DECISIONS
    )


def probe_autosave(
    page: Page,
    context: BrowserContext,
    cmp_entry: dict[str, Any] | None,
    wait_ms: int,
    action_log: list[dict[str, Any]],
    share_scenario_dir: Path,
    phase_ref: dict[str, str] | None = None,
    control_verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reload and re-observe optional toggles to check whether an unsaved
    settings-panel denial was actually kept.

    The exact step order here is the correctness, not a detail (issue #7):

    1. Screenshot the page as it stood right after the toggles were switched
       off, before anything else can change it.
    2. Record `probe_started`.
    3. Point `phase_ref` at `denial_verification_reload` *before* reloading.
       `_attach_event_listeners` stamps every request with `phase_ref["name"]`,
       and `analysis.py` only treats a request as post-denial when its phase is
       in `POST_DENIAL_PHASES` or carries an `internal_navigation_`/`exercise_`
       prefix - `denial_verification_reload` matches none of those, so this
       probe's own traffic is excluded automatically, but only if this step
       runs before the reload. Skipping it would manufacture the exact false
       "tracking continued after denial" finding this tool exists to prevent.
    4. Reload and let the page settle.
    5. Re-read banner visibility (observational only - see below).
    6. Only now try to reopen the settings layer, and if it opens, re-read the
       optional toggles with `read_optional_toggle_states` - the same label
       heuristics `disable_optional_toggles` used, so the read-back is
       comparable to what was actually switched off.
    7. Record `probe_finished` and restore whatever phase the caller was in.

    Reopening the settings panel can itself write a cookie on some CMPs, which
    is why the caller must compute its own narrow consent-storage diff from
    snapshots taken *before* this function ever runs - never from a snapshot
    taken after step 6.

    `banner_visible` is recorded here for evidence only. It is deliberately
    never consulted by `checks.classify_autosave_denial`: most CMPs leave a
    settings-path denial's banner closed regardless of whether the choice was
    kept, so banner absence alone can never verify anything.
    """
    probe: dict[str, Any] = {
        "probe_started": None,
        "probe_finished": None,
        "screenshot": None,
        "banner_visible_after_reload": None,
        "settings_reopened": False,
        "settings_resolution": None,
        "toggle_states": [],
    }

    try:
        screenshot_path = share_scenario_dir / "preferences-after-toggles.png"
        page.screenshot(path=str(screenshot_path), full_page=False, animations="disabled")
        probe["screenshot"] = str(screenshot_path)
    except Exception:
        pass

    probe["probe_started"] = utc_now()
    previous_phase = phase_ref["name"] if phase_ref is not None else None
    if phase_ref is not None:
        phase_ref["name"] = "denial_verification_reload"

    try:
        page.reload(wait_until="domcontentloaded")
    except Exception as error:
        probe["reload_error"] = str(error)[:800]
    _sleep_ms(min(wait_ms, 4000))

    probe["banner_visible_after_reload"] = banner_visible(page, cmp_entry)

    settings_control, _settings_candidates, settings_resolution = find_control(page, "settings", cmp_entry, label="settings_reopen_probe",
                                                                     control_verdicts=control_verdicts)
    probe["settings_resolution"] = settings_resolution
    if settings_control and click_control(settings_control, action_log, "settings_reopen_probe"):
        probe["settings_reopened"] = True
        _sleep_ms(min(wait_ms, 1500))
        probe["toggle_states"] = read_optional_toggle_states(page)

    probe["probe_finished"] = utc_now()
    if phase_ref is not None:
        phase_ref["name"] = previous_phase

    return probe


def execute_denial(
    page: Page,
    context: BrowserContext,
    wait_ms: int,
    manual: bool,
    share_scenario_dir: Path,
    cmp_entry: dict[str, Any] | None = None,
    phase_ref: dict[str, str] | None = None,
    control_verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    action_log: list[dict[str, Any]] = []
    before = consent_snapshot(page, context, cmp_entry)
    accept_control, accept_candidates, accept_resolution = find_control(
        page, "accept", cmp_entry, label="accept", control_verdicts=control_verdicts)
    reject_control, reject_candidates, reject_resolution = find_control(
        page, "reject", cmp_entry, label="reject", control_verdicts=control_verdicts)

    # E3 - measure real tab order and focus visibility while both controls are
    # still resolved and before either is clicked (a click may dismiss the
    # banner entirely). Only meaningful when both resolved to an actual
    # element; accept_candidates[0]/reject_candidates[0] are the exact public
    # form of accept_control/reject_control (see find_control), so mutating
    # them in place is what carries these fields through to measure_symmetry.
    # Only the raw traversal facts (position reached, whether the budget/cap
    # was hit) are recorded here; turning those into a reachable/unknown/
    # unreachable verdict is interpretation, which belongs in checks.py
    # (checks.measure_symmetry) alongside the rest of the pure, Playwright-free
    # logic - not here in the browser-driving half of the split.
    if accept_control and reject_control:
        tab_order = measure_tab_order(
            page, {"accept": accept_control["locator"], "reject": reject_control["locator"]}
        )
        accept_focus = measure_focus_visibility(accept_control["locator"])
        reject_focus = measure_focus_visibility(reject_control["locator"])
        accept_position = tab_order["positions"].get("accept")
        reject_position = tab_order["positions"].get("reject")

        accept_candidates[0].update(
            tab_position=accept_position,
            tab_order_cap_hit=tab_order["cap_hit"],
            focus_visible=accept_focus.get("visible"),
            focus_visibility=accept_focus,
        )
        reject_candidates[0].update(
            tab_position=reject_position,
            tab_order_cap_hit=tab_order["cap_hit"],
            focus_visible=reject_focus.get("visible"),
            focus_visibility=reject_focus,
        )

    result: dict[str, Any] = {
        "status": "not_started",
        "click_count": 0,
        "direct_accept_available": bool(accept_control),
        "accept_candidates": accept_candidates,
        "reject_candidates": reject_candidates,
        "resolution": {"accept": accept_resolution, "reject": reject_resolution},
        "action_log": action_log,
        "toggle_result": None,
        "manual_used": False,
        "consent_snapshot_before": before,
    }

    def finish(status: str, clicks: int) -> dict[str, Any]:
        result["status"] = status
        result["click_count"] = clicks
        _sleep_ms(wait_ms)
        after = consent_snapshot(page, context, cmp_entry)
        result["consent_snapshot_after"] = after
        result["verification"] = verify_choice_registered(before, after)
        return result

    if reject_control and click_control(reject_control, action_log, "reject"):
        return finish("direct_reject_clicked", 1)

    settings_control, settings_candidates, settings_resolution = find_control(
        page, "settings", cmp_entry, label="settings", control_verdicts=control_verdicts)
    result["settings_candidates"] = settings_candidates
    result["resolution"]["settings"] = settings_resolution
    toggle_result: dict[str, Any] | None = None
    disabled: list[Any] = []

    if settings_control and click_control(settings_control, action_log, "settings"):
        result["click_count"] = 1
        _sleep_ms(min(wait_ms, 2000))
        try:
            page.screenshot(path=str(share_scenario_dir / "preferences-open.png"), full_page=False, animations="disabled")
        except Exception:
            pass
        second_reject, second_reject_candidates, second_resolution = find_control(
            page, "reject", cmp_entry, label="second_layer_reject", control_verdicts=control_verdicts)
        result["second_layer_reject_candidates"] = second_reject_candidates
        result["resolution"]["second_layer_reject"] = second_resolution
        if second_reject and click_control(second_reject, action_log, "reject"):
            return finish("second_layer_reject_clicked", result["click_count"] + 1)
        toggle_result = disable_optional_toggles(page, action_log)
        result["toggle_result"] = toggle_result
        save_control, save_candidates, save_resolution = find_control(
            page, "save", cmp_entry, label="save", control_verdicts=control_verdicts)
        result["save_candidates"] = save_candidates
        result["resolution"]["save"] = save_resolution
        if save_control and click_control(save_control, action_log, "save"):
            return finish("preferences_disabled_and_saved", result["click_count"] + 1 + len(toggle_result.get("disabled", [])))

        disabled = toggle_result.get("disabled") or []

    def classify_toggle_denial() -> dict[str, Any]:
        # Toggles were switched off but no save control resolved. Falling
        # through to `manual_required` here would attach the note "No denial
        # control was operated, so there is nothing to verify" - false, since
        # the toggles above mutated page state. Record what actually
        # happened, then probe (#7) whether the CMP actually kept the
        # choice: take the narrow, CMP-scoped diff and reload for a
        # read-back *before* anything else can happen, so neither
        # measurement is influenced by the reload it verifies against.
        # `finish` takes both consent snapshots here, ahead of the reload
        # inside `probe_autosave` below - that ordering is what the
        # evidence-ordering acceptance check in #7 asserts on directly.
        unsaved = finish(UNSAVED_PREFERENCE_STATUS, result["click_count"] + len(disabled))
        broad_diff = dict(unsaved.get("verification") or {})

        namespace = checks.consent_namespace(cmp_entry)
        narrow_diff = checks.narrow_consent_diff(before, unsaved["consent_snapshot_after"], namespace)
        autosave_probe = probe_autosave(
            page, context, cmp_entry, wait_ms, action_log, share_scenario_dir, phase_ref,
            control_verdicts,
        )
        classification = checks.classify_autosave_denial(toggle_result, narrow_diff, autosave_probe)

        unsaved["status"] = classification["status"]
        unsaved["narrow_diff"] = narrow_diff
        unsaved["autosave_probe"] = autosave_probe
        # `broad_diff` is `verify_choice_registered`'s any-cookie-or-storage
        # comparison, kept for evidence only - some CMPs write provisional
        # state on toggle, which is not by itself proof the CMP kept the
        # choice. `verification["verified"]`/`["note"]` now come from the
        # probe-backed classification instead: whether the CMP actually
        # kept the choice, not merely whether *something* changed.
        unsaved["verification"] = {**classification, "broad_diff": broad_diff}
        return unsaved

    if disabled and not manual:
        return classify_toggle_denial()

    if manual:
        result["manual_used"] = True
        result["status"] = "manual_wait"
        print(
            "\nAutomatic denial was not reliable. In the opened browser, choose the most "
            "privacy-protective option, then return here and press Enter.",
            flush=True,
        )
        try:
            input()
            return finish("manual_denial_completed", result["click_count"])
        except EOFError:
            # Non-interactive stdin. audit_site.py refuses --manual without a
            # terminal, so reaching this branch means the environment changed
            # mid-run; record it rather than silently continuing. If optional
            # toggles were already switched off before the prompt failed, that
            # is an operated denial control - manual_required's "nothing was
            # operated" meaning must stay exact (analysis.py keys
            # denial-control-unresolved off it), so fall back to the same
            # probe-backed classification used when --manual was not
            # requested instead of misreporting manual_required here.
            result["manual_stdin_unavailable"] = True
            if disabled:
                return classify_toggle_denial()

    # Nothing was operated. *Why* not decides which status this is: a control
    # nobody could identify with confidence is a different fact from a page
    # where no denial control was found, and the two produce different
    # findings and different advice.
    ambiguous = ambiguous_resolution_labels(result["resolution"])
    if ambiguous:
        result["status"] = DENIAL_CONTROL_AMBIGUOUS
        result["ambiguous_controls"] = ambiguous
        note = (
            "No denial control was operated: "
            + ", ".join(ambiguous)
            + " could not be identified with confidence, so nothing was clicked."
        )
    else:
        result["status"] = "manual_required"
        note = "No denial control was operated, so there is nothing to verify."
    result["consent_snapshot_after"] = consent_snapshot(page, context, cmp_entry)
    result["verification"] = {"verified": False, "note": note}
    return result


def execute_accept(
    page: Page,
    context: BrowserContext,
    wait_ms: int,
    cmp_entry: dict[str, Any] | None = None,
    control_verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    action_log: list[dict[str, Any]] = []
    before = consent_snapshot(page, context, cmp_entry)
    control, candidates, resolution = find_control(
        page, "accept", cmp_entry, label="accept", control_verdicts=control_verdicts)
    result: dict[str, Any] = {
        "status": "accept_not_found",
        "click_count": 0,
        "candidates": candidates,
        "resolution": {"accept": resolution},
        "action_log": action_log,
        "consent_snapshot_before": before,
    }
    if control and click_control(control, action_log, "accept"):
        result["status"] = "accept_clicked"
        result["click_count"] = 1
        _sleep_ms(wait_ms)
        after = consent_snapshot(page, context, cmp_entry)
        result["consent_snapshot_after"] = after
        result["verification"] = verify_choice_registered(before, after)
    else:
        ambiguous = ambiguous_resolution_labels(result["resolution"])
        if ambiguous:
            # Not "not found" - found twice, or found and disqualified.
            result["status"] = ACCEPT_CONTROL_AMBIGUOUS
            result["ambiguous_controls"] = ambiguous
            note = "The accept control could not be identified with confidence, so nothing was clicked."
        else:
            note = "No accept control was operated, so there is nothing to verify."
        result["verification"] = {"verified": False, "note": note}
    return result


def safe_internal_links(page: Page, start_url: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    origin = origin_from_url(start_url)
    try:
        links = page.evaluate(
            r"""
            () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
              href: a.href,
              text: (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 300),
              visible: !!(a.offsetWidth || a.offsetHeight || a.getClientRects().length)
            })).filter(x => x.visible)
            """
        )
    except Exception:
        links = []
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    preferred = re.compile(r"(?:about|services|products|resources|news|blog|privacy|contact|locations|careers)", re.I)
    for item in links or []:
        href = str(item.get("href", ""))
        if not href or href in seen:
            continue
        try:
            parts = urlsplit(href)
        except Exception:
            continue
        if parts.scheme not in {"http", "https"}:
            continue
        href_origin = f"{parts.scheme}://{parts.hostname}{':' + str(parts.port) if parts.port else ''}"
        if href_origin != origin:
            continue
        if DANGEROUS_LINK.search(parts.path + " " + str(item.get("text", ""))) or DOWNLOAD_EXTENSION.search(href):
            continue
        normalized = f"{href_origin}{parts.path or '/'}"
        if normalized.rstrip("/") == start_url.split("?", 1)[0].rstrip("/"):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        score = 20 if preferred.search(parts.path + " " + str(item.get("text", ""))) else 0
        score -= parts.path.count("/")
        ranked.append((score, normalized))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in ranked[:limit]]


# --------------------------------------------------------------------------
# D1-D3 - exercising the page so deferred tags actually fire
# --------------------------------------------------------------------------

#: Obviously synthetic values. example.com is IANA-reserved and undeliverable;
#: 555-0100 is the reserved fictional US telephone range. Anything that reaches
#: a CRM from this tool should be immediately recognisable as an audit artefact.
SYNTHETIC_VALUES = {
    "email": "privacy-audit-test@example.com",
    "tel": "+1-555-0100",
    "name": "Privacy Audit Test",
    "company": "Privacy Audit Test",
    "text": "AUTOMATED PRIVACY AUDIT - DISREGARD",
    "number": "1",
    "url": "https://example.com",
}

SEARCH_INPUT_SELECTORS = [
    "input[type='search']",
    "[role='searchbox']",
    "input[name*='search' i]",
    "input[id*='search' i]",
    "input[placeholder*='search' i]",
    "input[aria-label*='search' i]",
]

#: Forms we must never touch, even to fill without submitting.
UNSAFE_FORM = re.compile(
    r"(?:login|log-in|signin|sign-in|signup|sign-up|register|password|payment|billing|card|"
    r"checkout|donate|unsubscribe|delete|cancel|account|profile|address)",
    re.I,
)


def dwell_and_nudge(page: Page, config: ScenarioConfig) -> dict[str, Any]:
    """Scroll in stages, move the mouse, and idle.

    Many advertising and analytics tags fire on scroll depth, a visibility
    threshold, or a timer rather than on load. A capture that only waits a few
    seconds after `load` systematically under-observes those transmissions.
    """
    record: dict[str, Any] = {"scrolled_to": [], "dwell_ms": config.settle_ms()}
    if not config.thorough:
        _sleep_ms(config.wait_ms)
        return record

    stages = max(1, config.scroll_stages)
    per_stage_ms = max(int(config.settle_ms() / (stages + 1)), 500)
    for stage in range(1, stages + 1):
        fraction = stage / stages
        try:
            page.evaluate(
                "f => window.scrollTo({top: document.body.scrollHeight * f, behavior: 'instant'})",
                fraction,
            )
            record["scrolled_to"].append(round(fraction, 2))
        except Exception:
            pass
        try:
            page.mouse.move(200 + stage * 90, 200 + stage * 45)
        except Exception:
            pass
        _sleep_ms(per_stage_ms)

    try:
        page.evaluate("() => window.scrollTo({top: 0, behavior: 'instant'})")
    except Exception:
        pass
    _sleep_ms(per_stage_ms)
    return record


def exercise_forms(page: Page, config: ScenarioConfig) -> dict[str, Any]:
    """Fill visible form fields with synthetic data, then blur each one.

    Filling and blurring is what fires form-capture and engagement tags such as
    HubSpot's collectedforms.js; submission is a separate, side-effecting act
    that creates real CRM records and can trigger notification workflows, so it
    stays behind an explicit opt-in.
    """
    record: dict[str, Any] = {
        "forms_examined": 0,
        "fields_filled": [],
        "submitted": False,
        "submit_enabled": config.submit_forms,
        "skipped_forms": [],
    }
    try:
        form_count = min(page.locator("form").count(), 10)
    except Exception:
        return record

    for index in range(form_count):
        form = page.locator("form").nth(index)
        try:
            if not form.is_visible(timeout=500):
                continue
            signature = " ".join(filter(None, [
                form.get_attribute("id") or "",
                form.get_attribute("name") or "",
                form.get_attribute("class") or "",
                form.get_attribute("action") or "",
            ]))
        except Exception:
            continue
        record["forms_examined"] += 1
        if UNSAFE_FORM.search(signature):
            record["skipped_forms"].append({"index": index, "reason": "matched unsafe-form pattern", "signature": signature[:200]})
            continue

        try:
            fields = form.locator("input, textarea")
            field_count = min(fields.count(), 15)
        except Exception:
            continue

        for field_index in range(field_count):
            field = fields.nth(field_index)
            try:
                if not field.is_visible(timeout=300) or not field.is_enabled(timeout=300):
                    continue
                field_type = (field.get_attribute("type") or "text").lower()
                name = " ".join(filter(None, [
                    field.get_attribute("name") or "",
                    field.get_attribute("id") or "",
                    field.get_attribute("placeholder") or "",
                ]))
            except Exception:
                continue
            if field_type in {"hidden", "submit", "button", "password", "file", "checkbox", "radio", "image", "reset"}:
                continue
            if field_type == "search" or re.search(r"search", name, re.I):
                continue  # handled separately by exercise_search

            if field_type in SYNTHETIC_VALUES:
                value = SYNTHETIC_VALUES[field_type]
            elif re.search(r"e-?mail", name, re.I):
                value = SYNTHETIC_VALUES["email"]
            elif re.search(r"phone|tel|mobile", name, re.I):
                value = SYNTHETIC_VALUES["tel"]
            elif re.search(r"company|organi[sz]ation|employer", name, re.I):
                value = SYNTHETIC_VALUES["company"]
            elif re.search(r"name", name, re.I):
                value = SYNTHETIC_VALUES["name"]
            else:
                value = SYNTHETIC_VALUES["text"]

            try:
                field.fill(value, timeout=2500)
                field.blur(timeout=1000)
                record["fields_filled"].append({"form_index": index, "field": name[:120] or field_type, "type": field_type})
                _sleep_ms(300)
            except Exception:
                continue

        if config.submit_forms and record["fields_filled"]:
            try:
                form.locator("button[type='submit'], input[type='submit']").first.click(timeout=5000)
                record["submitted"] = True
                _sleep_ms(config.wait_ms)
            except Exception as error:
                record["submit_error"] = str(error)[:300]
        break  # one form is enough to exercise the form-capture tags

    return record


def exercise_search(page: Page, config: ScenarioConfig, query: str = "performance") -> dict[str, Any]:
    """Run an on-site search.

    Site-search terms are routinely forwarded to analytics and advertising
    platforms, so this is a high-yield path for observing transmission that a
    plain page view never triggers. A search is a read-only GET and does not
    create records.
    """
    record: dict[str, Any] = {"attempted": False, "submitted": False, "query": query}
    for selector in SEARCH_INPUT_SELECTORS:
        try:
            field = page.locator(selector).first
            if field.count() == 0 or not field.is_visible(timeout=500):
                continue
        except Exception:
            continue
        record["attempted"] = True
        record["selector"] = selector
        try:
            field.fill(query, timeout=2500)
            _sleep_ms(400)
            field.press("Enter", timeout=2500)
            record["submitted"] = True
            try:
                page.wait_for_load_state("domcontentloaded", timeout=min(config.timeout_ms, 15000))
            except Exception:
                pass
            _sleep_ms(config.wait_ms)
            record["result_url"] = page.url
        except Exception as error:
            record["error"] = str(error)[:300]
        return record
    return record


def collect_page_links(page: Page) -> list[dict[str, Any]]:
    """Every visible link with its label, for the statutory-rights scan (E1)."""
    try:
        return page.eval_on_selector_all(
            "a[href]",
            r"""els => els.map(e => ({
              text: (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200),
              href: e.href
            }))""",
        ) or []
    except Exception:
        return []


#: Signals that a fetched page is a login wall rather than a public document.
_AUTH_WALL = re.compile(r"\b(sign in|log in|login|create an account|password)\b", re.I)


def _robots_allows(url: str, cache: dict[str, Any], timeout_s: float = 8.0) -> tuple[bool, str]:
    """May an automated fetcher retrieve `url`?

    Checked per origin and cached. A robots.txt that cannot be fetched is
    treated as permissive, which is the convention: an origin with no robots
    policy has not asked anyone to stay out. A robots.txt that *is* served and
    disallows the path is honoured, even though the same document was already
    linked from a page the audit loaded in a browser - fetching a document is a
    different act from following a link a user clicked.
    """
    try:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
    except Exception:
        return True, "url could not be parsed for a robots check"
    if origin not in cache:
        parser = RobotFileParser()
        try:
            with urlopen(f"{origin}/robots.txt", timeout=timeout_s) as response:  # noqa: S310
                body = response.read().decode("utf-8", "replace")
            parser.parse(body.splitlines())
            cache[origin] = parser
        except Exception:
            cache[origin] = None
    parser = cache[origin]
    if parser is None:
        return True, "no robots.txt served or it could not be read"
    try:
        return bool(parser.can_fetch("*", url)), "robots.txt consulted"
    except Exception:
        return True, "robots.txt could not be evaluated"


def _browser_policy_fetcher(browser: Browser, timeout_ms: int) -> tuple[Callable[[str], dict[str, Any]], BrowserContext]:
    """The real fetcher: one browser context/page, reused across every policy
    URL in a run and never the browser context of any scenario, so nothing
    here can touch a scenario's consent state.

    Returns the fetcher and the context that owns it, so the caller can close
    the context once every URL has been tried.
    """
    context = browser.new_context(accept_downloads=False)
    page = context.new_page()
    page.set_default_timeout(timeout_ms)

    def fetch(url: str) -> dict[str, Any]:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        status = response.status if response else None
        ok = bool(response is not None and response.ok)
        content_type = ((response.header_value("content-type") or "") if response else "").lower()
        text = ""
        if ok and (not content_type or "html" in content_type or "text/plain" in content_type):
            text = (page.inner_text("body") or "").strip()
        return {
            "status": status,
            "ok": ok,
            "content_type": content_type or None,
            "text": text,
            "final_url": page.url,
        }

    return fetch, context


def capture_policy_texts(
    browser: Browser | None,
    links: list[dict[str, Any]],
    share_dir: Path,
    timeout_ms: int = 30000,
    limit: int = 6,
    fetch_url: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Archive the text of the site's linked policies (E6).

    Counsel's first question about any observed behaviour is what the site said
    it would do. Without this, answering that means finding the policy by hand
    and hoping it has not changed since the capture - so the text is stored
    beside the behaviour with a retrieval timestamp and a content hash.

    **Capture and store only.** Nothing here compares the text to what was
    observed or draws any conclusion from it. A policy saying one thing and the
    network log showing another is a question for a reader, not a finding this
    tool is entitled to assert.

    Fetching goes through the `fetch_url` seam: a callable taking a URL and
    returning `{"status", "ok", "content_type", "text", "final_url"}`, or
    raising to signal a fetch failure. Leave it unset in production - a real
    fetcher is then built from `browser`, in a context of its own so nothing
    here touches the consent state of any scenario. Tests supply a fake
    fetcher instead, so the real fetcher (and the network) is never exercised
    by the suite. Anything behind a login is recorded as skipped rather than
    archived: a login page saved under the name of a privacy policy is worse
    than no file at all.
    """
    selections = checks.select_policy_links(links, limit=limit)
    output_dir = ensure_dir(share_dir / "policies")
    records: list[dict[str, Any]] = []
    robots_cache: dict[str, Any] = {}

    context = None
    try:
        if fetch_url is None:
            fetch_url, context = _browser_policy_fetcher(browser, timeout_ms)
        for index, selection in enumerate(selections, start=1):
            record = {
                "kind": selection["kind"],
                "url": selection["url"],
                "link_label": selection["label"],
                "host": selection["host"],
                "retrieved_at": utc_now(),
                "archived": False,
                "skipped_reason": None,
            }
            allowed, robots_note = _robots_allows(selection["url"], robots_cache)
            record["robots_note"] = robots_note
            if not allowed:
                record["skipped_reason"] = "robots.txt disallows automated retrieval of this path"
                records.append(record)
                continue
            try:
                fetched = fetch_url(selection["url"])
                record["http_status"] = fetched.get("status")
                content_type = (fetched.get("content_type") or "").lower()
                record["content_type"] = content_type or None
                if not fetched.get("ok"):
                    record["skipped_reason"] = f"fetch returned HTTP {fetched.get('status')}"
                    records.append(record)
                    continue
                if content_type and "html" not in content_type and "text/plain" not in content_type:
                    # A PDF policy is common and is genuinely the document, but
                    # extracting its text is a different job. Record that it
                    # exists rather than archiving an empty file for it.
                    record["skipped_reason"] = f"not extractable as text ({content_type})"
                    records.append(record)
                    continue
                text = (fetched.get("text") or "").strip()
                record["chars"] = len(text)
                if _AUTH_WALL.search(text[:2000]) and len(text) < 2500:
                    record["skipped_reason"] = "the fetched page looks like a login wall, not a public policy"
                    records.append(record)
                    continue
                if len(text) < 200:
                    record["skipped_reason"] = f"fetched page held too little text to be a policy ({len(text)} chars)"
                    records.append(record)
                    continue
                record["final_url"] = fetched.get("final_url") or selection["url"]
                record["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
                filename = f"{index:02d}-{selection['kind']}-{slugify(selection['host'])}.txt"
                header = (
                    f"Source URL: {selection['url']}\n"
                    f"Final URL after redirects: {record['final_url']}\n"
                    f"Retrieved at: {record['retrieved_at']}\n"
                    f"Link label on the audited page: {selection['label']}\n"
                    f"SHA-256 of the text below: {record['sha256']}\n"
                    f"{'-' * 72}\n"
                    "Archived verbatim for reference. This tool draws no conclusion from this text\n"
                    "and has not compared it to the observed behaviour.\n"
                    f"{'-' * 72}\n\n"
                )
                write_text(output_dir / filename, header + text)
                record["path"] = str(output_dir / filename)
                record["archived"] = True
            except Exception as error:
                record["skipped_reason"] = f"fetch failed: {str(error)[:200]}"
            records.append(record)
    except Exception as error:
        return {
            "attempted": len(selections),
            "archived": 0,
            "records": records,
            "error": str(error)[:300],
        }
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass

    return {
        "attempted": len(selections),
        "archived": sum(1 for r in records if r.get("archived")),
        "records": records,
        "note": (
            "Policy text is archived as reference material only. No comparison to observed "
            "behaviour has been performed and no finding is derived from it."
        ),
    }


def capture_served_html(page: Page) -> str:
    """Rendered HTML, used by the embedded-identifier scan (E2)."""
    try:
        return page.content()
    except Exception:
        return ""


def _attach_event_listeners(page: Page, phase_ref: dict[str, str], events: dict[str, list[dict[str, Any]]]) -> None:
    def on_request(request: Any) -> None:
        try:
            events["requests"].append({
                "time": utc_now(),
                "phase": phase_ref["name"],
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "is_navigation_request": request.is_navigation_request(),
                "redirected_from": request.redirected_from.url if request.redirected_from else None,
                "header_names": sorted(request.headers.keys()),
            })
        except Exception:
            pass

    def on_response(response: Any) -> None:
        try:
            events["responses"].append({
                "time": utc_now(),
                "phase": phase_ref["name"],
                "url": response.url,
                "status": response.status,
                "status_text": response.status_text,
                "from_service_worker": response.from_service_worker,
                "header_names": sorted(response.headers.keys()),
            })
        except Exception:
            pass

    def on_failed(request: Any) -> None:
        try:
            events["request_failures"].append({
                "time": utc_now(),
                "phase": phase_ref["name"],
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "failure": request.failure,
            })
        except Exception:
            pass

    def on_console(message: Any) -> None:
        try:
            events["console"].append({"time": utc_now(), "phase": phase_ref["name"], "type": message.type, "text": message.text[:3000]})
        except Exception:
            pass

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("requestfailed", on_failed)
    page.on("console", on_console)


# --------------------------------------------------------------------------
# B5 - prove the context started clean rather than assuming it
# --------------------------------------------------------------------------

def assert_clean_context(context: BrowserContext, page: Page) -> dict[str, Any]:
    """Record that a freshly created context carried no prior state.

    Playwright launches a throwaway browser profile and `new_context()` starts
    with no cookies or storage, so this always passes in practice. Recording it
    turns "the contexts were clean" from an assumption a reader has to take on
    trust into a line of evidence in the bundle.
    """
    assertion: dict[str, Any] = {"time": utc_now(), "checked": True}
    try:
        cookies = context.cookies()
        assertion["cookie_count"] = len(cookies)
        assertion["cookie_names"] = sorted({c.get("name", "") for c in cookies})
    except Exception as error:
        assertion["cookie_error"] = str(error)[:300]
    try:
        storage = page.evaluate(
            """() => {
              let local = -1, session = -1;
              try { local = localStorage.length; } catch {}
              try { session = sessionStorage.length; } catch {}
              return {local, session};
            }"""
        )
        assertion["local_storage_keys"] = storage.get("local")
        assertion["session_storage_keys"] = storage.get("session")
    except Exception as error:
        assertion["storage_error"] = str(error)[:300]

    assertion["clean"] = (
        assertion.get("cookie_count", 0) == 0
        and assertion.get("local_storage_keys", 0) in (0, -1)
        and assertion.get("session_storage_keys", 0) in (0, -1)
    )
    return assertion


def _collect_consent_mode(events: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Pull transmission-layer consent signals out of the request log (C3).

    Google Consent Mode and Meta Limited Data Use; see checks.parse_consent_signal
    for why other vendors are absent.
    """
    signals: list[dict[str, Any]] = []
    for request in events.get("requests", []) or []:
        parsed = checks.parse_consent_signal(str(request.get("url", "")))
        if parsed:
            parsed["phase"] = request.get("phase")
            parsed["time"] = request.get("time")
            signals.append(parsed)
    return {"signals": signals, "summary": checks.summarize_consent_mode(signals)}


def build_context_options(
    config: ScenarioConfig,
    gpc: bool = False,
    storage_state: Any = None,
    raw_har: Path | None = None,
) -> dict[str, Any]:
    """Build the Playwright context options for one scenario run.

    Extracted from `run_scenario` so device emulation is assertable without
    driving a full capture. The mobile branch is the reason this matters: if
    those options silently stopped being applied, every run would still
    succeed and would still be *labelled* mobile while actually being served
    the desktop banner.
    """
    options: dict[str, Any] = {
        "viewport": dict(config.viewport),
        "locale": config.locale,
        "ignore_https_errors": config.ignore_https_errors,
        "service_workers": "allow",
        "accept_downloads": False,
    }
    if raw_har is not None:
        options["record_har_path"] = str(raw_har)
        options["record_har_mode"] = "full"
        options["record_har_content"] = "omit"
    if config.is_mobile:
        # Chromium-only options; this runner always launches chromium. Touch
        # and the mobile UA travel with the narrow viewport because CMPs and
        # tag managers branch on all three.
        options["is_mobile"] = True
        options["has_touch"] = True
        options["device_scale_factor"] = config.device_scale_factor
    if config.timezone_id:
        options["timezone_id"] = config.timezone_id
    # The device profile supplies a user agent; an explicit --user-agent is a
    # deliberate override and wins, so applying it second is load-bearing.
    if config.device_user_agent:
        options["user_agent"] = config.device_user_agent
    if config.user_agent:
        options["user_agent"] = config.user_agent
    if config.proxy:
        options["proxy"] = {"server": config.proxy}
    if gpc:
        options["extra_http_headers"] = {"Sec-GPC": "1"}
    if storage_state is not None:
        options["storage_state"] = storage_state
    return options


def _scenario_validity(action: str, action_result: dict[str, Any], errors: list[dict[str, Any]]) -> dict[str, Any]:
    """Decide whether this scenario may support findings.

    A scenario whose required interaction never happened cannot evidence what
    happens after that interaction. Emitting findings from it anyway is the
    defect this gating exists to prevent.
    """
    required = {"deny": "denial click", "accept": "accept click"}.get(action)
    fatal = [e for e in errors if e.get("stage") == "scenario"]

    if required is None:
        completed = True
        verified = True
        reason = None
    else:
        status = action_result.get("status", "")
        completed = status in COMPLETED_DENIAL_STATUSES or status == "accept_clicked"
        verification = action_result.get("verification") or {}
        verified = bool(verification.get("verified"))
        if not completed:
            # These statuses carry a note that says something the generic
            # template cannot: which controls were ambiguous, or that page
            # state was mutated even though nothing was saved. The template's
            # "did not complete" is true but uninformative next to that.
            note = verification.get("note") if status in _STATUSES_WITH_THEIR_OWN_REASON else None
            reason = note or f"The required {required} did not complete (status: {status or 'unknown'})."
        elif not verified:
            reason = (
                f"The {required} was performed but no cookie, storage, CMP, or banner change "
                "followed, so the choice cannot be shown to have registered."
            )
        else:
            reason = None

    if fatal:
        completed = False
        reason = f"The scenario aborted: {fatal[0].get('error', '')[:200]}"

    return {
        "required_interaction": required,
        "interaction_completed": completed,
        "verification_passed": verified,
        "valid": bool(completed and verified),
        "invalid_reason": reason,
    }


def run_scenario(
    browser: Browser,
    scenario: str,
    config: ScenarioConfig,
    private_dir: Path,
    share_dir: Path,
    action: str,
    gpc: bool = False,
    cmp_table: list[dict[str, Any]] | None = None,
    pages: int | None = None,
    run_exercises: bool = True,
    storage_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    private_scenario = ensure_dir(private_dir / scenario)
    share_scenario = ensure_dir(share_dir / scenario)
    raw_har = private_scenario / f"{scenario}.raw.har"
    sanitized_har = share_scenario / f"{scenario}.sanitized.har"
    events: dict[str, list[dict[str, Any]]] = {"requests": [], "responses": [], "request_failures": [], "console": []}
    phase_ref = {"name": "context_created"}
    page_count = config.pages if pages is None else pages

    context_options = build_context_options(config, gpc=gpc, storage_state=storage_state, raw_har=raw_har)

    context: BrowserContext | None = None
    page: Page | None = None
    checkpoints: list[dict[str, Any]] = []
    action_result: dict[str, Any] = {"status": "not_run"}
    errors: list[dict[str, Any]] = []
    exercises: dict[str, Any] = {}
    page_scan: dict[str, Any] = {}
    cmp_match: dict[str, Any] | None = None
    isolation: dict[str, Any] = {}
    started = utc_now()

    def settle() -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=min(config.timeout_ms, 8000))
        except Exception:
            pass

    try:
        context = browser.new_context(**context_options)
        if gpc:
            context.add_init_script(
                """
                (() => {
                  try { Object.defineProperty(Navigator.prototype, 'globalPrivacyControl', {get: () => true, configurable: true}); } catch {}
                  try { Object.defineProperty(navigator, 'globalPrivacyControl', {get: () => true, configurable: true}); } catch {}
                })();
                """
            )
        page = context.new_page()
        page.set_default_timeout(config.timeout_ms)
        page.set_default_navigation_timeout(config.timeout_ms)

        if storage_state is None:
            isolation = assert_clean_context(context, page)
        else:
            isolation = {"checked": False, "note": "Context intentionally seeded with a prior storage state for the persistence check."}

        _attach_event_listeners(page, phase_ref, events)
        phase_ref["name"] = "initial_navigation"
        page.goto(config.url, wait_until="domcontentloaded", timeout=config.timeout_ms)
        settle()
        exercises["initial_dwell"] = dwell_and_nudge(page, config)

        cmp_match = fingerprint_cmp(page, cmp_table)
        cmp_entry = (cmp_match or {}).get("entry")

        phase_ref["name"] = "pre_interaction"
        checkpoints.append(capture_checkpoint(page, context, scenario, "01-pre-interaction", private_dir, share_dir))

        # E1/E2 inputs, captured before any choice so they reflect what every
        # visitor is served.
        page_scan = {
            "links": collect_page_links(page),
            "embedded_identifiers": checks.scan_embedded_identifiers(capture_served_html(page), page.url),
        }
        try:
            page_scan["page_text"] = page.inner_text("body")[:200000]
        except Exception:
            page_scan["page_text"] = ""

        if action == "deny":
            phase_ref["name"] = "denial_interaction"
            action_result = execute_denial(page, context, config.wait_ms, config.manual, share_scenario,
                                           cmp_entry, phase_ref, config.control_verdicts)
            phase_ref["name"] = "post_denial"
            checkpoints.append(capture_checkpoint(page, context, scenario, "02-post-denial", private_dir, share_dir))
        elif action == "accept":
            phase_ref["name"] = "accept_interaction"
            action_result = execute_accept(page, context, config.wait_ms, cmp_entry, config.control_verdicts)
            phase_ref["name"] = "post_accept"
            checkpoints.append(capture_checkpoint(page, context, scenario, "02-post-accept", private_dir, share_dir))
        elif action == "none":
            action_result = {"status": "no_interaction"}
        else:
            raise ValueError(f"Unsupported action: {action}")

        if action in {"deny", "accept"} or gpc:
            phase_ref["name"] = "refresh"
            try:
                page.reload(wait_until="domcontentloaded", timeout=config.timeout_ms)
                settle()
                exercises["refresh_dwell"] = dwell_and_nudge(page, config)
                checkpoints.append(capture_checkpoint(page, context, scenario, "03-after-refresh", private_dir, share_dir))
            except Exception as error:
                errors.append({"stage": "refresh", "error": str(error)[:2000]})

            links = safe_internal_links(page, config.url, page_count)
            for index, link in enumerate(links, start=1):
                phase_ref["name"] = f"internal_navigation_{index}"
                try:
                    page.goto(link, wait_until="domcontentloaded", timeout=config.timeout_ms)
                    settle()
                    exercises[f"page_{index}_dwell"] = dwell_and_nudge(page, config)
                    checkpoints.append(capture_checkpoint(page, context, scenario, f"{3 + index:02d}-internal-page-{index}", private_dir, share_dir))
                except Exception as error:
                    errors.append({"stage": f"internal_navigation_{index}", "url": sanitize_url(link), "error": str(error)[:2000]})

            # D2/D3 - exercise the paths that commonly trigger transmission.
            if run_exercises and config.thorough:
                if config.exercise_search:
                    phase_ref["name"] = "exercise_search"
                    try:
                        exercises["search"] = exercise_search(page, config)
                    except Exception as error:
                        errors.append({"stage": "exercise_search", "error": str(error)[:1000]})
                if config.exercise_forms:
                    phase_ref["name"] = "exercise_forms"
                    try:
                        page.goto(config.url, wait_until="domcontentloaded", timeout=config.timeout_ms)
                        settle()
                        exercises["forms"] = exercise_forms(page, config)
                        _sleep_ms(config.wait_ms)
                    except Exception as error:
                        errors.append({"stage": "exercise_forms", "error": str(error)[:1000]})
                phase_ref["name"] = "post_exercise"
                try:
                    checkpoints.append(capture_checkpoint(page, context, scenario, "09-post-exercise", private_dir, share_dir))
                except Exception as error:
                    errors.append({"stage": "post_exercise_checkpoint", "error": str(error)[:1000]})

        # Preserve the final state so the persistence check can replay it (E4).
        try:
            final_storage_state = context.storage_state()
        except Exception:
            final_storage_state = None
    except Exception as error:
        errors.append({"stage": "scenario", "error": str(error)[:4000], "type": type(error).__name__})
        final_storage_state = None
    finally:
        if context is not None:
            try:
                context.close()
            except Exception as error:
                errors.append({"stage": "context_close", "error": str(error)[:2000]})

    if raw_har.exists():
        try:
            sanitize_har_file(raw_har, sanitized_har)
        except Exception as error:
            errors.append({"stage": "har_sanitize", "error": str(error)[:2000]})

    write_json(private_scenario / f"{scenario}-events.raw.json", events)
    write_json(share_scenario / f"{scenario}-events.json", sanitize_event_log(events))

    validity = _scenario_validity(action, action_result, errors)
    scenario_result = {
        "scenario": scenario,
        "url": config.url,
        "started": started,
        "finished": utc_now(),
        "gpc": gpc,
        # Recorded per scenario, not only in run metadata: with --viewport both
        # a single bundle carries scenarios captured under two device profiles,
        # and a finding must be traceable to the one it was observed under.
        "viewport_label": config.viewport_label,
        "viewport": dict(config.viewport),
        "action": action,
        "action_result": action_result,
        "checkpoints": checkpoints,
        "events": events,
        "errors": errors,
        "cmp": {k: v for k, v in (cmp_match or {}).items() if k != "entry"} or None,
        "isolation_assertion": isolation,
        "exercises": exercises,
        "page_scan": page_scan,
        "consent_mode": _collect_consent_mode(events),
        "validity": validity,
        "final_storage_state": final_storage_state,
        "raw_har": str(raw_har) if raw_har.exists() else None,
        "sanitized_har": str(sanitized_har) if sanitized_har.exists() else None,
    }
    write_json(private_scenario / f"{scenario}-result.raw.json", scenario_result)

    share_result = json.loads(json.dumps({k: v for k, v in scenario_result.items() if k != "final_storage_state"}, default=str))
    share_result["events"] = sanitize_event_log(events)
    for checkpoint in share_result.get("checkpoints", []):
        checkpoint["cookies"] = redact_storage_state({"cookies": checkpoint.get("cookies", []), "origins": []}).get("cookies", [])
        checkpoint["storage_state"] = redact_storage_state(checkpoint.get("storage_state", {}))
    write_json(share_scenario / f"{scenario}-result.json", share_result)
    return scenario_result


def _fatal_scenario_error(scenario_result: dict[str, Any]) -> dict[str, Any] | None:
    """The stage=="scenario" error that aborted the whole attempt, if any."""
    for error in scenario_result.get("errors") or []:
        if error.get("stage") == "scenario":
            return error
    return None


def _classify_scenario_result(scenario_result: dict[str, Any]) -> str:
    """Map one attempt's result onto checks.classify_scenario_failure's inputs."""
    fatal = _fatal_scenario_error(scenario_result)
    validity = scenario_result.get("validity") or {}
    return checks.classify_scenario_failure(
        fatal_error=(fatal or {}).get("error"),
        fatal_error_type=(fatal or {}).get("type"),
        interaction_required=bool(validity.get("required_interaction")),
        interaction_completed=bool(validity.get("interaction_completed", True)),
        interaction_verified=bool(validity.get("verification_passed", True)),
    )


def _attempt_record(attempt: int, scenario_result: dict[str, Any], failure_class: str) -> dict[str, Any]:
    """A lightweight summary of one attempt for the `attempts` list.

    Deliberately small (not a duplicate capture): the full evidence for the
    attempt that stands is already the rest of the scenario result. This is
    just enough to show a reader what happened on each try.
    """
    fatal = _fatal_scenario_error(scenario_result)
    validity = scenario_result.get("validity") or {}
    return {
        "attempt": attempt,
        "failure_class": failure_class,
        "error": (fatal or {}).get("error"),
        "error_type": (fatal or {}).get("type"),
        "valid": validity.get("valid"),
        "invalid_reason": validity.get("invalid_reason"),
    }


def run_scenario_with_retry(
    browser: Browser,
    scenario: str,
    config: ScenarioConfig,
    private_dir: Path,
    share_dir: Path,
    action: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a scenario, retrying once when the first attempt is a transport flake.

    Retries only a navigation/timeout failure (see
    `checks.classify_scenario_failure` / `should_retry_scenario`). A scenario
    whose consent interaction itself failed to complete or verify is never
    retried - that is a finding about the site, not instability in our tooling
    (issue #12). Both attempts are recorded under `attempts` on the returned
    result so a flaky first try stays visible even when the retry succeeds.
    """
    result = run_scenario(browser, scenario, config, private_dir, share_dir, action, **kwargs)
    failure_class = _classify_scenario_result(result)
    attempts = [_attempt_record(1, result, failure_class)]

    if checks.should_retry_scenario(failure_class):
        retry_result = run_scenario(browser, scenario, config, private_dir, share_dir, action, **kwargs)
        retry_class = _classify_scenario_result(retry_result)
        attempts.append(_attempt_record(2, retry_result, retry_class))
        result = retry_result

    result["attempts"] = attempts

    # run_scenario already wrote both json files before we knew about a retry;
    # patch them in place rather than duplicating its (redaction-aware) write.
    private_path = private_dir / scenario / f"{scenario}-result.raw.json"
    share_path = share_dir / scenario / f"{scenario}-result.json"
    if private_path.exists():
        write_json(private_path, result)
    if share_path.exists():
        share_result = read_json(share_path) or {}
        share_result["attempts"] = attempts
        write_json(share_path, share_result)

    return result


def _endpoint_set(scenario_result: dict[str, Any]) -> set[str]:
    """Distinct host+path endpoints seen in a scenario.

    Identity comes from `checks.endpoint_key`, shared with compare_runs so the
    stability check and the run diff cannot drift into counting different
    things.
    """
    output: set[str] = set()
    for request in (scenario_result.get("events") or {}).get("requests", []) or []:
        key = checks.endpoint_key(str(request.get("url", "")))
        if key:
            output.add(key)
    return output


def run_persistence_check(
    browser: Browser,
    config: ScenarioConfig,
    storage_state: dict[str, Any] | None,
    private_dir: Path,
    share_dir: Path,
    cmp_table: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replay a saved denial state into a brand-new context (E4).

    Persisting a choice within one session is the easy half. This checks the
    harder half: that the preference survives a fresh browser context, which is
    what a returning visitor actually experiences.
    """
    if not storage_state:
        return {"ran": False, "reason": "No storage state was captured from the denial scenario."}
    result = run_scenario_with_retry(
        browser, "persistence", config, private_dir, share_dir,
        action="none", gpc=False, cmp_table=cmp_table, pages=0,
        run_exercises=False, storage_state=storage_state,
    )
    checkpoint = (result.get("checkpoints") or [{}])[0]
    banner = checkpoint.get("banner") or {}
    reprompted = bool(banner.get("best_text"))
    return {
        "ran": True,
        "banner_reprompted": reprompted,
        "banner_text": (banner.get("best_text") or "")[:600],
        "scenario_result": result,
        "note": (
            "The saved preference did not survive into a fresh context; the visitor is prompted again."
            if reprompted else
            "The saved preference survived into a fresh context and no re-prompt was observed."
        ),
    }


def run_all_scenarios(
    browser: Browser,
    config: ScenarioConfig,
    private_dir: Path,
    share_dir: Path,
    include_gpc: bool = True,
    include_accept: bool = True,
    baseline_repeats: int = 2,
    include_persistence: bool = True,
    include_policies: bool = True,
    time_budget_s: float | None = None,
) -> dict[str, Any]:
    cmp_table = load_cmp_table()
    results: dict[str, Any] = {}

    # D5 - an optional wall-clock ceiling. Baseline and denial are never
    # skipped: they are what the findings rest on, and a run without them is
    # incomplete anyway, so cutting them to save time would trade the answer
    # for the schedule. Only the corroborating work is droppable, and every
    # drop is recorded - a budget that silently truncated coverage would make a
    # thin run read exactly like a thorough one.
    started = time.monotonic()
    skipped: list[dict[str, Any]] = []

    def over_budget() -> bool:
        return time_budget_s is not None and (time.monotonic() - started) >= time_budget_s

    def skip(name: str) -> bool:
        if not over_budget():
            return False
        skipped.append({
            "step": name,
            "elapsed_s": round(time.monotonic() - started, 1),
            "budget_s": time_budget_s,
        })
        return True

    results["baseline"] = run_scenario_with_retry(
        browser, "baseline", config, private_dir, share_dir, "none",
        gpc=False, cmp_table=cmp_table, pages=0, run_exercises=False,
    )
    results["denial"] = run_scenario_with_retry(
        browser, "denial", config, private_dir, share_dir, "deny",
        gpc=False, cmp_table=cmp_table,
    )
    if include_gpc and not skip("gpc scenario"):
        results["gpc"] = run_scenario_with_retry(
            browser, "gpc", config, private_dir, share_dir, "none",
            gpc=True, cmp_table=cmp_table,
        )
    if include_accept and not skip("accept-control scenario"):
        results["accept"] = run_scenario_with_retry(
            browser, "accept", config, private_dir, share_dir, "accept",
            gpc=False, cmp_table=cmp_table,
        )

    # D4 - repeat the baseline so A/B tests and flaky tags are not reported as
    # settled fact.
    repeat_sets = [_endpoint_set(results["baseline"])]
    repeats: list[dict[str, Any]] = []
    for index in range(1, max(0, baseline_repeats) + 1):
        if skip(f"baseline repeat {index}"):
            break
        repeat = run_scenario_with_retry(
            browser, f"baseline-repeat-{index}", config, private_dir, share_dir, "none",
            gpc=False, cmp_table=cmp_table, pages=0, run_exercises=False,
        )
        repeats.append(repeat)
        repeat_sets.append(_endpoint_set(repeat))
    if repeats:
        results["baseline_repeats"] = repeats
        results["baseline_stability"] = checks.compare_repeat_runs(repeat_sets)

    # E6 - archive the linked policy documents. Uses the baseline scenario's
    # links, collected before any consent choice, so the policies captured are
    # the ones every visitor is offered.
    if include_policies and not skip("policy text capture"):
        results["policies"] = capture_policy_texts(
            browser,
            (results["baseline"].get("page_scan") or {}).get("links") or [],
            share_dir,
            timeout_ms=config.timeout_ms,
        )

    if include_persistence and not skip("persistence check"):
        results["persistence"] = run_persistence_check(
            browser, config, results["denial"].get("final_storage_state"),
            private_dir, share_dir, cmp_table,
        )

    results["time_budget"] = {
        "limit_s": time_budget_s,
        "elapsed_s": round(time.monotonic() - started, 1),
        "exceeded": bool(skipped),
        "skipped_steps": skipped,
    }
    return results


