"""Tests für den Status UNGEPRÜFT im Validator.

Bis v1.9.0 kannte der Validator nur „in Ordnung" und „beanstandet". Fehlten
Administratorrechte, kam UFS2Tool nicht an ein `.ffpkg` heran (``WinError
740``) – und der Bericht sagte **FAILED**, obwohl gar nichts angesehen worden
war. In zwei vollen Testrunden ist das jedes Mal aufgefallen: Ein
einwandfreies Abbild las sich wie ein beschädigtes.

Seit v1.9.1 gibt es dafür ``SKIPPED``. Der Unterschied ist keine
Formulierungsfrage:

* **FAILED** heißt: Es wurde etwas gefunden.
* **SKIPPED** heißt: Es wurde nichts angesehen.

Geprüft wird hier, dass beides auseinandergehalten wird – und dass ein
*echter* Startfehler weiterhin als Fehler durchgeht. Sonst hätte man den
einen Irrtum durch den anderen ersetzt.
"""
from __future__ import annotations

import errno
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.core.validator_base import ValidationResult
from ps5_validator.modules import ffpkg_validator as modul
from ps5_validator.utils.i18n import STRINGS


class StatusmodellTests(unittest.TestCase):
    """Was ``set_skipped`` tut – und was es bewusst nicht tut."""

    def test_setzt_den_status(self) -> None:
        r = ValidationResult(mode="ffpkg")
        r.set_skipped("keine Rechte")
        self.assertEqual(r.status, "SKIPPED")
        self.assertIn("keine Rechte", r.errors)
        self.assertFalse(r.wurde_geprueft)

    def test_ohne_meldung_geht_auch(self) -> None:
        r = ValidationResult(mode="ffpkg")
        r.set_skipped()
        self.assertEqual(r.status, "SKIPPED")
        self.assertEqual(r.errors, [])

    def test_ein_gefaelltes_urteil_wird_nicht_ueberschrieben(self) -> None:
        """Wer schon etwas gefunden hat, hat auch etwas gesehen.

        Ohne diese Regel könnte ein später auftretender Rechtefehler einen
        bereits erkannten Schaden verdecken – aus „beschädigt" würde
        „ungeprüft", und der Befund wäre weg.
        """
        for vorher, setzen in (("CORRUPTED", "set_corrupted"),
                               ("FAILED", "set_failed"),
                               ("MISSING", "set_missing")):
            with self.subTest(vorher=vorher):
                r = ValidationResult(mode="ffpkg")
                getattr(r, setzen)("Befund")
                r.set_skipped("und dann fehlten Rechte")
                self.assertEqual(r.status, vorher,
                                 "Der Befund wurde von SKIPPED verdeckt")

    def test_eine_warnung_darf_weichen(self) -> None:
        """Eine Warnung ist noch kein Urteil über die Datei."""
        r = ValidationResult(mode="ffpkg")
        r.add_error("Kleinigkeit")
        self.assertEqual(r.status, "WARNING")
        r.set_skipped("keine Rechte")
        self.assertEqual(r.status, "SKIPPED")

    def test_geprueft_ist_alles_ausser_skipped(self) -> None:
        for status in ("OK", "WARNING", "FAILED", "CORRUPTED", "MISSING"):
            with self.subTest(status=status):
                r = ValidationResult(mode="ffpkg", status=status)
                self.assertTrue(r.wurde_geprueft)


class RechtefehlerTests(unittest.TestCase):
    """Welcher Fehler als „nur Rechte" gilt – und welcher nicht."""

    def test_windows_meldet_740(self) -> None:
        fehler = OSError("erhöhte Rechte nötig")
        fehler.winerror = 740
        self.assertTrue(modul._braucht_rechte(fehler))

    def test_permissionerror_zaehlt(self) -> None:
        self.assertTrue(modul._braucht_rechte(PermissionError("verboten")))

    def test_eacces_und_eperm(self) -> None:
        for nummer in (errno.EACCES, errno.EPERM):
            with self.subTest(errno=nummer):
                fehler = OSError(nummer, "keine Berechtigung")
                self.assertTrue(modul._braucht_rechte(fehler))

    def test_alles_andere_bleibt_ein_fehler(self) -> None:
        """Der Gegentest – sonst würde jeder Startfehler geschluckt.

        ``ENOENT`` (Werkzeug fehlt) und ein ``ValueError`` aus dem Bau der
        Befehlszeile sind echte Fehler und müssen als solche durchgehen.
        """
        andere = [
            OSError(errno.ENOENT, "nicht gefunden"),
            ValueError("Befehlszeile unbrauchbar"),
            OSError("irgendwas"),
        ]
        winfehler = OSError("anderer Windows-Fehler")
        winfehler.winerror = 5
        andere.append(winfehler)
        for fehler in andere:
            with self.subTest(fehler=type(fehler).__name__):
                self.assertFalse(modul._braucht_rechte(fehler))


class _Werkzeug:
    """Ersatz für UFS2Tool, das beim Start eine bestimmte Ausnahme wirft."""

    def __init__(self, fehler: BaseException) -> None:
        self.fehler = fehler

    def __call__(self, *_a, **_k):
        raise self.fehler


class ValidierungslaufTests(unittest.TestCase):
    """Der ganze Weg: Ausnahme rein, Status raus."""

    def setUp(self) -> None:
        import tempfile
        self._ordner = tempfile.TemporaryDirectory(prefix="ffpkg_")
        self.abbild = Path(self._ordner.name) / "spiel.ffpkg"
        self.abbild.write_bytes(b"\x00" * 4096)
        self.werkzeug = Path(self._ordner.name) / "UFS2Tool.exe"
        self.werkzeug.write_bytes(b"MZ")
        self.addCleanup(self._ordner.cleanup)

    def _lauf(self, fehler: BaseException):
        prueferin = modul.FfpkgValidator(str(self.werkzeug))
        prueferin._run_tool = _Werkzeug(fehler)
        return prueferin.validate(str(self.abbild))

    def test_fehlende_rechte_ergeben_ungeprueft(self) -> None:
        fehler = OSError("erhöhte Rechte nötig")
        fehler.winerror = 740
        ergebnis = self._lauf(fehler)
        self.assertEqual(ergebnis.status, "SKIPPED")
        self.assertFalse(ergebnis.wurde_geprueft)
        self.assertTrue(any("Administratorrechte" in f
                            for f in ergebnis.errors), ergebnis.errors)

    def test_ein_echter_startfehler_bleibt_ein_fehler(self) -> None:
        ergebnis = self._lauf(OSError(errno.ENOENT, "nicht gefunden"))
        self.assertEqual(ergebnis.status, "FAILED")
        self.assertTrue(ergebnis.wurde_geprueft)

    def test_fehlendes_werkzeug_bleibt_ein_fehler(self) -> None:
        """Ein nicht vorhandenes UFS2Tool ist kein Rechteproblem."""
        prueferin = modul.FfpkgValidator(
            str(Path(self._ordner.name) / "gibtesnicht.exe"))
        ergebnis = prueferin.validate(str(self.abbild))
        self.assertEqual(ergebnis.status, "FAILED")

    def test_leere_datei_bleibt_beschaedigt(self) -> None:
        leer = Path(self._ordner.name) / "leer.ffpkg"
        leer.write_bytes(b"")
        prueferin = modul.FfpkgValidator(str(self.werkzeug))
        self.assertEqual(prueferin.validate(str(leer)).status, "CORRUPTED")


class TexteTests(unittest.TestCase):
    """Der Hinweis muss sagen, was zu tun ist."""

    def test_zweisprachig(self) -> None:
        eintrag = STRINGS["log.manual.result_skipped"]
        self.assertTrue(eintrag.get("de"))
        self.assertTrue(eintrag.get("en"))

    def test_nennt_die_ursache_und_den_ausweg(self) -> None:
        de = STRINGS["log.manual.result_skipped"]["de"]
        self.assertIn("UNGEPRÜFT", de)
        self.assertIn("Administrator", de)
        self.assertIn("kein", de.lower())

    def test_endet_mit_umbruch(self) -> None:
        """Alle Protokolltexte tun das - sonst klebt die nächste Zeile an."""
        for fassung in STRINGS["log.manual.result_skipped"].values():
            self.assertTrue(fassung.endswith("\n"))


class VerdrahtungTests(unittest.TestCase):
    """Dass der neue Status in der Oberfläche und im CLI ankommt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
                      ).read_text(encoding="utf-8")

    def test_alle_auswertungen_kennen_skipped(self) -> None:
        """Vier Zweige (Ordner, exFAT, ffpfsc, ffpkg) werten den Status aus."""
        self.assertEqual(
            self.quelle.count('result.status in ("OK", "WARNING", "SKIPPED")'), 4)
        self.assertNotIn('result.status in ("OK", "WARNING")', self.quelle,
                         "Ein Zweig kennt SKIPPED noch nicht")

    def test_eigener_abschlusssatz(self) -> None:
        self.assertIn('log.manual.result_skipped', self.quelle)

    def test_cli_hat_einen_eigenen_rueckgabewert(self) -> None:
        """Weder 0 noch 1 - beides wäre eine falsche Aussage."""
        self.assertIn('_last_validation_status', self.quelle)
        self.assertIn("return 4", self.quelle)

    def test_die_schlusszeile_sagt_nicht_erfolg(self) -> None:
        """Sie kommt aus dem gemeinsamen Abschluss aller Aufgaben.

        Bis v1.9.1 stand dort auch bei einem übersprungenen Lauf
        „Erfolgreich abgeschlossen" – der Ergebnisblock darüber sagte etwas
        anderes als die Statuszeile darunter. Statt den Abschluss umzubauen,
        wechselt jetzt nur die Stufe.
        """
        self.assertIn('_completion_status_text(mode, _stufe)', self.quelle)
        self.assertIn('"skipped"', self.quelle)
        for schluessel in ("status.completion.default.skipped",
                           "status.completion.container.skipped"):
            with self.subTest(schluessel):
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))
                self.assertNotIn("rfolg", STRINGS[schluessel]["de"],
                                 "Die Zeile behauptet weiter einen Erfolg")

    def test_der_status_wird_vor_jedem_lauf_geloescht(self) -> None:
        """Sonst erbte der nächste Lauf das „ungeprüft" des vorigen."""
        self.assertIn('self._last_validation_status = ""', self.quelle)

    def test_skipped_ist_eine_zulaessige_stufe(self) -> None:
        self.assertIn('"verify_failed", "done", "skipped", "keepalive_verify"',
                      self.quelle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
