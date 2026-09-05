# -*- coding: utf-8 -*-
"""Tests fuer den Payload-Versand mit seinen drei Wegen.

Die Wegwahl ist der ganze Sinn des Moduls, und sie ist nicht beliebig:
elfldr zuerst, weil nur er die Ausgabe des Payloads zurueckreicht. Wer die
Reihenfolge umdreht, bekommt ein Werkzeug, das zwar etwas startet, aber
nie sagen kann, ob es geklappt hat - genau der Zustand, in dem die
Fehlersuche am 29.08.2026 mehrfach stecken blieb.
"""
import io
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils import i18n, payload_versand as pv

HAUPTDATEI = str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")


class _Lauscher:
    """Ein Port, auf dem wirklich jemand zuhoert - fuer port_offen()."""

    def __init__(self):
        self.buchse = socket.socket()
        self.buchse.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.buchse.bind(("127.0.0.1", 0))
        self.buchse.listen(1)
        self.port = self.buchse.getsockname()[1]

    def zu(self):
        self.buchse.close()


class PortTests(unittest.TestCase):
    """port_offen soll nicht raten, sondern nachsehen."""

    def test_offener_port_wird_erkannt(self):
        lauscher = _Lauscher()
        try:
            self.assertTrue(pv.port_offen("127.0.0.1", lauscher.port))
        finally:
            lauscher.zu()

    def test_geschlossener_port_wird_erkannt(self):
        lauscher = _Lauscher()
        port = lauscher.port
        lauscher.zu()
        self.assertFalse(pv.port_offen("127.0.0.1", port, timeout=1.0))


class ElfldrTests(unittest.TestCase):
    """Der gewohnte Weg: senden, Senderichtung schliessen, Ausgabe lesen."""

    def test_ausgabe_kommt_zurueck(self):
        lauscher = _Lauscher()
        empfangen = []

        def bedienen():
            verbindung, _ = lauscher.buchse.accept()
            teile = []
            while True:
                st = verbindung.recv(4096)
                if not st:
                    break
                teile.append(st)
            empfangen.append(b"".join(teile))
            verbindung.sendall(b"appinst: 'FAKE02932' registriert\n")
            verbindung.close()

        threading.Thread(target=bedienen, daemon=True).start()
        antwort = pv.ueber_elfldr("127.0.0.1", b"ELFDATEN", port=lauscher.port)
        lauscher.zu()
        self.assertEqual(empfangen[0], b"ELFDATEN")
        self.assertIn("registriert", antwort)


class AblageortTests(unittest.TestCase):
    """Der Ordnername kommt vom Dienst, nicht aus einer Vermutung."""

    def setUp(self):
        self.echt = pv._pldmgr_ruf

    def tearDown(self):
        pv._pldmgr_ruf = self.echt

    def test_folder_name_aus_der_antwort_wird_genommen(self):
        pv._pldmgr_ruf = lambda *a, **k: '{"folder_name": "eigenwillig"}'
        self.assertEqual(pv.pldmgr_ablageort("h", "appinst.elf"),
                         "/data/pldmgr/payloads/eigenwillig/appinst.elf")

    def test_ohne_brauchbare_antwort_wird_der_name_genommen(self):
        pv._pldmgr_ruf = lambda *a, **k: "kein json"
        self.assertEqual(pv.pldmgr_ablageort("h", "appinst.elf"),
                         "/data/pldmgr/payloads/appinst/appinst.elf")


class PldmgrTests(unittest.TestCase):
    """Was der Payload Manager annimmt - und was nicht."""

    def setUp(self):
        self.rufe = []
        self.echt = pv._pldmgr_ruf

        def merken(host, pfad, koerper=None, port=pv.PLDMGR_PORT, timeout=0):
            self.rufe.append((pfad, len(koerper) if koerper else 0))
            return '{"folder_name": "appinst"}'
        pv._pldmgr_ruf = merken

    def tearDown(self):
        pv._pldmgr_ruf = self.echt

    def test_erst_hochladen_dann_starten(self):
        ziel = pv.ueber_pldmgr("h", b"ELF", "appinst.elf")
        pfade = [p for p, _ in self.rufe]
        self.assertTrue(pfade[0].startswith("/manage:check"))
        self.assertTrue(pfade[1].startswith("/manage:upload"))
        self.assertTrue(pfade[2].startswith("/loadpayload:"))
        self.assertEqual(ziel, "/data/pldmgr/payloads/appinst/appinst.elf")

    def test_nur_der_upload_traegt_daten(self):
        pv.ueber_pldmgr("h", b"ELFDATEN", "appinst.elf")
        groessen = {p.split("?")[0]: n for p, n in self.rufe}
        self.assertEqual(groessen["/manage:upload"], 8)

    def test_fremde_endung_wird_abgelehnt(self):
        # Der Dienst nimmt nur .elf und .bin. Das vorher zu sagen ist
        # freundlicher, als ihn einen Fehler zurueckgeben zu lassen.
        with self.assertRaises(pv.VersandFehler):
            pv.ueber_pldmgr("h", b"x", "irgendwas.txt")


class WegwahlTests(unittest.TestCase):
    """Welcher Weg genommen wird - der Kern des Moduls."""

    def setUp(self):
        self.gesichert = (pv.port_offen, pv.ueber_elfldr, pv.ueber_pldmgr,
                          pv.elfldr_aufwecken)
        self.tmp = tempfile.mkdtemp()
        self.elfldr = os.path.join(self.tmp, "elfldr.elf")
        with open(self.elfldr, "wb") as fh:
            fh.write(b"\x7fELF" + b"\x00" * 40)

    def tearDown(self):
        (pv.port_offen, pv.ueber_elfldr, pv.ueber_pldmgr,
         pv.elfldr_aufwecken) = self.gesichert
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ports(self, elfldr_offen, pldmgr_offen):
        pv.port_offen = lambda host, port, timeout=1.5: (
            elfldr_offen if int(port) == pv.ELFLDR_PORT else pldmgr_offen)

    def test_offener_elfldr_wird_direkt_genommen(self):
        self._ports(True, True)
        pv.ueber_elfldr = lambda *a, **k: "ausgabe"
        pv.ueber_pldmgr = lambda *a, **k: self.fail("Umweg genommen")
        weg, ausgabe, _b = pv.senden("h", b"x", "a.elf",
                                     elfldr_pfad=self.elfldr)
        self.assertEqual(weg, pv.WEG_ELFLDR)
        self.assertEqual(ausgabe, "ausgabe")

    def test_geschlossener_elfldr_wird_geweckt(self):
        # Der eigentliche Gewinn: Danach steht 9021 offen, und die Ausgabe
        # ist wieder da. Nur deshalb lohnt der Umweg ueberhaupt.
        self._ports(False, True)
        geweckt = []
        pv.elfldr_aufwecken = lambda *a, **k: (geweckt.append(1) or True)
        pv.ueber_elfldr = lambda *a, **k: "ausgabe nach dem Wecken"
        pv.ueber_pldmgr = lambda *a, **k: self.fail("haette wecken sollen")
        weg, ausgabe, bemerkung = pv.senden("h", b"x", "a.elf",
                                            elfldr_pfad=self.elfldr)
        self.assertEqual(weg, pv.WEG_GEWECKT)
        self.assertEqual(ausgabe, "ausgabe nach dem Wecken")
        self.assertEqual(bemerkung, "elfldr.elf")
        self.assertEqual(len(geweckt), 1)

    def test_ohne_elfldr_datei_bleibt_der_direkte_weg(self):
        self._ports(False, True)
        pv.ueber_pldmgr = lambda *a, **k: "/data/pldmgr/payloads/a/a.elf"
        weg, ausgabe, bemerkung = pv.senden("h", b"x", "a.elf", elfldr_pfad="")
        self.assertEqual(weg, pv.WEG_PLDMGR)
        self.assertEqual(ausgabe, "", "ohne elfldr gibt es keine Ausgabe")
        self.assertIn("a.elf", bemerkung)

    def test_gescheitertes_wecken_faellt_auf_den_direkten_weg(self):
        self._ports(False, True)
        pv.elfldr_aufwecken = lambda *a, **k: False
        pv.ueber_pldmgr = lambda *a, **k: "/data/pldmgr/payloads/a/a.elf"
        weg, _ausgabe, _b = pv.senden("h", b"x", "a.elf",
                                      elfldr_pfad=self.elfldr)
        self.assertEqual(weg, pv.WEG_PLDMGR)

    def test_beide_zu_ist_ein_fehler_mit_beiden_ports(self):
        self._ports(False, False)
        with self.assertRaises(pv.VersandFehler) as fall:
            pv.senden("h", b"x", "a.elf")
        text = str(fall.exception)
        self.assertIn("9021", text)
        self.assertIn("8084", text)


class EinbauTests(unittest.TestCase):
    """Verdrahtung im Hauptprogramm."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, "rb") as fh:
            cls.quelle = fh.read().decode("utf-8")

    def test_der_zentrale_sender_benutzt_das_modul(self):
        # Alle Wege - ftpsrv nachladen, KLOG, MicroMount, Autoloader - gehen
        # durch _send_payload_to_ps5. Nur dort eingesetzt, wirkt es ueberall.
        self.assertIn("payload_versand.senden", self.quelle)

    def test_das_mitgelieferte_elfldr_wird_durchgereicht(self):
        self.assertIn("elfldr_pfad=self._elfldr_payload_path()", self.quelle)

    def test_elfldr_liegt_bei(self):
        pfad = PROJEKT / "helloworld" / pv.ELFLDR_NAME
        self.assertTrue(pfad.is_file(), "%s fehlt" % pv.ELFLDR_NAME)
        with open(pfad, "rb") as fh:
            self.assertEqual(fh.read(4), b"\x7fELF")

    def test_texte_gibt_es_in_beiden_sprachen(self):
        for schluessel in ("payload.elfldr_geweckt", "payload.via_pldmgr",
                           "payload.sent_pldmgr", "webkit.credit"):
            eintrag = i18n.STRINGS[schluessel]
            self.assertTrue(eintrag.get("de"), schluessel)
            self.assertTrue(eintrag.get("en"), schluessel)

    def test_meldung_sagt_dass_der_port_offen_bleibt(self):
        # Das ist die Nachricht, die der Anwender braucht: Er muss nicht
        # jedes Mal neu wecken.
        text = i18n.STRINGS["payload.elfldr_geweckt"]["de"]
        self.assertIn("{port}", text)
        self.assertIn("offen", text)


class WebkitDankTests(unittest.TestCase):
    """Der Dank an itsPLK und das Bild daneben."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, "rb") as fh:
            cls.quelle = fh.read().decode("utf-8")

    def _gui(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda key, **kw: key
        return gui

    def test_dank_steht_im_fenster(self):
        self.assertIn('self._t("webkit.credit")', self.quelle)

    def test_dank_nennt_itsplk(self):
        for sprache in ("de", "en"):
            self.assertIn("itsPLK", i18n.STRINGS["webkit.credit"][sprache])

    def test_fehlendes_bild_stoert_nicht(self):
        # Ohne Datei muss das Fenster trotzdem aufgehen - deshalb None statt
        # einer Ausnahme. Geprueft wird gegen einen leeren Ordner: Solange
        # ein Bild beiliegt, sagte dieser Test sonst nichts mehr aus.
        gui = self._gui()
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, gui._WEBKIT_ORDNER))
            echt = APP._bundled_resource
            APP._bundled_resource = lambda *teile: os.path.join(tmp, *teile)
            try:
                self.assertIsNone(gui._webkit_bild_laden())
            finally:
                APP._bundled_resource = echt
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_das_beiliegende_bild_ist_brauchbar(self):
        # Nicht ueber _webkit_bild_laden: Das braucht eine Tk-Wurzel und
        # liefert ohne sie stillschweigend None - der Test saehe gruen aus,
        # auch wenn die Datei fehlte oder unlesbar waere.
        from PIL import Image
        gui = self._gui()
        pfad = APP._bundled_resource(gui._WEBKIT_ORDNER, gui._WEBKIT_BILD)
        self.assertTrue(pfad, "%s liegt nicht bei" % gui._WEBKIT_BILD)
        with Image.open(pfad) as bild:
            breite, hoehe = bild.size
        self.assertGreaterEqual(min(breite, hoehe), gui._WEBKIT_BILD_KANTE,
                                "kleiner als die Anzeigekante - wuerde weich")
        self.assertLess(os.path.getsize(pfad), 1024 * 1024,
                        "unnoetig gross fuer eine 84-px-Anzeige")

    def test_bild_wird_rund_und_quadratisch_geliefert(self):
        from PIL import Image
        gui = self._gui()
        tmp = tempfile.mkdtemp()
        try:
            ordner = os.path.join(tmp, gui._WEBKIT_ORDNER)
            os.makedirs(ordner)
            # Bewusst nicht quadratisch: Der Zuschnitt soll das richten.
            Image.new("RGB", (300, 200), (10, 20, 30)).save(
                os.path.join(ordner, gui._WEBKIT_BILD))
            echt = APP._bundled_resource
            APP._bundled_resource = lambda *teile: os.path.join(tmp, *teile)
            try:
                import tkinter
                try:
                    wurzel = tkinter.Tk()
                    wurzel.withdraw()
                except tkinter.TclError:
                    self.skipTest("keine Anzeige verfuegbar")
                try:
                    bild = gui._webkit_bild_laden()
                    self.assertIsNotNone(bild)
                    self.assertEqual(bild.width(), gui._WEBKIT_BILD_KANTE)
                    self.assertEqual(bild.height(), gui._WEBKIT_BILD_KANTE)
                finally:
                    wurzel.destroy()
            finally:
                APP._bundled_resource = echt
        finally:
            shutil.rmtree(tmp, ignore_errors=True)



class WebkitSendewegTests(unittest.TestCase):
    """Der Installer-Versand, wenn Port 9021 zu ist.

    Der USB-Weg bleibt ausdruecklich erhalten: Er traegt auch dann noch,
    wenn gar kein Dienst mehr antwortet - der Payload Manager nicht.
    """

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, "rb") as fh:
            cls.quelle = fh.read().decode("utf-8")

    def test_beide_wege_stehen_zur_wahl(self):
        self.assertIn('self._t("webkit.weg_pldmgr")', self.quelle)
        self.assertIn('self._t("webkit.weg_usb")', self.quelle)

    def test_der_usb_weg_ist_nicht_entfallen(self):
        self.assertIn("_webkit_auf_usb_ablegen", self.quelle)

    def test_ohne_payload_manager_bleibt_es_beim_alten_dialog(self):
        # Antwortet auch 8084 nicht, soll der Anwender nicht vor einer
        # Auswahl mit einem einzigen Eintrag stehen.
        self.assertIn("if len(wege) == 1:", self.quelle)

    def test_die_wahl_haengt_am_port_des_payload_managers(self):
        # Ueber _ps5_port_open, damit die Pruefung stillzulegen ist. Der
        # direkte Modulaufruf ging in den Tests an eine echte Konsole und
        # oeffnete dort einen Dialog, der auf eine Antwort wartete.
        self.assertIn("self._ps5_port_open(ip, payload_versand.PLDMGR_PORT)",
                      self.quelle)
        self.assertNotIn("payload_versand.port_offen(ip,", self.quelle)

    def test_texte_gibt_es_in_beiden_sprachen(self):
        for schluessel in ("webkit.weg_pldmgr", "webkit.weg_usb",
                           "webkit.port_closed_wahl"):
            eintrag = i18n.STRINGS[schluessel]
            self.assertTrue(eintrag.get("de"), schluessel)
            self.assertTrue(eintrag.get("en"), schluessel)

    def test_die_frage_erklaert_beide_wege(self):
        text = i18n.STRINGS["webkit.port_closed_wahl"]["de"]
        self.assertIn("{ip}", text)
        self.assertIn("{port}", text)
        self.assertIn("elfldr", text)
        self.assertIn("USB", text)

if __name__ == "__main__":
    unittest.main(verbosity=2)
