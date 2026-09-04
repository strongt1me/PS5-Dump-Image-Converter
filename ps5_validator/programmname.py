# -*- coding: utf-8 -*-
"""Wie das Programm heisst - an einer Stelle.

Der Name stand bis zum 31.08.2026 an fuenfzehn Stellen im Quelltext,
in zwei Schreibweisen und ohne Verbindung untereinander: im
Monolithen, in fuenf WPF-Bausteinen, in zwei Meldungsschluesseln, im
Kommandozeilenmodus und in der Umgebungspruefung. Eine Umbenennung
hiess: alle fuenfzehn finden.

Jetzt steht er hier. Wer ihn aendert, aendert ihn ueberall.

**Die Grossschreibung ist Gestaltung, nicht Name.** Seitenleiste und
Startbild setzen ihn in Versalien, weil er dort als Schriftzug wirkt.
Deshalb gibt es :data:`NAME` und :data:`NAME_GROSS` - nicht zwei
Namen, sondern einen in zwei Satzweisen.

Dieses Modul liegt bewusst NICHT unter ``ui/``: Es wird auch vom
Kommandozeilenmodus und von der Umgebungspruefung gebraucht, wo es
keine Oberflaeche gibt.
"""
from __future__ import annotations

#: Wie das Programm heisst.
# In der Pro-Arbeitskopie steht hier "... - Pro". Dieses Projekt ist die
# andere Auslieferung und heisst seit jeher ohne den Zusatz; eine
# Umbenennung waere eine sichtbare Aenderung fuer die Nutzer.
NAME = "PS5 Dump & Image Converter"

#: Derselbe Name als Schriftzug, fuer Seitenleiste und Startbild.
NAME_GROSS = NAME.upper()

#: Wer im Netz nach etwas fragt, nennt sich so.
#:
#: Ohne Sonderzeichen und ohne Leerzeichen am Rand - ein
#: ``User-Agent`` mit ``&`` darin ist zwar erlaubt, aber manche
#: Gegenstellen stolpern darueber.
NETZKENNUNG = "PS5-Dump-Image-Converter"


def titel(fassung: str = "") -> str:
    """Der Fenstertitel: Name und Fassungsnummer.

    Args:
        fassung: Die Fassungsnummer, etwa ``"v1.9.5"``. Leer laesst sie
            weg.

    Returns:
        Zum Beispiel ``"PS5 Dump & Image Converter v1.9.5"``.
    """
    nummer = str(fassung or "").strip()
    return "%s %s" % (NAME, nummer) if nummer else NAME


def titel_gross(fassung: str = "") -> str:
    """Dasselbe als Schriftzug."""
    nummer = str(fassung or "").strip()
    return "%s %s" % (NAME_GROSS, nummer) if nummer else NAME_GROSS
