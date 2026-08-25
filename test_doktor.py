# -*- coding: utf-8 -*-
"""Die Umgebungsprüfung (`--doktor`).

Das Vorbild sind ``flutter doctor -v`` und ``npm doctor``: ein Befehl, der die
häufigen "bei mir läuft es, bei dir nicht"-Ursachen abklappert und ein
Ergebnis liefert, das sich in eine Fehlermeldung kopieren lässt.

Geprüft wird bewusst nicht das Übliche aus solchen Listen, sondern das, was
dieses Programm schon einmal umgeworfen hat:

* **Abgeschaltete lange Pfade.** Am 23.08.2026 meldete der PS4-Helfer "Paket
  verschlüsselt", obwohl das Paket in Ordnung war. Der wirkliche Grund war ein
  Pfad jenseits von 260 Zeichen.
* **Ein Zielordner auf FAT32.** Dort endet jede Datei bei 4 GB - und der
  Abbruch kommt erst nach Stunden.
* **Ein nicht beschreibbarer Temp-Ordner.**
* **Fehlende mitgelieferte Ordner**, seit sie neben dem Programm liegen statt
  darin.

Der Rückgabewert ist Teil der Zusage: 1 bei einem echten Fehler, sonst 0.
Sonst könnte kein Skript darauf reagieren.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class DoktorTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="doktor_")

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.ordner, ignore_errors=True)

    def pruefe(self, temp="", ziel=""):
        return self.haupt.umgebung_doktor(temp, ziel)

    # ── Der gesunde Fall ────────────────────────────────────────────────
    def test_ein_gesunder_ordner_ergibt_keinen_fehler(self) -> None:
        zeilen = self.pruefe(self.ordner, self.ordner)
        fehler = [z for z in zeilen if z.startswith(self.haupt.DOKTOR_FEHLER)]
        self.assertEqual(fehler, [])

    def test_es_wird_wirklich_etwas_geprueft(self) -> None:
        """Eine Prüfung mit null Punkten bestünde immer."""
        zeilen = self.pruefe(self.ordner, self.ordner)
        abschluss = [z for z in zeilen if z.startswith("Doktor:")]
        self.assertEqual(len(abschluss), 1)
        anzahl = int(abschluss[0].split()[1])
        self.assertGreaterEqual(anzahl, 8)

    def test_jede_zeile_traegt_eine_bewertung(self) -> None:
        marken = (self.haupt.DOKTOR_GUT, self.haupt.DOKTOR_HINWEIS,
                  self.haupt.DOKTOR_FEHLER, self.haupt.DOKTOR_EGAL)
        for zeile in self.pruefe(self.ordner, self.ordner):
            if not zeile or zeile.startswith(("Doktor:", "Nichts", "       ")):
                continue
            self.assertTrue(zeile.startswith(marken),
                            "ohne Bewertung: %r" % zeile)

    def test_die_bewertungen_sind_reines_ascii(self) -> None:
        """Der Bericht wird kopiert und weitergegeben - Sonderzeichen
        überleben das oft nicht."""
        for marke in (self.haupt.DOKTOR_GUT, self.haupt.DOKTOR_HINWEIS,
                      self.haupt.DOKTOR_FEHLER, self.haupt.DOKTOR_EGAL):
            marke.encode("ascii")

    # ── Die Fehlerfälle ─────────────────────────────────────────────────
    def test_ein_fehlender_ordner_ist_ein_fehler(self) -> None:
        zeilen = self.pruefe(os.path.join(self.ordner, "gibtsnicht"))
        self.assertTrue(any(z.startswith(self.haupt.DOKTOR_FEHLER)
                            and "gibt es nicht" in z for z in zeilen),
                        "%r" % (zeilen[:8],))

    def test_eine_datei_statt_eines_ordners_faellt_auf(self) -> None:
        pfad = os.path.join(self.ordner, "keine_ordner_sondern_datei")
        with open(pfad, "wb") as f:
            f.write(b"x")
        zeilen = self.pruefe(pfad)
        self.assertTrue(any(z.startswith(self.haupt.DOKTOR_FEHLER)
                            for z in zeilen))

    def test_kein_zielordner_ist_kein_fehler(self) -> None:
        """Beim Start ist noch keiner gewählt - das ist kein Mangel."""
        zeilen = self.pruefe(self.ordner, "")
        self.assertTrue(any(z.startswith(self.haupt.DOKTOR_EGAL)
                            and "Zielordner" in z for z in zeilen))

    def test_die_schreibprobe_bleibt_nicht_liegen(self) -> None:
        self.pruefe(self.ordner, self.ordner)
        reste = [n for n in os.listdir(self.ordner) if "doktor_probe" in n]
        self.assertEqual(reste, [])

    # ── Die einzelnen Prüfungen ─────────────────────────────────────────
    def test_lange_pfade_werfen_nie(self) -> None:
        ergebnis = self.haupt._doktor_lange_pfade()
        self.assertIn(ergebnis, (True, False, None))

    def test_dateisystem_wirft_nie(self) -> None:
        for pfad in ("", self.ordner, "Z:\\gibtsnicht", "\\\\?\\unfug"):
            self.assertIsInstance(self.haupt._doktor_dateisystem(pfad), str)

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_das_dateisystem_wird_erkannt(self) -> None:
        """Die Gegenprobe - sonst bestünde die Prüfung auch bei leerem Ergebnis."""
        self.assertNotEqual(self.haupt._doktor_dateisystem(self.ordner), "")

    def test_fat32_wird_als_fehler_behandelt(self) -> None:
        """Sich nicht nachstellen lässt sich nur der Datenträger, nicht die
        Regel: Auf FAT32 endet jede Datei bei 4 GB, und ein PS5-Dump ist
        immer größer."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("def umgebung_doktor")
        koerper = quelle[anfang:anfang + 9000]
        self.assertIn('"FAT32"', koerper)
        self.assertIn("DOKTOR_FEHLER", koerper)

    def test_der_doktor_geht_nicht_ins_netz(self) -> None:
        """Er läuft auch dann, wenn nichts erreichbar ist - und er darf
        ungefragt nichts übertragen."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("def umgebung_doktor")
        koerper = quelle[anfang:anfang + 9000]
        for verboten in ("urlopen", "requests.", "socket.", "ftplib"):
            self.assertNotIn(verboten, koerper)

    # ── Der Anschluss ───────────────────────────────────────────────────
    def test_der_abschnitt_haengt_im_bericht(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn("diagnostics.report_section_doctor", quelle)
        self.assertIn("def _diagnose_doktor", quelle)

    def test_die_uebersetzung_gibt_es_zweisprachig(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        eintrag = STRINGS["diagnostics.report_section_doctor"]
        self.assertIn("de", eintrag)
        self.assertIn("en", eintrag)

    def test_die_kommandozeile_kennt_beide_schreibweisen(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn('("--doktor", "--doctor")', quelle)

    def test_der_aufruf_liefert_null_bei_gesunder_umgebung(self) -> None:
        """Ende zu Ende - sonst sagt keiner dieser Tests, ob der Befehl läuft."""
        lauf = subprocess.run(
            [sys.executable, str(HAUPTDATEI), "--doktor", self.ordner, self.ordner],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300)
        self.assertEqual(lauf.returncode, 0, lauf.stdout[-2000:] + lauf.stderr[-2000:])
        self.assertIn("Doktor:", lauf.stdout)

    def test_der_aufruf_liefert_eins_bei_einem_fehler(self) -> None:
        """Ohne unterschiedliche Rückgabewerte könnte kein Skript reagieren."""
        lauf = subprocess.run(
            [sys.executable, str(HAUPTDATEI), "--doktor",
             os.path.join(self.ordner, "gibtsnicht")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300)
        self.assertEqual(lauf.returncode, 1, lauf.stdout[-2000:])


class _Verteilung:
    """Eine erfundene Paketverteilung für die Gegenprobe."""

    def __init__(self, name, version, requires=None):
        self.metadata = {"Name": name}
        self.version = version
        self.requires = requires or []


class PaketpruefungTests(unittest.TestCase):
    """Das Gegenstück zu ``pip check``.

    Der Fall, den das fängt: Ein Paket wird gehoben und zieht eine
    Abhängigkeit mit, die ein anderes Paket in dieser Fassung nicht verträgt.
    Beide sind installiert, beide lassen sich einlesen, und der Fehler zeigt
    sich erst an einer beliebigen späteren Stelle.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def _mit(self, verteilungen):
        from unittest import mock
        # Der Import steht in der Funktion, also greift das Ersetzen am
        # Ursprungsmodul.
        return mock.patch("importlib.metadata.distributions",
                          lambda: list(verteilungen))

    def test_ein_widerspruch_wird_gefunden(self) -> None:
        """Die Gegenprobe - sonst bestünde die Prüfung immer."""
        verteilungen = [
            _Verteilung("alpha", "1.0", ["beta>=2.0"]),
            _Verteilung("beta", "1.0"),
        ]
        with self._mit(verteilungen):
            pruefbar, treffer = self.haupt._doktor_abhaengigkeiten()
        self.assertTrue(pruefbar)
        self.assertEqual(len(treffer), 1, treffer)
        self.assertIn("beta", treffer[0])
        self.assertIn("1.0", treffer[0])

    def test_ein_fehlendes_paket_wird_gefunden(self) -> None:
        with self._mit([_Verteilung("alpha", "1.0", ["gammanichtda"])]):
            pruefbar, treffer = self.haupt._doktor_abhaengigkeiten()
        self.assertTrue(pruefbar)
        self.assertEqual(len(treffer), 1, treffer)
        self.assertIn("nicht installiert", treffer[0])

    def test_ein_sauberer_stand_meldet_nichts(self) -> None:
        verteilungen = [
            _Verteilung("alpha", "1.0", ["beta>=2.0"]),
            _Verteilung("beta", "2.5"),
        ]
        with self._mit(verteilungen):
            pruefbar, treffer = self.haupt._doktor_abhaengigkeiten()
        self.assertTrue(pruefbar)
        self.assertEqual(treffer, [])

    def test_bedingte_abhaengigkeiten_ergeben_keinen_fehlalarm(self) -> None:
        """Extras und Plattformbedingungen gelten hier nicht."""
        verteilungen = [
            _Verteilung("alpha", "1.0",
                        ['nurunterlinux>=1; sys_platform == "linux2"',
                         'nurmitextra>=1; extra == "test"']),
        ]
        with self._mit(verteilungen):
            pruefbar, treffer = self.haupt._doktor_abhaengigkeiten()
        self.assertTrue(pruefbar)
        self.assertEqual(treffer, [])

    def test_gross_und_kleinschreibung_stoert_nicht(self) -> None:
        """``Pillow`` heißt in Anforderungen mal ``pillow``, mal ``Pillow``."""
        verteilungen = [
            _Verteilung("Alpha_Paket", "1.0", ["Beta-Paket>=1.0"]),
            _Verteilung("beta_paket", "2.0"),
        ]
        with self._mit(verteilungen):
            pruefbar, treffer = self.haupt._doktor_abhaengigkeiten()
        self.assertEqual(treffer, [])

    def test_kaputte_daten_werfen_nicht(self) -> None:
        class Kaputt:
            metadata = {"Name": None}
            version = None
            requires = ["das ist keine anforderung ((("]
        with self._mit([Kaputt()]):
            pruefbar, treffer = self.haupt._doktor_abhaengigkeiten()
        self.assertIsInstance(treffer, list)

    def test_der_echte_stand_stimmt_mit_pip_check_ueberein(self) -> None:
        """An der laufenden Umgebung gemessen, nicht an erfundenen Daten."""
        pruefbar, treffer = self.haupt._doktor_abhaengigkeiten()
        if not pruefbar:
            self.skipTest("keine Paketverwaltung erreichbar")
        lauf = subprocess.run([sys.executable, "-m", "pip", "check"],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300)
        pip_sauber = lauf.returncode == 0
        self.assertEqual(pip_sauber, not treffer,
                         "pip check sagt %s, der Doktor meldet %r"
                         % ("sauber" if pip_sauber else "kaputt", treffer))

    def test_im_fenster_wird_nicht_gruendlich_geprueft(self) -> None:
        """Ein Fünftel einer Sekunde für etwas, das sich zwischen zwei
        Programmstarts nie ändert, wäre im Fenster spürbar."""
        zeilen = self.haupt.umgebung_doktor(tempfile.gettempdir(), "")
        self.assertFalse(any("Paketstände" in z for z in zeilen))

    def test_auf_der_kommandozeile_schon(self) -> None:
        zeilen = self.haupt.umgebung_doktor(tempfile.gettempdir(), "",
                                            gruendlich=True)
        self.assertTrue(any("Paketstände" in z for z in zeilen))


class StartprobeTests(unittest.TestCase):
    """Nur echte Programme dieser Plattform dürfen gestartet werden.

    Gemessen am 25.08.2026 in WSL: Auf einem eingehängten Windows-Laufwerk
    trägt **jede** Datei Modus 0777. Das Ausführungsrecht als Kennzeichen zu
    nehmen ließ dort ``LICENSE`` als Programm gelten, und die Startprobe
    meldete drei Fehler, die keine waren – in einer Prüfung, deren ganzer
    Zweck es ist, Fehlspuren zu vermeiden.

    Eine Windows-``.exe`` unter Linux zu starten ist ebenso sinnlos: Es kommt
    „Exec format error", was nach einem Defekt aussieht, wo nur die Plattform
    nicht passt.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="startprobe_")

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.ordner, ignore_errors=True)

    def datei(self, name, inhalt: bytes) -> str:
        pfad = os.path.join(self.ordner, name)
        with open(pfad, "wb") as f:
            f.write(inhalt + b"\x00" * 64)
        os.chmod(pfad, 0o777)
        return pfad

    def test_eine_textdatei_ist_kein_programm(self) -> None:
        """Der gemessene Fall: ``LICENSE`` galt als Programm."""
        pfad = self.datei("LICENSE", b"MIT License\n\nCopyright")
        self.assertFalse(self.haupt._doktor_ist_programm(pfad))

    def test_das_ausfuehrungsrecht_allein_genuegt_nicht(self) -> None:
        pfad = self.datei("pruefsummen.json", b'{"a": 1}')
        self.assertTrue(os.access(pfad, os.X_OK) or sys.platform == "win32")
        self.assertFalse(self.haupt._doktor_ist_programm(pfad))

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_windows_erkennt_eine_exe(self) -> None:
        self.assertTrue(self.haupt._doktor_ist_programm(
            self.datei("echt.exe", b"MZ\x90\x00")))

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_windows_faellt_nicht_auf_eine_elf_herein(self) -> None:
        """Die mitgelieferten Linux- und macOS-Programme liegen daneben."""
        self.assertFalse(self.haupt._doktor_ist_programm(
            self.datei("UFS2Tool", b"\x7fELF\x02\x01\x01")))

    @unittest.skipIf(sys.platform in ("win32", "darwin"), "nur unter Linux")
    def test_linux_erkennt_eine_elf(self) -> None:
        self.assertTrue(self.haupt._doktor_ist_programm(
            self.datei("UFS2Tool", b"\x7fELF\x02\x01\x01")))

    @unittest.skipIf(sys.platform in ("win32", "darwin"), "nur unter Linux")
    def test_linux_faellt_nicht_auf_eine_exe_herein(self) -> None:
        """Sonst kommt „Exec format error" und sieht nach einem Defekt aus."""
        self.assertFalse(self.haupt._doktor_ist_programm(
            self.datei("ps4_pkg_extract.exe", b"MZ\x90\x00")))

    def test_eine_fehlende_datei_wirft_nicht(self) -> None:
        self.assertFalse(self.haupt._doktor_ist_programm(
            os.path.join(self.ordner, "gibtsnicht")))

    def test_ein_ordner_wirft_nicht(self) -> None:
        self.assertFalse(self.haupt._doktor_ist_programm(self.ordner))

    def test_eine_leere_datei_wirft_nicht(self) -> None:
        pfad = os.path.join(self.ordner, "leer")
        open(pfad, "wb").close()
        self.assertFalse(self.haupt._doktor_ist_programm(pfad))

    def test_die_auswahl_haengt_nicht_mehr_am_ausfuehrungsrecht(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("def _doktor_werkzeuge_starten")
        koerper = quelle[anfang:anfang + 3000]
        self.assertNotIn("os.X_OK", koerper)
        self.assertIn("_doktor_ist_programm", koerper)

    def test_die_startprobe_meldet_hier_nichts(self) -> None:
        """An den echten mitgelieferten Programmen, nicht an erfundenen."""
        befunde, _rechte = self.haupt._doktor_werkzeuge_starten()
        kaputt = [(n, b) for n, b in befunde if b]
        self.assertEqual(kaputt, [], "Fehlalarm: %r" % (kaputt,))


if __name__ == "__main__":
    unittest.main(verbosity=2)
