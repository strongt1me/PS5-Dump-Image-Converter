# -*- coding: utf-8 -*-
"""Prueft den Werkzeugbestand - und die Falle, die er beinahe wurde.

Einundzwanzigster Schnitt. ``_bestandteile_sammeln`` zog aus der
Tk-Klasse in ``diagnose_befund.Diagnosebericht``.

Dabei wartete eine Namenskollision: Der Konstruktor des
``Diagnosebericht`` wies bis dahin **unbedingt** ein Instanzattribut
gleichen Namens zu (``self._bestandteile_sammeln = ... or (lambda *a:
[])``). Eine Methode desselben Namens waere davon in jedem Fall
verdeckt worden, mit zwei moeglichen Ausgaengen:

* Reicht der Monolith nichts mehr herein, greift die Vorgabe, der
  verschobene Rumpf laeuft **nie**, und der Bericht meldet einen
  leeren Werkzeugbestand. Still.
* Reicht er weiter ``self._bestandteile_sammeln`` herein, zeigt das
  Attribut auf die neue Weiterleitung - und die ruft ueber den Bericht
  sich selbst. **Unbegrenzte Rekursion**, deren ``RecursionError`` an
  beiden Aufrufstellen von einem ``except Exception`` verschluckt wird
  und nur als "Aktualisierungspruefung fehlgeschlagen" erscheint.

Beide Ausgaenge werden hier ausgefuehrt, nicht beschrieben.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from ps5_validator.utils.diagnose_befund import Diagnosebericht


class SammelnTests(unittest.TestCase):
    def test_ohne_werte_kommt_eine_leere_liste(self) -> None:
        self.assertEqual(Diagnosebericht()._bestandteile_sammeln(), [])

    def test_eingebettete_werkzeuge_erscheinen(self) -> None:
        bericht = Diagnosebericht(
            eingebettete_werkzeuge=(("mkpfs", "mkpfs.exe", "art", "quelle"),),
            eingebettete_fassung=lambda _d: "0.0.9")
        teile = bericht._bestandteile_sammeln()
        self.assertEqual(len(teile), 1)
        self.assertEqual(teile[0].name, "mkpfs")
        self.assertEqual(teile[0].fassung, "0.0.9")

    def test_eine_unbekannte_fassung_wird_benannt(self) -> None:
        bericht = Diagnosebericht(
            eingebettete_werkzeuge=(("mkpfs", "mkpfs.exe", "art", "quelle"),),
            eingebettete_fassung=lambda _d: "")
        self.assertEqual(
            bericht._bestandteile_sammeln()[0].fassung, "unbekannt")

    def test_die_ampr_fassung_kommt_dazu(self) -> None:
        bericht = Diagnosebericht(ampr_hoechste_fassung=lambda: "0.3.5.1")
        namen = [t.name for t in bericht._bestandteile_sammeln()]
        self.assertIn("AMPR EMU", namen)

    def test_ohne_ampr_fassung_steht_nichts_da(self) -> None:
        bericht = Diagnosebericht(ampr_hoechste_fassung=lambda: "")
        namen = [t.name for t in bericht._bestandteile_sammeln()]
        self.assertNotIn("AMPR EMU", namen)

    def test_fremdwerkzeuge_kommen_aus_der_einstellung(self) -> None:
        bericht = Diagnosebericht(
            einstellung_lesen=lambda s, v="": (
                "C:/FileZilla/filezilla.exe" if s == "filezilla_path" else ""),
            datei_fassung=lambda _p: "3.66.1",
            fremdwerkzeuge_quellen={"filezilla_path": "filezilla-project.org"})
        teile = {t.name: t for t in bericht._bestandteile_sammeln()}
        self.assertIn("FileZilla", teile)
        self.assertEqual(teile["FileZilla"].fassung, "3.66.1")
        self.assertNotIn("OSFMount", teile,
                         "Ein nicht eingestelltes Werkzeug wurde gemeldet.")

    def test_ein_werkzeug_ohne_fassung_gilt_als_gefunden(self) -> None:
        bericht = Diagnosebericht(
            einstellung_lesen=lambda s, v="": (
                "C:/x.exe" if s == "osfmount_path" else ""),
            datei_fassung=lambda _p: "")
        teile = {t.name: t for t in bericht._bestandteile_sammeln()}
        self.assertEqual(teile["OSFMount"].fassung, "gefunden")

    def test_eine_werfende_einstellung_haelt_nichts_auf(self) -> None:
        def _wirft(*_a, **_k):
            raise RuntimeError("Datei belegt")

        bericht = Diagnosebericht(
            einstellung_lesen=_wirft,
            ampr_hoechste_fassung=lambda: "0.3.5")
        namen = [t.name for t in bericht._bestandteile_sammeln()]
        self.assertIn("AMPR EMU", namen,
                      "Ein Fehler beim Lesen der Einstellung hat den "
                      "ganzen Bestand gekostet.")


class KollisionTests(unittest.TestCase):
    """Die Falle selbst - beide Ausgaenge ausgefuehrt."""

    def test_der_konstruktor_kennt_den_alten_rueckruf_nicht_mehr(self) -> None:
        """Er haette die Methode gleichen Namens verdeckt."""
        import inspect

        namen = list(inspect.signature(Diagnosebericht.__init__).parameters)
        self.assertNotIn(
            "bestandteile_sammeln", namen,
            "Der Parameter ist zurueck. Er wuerde die Methode gleichen "
            "Namens verdecken - entweder laeuft ihr Rumpf nie, oder die "
            "Weiterleitung des Monolithen ruft sich selbst.")

    def test_das_attribut_verdeckt_die_methode_nicht(self) -> None:
        """Ausgang eins: der Rumpf liefe nie."""
        bericht = Diagnosebericht(
            eingebettete_werkzeuge=(("A", "a.exe", "art", "q"),),
            eingebettete_fassung=lambda _d: "1.0")
        self.assertTrue(callable(bericht._bestandteile_sammeln))
        self.assertEqual(len(bericht._bestandteile_sammeln()), 1,
                         "Der Rumpf lief nicht - da verdeckt etwas die "
                         "Methode.")

    def test_die_kollision_wuerde_sich_selbst_rufen(self) -> None:
        """Ausgang zwei: die Rekursion - hier wirklich ausgeloest.

        Diese Pruefung baut die Falle nach, statt sie zu beschreiben:
        Ein Bericht bekommt ein Instanzattribut, das auf einen Aufruf
        seiner selbst zeigt. Wer den Konstruktorparameter je wieder
        einfuehrt, baut genau das - und der RecursionError wird an
        beiden echten Aufrufstellen von einem ``except Exception``
        verschluckt.
        """
        bericht = Diagnosebericht()
        bericht._bestandteile_sammeln = (          # type: ignore[method-assign]
            lambda: bericht._bestandteile_sammeln())
        with self.assertRaises(RecursionError):
            bericht._bestandteile_sammeln()

    def test_der_monolith_reicht_den_alten_rueckruf_nicht_mehr(self) -> None:
        """Die zweite Haelfte der Kopplung - ohne sie nuetzt die erste
        nichts."""
        quelle = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        self.assertFalse(
            'bestandteile_sammeln=getattr(self, "_bestandteile_sammeln"'
            in quelle,
            "Der Monolith reicht den Rueckruf wieder herein - das ist die "
            "Rekursion.")


class MonolithTests(unittest.TestCase):
    def test_die_drei_tabellen_bleiben_an_der_klasse(self) -> None:
        """Pruefungen lesen sie dort - test_protokoll_und_mausrad etwa."""
        import PS5ImageConverter_Pro_FINAL_revised as APP

        for name in ("_EINGEBETTETE_WERKZEUGE", "_GEPRUEFTE_BIBLIOTHEKEN",
                     "_FREMDWERKZEUGE_QUELLEN"):
            with self.subTest(tabelle=name):
                self.assertTrue(hasattr(APP.PS5ConverterGUI, name))

    def test_der_bauer_greift_nirgends_unmittelbar_zu(self) -> None:
        """Der Bericht darf von der Oberflaeche nichts brauchen.

        test_fortschrittsbalken baut Traeger, die nur die eine
        Pruefung kennen - und haelt damit fest, dass der Bericht auch
        in der EXE laeuft, wo es die Oberflaeche noch nicht gibt. Ein
        unmittelbares ``self._X`` im Bauer bricht das mit einem
        AttributeError.

        Dieser Fehler ist beim Bau von Schnitt 21 zum zweiten Mal
        passiert - sieben neue Werte gingen unmittelbar zu, und zehn
        Pruefungen fielen. Deshalb wacht hier jetzt der Baum darueber
        statt nur ein Kommentar.
        """
        import ast

        quelle = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        klasse = next(k for k in ast.walk(ast.parse(quelle))
                      if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")
        bauer = next(m for m in klasse.body
                     if isinstance(m, ast.FunctionDef)
                     and m.name == "_diagnosebericht")
        ruf = next(c for c in ast.walk(bauer)
                   if isinstance(c, ast.Call)
                   and getattr(c.func, "attr", "") == "Diagnosebericht")
        unmittelbar = [
            kw.arg for kw in ruf.keywords
            if isinstance(kw.value, ast.Attribute)
            and isinstance(kw.value.value, ast.Name)
            and kw.value.value.id == "self"]
        self.assertEqual(
            unmittelbar, [],
            "Diese Werte gehen unmittelbar an self: %s. Sie muessen "
            "ueber getattr(self, ..., Vorgabe) kommen, sonst bricht "
            "jeder Traeger, der sie nicht hat." % unmittelbar)

    def test_die_weiterleitung_ist_duenn(self) -> None:
        import ast

        quelle = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        klasse = next(k for k in ast.walk(ast.parse(quelle))
                      if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")
        methode = next(m for m in klasse.body
                       if isinstance(m, ast.FunctionDef)
                       and m.name == "_bestandteile_sammeln")
        self.assertLess(methode.end_lineno - methode.lineno + 1, 8)


if __name__ == "__main__":
    unittest.main()
