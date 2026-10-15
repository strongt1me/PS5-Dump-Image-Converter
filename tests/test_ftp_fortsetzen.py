# -*- coding: utf-8 -*-
"""Senden mit Fortsetzen und Wiederverbinden (``konsole_ftp``, seit 10.10.2026).

Vorbild war fpkg2ftp (kvaps, GPL-3.0-or-later): eine angefangene Datei wird von der Stelle an weitergeschrieben, an
der die Konsole sie hat (``SIZE``, ``APPE``), eine vollstaendige uebersprungen, ein abgerissener Zugriff mit frischer
Verbindung wiederholt. Geprueft wird gegen einen **echten** kleinen FTP-Server auf diesem Rechner (``Attrappe``), der
die Faelle erzeugen kann, um die es geht: eine abreissende Verbindung mitten in einer Datei, einen Server ohne
``APPE``, ein ``550`` beim Schreiben, eine still abgeschnittene Datei. Ein Mock von ``ftplib`` zeigte genau das nicht.

Die Gegenprobe zu jedem Test steht in seinem Namen: Ohne die neue Logik schrieben die Tests mit "fortsetzen" jede
Datei neu, und der Abriss beendete den Lauf mit einem Fehler.
"""
from __future__ import annotations

import os
import posixpath
import random
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ftplib                                                # noqa: E402

from ps5_validator.utils import konsole_ftp as kf            # noqa: E402


class Attrappe:
    """Ein FTP-Server auf 127.0.0.1 mit Fehlerbildern - genug fuer ``ftplib``.

    Beherrscht ``USER``/``PASS``/``TYPE``/``PWD``/``CWD``/``PASV``/``MLSD``/``STOR``/``APPE``/``SIZE``/``MKD``/
    ``QUIT``. Jede Sitzung laeuft in einem eigenen Faden, damit eine zweite Verbindung nach einem Abriss bedient wird.

    Die Fehlerbilder:

    * ``abriss`` - Pfad -> Byte: Beim ersten Schreiben dieser Datei nimmt der Server so viele Byte an und beendet
      dann Daten- und Steuerverbindung ohne ``226`` (der Eintrag gilt einmal).
    * ``abriss_immer`` - Pfade, bei denen jedes Schreiben nach ``abriss_bytes`` Byte so endet.
    * ``ohne_appe`` - ``APPE`` antwortet ``502``.
    * ``stor_verweigert`` - Pfade, deren ``STOR`` mit ``550`` abgelehnt wird (vor der Datenverbindung).
    * ``abschneiden_einmal`` - Pfade, die der Server nach dem ersten Schreiben um ein Byte kuerzt (``226`` kommt
      trotzdem), die Groesse stimmt danach nicht.
    """

    def __init__(self, wurzel: Path, *, abriss: "dict[str, int] | None" = None, abriss_immer: "set[str] | None" = None,
                 abriss_bytes: int = 1000, ohne_appe: bool = False, stor_verweigert: "set[str] | None" = None,
                 abschneiden_einmal: "set[str] | None" = None) -> None:
        self.wurzel = Path(wurzel)
        self.abriss = dict(abriss or {})
        self.abriss_immer = set(abriss_immer or ())
        self.abriss_bytes = abriss_bytes
        self.ohne_appe = ohne_appe
        self.stor_verweigert = set(stor_verweigert or ())
        self.abschneiden_einmal = set(abschneiden_einmal or ())
        #: Alle Befehle in der Reihenfolge ihres Eintreffens: (Verbindung, Befehl, Argument).
        self.befehle: list[tuple[int, str, str]] = []
        #: Je Schreibbefehl: (Befehl, Pfad, empfangene Byte).
        self.empfangen: list[tuple[str, str, int]] = []
        self.verbindungen = 0
        self._sperre = threading.Lock()
        self.horcher = socket.socket()
        self.horcher.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.horcher.bind(("127.0.0.1", 0))
        self.horcher.listen(8)
        self.port = self.horcher.getsockname()[1]
        self.laeuft = True
        threading.Thread(target=self._bedienen, daemon=True, name="ftp-attrappe").start()

    def schliessen(self) -> None:
        self.laeuft = False
        try:
            self.horcher.close()
        except OSError:
            pass

    def befehl_zaehler(self, befehl: str, argument: "str | None" = None) -> int:
        return len([1 for _n, b, a in self.befehle if b == befehl and (argument is None or a == argument)])

    def empfangen_von(self, befehl: str, pfad: str) -> list[int]:
        return [n for b, p, n in self.empfangen if b == befehl and p == pfad]

    def _ort(self, fern: str) -> Path:
        return self.wurzel / str(fern).strip().lstrip("/")

    def _bedienen(self) -> None:
        while self.laeuft:
            try:
                verbindung, _ = self.horcher.accept()
            except OSError:
                return
            with self._sperre:
                self.verbindungen += 1
                nummer = self.verbindungen
            threading.Thread(target=self._sitzung, args=(verbindung, nummer), daemon=True,
                             name="ftp-attrappe-%d" % nummer).start()

    @staticmethod
    def _sagen(datei, text: str) -> None:
        datei.write((text + "\r\n").encode("utf-8"))
        datei.flush()

    def _sitzung(self, steuer: socket.socket, nummer: int) -> None:
        steuer.settimeout(15.0)
        datei = steuer.makefile("rwb")
        horcher: "socket.socket | None" = None
        cwd = "/"
        try:
            self._sagen(datei, "220 attrappe bereit")
            while True:
                zeile = datei.readline()
                if not zeile:
                    return
                befehl, _, rest = zeile.decode("utf-8", "replace").strip().partition(" ")
                befehl = befehl.upper()
                rest = rest.strip()
                with self._sperre:
                    self.befehle.append((nummer, befehl, rest))
                if befehl in ("USER", "PASS"):
                    self._sagen(datei, "230 angemeldet" if befehl == "PASS" else "331 weiter")
                elif befehl in ("TYPE", "NOOP"):
                    self._sagen(datei, "200 gut")
                elif befehl == "PWD":
                    self._sagen(datei, '257 "%s"' % cwd)
                elif befehl == "CWD":
                    neu = posixpath.normpath(rest if rest.startswith("/") else posixpath.join(cwd, rest))
                    if self._ort(neu).is_dir():
                        cwd = neu
                        self._sagen(datei, "250 OK")
                    else:
                        self._sagen(datei, "550 gibt es nicht")
                elif befehl == "PASV":
                    horcher = socket.socket()
                    horcher.bind(("127.0.0.1", 0))
                    horcher.listen(1)
                    horcher.settimeout(15.0)
                    port = horcher.getsockname()[1]
                    self._sagen(datei, "227 Entering Passive Mode (127,0,0,1,%d,%d)" % (port // 256, port % 256))
                elif befehl == "SIZE":
                    ort = self._ort(rest)
                    if ort.is_file():
                        self._sagen(datei, "213 %d" % ort.stat().st_size)
                    else:
                        self._sagen(datei, "550 gibt es nicht")
                elif befehl == "MKD":
                    self._ort(rest).mkdir(parents=True, exist_ok=True)
                    self._sagen(datei, '257 "%s"' % rest)
                elif befehl == "MLSD":
                    if horcher is None:
                        self._sagen(datei, "425 kein PASV")
                        continue
                    self._auflisten(datei, horcher, cwd)
                    horcher = None
                elif befehl in ("STOR", "APPE"):
                    if horcher is None:
                        self._sagen(datei, "425 kein PASV")
                        continue
                    if befehl == "APPE" and self.ohne_appe:
                        self._sagen(datei, "502 APPE gibt es hier nicht")
                        horcher.close()
                        horcher = None
                        continue
                    if rest in self.stor_verweigert and befehl == "STOR":
                        self._sagen(datei, "550 keine Berechtigung")
                        horcher.close()
                        horcher = None
                        continue
                    if not self._schreiben(datei, steuer, horcher, befehl, rest):
                        return
                    horcher = None
                elif befehl == "QUIT":
                    self._sagen(datei, "221 tschuess")
                    return
                else:
                    self._sagen(datei, "502 kenne ich nicht")
        except (OSError, ValueError):
            return
        finally:
            for ding in (datei, steuer):
                try:
                    ding.close()
                except OSError:
                    pass

    def _auflisten(self, steuer, horcher, ordner: str) -> None:
        self._sagen(steuer, "150 Auflistung")
        try:
            daten, _ = horcher.accept()
        except OSError:
            self._sagen(steuer, "425 keine Datenverbindung")
            return
        try:
            ort = self._ort(ordner)
            for eintrag in sorted(ort.iterdir(), key=lambda p: p.name):
                if eintrag.is_dir():
                    daten.sendall(("type=dir;size=0; %s\r\n" % eintrag.name).encode("utf-8"))
                else:
                    daten.sendall(("type=file;size=%d; %s\r\n" % (eintrag.stat().st_size, eintrag.name)).encode("utf-8"))
        finally:
            daten.close()
            horcher.close()
        self._sagen(steuer, "226 fertig")

    def _schreiben(self, datei, steuer, horcher, befehl: str, rest: str) -> bool:
        """STOR/APPE. ``False`` heisst: Die Sitzung ist beendet (Abriss)."""
        self._sagen(datei, "150 Datenverbindung offen")
        try:
            daten, _ = horcher.accept()
        except OSError:
            self._sagen(datei, "425 keine Datenverbindung")
            return True
        ort = self._ort(rest)
        ort.parent.mkdir(parents=True, exist_ok=True)
        grenze = None
        if rest in self.abriss_immer:
            grenze = self.abriss_bytes
        elif rest in self.abriss:
            grenze = self.abriss.pop(rest)
        n = 0
        try:
            with open(ort, "wb" if befehl == "STOR" else "ab") as ziel:
                while True:
                    wunsch = 65536 if grenze is None else min(65536, grenze - n)
                    if wunsch <= 0:
                        break
                    brocken = daten.recv(wunsch)
                    if not brocken:
                        break
                    ziel.write(brocken)
                    n += len(brocken)
        except OSError:
            pass
        with self._sperre:
            self.empfangen.append((befehl, rest, n))
        if grenze is not None and n >= grenze:
            # Abriss: kein 226, beide Verbindungen weg.
            for ding in (daten, horcher, steuer):
                try:
                    ding.close()
                except OSError:
                    pass
            return False
        for ding in (daten, horcher):
            try:
                ding.close()
            except OSError:
                pass
        if rest in self.abschneiden_einmal:
            self.abschneiden_einmal.discard(rest)
            groesse = ort.stat().st_size
            if groesse > 0:
                with open(ort, "r+b") as ziel:
                    ziel.truncate(groesse - 1)
        self._sagen(datei, "226 fertig")
        return True


def _bytes(anzahl: int, samen: int) -> bytes:
    return random.Random(samen).randbytes(anzahl)


class _Basis(unittest.TestCase):
    """Ein lokaler Ordner mit vier Dateien und eine Attrappe als Konsole."""

    ABRISS: "dict[str, int]" = {}
    ABRISS_IMMER: "set[str]" = set()
    OHNE_APPE = False
    STOR_VERWEIGERT: "set[str]" = set()
    ABSCHNEIDEN: "set[str]" = set()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        wurzel = Path(self._tmp.name)
        self.lokal = wurzel / "lokal"
        self.fern = wurzel / "fern"
        self.lokal.mkdir()
        self.fern.mkdir()
        self.inhalt = {
            "a.bin": _bytes(300_000, 1),
            "sub/b.bin": _bytes(700_000, 2),
            "sub/deep/c.txt": b"klein\n" * 20,
            "leer.dat": b"",
        }
        for name, daten in self.inhalt.items():
            ziel = self.lokal / name
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(daten)
        self.server = Attrappe(self.fern, abriss=dict(self.ABRISS), abriss_immer=set(self.ABRISS_IMMER),
                               ohne_appe=self.OHNE_APPE, stor_verweigert=set(self.STOR_VERWEIGERT),
                               abschneiden_einmal=set(self.ABSCHNEIDEN))
        self.addCleanup(self.server.schliessen)
        self.addCleanup(self._tmp.cleanup)

    def senden(self, **optionen):
        optionen.setdefault("pause", 0.0)
        return kf.ordner_senden("127.0.0.1", self.lokal, "/ziel", self.server.port, **optionen)

    def fern_lesen(self, name: str) -> bytes:
        return (self.fern / "ziel" / name).read_bytes()

    def alles_gleich(self) -> None:
        for name, daten in self.inhalt.items():
            with self.subTest(datei=name):
                self.assertEqual(daten, self.fern_lesen(name))


class HilfenTests(unittest.TestCase):

    def test_fortsetzen_ab_entscheidet_nach_der_groesse(self) -> None:
        self.assertEqual(("neu", 0), kf.fortsetzen_ab(100, None))
        self.assertEqual(("ueberspringen", 100), kf.fortsetzen_ab(100, 100))
        self.assertEqual(("fortsetzen", 40), kf.fortsetzen_ab(100, 40))
        self.assertEqual(("neu", 0), kf.fortsetzen_ab(100, 0), "Ein leerer Anfang ist kein Anfang")
        self.assertEqual(("neu", 0), kf.fortsetzen_ab(100, 150), "Zu gross: neu schreiben")
        self.assertEqual(("neu", 0), kf.fortsetzen_ab(0, 0), "Eine leere Quelle wird immer neu angelegt")
        self.assertEqual(("neu", 0), kf.fortsetzen_ab(0, 7))

    def test_ist_netzfehler(self) -> None:
        for fehler in (OSError("weg"), ConnectionResetError(), socket.timeout("zu langsam"), EOFError(),
                       ftplib.error_temp("421 spaeter"), ftplib.error_proto("kein Code"),
                       kf.GroesseFalsch("1 Byte zu wenig")):
            with self.subTest(fehler=type(fehler).__name__):
                self.assertTrue(kf.ist_netzfehler(fehler))
        for fehler in (ftplib.error_perm("550 nein"), kf.LeseFehler("Platte"), kf.FtpFehler("irgendwas"),
                       ValueError("kaputt")):
            with self.subTest(fehler=type(fehler).__name__):
                self.assertFalse(kf.ist_netzfehler(fehler))

    def test_begrenzt_liest_hoechstens_die_anzahl(self) -> None:
        import io
        quelle = kf._Begrenzt(io.BytesIO(b"0123456789"), 4)
        self.assertEqual(b"0123", quelle.read(100))
        self.assertEqual(b"", quelle.read(100))
        self.assertEqual(b"", kf._Begrenzt(io.BytesIO(b"abc"), 0).read(10))

    def test_begrenzt_meldet_ein_zu_fruehes_ende_der_quelle(self) -> None:
        import io
        quelle = kf._Begrenzt(io.BytesIO(b"abc"), 10)
        self.assertEqual(b"abc", quelle.read(10))
        with self.assertRaises(kf.LeseFehler):
            quelle.read(10)

    def test_begrenzt_macht_aus_einem_lesefehler_der_quelle_einen_lesefehler(self) -> None:
        class _Kaputt:
            def read(self, _n):
                raise PermissionError("gesperrt")
        with self.assertRaises(kf.LeseFehler):
            kf._Begrenzt(_Kaputt(), 5).read(5)

    def test_warten_fragt_den_abbruch(self) -> None:
        self.assertTrue(kf.warten(5.0, lambda: True))
        self.assertFalse(kf.warten(0.0))


class FernTests(_Basis):

    def test_groesse_fern(self) -> None:
        (self.fern / "ziel").mkdir()
        (self.fern / "ziel" / "x.bin").write_bytes(b"12345")
        v = kf.verbinden("127.0.0.1", self.server.port)
        self.addCleanup(kf.schliessen, v)
        self.assertEqual(5, kf.groesse_fern(v, "/ziel/x.bin"))
        self.assertIsNone(kf.groesse_fern(v, "/ziel/gibt-es-nicht"))

    def test_fern_baum_liefert_relative_pfade_und_groessen(self) -> None:
        self.senden()
        v = kf.verbinden("127.0.0.1", self.server.port)
        self.addCleanup(kf.schliessen, v)
        baum = kf.fern_baum(v, "/ziel")
        self.assertEqual({name: len(daten) for name, daten in self.inhalt.items()}, baum)

    def test_fern_baum_eines_fehlenden_ordners_ist_leer(self) -> None:
        v = kf.verbinden("127.0.0.1", self.server.port)
        self.addCleanup(kf.schliessen, v)
        self.assertEqual({}, kf.fern_baum(v, "/gibt/es/nicht"))


class StandardlaufTests(_Basis):

    def test_ohne_fortsetzen_geht_jede_datei_neu_per_stor(self) -> None:
        stand = self.senden()
        self.alles_gleich()
        self.assertEqual((4, sum(len(d) for d in self.inhalt.values())), (stand.dateien, stand.bytes))
        self.assertEqual(0, self.server.befehl_zaehler("APPE"))
        self.assertEqual(4, self.server.befehl_zaehler("STOR"))
        self.assertEqual((0, 0, 0), (stand.uebersprungen, stand.fortgesetzt, stand.wiederholt))
        self.assertFalse(stand.abgebrochen)

    def test_ohne_fortsetzen_ersetzt_auch_gleich_grosse_dateien(self) -> None:
        (self.fern / "ziel").mkdir()
        (self.fern / "ziel" / "a.bin").write_bytes(b"x" * len(self.inhalt["a.bin"]))      # gleich gross, anderer Inhalt
        self.senden()
        self.assertEqual(self.inhalt["a.bin"], self.fern_lesen("a.bin"))

    def test_ordner_werden_je_einmal_angelegt(self) -> None:
        self.senden()
        for pfad in ("/ziel", "/ziel/sub", "/ziel/sub/deep"):
            with self.subTest(pfad=pfad):
                self.assertEqual(1, self.server.befehl_zaehler("MKD", pfad))

    def test_der_fortschritt_wird_in_bloecken_gemeldet(self) -> None:
        stufen: list[int] = []
        self.senden(auf_fortschritt=lambda s: stufen.append(s.bytes))
        self.assertEqual(sorted(stufen), stufen, "Der Stand geht nur vorwaerts")
        self.assertEqual(sum(len(d) for d in self.inhalt.values()), stufen[-1])

    def test_der_abbruch_wirkt_nur_zwischen_den_dateien(self) -> None:
        meldungen: list[str] = []

        def _abbruch() -> bool:
            return len(meldungen) >= 1

        def _fort(stand: kf.Fortschritt) -> None:
            if stand.dateien >= 1 and not meldungen:
                meldungen.append(stand.aktuell)

        stand = self.senden(abbruch=_abbruch, auf_fortschritt=_fort)
        self.assertTrue(stand.abgebrochen)
        self.assertEqual(1, stand.dateien)
        # Die erste Datei liegt vollstaendig drueben, die zweite wurde nicht angefangen.
        self.assertEqual(self.inhalt["a.bin"], self.fern_lesen("a.bin"))
        self.assertFalse((self.fern / "ziel" / "sub" / "b.bin").exists())

    def test_kein_ordner_ist_ein_fehler(self) -> None:
        with self.assertRaises(kf.FtpFehler):
            kf.ordner_senden("127.0.0.1", self.lokal / "gibt-es-nicht", "/ziel", self.server.port)


class FortsetzenTests(_Basis):

    def test_vollstaendige_werden_uebersprungen_angefangene_fortgesetzt(self) -> None:
        ziel = self.fern / "ziel"
        (ziel / "sub").mkdir(parents=True)
        (ziel / "a.bin").write_bytes(self.inhalt["a.bin"])                                  # vollstaendig
        (ziel / "sub" / "b.bin").write_bytes(self.inhalt["sub/b.bin"][:123_456])             # angefangen
        (ziel / "sub" / "deep").mkdir()
        (ziel / "sub" / "deep" / "c.txt").write_bytes(self.inhalt["sub/deep/c.txt"] + b"zu lang")   # zu gross
        stand = self.senden(fortsetzen=True)
        self.alles_gleich()
        self.assertEqual(1, stand.uebersprungen)
        self.assertEqual(1, stand.fortgesetzt)
        self.assertEqual(sum(len(d) for d in self.inhalt.values()), stand.bytes)
        self.assertEqual([], self.server.empfangen_von("STOR", "/ziel/a.bin"), "a.bin wird nicht noch einmal gesendet")
        self.assertEqual([len(self.inhalt["sub/b.bin"]) - 123_456], self.server.empfangen_von("APPE", "/ziel/sub/b.bin"),
                         "von b.bin geht nur der Rest")
        self.assertEqual(1, len(self.server.empfangen_von("STOR", "/ziel/sub/deep/c.txt")), "zu grosse: neu")

    def test_ohne_fortgesetztes_ziel_wird_alles_gesendet(self) -> None:
        stand = self.senden(fortsetzen=True)
        self.alles_gleich()
        self.assertEqual((0, 0), (stand.uebersprungen, stand.fortgesetzt))
        self.assertEqual(0, self.server.befehl_zaehler("APPE"))

    def test_eine_leere_quelle_wird_immer_neu_angelegt(self) -> None:
        ziel = self.fern / "ziel"
        ziel.mkdir()
        (ziel / "leer.dat").write_bytes(b"altes zeug")
        self.senden(fortsetzen=True)
        self.assertEqual(0, (ziel / "leer.dat").stat().st_size)

    def test_ein_zweiter_lauf_sendet_nichts_mehr(self) -> None:
        self.senden()
        stand = self.senden(fortsetzen=True)
        self.assertEqual(3, stand.uebersprungen, "drei Dateien mit Inhalt (die leere wird neu angelegt)")
        self.assertEqual(sum(len(d) for d in self.inhalt.values()), stand.bytes)
        self.alles_gleich()


class AbrissTests(_Basis):
    ABRISS = {"/ziel/sub/b.bin": 150_000}

    def test_ein_abriss_mitten_in_der_datei_wird_fortgesetzt(self) -> None:
        stand = self.senden()
        self.alles_gleich()
        self.assertEqual(1, stand.wiederholt)
        self.assertEqual(2, self.server.verbindungen, "eine frische Verbindung nach dem Abriss")
        self.assertEqual([150_000], self.server.empfangen_von("STOR", "/ziel/sub/b.bin"))
        # Der zweite Versuch haengt nur den Rest an - kein zweites Mal von vorn:
        self.assertEqual([len(self.inhalt["sub/b.bin"]) - 150_000], self.server.empfangen_von("APPE", "/ziel/sub/b.bin"))
        self.assertEqual(1, stand.fortgesetzt)
        self.assertEqual(sum(len(d) for d in self.inhalt.values()), stand.bytes)

    def test_der_fortschritt_zaehlt_den_wiederholten_teil_nicht_doppelt(self) -> None:
        stufen: list[int] = []
        stand = self.senden(auf_fortschritt=lambda s: stufen.append(s.bytes))
        self.assertEqual(stand.bytes_gesamt, stand.bytes)
        self.assertLessEqual(max(stufen), stand.bytes_gesamt, "Der Balken darf nie ueber 100 % laufen")


class AbrissOhneAppeTests(_Basis):
    ABRISS = {"/ziel/sub/b.bin": 150_000}
    OHNE_APPE = True

    def test_lehnt_der_server_appe_ab_geht_die_datei_neu(self) -> None:
        stand = self.senden()
        self.alles_gleich()
        self.assertEqual(1, stand.wiederholt)
        self.assertGreaterEqual(self.server.befehl_zaehler("APPE"), 1, "APPE wurde versucht")
        self.assertEqual(2, len(self.server.empfangen_von("STOR", "/ziel/sub/b.bin")), "und die Datei dann neu gesendet")
        self.assertEqual(0, stand.fortgesetzt)


class AbrissOhneAppeBeimFortsetzenTests(_Basis):
    OHNE_APPE = True

    def test_ohne_appe_wird_auch_die_angefangene_neu_gesendet(self) -> None:
        ziel = self.fern / "ziel" / "sub"
        ziel.mkdir(parents=True)
        (ziel / "b.bin").write_bytes(self.inhalt["sub/b.bin"][:1000])
        stand = self.senden(fortsetzen=True)
        self.alles_gleich()
        self.assertEqual(0, stand.fortgesetzt)
        self.assertEqual(1, self.server.befehl_zaehler("APPE"), "nur ein Versuch, danach weiss der Lauf es")


class ImmerAbrissTests(_Basis):
    ABRISS_IMMER = {"/ziel/a.bin"}

    def test_zu_viele_abrisse_geben_auf(self) -> None:
        with self.assertRaises(kf.FtpFehler) as ctx:
            self.senden(versuche=2)
        self.assertIn("a.bin", str(ctx.exception))
        self.assertEqual(3, self.server.verbindungen, "erster Versuch und zwei Wiederholungen")


class VerweigertTests(_Basis):
    STOR_VERWEIGERT = {"/ziel/a.bin"}

    def test_ein_550_wird_nicht_wiederholt(self) -> None:
        with self.assertRaises(kf.FtpFehler) as ctx:
            self.senden()
        self.assertIn("a.bin", str(ctx.exception))
        self.assertEqual(1, self.server.verbindungen)


class AbgeschnittenTests(_Basis):
    ABSCHNEIDEN = {"/ziel/sub/b.bin"}

    def test_eine_falsche_groesse_nach_dem_senden_wird_behoben(self) -> None:
        stand = self.senden()
        self.alles_gleich()
        self.assertEqual(1, stand.wiederholt)
        self.assertEqual([1], self.server.empfangen_von("APPE", "/ziel/sub/b.bin"), "das fehlende Byte wird angehaengt")


class LeseFehlerTests(_Basis):

    def test_eine_nicht_lesbare_datei_wird_nicht_wiederholt(self) -> None:
        echt = open

        def _oeffnen(datei, *a, **k):
            if str(datei).endswith("b.bin"):
                raise PermissionError("gesperrt")
            return echt(datei, *a, **k)

        with mock.patch.object(kf, "open", _oeffnen, create=True):
            with self.assertRaises(kf.FtpFehler) as ctx:
                self.senden()
        self.assertIn("b.bin", str(ctx.exception))
        self.assertEqual(1, self.server.verbindungen, "ein Fehler der Platte ist kein Netzfehler")


class Wiederverbinden(unittest.TestCase):

    def test_ohne_server_nach_den_versuchen_ein_fehler(self) -> None:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()                                           # nichts horcht mehr dort
        with self.assertRaises(kf.FtpFehler):
            kf.wiederverbinden("127.0.0.1", port, 0, 2, 0.0)

    def test_abbruch_waehrend_des_wartens(self) -> None:
        verbindung, versuch = kf.wiederverbinden("127.0.0.1", 1, 0, 3, 5.0, abbruch=lambda: True)
        self.assertIsNone(verbindung)
        self.assertEqual(1, versuch)


if __name__ == "__main__":
    unittest.main()
