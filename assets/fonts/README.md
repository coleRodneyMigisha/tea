# Bundled fonts

Both families are SIL Open Font License 1.1 (texts in `OFL-*.txt`), from the `google/fonts`
repository: `ofl/jetbrainsmono` and `ofl/newsreader` (fetched 2026-11-11).

Qt registers a variable font as a single Regular style, so weights 500 and 600 rendered as
regular. These are static instances cut from the variable files with fontTools
(`tools/make_static_fonts.py`; Newsreader optical size pinned at 16):

```
python3 tools/make_static_fonts.py <folder> assets/fonts   # folder holds JetBrainsMono-wght.ttf,
# JetBrainsMono-Italic-wght.ttf, Newsreader-opsz-wght.ttf, Newsreader-Italic-opsz-wght.ttf
```

fontTools is only needed to regenerate them; it is not a tea dependency.
