# -*- coding: utf-8 -*-
"""Stufe 2 der Ansicht KONSOLE: Dienste-Ampel und Payload-Startrampe.

Die haeufigste Ursache, wenn etwas mit der Konsole nicht klappt, ist ein
Payload, das gar nicht laeuft. Das Fenster "Konsole & Payloads" fragt alle
bekannten Ports ab und startet fehlende Dienste aus ``helloworld``.

Geprueft wird hier:

* die Abfrage gegen einen **echten** Port auf diesem Rechner (offen und zu),
* dass der Katalog in sich stimmt und zu den mitgelieferten Dateien passt,
* die Verdrahtung der Knoepfe der zweiten Ansicht,
* das Fenster selbst (oeffnet, Tabelle gefuellt, Knoepfe da).

Die Konsole selbst wird nicht gebraucht - und nichts an sie geschickt.
"""
from __future__ import annotations

import importlib.util
import os
import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import konsole_dienste as kd      # noqa: E402
from ps5_validator.utils.i18n import STRINGS               # noqa: E402

PROJEKT = Path(__file__).resolve().parent
HAUPTDATEI = str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _Horcher:
    """Ein echter, offener TCP-Port auf diesem Rechner.

    ``gruss`` schickt beim Verbinden etwas zurueck - damit laesst sich der
    haengende Dienst nachstellen (Port offen, aber stumm).
    """

    def __init__(self, gruss: bytes = b""):
        self._gruss = gruss

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self._faden = threading.Thread(target=self._annehmen, daemon=True)
        self._faden.start()
        return self

    def _annehmen(self):
        try:
            verbindung, _ = self.sock.accept()
            if self._gruss:
                verbindung.sendall(self._gruss)
            else:
                # Offen lassen und schweigen - wie der haengende ftpsrv.
                import time as _t
                _t.sleep(2.0)
            verbindung.close()
        except OSError:
            pass

    def __exit__(self, *_a):
        self.sock.close()
        return False


def _freier_port() -> int:
    """Eine Portnummer, auf der sicher niemand horcht."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class KatalogTests(unittest.TestCase):

    def test_schluessel_und_ports_sind_eindeutig(self):
        schluessel = [d.schluessel for d in kd.KATALOG]
        self.assertEqual(len(schluessel), len(set(schluessel)))
        ports = [d.port for d in kd.KATALOG]
        self.assertEqual(len(ports), len(set(ports)))

    def test_die_bekannten_ports_stimmen(self):
        """Gegen das, was an der Konsole des Nutzers gemessen ist."""
        erwartet = {"elfldr9021": 9021, "pldmgr": 8084, "ftpsrv": 2121,
                    "klogsrv": 3232}
        for schluessel, port in erwartet.items():
            with self.subTest(dienst=schluessel):
                self.assertEqual(port, kd.dienst(schluessel).port)

    def test_ftpsrv_wird_am_gruss_gemessen(self):
        """Sonst meldet ein haengender ftpsrv faelschlich "laeuft"."""
        self.assertTrue(kd.dienst("ftpsrv").begruessung)

    def test_pkgmgr_haengt_an_seiner_weboberflaeche(self):
        """8844 = ``DEFAULT_HTTP_PORT`` aus der Quelle des PKG Managers.

        Die beiden anderen Ports (18841 Paketstrom, 18842 Direct Install)
        kommen mit demselben Payload hoch und werden nicht einzeln gefragt.
        """
        eintrag = kd.dienst("pkgmgr")
        self.assertEqual(8844, eintrag.port)
        self.assertEqual("http://10.0.0.5:8844/",
                         kd.web_adresse(eintrag, "10.0.0.5"))

    def test_zu_jedem_muster_liegt_eine_datei_bei(self):
        """Faengt den Fall "Payload auf neue Fassung getauscht, Muster passt nicht mehr".

        Am 22.09.2026 wurde ``pkgmgr_v1.0.0.elf`` gegen ``pkgmgr_v1.2.2.elf``
        getauscht; ein auf die Fassung festgelegtes Muster haette danach still
        ins Leere gegriffen.
        """
        ordner = PROJEKT / "helloworld"
        for eintrag in kd.KATALOG:
            if not eintrag.payload_muster:
                continue
            with self.subTest(dienst=eintrag.schluessel):
                self.assertTrue(
                    list(ordner.glob(eintrag.payload_muster)),
                    "keine Datei zu %s" % eintrag.payload_muster)

    def test_grundausstattung_steht_im_katalog(self):
        for schluessel in kd.GRUNDAUSSTATTUNG:
            with self.subTest(dienst=schluessel):
                eintrag = kd.dienst(schluessel)
                self.assertIsNotNone(eintrag)
                self.assertTrue(eintrag.payload_muster,
                                "ohne Datei laesst sich nichts starten")

    def test_jeder_dienst_ist_zweisprachig_beschriftet(self):
        for eintrag in kd.KATALOG:
            for schluessel in (eintrag.name_schluessel, eintrag.zweck_schluessel):
                with self.subTest(schluessel=schluessel):
                    self.assertIn(schluessel, STRINGS)
                    self.assertTrue(STRINGS[schluessel].get("de"))
                    self.assertTrue(STRINGS[schluessel].get("en"))

    def test_web_adresse(self):
        webfm = kd.dienst("webfm")
        self.assertEqual("http://10.0.0.5:8888/", kd.web_adresse(webfm, "10.0.0.5"))
        self.assertEqual("", kd.web_adresse(webfm, "   "))
        self.assertEqual("", kd.web_adresse(kd.dienst("ftpsrv"), "10.0.0.5"))


class AbfrageTests(unittest.TestCase):

    def test_offener_port_wird_erkannt(self):
        with _Horcher() as h:
            self.assertTrue(kd.port_offen("127.0.0.1", h.port, zeit=1.0))

    def test_geschlossener_port_wird_erkannt(self):
        self.assertFalse(kd.port_offen("127.0.0.1", _freier_port(), zeit=0.3))

    def test_uebersicht_an_echten_ports(self):
        with _Horcher() as h:
            zu = _freier_port()
            dienste = (kd.Dienst("offen", h.port, gruppe="elfldr"),
                       kd.Dienst("zu", zu))
            uebersicht = kd.pruefen("127.0.0.1", zeit=1.0, dienste=dienste)
            self.assertEqual(2, len(uebersicht))
            self.assertTrue(uebersicht.laeuft("offen"))
            self.assertFalse(uebersicht.laeuft("zu"))
            self.assertEqual(1, uebersicht.anzahl_laufend)
            self.assertEqual(h.port, uebersicht.loader_port)
            self.assertTrue(uebersicht.bereit)

    def test_ohne_adresse_wird_nichts_gefragt(self):
        uebersicht = kd.pruefen("   ")
        self.assertEqual(len(kd.KATALOG), len(uebersicht))
        self.assertEqual(0, uebersicht.anzahl_laufend)
        self.assertFalse(uebersicht.bereit)

    def test_haengender_dienst_gilt_nicht_als_laufend(self):
        """Port offen, kein Gruss: am 17.08.2026 an ftpsrv erlebt."""
        with _Horcher() as stumm:
            eintrag = kd.Dienst("ftpsrv", stumm.port, begruessung=True)
            laeuft, ist_stumm = kd.dienst_pruefen("127.0.0.1", eintrag, zeit=0.8)
            self.assertFalse(laeuft)
            self.assertTrue(ist_stumm)
            uebersicht = kd.pruefen("127.0.0.1", zeit=0.8, dienste=(eintrag,))
            self.assertFalse(uebersicht.laeuft("ftpsrv"))
            self.assertTrue(uebersicht.staende[0].stumm)

    def test_mit_gruss_gilt_der_dienst_als_laufend(self):
        with _Horcher(gruss=b"220 ftpsrv ready\r\n") as gut:
            eintrag = kd.Dienst("ftpsrv", gut.port, begruessung=True)
            self.assertEqual((True, False),
                             kd.dienst_pruefen("127.0.0.1", eintrag, zeit=0.8))

    def test_ohne_erwarteten_gruss_genuegt_der_offene_port(self):
        with _Horcher() as offen:
            eintrag = kd.Dienst("klogsrv", offen.port)
            self.assertEqual((True, False),
                             kd.dienst_pruefen("127.0.0.1", eintrag, zeit=0.8))

    def test_bereit_auch_ueber_den_payload_manager(self):
        dienste = (kd.Dienst("elfldr9021", 1, gruppe="elfldr"),
                   kd.Dienst("pldmgr", 2))
        uebersicht = kd.Uebersicht("1.2.3.4", [kd.Stand(dienste[0], False),
                                               kd.Stand(dienste[1], True)])
        self.assertTrue(uebersicht.bereit)
        self.assertIsNone(uebersicht.loader_port)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _oeffnen(self):
        vorher = set(_WURZEL.winfo_children())
        self.app._show_konsole_dienste()
        _WURZEL.update_idletasks()
        neu = [w for w in _WURZEL.winfo_children()
               if w not in vorher and isinstance(w, tk.Toplevel)]
        self.assertTrue(neu, "Kein Fenster geoeffnet.")
        return neu[0]

    @staticmethod
    def _alle(widget):
        for kind in widget.winfo_children():
            yield kind
            yield from FensterTests._alle(kind)

    def test_die_knoepfe_der_ansicht_sind_verdrahtet(self):
        klasse = self.haupt.PS5ConverterGUI
        for kennung, methode in klasse._KONSOLE_FENSTER.items():
            with self.subTest(knopf=kennung):
                self.assertIn(kennung, [k for _s, k in klasse._KONSOLE_KNOEPFE])
                self.assertTrue(hasattr(klasse, methode), methode)

    def test_klog_knopf_oeffnet_das_vorhandene_fenster(self):
        with mock.patch.object(self.app, "_werkzeugfenster_umschalten") as um:
            self.app._konsole_knopf_gedrueckt("klog", "konsole.btn_klog")
        um.assert_called_once_with("_show_klog_window_geprueft")

    def test_kennung_ohne_fenster_sagt_dass_es_folgt(self):
        """Das Auffangnetz fuer eine Kennung ohne Fenster.

        Seit Stufe 4 ist jeder Knopf der Seitenleiste verdrahtet - der Fall
        laesst sich also nicht mehr ueber einen Knopf ausloesen. Der Zweig
        im Code bleibt trotzdem: Er faengt einen Knopf ab, den jemand
        spaeter hinzufuegt, ohne ein Fenster dafuer zu bauen. Geprueft wird
        er deshalb direkt.
        """
        klasse = self.haupt.PS5ConverterGUI
        self.assertNotIn("gibt_es_noch_nicht", klasse._KONSOLE_FENSTER)
        with mock.patch.object(self.haupt, "messagebox") as box, \
                mock.patch.object(self.app, "_werkzeugfenster_umschalten") as um:
            self.app._konsole_knopf_gedrueckt("gibt_es_noch_nicht",
                                              "konsole.btn_klog")
        um.assert_not_called()
        box.showinfo.assert_called_once()

    def test_verdrahtete_knoepfe_oeffnen_ihr_fenster(self):
        """Gegenstueck: Was in der Karte steht, muss auch aufgehen."""
        klasse = self.haupt.PS5ConverterGUI
        for kennung, methode in klasse._KONSOLE_FENSTER.items():
            with self.subTest(kennung=kennung):
                with mock.patch.object(self.app,
                                       "_werkzeugfenster_umschalten") as um:
                    self.app._konsole_knopf_gedrueckt(kennung, "konsole.btn_klog")
                um.assert_called_once_with(methode)

    def test_fenster_zeigt_alle_dienste(self):
        fenster = self._oeffnen()
        try:
            tabelle = next(w for w in self._alle(fenster)
                           if isinstance(w, ttk.Treeview))
            self.assertEqual([d.schluessel for d in kd.KATALOG],
                             list(tabelle.get_children()))
            erste = tabelle.item(kd.KATALOG[0].schluessel, "values")
            self.assertEqual(self.app._t(kd.KATALOG[0].name_schluessel), erste[0])
            self.assertEqual(str(kd.KATALOG[0].port), str(erste[1]))
            self.assertEqual(self.app._t("dienste.zustand_aus"), erste[2])
            texte = [str(w.cget("text")) for w in self._alle(fenster)
                     if isinstance(w, ttk.Button)]
            for schluessel in ("dienste.check_button", "dienste.start_button",
                               "dienste.base_button", "dienste.web_button"):
                self.assertIn(self.app._t(schluessel), texte)
        finally:
            fenster.destroy()

    def test_ohne_adresse_wird_nichts_geschickt(self):
        fenster = self._oeffnen()
        try:
            # Das Feld traegt die zuletzt gespeicherte Adresse - hier leeren,
            # damit die Pruefung nicht von der Einstellung abhaengt.
            feld = next(w for w in self._alle(fenster) if isinstance(w, tk.Entry))
            feld.delete(0, "end")
            knopf = next(w for w in self._alle(fenster)
                         if isinstance(w, ttk.Button)
                         and str(w.cget("text")) == self.app._t("dienste.base_button"))
            with mock.patch.object(self.haupt, "messagebox") as box, \
                    mock.patch.object(self.app, "_send_payload_to_ps5") as senden:
                knopf.invoke()
            senden.assert_not_called()
            box.showwarning.assert_called_once()
        finally:
            fenster.destroy()

    def test_payload_datei_nimmt_die_neueste_fassung(self):
        """helloworld traegt ftpsrv 0.21.1, 1.15 und 1.16 - 1.16 gewinnt."""
        pfad = self.app._konsole_payload_datei("ftpsrv-ps5*.elf")
        self.assertTrue(pfad, "keine ftpsrv-Datei in helloworld gefunden")
        self.assertIn("1.16", os.path.basename(pfad))
        self.assertEqual("", self.app._konsole_payload_datei(""))
        self.assertEqual("", self.app._konsole_payload_datei("gibtesnicht*.elf"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
