# -*- coding: utf-8 -*-
"""Die Rueckrufe, ueber die der Kern mit einer Oberflaeche spricht.

Beim Herausloesen der Ablauflogik aus dem Tk-Monolithen taucht immer
dasselbe Paar auf: Etwas ist zu **melden**, und ein sichtbarer **Text**
muss uebersetzt werden. Beides kam frueher von der Instanz
(``_append_to_log`` und ``_t``) und wird jetzt hereingereicht.

Damit die Module auch ohne Oberflaeche vollstaendig arbeiten, hat jeder
Rueckruf einen Ersatz:

* :func:`stumm` nimmt Meldungen entgegen und verwirft sie.
* :func:`schluessel_zeigen` gibt den Uebersetzungsschluessel im Klartext
  zurueck. Im Protokoll ist das haesslich, aber es sagt, was gemeint war -
  eine leere Zeichenkette taete das nicht, und in Tests ist der Schluessel
  genau das, worauf sich pruefen laesst.

Diese Datei ist bewusst winzig. Sie steht hier, weil sonst jedes
herausgeloeste Modul dieselben zehn Zeilen mitbraechte - und
Doppelungen laufen auseinander, sobald jemand nur eine davon aendert.
"""
from __future__ import annotations

from typing import Any, Callable

#: Ein Melder nimmt eine fertige Zeile entgegen.
Melder = Callable[[str], None]

#: Eine Textquelle uebersetzt einen Schluessel samt Platzhaltern.
Textquelle = Callable[..., str]


def stumm(_zeile: str) -> None:
    """Nimmt Meldungen entgegen und verwirft sie."""


def schluessel_zeigen(schluessel: str, **werte: Any) -> str:
    """Ersatz fuer eine fehlende Uebersetzung - nennt Schluessel und Werte."""
    if not werte:
        return schluessel
    angaben = ", ".join("%s=%s" % (name, wert)
                        for name, wert in sorted(werte.items()))
    return "%s (%s)" % (schluessel, angaben)
