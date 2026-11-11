"""Dev-time: cut static weight instances from the bundled variable fonts (fontTools)."""

import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

src, out = Path(sys.argv[1]), Path(sys.argv[2])
NAMES = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold"}
jobs = [
    ("JetBrainsMono-wght.ttf", "JetBrains Mono", "JetBrainsMono", {}, False),
    ("JetBrainsMono-Italic-wght.ttf", "JetBrains Mono", "JetBrainsMono", {}, True),
    ("Newsreader-opsz-wght.ttf", "Newsreader", "Newsreader", {"opsz": 16}, False),
    ("Newsreader-Italic-opsz-wght.ttf", "Newsreader", "Newsreader", {"opsz": 16}, True),
]
for fname, family, ps, extra, italic in jobs:
    for w in [400] if italic else [400, 500, 600, 700]:
        inst = instantiateVariableFont(TTFont(src / fname), {"wght": w, **extra})
        style = NAMES[w] + " Italic" if italic and w != 400 else ("Italic" if italic else NAMES[w])
        ribbi = style in ("Regular", "Italic", "Bold", "Bold Italic")
        name = inst["name"]
        for rec in list(name.names):
            if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 25):
                name.removeNames(nameID=rec.nameID)
        legacy_family = family if ribbi else f"{family} {NAMES[w]}"
        legacy_style = style if ribbi else ("Italic" if italic else "Regular")
        name.setName(legacy_family, 1, 3, 1, 0x409)
        name.setName(legacy_style, 2, 3, 1, 0x409)
        name.setName(f"{family} {style}", 4, 3, 1, 0x409)
        name.setName(f"{ps}-{style.replace(' ', '')}", 6, 3, 1, 0x409)
        name.setName(f"{ps}-{style.replace(' ', '')};static", 3, 3, 1, 0x409)
        name.setName(family, 16, 3, 1, 0x409)
        name.setName(style, 17, 3, 1, 0x409)
        inst["OS/2"].usWeightClass = w
        sel = inst["OS/2"].fsSelection & ~0b1100001  # clear italic, bold, regular
        sel |= 0b1 if italic else 0
        sel |= 0b100000 if style.startswith("Bold") else 0
        sel |= 0b1000000 if style == "Regular" else 0
        inst["OS/2"].fsSelection = sel
        inst["head"].macStyle = (1 if style.startswith("Bold") else 0) | (2 if italic else 0)
        if "STAT" in inst:
            del inst["STAT"]
        path = out / f"{ps}-{style.replace(' ', '')}.ttf"
        inst.save(path)
        print(path.name, path.stat().st_size)
