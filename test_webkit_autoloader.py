"""Tests für den WebKit Autoloader (Dateien, Fassungen, drei Wege).

Bis v1.9.62 gab es dafür einen Knopf in der Titelleiste (er saß dort, wo bis
v1.8.100 SHADOWMOUNT+ stand; jener ist ins Menü „WEITERE TOOLS" gewandert) und
ein rahmenloses Fenster; seit v1.9.63 ist es die Seite „2. WebKit Autoloader“ der
Ansicht KONSOLE (test_webkit_seite). Die drei Wege sind geblieben:

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
    def _senden(ip, pfad, port=0, lesezeit=30.0, rueckmeldung=None):
        g.gesendet.append((ip, pfad))
        if rueckmeldung is not None:
            rueckmeldung.update(weg="elfldr", ausgabe="", bemerkung="", bytes=4711, dauer=0.2)
        return True, "4711 Bytes"

    g._send_payload_to_ps5 = _senden

    # Seit dem 05.09.2026 laeuft der Sendeweg ueber Arbeitsfaeden:
    # Sondierung und Upload blockierten sonst den Hauptstrang. Die
    # Rueckmeldung geht dabei ueber _spaeter_im_fenster - hier direkt
    # ausgefuehrt, damit die Pruefungen synchron bleiben. Auf den Faden
    # selbst wartet _fertig_abwarten() unten.
    g._spaeter_im_fenster = lambda _fenster, rueckruf, *a: rueckruf(*a)
    g._set_status_fluechtig = lambda *a, **k: None
    return g


def _fertig_abwarten(frist: float = 10.0) -> None:
    """Wartet, bis die WebKit-Arbeitsfaeden durch sind."""
    import threading, time

    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        offen = [f for f in threading.enumerate()
                 if (f.name or "").startswith("webkit-") and f.is_alive()]
        if not offen:
            return
        time.sleep(0.01)


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


class FassungTests(unittest.TestCase):
    """Die Fassung steckt im Dateinamen (02.10.2026; seit v1.9.63 waehlt die Seite).

    Wunsch des Nutzers: "Man weiss ja gar nicht welche man sonst benutzt." Die
    Fassung steht im Dateinamen - nach derselben Stelle sortiert das Programm,
    wenn mehrere Dateien im Ordner liegen, und nach ihr bietet die Seite "WebKit
    Autoloader" die Auswahl an. Welche Fassungen beiliegen und ob jede vollstaendig
    ist, prueft test_webkit_seite.
    """

    def test_die_fassung_aus_dem_dateinamen(self) -> None:
        lesen = PS5ConverterGUI._webkit_fassung_aus_name
        self.assertEqual(lesen("webkit-autoloader-installer_v0.5.2.elf"), "0.5.2")
        self.assertEqual(lesen("webkit-autoloader-host_v0.10.0.exe"), "0.10.0",
                         "zweistellige Teile muessen ganz bleiben")
        self.assertEqual(lesen("webkit-autoloader-host_v1.py"), "1")
        self.assertEqual(lesen("webkit-autoloader-installer.elf"), "")
        self.assertEqual(lesen(""), "")

    def test_ein_name_mit_zweiter_nummer_zaehlt_die_erste(self) -> None:
        """Dieselbe Stelle wie beim Sortieren - sonst zeigte die Auswahl eine
        andere Datei an als die, die gestartet wird.

        So hiess die Datei, die der Nutzer am 28.09.2026 selbst gebaut hatte:
        der Payload Manager steckt im Namen, die Fassung davor.
        """
        name = "webkit-autoloader-installer_v0.4.0_(inkl. plmgr_v0.5.1 fix2).elf"
        self.assertEqual(PS5ConverterGUI._webkit_fassung_aus_name(name), "0.4.0")
        schluessel = PS5ConverterGUI._webkit_versionsschluessel(name)
        self.assertEqual(schluessel[:3], (0, 4, 0))

    def test_beide_sprachen_haben_dieselben_platzhalter(self) -> None:
        import re
        for schluessel, erwartet in (("webkit.fassung_neueste", {"version"}),
                                     ("webkit.fassung_unvollstaendig", {"fehlt"}),
                                     ("webkit.log_gesendet", {"datei", "ip", "groesse"}),
                                     ("webkit.log_usb", {"datei", "usb"})):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertEqual(set(re.findall(r"\{(\w+)\}", text)), erwartet)

    def test_die_neueste_fassung_liegt_vollstaendig_bei(self) -> None:
        """Ohne Nummer gewinnt die hoechste - alle drei Arten tragen dieselbe."""
        g = PS5ConverterGUI.__new__(PS5ConverterGUI)
        nummern = {art: PS5ConverterGUI._webkit_fassung_aus_name(Path(g._webkit_datei(art)).name)
                   for art in ("exe", "py", "elf")}
        self.assertTrue(all(nummern.values()), nummern)
        self.assertEqual(1, len(set(nummern.values())), nummern)


class OberflaecheTests(unittest.TestCase):
    """Knopf und Klappliste."""

    def test_webkit_steht_nicht_mehr_in_der_titelleiste(self) -> None:
        """Seit dem 04.10.2026 eine Seite der Ansicht KONSOLE (Knopf 2), kein Fenster."""
        namen = [n for n, _k, _b in PS5ConverterGUI._FALTBARE_TITELKNOEPFE]
        self.assertNotIn("_btn_webkit_title", namen)
        self.assertEqual(("konsole.btn_webkit", "webkit"), PS5ConverterGUI._KONSOLE_KNOEPFE[1])
        self.assertFalse(hasattr(PS5ConverterGUI, "_show_webkit_autoloader"))

    def test_shadowmount_ist_in_die_klappliste_gewandert(self) -> None:
        namen = [n for n, _k, _b in PS5ConverterGUI._FALTBARE_TITELKNOEPFE]
        self.assertNotIn("_btn_shadowmount_title", namen,
                         "SHADOWMOUNT+ sitzt noch als eigener Knopf")
        befehle = [b for _k, b in PS5ConverterGUI._MORE_TOOLS_ENTRIES]
        self.assertIn("_show_shadowmount_editor", befehle)

    def test_kein_verwaister_verweis_auf_die_alten_knoepfe(self) -> None:
        """Sprachwechsel und Farbtabelle nennen Knöpfe beim Namen.

        Bleibt dort ein Name stehen, den es nicht mehr gibt, faellt das
        nicht auf – die Schleifen ueberspringen Fehlendes stillschweigend.
        """
        with io.open(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py",
                     encoding="utf-8") as fh:
            quelle = fh.read()
        self.assertNotIn("_btn_shadowmount_title", quelle)
        self.assertNotIn("_btn_webkit_title", quelle)

    def test_texte_sind_zweisprachig(self) -> None:
        schluessel = [k for k in STRINGS if k.startswith("webkit.")]
        self.assertGreaterEqual(len(schluessel), 25)
        for name in schluessel:
            with self.subTest(name):
                self.assertTrue(STRINGS[name].get("de"))
                self.assertTrue(STRINGS[name].get("en"))
        self.assertNotIn("titlebar.webkit", STRINGS)


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
        _fertig_abwarten()
        self.assertEqual(len(g.gesendet), 1, "nicht ueber Port 9021 geschickt")
        self.assertEqual(g.ftp.abgelegt, [], "trotz Loader den FTP-Weg genommen")

    def test_schweigender_loader_fuehrt_auf_den_usb_weg(self) -> None:
        g = _gui(offene_ports={2121})
        self._mit_dialogen(g, True)
        g._webkit_installer_senden()
        _fertig_abwarten()
        self.assertEqual(g.gesendet, [], "trotz stummem Loader gesendet")
        self.assertEqual(g.ftp.abgelegt, ["STOR /mnt/usb0/%s" % self.elf],
                         "der Installer liegt nicht im Wurzelverzeichnis")
        self.assertEqual(g.ftp_port, [2121], "falscher FTP-Port")

    def test_usb_weg_nimmt_auch_2021(self) -> None:
        g = _gui(offene_ports={2021})
        self._mit_dialogen(g, True)
        g._webkit_installer_senden()
        _fertig_abwarten()
        self.assertEqual(g.ftp_port, [2021])
        self.assertEqual(g.ftp.abgelegt, ["STOR /mnt/usb0/%s" % self.elf])

    def test_wer_nein_sagt_bekommt_nichts_abgelegt(self) -> None:
        g = _gui(offene_ports={2121})
        self._mit_dialogen(g, False)
        g._webkit_installer_senden()
        _fertig_abwarten()
        self.assertEqual(g.ftp.abgelegt, [])
        self.assertEqual(g.gesendet, [])

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
        _fertig_abwarten()
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


class SendeanzeigeTests(InstallerwegTests):
    """Das grosse Feld der Seite zeigt jeden Schritt (Nutzer 06.10.2026: "wie und ob die elf
    gesendet worden ist ... angekommen und geladen")."""

    def _protokoll(self, g) -> str:
        return "".join(g._log_lines)

    def _text(self, schluessel: str) -> str:
        """Der feste Anfang eines Textes (bis zum ersten Platzhalter)."""
        return STRINGS[schluessel]["de"].split("{", 1)[0]

    def setUp(self) -> None:
        super().setUp()
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        alt = getattr(haupt.PS5ConverterGUI, "_current_language", None)
        haupt.PS5ConverterGUI._current_language = "de"
        self.addCleanup(setattr, haupt.PS5ConverterGUI, "_current_language", alt)

    def test_direkter_weg_zeigt_start_port_senden_angekommen_geladen(self) -> None:
        g = _gui(offene_ports={9021, 2121})
        self._mit_dialogen(g, True)
        g._webkit_installer_senden()
        _fertig_abwarten()
        text = self._protokoll(g)
        for schluessel in ("webkit.log_start", "webkit.log_pruefe_port", "webkit.log_port_offen",
                           "webkit.log_sende", "webkit.log_angekommen", "webkit.log_weg_elfldr",
                           "webkit.log_keine_ausgabe"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(self._text(schluessel), text)
        self.assertLess(text.index(self._text("webkit.log_sende")),
                        text.index(self._text("webkit.log_angekommen")))

    def test_die_antwort_der_konsole_steht_im_feld(self) -> None:
        g = _gui(offene_ports={9021})
        self._mit_dialogen(g, True)

        def _senden(ip, pfad, port=0, lesezeit=30.0, rueckmeldung=None):
            rueckmeldung.update(weg="elfldr", ausgabe="autoloader installed", dauer=1.0)
            return True, "4711 B"

        g._send_payload_to_ps5 = _senden
        g._webkit_installer_senden()
        _fertig_abwarten()
        self.assertIn("autoloader installed", self._protokoll(g))
        self.assertNotIn(self._text("webkit.log_keine_ausgabe"), self._protokoll(g))

    def test_nein_steht_als_abgebrochen_im_feld(self) -> None:
        g = _gui(offene_ports={9021})
        self._mit_dialogen(g, False)
        g._webkit_installer_senden()
        _fertig_abwarten()
        self.assertIn(self._text("webkit.log_abgebrochen"), self._protokoll(g))
        self.assertEqual([], g.gesendet)

    def test_usb_weg_prueft_die_groesse_auf_der_konsole(self) -> None:
        g = _gui(offene_ports={2121})
        self._mit_dialogen(g, True)
        groesse = os.path.getsize(g._webkit_datei("elf"))
        g.ftp.size = lambda _pfad: groesse
        g._webkit_installer_senden()
        _fertig_abwarten()
        text = self._protokoll(g)
        for schluessel in ("webkit.log_usb_ftp", "webkit.log_usb_verbunden", "webkit.log_usb_gefunden",
                           "webkit.log_usb_lade", "webkit.log_usb_geprueft", "webkit.log_usb"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(self._text(schluessel), text)

    def test_usb_weg_mit_falscher_groesse_ist_ein_fehler(self) -> None:
        g = _gui(offene_ports={2121})
        self._mit_dialogen(g, True)
        g.ftp.size = lambda _pfad: 3
        g._webkit_installer_senden()
        _fertig_abwarten()
        text = self._protokoll(g)
        self.assertIn(self._text("webkit.log_usb_groesse_falsch"), text)
        self.assertNotIn(self._text("webkit.log_usb_geprueft"), text)
        self.assertNotIn("[OK] Installer", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
