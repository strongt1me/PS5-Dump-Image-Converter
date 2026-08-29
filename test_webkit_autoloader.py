"""Tests für den WebKit Autoloader (Knopf, Fenster, drei Wege).

Der Knopf sitzt dort, wo bis v1.8.100 SHADOWMOUNT+ stand; jener ist ins
Menü „WEITERE TOOLS" gewandert. Dahinter liegt ein rahmenloses Fenster mit
drei Wegen:

* der Host als Windows-Programm,
* derselbe Host als Python-Skript,
* der Installer (``.elf``) auf die Konsole.

Beim Installer gibt es zwei Wege, und **welcher** genommen wird, entscheidet
allein, ob der Payload-Loader auf Port 9021 antwortet. Schweigt er, kommt die
Datei per FTP ins Wurzelverzeichnis eines USB-Datenträgers – von dort holt sie
der Payload Manager der Konsole ab. Der FTP-Port ist dabei nicht fest: Es wird
2121 und danach 2021 probiert, genommen wird der erste, der antwortet.

Getestet wird ohne Konsole und ohne Netz: Die Prüfungen ersetzen
``_ps5_port_open``, ``_send_payload_to_ps5`` und den FTP-Aufbau durch
Attrappen. Gemessen wird, **welcher Weg** genommen wurde.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
from ps5_validator.utils.i18n import STRINGS


class _FTP:
    """Ersatz für eine FTP-Verbindung; merkt sich, was abgelegt wurde."""

    def __init__(self) -> None:
        self.abgelegt: list[str] = []
        self.beendet = False

    def storbinary(self, befehl: str, _fh) -> None:
        self.abgelegt.append(befehl)

    def quit(self) -> None:
        self.beendet = True


def _gui(*, offene_ports: set[int], usb: list[str] | None = None) -> PS5ConverterGUI:
    """Prüfling ohne Tk und ohne Netz."""
    g = PS5ConverterGUI.__new__(PS5ConverterGUI)
    # Die Meldungsfenster bekommen ein Elternfenster genannt; ohne Attrappe
    # bricht schon der erste Zugriff auf self.root ab.
    g.root = None
    g._log_lines = []
    g._append_to_log = g._log_lines.append
    g._load_setting = lambda schluessel, vorgabe="": (
        "192.168.1.94" if schluessel == "ps5_ip" else vorgabe)
    g._fmt_bytes = lambda n: "%d B" % n
    g._ps5_port_open = lambda _ip, port, timeout=1.5: int(port) in offene_ports
    g._ps5_usb_datentraeger = lambda _ftp: list(
        usb if usb is not None else ["/mnt/usb0"])

    g.gemeldet: list[tuple[str, str]] = []
    g.gesendet: list[tuple[str, str]] = []
    g.ftp = _FTP()
    g.ftp_port: list[int] = []

    def _connect(_ip, port=0, **_kw):
        g.ftp_port.append(int(port))
        return g.ftp

    g._ampr_ftp_connect = _connect
    g._send_payload_to_ps5 = lambda ip, pfad, port=0: (
        g.gesendet.append((ip, pfad)) or (True, "4711 Bytes"))
    return g


class AblageTests(unittest.TestCase):
    """Die drei Dateien müssen im Ordner des Benutzers liegen."""

    def test_alle_drei_arten_werden_gefunden(self) -> None:
        g = PS5ConverterGUI.__new__(PS5ConverterGUI)
        for art, name in (("exe", "Host-Programm"), ("py", "Host-Skript"),
                          ("elf", "Installer")):
            with self.subTest(name):
                pfad = g._webkit_datei(art)
                self.assertTrue(pfad, "%s nicht gefunden" % name)
                self.assertTrue(Path(pfad).is_file())
                self.assertGreater(Path(pfad).stat().st_size, 1024)
                self.assertEqual(Path(pfad).parent.name,
                                 PS5ConverterGUI._WEBKIT_ORDNER)

    def test_neuere_fassung_gewinnt(self) -> None:
        """Der Kern der Sache: Wer eine neuere Datei ablegt, bekommt sie.

        Ohne diese Regel bliebe der Name fest verdrahtet, und eine neue
        Fassung im Ordner waere wirkungslos.
        """
        schluessel = PS5ConverterGUI._webkit_versionsschluessel
        self.assertGreater(schluessel("webkit-autoloader-host_v0.5.0.exe"),
                           schluessel("webkit-autoloader-host_v0.4.0.exe"))
        self.assertGreater(schluessel("webkit-autoloader-host_v0.4.1.exe"),
                           schluessel("webkit-autoloader-host_v0.4.exe"),
                           "kuerzere Nummer darf nicht gewinnen")
        self.assertGreater(schluessel("webkit-autoloader-host_v0.10.0.exe"),
                           schluessel("webkit-autoloader-host_v0.9.0.exe"),
                           "zweistellig muss ueber einstellig stehen")

    def test_der_ordner_gehoert_dem_benutzer(self) -> None:
        """Sein Name steht so im Projekt - danach sucht auch der Bauplan."""
        self.assertEqual(PS5ConverterGUI._WEBKIT_ORDNER,
                         "PS5 WebKit Autoloader")
        self.assertTrue((PROJEKT / "PS5 WebKit Autoloader").is_dir())

    def test_alle_drei_bauplaene_nehmen_den_ordner_mit(self) -> None:
        """Ohne Eintrag in der .spec fehlte der Host in der fertigen EXE."""
        for spec in ("PS5ImageConverter_Pro.spec",
                     "PS5ImageConverter_Pro_linux.spec",
                     "PS5ImageConverter_Pro_macos.spec"):
            with self.subTest(spec):
                with io.open(PROJEKT / spec, encoding="utf-8") as fh:
                    text = fh.read()
                self.assertIn(PS5ConverterGUI._WEBKIT_ORDNER, text)


class OberflaecheTests(unittest.TestCase):
    """Knopf und Klappliste."""

    def test_webkit_steht_in_der_leiste(self) -> None:
        namen = [n for n, _k, _b in PS5ConverterGUI._FALTBARE_TITELKNOEPFE]
        self.assertIn("_btn_webkit_title", namen)
        eintrag = [z for z in PS5ConverterGUI._FALTBARE_TITELKNOEPFE
                   if z[0] == "_btn_webkit_title"][0]
        self.assertEqual(eintrag[1], "titlebar.webkit")
        self.assertEqual(eintrag[2], "_show_webkit_autoloader")

    def test_shadowmount_ist_in_die_klappliste_gewandert(self) -> None:
        namen = [n for n, _k, _b in PS5ConverterGUI._FALTBARE_TITELKNOEPFE]
        self.assertNotIn("_btn_shadowmount_title", namen,
                         "SHADOWMOUNT+ sitzt noch als eigener Knopf")
        befehle = [b for _k, b in PS5ConverterGUI._MORE_TOOLS_ENTRIES]
        self.assertIn("_show_shadowmount_editor", befehle)

    def test_kein_verwaister_verweis_auf_den_alten_knopf(self) -> None:
        """Sprachwechsel und Farbtabelle nennen Knöpfe beim Namen.

        Bleibt dort ein Name stehen, den es nicht mehr gibt, faellt das
        nicht auf – die Schleifen ueberspringen Fehlendes stillschweigend.
        """
        with io.open(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py",
                     encoding="utf-8") as fh:
            quelle = fh.read()
        self.assertNotIn("_btn_shadowmount_title", quelle)

    def test_texte_sind_zweisprachig(self) -> None:
        schluessel = [k for k in STRINGS
                      if k.startswith("webkit.") or k == "titlebar.webkit"]
        self.assertGreaterEqual(len(schluessel), 15)
        for name in schluessel:
            with self.subTest(name):
                self.assertTrue(STRINGS[name].get("de"))
                self.assertTrue(STRINGS[name].get("en"))


class FtpPortTests(unittest.TestCase):
    """2121 zuerst, sonst 2021 – und nichts, wenn beide schweigen."""

    def test_bevorzugt_2121(self) -> None:
        g = _gui(offene_ports={2121, 2021})
        self.assertEqual(g._webkit_ftp_port("192.168.1.94"), 2121)

    def test_nimmt_2021_wenn_2121_schweigt(self) -> None:
        g = _gui(offene_ports={2021})
        self.assertEqual(g._webkit_ftp_port("192.168.1.94"), 2021)

    def test_null_wenn_keiner_antwortet(self) -> None:
        g = _gui(offene_ports=set())
        self.assertEqual(g._webkit_ftp_port("192.168.1.94"), 0)


class InstallerwegTests(unittest.TestCase):
    """Welcher der beiden Wege genommen wird."""

    def setUp(self) -> None:
        pfad = PS5ConverterGUI.__new__(PS5ConverterGUI)._webkit_datei("elf")
        if not pfad:
            self.skipTest("Installer liegt nicht bei")
        self.elf = os.path.basename(pfad)

    def _mit_dialogen(self, g: PS5ConverterGUI, antwort: bool) -> None:
        """Haengt Attrappen fuer die Meldungsfenster ein."""
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        self._alt = {n: getattr(haupt.messagebox, n)
                     for n in ("showinfo", "showwarning", "showerror",
                               "askyesno")}
        self.addCleanup(lambda: [setattr(haupt.messagebox, n, f)
                                 for n, f in self._alt.items()])
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(haupt.messagebox, name,
                    lambda titel, text, **_k: g.gemeldet.append((titel, text)))
        setattr(haupt.messagebox, "askyesno",
                lambda titel, text, **_k: (g.gemeldet.append((titel, text))
                                           or antwort))

    def test_offener_loader_bekommt_die_datei_direkt(self) -> None:
        g = _gui(offene_ports={9021, 2121})
        self._mit_dialogen(g, True)
        g._webkit_installer_senden()
        self.assertEqual(len(g.gesendet), 1, "nicht ueber Port 9021 geschickt")
        self.assertEqual(g.ftp.abgelegt, [], "trotz Loader den FTP-Weg genommen")

    def test_schweigender_loader_fuehrt_auf_den_usb_weg(self) -> None:
        g = _gui(offene_ports={2121})
        self._mit_dialogen(g, True)
        g._webkit_installer_senden()
        self.assertEqual(g.gesendet, [], "trotz stummem Loader gesendet")
        self.assertEqual(g.ftp.abgelegt, ["STOR /mnt/usb0/%s" % self.elf],
                         "der Installer liegt nicht im Wurzelverzeichnis")
        self.assertEqual(g.ftp_port, [2121], "falscher FTP-Port")

    def test_usb_weg_nimmt_auch_2021(self) -> None:
        g = _gui(offene_ports={2021})
        self._mit_dialogen(g, True)
        g._webkit_installer_senden()
        self.assertEqual(g.ftp_port, [2021])
        self.assertEqual(g.ftp.abgelegt, ["STOR /mnt/usb0/%s" % self.elf])

    def test_wer_nein_sagt_bekommt_nichts_abgelegt(self) -> None:
        g = _gui(offene_ports={2121})
        self._mit_dialogen(g, False)
        g._webkit_installer_senden()
        self.assertEqual(g.ftp.abgelegt, [])
        self.assertEqual(g.gesendet, [])

    # ---------------------------------------------------------------- Wahl
    #
    # Ist 9021 zu, aber der Payload Manager erreichbar, gibt es zwei Wege.
    # Der USB-Weg bleibt dabei ausdruecklich erhalten: Er traegt auch dann
    # noch, wenn gar kein Dienst mehr antwortet.

    def _mit_wahl(self, g: PS5ConverterGUI, wahl: str) -> None:
        """Legt fest, was der Auswahldialog zurueckgibt, statt ihn zu oeffnen."""
        g.gefragt: list[str] = []

        def _auswahl(_titel, frage, eintraege, parent=None):
            g.gefragt.append(frage)
            g.angeboten = list(eintraege)
            return wahl
        g._auswahl_dialog = _auswahl

    def test_bei_erreichbarem_payload_manager_stehen_zwei_wege(self) -> None:
        g = _gui(offene_ports={2121, 8084})
        self._mit_dialogen(g, True)
        self._mit_wahl(g, "")          # nichts gewaehlt: es passiert nichts
        g._webkit_installer_senden()
        self.assertEqual(len(g.angeboten), 2, g.angeboten)
        self.assertEqual(g.gesendet, [], "ohne Wahl gesendet")
        self.assertEqual(g.ftp.abgelegt, [], "ohne Wahl abgelegt")

    def test_wahl_payload_manager_schickt_die_datei(self) -> None:
        g = _gui(offene_ports={2121, 8084})
        self._mit_dialogen(g, True)
        self._mit_wahl(g, STRINGS["webkit.weg_pldmgr"]["de"])
        g._webkit_installer_senden()
        self.assertEqual(len(g.gesendet), 1, "nicht ueber den Payload Manager")
        self.assertEqual(g.ftp.abgelegt, [], "trotzdem den USB-Weg genommen")

    def test_wahl_usb_legt_weiterhin_ab(self) -> None:
        # Der alte Weg darf durch den neuen nicht verlorengehen.
        g = _gui(offene_ports={2121, 8084})
        self._mit_dialogen(g, True)
        self._mit_wahl(g, STRINGS["webkit.weg_usb"]["de"])
        g._webkit_installer_senden()
        self.assertEqual(g.gesendet, [], "statt USB gesendet")
        self.assertEqual(g.ftp.abgelegt, ["STOR /mnt/usb0/%s" % self.elf])

    def test_ohne_payload_manager_bleibt_der_alte_dialog(self) -> None:
        # Eine Auswahl mit einem einzigen Eintrag waere eine Zumutung.
        g = _gui(offene_ports={2121})
        self._mit_dialogen(g, True)
        self._mit_wahl(g, "sollte nicht gefragt werden")
        g._webkit_installer_senden()
        self.assertEqual(getattr(g, "gefragt", []), [],
                         "hat trotz fehlendem Payload Manager gewaehlt")
        self.assertEqual(g.ftp.abgelegt, ["STOR /mnt/usb0/%s" % self.elf])

    def test_der_hinweis_nennt_beide_dinge(self) -> None:
        """Der Text muss den Payload Manager und die Kachel nennen.

        Ohne beides wuesste niemand, was nach dem Ablegen zu tun ist und wo
        die Kachel danach auftaucht.
        """
        for fassung in STRINGS["webkit.port_closed"].values():
            self.assertIn("Payload Manager", fassung)
        self.assertIn("Medien", STRINGS["webkit.port_closed"]["de"])
        self.assertIn("Media", STRINGS["webkit.port_closed"]["en"])
        for schluessel in ("webkit.send_ok", "webkit.usb_done"):
            self.assertIn("Medien", STRINGS[schluessel]["de"], schluessel)

    def test_ohne_adresse_passiert_nichts(self) -> None:
        g = _gui(offene_ports={9021})
        g._load_setting = lambda _s, vorgabe="": vorgabe
        self._mit_dialogen(g, True)
        g._webkit_installer_senden()
        self.assertEqual(g.gesendet, [])
        self.assertEqual(g.ftp.abgelegt, [])


class HostTests(unittest.TestCase):
    """Der Start des Hosts – ohne ihn wirklich zu starten."""

    def test_python_ist_nie_das_programm_selbst(self) -> None:
        """Aus der EXE heraus liefe sonst die Anwendung ein zweites Mal an."""
        g = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gefunden = g._webkit_python()
        if getattr(sys, "frozen", False):
            self.assertNotEqual(os.path.abspath(gefunden or ""),
                                os.path.abspath(sys.executable))
        else:
            self.assertEqual(gefunden, sys.executable)

    def test_ohne_zustimmung_startet_nichts(self) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        g = PS5ConverterGUI.__new__(PS5ConverterGUI)
        g.root = None
        g._log_lines = []
        g._append_to_log = g._log_lines.append
        alt_frage, alt_popen = haupt.messagebox.askyesno, haupt.subprocess.Popen
        self.addCleanup(lambda: (setattr(haupt.messagebox, "askyesno", alt_frage),
                                 setattr(haupt.subprocess, "Popen", alt_popen)))
        gestartet: list = []
        haupt.messagebox.askyesno = lambda *_a, **_k: False
        haupt.subprocess.Popen = lambda *a, **k: gestartet.append(a)
        g._webkit_host_starten("py")
        self.assertEqual(gestartet, [], "der Host lief trotz Absage an")


if __name__ == "__main__":
    unittest.main(verbosity=2)
