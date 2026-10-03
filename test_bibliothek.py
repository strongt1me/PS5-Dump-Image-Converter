# -*- coding: utf-8 -*-
"""Der Bestand der Bibliothek: Suchlauf und Bildspeicher.

Zwei Dinge, die der bisherige Scan nicht konnte und die den Anwender am
12.09.2026 zu der Frage gebracht haben, wo denn seine Spiele sind:

* **Er ging nur eine Ebene tief.** Wer seine Sicherungen in
  ``Downloads/PS5/Spiele/…`` ablegt - also so, wie man Ordnung hält -, sah
  eine leere Liste und keinen Grund dafür.
* **Er kannte keinen Bildspeicher.** Ein Titelbild aus einer ``.ffpfsc`` zu
  holen heißt, den Container zu öffnen; bei fünfzig Titeln sind das Minuten,
  und beim nächsten Öffnen der Bibliothek wieder.

Gemessen wird an echten Ordnern im Temp, nicht an Attrappen: Der Suchlauf
hängt an ``os.scandir`` und an dem, was ``is_dir`` über einen Pfad sagt.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import bibliothek


def _dump(ordner: Path) -> Path:
    """Legt einen Ordner an, den der Suchlauf als Spiel erkennen muss."""
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "sce_sys").mkdir(exist_ok=True)
    (ordner / "sce_sys" / "param.json").write_text('{"titleId":"PPSA00001"}',
                                                   encoding="utf-8")
    (ordner / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 64)
    return ordner


def _container(pfad: Path, groesse: int = 4096) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(b"x" * groesse)
    return pfad


class SuchlaufTests(unittest.TestCase):
    """Was der Suchlauf findet - und was er in Ruhe lässt."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="bibliothek_")
        self.wurzel = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_alle_fuenf_bauformen(self):
        _dump(self.wurzel / "Spiel A")
        _container(self.wurzel / "Spiel B.ffpfsc")
        _container(self.wurzel / "Spiel C.ffpfs")
        _container(self.wurzel / "Spiel D.exfat")
        _container(self.wurzel / "Spiel E.ffpkg")
        funde = bibliothek.ordner_durchsuchen(str(self.wurzel))
        arten = sorted(f["art"] for f in funde)
        self.assertEqual(["exfat", "ffpfs", "ffpfsc", "ffpkg", "folder"], arten)

    def test_findet_auch_tief_verschachtelt(self):
        """Der eigentliche Punkt: Unterordner zählen mit.

        Der bisherige Scan ging genau eine Ebene tief. Wer seine Sicherungen
        sortiert ablegt, sah deshalb nichts.
        """
        _container(self.wurzel / "Downloads" / "PS5" / "Spiele" / "Tief.ffpfsc")
        _dump(self.wurzel / "a" / "b" / "c" / "Noch tiefer")
        funde = bibliothek.ordner_durchsuchen(str(self.wurzel))
        pfade = sorted(os.path.basename(f["pfad"]) for f in funde)
        self.assertEqual(["Noch tiefer", "Tief.ffpfsc"], pfade)

    def test_dump_ordner_wird_nicht_weiter_durchsucht(self):
        """Was im Spiel liegt, ist kein zweites Spiel.

        Ein Dump traegt selbst ein ``sce_sys``; ohne diese Schranke zaehlte
        jeder Unterordner mit, der zufaellig danach aussieht.
        """
        spiel = _dump(self.wurzel / "Spiel")
        _container(spiel / "irgendwo" / "Beipack.ffpfsc")
        funde = bibliothek.ordner_durchsuchen(str(self.wurzel))
        self.assertEqual(1, len(funde), "Der Inhalt des Dumps wurde mitgezaehlt: %r"
                         % [f["pfad"] for f in funde])
        self.assertEqual("folder", funde[0]["art"])

    def test_asset_pack_ordner_zaehlt_nicht_als_spiel(self):
        """``…_ampr_pack`` liegt neben dem Spiel, ist aber keines."""
        _dump(self.wurzel / "Spiel")
        pack = self.wurzel / "Spiel_ampr_pack"
        pack.mkdir()
        (pack / "sce_sys").mkdir()      # sieht faelschlich nach Dump aus
        funde = bibliothek.ordner_durchsuchen(str(self.wurzel))
        namen = [f["name"] for f in funde]
        self.assertIn("Spiel", namen)
        self.assertNotIn("Spiel_ampr_pack", namen,
                         "Die Ablage der Asset-Baender wurde als Titel gezaehlt.")

    def test_groesse_kommt_mit(self):
        _container(self.wurzel / "Mit Groesse.ffpkg", groesse=12345)
        funde = bibliothek.ordner_durchsuchen(str(self.wurzel))
        self.assertEqual(12345, funde[0]["groesse"])

    def test_fremde_dateien_bleiben_draussen(self):
        (self.wurzel / "liesmich.txt").write_text("nichts", encoding="utf-8")
        (self.wurzel / "bild.png").write_bytes(b"\x89PNG")
        self.assertEqual([], bibliothek.ordner_durchsuchen(str(self.wurzel)))

    def test_tiefenschranke_wird_eingehalten(self):
        tief = self.wurzel
        for i in range(12):
            tief = tief / ("e%02d" % i)
        _container(tief / "Zutief.ffpfsc")
        funde = bibliothek.ordner_durchsuchen(str(self.wurzel), max_tiefe=3)
        self.assertEqual([], funde, "Die Tiefenschranke greift nicht.")

    def test_unlesbares_wird_gemeldet_nicht_verschwiegen(self):
        """Eine leere Liste heisst sonst "da ist nichts" statt "durfte nicht"."""
        gemeldet: list[str] = []
        funde = bibliothek.ordner_durchsuchen(
            str(self.wurzel / "gibtesnicht"), melden=gemeldet.append)
        self.assertEqual([], funde)
        self.assertEqual(1, len(gemeldet))

    def test_abbruch_wirkt(self):
        for i in range(20):
            _container(self.wurzel / ("Spiel %02d.ffpfsc" % i))
        funde = bibliothek.ordner_durchsuchen(str(self.wurzel),
                                              abbruch=lambda: True)
        self.assertEqual([], funde)

    def test_pakete_werden_gefunden(self):
        """``.pkg`` und ``.fpkg`` gehoeren seit dem 03.10.2026 auf dem Rechner dazu - auch gross geschrieben."""
        _container(self.wurzel / "Spiel P.pkg")
        _container(self.wurzel / "Spiel Q.fpkg")
        _container(self.wurzel / "Spiel R.PKG")
        funde = bibliothek.ordner_durchsuchen(str(self.wurzel))
        self.assertEqual({"Spiel P": "pkg", "Spiel Q": "fpkg", "Spiel R": "pkg"},
                         {f["name"]: f["art"] for f in funde})

    def test_die_endungen_lassen_sich_eingrenzen(self):
        _container(self.wurzel / "Spiel P.pkg")
        _container(self.wurzel / "Spiel B.ffpfsc")
        funde = bibliothek.ordner_durchsuchen(str(self.wurzel),
                                              endungen=bibliothek.CONTAINER_ENDUNGEN)
        self.assertEqual(["ffpfsc"], [f["art"] for f in funde],
                         "Ein Paket zaehlte mit, obwohl die Endung nicht gewuenscht war.")

    def test_ein_dump_ordner_als_wurzel_ist_der_eine_fund(self):
        """Wer einen Dump-Ordner selbst als Scan-Ordner eintraegt, bekommt ihn als Treffer.

        Bis zum 03.10.2026 pruefte der Suchlauf nur die Unterordner: ``Dirt 5`` lief durch sein ganzes Innere
        (4297 Verzeichnisse, 36 s) und lieferte nichts.
        """
        spiel = _dump(self.wurzel / "Mein Spiel")
        _container(spiel / "irgendwo" / "Beipack.ffpfsc")       # gehoert zum Spiel, ist kein eigener Titel
        gesehen: list[str] = []
        funde = bibliothek.ordner_durchsuchen(
            str(spiel), fortschritt=lambda ordner, anzahl, ort: gesehen.append(ort))
        self.assertEqual([("Mein Spiel", "folder")], [(f["name"], f["art"]) for f in funde])
        self.assertEqual(str(spiel), funde[0]["pfad"])
        self.assertEqual([str(spiel)], gesehen, "Es wurde in das Spiel hineingestiegen.")

    def test_der_fortschritt_zaehlt_ordner_und_funde(self):
        _dump(self.wurzel / "A" / "Spiel 1")
        _dump(self.wurzel / "A" / "Spiel 2")
        _container(self.wurzel / "B" / "Spiel 3.ffpfsc")
        meldungen: list[tuple[int, int, str]] = []
        funde = bibliothek.ordner_durchsuchen(
            str(self.wurzel), fortschritt=lambda *a: meldungen.append(a))
        self.assertEqual(3, len(funde))
        self.assertEqual(3, meldungen[-1][1], "Die letzte Meldung nennt alle Funde.")
        ordner = [m[0] for m in meldungen]
        self.assertEqual(sorted(ordner), ordner, "Die Zahl der gesehenen Ordner waechst nur.")
        self.assertGreaterEqual(max(ordner), 3, "Wurzel, A und B wurden gelesen.")
        self.assertTrue(all(isinstance(m[2], str) for m in meldungen))


class KonsolenSuchlaufTests(unittest.TestCase):
    """Der Suchlauf über FTP - mit gestellter Verbindung."""

    #: So sieht die Konsole in diesem Test aus.
    #:
    #: Die Ordner **der Spiele** tragen ihre Merkmale: Ein Ordner gilt nur
    #: dann als Titel, wenn ``sce_sys`` oder ``eboot.bin`` darin liegt. Auf
    #: einem echten USB-Datentraeger der Konsole liegen sonst ``GAMES``,
    #: ``GAMEI`` und der Papierkorb gleich daneben - die standen am
    #: 12.09.2026 alle als Spiel in der Bibliothek.
    BESTAND = {
        "/data/homebrew": {"dirs": ["Spiel A"], "files": ["Spiel B.ffpkg", "notiz.txt"]},
        "/mnt/usb0/homebrew": {"dirs": [], "files": ["Spiel C.ffpfsc"]},
        "/data/etaHEN/games": {"dirs": ["Spiel D"], "files": []},
        "/data/homebrew/Spiel A": {"dirs": ["sce_sys"], "files": ["eboot.bin"]},
        "/data/etaHEN/games/Spiel D": {"dirs": ["sce_sys"], "files": []},
        # Das ist kein Spiel, sondern ein Sammelordner der Konsole.
        "/mnt/usb0": {"dirs": ["GAMES", "$RECYCLE.BIN", "homebrew", "Spiel E"],
                      "files": []},
        "/mnt/usb0/GAMES": {"dirs": [], "files": []},
        "/mnt/usb0/$RECYCLE.BIN": {"dirs": [], "files": ["desktop.ini"]},
        "/mnt/usb0/Spiel E": {"dirs": ["sce_sys"], "files": ["eboot.bin"]},
    }

    def _helfer(self):
        def ist_ordner(_ftp, pfad):
            return pfad in self.BESTAND

        def auflisten(_ftp, pfad):
            return self.BESTAND[pfad]

        return ist_ordner, auflisten

    def test_findet_ordner_und_container(self):
        ist_ordner, auflisten = self._helfer()
        funde = bibliothek.konsole_durchsuchen(
            object(),
            ["/data/homebrew", "/data/etaHEN/games", "/mnt/usb0/homebrew",
             "/mnt/usb1/homebrew"],
            ist_ordner=ist_ordner, auflisten=auflisten)
        namen = sorted(f["name"] for f in funde)
        self.assertEqual(["Spiel A", "Spiel B", "Spiel C", "Spiel D"], namen)

    def test_fremde_dateien_bleiben_draussen(self):
        ist_ordner, auflisten = self._helfer()
        funde = bibliothek.konsole_durchsuchen(
            object(), ["/data/homebrew"],
            ist_ordner=ist_ordner, auflisten=auflisten)
        self.assertNotIn("notiz", [f["name"] for f in funde])

    def test_die_ablage_steht_dabei(self):
        """Damit man sieht, ob ein Titel auf USB oder intern liegt."""
        ist_ordner, auflisten = self._helfer()
        funde = bibliothek.konsole_durchsuchen(
            object(), ["/mnt/usb0/homebrew"],
            ist_ordner=ist_ordner, auflisten=auflisten)
        self.assertEqual("/mnt/usb0/homebrew", funde[0]["ablage"])

    def test_ein_unlesbarer_ort_stoppt_die_suche_nicht(self):
        def ist_ordner(_ftp, pfad):
            if pfad == "/data/homebrew":
                raise OSError("Zeitueberschreitung")
            return pfad in self.BESTAND

        _i, auflisten = self._helfer()
        funde = bibliothek.konsole_durchsuchen(
            object(), ["/data/homebrew", "/mnt/usb0/homebrew"],
            ist_ordner=ist_ordner, auflisten=auflisten)
        self.assertEqual(["Spiel C"], [f["name"] for f in funde])

    def test_ein_ordner_ohne_spielmerkmale_ist_kein_spiel(self):
        """``GAMES`` und der Papierkorb standen als Titel in der Liste.

        ``/mnt/usb0`` ist selbst ein Ablageort - dort liegen Abbilder, die
        ShadowMount+ sonst nie indiziert. Damit kamen aber auch alle
        Sammelordner des Datentraegers als vermeintliche Spiele herein.
        """
        ist_ordner, auflisten = self._helfer()
        funde = bibliothek.konsole_durchsuchen(
            object(), ["/mnt/usb0"],
            ist_ordner=ist_ordner, auflisten=auflisten)
        self.assertEqual(["Spiel E"], [f["name"] for f in funde])

    def test_ein_ablageort_ist_kein_fund(self):
        """``/mnt/usb0/homebrew`` stand doppelt: als Ort und als Spiel.

        Seit dem 17.09.2026 traegt der Ablageort hier selbst ein Spielmerkmal.
        Vorher fiel er schon an der Merkmalspruefung heraus, und die eigentliche
        Regel (Ablageort ist kein Fund) konnte fehlen, ohne dass der Test es
        merkte.
        """
        bestand = dict(self.BESTAND)
        bestand["/mnt/usb0/homebrew"] = {"dirs": ["sce_sys"],
                                         "files": ["eboot.bin", "Spiel C.ffpfsc"]}
        funde = bibliothek.konsole_durchsuchen(
            object(), ["/mnt/usb0", "/mnt/usb0/homebrew"],
            ist_ordner=lambda _ftp, pfad: pfad in bestand,
            auflisten=lambda _ftp, pfad: bestand[pfad])
        self.assertNotIn("homebrew", [f["name"] for f in funde])
        # Ohne die Regel waere er ein Fund - sonst misst der Test nichts.
        ohne_regel = bibliothek.konsole_durchsuchen(
            object(), ["/mnt/usb0"],
            ist_ordner=lambda _ftp, pfad: pfad in bestand,
            auflisten=lambda _ftp, pfad: bestand[pfad])
        self.assertIn("homebrew", [f["name"] for f in ohne_regel])

    def test_der_fortschritt_nennt_jeden_ort_auch_den_fehlenden(self):
        """Die Zahl der Orte steht von Anfang an fest - daran haengt der Balken der Konsolensuche."""
        ist_ordner, auflisten = self._helfer()
        orte = ["/data/homebrew", "/gibt/es/nicht", "/mnt/usb0/homebrew"]
        meldungen: list[tuple[int, int, str]] = []
        bibliothek.konsole_durchsuchen(
            object(), orte, ist_ordner=ist_ordner, auflisten=auflisten,
            fortschritt=lambda *a: meldungen.append(a))
        self.assertEqual([(1, 3, orte[0]), (2, 3, orte[1]), (3, 3, orte[2])], meldungen)

    def test_pakete_stehen_nicht_in_den_ablagen_der_konsole(self):
        """ShadowMount+ liest keine Pakete - die Konsolensuche zeigt sie nicht (der Rechner schon)."""
        bestand = {"/data/homebrew": {"dirs": [], "files": ["Spiel.pkg", "Spiel.fpkg", "Spiel B.ffpkg"]}}
        funde = bibliothek.konsole_durchsuchen(
            object(), ["/data/homebrew"],
            ist_ordner=lambda _ftp, pfad: pfad in bestand, auflisten=lambda _ftp, pfad: bestand[pfad])
        self.assertEqual(["Spiel B"], [f["name"] for f in funde])


class BildspeicherTests(unittest.TestCase):
    """Einmal geöffnet, bleibt das Titelbild liegen."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="bildspeicher_")
        self.ordner = os.path.join(self._tmp.name, "bilder")
        self.quelle = os.path.join(self._tmp.name, "Spiel.ffpfsc")
        with io.open(self.quelle, "wb") as f:
            f.write(b"x" * 2048)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_schreiben_und_lesen(self):
        sp = bibliothek.Bildspeicher(self.ordner)
        self.assertEqual("", sp.lesen(self.quelle))
        ziel = sp.schreiben(self.quelle, b"\x89PNG-Testbild")
        self.assertTrue(os.path.isfile(ziel))
        self.assertEqual(ziel, sp.lesen(self.quelle))

    def test_ueberdauert_einen_neustart(self):
        """Der Sinn der Sache: ein zweiter Speicher findet dasselbe Bild."""
        bibliothek.Bildspeicher(self.ordner).schreiben(self.quelle, b"bild")
        zweiter = bibliothek.Bildspeicher(self.ordner)
        self.assertTrue(zweiter.lesen(self.quelle))

    def test_geaenderte_datei_bekommt_kein_altes_bild(self):
        """Ein neu gebauter Container liegt unter demselben Pfad.

        Ohne Aenderungszeit und Groesse im Schluessel zeigte die Bibliothek
        das Titelbild des Vorgaengers - und niemand sieht, dass es falsch ist.
        """
        sp = bibliothek.Bildspeicher(self.ordner)
        sp.schreiben(self.quelle, b"altes bild")
        self.assertTrue(sp.lesen(self.quelle))
        time.sleep(0.01)
        with io.open(self.quelle, "wb") as f:
            f.write(b"y" * 4096)          # andere Groesse, andere Zeit
        self.assertEqual("", sp.lesen(self.quelle),
                         "Das Bild des Vorgaengers gilt weiter.")

    def test_kein_bild_wird_auch_gemerkt(self):
        """Sonst wird der teuerste Fall bei jedem Aufschlagen wiederholt."""
        sp = bibliothek.Bildspeicher(self.ordner)
        self.assertFalse(sp.kennt_ohne_bild(self.quelle))
        sp.schreiben(self.quelle, None)
        self.assertTrue(sp.kennt_ohne_bild(self.quelle))
        self.assertEqual("", sp.lesen(self.quelle))

    def test_geloeschtes_bild_gilt_nicht_mehr(self):
        sp = bibliothek.Bildspeicher(self.ordner)
        ziel = sp.schreiben(self.quelle, b"bild")
        os.remove(ziel)
        self.assertEqual("", sp.lesen(self.quelle),
                         "Ein Verweis auf ein geloeschtes Bild gilt weiter.")

    def test_kaputtes_verzeichnis_wirft_nicht(self):
        os.makedirs(self.ordner, exist_ok=True)
        with io.open(os.path.join(self.ordner, "index.json"), "w",
                     encoding="utf-8") as f:
            f.write("{kein json")
        sp = bibliothek.Bildspeicher(self.ordner)
        self.assertEqual("", sp.lesen(self.quelle))
        self.assertTrue(sp.schreiben(self.quelle, b"bild"))

    def test_aufraeumen_wirft_altes_weg(self):
        sp = bibliothek.Bildspeicher(self.ordner)
        sp.schreiben(self.quelle, b"bild")
        # Den Eintrag kuenstlich altern lassen.
        pfad = os.path.join(self.ordner, "index.json")
        with io.open(pfad, encoding="utf-8") as f:
            index = json.load(f)
        for eintrag in index.values():
            eintrag["zeit"] = time.time() - (sp.MAX_ALTER_TAGE + 1) * 86400
        with io.open(pfad, "w", encoding="utf-8") as f:
            json.dump(index, f)

        frisch = bibliothek.Bildspeicher(self.ordner)
        self.assertEqual(1, frisch.aufraeumen())
        self.assertEqual("", frisch.lesen(self.quelle))

    # --- Angaben des Suchlaufs ---------------------------------------------------------------
    def test_scan_angaben_werden_gemerkt_und_ueberdauern_einen_neustart(self):
        """Ein Abbild zu oeffnen kostet auf einer kalten Platte Sekunden - der zweite Lauf soll es nicht tun."""
        sp = bibliothek.Bildspeicher(self.ordner)
        self.assertIsNone(sp.scan_lesen(self.quelle))
        sp.scan_schreiben(self.quelle, {"title": "Spiel", "title_id": "CUSA00001", "version": "01.00"})
        self.assertEqual({"title": "Spiel", "title_id": "CUSA00001", "version": "01.00"},
                         sp.scan_lesen(self.quelle))
        zweiter = bibliothek.Bildspeicher(self.ordner)
        self.assertEqual("Spiel", zweiter.scan_lesen(self.quelle)["title"])

    def test_scan_angaben_einer_ersetzten_datei_gelten_nicht_mehr(self):
        sp = bibliothek.Bildspeicher(self.ordner)
        sp.scan_schreiben(self.quelle, {"title": "Alt"})
        time.sleep(0.01)
        with io.open(self.quelle, "wb") as f:
            f.write(b"y" * 4096)
        self.assertIsNone(sp.scan_lesen(self.quelle), "Die Angaben des Vorgaengers gelten weiter.")

    def test_scan_angaben_einer_anderen_fassung_gelten_nicht(self):
        sp = bibliothek.Bildspeicher(self.ordner)
        sp.scan_schreiben(self.quelle, {"title": "Spiel"})
        sp.SCAN_FASSUNG = sp.SCAN_FASSUNG + 1                 # der Suchlauf liest inzwischen mehr Felder
        self.assertIsNone(sp.scan_lesen(self.quelle))

    def test_leere_scan_angaben_zaehlen_als_nicht_gemerkt(self):
        sp = bibliothek.Bildspeicher(self.ordner)
        sp.scan_schreiben(self.quelle, {})
        self.assertIsNone(sp.scan_lesen(self.quelle), "Ein leeres Ergebnis darf nichts 'beantworten'.")

    def test_scan_angaben_lassen_bild_angaben_und_einbauten_in_ruhe(self):
        sp = bibliothek.Bildspeicher(self.ordner)
        sp.schreiben(self.quelle, b"bild")
        sp.angaben_schreiben(self.quelle, {"sdk": "9.00"})
        sp.einbauten_schreiben(self.quelle, {"zustand": "ok", "ampr": True})
        sp.scan_schreiben(self.quelle, {"title": "Spiel"})
        self.assertTrue(sp.lesen(self.quelle))
        self.assertEqual({"sdk": "9.00"}, sp.angaben_lesen(self.quelle))
        self.assertTrue(sp.einbauten_lesen(self.quelle)["ampr"])
        # und umgekehrt: ein Bild danach loescht die Scan-Angaben nicht
        sp.schreiben(self.quelle, b"anderes bild")
        self.assertEqual("Spiel", sp.scan_lesen(self.quelle)["title"])




class KonsolenGroessenTests(unittest.TestCase):
    """Der Browser des Programms liefert ``(name, groesse)`` - beides zählt.

    ``_ampr_ftp_browse`` gibt Dateien als Tupel zurück. Nimmt man nur den
    Namen, steht in der Bibliothek bei jedem Titel auf der Konsole „Größe
    unbekannt" - und die Größe noch einmal über FTP nachzuschlagen kostet je
    Datei einen Umlauf.
    """

    def test_tupel_bringen_die_groesse_mit(self):
        bestand = {"/data/homebrew": {
            "dirs": [], "files": [("Spiel.ffpkg", 61114810368), ("x.txt", 12)]}}
        funde = bibliothek.konsole_durchsuchen(
            object(), ["/data/homebrew"],
            ist_ordner=lambda _f, p: p in bestand,
            auflisten=lambda _f, p: bestand[p])
        self.assertEqual(1, len(funde))
        self.assertEqual(61114810368, funde[0]["groesse"])

    def test_blosse_namen_gehen_weiterhin(self):
        """Die einfache Form muss weiter funktionieren - Prüfstände nutzen sie."""
        bestand = {"/data/homebrew": {"dirs": [], "files": ["Spiel.ffpfsc"]}}
        funde = bibliothek.konsole_durchsuchen(
            object(), ["/data/homebrew"],
            ist_ordner=lambda _f, p: p in bestand,
            auflisten=lambda _f, p: bestand[p])
        self.assertEqual(1, len(funde))
        self.assertIsNone(funde[0]["groesse"])




class NamensabgleichTests(unittest.TestCase):
    """Ein Abbild ohne Kennung im Namen der Konsole zuordnen.

    Am 12.09.2026 an der echten Konsole gemessen: Von 16 Funden trugen nur
    6 eine Title-ID im Namen. Ein 51-GB-Abbild über FTP zu öffnen, um an
    seine param.json zu kommen, dauert Stunden - die Konsole führt den
    Namen aber unter ``/system_data/priv/appmeta`` neben der Kennung.

    Die Namen weichen dabei regelmäßig voneinander ab: Die Konsole hängt
    ein "Bundle" an, die Datei trägt die Fassung im Namen, und auf einem
    USB-Datenträger stehen Unterstriche statt Leerzeichen.
    """

    #: So sah es an der Konsole aus - echte Namenspaare.
    VERZEICHNIS = {
        bibliothek.namen_vergleichbar("Crazy Chicken Shooter Bundle"): "PPSA03117",
        bibliothek.namen_vergleichbar("Crash Bandicoot 4: It's About Time"): "PPSA02433",
        bibliothek.namen_vergleichbar("Arcade Game Zone"): "PPSA19015",
        bibliothek.namen_vergleichbar("Double Dragon Revive"): "PPSA23000",
        bibliothek.namen_vergleichbar("Teardown"): "PPSA15246",
    }

    def test_die_konsole_haengt_etwas_an(self):
        self.assertEqual("PPSA03117", bibliothek.name_zuordnen(
            "Crazy Chicken Shooter", self.VERZEICHNIS))

    def test_die_datei_traegt_die_fassung_im_namen(self):
        self.assertEqual("PPSA02433", bibliothek.name_zuordnen(
            "Crash Bandicoot 4 It's About Time (01.000.000)", self.VERZEICHNIS))

    def test_unterstriche_statt_leerzeichen(self):
        self.assertEqual("PPSA19015", bibliothek.name_zuordnen(
            "Arcade_Game_Zone", self.VERZEICHNIS))

    def test_ein_fremder_titel_bleibt_ohne_kennung(self):
        self.assertEqual("", bibliothek.name_zuordnen(
            "Ein ganz anderes Spiel", self.VERZEICHNIS))

    def test_zu_kurze_namen_werden_nicht_zugeordnet(self):
        """"Teardown" hat 8 Zeichen und zählt gerade noch; kürzer nicht.

        Ohne diese Schranke ordnete ein Ordner namens "Demo" dem
        erstbesten Titel ein Bild zu - und ein falsches Titelbild ist
        schlimmer als gar keines, weil es richtig aussieht.
        """
        self.assertEqual("PPSA15246", bibliothek.name_zuordnen(
            "Teardown", self.VERZEICHNIS))
        self.assertEqual("", bibliothek.name_zuordnen("Tear", self.VERZEICHNIS))

    def test_mehrdeutig_heisst_keine_zuordnung(self):
        """Passen zwei Titel, ist keiner gemeint."""
        verzeichnis = {
            bibliothek.namen_vergleichbar("Spielreihe Teil 1"): "PPSA00001",
            bibliothek.namen_vergleichbar("Spielreihe Teil 2"): "PPSA00002",
        }
        self.assertEqual("", bibliothek.name_zuordnen("Spielreihe", verzeichnis))

    def test_vergleichbar_wirft_interpunktion_weg(self):
        self.assertEqual(
            bibliothek.namen_vergleichbar("Asterix & Obelix: Heroes"),
            bibliothek.namen_vergleichbar("Asterix  Obelix Heroes"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
