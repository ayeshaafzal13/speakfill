"""Download the Urdu-capable Naskh font used for PDF output.  Run once:  python download_fonts.py"""
import sys
import urllib.request
from pathlib import Path

FONT_DIR = Path(__file__).parent / "app" / "fonts"
FONTS = {
    "NotoNaskhArabic-Regular.ttf": [
        "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoNaskhArabic/hinted/ttf/NotoNaskhArabic-Regular.ttf",
        "https://github.com/google/fonts/raw/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
    ],
}

FONT_DIR.mkdir(parents=True, exist_ok=True)
ok = True
for name, urls in FONTS.items():
    target = FONT_DIR / name
    if target.exists():
        print("already have", name)
        continue
    for url in urls:
        try:
            print("downloading", url)
            urllib.request.urlretrieve(url, target)
            print("saved", target)
            break
        except Exception as e:
            print("failed:", e)
    else:
        ok = False
if not ok:
    print("\nCould not download. Manually download 'Noto Naskh Arabic' (or Amiri) from fonts.google.com")
    print("and put the .ttf file in app/fonts/")
    sys.exit(1)
