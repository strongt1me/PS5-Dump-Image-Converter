# -*- coding: utf-8 -*-
"""Stufe 3 der Ansicht KONSOLE: holen, zurueckspielen, Spielstaende.

Geprueft wird gegen einen **echten** kleinen FTP-Server auf diesem Rechner
(``_FtpStube``), nicht gegen eine Nachbildung von ``ftplib``. Grund: Die
Regeln, um die es hier geht, stehen zwischen den Zeilen des Protokolls -
wann eine Datenverbindung aufgemacht wird, wann eine Datei vollstaendig
angekommen ist, und vor allem: dass ein Abbruch erst **nach** der laufenden
Datei greift. Ein Mock haette genau das nicht gezeigt.

Die wichtigste Pruefung ist :meth:`AbbruchTests.test_abbruch_beendet_erst_die_laufende_datei`:
Ein mitten im ``RETR`` abgebrochener Download legt ftpsrv auf der echten
Konsole lahm (17.08.2026, nur ein Neustart half). Der Test setzt den
Abbruch **waehrend** der ersten Datei und misst, dass sie trotzdem
vollstaendig auf der Platte liegt und erst danach Schluss ist.
"""
from __future__ import annotations

import os
import posixpath
import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import konsole_dienste as kd       # noqa: E402
from ps5_validator.utils import konsole_ftp as kf           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

PROJEKT = Path(__file__).resolve().parent

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001 - ohne Anzeige laufen nur die anderen Tests
    _WURZEL = None
    _TK_DA = False


class _FtpStube:
    """Ein winziger FTP-Server auf 127.0.0.1 - genug fuer ftplib.

    Beherrscht, was ``konsole_ftp`` braucht: Anmeldung ohne Kennwort,
    ``TYPE``, ``PASV``, ``MLSD``, ``RETR``, ``STOR``, ``MKD``, ``QUIT``.
    Er bedient **eine** Steuerverbindung nach der anderen; mehr braucht es
    nicht, weil jede Funktion des Moduls ihre Verbindung selbst auf- und
    abbaut.
    """

    def __init__(self, wurzel: Path, *, mlsd_wie_0211: bool = False) -> None:
        self.wurzel = Path(wurzel)
        #: Wie ftpsrv 0.21.1 (cmd.c, ftp_cmd_MLSD): MLSD uebergeht seinen
        #: Pfad und listet das Arbeitsverzeichnis.
        self.mlsd_wie_0211 = mlsd_wie_0211
        #: Zaehlt die Auflistungen - ein Klient, der im Kreis laeuft, wird
        #: nach 300 mit "421" abgewiesen, statt den Test ewig laufen zu lassen.
        self.auflistungen = 0
        self.horcher = socket.socket()
        self.horcher.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.horcher.bind(("127.0.0.1", 0))
        self.horcher.listen(4)
        self.port = self.horcher.getsockname()[1]
        self.laeuft = True
        #: Welche Dateien wurden tatsaechlich abgeholt? Das ist die Messung.
        self.geholt: list[str] = []
        #: Welche RETR hat der Klient bis zum letzten Byte abgenommen?
        self.fertig_gesendet: list[str] = []
        self.faden = threading.Thread(target=self._bedienen, daemon=True,
                                      name="ftp-stube")
        self.faden.start()

    # -- Dienst -------------------------------------------------------

    def __enter__(self) -> "_FtpStube":
        return self

    def __exit__(self, *_rest) -> None:
        self.schliessen()

    def schliessen(self) -> None:
        self.laeuft = False
        try:
            self.horcher.close()
        except OSError:
            pass

    def _bedienen(self) -> None:
        while self.laeuft:
            try:
                verbindung, _ = self.horcher.accept()
            except OSError:
                return
            threading.Thread(target=self._sitzung, args=(verbindung,),
                             daemon=True, name="ftp-sitzung").start()

    # -- eine Sitzung -------------------------------------------------

    def _sitzung(self, steuer: socket.socket) -> None:
        steuer.settimeout(10.0)
        datei = steuer.makefile("rwb")
        datenhorcher: "socket.socket | None" = None
        cwd = "/"
        try:
            self._sagen(datei, "220 ftp-stube bereit")
            while True:
                zeile = datei.readline()
                if not zeile:
                    return
                befehl, _, rest = zeile.decode("utf-8", "replace").strip(
                ).partition(" ")
                befehl = befehl.upper()

                if befehl in ("USER", "PASS"):
                    self._sagen(datei, "230 angemeldet" if befehl == "PASS"
                                else "331 weiter")
                elif befehl == "TYPE":
                    self._sagen(datei, "200 Typ gesetzt")
                elif befehl == "PWD":
                    self._sagen(datei, '257 "%s"' % cwd)
                elif befehl == "CWD":
                    ziel = rest.strip() or "/"
                    neu = posixpath.normpath(
                        ziel if ziel.startswith("/") else posixpath.join(cwd, ziel))
                    if (self.wurzel / neu.lstrip("/")).is_dir():
                        cwd = neu
                        self._sagen(datei, "250 OK")
                    else:
                        self._sagen(datei, "550 No such directory")
                elif befehl == "MLSD":
                    self.auflistungen += 1
                    if self.auflistungen > 300:
                        self._sagen(datei, "421 zu viele Auflistungen - im Kreis?")
                        return
                    if datenhorcher is None:
                        self._sagen(datei, "425 kein PASV")
                        continue
                    ort = cwd if (self.mlsd_wie_0211 or not rest.strip()) else rest
                    self._uebertragen(datei, datenhorcher, befehl, ort)
                    datenhorcher = None
                elif befehl == "PASV":
                    datenhorcher = socket.socket()
                    datenhorcher.bind(("127.0.0.1", 0))
                    datenhorcher.listen(1)
                    datenhorcher.settimeout(10.0)
                    port = datenhorcher.getsockname()[1]
                    self._sagen(datei, "227 Entering Passive Mode "
                                       "(127,0,0,1,%d,%d)"
                                % (port // 256, port % 256))
                elif befehl in ("RETR", "STOR"):
                    if datenhorcher is None:
                        self._sagen(datei, "425 kein PASV")
                        continue
                    self._uebertragen(datei, datenhorcher, befehl, rest)
                    datenhorcher = None
                elif befehl == "MKD":
                    (self.wurzel / rest.strip("/")).mkdir(parents=True,
                                                          exist_ok=True)
                    self._sagen(datei, '257 "%s"' % rest)
                elif befehl == "QUIT":
                    self._sagen(datei, "221 tschuess")
                    return
                else:
                    self._sagen(datei, "502 kenne ich nicht")
        except (OSError, ValueError):
            return
        finally:
            try:
                datei.close()
            except OSError:
                pass
            try:
                steuer.close()
            except OSError:
                pass

    def _uebertragen(self, steuer, datenhorcher, befehl: str, rest: str) -> None:
        self._sagen(steuer, "150 Datenverbindung offen")
        try:
            daten, _ = datenhorcher.accept()
        except OSError:
            self._sagen(steuer, "425 keine Datenverbindung")
            return
        try:
            if befehl == "MLSD":
                for zeile in self._mlsd(rest):
                    daten.sendall(zeile.encode("utf-8"))
            elif befehl == "RETR":
                pfad = self._ortsteil(rest)
                self.geholt.append(rest.strip())
                with open(pfad, "rb") as quelle:
                    while True:
                        brocken = quelle.read(8192)
                        if not brocken:
                            break
                        daten.sendall(brocken)
                # Bis zum letzten Byte angenommen - bricht der Klient ab,
                # wirft sendall vorher (wie bei ftpsrv, das dann haengt).
                daten.shutdown(socket.SHUT_WR)
                daten.settimeout(10.0)
                while daten.recv(8192):
                    pass
                self.fertig_gesendet.append(rest.strip())
            else:  # STOR
                pfad = self._ortsteil(rest)
                pfad.parent.mkdir(parents=True, exist_ok=True)
                with open(pfad, "wb") as ziel:
                    while True:
                        brocken = daten.recv(8192)
                        if not brocken:
                            break
                        ziel.write(brocken)
        except OSError:
            pass
        finally:
            try:
                daten.close()
            except OSError:
                pass
            try:
                datenhorcher.close()
            except OSError:
                pass
        self._sagen(steuer, "226 fertig")

    def _ortsteil(self, fern: str) -> Path:
        return self.wurzel / str(fern).strip().lstrip("/")

    def _mlsd(self, fern: str):
        ordner = self._ortsteil(fern)
        if not ordner.is_dir():
            return
        for eintrag in sorted(ordner.iterdir(), key=lambda p: p.name):
            if eintrag.is_dir():
                yield "type=dir;size=0; %s\r\n" % eintrag.name
            else:
                yield "type=file;size=%d; %s\r\n" % (
                    eintrag.stat().st_size, eintrag.name)

    @staticmethod
    def _sagen(datei, text: str) -> None:
        datei.write((text + "\r\n").encode("utf-8"))
        datei.flush()


def _baum_anlegen(wurzel: Path) -> None:
    """Ein kleiner Spielordner, wie ihn der App-Dumper hinterlaesst."""
    (wurzel / "PPSA01234" / "sce_sys").mkdir(parents=True, exist_ok=True)
    (wurzel / "PPSA01234" / "eboot.bin").write_bytes(b"E" * 200000)
    (wurzel / "PPSA01234" / "zweite.bin").write_bytes(b"Z" * 1000)
    (wurzel / "PPSA01234" / "sce_sys" / "param.json").write_bytes(b"{}")


class HilfenTests(unittest.TestCase):
    """Die kleinen Rechnungen - ohne Netz."""

    def test_hoehere_ebene(self):
        for eingabe, erwartet in (("/mnt/usb0/dump", "/mnt/usb0"),
                                  ("/mnt/usb0", "/mnt"),
                                  ("/mnt", "/"),
                                  ("/", "/"),
                                  ("", "/"),
                                  ("/mnt/usb0/", "/mnt")):
            with self.subTest(pfad=eingabe):
                self.assertEqual(erwartet, kf.hoehere_ebene(eingabe))

    def test_menge_lesbar(self):
        self.assertEqual("512 B", kf.menge_lesbar(512))
        self.assertEqual("1.0 KB", kf.menge_lesbar(1024))
        self.assertEqual("1.5 MB", kf.menge_lesbar(int(1.5 * 1024 * 1024)))
        self.assertEqual("0 B", kf.menge_lesbar(-5))

    def test_dauer_nach_gemessener_leitung(self):
        """1,1 MB/s ist die am 20.09.2026 gemessene Leitung zur Konsole."""
        sekunden = kf.dauer_schaetzen(1.1 * 1024 * 1024)
        self.assertAlmostEqual(1.0, sekunden, places=2)
        self.assertEqual(0.0, kf.dauer_schaetzen(0))

    def test_bekannte_orte_beginnen_beim_usb(self):
        """Der App-Dumper schreibt auf USB - deshalb steht der oben."""
        self.assertEqual("/mnt/usb0", kf.BEKANNTE_ORTE[0][0])

    def test_port_ist_2121(self):
        self.assertEqual(2121, kf.FTP_PORT)
        self.assertEqual(kd.dienst("ftpsrv").port, kf.FTP_PORT)


class UebertragungTests(unittest.TestCase):
    """Gegen den echten kleinen Server."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.fern = Path(self._tmp.name) / "konsole"
        self.lokal = Path(self._tmp.name) / "pc"
        self.fern.mkdir(parents=True)
        self.lokal.mkdir(parents=True)
        _baum_anlegen(self.fern)
        self.stube = _FtpStube(self.fern)

    def tearDown(self):
        self.stube.schliessen()
        self._tmp.cleanup()

    def test_auflisten_trennt_ordner_und_dateien(self):
        verbindung = kf.verbinden("127.0.0.1", self.stube.port)
        try:
            eintraege = kf.auflisten(verbindung, "/PPSA01234")
        finally:
            kf.schliessen(verbindung)
        namen = [e.name for e in eintraege]
        self.assertEqual(["sce_sys", "eboot.bin", "zweite.bin"], namen)
        self.assertTrue(eintraege[0].ordner)
        self.assertEqual(200000, eintraege[1].groesse)

    def test_groesse_schaetzen_zaehlt_den_ganzen_baum(self):
        zwischen: list[tuple[int, int]] = []
        dateien, bytes_ = kf.groesse_schaetzen(
            "127.0.0.1", "/PPSA01234", self.stube.port,
            melden=lambda d, b: zwischen.append((d, b)))
        self.assertEqual(3, dateien)
        self.assertEqual(200000 + 1000 + 2, bytes_)
        self.assertTrue(zwischen, "der Schritt muss sich melden")

    def test_ordner_holen_bringt_alles_mit_unterordner(self):
        meldungen: list[str] = []
        stand = kf.ordner_holen(
            "127.0.0.1", "/PPSA01234", self.lokal / "spiel", self.stube.port,
            auf_fortschritt=lambda f: meldungen.append(f.aktuell))
        self.assertFalse(stand.abgebrochen)
        self.assertEqual(3, stand.dateien)
        self.assertEqual(200000 + 1000 + 2, stand.bytes)
        self.assertTrue((self.lokal / "spiel" / "eboot.bin").is_file())
        self.assertEqual(
            b"{}", (self.lokal / "spiel" / "sce_sys" / "param.json").read_bytes())
        self.assertTrue(meldungen, "ohne Meldung waere es ein stiller Vorgang")

    def test_ordner_senden_legt_ordner_an(self):
        quelle = self.lokal / "fertig"
        (quelle / "sce_sys").mkdir(parents=True)
        (quelle / "sce_sys" / "param.json").write_bytes(b"{}")
        (quelle / "app.bin").write_bytes(b"A" * 4096)

        stand = kf.ordner_senden("127.0.0.1", quelle, "/ziel", self.stube.port)
        self.assertEqual(2, stand.dateien)
        self.assertEqual(4098, stand.bytes)
        self.assertEqual(b"A" * 4096, (self.fern / "ziel" / "app.bin").read_bytes())
        self.assertTrue((self.fern / "ziel" / "sce_sys" / "param.json").is_file())

    def test_fortschritt_anteil(self):
        stand = kf.Fortschritt(bytes=50, bytes_gesamt=200)
        self.assertAlmostEqual(0.25, stand.anteil)
        self.assertEqual(0.0, kf.Fortschritt(bytes=5).anteil)


class AbbruchTests(unittest.TestCase):
    """Die Regel, die auf der echten Konsole Geld gekostet hat."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.fern = Path(self._tmp.name) / "konsole"
        self.lokal = Path(self._tmp.name) / "pc"
        self.fern.mkdir(parents=True)
        self.lokal.mkdir(parents=True)
        (self.fern / "dump").mkdir()
        # Drei gleich grosse Dateien; die erste ist gross genug, dass der
        # Abbruch waehrend ihrer Uebertragung faellt.
        for name in ("a.bin", "b.bin", "c.bin"):
            (self.fern / "dump" / name).write_bytes(b"X" * 300000)
        self.stube = _FtpStube(self.fern)

    def tearDown(self):
        self.stube.schliessen()
        self._tmp.cleanup()

    def test_abbruch_beendet_erst_die_laufende_datei(self):
        """Abbruch mitten in der ersten Datei - sie muss ganz ankommen.

        Ein abgebrochener RETR legt ftpsrv lahm; nur ein Neustart der
        Konsole hilft. Deshalb darf der Abbruch die laufende Uebertragung
        nicht unterbrechen, sondern erst danach greifen.
        """
        schalter = {"aus": False}

        def _fortschritt(fort) -> None:
            # Mitten in der ersten Datei umlegen.
            if fort.bytes > 1000:
                schalter["aus"] = True

        stand = kf.ordner_holen(
            "127.0.0.1", "/dump", self.lokal / "ziel", self.stube.port,
            auf_fortschritt=_fortschritt,
            abbruch=lambda: schalter["aus"],
            dateien_gesamt=3, bytes_gesamt=900000)

        self.assertTrue(stand.abgebrochen, "der Abbruch muss ankommen")
        self.assertEqual(1, stand.dateien, "genau die laufende Datei zu Ende")
        erste = self.lokal / "ziel" / "a.bin"
        self.assertEqual(300000, erste.stat().st_size,
                         "die laufende Datei muss vollstaendig sein")
        self.assertFalse((self.lokal / "ziel" / "b.bin").exists())
        # Und der Server hat auch wirklich nur eine Datei ausgeliefert.
        self.assertEqual(1, len([p for p in self.stube.geholt
                                 if p.endswith(".bin")]))

    def test_abbruch_vor_der_ersten_datei_holt_nichts(self):
        stand = kf.ordner_holen(
            "127.0.0.1", "/dump", self.lokal / "ziel2", self.stube.port,
            abbruch=lambda: True)
        self.assertTrue(stand.abgebrochen)
        self.assertEqual(0, stand.dateien)
        self.assertEqual([], [p for p in self.stube.geholt
                              if p.endswith(".bin")])

    def test_senden_bricht_ebenfalls_zwischen_dateien_ab(self):
        quelle = self.lokal / "raus"
        quelle.mkdir()
        for name in ("a.bin", "b.bin"):
            (quelle / name).write_bytes(b"Y" * 200000)
        schalter = {"aus": False}

        def _fortschritt(fort) -> None:
            if fort.bytes > 1000:
                schalter["aus"] = True

        stand = kf.ordner_senden("127.0.0.1", quelle, "/rein", self.stube.port,
                                 auf_fortschritt=_fortschritt,
                                 abbruch=lambda: schalter["aus"])
        self.assertTrue(stand.abgebrochen)
        self.assertEqual(1, stand.dateien)
        self.assertEqual(200000, (self.fern / "rein" / "a.bin").stat().st_size)


class FehlerTests(unittest.TestCase):

    def test_ohne_adresse_kein_versuch(self):
        with self.assertRaises(kf.FtpFehler):
            kf.verbinden("   ")

    def test_geschlossener_port_meldet_ftpsrv(self):
        horcher = socket.socket()
        horcher.bind(("127.0.0.1", 0))
        port = horcher.getsockname()[1]
        horcher.close()
        with self.assertRaises(kf.FtpFehler) as fehler:
            kf.verbinden("127.0.0.1", port, zeit=1.0)
        self.assertIn("ftpsrv", str(fehler.exception))

    def test_senden_ohne_ordner(self):
        with self.assertRaises(kf.FtpFehler):
            kf.ordner_senden("127.0.0.1", "/gibt/es/nicht", "/ziel")


class _StubenTest(unittest.TestCase):
    """Baum und Stube fuer die Befunde der Durchsicht vom 23.09.2026."""

    MLSD_WIE_0211 = False

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.fern = Path(self._tmp.name) / "konsole"
        self.lokal = Path(self._tmp.name) / "pc"
        self.fern.mkdir(parents=True)
        self.lokal.mkdir(parents=True)
        _baum_anlegen(self.fern)
        self.stube = _FtpStube(self.fern, mlsd_wie_0211=self.MLSD_WIE_0211)

    def tearDown(self):
        self.stube.schliessen()
        self._tmp.cleanup()


class Ftpsrv0211Tests(_StubenTest):
    """ftpsrv 0.21.1 uebergeht den Pfad von MLSD (U3-1).

    Die Stube antwortet hier wie dessen cmd.c (``opendir(env->cwd)``). Vorher
    sah jeder Ordner aus wie "/", und groesse_schaetzen stieg endlos in
    dieselben Ordner hinab - die Stube bricht nach 300 Auflistungen ab.
    """

    MLSD_WIE_0211 = True

    def test_auflisten_zeigt_den_gewaehlten_ordner(self):
        verbindung = kf.verbinden("127.0.0.1", self.stube.port)
        try:
            namen = [e.name for e in kf.auflisten(verbindung, "/PPSA01234")]
        finally:
            kf.schliessen(verbindung)
        self.assertEqual(["sce_sys", "eboot.bin", "zweite.bin"], namen)

    def test_groesse_schaetzen_endet_und_stimmt(self):
        self.assertEqual((3, 200000 + 1000 + 2), kf.groesse_schaetzen(
            "127.0.0.1", "/PPSA01234", self.stube.port))

    def test_holen_bringt_den_gewaehlten_ordner(self):
        stand = kf.ordner_holen("127.0.0.1", "/PPSA01234",
                                self.lokal / "spiel", self.stube.port)
        self.assertEqual(3, stand.dateien)
        self.assertEqual(
            b"{}", (self.lokal / "spiel" / "sce_sys" / "param.json").read_bytes())

    def test_der_ampr_picker_listet_den_gewaehlten_ordner(self):
        import ftplib

        import PS5ImageConverter_Pro_FINAL_revised as haupt
        gui = haupt.PS5ConverterGUI.__new__(haupt.PS5ConverterGUI)
        ftp = ftplib.FTP()
        ftp.connect("127.0.0.1", self.stube.port, timeout=10)
        ftp.login()
        try:
            eintraege = gui._ampr_ftp_list_entries(ftp, "/PPSA01234")
        finally:
            ftp.close()
        self.assertEqual({"sce_sys", "eboot.bin", "zweite.bin"},
                         {name for name, _ in eintraege})

    def test_abbrechen_beendet_das_vermessen(self):
        with self.assertRaises(kf.FtpAbgebrochen):
            kf.groesse_schaetzen("127.0.0.1", "/PPSA01234", self.stube.port,
                                 abbruch=lambda: True)


class WindowsNamenTests(unittest.TestCase):
    """H9-9: Ein ":" im Namen legt unter Windows einen alternativen
    Datenstrom an - die Datei sah danach leer aus."""

    def test_die_pruefung_kennt_die_verbotenen_zeichen(self):
        if os.name != "nt":
            self.assertTrue(kf.unter_windows_speicherbar("a:b/c?.bin"))
            return
        self.assertTrue(kf.unter_windows_speicherbar("sce_sys/param.json"))
        for pfad in ("Spiel: Titel/eboot.bin", "daten/a?.bin", "punkt./x", "raum /x"):
            with self.subTest(pfad=pfad):
                self.assertFalse(kf.unter_windows_speicherbar(pfad))

    @unittest.skipUnless(os.name == "nt", "nur unter Windows ein Problem")
    def test_holen_endet_vor_einem_solchen_namen_ohne_retr(self):
        import tempfile

        class _Verbindung:
            def __init__(self):
                self.retr: list = []
                self.timeout = 10.0

            def retrbinary(self, befehl, *_a, **_k):
                self.retr.append(befehl)

        verbindung = _Verbindung()
        eintraege = [("/dump/ok.bin", kf.Eintrag("ok.bin", False, 5)),
                     ("/dump/Spiel: Titel.bin", kf.Eintrag("Spiel: Titel.bin", False, 5))]
        with tempfile.TemporaryDirectory() as lokal, \
                mock.patch.object(kf, "verbinden", lambda *a, **k: verbindung), \
                mock.patch.object(kf, "schliessen", lambda _v: None), \
                mock.patch.object(kf, "_durchlaufen", lambda *_a, **_k: iter(eintraege)):
            with self.assertRaises(kf.FtpFehler) as fehler:
                kf.ordner_holen("127.0.0.1", "/dump", lokal)
            self.assertFalse(os.path.exists(os.path.join(lokal, "Spiel")),
                             "Ein Datenstrom-Rest liegt im Ziel.")
        self.assertIn("Spiel: Titel.bin", str(fehler.exception))
        self.assertEqual(["RETR /dump/ok.bin"], verbindung.retr)

    def test_der_bibliotheksdownload_bereinigt_den_namen(self):
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        name = haupt.PS5ConverterGUI._windows_dateiname
        self.assertEqual("Spiel_ Titel.ffpfsc", name("Spiel: Titel.ffpfsc"))
        self.assertEqual("a_b_c", name('a<b>c.'))
        self.assertEqual("_", name(":"))


class HolenAmPcScheitertTests(_StubenTest):
    """Scheitert es auf dem PC, darf kein RETR mittendrin abreissen (U3-2).

    Ein abgerissener RETR legt ftpsrv auf der Konsole lahm - auch wenn der
    Grund ein voller Datentraeger auf dem PC war.
    """

    def test_zu_wenig_platz_meldet_sich_vor_dem_ersten_retr(self):
        with mock.patch.object(kf.shutil, "disk_usage",
                               return_value=mock.Mock(free=1000)):
            with self.assertRaises(kf.FtpFehler) as fehler:
                kf.ordner_holen("127.0.0.1", "/PPSA01234", self.lokal / "spiel",
                                self.stube.port, dateien_gesamt=3,
                                bytes_gesamt=201002)
        self.assertIn("Platz", str(fehler.exception))
        self.assertEqual([], self.stube.geholt)

    def test_ein_schreibfehler_liest_den_download_zu_ende(self):
        echtes_open = open

        class _VollePlatte:
            def __init__(self, pfad, modus):
                self._datei = echtes_open(pfad, modus)

            def write(self, _block):
                raise OSError(28, "No space left on device")

            def close(self):
                self._datei.close()

            def __enter__(self):
                return self

            def __exit__(self, *_rest):
                self.close()

        with mock.patch.object(kf, "open", _VollePlatte, create=True):
            with self.assertRaises(kf.FtpFehler) as fehler:
                kf.ordner_holen("127.0.0.1", "/PPSA01234",
                                self.lokal / "spiel", self.stube.port)
        self.assertIn("eboot.bin", str(fehler.exception))
        self.assertIn("/PPSA01234/eboot.bin", self.stube.fertig_gesendet,
                      "Der RETR wurde mittendrin abgerissen.")
        self.assertFalse((self.lokal / "spiel" / "eboot.bin").exists(),
                         "Die halbe Datei blieb liegen.")


class TexteTests(unittest.TestCase):
    """Jeder benutzte Schluessel muss zweisprachig dastehen."""

    #: Seit dem 25.09.2026 gibt es "Spiel holen" und "Zurueckspielen" nicht
    #: mehr als eigene Fenster - beide sind in der Bibliothek aufgegangen.
    #: Hier stehen die Schluessel, die sie von dort weiter benutzt.
    SCHLUESSEL = (
        "holen.hint_dumper", "holen.btn_dump", "holen.no_dumper",
        "holen.status_dumping", "holen.status_dumped", "holen.status_sizing",
        "holen.status_file", "holen.status_failed", "holen.size_running",
        "holen.ziel_vorhanden", "holen.log_dumper", "holen.log_start",
        "holen.log_done", "holen.log_cancelled",
        "zurueck.ask_overwrite", "zurueck.log_kept", "zurueck.no_webfm",
        "zurueck.log_start", "zurueck.log_done", "zurueck.log_cancelled",
        "zurueck.log_webfm", "zurueck.log_webfm_port", "zurueck.log_webfm_kein_port",
        "spielstaende.window_title", "spielstaende.subtitle",
        "spielstaende.usage", "spielstaende.warn_backup",
        "spielstaende.warn_benutzer", "spielstaende.btn_check",
        "spielstaende.btn_start", "spielstaende.btn_open",
        "spielstaende.status_idle", "spielstaende.status_checking",
        "spielstaende.status_starting", "spielstaende.status_failed",
        "spielstaende.running", "spielstaende.stopped", "spielstaende.opened",
        "spielstaende.no_file", "spielstaende.log_start",
        "konsoleftp.log_ftp_aus", "konsoleftp.log_ftp_stumm",
        "library.ordner_abbruch_vorgemerkt",
    )

    def test_alle_schluessel_zweisprachig(self):
        for schluessel in self.SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))

    def test_abbruchhinweis_nennt_den_grund(self):
        """Der Anwender soll wissen, warum nicht sofort Schluss ist."""
        self.assertIn("ftpsrv", STRINGS["library.ordner_abbruch_vorgemerkt"]["de"])


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class FensterTests(unittest.TestCase):
    """Die drei Fenster oeffnen - am wirklichen Programm."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        pfad = str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
        spec = importlib.util.spec_from_file_location("hauptprogramm", pfad)
        cls.modul = importlib.util.module_from_spec(spec)
        sys.modules["hauptprogramm"] = cls.modul
        spec.loader.exec_module(cls.modul)
        cls.app = cls.modul.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _fenster_oeffnen(self, name: str):
        vorher = set(_WURZEL.winfo_children())
        getattr(self.app, name)()
        _WURZEL.update()
        neu = [w for w in _WURZEL.winfo_children() if w not in vorher]
        self.assertTrue(neu, "%s hat kein Fenster geoeffnet" % name)
        return neu[-1]

    @staticmethod
    def _beschriftungen(fenster) -> list[str]:
        texte: list[str] = []

        def _durch(widget):
            for kind in widget.winfo_children():
                try:
                    texte.append(str(kind.cget("text")))
                except Exception:  # noqa: BLE001
                    pass
                _durch(kind)

        _durch(fenster)
        return texte

    def test_spielstaende_ist_verdrahtet_holen_und_senden_gibt_es_nicht_mehr(self):
        """Seit dem 25.09.2026: Holen und Senden stecken in der Bibliothek."""
        karte = self.modul.PS5ConverterGUI._KONSOLE_FENSTER
        self.assertEqual("_show_konsole_spielstaende", karte.get("spielstaende"))
        self.assertTrue(hasattr(self.app, "_show_konsole_spielstaende"))
        for kennung, methode in (("spiel_holen", "_show_konsole_spiel_holen"),
                                 ("zurueckspielen", "_show_konsole_zurueckspielen")):
            with self.subTest(kennung=kennung):
                self.assertNotIn(kennung, karte)
                self.assertFalse(hasattr(self.app, methode),
                                 "%s ist zurueck - es sollte in der Bibliothek stecken."
                                 % methode)

    def test_jede_kennung_der_seitenleiste_hat_ihr_ziel(self):
        """Kein Knopf der Ansicht darf auf eine fehlende Methode zeigen."""
        for _schluessel, kennung in self.modul.PS5ConverterGUI._KONSOLE_KNOEPFE:
            methode = self.modul.PS5ConverterGUI._KONSOLE_FENSTER.get(kennung)
            if not methode:
                continue  # sagt noch "kommt in einer der naechsten Stufen"
            with self.subTest(kennung=kennung):
                self.assertTrue(callable(getattr(self.app, methode, None)))

    def test_spielstaende_warnt_vor_dem_schreiben(self):
        fenster = self._fenster_oeffnen("_show_konsole_spielstaende")
        try:
            texte = self._beschriftungen(fenster)
            self.assertIn(self.app._t("spielstaende.warn_backup"), texte)
            self.assertIn(self.app._t("spielstaende.btn_start"), texte)
        finally:
            fenster.destroy()
            _WURZEL.update()

    @staticmethod
    def _knopf(fenster, text: str):
        """Der Knopf mit dieser Beschriftung - irgendwo im Fenster."""
        offen = list(fenster.winfo_children())
        while offen:
            kind = offen.pop()
            offen.extend(kind.winfo_children())
            try:
                if str(kind.cget("text")) == text:
                    return kind
            except Exception:  # noqa: BLE001 - nicht jedes Element hat Text
                pass
        raise AssertionError("Kein Knopf %r" % text)

    @staticmethod
    def _lebt(fenster) -> bool:
        try:
            return bool(fenster.winfo_exists())
        except tk.TclError:
            return False

    def _uebertragungsfenster(self, **werte):
        """Startet die Ordneruebertragung der Bibliothek und liefert ihr Fenster."""
        vorher = set(_WURZEL.winfo_children())
        self.app._bibliothek_ordner_uebertragen(_WURZEL, **werte)
        _WURZEL.update()
        neu = [w for w in _WURZEL.winfo_children() if w not in vorher]
        self.assertTrue(neu, "Die Uebertragung hat kein Fenster geoeffnet")
        return neu[-1]

    def _warten_bis_zu(self, fenster, sekunden: float = 5.0) -> None:
        import time
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende and self._lebt(fenster):
            _WURZEL.update()
            time.sleep(0.05)

    def test_das_kreuz_wartet_die_laufende_uebertragung_ab(self):
        """H3-1 (Durchsicht 23.09.2026): Das Kreuz - und damit das Beenden
        des Programms - riss eine laufende Uebertragung mitten im RETR ab.

        Seit dem 25.09.2026 holt die Bibliothek die Ordner ("Spiel holen" ist
        in ihr aufgegangen). Das Kreuz ihres Uebertragungsfensters ist ein
        Abbruch nach der laufenden Datei - das Fenster bleibt so lange stehen.
        """
        import tempfile

        freigabe = threading.Event()
        gestartet = threading.Event()

        def _haengt(*_a, **_k):
            gestartet.set()
            freigabe.wait(10)
            return 3, 201002

        with tempfile.TemporaryDirectory() as lokal, \
                mock.patch.object(kf, "groesse_schaetzen", _haengt), \
                mock.patch.object(self.app, "_ps5_ip", return_value="192.168.178.50"), \
                mock.patch.object(self.app, "_konsole_ftp_bereit", lambda *_a: True), \
                mock.patch.object(self.app, "_im_hauptfaden", lambda *_a, **_k: False):
            fenster = self._uebertragungsfenster(
                richtung="runter", oertlich=os.path.join(lokal, "PPSA01234"),
                entfernt="/mnt/usb0/PPSA01234")
            try:
                self.assertTrue(gestartet.wait(5), "Das Vermessen lief nicht an.")
                fenster.tk.call(fenster.protocol("WM_DELETE_WINDOW"))
                _WURZEL.update()
                self.assertTrue(self._lebt(fenster),
                                "Das Fenster ging mitten in der Uebertragung zu.")
                freigabe.set()
                self._warten_bis_zu(fenster)
                self.assertFalse(self._lebt(fenster),
                                 "Nach dem Ende schloss sich das Fenster nicht.")
            finally:
                freigabe.set()
                if self._lebt(fenster):
                    fenster.destroy()
                _WURZEL.update()

    def test_holen_fragt_vor_einem_belegten_ordner(self):
        """H3-5: Ein vorhandener Ordner wurde still mit dem neuen Stand gemischt.

        Seit dem 25.09.2026 an der Ordneruebertragung der Bibliothek.
        """
        import tempfile

        fragen: list = []

        def _frage(_funktion, _titel, text, **_k):
            fragen.append(text)
            return False

        with tempfile.TemporaryDirectory() as lokal:
            belegt = os.path.join(lokal, "PPSA01234")
            os.makedirs(belegt)
            Path(belegt, "alt.bin").write_bytes(b"alt")
            with mock.patch.object(kf, "groesse_schaetzen") as messen, \
                    mock.patch.object(self.app, "_ps5_ip", return_value="192.168.178.50"), \
                    mock.patch.object(self.app, "_konsole_ftp_bereit", lambda *_a: True), \
                    mock.patch.object(self.app, "_im_hauptfaden", _frage):
                fenster = self._uebertragungsfenster(
                    richtung="runter", oertlich=belegt, entfernt="/mnt/usb0/PPSA01234")
                self._warten_bis_zu(fenster)
            self.assertEqual(1, len(fragen))
            self.assertIn(belegt, fragen[0])
            self.assertFalse(messen.called, "Nach Nein lief die Uebertragung an.")
            self.assertEqual(b"alt", Path(belegt, "alt.bin").read_bytes())
            self.assertFalse(self._lebt(fenster))

    def test_ein_fertiger_download_bleibt_wenn_das_umbenennen_scheitert(self):
        """H9-7: Scheiterte nur das Umbenennen der fertigen .part, loeschte
        das finally sie - der ganze Download war weg."""
        import tempfile
        import time

        class _Ftp:
            def retrbinary(self, _befehl, rueckruf, blocksize=0):
                rueckruf(b"A" * 1000)
                rueckruf(b"B" * 1000)

            def quit(self):
                pass

            def close(self):
                pass

        echtes_replace = os.replace

        def _replace(quelle, ziel):
            if str(quelle).endswith(".part"):
                raise PermissionError(13, "Zieldatei gesperrt")
            return echtes_replace(quelle, ziel)

        with tempfile.TemporaryDirectory() as ordner:
            oertlich = os.path.join(ordner, "Spiel.ffpfsc")
            meldungen: list = []

            def _melden(*a, **_k):
                meldungen.append(" ".join(str(x) for x in a))

            # Ohne laufende Hauptschleife erreicht der Faden das Fenster nicht
            # (_spaeter_im_fenster) - dann geht das Ergebnis ins Protokoll.
            # Gemessen wird beides.
            with mock.patch.object(self.app, "_ampr_ftp_connect",
                                   lambda *a, **k: _Ftp()), \
                    mock.patch.object(self.modul.os, "replace", _replace), \
                    mock.patch.object(self.modul.messagebox, "showwarning", _melden), \
                    mock.patch.object(self.modul.messagebox, "showinfo", _melden), \
                    mock.patch.object(self.app, "_append_to_log", _melden):
                self.app._bibliothek_uebertragen(
                    _WURZEL, richtung="runter", oertlich=oertlich,
                    entfernt="/mnt/usb0/Spiel.ffpfsc", groesse=2000)
                ende = time.monotonic() + 5.0
                while time.monotonic() < ende and any(
                        t.name == "bibliothek-transfer" for t in threading.enumerate()):
                    _WURZEL.update()
                    time.sleep(0.05)
                _WURZEL.update()
            self.assertEqual(2000, os.path.getsize(oertlich + ".part"),
                             "Die vollstaendige Datei wurde geloescht.")
            self.assertTrue(any(oertlich + ".part" in m for m in meldungen),
                            "Keine Meldung, wo die fertige Datei liegt: %r" % meldungen)

    def test_der_ampr_index_zieht_mit_dem_ordner_um(self):
        """H11-1: Ordner A, dann Ordner B gewaehlt - der Index von B ging in
        die Ausgabe von A und ueberschrieb deren Index."""
        import tempfile
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            antworten = iter([a, b])
            fenster = self._fenster_oeffnen("_show_ampr_index_builder")
            try:
                knoepfe = []
                offen = list(fenster.winfo_children())
                while offen:
                    kind = offen.pop(0)
                    offen.extend(kind.winfo_children())
                    try:
                        if str(kind.cget("text")) == self.app._t("action.browse"):
                            knoepfe.append(kind)
                    except Exception:  # noqa: BLE001
                        pass
                self.assertEqual(2, len(knoepfe), "Ordner- und Ausgabeknopf erwartet")
                # Das Ausgabefeld steht in derselben Zeile wie sein Knopf.
                ausgabe = next(k for k in knoepfe[1].master.winfo_children()
                               if isinstance(k, tk.Entry))
                with mock.patch.object(self.modul.filedialog, "askdirectory",
                                       lambda **_k: next(antworten)):
                    knoepfe[0].invoke()
                    self.assertEqual(os.path.join(a, "ampr_emu.index"), ausgabe.get())
                    knoepfe[0].invoke()
                self.assertEqual(os.path.join(b, "ampr_emu.index"), ausgabe.get(),
                                 "Die Ausgabe zeigt noch in den ersten Ordner.")
            finally:
                fenster.destroy()
                _WURZEL.update()

    def test_kein_arbeitsfaden_bleibt_stehen(self):
        """Die Fenster duerfen beim Oeffnen keinen Faden starten."""
        vorher = {t.name for t in threading.enumerate()}
        for name in ("_show_konsole_spielstaende",):
            fenster = self._fenster_oeffnen(name)
            fenster.destroy()
            _WURZEL.update()
        neu = {t.name for t in threading.enumerate()} - vorher
        self.assertEqual(set(), {n for n in neu if n.startswith("konsole-")})


if __name__ == "__main__":
    unittest.main()
