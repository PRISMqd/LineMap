#!/usr/bin/env python3
"""Dependency-free regressions for LineMap static release URI policy."""
from __future__ import annotations

import unittest

from release_preflight import reference_errors


class ReferencePolicyTests(unittest.TestCase):
    def assert_allowed(self, attr: str, ref: str) -> None:
        self.assertEqual(reference_errors(attr, ref), [], ref)

    def assert_blocked(self, attr: str, ref: str) -> None:
        self.assertTrue(reference_errors(attr, ref), ref)

    def test_allowed_reference_shapes(self) -> None:
        self.assert_allowed("href", "https://prismqd.ai/")
        self.assert_allowed("href", "mailto:jen@prismqd.ai?subject=LineMap%20workflow%20review")
        self.assert_allowed("href", "#main-content")
        self.assert_allowed("href", "./")

    def test_dangerous_and_ambiguous_schemes_fail_closed(self) -> None:
        for ref in (
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "ftp://example.com/file",
            "http://example.com/",
            "//example.com/path",
        ):
            with self.subTest(ref=ref):
                self.assert_blocked("href", ref)

    def test_mailto_is_href_only(self) -> None:
        self.assert_blocked("src", "mailto:jen@prismqd.ai")

    def test_root_relative_project_site_reference_fails_closed(self) -> None:
        self.assert_blocked("href", "/")


if __name__ == "__main__":
    unittest.main()
