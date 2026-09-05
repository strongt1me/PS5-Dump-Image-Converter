"""Tests fuer die KLOG-Vorabpruefung und den Weg ueber einen USB-Datentraeger.

Ohne laufenden klogsrv blieb das KLOG-Fenster stumm. Beim Druck auf KLOG wird
jetzt zuerst geprueft, ob etwas zuhoert:

1. klogsrv-Port offen  -> Fenster wie bisher
2. sonst Payload-Loader (9021) offen -> Senden anbieten
3. sonst -> Uebertragung auf einen USB-Datentraeger der Konsole anbieten

Beim USB-Weg gilt: Gibt es ``ps5_autoloader/autoload.txt``, kommt der Payload
dorthin und wird eingetragen - unter dem letzten Eintrag zuerst die Pause
``!2000``, darunter der Dateiname. Gibt es den Ordner nicht (Payload Manager),
wird das Wurzelverzeichnis angeboten.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils.i18n import STRINGS, translate

QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
K = APP.PS5ConverterGUI


def _blank():
    return K.__new__(K)


class AutoloadTests(unittest.TestCase):
    """Der Eintrag in autoload.txt."""

    def test_leere_datei_bekommt_nur_den_namen(self):
        neu, ergaenzt = K._autoload_ergaenzen(_blank(), "", "klog.elf")
        self.assertTrue(ergaenzt)
        self.assertEqual(neu, "klog.elf\n")

    def test_pause_kommt_vor_den_namen_wenn_eintraege_da_sind(self):
        neu, ergaenzt = K._autoload_ergaenzen(_blank(), "etaHEN.elf\n", "klog.elf")
        self.assertTrue(ergaenzt)
        self.assertEqual(neu, "etaHEN.elf\n!2000\nklog.elf\n")

    def test_mehrere_eintraege_bleiben_erhalten(self):
        alt = "etaHEN.elf\n!3000\nftpsrv.elf\n"
        neu, _ = K._autoload_ergaenzen(_blank(), alt, "klog.elf")
        self.assertTrue(neu.startswith(alt))
        self.assertTrue(neu.endswith("!2000\nklog.elf\n"))

    def test_kein_doppelter_eintrag(self):
        alt = "etaHEN.elf\n!2000\nklog.elf\n"
        neu, ergaenzt = K._autoload_ergaenzen(_blank(), alt, "klog.elf")
        self.assertFalse(ergaenzt)
        self.assertEqual(neu, alt)

    def test_gross_klein_zaehlt_als_gleicher_eintrag(self):
        _neu, ergaenzt = K._autoload_ergaenzen(_blank(), "KLOG.ELF\n", "klog.elf")
        self.assertFalse(ergaenzt)

    def test_leerzeilen_am_ende_werden_nicht_vermehrt(self):
        neu, _ = K._autoload_ergaenzen(_blank(), "etaHEN.elf\n\n\n", "klog.elf")
        self.assertEqual(neu, "etaHEN.elf\n!2000\nklog.elf\n")

    def test_nur_kommentare_gelten_nicht_als_eintrag(self):
        neu, _ = K._autoload_ergaenzen(_blank(), "# nichts hier\n", "klog.elf")
        self.assertNotIn("!2000", neu)
        self.assertTrue(neu.endswith("klog.elf\n"))


class _FtpAttrappe:
    """Liefert vorgegebene LIST-Zeilen."""

    def __init__(self, zeilen):
        self.zeilen = zeilen

    def cwd(self, _pfad):
        return None

    def retrlines(self, befehl, rueckruf):
        if befehl != "LIST":
            raise AssertionError("erwartet wird LIST")
        for z in self.zeilen:
            rueckruf(z)


class UsbErkennungTests(unittest.TestCase):
    """An der echten Konsole abgenommene Zeilen (Firmware 12.00)."""

    ECHT = [
        "drwxrwxrwx 19 0 0 1088 Aug 16 14:01 .",
        "drwxrwxrwx 1 0 0 16384 Jan  1  2000 ..",
        "drwxrwx--- 2 0 0 0 Aug 16 14:00 ext0",
        "dr-xr-xr-x 2 0 0 0 Aug 16 14:00 usb1",
        "drwxrwxrwx 1 4294967295 4294967295 32768 Jan  1  2000 usb0",
        "dr-xr-xr-x 2 0 0 0 Aug 16 14:00 usb3",
        "drwxrwxrwx 6 0 0 256 Aug 16 14:45 shadowmnt",
    ]

    def test_nur_der_wirklich_eingehaengte_traeger(self):
        gefunden = K._ps5_usb_datentraeger(_blank(), _FtpAttrappe(self.ECHT))
        self.assertEqual(gefunden, ["/mnt/usb0"])

    def test_leere_einhaengepunkte_fallen_weg(self):
        gefunden = K._ps5_usb_datentraeger(_blank(), _FtpAttrappe(self.ECHT))
        for tot in ("/mnt/usb1", "/mnt/usb3", "/mnt/ext0"):
            self.assertNotIn(tot, gefunden)

    def test_fremde_ordner_werden_ignoriert(self):
        gefunden = K._ps5_usb_datentraeger(_blank(), _FtpAttrappe(self.ECHT))
        self.assertNotIn("/mnt/shadowmnt", gefunden)

    def test_mehrere_traeger_werden_sortiert(self):
        zeilen = self.ECHT + [
            "drwxrwxrwx 1 0 0 32768 Jan  1  2000 usb2",
            "drwxrwxrwx 1 0 0 16384 Jan  1  2000 ext1",
        ]
        self.assertEqual(K._ps5_usb_datentraeger(_blank(), _FtpAttrappe(zeilen)),
                         ["/mnt/ext1", "/mnt/usb0", "/mnt/usb2"])

    def test_fehler_beim_listen_gibt_leere_liste(self):
        class Kaputt:
            def cwd(self, _p):
                raise OSError("weg")

            def retrlines(self, *_a):
                raise OSError("weg")

        self.assertEqual(K._ps5_usb_datentraeger(_blank(), Kaputt()), [])


class PayloadTests(unittest.TestCase):
    def test_klogsrv_liegt_bei(self):
        self.assertTrue((PROJEKT / "helloworld" / K._KLOG_PAYLOAD).is_file())

    def test_pfad_wird_gefunden(self):
        self.assertTrue(K._klog_payload_pfad(_blank()))

    def test_pause_ist_2000(self):
        self.assertEqual(K._PS5_AUTOLOAD_PAUSE, "!2000")


class QuelltextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = QUELLE.read_text(encoding="utf-8")

    def test_knopf_ruft_die_pruefung(self):
        """Der Knopf muss ueber die gepruefte Fassung gehen.

        Seit dem Umschalter haengt am Knopf nicht mehr die gebundene
        Methode, sondern ``_werkzeugknopf("...")``. Die Absicht ist
        dieselbe geblieben: nie die ungepruefte Fassung.
        """
        self.assertIn('self._werkzeugknopf("_show_klog_window_geprueft")',
                      self.text)
        self.assertNotIn('self._werkzeugknopf("_show_klog_window")', self.text)
        self.assertNotIn("command=self._show_klog_window,", self.text)

    def _methode(self, name):
        """Die Methode aus PS5ConverterGUI - ueber den Syntaxbaum.

        Frueher stand hier ein fester Zeichenausschnitt (``[stelle:stelle+700]``).
        Der haelt nicht: Ein laengerer Erklaertext schob die gesuchte Zeile aus
        dem Fenster heraus, und die Pruefung fiel, obwohl nichts kaputt war -
        am 05.09.2026 genau so passiert.
        """
        import ast

        baum = ast.parse(self.text)
        klasse = next(k for k in baum.body
                      if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        for k in klasse.body:
            if isinstance(k, ast.FunctionDef) and k.name == name:
                return k
        self.fail("Methode %s nicht gefunden" % name)

    def test_pruefung_darf_das_fenster_nicht_verhindern(self):
        """Das Fenster geht auf, egal was die Messung ergibt."""
        import ast

        knopf = self._methode("_show_klog_window_geprueft")
        oeffnet = [k for k in ast.walk(knopf)
                   if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "_show_klog_window"]
        self.assertTrue(oeffnet, "Das Fenster wird gar nicht mehr geoeffnet.")
        faengt = [k for k in ast.walk(knopf) if isinstance(k, ast.Try)]
        self.assertTrue(faengt,
                        "Eine Ausnahme der Messung reisst wieder alles mit.")

    def test_die_messung_blockiert_den_hauptstrang_nicht(self):
        """Zwei Portpruefungen mit je 1,5 s gehoeren nicht vor das Fenster.

        Bis zum 05.09.2026 lief die ganze Vorabpruefung im Hauptstrang, und
        zwar bevor das Fenster aufging: Ist die Konsole aus, stand das
        Programm nach dem Klick rund drei Sekunden still.
        """
        import ast

        knopf = self._methode("_show_klog_window_geprueft")
        faeden = [k for k in ast.walk(knopf)
                  if isinstance(k, ast.Call)
                  and getattr(k.func, "attr", "") == "Thread"]
        self.assertTrue(faeden, "Die Messung laeuft wieder im Hauptstrang.")
        # Und die Messung selbst darf kein Tk anfassen.
        messung = self._methode("_klog_erreichbarkeit")
        dialoge = [k.lineno for k in ast.walk(messung)
                   if isinstance(k, ast.Call)
                   and getattr(getattr(k.func, "value", None), "id", "") == "messagebox"]
        self.assertEqual([], dialoge,
                         "Zeile(n) %s zeigen einen Dialog aus dem Arbeitsfaden."
                         % dialoge)

    def test_die_messung_nimmt_die_werte_des_fensters(self):
        """Nicht die zentralen - sonst urteilt sie ueber etwas anderes.

        Das KLOG-Fenster arbeitet mit eigenen Werten (``klog_ip``,
        ``klog_port``) und speichert sie beim Verbinden selbst. Die Messung
        las bis zum 05.09.2026 nur die zentralen: Wer die Adresse allein im
        Fenster eingetragen hatte, bekam die Pruefung nie zu sehen - sie stieg
        bei leerem zentralen Wert wortlos aus. Und wich der dort gespeicherte
        Port ab, bot sie das Senden an, obwohl klogsrv laengst lief.
        """
        import ast

        messung = ast.unparse(self._methode("_klog_erreichbarkeit"))
        for schluessel in ("klog_ip", "klog_port"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(
                    "_ps5_wert_oder_zentral(%r" % schluessel, messung,
                    "%s wird nicht ueber den Fensterwert geholt." % schluessel)

    def test_reihenfolge_klog_dann_loader_dann_usb(self):
        """Erst klogsrv, dann der Loader, dann USB - jetzt ueber zwei Methoden."""
        import ast

        messung = ast.unparse(self._methode("_klog_erreichbarkeit"))
        self.assertLess(messung.index("_ps5_klog_port"),
                        messung.index("_PAYLOAD_SEND_PORT"),
                        "klogsrv muss zuerst gefragt werden - laeuft er, gibt "
                        "es nichts anzubieten.")
        anbieten = ast.unparse(self._methode("_klog_anbieten"))
        self.assertLess(anbieten.index("_PAYLOAD_SEND_PORT"),
                        anbieten.index("_klog_auf_usb_ablegen"),
                        "Der USB-Weg ist der letzte Ausweg, nicht der erste.")


class UebersetzungTests(unittest.TestCase):
    SCHLUESSEL = ("klog.preflight.title", "klog.preflight.send_over_loader",
                  "klog.preflight.offer_usb", "klog.usb.none_found",
                  "klog.usb.offer_root", "klog.usb.done_autoloader",
                  "klog.usb.done_root", "klog.usb.already_listed",
                  "klog.usb.failed", "klog.usb.payload_missing")

    def test_alle_in_beiden_sprachen(self):
        for schluessel in self.SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                for sprache in ("de", "en"):
                    self.assertTrue(translate(sprache, schluessel).strip())

    def test_platzhalter_werden_gefuellt(self):
        text = translate("de", "klog.preflight.offer_usb", ip="1.2.3.4", port=3232,
                         loader=9021, datei="klog.elf")
        for teil in ("1.2.3.4", "3232", "9021", "klog.elf"):
            self.assertIn(teil, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
