"""Erkennt in Zeilen des Kernel-Protokolls (KLOG) Meldungen, bei denen ein Hinweis weiterhilft.

Nur reine Erkennung, ohne Oberflaeche und ohne Texte (utils-Module binden ``i18n`` nicht ein): Die Funktion nennt eine
Kennung, die Oberflaeche macht daraus ihren Hinweis (``klog.hinweis.<kennung>``).

Belegt ist bisher eine Meldung: ``Call to unpatched function is detected!!!``. Sie steht im Kernel-Protokoll, wenn ein
Programm eine Funktion aufruft, zu der der Lader keine Bibliothek gefunden hat. Gemessen von ps5upload 12.6.16 an Red Dead
Redemption: ein Spiel ohne jede Ersatzbibliothek schrieb genau diese Zeile, eines mit einem falschen Satz schrieb keine.
Die Zeile ist also ein **positives** Zeichen fuer fehlende Bibliotheken - ihr Fehlen beweist nichts.
"""
from __future__ import annotations

import re

#: Kennung -> Muster (ohne Beachtung der Gross-/Kleinschreibung). Neue, gemessene Meldungen hier ergaenzen und in
#: ``i18n`` einen Text ``klog.hinweis.<kennung>`` anlegen.
MELDUNGEN: dict[str, "re.Pattern[str]"] = {
    "fehlende_funktion": re.compile(r"call to unpatched function", re.IGNORECASE),
}


def hinweis_kennung(zeile: str) -> "str | None":
    """Die Kennung des Hinweises, den ``zeile`` ausloest - ``None``, wenn die Zeile nichts Besonderes meldet."""
    text = str(zeile or "")
    for kennung, muster in MELDUNGEN.items():
        if muster.search(text):
            return kennung
    return None
