"""Deterministic SYNTHETIC avatar illustrations (no real photographs are used anywhere)."""
import hashlib
from xml.sax.saxutils import escape

_PALETTE = [("#176B57", "#E5F5EF"), ("#2A9D8F", "#EAF3FB"), ("#3976B8", "#E5F5EF"),
            ("#5B8E7D", "#F5F9F7"), ("#2F6F9F", "#EAF3FB"), ("#4C9F70", "#E5F5EF")]


def avatar_svg(name: str, seed: str) -> str:
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    fg, bg = _PALETTE[h % len(_PALETTE)]
    initials = "".join(w[0] for w in name.split()[:2]).upper()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" role="img" aria-label="Synthetic profile illustration for {escape(name)}">
<rect width="200" height="200" fill="{bg}"/>
<circle cx="100" cy="78" r="38" fill="{fg}" opacity="0.92"/>
<path d="M30 200 C30 142 66 122 100 122 C134 122 170 142 170 200 Z" fill="{fg}" opacity="0.92"/>
<text x="100" y="92" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="30" font-weight="600" fill="#FFFFFF">{escape(initials)}</text>
<text x="100" y="194" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="9" fill="#FFFFFF" opacity="0.85">SYNTHETIC DEMO</text>
</svg>"""
