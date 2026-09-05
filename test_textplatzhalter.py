# -*- coding: utf-8 -*-
"""Jeder Platzhalter in einem Text bekommt beim Aufruf auch einen Wert.

``translate()`` formatiert mit ``str.format(**kwargs)`` und faengt dabei
``KeyError`` ab::

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text

Das ist als Schutz gedacht, hat aber eine unangenehme Folge: Fehlt einem
Aufruf ein Platzhalter, den der Text nennt, **steht die geschweifte Klammer
woertlich im Fenster** - "Dieser Ordner ist nicht mehr da:\\n{pfad}". Ohne
Absturz, ohne Protokollzeile, ohne dass es beim Entwickeln auffaellt.

Die vorhandene Pruefung in ``test_downloads.py`` vergleicht nur Deutsch gegen
Englisch. Trueg**en** beide denselben falschen Platzhalter, kaeme sie durch -
und genau das ist der haeufige Fall, weil Uebersetzungen gemeinsam
geschrieben werden.

Diese Datei schliesst die Luecke von der anderen Seite: Sie sammelt aus dem
Quelltext, **welche Werte** jeder Aufruf tatsaechlich mitgibt, und haelt das
gegen die Platzhalter im Text. Aufgedeckt wurde die Luecke am 05.09.2026
beim Gegenlesen einer Aenderung an der Downloads-Verwaltung.
"""
from __future__ import annotations

import ast
import io
import re
import sys
import unittest
from collections import defaultdict
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils.i18n import STRINGS                # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

#: ``{}`` und ``{0}`` zaehlen nicht - hier geht es um benannte Werte.
_PLATZHALTER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)[!:}]")


def _platzhalter(text: str) -> set[str]:
    return set(_PLATZHALTER.findall(text))


def _aufrufe_sammeln() -> dict[str, list[tuple[int, set[str]]]]:
    """Sammelt je Textschluessel, welche Werte die Aufrufe mitgeben.

    Erfasst werden ``self._t("schluessel", name=...)`` und
    ``gui._t(...)``/``app._t(...)`` - der Handler des Log-Servers etwa ruft
    ueber eine umbenannte Referenz.

    Aufrufe mit ``**etwas`` bleiben aussen vor: Was da drinsteht, ist zur
    Pruefzeit nicht bekannt.
    """
    with io.open(HAUPTDATEI, encoding="utf-8") as fh:
        baum = ast.parse(fh.read())

    gefunden: dict[str, list[tuple[int, set[str]]]] = defaultdict(list)
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        if getattr(knoten.func, "attr", "") != "_t" or not knoten.args:
            continue
        erstes = knoten.args[0]
        if not (isinstance(erstes, ast.Constant) and isinstance(erstes.value, str)):
            continue                      # Schluessel wird berechnet
        if any(w.arg is None for w in knoten.keywords):
            continue                      # **kwargs - Inhalt unbekannt
        werte = {w.arg for w in knoten.keywords if w.arg}
        gefunden[erstes.value].append((knoten.lineno, werte))
    return gefunden


class PlatzhalterTests(unittest.TestCase):
    """Text und Aufruf muessen zueinander passen - in beide Richtungen."""

    @classmethod
    def setUpClass(cls):
        cls.aufrufe = _aufrufe_sammeln()

    def test_es_wurden_ueberhaupt_aufrufe_gefunden(self):
        """Ohne diese Zusicherung waere die ganze Datei ein Scheinriese.

        Aendert sich der Name der Uebersetzungsmethode, faende das Sammeln
        nichts mehr - und alle Pruefungen darunter waeren still gruen.
        """
        self.assertGreater(len(self.aufrufe), 300,
                           "Zu wenige _t-Aufrufe gefunden - sammelt die "
                           "Auswertung noch richtig?")

    def test_jeder_aufruf_gibt_alle_platzhalter_mit(self):
        """Der Fehlerfall: Der Text nennt {pfad}, der Aufruf gibt keinen mit.

        Dann steht "{pfad}" woertlich im Fenster.
        """
        fehlend: list[str] = []
        for schluessel, stellen in sorted(self.aufrufe.items()):
            eintrag = STRINGS.get(schluessel)
            if not isinstance(eintrag, dict):
                continue                  # unbekannter Schluessel - andere Pruefung
            for sprache, text in eintrag.items():
                if not isinstance(text, str):
                    continue
                noetig = _platzhalter(text)
                if not noetig:
                    continue
                for zeile, gegeben in stellen:
                    if noetig - gegeben:
                        fehlend.append(
                            "%s (%s), Zeile %d: es fehlt %s"
                            % (schluessel, sprache, zeile,
                               ", ".join(sorted(noetig - gegeben))))
        self.assertEqual([], fehlend, "\n".join(fehlend))

    def test_kein_aufruf_gibt_werte_mit_die_der_text_nicht_kennt(self):
        """Die Gegenrichtung: ein Wert zu viel bleibt unbemerkt liegen.

        Das ist kein Fehler im Fenster, aber fast immer ein Zeichen dafuer,
        dass der Text umgeschrieben und der Aufruf vergessen wurde - oder
        umgekehrt.
        """
        ueberfluessig: list[str] = []
        for schluessel, stellen in sorted(self.aufrufe.items()):
            eintrag = STRINGS.get(schluessel)
            if not isinstance(eintrag, dict):
                continue
            bekannt: set[str] = set()
            for text in eintrag.values():
                if isinstance(text, str):
                    bekannt |= _platzhalter(text)
            for zeile, gegeben in stellen:
                zuviel = gegeben - bekannt
                if zuviel:
                    ueberfluessig.append(
                        "%s, Zeile %d: %s wird mitgegeben, steht aber in "
                        "keiner Sprache im Text"
                        % (schluessel, zeile, ", ".join(sorted(zuviel))))
        self.assertEqual([], ueberfluessig, "\n".join(ueberfluessig))

    def test_beide_sprachen_nennen_dieselben_platzhalter(self):
        """Wie die Pruefung in test_downloads, aber ueber ALLE Texte.

        Dort galt sie nur fuer den downloads.*-Block.
        """
        abweichend: list[str] = []
        for schluessel, eintrag in sorted(STRINGS.items()):
            if not isinstance(eintrag, dict):
                continue
            je_sprache = {s: _platzhalter(t) for s, t in eintrag.items()
                          if isinstance(t, str)}
            if len(set(map(frozenset, je_sprache.values()))) > 1:
                abweichend.append("%s: %s" % (schluessel, je_sprache))
        self.assertEqual([], abweichend, "\n".join(abweichend))


class GegenprobeTests(unittest.TestCase):
    """Faengt die Auswertung ueberhaupt etwas?"""

    def test_die_auswertung_erkennt_einen_fehlenden_wert(self):
        """Nachgestellt an einem Baum, nicht am echten Quelltext."""
        baum = ast.parse('self._t("beispiel.text")\n')
        aufruf = next(k for k in ast.walk(baum) if isinstance(k, ast.Call))
        gegeben = {w.arg for w in aufruf.keywords if w.arg}
        self.assertEqual(set(), gegeben)
        self.assertEqual({"pfad"}, _platzhalter("Hier: {pfad}"))
        self.assertTrue(_platzhalter("Hier: {pfad}") - gegeben,
                        "Die Auswertung wuerde den Fehler nicht sehen.")

    def test_geschweifte_klammern_ohne_namen_zaehlen_nicht(self):
        self.assertEqual(set(), _platzhalter("100 % geschafft"))
        self.assertEqual(set(), _platzhalter("{} und {0}"))
        self.assertEqual({"v0"}, _platzhalter("{v0} Bytes"))
        self.assertEqual({"groesse"}, _platzhalter("{groesse:.1f} MB"))


if __name__ == "__main__":
    unittest.main()
