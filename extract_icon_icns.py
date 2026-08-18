"""
Erzeugt app_icon.icns aus app_icon.ico.
Wird von Build_macOS.sh aufgerufen.

Drittes Gegenstueck zu extract_icon.py (Windows, .ico) und
extract_icon_png.py (Linux, .png): macOS erwartet fuer das Symbol eines
Programmbuendels eine .icns-Datei. PyInstaller reicht sie unveraendert nach
Contents/Resources/ durch - was dort nicht als .icns liegt, zeigt der Finder
als leeres Blatt an.

Bewusst ohne ``iconutil``: Das Apple-Werkzeug gibt es nur auf einem Mac, und
diese Datei soll sich auch auf dem Windows-Rechner erzeugen lassen, auf dem der
uebrige Quelltext gepflegt wird. Pillow schreibt das Format in reinem Python.

Die Groessen werden einzeln mit LANCZOS gerechnet und ueber ``append_images``
uebergeben. Ohne das nimmt Pillow fuer jede Kachel sein eigenes,
qualitativ schlechteres ``resize()`` - sichtbar vor allem bei 512 und 1024,
die aus der 256er Vorlage hochgerechnet werden muessen.
"""
import base64
import io
import os
import re
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(script_dir, "PS5ImageConverter_Pro_FINAL_revised.py")
ico = os.path.join(script_dir, "app_icon.ico")
dst = os.path.join(script_dir, "app_icon.icns")

#: Kachelgroessen, die Pillow fuer eine vollstaendige .icns-Datei braucht.
GROESSEN = (32, 64, 128, 256, 512, 1024)

try:
    from PIL import Image
except ImportError:
    print("FEHLER: Pillow fehlt. Bitte 'pip install pillow' ausfuehren.")
    sys.exit(1)

_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1)


def groesstes_aus_ico():
    """Groesstes Einzelbild der .ico-Datei als RGBA-Bild."""
    if not os.path.isfile(ico):
        return None
    try:
        with Image.open(ico) as bild:
            # .ico enthaelt mehrere Groessen; Pillow oeffnet nicht zwingend die
            # groesste. Gleiche Auswahl wie in extract_icon_png.py.
            groessen = sorted(bild.ico.sizes()) if hasattr(bild, "ico") else []
            if groessen:
                bild = bild.ico.getimage(groessen[-1])
            return bild.convert("RGBA")
    except Exception as exc:  # noqa: BLE001 - Rueckfallebene folgt
        print(f"Hinweis: app_icon.ico nicht lesbar ({exc}), nutze eingebettetes PNG.")
        return None


def aus_quelltext():
    """32x32-PNG aus dem eingebetteten Base64 im Hauptskript."""
    try:
        with open(src, "r", encoding="utf-8") as datei:
            treffer = re.search(r'_APP_ICON_PNG32_B64 = "([^"]+)"', datei.read())
    except OSError as exc:
        print(f"FEHLER: {src} nicht lesbar ({exc}).")
        return None
    if not treffer:
        return None
    return Image.open(io.BytesIO(base64.b64decode(treffer.group(1)))).convert("RGBA")


vorlage = groesstes_aus_ico() or aus_quelltext()
if vorlage is None:
    print("FEHLER: Weder app_icon.ico noch _APP_ICON_PNG32_B64 nutzbar.")
    sys.exit(1)

if vorlage.width != vorlage.height:
    # .icns kennt nur Quadrate. Ein schiefes Seitenverhaeltnis wuerde Pillow
    # kommentarlos stauchen - lieber vorher auf die laengere Kante auffuellen.
    kante = max(vorlage.size)
    quadrat = Image.new("RGBA", (kante, kante), (0, 0, 0, 0))
    quadrat.paste(vorlage, ((kante - vorlage.width) // 2, (kante - vorlage.height) // 2))
    vorlage = quadrat

kacheln = [vorlage.resize((kante, kante), _LANCZOS) for kante in GROESSEN]

puffer = io.BytesIO()
# Das erste Bild traegt den Aufruf, die uebrigen liefern die Kacheln nach.
kacheln[-1].save(puffer, format="ICNS", append_images=kacheln)
daten = puffer.getvalue()

if os.path.isfile(dst):
    with open(dst, "rb") as f:
        if f.read() == daten:
            print(f"app_icon.icns bereits synchron ({len(daten)} Bytes)")
            sys.exit(0)

with open(dst, "wb") as f:
    f.write(daten)

print(f"app_icon.icns erzeugt ({os.path.getsize(dst)} Bytes, Vorlage {vorlage.width}x{vorlage.height})")
