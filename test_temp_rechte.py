# -*- coding: utf-8 -*-
"""Ein Temp-Ordner darf dem Anwender nicht den Zugriff nehmen.

Ein Anwender meldete am 04.09.2026: Der entpackte Dump lag vollstaendig da,
das Protokoll stimmte, aber der Explorer zeigte statt der erwarteten Groesse
nur ein paar hundert Megabyte. Ursache war kein Entpackfehler - er kam an die
Unterordner nicht heran.

**Die Kette:**

1. ``_mkdtemp`` legte den Staging-Ordner mit ``tempfile.mkdtemp`` an. Das
   benutzt Modus ``0o700``; Python uebersetzt ihn unter Windows in eine
   **ausdrueckliche** Rechteliste und schaltet die Vererbung ab. Uebrig
   bleiben ``SYSTEM``, ``Administratoren`` und ``EIGENTUEMERRECHTE`` - der
   angemeldete Anwender steht namentlich nicht mehr drin.
2. Die Eintraege tragen ``(OI)(CI)``, erben also an jede Datei und jeden
   Unterordner darin weiter.
3. ``_move_tree_into`` verschiebt den Inhalt an den Zielort. Windows vererbt
   nur beim **Kopieren** neu - ein ``rename`` nimmt die Rechte mit. Und der
   Staging-Ordner entsteht mit ``dir_path=dst`` im Zielordner, es ist also
   immer dasselbe Laufwerk.

**Warum es beim Entwickeln nie auffiel:** Nicht eleviert ist der Besitzer der
Anwender selbst, ``EIGENTUEMERRECHTE`` meint also ihn. Das Programm laeuft
aber eleviert - dann gehoert der Ordner der Gruppe *Administratoren*, und der
Anwender hat nichts mehr.

Geprueft wird deshalb die **Eigenschaft**, nicht der Wortlaut: Wer auf den
Zielordner zugreifen darf, muss auch auf den darin angelegten Temp-Ordner
zugreifen duerfen.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP  # noqa: E402

G = APP.PS5ConverterGUI


def _kennungen(pfad: str) -> set[str]:
    """Die Kennungen aus der Rechteliste eines Ordners.

    Ueber ``icacls``, weil es das einzige Mittel ist, das ohne
    Zusatzpakete auskommt und genau das zeigt, was der Explorer auch sieht.
    """
    lauf = subprocess.run(["icacls", pfad], capture_output=True, text=True,
                          encoding="oem", errors="replace")
    raus = set()
    for zeile in lauf.stdout.splitlines():
        for treffer in re.finditer(r"([^\s:]+(?:\\[^\s:]+)?):\(", zeile):
            name = treffer.group(1).strip()
            if name and not name.lower().endswith(".txt"):
                raus.add(name.split("\\")[-1].upper())
    return raus


class _NurWindows(unittest.TestCase):
    def setUp(self) -> None:
        if os.name != "nt":
            self.skipTest("Rechtelisten gibt es so nur unter Windows.")


class VererbungTests(_NurWindows):
    """Der Kern: Der Temp-Ordner muss die Rechte des Zielordners erben."""

    def setUp(self) -> None:
        super().setUp()
        # Der Aufbau darf **nicht** selbst aus mkdtemp stammen - sonst traegt
        # schon der Elternordner die enge Liste, und die Messung zeigt
        # zweimal dasselbe. Beim Schreiben dieser Datei genau so passiert.
        self.basis = os.path.join(os.path.expanduser("~"),
                                  "ps5conv_rechteprobe")
        if os.path.isdir(self.basis):
            import shutil
            shutil.rmtree(self.basis, ignore_errors=True)
        os.makedirs(self.basis)
        self.ziel = os.path.join(self.basis, "Ziel")
        os.mkdir(self.ziel)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(getattr(self, "basis", ""), ignore_errors=True)

    def test_wer_ans_ziel_darf_darf_auch_in_den_temp_ordner(self) -> None:
        temp = G._temp_ordner_anlegen("probe_", self.ziel)
        fehlend = _kennungen(self.ziel) - _kennungen(temp)
        self.assertEqual(
            set(), fehlend,
            "Diese Kennungen verlieren den Zugriff: %s" % sorted(fehlend))

    def test_auch_ein_unterordner_darin(self) -> None:
        """Der eigentliche Schaden - die entpackten Ordner liegen eine Ebene tiefer."""
        temp = G._temp_ordner_anlegen("probe_", self.ziel)
        unter = os.path.join(temp, "ac2")
        os.mkdir(unter)
        fehlend = _kennungen(self.ziel) - _kennungen(unter)
        self.assertEqual(
            set(), fehlend,
            "Im Unterordner fehlen: %s" % sorted(fehlend))

    def test_die_gegenprobe_mit_mkdtemp_faellt(self) -> None:
        """Ohne sie waere nicht belegt, dass die Pruefung oben etwas misst.

        ``tempfile.mkdtemp`` ist der alte Weg. Er **muss** hier auffallen -
        sonst pruefte die Messung nur, dass zwei gleiche Ordner gleich sind.
        """
        alt = tempfile.mkdtemp(prefix="alt_", dir=self.ziel)
        fehlend = _kennungen(self.ziel) - _kennungen(alt)
        self.assertNotEqual(
            set(), fehlend,
            "mkdtemp verhaelt sich unerwartet - dann sagt der Test oben nichts.")


class AnlageTests(unittest.TestCase):
    """Plattformunabhaengig: was die Methode tut, nicht was Windows daraus macht."""

    def setUp(self) -> None:
        self.basis = tempfile.mkdtemp(prefix="ps5conv_anlage_")

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.basis, ignore_errors=True)

    def test_der_ordner_entsteht_und_traegt_den_namensanfang(self) -> None:
        p = G._temp_ordner_anlegen("ps5conv_probe_", self.basis)
        self.assertTrue(os.path.isdir(p))
        self.assertTrue(os.path.basename(p).startswith("ps5conv_probe_"))

    def test_zwei_aufrufe_geben_zwei_ordner(self) -> None:
        a = G._temp_ordner_anlegen("x_", self.basis)
        b = G._temp_ordner_anlegen("x_", self.basis)
        self.assertNotEqual(a, b)

    def test_ohne_rechtemodus_angelegt(self) -> None:
        """Der Modus ist die ganze Ursache - er darf nicht zurueckkehren.

        ``os.mkdir(pfad, 0o700)`` schaltet unter Windows die Vererbung ab,
        ``os.mkdir(pfad)`` nicht. Ein zweites Argument waere also ein
        Rueckfall in genau den gemeldeten Fehler.
        """
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        baum = ast.parse(quelle)
        klasse = next(k for k in baum.body if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")
        methode = next(m for m in klasse.body
                       if isinstance(m, ast.FunctionDef)
                       and m.name == "_temp_ordner_anlegen")
        rufe = [k for k in ast.walk(methode) if isinstance(k, ast.Call)
                and ast.unparse(k.func).endswith("mkdir")]
        self.assertTrue(rufe, "Kein mkdir-Aufruf gefunden.")
        for k in rufe:
            self.assertEqual(1, len(k.args),
                             "mkdir mit Rechtemodus: %s" % ast.unparse(k))

    def test_mkdtemp_wird_dafuer_nicht_mehr_benutzt(self) -> None:
        """``_mkdtemp`` muss die neue Anlage rufen, nicht die alte."""
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        baum = ast.parse(quelle)
        klasse = next(k for k in baum.body if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")
        methode = next(m for m in klasse.body
                       if isinstance(m, ast.FunctionDef) and m.name == "_mkdtemp")
        text = ast.unparse(methode)
        self.assertIn("_temp_ordner_anlegen", text)
        self.assertNotIn("tempfile.mkdtemp", text,
                         "_mkdtemp legt wieder mit tempfile.mkdtemp an.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
