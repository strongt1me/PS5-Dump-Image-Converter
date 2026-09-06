# -*- coding: utf-8 -*-
"""Die Tests des MkPFS-Autors gegen unsere eingebettete Fassung.

**Wozu.** Unter ``MkPFS-1.0.0/mkpfs/`` liegt ein Quellauszug von MkPFS 1.0.0
(PSBrew, GPL-3.0) mit zwei bewussten Abweichungen und den Korrekturen, die
hier dazugekommen sind - ``MkPFS-1.0.0/UPSTREAM.md`` fuehrt sie einzeln auf.
Bis zum 06.09.2026 gab es keine Moeglichkeit zu pruefen, ob eine dieser
Aenderungen etwas bricht, das der Autor absichtlich so gebaut hat: Sein
Testbestand lag hier nicht.

Er liegt jetzt unter ``MkPFS-1.0.0/tests/`` und laeuft im Vollauf mit. Beim
naechsten Umstieg auf eine neuere Vorlage zeigt er sofort, was sich geaendert
hat - die Versionsnummer taugt dafuer nicht, sie bleibt ``1.0.0``.

**Erste Messung am 06.09.2026:** 459 Pruefungen, eine ausgelassen, ein
bekannter Fehlschlag (siehe unten). Alle vier Aenderungen dieses Projekts an
``exfat_writer.py`` und ``cli.py`` gehen durch.

**Was nicht mitkommt.** Drei der siebzehn Dateien der Vorlage verlangen
``pytest`` (``test_compression_backends``, ``test_compression_integration``,
``test_gather``). Der Testbestand dieses Projekts kommt ohne aus, und fuer
eine Abhaengigkeit reicht der Ertrag nicht: Die Ecke, die sie abdecken,
bewacht hier bereits ``test_mkpfs_fassung.py``. Die uebrigen vierzehn sind
reines ``unittest``.

**Warum die Ausgabe umgeleitet wird.** Die Vorlage-Tests schreiben viel auf
die Konsole, darunter Zeichen, die die Windows-Konsole in ihrer Vorgabe nicht
darstellen kann - dreizehn davon brachen daran ab, bevor sie ueberhaupt etwas
pruefen konnten. Unter ``pytest`` faellt das nicht auf, weil der die Ausgabe
ohnehin abfaengt.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
VORLAGE = PROJEKT / "MkPFS-1.0.0" / "tests"

# MkPFS-1.0.0 auf den Pfad, damit "import mkpfs" die eingebettete Fassung
# findet - dieselbe, die das Programm benutzt. Und den Testordner, weil die
# Dateien sich gegenseitig importieren ("from test_cli import ...").
for pfad in (PROJEKT / "MkPFS-1.0.0", VORLAGE):
    if str(pfad) not in sys.path:
        sys.path.insert(0, str(pfad))

# Ein Teil der Vorlage-Tests startet "python -m mkpfs" als Unterprozess.
# Der erbt sys.path nicht - im Baum des Autors lag mkpfs/ einfach im
# Arbeitsverzeichnis, hier eine Ebene tiefer. Ohne diese Zeile scheitert
# der Unterprozess mit Rueckgabewert 1, und der Test liest das als
# Programmfehler.
_ALT = os.environ.get("PYTHONPATH", "")
_NEU = str(PROJEKT / "MkPFS-1.0.0")
if _NEU not in _ALT.split(os.pathsep):
    os.environ["PYTHONPATH"] = (_NEU + os.pathsep + _ALT) if _ALT else _NEU

#: Diese eine Pruefung faellt hier aus einem Grund, der nichts mit dem
#: Programm zu tun hat: Sie vergleicht einen Pfad, den sie selbst ueber
#: ``tempfile`` erzeugt hat, mit dem Pfad in einer Fehlermeldung. Unter
#: Windows steht in dem einen der 8.3-Kurzname (``JBUSER~1``), im anderen
#: der ausgeschriebene. **Gemessen: Sie faellt genauso mit der
#: unveraenderten Vorlage** - also ist es die Umgebung, nicht unsere
#: Fassung. Auf einem Laeufer ohne Kurznamen laeuft sie durch.
AUSGELASSEN = {
    ("test_cli", "TestCliBatchRun",
     "test_batch_nonexistent_source_gives_clean_error"),
}


class _Papierkorb(io.TextIOBase):
    """Nimmt jede Ausgabe an und behaelt nichts davon.

    ``io.StringIO`` waere naheliegender, sammelt aber alles - und die
    Vorlage-Tests schreiben genug, dass daraus ein ``MemoryError`` wurde.
    Ausserdem gehen hier Zeichen durch, an denen die Windows-Konsole in
    ihrer Vorgabekodierung scheitert; dreizehn Tests brachen daran ab,
    bevor sie etwas pruefen konnten.
    """

    def write(self, text: str) -> int:      # noqa: D102
        return len(text)

    def writable(self) -> bool:             # noqa: D102
        return True


def _vorlagentests() -> unittest.TestSuite:
    """Sammelt die Tests der Vorlage, ohne die ausgelassenen."""
    lader = unittest.TestLoader()
    gefunden = lader.discover(str(VORLAGE), pattern="test_*.py",
                              top_level_dir=str(VORLAGE))
    behalten = unittest.TestSuite()

    def _durchgehen(sammlung):
        for teil in sammlung:
            if isinstance(teil, unittest.TestSuite):
                _durchgehen(teil)
                continue
            kennung = (type(teil).__module__, type(teil).__name__,
                       teil._testMethodName)
            if kennung not in AUSGELASSEN:
                behalten.addTest(teil)

    _durchgehen(gefunden)
    return behalten


class VorlageTests(unittest.TestCase):
    """Der Testbestand des Autors, gegen unsere Fassung gefahren."""

    def test_der_bestand_ist_da(self):
        """Ohne diese Pruefung saehe ein leerer Ordner wie Erfolg aus."""
        dateien = sorted(p.name for p in VORLAGE.glob("test_*.py"))
        self.assertGreaterEqual(len(dateien), 13,
                                "Vorlage-Tests fehlen: %s" % dateien)
        # Die beiden, die unsere Aenderungen vom 06.09.2026 abdecken.
        self.assertIn("test_exfat_writer.py", dateien)
        self.assertIn("test_cli.py", dateien)

    def test_die_fixtures_liegen_daneben(self):
        self.assertTrue((VORLAGE / "fixtures" / "tiny.exfat.gz").is_file())

    def test_sie_pruefen_unsere_eingebettete_fassung(self):
        """Nicht irgendein mkpfs aus site-packages."""
        import mkpfs
        self.assertEqual(
            (PROJEKT / "MkPFS-1.0.0" / "mkpfs").resolve(),
            Path(mkpfs.__file__).parent.resolve())

    def test_die_vorlage_laeuft_gegen_unsere_fassung(self):
        """Der eigentliche Lauf - 459 Pruefungen des Autors.

        Die Ausgabe wird verworfen: Sie ist umfangreich, und ein Teil
        davon laesst sich in der Windows-Konsole nicht darstellen.
        Fehlschlaege stehen trotzdem vollstaendig im Bericht - die sammelt
        das Ergebnis, nicht die Konsole.
        """
        suite = _vorlagentests()
        self.assertGreater(suite.countTestCases(), 400,
                           "Es wurden kaum Tests gefunden - stimmt der Pfad?")
        strom = io.StringIO()
        laeufer = unittest.TextTestRunner(stream=strom, verbosity=0)
        # In den Papierkorb, nicht in einen Puffer: Ein Vorlage-Test baut
        # ein grosses Abbild und schreibt dabei viel; gesammelt lief das in
        # einen MemoryError, und der stand dann im Bericht, als waere ein
        # Test des Autors fehlgeschlagen.
        with contextlib.redirect_stdout(_Papierkorb()), \
                contextlib.redirect_stderr(_Papierkorb()):
            ergebnis = laeufer.run(suite)
        if ergebnis.wasSuccessful():
            return
        bericht = []
        for fall, text in list(ergebnis.failures) + list(ergebnis.errors):
            bericht.append("%s\n%s" % (fall, text))
        self.fail(
            "%d von %d Pruefungen der Vorlage schlagen gegen unsere Fassung "
            "fehl. Das heisst: Eine Aenderung an MkPFS-1.0.0/mkpfs/ bricht "
            "etwas, das der Autor absichtlich so gebaut hat - oder die "
            "Vorlage unter MkPFS-1.0.0/tests/ ist neuer als der Quellauszug "
            "daneben.\n\n%s"
            % (len(ergebnis.failures) + len(ergebnis.errors),
               suite.countTestCases(), "\n\n".join(bericht)[:8000]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
