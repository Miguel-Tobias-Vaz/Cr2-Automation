"""Envolve scripts inline finais com opto-ready (uso único)."""
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent / "front"

for p in ROOT.glob("*.html"):
    text = p.read_text(encoding="utf-8")
    if "opto-ready" in text or p.name == "sessao.html":
        continue
    m = re.search(
        r"<script>\s*((?:(?!</script>).)+)\s*</script>\s*(?=</body>)",
        text,
        flags=re.DOTALL,
    )
    if not m:
        continue
    body = m.group(1).strip()
    if body.startswith("document.addEventListener"):
        continue
    wrapped = (
        '<script>\ndocument.addEventListener("opto-ready", () => {\n'
        + body
        + "\n});\n</script>"
    )
    text2 = text[: m.start()] + wrapped + text[m.end() :]
    p.write_text(text2, encoding="utf-8")
    print("wrapped", p.name)
