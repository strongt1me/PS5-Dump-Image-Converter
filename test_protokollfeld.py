"""Tests fuer die Fortschrittszeilen im Protokollfeld.

Die Engine mischt Text und Fortschrittsbalken:

    Writing PFS image to ...\\r[####] 72% write\\n

Der Leser der Unterprozess-Ausgabe suchte frueher **erst** nach ``\\n`` und
danach nach ``\\r``. Damit wurde alles bis zum ``\\n`` als EINE Zeile genommen -
mit eingebettetem ``\\r``. Im Feld klebten Text und Balken aneinander:

    Writing PFS image to ...[####################---------]  72% write @ 106 MB/s

Daraus folgte auch das Stapeln: Eine solche Zeile beginnt nicht mit ``[``, gilt
also nicht als Balkenzeile. Der Merker "die letzte war ein Balken" wurde dadurch
staendig zurueckgesetzt, und die naechste echte Balkenzeile wurde angehaengt
statt die vorige zu ersetzen.

Getrennt wird jetzt am zuerst auftretenden Zeilenende.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP

QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
K = APP.PS5ConverterGUI


def _blank():
    return K.__new__(K)


def _zerlegen(bloecke: list[str]) -> list[str]:
    """Bildet den Zeilentrenner des Ausgabelesers nach."""
    puffer = ""
    zeilen: list[str] = []
    for text in bloecke:
        puffer += text
        while True:
            stellen = [i for i in (puffer.find("\n"), puffer.find("\r")) if i >= 0]
            if not stellen:
                break
            idx = min(stellen)
            zeile = puffer[:idx].strip()
            puffer = puffer[idx + 1:]
            if zeile:
                zeilen.append(zeile)
    return zeilen


class ZeilentrennerTests(unittest.TestCase):
    def test_text_und_balken_werden_getrennt(self):
        """Der Fall aus der Bildschirmaufnahme."""
        block = "Writing PFS image to E:\\tmp\\pfs_image.dat...\r[####----]  72% write\n"
        zeilen = _zerlegen([block])
        self.assertEqual(len(zeilen), 2)
        self.assertTrue(zeilen[0].startswith("Writing PFS image"))
        self.assertTrue(zeilen[1].startswith("["))

    def test_mehrere_balken_in_einem_block(self):
        block = "\r[#---]  10% write\r[##--]  20% write\r[###-]  30% write\n"
        self.assertEqual(len(_zerlegen([block])), 3)

    def test_ueber_blockgrenzen_hinweg(self):
        zeilen = _zerlegen(["Uncompressed size: 248.85 MB", "\r[##--]  49% compress\n"])
        self.assertEqual(len(zeilen), 2)
        self.assertTrue(zeilen[0].startswith("Uncompressed size"))

    def test_reine_textzeilen_bleiben_ganz(self):
        self.assertEqual(_zerlegen(["Build Summary\nInput path: D:\\x\n"]),
                         ["Build Summary", "Input path: D:\\x"])

    def test_quelltext_trennt_am_ersten_zeilenende(self):
        """Gegenprobe am Programm selbst - nicht nur an der Nachbildung."""
        text = QUELLE.read_text(encoding="utf-8")
        stelle = text.index("def write(self, text: str) -> int:")
        block = text[stelle:stelle + 1200]
        self.assertIn("min(stellen)", block)
        self.assertNotIn('for sep in ("\\n", "\\r")', block)


class BalkenerkennungTests(unittest.TestCase):
    ECHT = [
        "[################################] 100% scan",
        "[##############################--]  96% write @ 32.94 MB/s ETA 1s",
        "[#############-------------------]  48% compress @ 28.74 MB/s ETA 00:20",
        "[--------------------------------]   0% read",
    ]

    def test_echte_balkenzeilen_werden_erkannt(self):
        for zeile in self.ECHT:
            with self.subTest(zeile=zeile[:30]):
                self.assertTrue(K._FORTSCHRITT_ZEILE.match(zeile))

    def test_normale_zeilen_gelten_nicht_als_balken(self):
        for zeile in ("Build Summary", "Total files:  63",
                      "Wasted space: 37.22 KB (0.02% of file data blocks)",
                      "Actual gain achieved:  40.97%"):
            with self.subTest(zeile=zeile[:30]):
                self.assertFalse(K._FORTSCHRITT_ZEILE.match(zeile))

    def test_phase_wird_gelesen(self):
        o = _blank()
        self.assertEqual(K._balkenphase(o, self.ECHT[0]), "scan")
        self.assertEqual(K._balkenphase(o, self.ECHT[1]), "write")
        self.assertEqual(K._balkenphase(o, self.ECHT[2]), "compress")
        self.assertEqual(K._balkenphase(o, "Build Summary"), "")

    def test_zwei_balken_in_einer_zeile_lassen_sich_trennen(self):
        geklebt = ("[####------]  96% write @ 32.82 MB/s ETA 1s"
                   "[##--------]  48% compress @ 28.74 MB/s ETA 00:20")
        teile = K._FORTSCHRITT_START.split(geklebt)
        self.assertGreaterEqual(len(teile), 3)
        letzter = "[" + teile[-2] + teile[-1]
        self.assertTrue(K._FORTSCHRITT_ZEILE.match(letzter))
        self.assertEqual(K._balkenphase(_blank(), letzter), "compress")


class AmStueckAngeliefertTests(unittest.TestCase):
    """Der zweite Weg: die Engine liefert ihre Ausgabe komplett auf einmal.

    ``_run_command`` nutzt ausserhalb des Rueckruf-Modus ``communicate()`` und
    reicht das Ergebnis am Stueck an ``_append_to_log``. ``_clean_log_text``
    entfernt ``\\r`` ersatzlos - dadurch klebten Meldung und Fortschrittsbalken
    zu einer sehr langen Zeile zusammen, obwohl der Zeilentrenner des anderen
    Weges laengst repariert war.
    """

    @classmethod
    def setUpClass(cls):
        cls.text = QUELLE.read_text(encoding="utf-8")

    def test_mehrzeiliges_geht_ueber_das_zusammenfassen(self):
        stelle = self.text.index("def _append_to_log")
        block = self.text[stelle:stelle + 6000]
        self.assertIn("zeilen_anzeige", block)
        self.assertIn("self._log_engine_zeilen(z)", block)

    def test_wagenruecklauf_wird_zum_zeilenwechsel(self):
        stelle = self.text.index("def _append_to_log")
        block = self.text[stelle:stelle + 6000]
        self.assertIn('text.replace("\\r\\n", "\\n").replace("\\r", "\\n")', block)

    def test_kommandozeile_und_fehlerpuffer_kommen_zuerst(self):
        """Die Weiche darf CLI-Ausgabe und _build_log_tail nicht ueberspringen."""
        stelle = self.text.index("def _append_to_log")
        block = self.text[stelle:stelle + 6000]
        self.assertLess(block.index("_cli_mode"), block.index("zeilen_anzeige"))
        self.assertLess(block.index("_build_log_tail"), block.index("zeilen_anzeige"))


class ZusammenfassenTests(unittest.TestCase):
    """Quelltextpruefungen zum Verhalten von _log_engine_zeilen."""

    @classmethod
    def setUpClass(cls):
        cls.text = QUELLE.read_text(encoding="utf-8")

    def test_gleiche_phase_wird_ersetzt(self):
        stelle = self.text.index("def _log_engine_zeilen")
        block = self.text[stelle:stelle + 4200]
        self.assertIn("_balkenphase(z) == self._balkenphase(gefiltert[-1])", block)

    def test_phasenwechsel_haengt_an(self):
        stelle = self.text.index("def _log_engine_zeilen")
        block = self.text[stelle:stelle + 4200]
        self.assertIn("gefiltert.append(z)", block)

    def test_beide_schreibwege_fuehren_die_phase_mit(self):
        self.assertEqual(self.text.count("self._log_letzte_phase ="), 2)

    def test_obergrenze_entfernt_nur_ganze_zeilen(self):
        self.assertIn("_LOG_MAX_ZEILEN", self.text)
        stelle = self.text.index("def _log_engine_zeilen")
        block = self.text[stelle:stelle + 4200]
        self.assertIn('ansicht.delete("1.0", f"{anzahl - self._LOG_MAX_ZEILEN + 1}.0")', block)


class EchtesTextfeldTests(unittest.TestCase):
    """Prueft die Anzeige an einem **echten** tk.Text.

    Die Tests darueber arbeiten mit Nachbildungen und haben deshalb zwei
    Releases lang nichts gefunden: Der Fehler steckte nicht im Zerlegen der
    Engine-Ausgabe, sondern in Tks Index-Semantik. ``delete(zeile, END)`` nimmt
    der davorstehenden Zeile ihren Umbruch mit - Tk haelt nur einen
    abschliessenden Umbruch vor und laesst ihn nicht loeschen. Danach endete das
    Feld mitten in der Zeile, der naechste Einschub klebte an, und beim
    naechsten Balken wurde die verklebte Zeile **samt Meldung** geloescht.
    Nachgemessen an einem echten Lauf: 72 Sachzeilen verschwanden so.
    """

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:            # kein Fenstersystem verfuegbar
            raise unittest.SkipTest(f"Tk nicht verfuegbar: {exc}") from exc
        cls.root.withdraw()
        cls.tk = tk

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.feld = self.tk.Text(self.root)
        self.app = _blank()
        self.app.console_view = self.feld
        self.app.root = self.root
        self.app._cli_mode = False
        self.app._cli_quiet = True
        self.app._log_letzte_war_balken = False
        self.app._log_letzte_phase = ""

    def _zeilen(self) -> list[str]:
        inhalt = self.feld.get("1.0", "end-1c")
        return [z for z in inhalt.split("\n") if z.strip()]

    def _melden(self, text: str) -> None:
        """Eine Meldung ohne Zeilenumbruch - so kommen sie im Programm an."""
        self.app._append_to_log(text)
        self.root.update()

    # -- die Falle selbst --------------------------------------------------

    def test_loeschen_bis_ende_laesst_die_zeile_offen(self):
        """Haelt die Tk-Eigenheit fest, die den Fehler ausgeloest hat."""
        self.feld.insert("end", "erste Zeile\nzweite Zeile\n")
        self.app._log_letzte_zeile_entfernen(self.feld)
        spalte = int(self.feld.index("end-1c").split(".")[1])
        self.assertNotEqual(spalte, 0, "Tk laesst nach dem Loeschen eine offene Zeile zurueck")
        self.assertEqual(self.feld.get("1.0", "end-1c"), "erste Zeile")

    def test_auf_zeilenanfang_schliesst_die_offene_zeile(self):
        self.feld.insert("end", "offen")
        self.app._log_auf_zeilenanfang(self.feld)
        self.assertEqual(int(self.feld.index("end-1c").split(".")[1]), 0)

    def test_auf_zeilenanfang_fuegt_nichts_doppelt_ein(self):
        self.feld.insert("end", "zu\n")
        vorher = self.feld.get("1.0", "end-1c")
        self.app._log_auf_zeilenanfang(self.feld)
        self.assertEqual(self.feld.get("1.0", "end-1c"), vorher)

    # -- der Fall aus der Bildschirmaufnahme -------------------------------

    def test_meldung_und_balken_bleiben_getrennt(self):
        self._melden(">>> Schritt 2 / 2: inneres PFS -> Aussencontainer...")
        self.app._log_engine_zeilen(["[####----]  48% compress @ 15.9 MB/s"])
        zeilen = self._zeilen()
        self.assertEqual(len(zeilen), 2, f"verklebt: {zeilen}")
        self.assertTrue(zeilen[0].startswith(">>> Schritt 2 / 2"))
        self.assertTrue(zeilen[1].lstrip().startswith("["))

    def test_fortschreibender_balken_frisst_die_meldung_nicht(self):
        """Der eigentliche Regressionsfall: Balken zwei Mal, Meldung muss stehen."""
        self._melden(">>> Schritt 1 / 2: Ordner -> PFS...")
        self.app._log_engine_zeilen(["[##------]  20% write"])
        self.app._log_engine_zeilen(["[######--]  70% write"])
        self.app._log_engine_zeilen(["[########] 100% write"])
        zeilen = self._zeilen()
        self.assertIn(">>> Schritt 1 / 2: Ordner -> PFS...", zeilen)
        balken = [z for z in zeilen if z.lstrip().startswith("[")]
        self.assertEqual(len(balken), 1, f"Balken gestapelt: {zeilen}")
        self.assertIn("100%", balken[0])

    def test_keine_zeile_geht_verloren(self):
        """Meldungen und Balken abwechselnd - am Ende muss alles da sein."""
        meldungen = [f"[INFO] Meldung {i}" for i in range(1, 6)]
        for i, m in enumerate(meldungen):
            self._melden(m)
            self.app._log_engine_zeilen([f"[###-----]  {10 * i + 5}% write"])
        zeilen = self._zeilen()
        for m in meldungen:
            self.assertIn(m, zeilen, f"verschluckt: {m}\nFeld: {zeilen}")

    def test_engine_block_nach_balken_bleibt_vollstaendig(self):
        """Der Parameterblock, der in der Aufnahme abgeschnitten aussah."""
        block = ["Signed:            no", "64-bit inodes:     no",
                 "Encrypted:         no", "Dry run:           no"]
        self.app._log_engine_zeilen(["[####----]  40% write"])
        self.app._log_engine_zeilen(["[######--]  60% write"])
        self.app._log_engine_zeilen(block)
        zeilen = self._zeilen()
        for z in block:
            self.assertIn(z, zeilen)
        self.assertEqual(len([z for z in zeilen if z.lstrip().startswith("[")]), 1)

    def test_phasenwechsel_laesst_den_alten_balken_stehen(self):
        self.app._log_engine_zeilen(["[########] 100% scan"])
        self.app._log_engine_zeilen(["[--------]   0% write"])
        balken = [z for z in self._zeilen() if z.lstrip().startswith("[")]
        self.assertEqual(len(balken), 2, f"Phasenwechsel verschluckt: {balken}")

    def test_kein_balken_steht_mitten_in_einer_zeile(self):
        """Die Bedingung, die im Video verletzt war - ueber eine laengere Folge."""
        BALKEN = re.compile(r'\[[#=\-\s]*\]\s*\d{1,3}\s*%')
        self._melden("[INFO] Starte Aufgabe: pack_folder")
        for pct in (0, 25, 50, 75, 100):
            self.app._log_engine_zeilen([f"[###-----]  {pct}% compress @ 12.0 MB/s"])
        self._melden("Successfully wrote 149.50 MB image")
        self.app._log_engine_zeilen(["[--------]   0% verify"])
        for z in self._zeilen():
            treffer = BALKEN.findall(z)
            self.assertLessEqual(len(treffer), 1, f"zwei Balken in einer Zeile: {z}")
            if treffer:
                self.assertTrue(BALKEN.match(z.lstrip()), f"Balken klebt hinten an: {z}")


class ZeilenanfangQuelltextTests(unittest.TestCase):
    """Sichert ab, dass beide Schreibwege vor dem Einschub aufraeumen."""

    @classmethod
    def setUpClass(cls):
        cls.text = QUELLE.read_text(encoding="utf-8")

    def test_beide_wege_rufen_auf_zeilenanfang(self):
        # Einmal in _log_engine_zeilen, einmal in _append_to_log._update.
        self.assertEqual(self.text.count("self._log_auf_zeilenanfang(ansicht)"), 2)

    def test_engine_weg_raeumt_vor_dem_einschub_auf(self):
        stelle = self.text.index("def _log_engine_zeilen")
        block = self.text[stelle:stelle + 4600]
        aufraeumen = block.index("self._log_auf_zeilenanfang(ansicht)")
        einschub = block.index('ansicht.insert(tk.END, "\\n".join(gefiltert)')
        self.assertLess(aufraeumen, einschub, "erst aufraeumen, dann einschieben")

    def test_meldungen_gehen_immer_mit_umbruch_ins_feld(self):
        self.assertIn('clean if clean.endswith("\\n") else clean + "\\n"', self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
