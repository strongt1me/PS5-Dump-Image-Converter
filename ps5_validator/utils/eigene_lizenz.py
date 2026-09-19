# -*- coding: utf-8 -*-
"""Die Lizenz dieses Programms selbst: MIT.

Der Text ist wortgleich mit der Datei ``LICENSE`` im Projektordner - der
Datei, mit der das Repo am 25.06.2026 angelegt wurde. ``test_eigene_lizenz.py``
haelt beide gegeneinander.

Bis v1.9.28 liefen sie auseinander: Die ``LICENSE`` fiel am 06.07.2026 beim
Aufraeumen von "Diverses" mit aus dem Repo, und der Text, den das Programm
unter Windows beim Start in die Registry schreibt, nannte einen anderen
Inhaber ("PS5 Dump & Image Converter Contributors") und ein Jahr, das mit der
Uhr mitlief. Das Jahr hier ist das der Erstveroeffentlichung und bleibt stehen.
"""
from __future__ import annotations

#: Name der Datei im Projektordner und in den gebauten Fassungen.
DATEINAME = "LICENSE"
SPDX = "MIT"
INHABER = "strongt1me"
#: Jahr der Erstveroeffentlichung - laeuft bewusst nicht mit der Uhr mit.
JAHR = 2026
COPYRIGHT = f"Copyright (c) {JAHR} {INHABER}"

TEXT = (
    "MIT License\n"
    "\n"
    f"{COPYRIGHT}\n"
    "\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
    "of this software and associated documentation files (the \"Software\"), to deal\n"
    "in the Software without restriction, including without limitation the rights\n"
    "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
    "copies of the Software, and to permit persons to whom the Software is\n"
    "furnished to do so, subject to the following conditions:\n"
    "\n"
    "The above copyright notice and this permission notice shall be included in all\n"
    "copies or substantial portions of the Software.\n"
    "\n"
    "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n"
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
    "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
    "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
    "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
    "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
    "SOFTWARE.\n"
)
