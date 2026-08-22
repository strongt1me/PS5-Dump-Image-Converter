"""Tests für „PS4 PKG → ffpfsc" – das eingebettete PS4-FFPFSC 0.2.8.

Das Werkzeug wandelt PS4-PKG (Basis, Patch, wahlweise DLC) oder ein bereits
entpacktes PS4-Spiel in ein ShadowMountPlus-Abbild. Es liegt als Quellauszug
unter ``PS4FFPFSC-0.2.8/`` im Projekt; seine Qt-Oberfläche bleibt außen vor,
die Arbeit treibt ein eigenes Fenster über die Kommandozeile an.

Geprüft wird hier dreierlei:

  1. **Die Einbettung trägt** – Ordner gefunden, interne Modi verdrahtet,
     Menüeintrag und Texte vollständig.
  2. **Die beiden behobenen Fehler bleiben behoben.** Beide stammen aus der
     Vorlage und traten erst durch die Einbettung zutage:
     * ``doctor`` verlangte Compiler und CMake, obwohl der fertige Entpacker
       daneben liegt – und meldete deshalb immer „nicht bereit";
     * ``inspect`` mit Prüfsumme wertete den Rückgabewert des Entpackers nicht
       aus. Stürzt der ab (gemessen: Stapelüberlauf 0xC00000FD an mehreren
       PKG), kam „PKG nicht unterstützt" heraus – ein Fehler in der Datei
       also, wo einer im Werkzeug vorlag.
  3. **Der Schutz vor zu langen Arbeitspfaden** – der PKG-Entpacker bricht
     sonst mit „Failed to write extracted PKG entry" ab.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as hauptprogramm
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
from ps5_validator.utils.i18n import STRINGS

PS4_ORDNER = PROJEKT / hauptprogramm.PS4FFPFSC_ORDNER


class EinbettungTests(unittest.TestCase):
    """Der Quellauszug muss vollständig und auffindbar sein."""

    def test_ordner_wird_gefunden(self) -> None:
        self.assertTrue(hauptprogramm._ps4ffpsc_wurzel(), "PS4-Ordner nicht gefunden")

    def test_arbeitsteile_sind_da(self) -> None:
        for rel in ("ps4ffpsc/cli.py", "ps4ffpsc/pipeline.py", "ps4ffpsc/inventory.py",
                    "mkpfs_1_0_0/mkpfs/__init__.py", "UPSTREAM.md", "LICENSE"):
            with self.subTest(datei=rel):
                self.assertTrue((PS4_ORDNER / rel).is_file(), f"{rel} fehlt")

    def test_qt_oberflaeche_ist_nicht_dabei(self) -> None:
        """PySide6 wird nicht gebraucht - die Oberfläche stellt dieses Programm."""
        for rel in ("ps4ffpsc/gui.py", "ps4ffpsc/gui_model.py"):
            with self.subTest(datei=rel):
                self.assertFalse((PS4_ORDNER / rel).exists(), f"{rel} sollte fehlen")

    def test_mkpfs_liegt_ausserhalb_des_suchmusters(self) -> None:
        """Sonst greift der Validator zur falschen Engine.

        Das Programm und ``ffpfs_validator._ensure_mkpfs_importable`` suchen
        ihre eigene Fassung über ``MkPFS-*`` im Projektstamm. Läge die 1.0.0
        des PS4-Werkzeugs dort, gewänne sie die Sortierung.
        """
        treffer = sorted(p.name for p in PROJEKT.glob("MkPFS-*") if p.is_dir())
        self.assertEqual(treffer, [f"MkPFS-{hauptprogramm.MKPFS_REQUIRED_VERSION}"])

    def test_menueeintrag_und_methode(self) -> None:
        eintraege = dict(PS5ConverterGUI._MORE_TOOLS_ENTRIES)
        self.assertIn("titlebar.ps4pkg", eintraege)
        self.assertEqual(eintraege["titlebar.ps4pkg"], "_show_ps4_pkg_converter")
        self.assertTrue(callable(getattr(PS5ConverterGUI, "_show_ps4_pkg_converter", None)))

    def test_texte_sind_zweisprachig(self) -> None:
        schluessel = [k for k in STRINGS if k.startswith("ps4pkg.")]
        self.assertGreaterEqual(len(schluessel), 20)
        for name in [*schluessel, "titlebar.ps4pkg"]:
            with self.subTest(schluessel=name):
                self.assertTrue(STRINGS[name].get("de"))
                self.assertTrue(STRINGS[name].get("en"))


class InterneModiTests(unittest.TestCase):
    """Die beiden Schalter, über die das Werkzeug angetrieben wird."""

    def _aufruf(self, *argumente: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"), *argumente],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        )

    def test_mkpfs_modus_startet_die_geprüfte_fassung(self) -> None:
        """--ps4-mkpfs muss 1.0.0 liefern, nicht die 0.0.9 des Programms."""
        ergebnis = self._aufruf("--ps4-mkpfs", "-V")
        self.assertEqual(ergebnis.returncode, 0, ergebnis.stderr[-400:])
        self.assertIn("1.0.0", ergebnis.stdout + ergebnis.stderr)

    def test_doctor_meldet_bereit(self) -> None:
        """Der erste behobene Fehler: doctor verlangte einen Compiler.

        Die Vorlage koppelte Compiler-, CMake- und Quelltextprüfung an
        ``is_frozen()``. Aus der Quelle heraus – also genau hier – meldete sie
        deshalb „nicht bereit", obwohl der fertige Entpacker danebenliegt.
        """
        ergebnis = self._aufruf("--ps4ffpsc", "doctor", "--json")
        daten = json.loads(ergebnis.stdout)
        pruefungen = daten["checks"]
        self.assertTrue(pruefungen["extractor"]["ok"], "Entpacker nicht gefunden")
        self.assertTrue(pruefungen["mkpfs"]["ok"], pruefungen["mkpfs"])
        self.assertFalse(pruefungen["compiler"]["required"],
                         "Mit fertigem Entpacker darf kein Compiler verlangt werden")
        self.assertFalse(pruefungen["cmake"]["required"])
        self.assertTrue(pruefungen["shadps4_source"]["ok"])
        self.assertTrue(daten["ok"], daten)


class InspectAbsturzTests(unittest.TestCase):
    """Der zweite behobene Fehler: ein Absturz galt als „PKG nicht unterstützt".

    Statt eines echten PKG tritt hier ein Ersatz-Entpacker an, der den
    gemessenen Fall nachstellt: Mit Prüfsummenlauf bricht er ohne Ausgabe ab,
    mit ``--fast`` liefert er JSON. So ist der Test unabhängig davon, welche
    PKG auf dem Rechner liegen.
    """

    def setUp(self) -> None:
        if str(PS4_ORDNER) not in sys.path:
            sys.path.insert(0, str(PS4_ORDNER))
        self._tmp = TemporaryDirectory(prefix="ps4_inspect_")
        self.basis = Path(self._tmp.name)
        self.paket = self.basis / "spiel.pkg"
        self.paket.write_bytes(b"\x7fCNT" + os.urandom(4096))
        self.extractor = self.basis / "extractor.py"
        self.extractor.write_text(
            "import json, sys\n"
            "if '--fast' not in sys.argv:\n"
            "    sys.exit(3221225725)\n"
            "print(json.dumps({'path': sys.argv[2], 'supported': True,\n"
            "                  'title_id': 'CUSA00001', 'title': 'Test',\n"
            "                  'kind': 'base', 'sha256': None}))\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _inspizieren(self, compute_sha256: bool):
        from ps4ffpsc.inventory import inspect_package  # noqa: PLC0415

        # Der Ersatz-Entpacker ist ein Python-Skript; ein Startskript daneben
        # macht daraus einen aufrufbaren "Entpacker".
        starter = self.basis / ("start.cmd" if os.name == "nt" else "start.sh")
        if os.name == "nt":
            starter.write_text(f'@"{sys.executable}" "{self.extractor}" %*\n', encoding="utf-8")
        else:
            starter.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{self.extractor}" "$@"\n',
                               encoding="utf-8")
            starter.chmod(0o755)
        return inspect_package(starter, self.paket, compute_sha256=compute_sha256)

    def test_absturz_gilt_nicht_mehr_als_nicht_unterstuetzt(self) -> None:
        befund = self._inspizieren(compute_sha256=True)
        self.assertTrue(befund.get("supported"),
                        f"Absturz wurde wieder als Dateifehler gedeutet: {befund}")
        self.assertEqual(befund.get("title_id"), "CUSA00001")

    def test_pruefsumme_wird_nachgerechnet(self) -> None:
        """Weicht der Aufruf auf --fast aus, rechnet Python die Summe nach."""
        import hashlib  # noqa: PLC0415

        befund = self._inspizieren(compute_sha256=True)
        erwartet = hashlib.sha256(self.paket.read_bytes()).hexdigest()
        self.assertEqual(befund.get("sha256"), erwartet)

    def test_ohne_pruefsumme_bleibt_es_beim_schnellen_weg(self) -> None:
        befund = self._inspizieren(compute_sha256=False)
        self.assertTrue(befund.get("supported"))
        self.assertIsNone(befund.get("sha256"))


class NachpruefungTests(unittest.TestCase):
    """Was nach dem Bauen ueber das Abbild gesagt wird.

    Anlass: Am 20.08.2026 wurde ein PS4-Titel gebaut, der sich einbinden und
    registrieren liess, beim Start aber die Konsole mitnahm. Das eingebettete
    Werkzeug sichert den PS5-Betrieb ausdruecklich nicht zu
    (``ps5_runtime_verified`` steht fest auf ``False``) - nur stand das
    bislang allein in einer Begleitdatei neben dem Abbild.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")

    def _methode(self, name: str) -> str:
        anfang = self.quelltext.index("    def %s(self" % name)
        weiter = self.quelltext.index("\n    def ", anfang + 10)
        return self.quelltext[anfang:weiter]

    def test_hinweis_steht_in_der_einblendung(self) -> None:
        """Vor dem Bauen sichtbar, nicht nur in der Begleitdatei.

        Bis v1.8.76 als eigene Zeile im Fenster, seither in der Einblendung -
        dort wird sie eher gelesen.
        """
        self.assertIn("ps4pkg.runtime_note",
                      self._methode("_ps4_hinweis_zeigen"))
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertIn("ps5_runtime_verified",
                              STRINGS["ps4pkg.runtime_note"][sprache])

    def test_ablageort_steht_in_der_einblendung(self) -> None:
        """Der Ablageort entscheidet ueber Auffinden und Absturz.

        Am 21.08.2026 an der Konsole gemessen (FW 12.00, ShadowMount+
        v1.7alpha6): Ein .ffpfsc in /mnt/usb0/ps4ffpsc/ wurde nie indiziert,
        direkt in /mnt/usb0/ beim naechsten Durchlauf sofort, in
        /mnt/usb0/homebrew/ ebenfalls. Aus /data/homebrew gestartet nimmt ein
        PS4-Titel die Konsole mit.

        Seit v1.8.77 steht das nicht mehr dauerhaft im Fenster, sondern in der
        Einblendung waehrend der Umwandlung - dort erreicht es den Nutzer im
        richtigen Moment, und das Fenster wird um rund 190 px kuerzer.
        """
        rumpf = self._methode("_ps4_hinweis_zeigen")
        for schluessel in ("ps4pkg.place_title", "ps4pkg.place_ok",
                           "ps4pkg.place_bad", "ps4pkg.place_after_crash"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, rumpf)
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[schluessel][sprache].strip(),
                                    "%s fehlt auf %s" % (schluessel, sprache))

    def test_der_richtige_ordner_wird_genannt(self) -> None:
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertIn("/mnt/usb0/", STRINGS["ps4pkg.place_ok"][sprache])
                self.assertIn("/data/homebrew",
                              STRINGS["ps4pkg.place_bad"][sprache])
                self.assertIn("/data/etaHEN/games",
                              STRINGS["ps4pkg.place_bad"][sprache])

    def test_der_unterordner_wird_nur_mit_manual_lst_genannt(self) -> None:
        """Ein eigener Ordner geht - aber nur mit Eintrag in manual.lst.

        Zwei Fassungen dieses Tests waren vorher falsch. Die erste liess den
        Pfad als Empfehlung stehen, die zweite verlangte die Aussage "wird
        nicht gefunden". Beide gingen an der Sache vorbei; am 22.08.2026
        wurde es in drei Schritten an der Konsole gemessen:

          1. Datei nach /mnt/usb0/ps4ffpsc/ verschoben, 190 s gewartet -
             aus dem Verzeichnis verschwunden, die automatische Suche geht
             dort nicht hinein.
          2. Pfad in /data/shadowmount/manual.lst eingetragen - sofort
             eingehaengt und als installiert vermerkt.
          3. An der Konsole gestartet:
             ``[GAME] started: CUSA00775 pid=121 app_id=0x00008018``.
             Gelaufen, sauber beendet, im Kernel-Protokoll keine Panik.

        Wer den Pfad also nennt, muss manual.lst dazusagen - sonst ist die
        Aussage in die eine oder andere Richtung falsch.
        """
        for schluessel, eintrag in STRINGS.items():
            if not schluessel.startswith("ps4pkg."):
                continue
            for sprache, text in eintrag.items():
                if "/mnt/usb0/ps4ffpsc" not in text:
                    continue
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertIn(
                        "manual.lst", text,
                        "%s (%s) nennt den Unterordner, ohne die Bedingung "
                        "zu nennen, unter der er funktioniert."
                        % (schluessel, sprache))

    def test_die_einblendung_faellt_auf(self) -> None:
        """Eine weitere graue Zeile haette der Nutzer wieder ueberlesen.

        Deshalb ein umrandetes Fenster in der Warnfarbe, mittig ueber dem
        Bau-Fenster - nicht eine Zeile mehr im ohnehin vollen Fenster.
        """
        rumpf = self._methode("_ps4_hinweis_zeigen")
        self.assertIn('bg=c["fg_warning"]', rumpf,
                      "Der Rahmen traegt nicht die Warnfarbe")
        self.assertIn("fg=c[\"fg_warning\"]", rumpf,
                      "Die Ueberschrift traegt nicht die Warnfarbe")

    def test_das_fenster_traegt_den_kasten_nicht_mehr(self) -> None:
        """Er nahm 190 px, obwohl er nur einmal gelesen werden muss."""
        rumpf = self._methode("_show_ps4_pkg_converter")
        self.assertNotIn("_ps4_ablage_kasten", rumpf)
        for schluessel in ("ps4pkg.place_title", "ps4pkg.place_ok",
                           "ps4pkg.runtime_note"):
            with self.subTest(schluessel=schluessel):
                self.assertNotIn(schluessel, rumpf)

    def test_werkzeug_sichert_den_betrieb_wirklich_nicht_zu(self) -> None:
        """Der Hinweis muss stimmen - also nachsehen, was das Werkzeug setzt."""
        pipeline = (PS4_ORDNER / "ps4ffpsc" / "pipeline.py").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('"ps5_runtime_verified": False', pipeline)
        self.assertNotIn('"ps5_runtime_verified": True', pipeline)

    def test_die_begleitdatei_nennt_die_bedingung(self) -> None:
        """Die Vorlage nannte /mnt/usb0/ps4ffpsc/ - aber nicht die Bedingung.

        Sie schrieb "Recommended USB path" und "manual.lst" mit demselben
        Pfad untereinander, ohne zu sagen, dass der Eintrag in manual.lst
        dafuer noetig ist. Ohne ihn verschwindet der Titel (am 22.08.2026
        gemessen), mit ihm laeuft er.

        Die Begleitdatei liegt neben jedem fertigen Abbild - sie darf der
        Einblendung im Fenster nicht widersprechen.
        """
        pipeline = (PS4_ORDNER / "ps4ffpsc" / "pipeline.py").read_text(
            encoding="utf-8", errors="replace")
        self.assertNotIn('"Recommended USB path: /mnt/usb0/ps4ffpsc/"',
                         pipeline, "Empfiehlt den Ordner ohne die Bedingung.")
        self.assertIn('"Recommended USB path: /mnt/usb0/"', pipeline)
        for stueck in ("/mnt/usb0/homebrew/", "/mnt/usb0/etaHEN/games/",
                       "kernel panic", "manual.lst",
                       # Im Quelltext ueber zwei Zeilen umbrochen - deshalb
                       # nur das Stueck suchen, das in einer Zeile steht.
                       "picked up by the automatic scan"):
            with self.subTest(stueck=stueck):
                self.assertIn(stueck, pipeline)

    def test_der_eingriff_steht_in_upstream_md(self) -> None:
        """Aenderungen an der Vorlage werden dort festgehalten."""
        text = (PS4_ORDNER / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn("shadowmount.txt", text)
        self.assertIn("ps4ffpsc/", text)

    def test_die_nachpruefung_bekommt_die_datei_nicht_den_ordner(self) -> None:
        """Bis v1.8.77 wurde der Ausgabeordner uebergeben.

        Die Pruefung scheiterte dadurch jedes Mal mit
        "[Errno 13] Permission denied" auf dem Ordnerpfad - sie hat also nie
        stattgefunden, obwohl im Protokoll stand, dass sie laeuft. Am
        22.08.2026 an einer echten Konvertierung gesehen (Tetris Ultimate,
        CUSA00775); nach der Korrektur meldet sie 113 Dateien.
        """
        rumpf = self._methode("_show_ps4_pkg_converter")
        self.assertNotIn("_ps4ffpsc_abbild_pruefen(ziel)", rumpf,
                         "Der Ordner wird wieder als Abbild uebergeben.")
        self.assertIn("_ps4ffpsc_ergebnis_finden(", rumpf,
                      "Die erzeugte Datei wird nicht gesucht.")

    def test_das_ergebnis_wird_im_ausgabeordner_gefunden(self) -> None:
        """Bevorzugt die Title-ID und das gewaehlte Format."""
        with TemporaryDirectory() as ordner:
            for name in ("alt.exfat", "CUSA00775 - Tetris [v01.00].ffpfsc",
                         "fremd.ffpfsc", "notiz.txt"):
                with open(os.path.join(ordner, name), "w",
                          encoding="utf-8") as datei:
                    datei.write("x")
            # Die Klasse als "self": Die Methode liest nur eine
            # Klassenvariable, eine ganze Oberflaeche braucht es dafuer nicht.
            treffer = PS5ConverterGUI._ps4ffpsc_ergebnis_finden(
                PS5ConverterGUI, ordner, "CUSA00775", "ffpfsc")
        self.assertTrue(treffer.endswith("CUSA00775 - Tetris [v01.00].ffpfsc"),
                        "Gefunden wurde: %r" % treffer)

    def test_ohne_abbild_wird_nicht_gepruft(self) -> None:
        """Statt eines Fehlers eine verstaendliche Meldung."""
        rumpf = self._methode("_show_ps4_pkg_converter")
        self.assertIn("ps4pkg.check_no_image", rumpf)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertTrue(STRINGS["ps4pkg.check_no_image"][sprache].strip())

    def test_abbild_wird_nach_dem_bauen_angesehen(self) -> None:
        self.assertIn("_ps4ffpsc_abbild_pruefen", self.quelltext)
        rumpf = self._methode("_ps4ffpsc_abbild_pruefen")
        self.assertIn("ExfatReader", rumpf)
        # Nur die Verzeichnisbloecke lesen, nicht 20 GB Nutzdaten: iter_files
        # laeuft ueber die Verzeichnisse, read_file holte den Inhalt.
        self.assertIn("iter_files", rumpf)
        self.assertNotIn("read_file", rumpf)

    def test_ps4_titel_gilt_nicht_als_mangelhaft(self) -> None:
        """pfs-version.dat ist ein PS5-Marker.

        Zehn Byte ASCII mit der Inhaltsversion, wortgleich mit
        ``contentVersion`` aus param.json - an drei echten Dumps nachgesehen.
        Ein PS4-Spiel hat die Datei nicht; sie dort zu vermissen waere ein
        Fehlalarm bei jedem einzelnen Titel.
        """
        self.assertIn("ps4pkg.check_ps4_title", self.quelltext)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertIn("pfs-version.dat",
                              STRINGS["ps4pkg.check_ps4_title"][sprache])

    def test_erkennungsmerkmale_eines_ps4_titels(self) -> None:
        merkmale = PS5ConverterGUI._PS4_MERKMALE
        self.assertIn("manifest_nonufsfiles_ps4.txt", merkmale)
        self.assertIn("sce_discmap.plt", merkmale)
        for eintrag in merkmale:
            with self.subTest(eintrag=eintrag):
                self.assertEqual(eintrag, eintrag.lower(),
                                 "Vergleich laeuft in Kleinschreibung")

    def test_die_np_luecke_ist_dokumentiert(self) -> None:
        """Am 22.08.2026 in einer Kette an der Konsole nachgewiesen.

        ShadowMountPlus kopiert nach /system_data/priv/appmeta/<TITLE>/ nur
        sce_sys/trophy2/npbind.dat und sce_sys/uds/npbind.dat - beides
        PS5-Pfade. Ein PS4-Spiel legt die NP-Bindung flach unter
        sce_sys/npbind.dat ab; sie ist im Abbild enthalten, wird aber nie
        abgeholt. Folge: "Trophy registration failed (0x80551618)" bei
        jedem Start, und Titel mit Online-Pruefung bleiben haengen.

        Gegenprobe: Datei von Hand nach appmeta gelegt - Fehler weg,
        SceNpTrophy greift zu. In den drei Mitschnitten davor stand er
        jedes Mal drin. Das gehoert dokumentiert, weil es sonst wie ein
        Fehler unseres Abbilds aussieht.
        """
        self.assertIn('ps4pkg.check_np_note', STRINGS)
        for sprache in ('de', 'en'):
            with self.subTest(sprache=sprache):
                text = STRINGS['ps4pkg.check_np_note'][sprache]
                self.assertIn('npbind.dat', text)
                self.assertIn('0x80551618', text)
        # Nach dem Bau gemeldet, wenn ein PS4-Titel erkannt wurde.
        rumpf = self._methode('_show_ps4_pkg_converter')
        self.assertIn('ps4pkg.check_np_note', rumpf)
        # Und im Handbuch erklaert.
        handbuch = (PROJEKT / 'BENUTZERHANDBUCH.html').read_text(
            encoding='utf-8')
        self.assertIn('npbind.dat', handbuch)
        self.assertIn('0x80551618', handbuch)

    def test_alle_texte_sind_uebersetzt(self) -> None:
        for schluessel in ("ps4pkg.runtime_note", "ps4pkg.check_running",
                           "ps4pkg.check_files", "ps4pkg.check_missing",
                           "ps4pkg.check_complete", "ps4pkg.check_ps4_title",
                           "ps4pkg.check_failed"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[schluessel].get(sprache))


class KonsolenerkennungTests(unittest.TestCase):
    """Beim Einlesen steht da, zu welcher Konsole der Titel gehoert.

    Bis v1.8.77 sagte das Fenster erst nach dem Bau "Es ist ein PS4-Titel".
    Wer eine PS5-PKG hierher legt, wartete also den ganzen Bau ab, um zu
    erfahren, dass er im falschen Fenster ist - dieses baut PS4-Abbilder.
    Die Title-ID sagt es von Anfang an.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")

    def _plattform(self, title_id, spiel=None):
        # Die Klasse als "self": Die Methode liest nur Klassenvariablen.
        return PS5ConverterGUI._ps4ffpsc_plattform(PS5ConverterGUI, title_id, spiel)

    def test_die_kennung_entscheidet(self) -> None:
        """An echten Dumps abgelesen, dieselbe Zuordnung wie beim Patch-Abruf."""
        for kennung, erwartet in (("CUSA00775", "ps4"), ("PUSA01234", "ps4"),
                                  ("PPSA08329", "ps5"), ("PPSS40001", "ps5"),
                                  ("cusa00775", "ps4")):
            with self.subTest(kennung=kennung):
                self.assertEqual(self._plattform(kennung), erwartet)

    def test_fremde_kennung_wird_nicht_geraten(self) -> None:
        """NPUB ist PS3, und Leeres ist Leeres - beides heisst hier "unklar"."""
        for kennung in ("NPUB31397", "", "   ", None, "XXXX00001"):
            with self.subTest(kennung=kennung):
                self.assertEqual(self._plattform(kennung), "")

    def test_das_werkzeug_darf_es_selbst_sagen(self) -> None:
        """Meldet der Entpacker die Plattform mit, zaehlt sie als Rueckfall."""
        self.assertEqual(self._plattform("XXXX1", {"platform": "PS5"}), "ps5")
        self.assertEqual(self._plattform("XXXX1", {"console": "orbis"}), "ps4")
        # Die Kennung wiegt schwerer als eine mitgelieferte Angabe.
        self.assertEqual(self._plattform("CUSA00775", {"platform": "PS5"}), "ps4")

    def test_die_spalte_steht_in_der_liste(self) -> None:
        rumpf = self._methode_lesen("_show_ps4_pkg_converter")
        self.assertIn('spalten = ("title_id", "plattform", "titel"', rumpf,
                      "Die Konsolenspalte fehlt in der Liste.")
        self.assertIn("_ps4ffpsc_plattform(title_id", rumpf,
                      "Die Spalte wird nicht gefuellt.")

    def test_ein_ps5_titel_faellt_auf(self) -> None:
        """Nicht nur eine Spalte weiter rechts - die Zeile wird eingefaerbt."""
        rumpf = self._methode_lesen("_show_ps4_pkg_converter")
        self.assertIn('tag_configure("ps5"', rumpf)
        self.assertIn("ps4pkg.is_ps5_title", rumpf)

    def test_die_texte_sind_zweisprachig(self) -> None:
        for schluessel in ("ps4pkg.col_plattform", "ps4pkg.platform_unknown",
                           "ps4pkg.is_ps5_title", "ps4pkg.platform_unclear"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[schluessel].get(sprache, "").strip())

    def test_der_hinweis_schickt_zur_richtigen_aufgabe(self) -> None:
        """Dieses Fenster baut aus PS4-PKG; PS5 gehoert in Aufgabe 1 bis 6."""
        text = STRINGS["ps4pkg.is_ps5_title"]["de"]
        self.assertIn("{title_id}", text)
        self.assertIn("PS5", text)

    def _methode_lesen(self, name: str) -> str:
        anfang = self.quelltext.index("    def %s(self" % name)
        weiter = self.quelltext.index("\n    def ", anfang + 10)
        return self.quelltext[anfang:weiter]


class PaketMagicTests(unittest.TestCase):
    """Vier Bytes am Dateianfang sagen, fuer welche Konsole ein Paket ist.

    Anlass: Am 22.08.2026 wurden alle 31 PKG eines Datentraegers geprueft.
    Der eingebettete Entpacker weist jedes PS5-Paket ab, bevor er etwas
    ausliest - an 11 von 11 gemessen, jedes Mal mit demselben Wortlaut
    ``supported=False / unsupported_or_encrypted_pkg / Invalid PKG magic``.
    Im Fenster stand daraufhin nur "0 Spiel(e) gefunden", ohne Grund.

    Das Magic unterscheidet die beiden Formate ohne Entpacken, und an
    denselben 31 Dateien (20 PS4, 11 PS5) stimmte es ausnahmslos mit der
    Title-ID im Paket ueberein.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")

    def _schreibe(self, ordner, name, kopf):
        pfad = os.path.join(ordner, name)
        with open(pfad, "wb") as datei:
            datei.write(kopf + b"\x00" * 64)
        return pfad

    def test_die_beiden_magic_stehen_fest(self) -> None:
        self.assertEqual(PS5ConverterGUI._PKG_MAGIC_PS4, b"\x7fCNT")
        self.assertEqual(PS5ConverterGUI._PKG_MAGIC_PS5, b"\x7fFIH")

    def test_das_magic_entscheidet(self) -> None:
        with TemporaryDirectory() as ordner:
            ps4 = self._schreibe(ordner, "ps4.pkg", b"\x7fCNT")
            ps5 = self._schreibe(ordner, "ps5.pkg", b"\x7fFIH")
            fremd = self._schreibe(ordner, "fremd.pkg", b"RIFF")
            leer = os.path.join(ordner, "gibtsnicht.pkg")
            for pfad, erwartet in ((ps4, "ps4"), (ps5, "ps5"),
                                   (fremd, ""), (leer, "")):
                with self.subTest(datei=os.path.basename(pfad)):
                    self.assertEqual(
                        PS5ConverterGUI._pkg_konsole_am_magic(
                            PS5ConverterGUI, pfad), erwartet)

    def test_ein_ordner_wird_durchgezaehlt(self) -> None:
        """Nur die Ebene selbst - genau das nimmt das Werkzeug auch."""
        with TemporaryDirectory() as ordner:
            self._schreibe(ordner, "a.pkg", b"\x7fCNT")
            self._schreibe(ordner, "b.pkg", b"\x7fFIH")
            self._schreibe(ordner, "c.pkg", b"\x7fFIH")
            self._schreibe(ordner, "d.pkg", b"XXXX")
            self._schreibe(ordner, "notiz.txt", b"\x7fFIH")
            tiefer = os.path.join(ordner, "unten")
            os.makedirs(tiefer)
            self._schreibe(tiefer, "e.pkg", b"\x7fFIH")

            app = _Sichter()
            befund = PS5ConverterGUI._ps4ffpsc_quellen_sichten(
                app, ordner, "pkg_dir")
        self.assertEqual(len(befund["ps4"]), 1)
        self.assertEqual(sorted(befund["ps5"]), ["b.pkg", "c.pkg"],
                         "Unterordner oder .txt mitgezaehlt?")
        self.assertEqual(befund["fremd"], ["d.pkg"])

    def test_einzelne_dateien_werden_getrennt(self) -> None:
        with TemporaryDirectory() as ordner:
            eins = self._schreibe(ordner, "eins.pkg", b"\x7fFIH")
            zwei = self._schreibe(ordner, "zwei.pkg", b"\x7fCNT")
            app = _Sichter()
            befund = PS5ConverterGUI._ps4ffpsc_quellen_sichten(
                app, os.pathsep.join((eins, zwei)), "pkg_file")
        self.assertEqual(befund["ps5"], ["eins.pkg"])
        self.assertEqual(befund["ps4"], ["zwei.pkg"])

    def test_das_einlesen_sagt_es(self) -> None:
        anfang = self.quelltext.index("    def _show_ps4_pkg_converter(self")
        weiter = self.quelltext.index("\n    def ", anfang + 10)
        rumpf = self.quelltext[anfang:weiter]
        self.assertIn("_ps4ffpsc_quellen_sichten(", rumpf,
                      "Die Quelle wird beim Einlesen nicht gesichtet.")
        self.assertIn("ps4pkg.ps5_packages", rumpf)

    def test_die_texte_sind_zweisprachig(self) -> None:
        for schluessel in ("ps4pkg.ps5_packages", "ps4pkg.and_more"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[schluessel].get(sprache, "").strip())
        self.assertIn("{anzahl}", STRINGS["ps4pkg.ps5_packages"]["de"])

    def test_die_deutschen_texte_haben_echte_umlaute(self) -> None:
        """Der Rest der Oberflaeche schreibt "Datentraeger" mit ae-Ligatur.

        Ersatzschreibungen fallen im Fenster sofort auf, weil die Nachbarn
        daneben richtig gesetzt sind.
        """
        ersatz = ("fuer ", "oeffn", "gehoert", "pruefen", "entfaellt",
                  "waehlen", "muessen", "koennen", "laesst", "ausfuehren")
        schlecht = []
        for schluessel, texte in STRINGS.items():
            if not schluessel.startswith("ps4pkg."):
                continue
            de = texte.get("de", "")
            for wort in ersatz:
                if wort in de:
                    schlecht.append("%s: %r" % (schluessel, wort))
        self.assertEqual(schlecht, [], "Ersatzschreibung statt Umlaut")


class _Sichter:
    """Traegt nur, was _ps4ffpsc_quellen_sichten von "self" braucht."""

    _PKG_MAGIC_PS4 = PS5ConverterGUI._PKG_MAGIC_PS4
    _PKG_MAGIC_PS5 = PS5ConverterGUI._PKG_MAGIC_PS5

    def _pkg_konsole_am_magic(self, pfad: str) -> str:
        return PS5ConverterGUI._pkg_konsole_am_magic(self, pfad)


class PlattformTests(unittest.TestCase):
    """Nur wo ein lauffaehiger Entpacker liegt, darf das Fenster oeffnen.

    Fertige Programmdateien gibt es beim Hersteller nur fuer Windows x64 und
    macOS ARM64. Beide Saetze liegen zusammen in ``bin/``: ``*.exe`` fuer
    Windows, endungslos fuer Apple Silicon. Eine Suche allein ueber den
    Dateinamen fand unter Linux die Mach-O-Datei und hielt sie fuer brauchbar -
    ausfuehren laesst sie sich dort nicht ("Exec format error").
    """

    def test_beide_saetze_liegen_bei(self) -> None:
        for name in ("ps4_pkg_extract.exe", "ps4-dlc-patch.exe",
                     "ps4_pkg_extract", "ps4-dlc-patch"):
            with self.subTest(datei=name):
                self.assertTrue((PS4_ORDNER / "bin" / name).is_file(), f"{name} fehlt")

    def test_windows_nimmt_die_exe(self) -> None:
        if not hauptprogramm.IST_WINDOWS:
            self.skipTest("nur unter Windows aussagekraeftig")
        self.assertTrue(hauptprogramm._ps4ffpsc_entpacker().endswith("ps4_pkg_extract.exe"))

    def test_fremde_plattform_meldet_keinen_entpacker(self) -> None:
        """Linux und Intel-Macs duerfen die Mach-O-Datei nicht annehmen."""
        import platform as _platform  # noqa: PLC0415

        merker = (hauptprogramm.IST_WINDOWS, sys.platform, _platform.machine)
        try:
            hauptprogramm.IST_WINDOWS = False
            sys.platform = "linux"
            self.assertEqual(hauptprogramm._ps4ffpsc_entpacker(), "")
            sys.platform = "darwin"
            _platform.machine = lambda: "x86_64"
            self.assertEqual(hauptprogramm._ps4ffpsc_entpacker(), "")
            _platform.machine = lambda: "arm64"
            self.assertTrue(hauptprogramm._ps4ffpsc_entpacker().endswith("ps4_pkg_extract"))
        finally:
            hauptprogramm.IST_WINDOWS, sys.platform, _platform.machine = merker


class LangePfadeTests(unittest.TestCase):
    """Der Arbeitsordner darf den Entpacker nicht an die Pfadgrenze treiben."""

    def test_grenze_ist_gesetzt_und_konservativ(self) -> None:
        grenze = hauptprogramm._PS4FFPSC_MAX_ARBEITSPFAD
        self.assertIsInstance(grenze, int)
        # Unter dem Arbeitsordner entstehen noch rund 100 Zeichen
        # (unpacked/<Title-ID>/<Paket>/sce_sys/...), Windows endet bei 260.
        self.assertLessEqual(grenze, 150)
        self.assertGreaterEqual(grenze, 60)

    def test_hinweistext_nennt_laenge_und_ausweichpfad(self) -> None:
        from ps5_validator.utils.i18n import translate  # noqa: PLC0415

        text = translate("de", "ps4pkg.short_workdir", laenge=180, pfad=r"C:\ps4ffpsc_arbeit")
        self.assertIn("180", text)
        self.assertIn("ps4ffpsc_arbeit", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
