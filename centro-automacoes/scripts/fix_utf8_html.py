# -*- coding: utf-8 -*-
"""Regrava HTML com UTF-8 correto (evita corrupção do editor)."""
from __future__ import annotations

import re
from pathlib import Path

FRONT = Path(__file__).resolve().parent.parent / "front"
CACHE = "home53"


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
        if "\ufffd" not in text:
            return text
    except UnicodeDecodeError:
        pass
    return raw.decode("cp1252")


def bump_cache(text: str) -> str:
    return re.sub(r"\?v=home\d+", f"?v={CACHE}", text)


def main() -> None:
    for f in sorted(FRONT.glob("*.html")):
        t = bump_cache(read_text(f))
        f.write_text(t, encoding="utf-8", newline="\n")
        t.encode("utf-8")
        print("ok", f.name)

    shared = Path(__file__).resolve().parent.parent / "front" / "shared.js"
    s = shared.read_text(encoding="utf-8")
    s = re.sub(r"shader-background\.js\?v=home\d+", f"shader-background.js?v={CACHE}", s)
    shared.write_text(s, encoding="utf-8", newline="\n")
    print("ok shared.js")


if __name__ == "__main__":
    main()
