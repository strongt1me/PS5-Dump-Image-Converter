# -*- coding: utf-8 -*-
"""Fenster "Downloads - Updates & Patches": ABBRECHEN und Fortschritt beim Laden eines Spiel-Updates (gemeldet 08.11.2026).

Gemeldet: "Das Abbrechen funktioniert nicht, wenn ich ein Spiel-Update herunterlade. Man sieht auch nicht, ob etwas
gestartet ist; erst wenn (nach langer Zeit) 1 % dasteht, weiss man, dass das Update laedt."

Ursachen im Arbeiter ``_download_worker``: ``urlopen(timeout=60)`` und ``read(1 MiB)`` liessen sich nicht unterbrechen (der
Abbruch-Flag wurde nur zwischen zwei Megabyte-Bloecken angesehen), vor der ersten Antwort stand "wartet", und die Spalte
Fortschritt zeigte ganze Prozent (bei einem 50-GB-Paket bleibt das lange auf "0 %"). Hier laeuft der echte Arbeiter gegen
den lokalen Langsam-Server (``langsamserver``).
"""
from __future__ import annotations

import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("download_fenster")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from langsamserver import DATEN, GRENZE, _Server            # noqa: E402


class _Baum:
    """Ein Treeview-Ersatz, der jede Aenderung mit Zeit mitschreibt."""

    def __init__(self) -> None:
        self.aenderungen: list[tuple[float, str, str]] = []
        self.t0 = time.monotonic()
        self.werte: dict[str, str] = {}

    def winfo_exists(self) -> bool:
        return True

    def exists(self, _iid: str) -> bool:
        return True

    def set(self, _iid: str, spalte: str, wert: str) -> None:
        self.werte[spalte] = wert
        self.aenderungen.append((time.monotonic() - self.t0, spalte, wert))


class DownloadFensterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _Server()
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop.set()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory(prefix="dlfenster_")
        self.addCleanup(self.td.cleanup)
        self.gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        self.gui._current_language = "de"
        self.gui.protokoll = []
        self.gui._append_to_log = self.gui.protokoll.append
        self.gui._hauptfaden_planen = lambda f, *a, **k: f(*a)
        self.baum = _Baum()
        self.gui._downloads_tree = self.baum
        self.eintrag = {"url": "", "pfad": str(Path(self.td.name) / "PPSA00001-patch.pkg"), "dateiname": "PPSA00001-patch.pkg",
                        "title_id": "PPSA00001", "art": "update", "status": "queued", "abbrechen": False}
        self.gui._downloads = {"i1": self.eintrag}

    def _starten(self, szenario: str):
        self.eintrag["url"] = "http://127.0.0.1:%d/%s/teil.pkg" % (self.port, szenario)
        faden = threading.Thread(target=self.gui._download_worker, args=("i1",), daemon=True)
        faden.start()
        return faden

    def _abbrechen_nach(self, faden: threading.Thread, sekunden: float) -> float:
        time.sleep(sekunden)
        t_ab = time.monotonic()
        self.eintrag["abbrechen"] = True
        faden.join(10)
        self.assertFalse(faden.is_alive(), "der Arbeiter reagiert nicht auf ABBRECHEN")
        return time.monotonic() - t_ab

    def test_sofort_nach_dem_start_steht_verbindet_nicht_wartet(self) -> None:
        faden = self._starten("spaet")
        time.sleep(0.4)
        self.assertEqual(self.gui._t("downloads.state_connecting", sek=0), self.baum.werte.get("status"),
                         "vor der ersten Antwort stand bisher 'wartet' (bis zu 60 s)")
        self._abbrechen_nach(faden, 0.1)

    def test_abbruch_beim_langsamen_server_wirkt_sofort(self) -> None:
        faden = self._starten("trickle")
        dauer = self._abbrechen_nach(faden, 1.5)
        self.assertLess(dauer, GRENZE, "ABBRECHEN wirkte erst nach %.1f s (vorher bis zu 21 s)" % dauer)
        self.assertEqual("cancelled", self.eintrag["status"])
        self.assertEqual(self.gui._t("downloads.state_cancelled"), self.baum.werte["status"])
        self.assertTrue(Path(self.eintrag["pfad"] + ".teil").is_file(), "die Teildatei bleibt zum Fortsetzen liegen")

    def test_abbruch_vor_der_ersten_antwort_wirkt_sofort(self) -> None:
        faden = self._starten("spaet")
        dauer = self._abbrechen_nach(faden, 0.6)
        self.assertLess(dauer, GRENZE, "urlopen liess sich nicht unterbrechen")
        self.assertEqual("cancelled", self.eintrag["status"])

    def test_abbruch_beim_schweigenden_server_wirkt_sofort_und_ist_kein_fehler(self) -> None:
        faden = self._starten("stumm")
        dauer = self._abbrechen_nach(faden, 1.0)
        self.assertLess(dauer, GRENZE)
        self.assertEqual("cancelled", self.eintrag["status"], "als Fehler statt als Abbruch gemeldet")

    def test_fortschritt_zeigt_unter_einem_prozent_zwei_nachkommastellen(self) -> None:
        faden = self._starten("trickle")
        time.sleep(2.2)                       # rund 160 KB von 4 MB = 3,9 % - zu schnell? dann zaehlt der erste Wert
        self._abbrechen_nach(faden, 0.0)
        werte = [w for _z, spalte, w in self.baum.aenderungen if spalte == "fortschritt"]
        self.assertTrue(werte, "keine Fortschrittsmeldung")
        self.assertTrue(all(re.fullmatch(r"\d+\.\d\d? %", w) for w in werte), werte)
        self.assertFalse(any(w in ("0 %", "1 %") for w in werte), "ganze Prozentzahlen wie frueher: %s" % werte)

    def test_herzschlag_zeigt_menge_und_tempo(self) -> None:
        faden = self._starten("trickle")
        time.sleep(2.4)
        self._abbrechen_nach(faden, 0.0)
        laufend = [w for _z, spalte, w in self.baum.aenderungen if spalte == "status" and w.startswith("lädt …")]
        self.assertTrue(laufend, "kein Lebenszeichen mit Menge und Tempo: %s" % [w for _z, s, w in self.baum.aenderungen if s == "status"])
        self.assertRegex(laufend[-1], r"/s")

    def test_ruhe_wird_als_stillstand_gemeldet(self) -> None:
        faden = self._starten("stumm")
        time.sleep(10.0)                      # 4 KiB kamen, dann nichts: ab 8 s Ruhe der Hinweis
        self._abbrechen_nach(faden, 0.0)
        status = [w for _z, spalte, w in self.baum.aenderungen if spalte == "status"]
        self.assertTrue(any("keine Daten seit" in w for w in status), status)

    def test_fertig_bleibt_fertig_der_herzschlag_ueberschreibt_den_endstand_nicht(self) -> None:
        faden = self._starten("schnell")
        faden.join(20)
        self.assertFalse(faden.is_alive())
        time.sleep(1.6)                       # ein spaeter Herzschlag haette jetzt zugeschlagen
        self.assertEqual("done", self.eintrag["status"])
        self.assertEqual(self.gui._t("downloads.state_done"), self.baum.werte["status"])
        self.assertEqual("100 %", self.baum.werte["fortschritt"])
        self.assertEqual(DATEN, Path(self.eintrag["pfad"]).read_bytes())

    def test_abbrechen_knopf_zeigt_gleich_wird_abgebrochen(self) -> None:
        """Die Liste meldet den Abbruch sofort, nicht erst wenn der Faden ihn bemerkt (Quelltextprobe der Knopffunktion)."""
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        i = quelle.index("        def _abbrechen() -> None:\r\n            for iid in baum.selection():") if "\r\n" in quelle else \
            quelle.index("        def _abbrechen() -> None:\n            for iid in baum.selection():")
        stueck = quelle[i:i + 900]
        self.assertIn('eintrag["abbrechen"] = True', stueck)
        self.assertIn("downloads.state_cancelling", stueck)


if __name__ == "__main__":
    unittest.main()
