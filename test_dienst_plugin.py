# -*- coding: utf-8 -*-
"""DPI v2 als OnionHEN-Plugin auf der Seite "Konsole & Payloads" (Nutzer 06.10.2026).

Ein Plugin ist keine eigenstaendige ELF: Ist es markiert, ist "Ausgewaehltes starten" gesperrt und ein Hinweis
nennt den Wirt (OnionHEN). "Plugin auf die PS5 legen" laedt es per FTP - erst als ``.installing``, Groesse
pruefen, dann umbenennen (so verlangt es der Autor). Fehlt ``/data/OnionHEN``, wird nichts hochgeladen.
Kein Test spricht mit einer echten Konsole: FTP und Ports sind nachgebildet.
"""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import konsole_dienste             # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

PFAD = "/data/OnionHEN/plugins/DPIV00001.elf"


class _FTP:
    """Ein FTP-Server zum Mitschreiben: Ordner, Dateien mit Groesse, Befehlsfolge."""

    def __init__(self, ordner=("/data", "/data/OnionHEN"), dateien=None) -> None:
        self.ordner = set(ordner)
        self.dateien = dict(dateien or {})
        self.befehle: list[str] = []

    def cwd(self, pfad):
        if pfad not in self.ordner:
            raise OSError("550 no such directory")
        self.befehle.append("CWD " + pfad)

    def mkd(self, pfad):
        self.ordner.add(pfad)
        self.befehle.append("MKD " + pfad)

    def size(self, pfad):
        if pfad not in self.dateien:
            raise OSError("550 no such file")
        return self.dateien[pfad]

    def storbinary(self, befehl, fh):
        pfad = befehl.split(" ", 1)[1]
        self.dateien[pfad] = len(fh.read())
        self.befehle.append(befehl)

    def rename(self, alt, neu):
        self.dateien[neu] = self.dateien.pop(alt)
        self.befehle.append("RNTO %s -> %s" % (alt, neu))

    def quit(self):
        self.befehle.append("QUIT")


class _SofortFaden:
    """Ersetzt threading.Thread: die Arbeit laeuft gleich im Testfaden."""

    def __init__(self, target=None, daemon=None, name=None, args=(), kwargs=None):
        self._ziel, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        self._ziel(*self._args, **self._kwargs)


class KatalogTests(unittest.TestCase):
    def test_dpiv2_ist_ein_plugin_fuer_onionhen(self) -> None:
        eintrag = konsole_dienste.dienst("dpiv2")
        self.assertTrue(eintrag.ist_plugin)
        self.assertEqual((PFAD, "OnionHEN"), (eintrag.plugin_pfad, eintrag.plugin_wirt))
        self.assertEqual("", eintrag.payload_muster, "ein Plugin darf nie ueber den ELF-Loader gehen")

    def test_nur_dpiv2_ist_ein_plugin(self) -> None:
        self.assertEqual(["dpiv2"], [d.schluessel for d in konsole_dienste.KATALOG if d.ist_plugin])

    def test_die_texte_nennen_wirt_und_dass_es_keine_elf_ist(self) -> None:
        de = STRINGS["dienste.plugin_hinweis"]["de"]
        self.assertIn("keine eigenständige ELF", de)
        self.assertIn("installiert", de)
        for sprache in ("de", "en"):
            self.assertIn("{wirt}", STRINGS["dienste.plugin_hinweis"][sprache])


class SeitenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Eine Wurzel je Prozess, nie zerstoeren - siehe test_fensterlayout.py.
        cls.root = tk._default_root or tk.Tk()
        cls.root.withdraw()
        cls.app = APP.PS5ConverterGUI(cls.root)
        cls.app._current_language = "de"
        cls.root.withdraw()
        for kind in cls.root.winfo_children():
            if isinstance(kind, tk.Toplevel):
                kind.withdraw()
        if getattr(cls.app, "_konsole_tafel", None) is None:
            cls.app._konsole_tafel_bauen()

    def setUp(self) -> None:
        self.app._konsole_tafel_laeuft = {"aktiv": False}
        self.app._konsole_tafel_ip.set("192.0.2.10")
        self.tabelle = self.app._konsole_tafel_tabelle
        self.addCleanup(self._abwaehlen)

    def _abwaehlen(self) -> None:
        self.tabelle.selection_remove(*self.tabelle.selection())
        self.app._konsole_tafel_auswahl_pruefen()
        self.app._konsole_tafel_laeuft = {"aktiv": False}

    def _waehlen(self, schluessel: str) -> None:
        self.tabelle.selection_set(schluessel)
        self.app._konsole_tafel_auswahl_pruefen()

    def _protokoll(self) -> str:
        return "\n".join(self.app._konsole_tafel_zeile(e) for e in self.app._konsole_tafel_puffer)

    def test_plugin_markiert_sperrt_starten_und_zeigt_den_hinweis(self) -> None:
        self._waehlen("dpiv2")
        self.assertEqual("disabled", str(self.app._konsole_tafel_start_knopf.cget("state")))
        self.assertTrue(self.app._konsole_tafel_plugin_reihe.winfo_manager())
        text = self.app._konsole_tafel_plugin_text.get()
        self.assertIn("OnionHEN", text)
        self.assertIn(PFAD, text)

    def test_anderer_dienst_gibt_starten_wieder_frei(self) -> None:
        self._waehlen("dpiv2")
        self._waehlen("ftpsrv")
        self.assertEqual("normal", str(self.app._konsole_tafel_start_knopf.cget("state")))
        self.assertFalse(self.app._konsole_tafel_plugin_reihe.winfo_manager())

    def test_starten_schickt_ein_plugin_nie(self) -> None:
        self._waehlen("dpiv2")
        with mock.patch.object(self.app, "_konsole_dienst_starten") as starten, \
                mock.patch.object(APP.threading, "Thread", _SofortFaden):
            self.app._konsole_tafel_starten()
        starten.assert_not_called()

    def _ablegen(self, ftp: _FTP) -> None:
        self._waehlen("dpiv2")
        self.app._konsole_tafel_puffer.clear()
        with mock.patch.object(self.app, "_ampr_ftp_connect", return_value=ftp), \
                mock.patch.object(self.app, "_ps5_port_open", return_value=True), \
                mock.patch.object(APP.threading, "Thread", _SofortFaden), \
                mock.patch.object(APP.konsole_dienste, "pruefen",
                                  return_value=konsole_dienste.pruefen("")):
            self.app._konsole_tafel_plugin_ablegen()

    def test_ohne_onionhen_wird_nichts_hochgeladen(self) -> None:
        ftp = _FTP(ordner=("/data",))
        self._ablegen(ftp)
        self.assertFalse([b for b in ftp.befehle if b.startswith(("STOR", "RNTO", "MKD"))])
        self.assertIn("nicht installiert", self._protokoll())

    def test_erst_installing_dann_umbenennen(self) -> None:
        ftp = _FTP()
        self._ablegen(ftp)
        befehle = [b for b in ftp.befehle if b.startswith(("MKD", "STOR", "RNTO"))]
        self.assertEqual(["MKD /data/OnionHEN/plugins",
                          "STOR /data/OnionHEN/plugins/DPIV00001.installing",
                          "RNTO /data/OnionHEN/plugins/DPIV00001.installing -> " + PFAD], befehle)
        datei = self.app._konsole_payload_datei("dpiv2-*.elf")
        self.assertEqual(Path(datei).stat().st_size, ftp.dateien[PFAD])
        self.assertIn("[OK]", self._protokoll())

    def test_unveraendert_vorhanden_wird_nicht_neu_geladen(self) -> None:
        groesse = Path(self.app._konsole_payload_datei("dpiv2-*.elf")).stat().st_size
        ftp = _FTP(ordner=("/data", "/data/OnionHEN", "/data/OnionHEN/plugins"),
                   dateien={PFAD: groesse})
        self._ablegen(ftp)
        self.assertFalse([b for b in ftp.befehle if b.startswith("STOR")])
        self.assertIn("schon unverändert", self._protokoll())

    def test_falsche_groesse_wird_nicht_scharf_geschaltet(self) -> None:
        ftp = _FTP()
        ftp.storbinary = lambda befehl, fh: (ftp.dateien.__setitem__(befehl.split(" ", 1)[1], 3),
                                             ftp.befehle.append(befehl))
        self._ablegen(ftp)
        self.assertNotIn(PFAD, ftp.dateien)
        self.assertFalse([b for b in ftp.befehle if b.startswith("RNTO")])


if __name__ == "__main__":
    unittest.main()
