#!/usr/bin/env python3
"""Deterministic static release preflight for the LineMap public prototype site.

This is intentionally stdlib-only so the release gate has no package-install step.
It validates repository-local references and locked product-boundary language. It
does not claim that external destinations are reachable; destination verification
remains a separate release gate.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

REQUIRED_SNIPPETS = (
    "Working browser prototype",
    "It is not a production clinical system",
    "has not established clinical, operational, or economic outcomes",
    "This hypothesis requires testing",
    "No clinical, operational, or economic outcomes have been established",
    "https://prismqd.github.io/LineMapDemo/",
    "Do not provide patient information",
    'nav aria-label="Primary"',
    "a:focus-visible",
    '<link rel="canonical" href="https://prismqd.github.io/LineMap/">',
    '<meta property="og:url" content="https://prismqd.github.io/LineMap/">',
)

EXPECTED_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; font-src 'none'; connect-src 'none'; script-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"

FORBIDDEN_PUBLIC_CLAIMS = (
    "clinically validated",
    "proven to reduce",
    "proven to improve",
    "reduces medication errors",
    "improves patient outcomes",
    "saves time and money",
)

SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "Stripe live secret": re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b"),
    "generic private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


class RefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[tuple[str, str]] = []
        self.html_lang: str | None = None
        self.has_title = False
        self.meta_names: dict[str, str] = {}
        self.meta_http_equiv: dict[str, str] = {}
        self.h1_count = 0
        self.empty_links = 0
        self._anchor_depth = 0
        self._anchor_has_text: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "html":
            self.html_lang = a.get("lang")
        if tag == "title":
            self.has_title = True
        if tag == "h1":
            self.h1_count += 1
        if tag == "meta" and a.get("name"):
            self.meta_names[a["name"].lower()] = a.get("content") or ""
        if tag == "meta" and a.get("http-equiv"):
            self.meta_http_equiv[a["http-equiv"].lower()] = a.get("content") or ""
        if tag == "a":
            self._anchor_depth += 1
            self._anchor_has_text.append(bool(a.get("aria-label")))
        for key in ("href", "src"):
            value = a.get(key)
            if value:
                self.refs.append((key, value))

    def handle_data(self, data: str) -> None:
        if self._anchor_depth and data.strip() and self._anchor_has_text:
            self._anchor_has_text[-1] = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_depth and self._anchor_has_text:
            if not self._anchor_has_text.pop():
                self.empty_links += 1
            self._anchor_depth -= 1


def local_path(ref: str) -> Path | None:
    parsed = urlparse(ref)
    if parsed.scheme or ref.startswith("//") or ref.startswith("#"):
        return None
    path = unquote(parsed.path)
    if path in ("", "/"):
        return None
    # GitHub Pages project sites resolve root-relative paths at the host root,
    # so only repository-relative paths can be validated as local files here.
    if path.startswith("/"):
        return None
    return ROOT / path


def fail(errors: list[str]) -> None:
    for item in errors:
        print(f"ERROR: {item}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    errors: list[str] = []
    if not INDEX.is_file():
        fail(["index.html is missing"])

    text = INDEX.read_text(encoding="utf-8")
    lower = text.lower()
    parser = RefParser()
    parser.feed(text)

    if parser.html_lang != "en":
        errors.append("<html lang=\"en\"> is required")
    if not parser.has_title:
        errors.append("document title is missing")
    if not parser.meta_names.get("viewport"):
        errors.append("viewport meta is missing")
    if not parser.meta_names.get("description"):
        errors.append("meta description is missing")
    if parser.meta_names.get("referrer") != "no-referrer":
        errors.append("referrer policy must remain no-referrer")
    if parser.meta_http_equiv.get("content-security-policy") != EXPECTED_CSP:
        errors.append("Content Security Policy is missing or weaker/different than the locked static runtime policy")
    if parser.h1_count != 1:
        errors.append(f"exactly one h1 is required; found {parser.h1_count}")
    if parser.empty_links:
        errors.append(f"links without accessible text/label detected: {parser.empty_links}")

    for snippet in REQUIRED_SNIPPETS:
        if snippet not in text:
            errors.append(f"required product-boundary/accessibility text missing: {snippet!r}")

    for phrase in FORBIDDEN_PUBLIC_CLAIMS:
        if phrase in lower:
            errors.append(f"unsupported public claim detected: {phrase!r}")

    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"secret-shaped value detected ({name})")

    for attr, ref in parser.refs:
        parsed = urlparse(ref)
        if parsed.scheme == "http":
            errors.append(f"insecure external {attr}: {ref}")
        if not parsed.scheme and not ref.startswith(("//", "#")) and parsed.path.startswith("/"):
            errors.append(f"root-relative {attr} is unsafe for a GitHub Pages project site: {ref}")
        candidate = local_path(ref)
        if candidate is not None and not candidate.exists():
            errors.append(f"missing repository-local {attr}: {ref}")

    if errors:
        fail(errors)

    print("PASS: LineMap static release preflight")
    print(f"Checked {len(parser.refs)} href/src references, {len(REQUIRED_SNIPPETS)} product/accessibility controls, locked CSP/referrer policy, and Pages-safe routing.")
    print("NOTE: External URL reachability and rendered GitHub Pages verification remain separate destination gates.")


if __name__ == "__main__":
    main()
