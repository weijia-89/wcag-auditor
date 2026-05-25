#!/usr/bin/env python3
"""Download axe.min.js from the pinned npm/jsDelivr bundle and SHA256-check it.

    uv run python scripts/download_axe.py
    # or:
    make download-axe

B8 hardening: URL is pinned to axe-core@VERSION on jsDelivr (no `latest/download`
moving target), and the body is hashed before write. If EXPECTED_SHA256 is still
the TODO placeholder, this script refuses. Fail-closed beats fail-yolo.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

# Bump version + hash together. Don't update one without the other.
AXE_VERSION = "4.10.2"
# GitHub release assets no longer ship axe.min.js; npm registry is the pinned source.
URL = f"https://cdn.jsdelivr.net/npm/axe-core@{AXE_VERSION}/axe.min.js"

# SHA256 of axe-core v4.10.2 axe.min.js from the npm package.
# To re-verify: curl -fsSL "$URL" | shasum -a 256
EXPECTED_SHA256 = "b511cd9dec01c76f4b2ad1723b66b6db37d4c2eb4ed199076e1829d9ee7b75e3"

OUT = Path(__file__).parent.parent / "src" / "wcag_auditor" / "static" / "axe.min.js"


def main() -> None:
    if EXPECTED_SHA256 == "TODO_PIN_SHA256_FROM_RELEASE" or len(EXPECTED_SHA256) != 64:
        print(
            "ERROR: EXPECTED_SHA256 is not populated in scripts/download_axe.py.\n"
            f"Compute it for axe-core v{AXE_VERSION}:\n"
            f"  curl -fsSL {URL} | shasum -a 256\n"
            "Then paste the 64-char hex digest into EXPECTED_SHA256.",
            file=sys.stderr,
        )
        sys.exit(2)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading axe-core v{AXE_VERSION} from pinned npm/jsDelivr URL...")
    print(f"  URL: {URL}")
    print(f"  OUT: {OUT}")

    with urllib.request.urlopen(URL) as response:  # noqa: S310 (HTTPS, pinned URL)
        body = response.read()

    actual_sha = hashlib.sha256(body).hexdigest()
    if actual_sha != EXPECTED_SHA256:
        print(
            "ERROR: SHA256 mismatch. Refusing to write file.\n"
            f"  expected: {EXPECTED_SHA256}\n"
            f"  actual:   {actual_sha}\n"
            "If you intentionally bumped the version, update EXPECTED_SHA256.",
            file=sys.stderr,
        )
        sys.exit(3)

    OUT.write_bytes(body)
    size_kb = OUT.stat().st_size // 1024
    print(f"Done ({size_kb}KB). SHA256 verified.")


if __name__ == "__main__":
    main()
