"""
Erzeugt app_icon.png aus dem eingebetteten Base64 im Hauptskript.
Wird von Build_Linux.sh aufgerufen.

Gegenstueck zu extract_icon.py: Windows braucht die .ico-Datei, Linux eine PNG.
Der Menueeintrag (.desktop) verweist auf ein Icon im Themenordner, und dort
erwartet die Spezifikation PNG oder SVG - .ico zeigen die wenigsten
Arbeitsumgebungen an.

Bevorzugt wird das groesste Bild aus app_icon.ico (schaerfer im Menue). Fehlt
Pillow oder die .ico-Datei, dient das ebenfalls eingebettete 32x32-PNG als
Rueckfallebene - klein, aber immer vorhanden.
"""
import base64
import os
import re
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(script_dir, "PS5ImageConverter_Pro_FINAL_revised.py")
ico = os.path.join(script_dir, "app_icon.ico")
dst = os.path.join(script_dir, "app_icon.png")

with open(src, "r", encoding="utf-8") as f:
    content = f.read()


def aus_ico() -> bytes | None:
    """Groesstes Einzelbild der .ico-Datei als PNG-Bytes."""
    if not os.path.isfile(ico):
        return None
    try:
        import io

        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(ico) as bild:
            # .ico enthaelt mehrere Groessen; Pillow oeffnet standardmaessig
            # nicht zwingend die groesste.
            groessen = sorted(getattr(bild, "ico", None).sizes()) if hasattr(bild, "ico") else []
            if groessen:
                bild.size = groessen[-1]
                bild = bild.ico.getimage(groessen[-1])
            puffer = io.BytesIO()
            bild.convert("RGBA").save(puffer, format="PNG")
            return puffer.getvalue()
    except Exception as exc:  # noqa: BLE001 - Rueckfallebene folgt
        print(f"Hinweis: app_icon.ico nicht lesbar ({exc}), nutze eingebettetes PNG.")
        return None


def aus_quelltext() -> bytes | None:
    """32x32-PNG aus dem eingebetteten Base64 im Hauptskript."""
    treffer = re.search(r'_APP_ICON_PNG32_B64 = "([^"]+)"', content)
    if not treffer:
        return None
    return base64.b64decode(treffer.group(1))


daten = aus_ico() or aus_quelltext()
if not daten:
    print("FEHLER: Weder app_icon.ico noch _APP_ICON_PNG32_B64 nutzbar.")
    sys.exit(1)

if os.path.isfile(dst):
    with open(dst, "rb") as f:
        if f.read() == daten:
            print(f"app_icon.png bereits synchron ({len(daten)} Bytes)")
            sys.exit(0)

with open(dst, "wb") as f:
    f.write(daten)

print(f"app_icon.png erzeugt ({os.path.getsize(dst)} Bytes)")
