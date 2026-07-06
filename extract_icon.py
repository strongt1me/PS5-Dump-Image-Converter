"""
Extrahiert app_icon.ico aus dem eingebetteten Base64 im Hauptskript.
Wird von Build_EXE.ps1 aufgerufen.
"""
import base64
import re
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(script_dir, "PS5ImageConverter_Pro_FINAL_revised.py")
dst = os.path.join(script_dir, "app_icon.ico")

if os.path.isfile(dst) and os.path.getsize(dst) > 0:
    print(f"app_icon.ico bereits vorhanden ({os.path.getsize(dst)} Bytes)")
    sys.exit(0)

with open(src, "r", encoding="utf-8") as f:
    content = f.read()

m = re.search(r'_APP_ICON_ICO_B64 = "([^"]+)"', content)
if not m:
    print("FEHLER: _APP_ICON_ICO_B64 nicht gefunden im Skript.")
    sys.exit(1)

with open(dst, "wb") as f:
    f.write(base64.b64decode(m.group(1)))

print(f"app_icon.ico erfolgreich erstellt ({os.path.getsize(dst)} Bytes)")
