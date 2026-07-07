"""
Synchronisiert app_icon.ico mit dem eingebetteten Base64 im Hauptskript.
Wird von Build_EXE.ps1 aufgerufen.
"""
import base64
import os
import re
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(script_dir, "PS5ImageConverter_Pro_FINAL_revised.py")
dst = os.path.join(script_dir, "app_icon.ico")

with open(src, "r", encoding="utf-8") as f:
    content = f.read()

m = re.search(r'_APP_ICON_ICO_B64 = "([^"]+)"', content)
if not m:
    print("FEHLER: _APP_ICON_ICO_B64 nicht gefunden im Skript.")
    sys.exit(1)

icon_bytes = base64.b64decode(m.group(1))

if os.path.isfile(dst):
    with open(dst, "rb") as f:
        current_bytes = f.read()
    if current_bytes == icon_bytes:
        print(f"app_icon.ico bereits synchron ({len(icon_bytes)} Bytes)")
        sys.exit(0)

with open(dst, "wb") as f:
    f.write(icon_bytes)

print(f"app_icon.ico mit eingebettetem Icon synchronisiert ({os.path.getsize(dst)} Bytes)")
