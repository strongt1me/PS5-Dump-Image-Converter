# -*- coding: utf-8 -*-
"""Die Lizenz dieses Programms selbst: GPL-3.0-or-later.

Seit dem 07.10.2026 (Nutzerentscheid) steht das Programm unter der GNU General
Public License, Version 3 oder (nach Wahl) jeder spaeteren Fassung. Vorher galt
MIT - alles, was bis einschliesslich v1.9.64 veroeffentlicht wurde, bleibt fuer
seine Empfaenger unter MIT. Grund des Wechsels: Das Programm bindet GPL-Werke
direkt ein (MkPFS im eigenen Prozess, PS4 FFPFSC, LibProsperoPkg), und Code aus
GPL-Projekten darf jetzt uebernommen werden statt nur deren Ideen.

Die Datei ``LICENSE`` im Projektordner ist der **unveraenderte** Lizenztext der
Free Software Foundation (er darf nicht geaendert werden, deshalb steht der
Hinweis "oder spaeter" nicht dort, sondern hier, in der README und in der
Registry). ``test_eigene_lizenz.py`` haelt die Datei ueber :data:`TEXT_SHA256`
gegen das Original und den Hinweis gegen Bauplaene und Doku.

Bis v1.9.28 liefen Datei und Programm auseinander: Die ``LICENSE`` fiel am
06.07.2026 beim Aufraeumen von "Diverses" mit aus dem Repo, und der Text, den
das Programm unter Windows beim Start in die Registry schreibt, nannte einen
anderen Inhaber und ein Jahr, das mit der Uhr mitlief. Das Jahr hier ist das
der Erstveroeffentlichung und bleibt stehen.
"""
from __future__ import annotations

#: Name der Datei im Projektordner und in den gebauten Fassungen.
DATEINAME = "LICENSE"
SPDX = "GPL-3.0-or-later"
#: Der Name der Lizenz, wie ihn die Registry und die Doku nennen.
NAME = "GNU General Public License v3.0 or later"
INHABER = "strongt1me"
#: Jahr der Erstveroeffentlichung - laeuft bewusst nicht mit der Uhr mit.
JAHR = 2026
COPYRIGHT = f"Copyright (C) {JAHR} {INHABER}"
#: SHA-256 des unveraenderten GPL-3.0-Textes der FSF (gpl-3.0.txt, 35.149 Bytes,
#: Zeilenenden LF) - derselbe Text wie ``helloworld/LICENSE-GPL-3.0.txt``.
TEXT_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"

#: Der Hinweis, den die GPL fuer ein Programm unter ihr vorsieht ("How to Apply
#: These Terms to Your New Programs") - mit "or (at your option) any later version".
HINWEIS = (
    "PS5 Dump & Image Converter\n"
    f"{COPYRIGHT}\n"
    "\n"
    "This program is free software: you can redistribute it and/or modify\n"
    "it under the terms of the GNU General Public License as published by\n"
    "the Free Software Foundation, either version 3 of the License, or\n"
    "(at your option) any later version.\n"
    "\n"
    "This program is distributed in the hope that it will be useful,\n"
    "but WITHOUT ANY WARRANTY; without even the implied warranty of\n"
    "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the\n"
    "GNU General Public License for more details.\n"
    "\n"
    "You should have received a copy of the GNU General Public License\n"
    "along with this program.  If not, see <https://www.gnu.org/licenses/>.\n"
)
