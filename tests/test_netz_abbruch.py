# -*- coding: utf-8 -*-
"""ABBRECHEN und Fortschritt der Update-Downloads bei langsamer oder schweigender Leitung (gemeldet 08.11.2026).

Gemeldet: "Das Abbrechen funktioniert nicht, und man sieht erst bei 1 %, dass ein Download laeuft." Gemessen an einem
lokalen Langsam-Server (40 KB/s): erste Meldung nach 26 s, Abbruch wirksam nach 21 s (``antwort.read(1 MiB)``
blockiert); wartete der Server mit der Antwort, liess sich ``urlopen`` nicht unterbrechen (10 s); schwieg er mitten im
Strom, dauerte es bis zur Zeitgrenze von 30 s. Hier laeuft dieselbe Messung als Test mit kleinen Zeiten.

Geprueft werden alle drei Lader: ``ps5_updates.paket_laden`` (PS5, Manifest), ``ps5_updates.datei_laden`` (PS4-Direktliste)
und ``ps4pkg_updates.herunterladen`` (PS4-PKG-Werkzeug).
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("netz_abbruch")

from ps5_validator.utils import netz_abbruch as na          # noqa: E402
from ps5_validator.utils import ps4pkg_updates as p4        # noqa: E402
from ps5_validator.utils import ps5_updates as pu           # noqa: E402

from langsamserver import DATEN, GRENZE, GROESSE, SHA, _Server   # noqa: E402


class _Basis(unittest.TestCase):
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
        self.td = tempfile.TemporaryDirectory(prefix="netzabbruch_")
        self.addCleanup(self.td.cleanup)
        self.ordner = Path(self.td.name)
        for ziel in (mock.patch.object(pu, "url_erlaubt", return_value=True),
                     mock.patch.object(pu, "_oeffner", lambda: urllib.request.build_opener())):
            ziel.start()
            self.addCleanup(ziel.stop)

    def url(self, szenario: str) -> str:
        return "http://127.0.0.1:%d/%s/teil" % (self.port, szenario)


class LaderReagierenTests(_Basis):
    """Abbruch wirkt sofort, der Fortschritt kommt von der ersten Sekunde an - in jedem Lader."""

    def _lauf(self, wie: str, szenario: str, abbruch_nach: float = 1.0):
        abbruch = threading.Event()
        meldungen: list[tuple[float, int]] = []
        ende: dict = {}
        t0 = time.monotonic()

        def fortschritt(geladen: int, gesamt: int) -> None:
            meldungen.append((time.monotonic() - t0, geladen))

        def arbeit() -> None:
            try:
                ziel = str(self.ordner / "t.pkg")
                url = self.url(szenario)
                if wie == "paket":
                    pu.paket_laden(pu.Manifest(GROESSE, [pu.Teil(url, 0, GROESSE, SHA)]), ziel, fortschritt=fortschritt,
                                   abbruch=abbruch.is_set, faeden=1, versuche=0)
                elif wie == "datei":
                    pu.datei_laden(url, ziel, fortschritt=fortschritt, abbruch=abbruch.is_set, versuche=0)
                else:
                    info = p4.UpdateInfo(title_id="CUSA00001", verzeichnis=p4.UpdateVerzeichnis(
                        gesamtgroesse=GROESSE, anzahl=1, teile=[p4.UpdateTeil(url, 0, GROESSE, SHA)]))
                    p4.herunterladen(info, str(self.ordner), fortschritt=fortschritt, abbruch=abbruch.is_set)
                ende["wie"] = "fertig"
            except (pu.UpdateFehler, p4.UpdateFehler) as exc:
                ende["wie"] = str(exc) if isinstance(exc, pu.UpdateFehler) else exc.schluessel
            ende["t"] = time.monotonic() - t0

        faden = threading.Thread(target=arbeit, daemon=True)
        faden.start()
        time.sleep(abbruch_nach)
        t_abbruch = time.monotonic() - t0
        abbruch.set()
        faden.join(15)
        self.assertFalse(faden.is_alive(), "%s/%s: der Lader reagiert nicht auf ABBRECHEN" % (wie, szenario))
        return meldungen, ende, t_abbruch

    def test_langsame_leitung_zeigt_sofort_fortschritt_und_bricht_sofort_ab(self) -> None:
        for wie in ("paket", "datei", "ps4"):
            with self.subTest(lader=wie):
                meldungen, ende, t_abbruch = self._lauf(wie, "trickle")
                erste = next((z for z, g in meldungen if g > 0), None)
                self.assertIsNotNone(erste, "keine Meldung mit Bytes (vorher erst nach rund 13 s bei 80 KB/s)")
                self.assertLess(erste, 1.5)
                self.assertIn(ende["wie"], ("ps5upd.abgebrochen", "abgebrochen"))
                self.assertLess(ende["t"] - t_abbruch, GRENZE, "ABBRECHEN wirkte zu spaet")

    def test_server_der_mit_der_antwort_wartet_laesst_sich_abbrechen(self) -> None:
        for wie in ("paket", "datei", "ps4"):
            with self.subTest(lader=wie):
                _meldungen, ende, t_abbruch = self._lauf(wie, "spaet")
                self.assertIn(ende["wie"], ("ps5upd.abgebrochen", "abgebrochen"))
                self.assertLess(ende["t"] - t_abbruch, GRENZE, "urlopen liess sich nicht unterbrechen")

    def test_schweigender_server_laesst_sich_abbrechen_und_ist_kein_netzfehler(self) -> None:
        for wie in ("paket", "datei", "ps4"):
            with self.subTest(lader=wie):
                _meldungen, ende, t_abbruch = self._lauf(wie, "stumm")
                self.assertIn(ende["wie"], ("ps5upd.abgebrochen", "abgebrochen"),
                              "als Netzfehler statt als Abbruch gemeldet")
                self.assertLess(ende["t"] - t_abbruch, GRENZE, "das blockierte Lesen wurde nicht befreit")

    def test_ohne_abbruch_laedt_alles_vollstaendig_und_geprueft(self) -> None:
        """Gegenprobe: Die kleinen Lesestuecke ruehren die Daten nicht an."""
        for wie in ("paket", "datei", "ps4"):
            with self.subTest(lader=wie):
                ziel = self.ordner / ("t_%s.pkg" % wie)
                url = self.url("schnell")
                if wie == "paket":
                    pu.paket_laden(pu.Manifest(GROESSE, [pu.Teil(url, 0, GROESSE, SHA)]), str(ziel), faeden=1)
                elif wie == "datei":
                    pu.datei_laden(url, str(ziel))
                else:
                    info = p4.UpdateInfo(title_id="CUSA00002", verzeichnis=p4.UpdateVerzeichnis(
                        gesamtgroesse=GROESSE, anzahl=1, teile=[p4.UpdateTeil(url, 0, GROESSE, SHA)]))
                    ziel = Path(p4.herunterladen(info, str(self.ordner)))
                self.assertEqual(DATEN, ziel.read_bytes())


class HilfsfunktionenTests(unittest.TestCase):
    def test_schlafen_endet_beim_abbruch_sofort(self) -> None:
        abbruch = threading.Event()
        threading.Timer(0.3, abbruch.set).start()
        t0 = time.monotonic()
        self.assertTrue(na.schlafen(30.0, abbruch.is_set))
        self.assertLess(time.monotonic() - t0, 1.5)

    def test_schlafen_ohne_abbruch_wartet_die_zeit_ab(self) -> None:
        t0 = time.monotonic()
        self.assertFalse(na.schlafen(0.4, None))
        self.assertGreaterEqual(time.monotonic() - t0, 0.35)

    def test_oeffnen_reicht_die_ausnahme_des_aufrufs_weiter(self) -> None:
        def kaputt():
            raise OSError("keine Verbindung")

        with self.assertRaises(OSError):
            na.oeffnen(kaputt, lambda: False, lambda: RuntimeError("abgebrochen"))

    def test_oeffnen_schliesst_die_spaet_kommende_antwort_nach_dem_abbruch(self) -> None:
        geschlossen = threading.Event()
        frei = threading.Event()

        class _Antwort:
            def close(self) -> None:
                geschlossen.set()

        def langsam():
            frei.wait(5)
            return _Antwort()

        abbruch = threading.Event()
        threading.Timer(0.3, abbruch.set).start()
        with self.assertRaises(RuntimeError):
            na.oeffnen(langsam, abbruch.is_set, lambda: RuntimeError("abgebrochen"))
        frei.set()
        self.assertTrue(geschlossen.wait(3), "die spaete Antwort blieb offen")

    def test_ende_waehrend_des_abbruchs_ist_ein_abbruch_kein_vorzeitiges_ende(self) -> None:
        """Hat die Wache die Verbindung getrennt, liefert das Lesen ``b""``: Das darf nicht als fertig gelten."""
        class _Leer:
            def read1(self, _n):
                return b""

        with self.assertRaises(RuntimeError):
            na.stueck_lesen(_Leer(), lambda: True, lambda: RuntimeError("abgebrochen"))
        self.assertEqual(b"", na.stueck_lesen(_Leer(), lambda: False, lambda: RuntimeError("abgebrochen")))

    def test_lesefehler_waehrend_des_abbruchs_wird_zum_abbruch(self) -> None:
        zaehler = [0]

        class _Kaputt:
            def read1(self, _n):
                raise OSError(10038, "getrennt")

        def abbruch() -> bool:
            zaehler[0] += 1
            return zaehler[0] > 1                     # erst nach dem Vorab-Test verlangt

        with self.assertRaises(RuntimeError):
            na.stueck_lesen(_Kaputt(), abbruch, lambda: RuntimeError("abgebrochen"))
        with self.assertRaises(OSError):
            na.stueck_lesen(_Kaputt(), lambda: False, lambda: RuntimeError("abgebrochen"))

    def test_fehlendes_read1_faellt_auf_read_zurueck(self) -> None:
        class _Alt:
            def read(self, n):
                return b"x" * min(n, 3)

        self.assertEqual(b"xxx", na.stueck_lesen(_Alt(), None, lambda: RuntimeError("abgebrochen")))


if __name__ == "__main__":
    unittest.main()
