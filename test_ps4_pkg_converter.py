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

import inspect
import json
import platform
import os
import subprocess
import sys
import unittest
from unittest import mock
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
        """--ps4-mkpfs muss die eigene Kopie des PS4-Werkzeugs starten.

        Seit das Programm selbst auf 1.0.0 steht, nennen beide dieselbe
        Fassung. Der Schalter muss trotzdem die Kopie des Werkzeugs nehmen.
        """
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


class AufrufwegTests(unittest.TestCase):
    """Startet der PS4-Weg ueberhaupt?

    Am 04.09.2026 tat der Konverter gar nichts mehr: ``ps4_werkzeug.lauf()``
    schrieb ``befehl = [*befehl(hauptdatei), *argumente]``. Die Zuweisung
    macht ``befehl`` in der ganzen Funktion lokal; der Aufruf daneben traf
    damit nicht mehr die Modulfunktion darueber, sondern die eigene, noch
    unbelegte Variable. Jeder Lauf endete im ``UnboundLocalError``, und
    zwar vor dem Prozessstart - also noch vor jeder Ausgabe, an der man
    etwas haette sehen koennen.

    Gemerkt hat es niemand, weil ``lauf()`` in keiner Pruefung lief: Die
    einzige Beruehrung des Moduls war eine Quelltextsuche, und die sieht
    so etwas nie. Hier wird deshalb wirklich gestartet - gegen ein
    winziges gestelltes Hauptprogramm statt gegen das echte, damit die
    Pruefung ohne PKG, ohne Entpacker und in Sekundenbruchteilen laeuft.
    """

    #: Verhaelt sich wie das Hauptprogramm unter ``--ps4ffpsc``: Es meldet
    #: seine Argumente, schreibt eine Fortschrittszeile im Format des
    #: Werkzeugs und geht mit einem eigenen Rueckgabewert.
    GESTELLTES_HAUPTPROGRAMM = (
        "import sys\n"
        "print('ARGV ' + ' '.join(sys.argv[1:]))\n"
        "print('PS4FFPSC_PROGRESS {\"percent\": 42}')\n"
        "print('fertig')\n"
        "sys.exit(3)\n"
    )

    def test_lauf_startet_den_prozess_und_meldet_zurueck(self) -> None:
        # Das Modul so nehmen, wie das Programm es haelt.
        werkzeug = hauptprogramm.ps4_werkzeug
        with TemporaryDirectory() as tmp:
            haupt = Path(tmp) / "gestelltes_hauptprogramm.py"
            haupt.write_text(self.GESTELLTES_HAUPTPROGRAMM, encoding="utf-8")
            zeilen: list[str] = []
            fortschritt: list[dict] = []
            gefragte_ordner: list[str] = []

            def umgebung(ordner: str) -> dict:
                gefragte_ordner.append(ordner)
                return dict(os.environ)

            rc, gesammelt = werkzeug.lauf(
                ["doctor"], arbeitsordner=tmp,
                zeile_callback=zeilen.append,
                fortschritt_callback=fortschritt.append,
                hauptdatei=str(haupt), umgebung_bauen=umgebung)
        # Der Schalter steht vor dem Unterbefehl: Der Aufruf kommt also
        # wirklich aus befehl() und nicht aus einer zweiten Bauart daneben.
        self.assertEqual(["ARGV --ps4ffpsc doctor", "fertig"], zeilen)
        self.assertEqual(3, rc, "Rueckgabewert geht verloren")
        self.assertEqual([{"percent": 42}], fortschritt)
        self.assertEqual([tmp], gefragte_ordner)
        # Fortschrittszeilen sind Steuerung, keine Protokollausgabe.
        self.assertNotIn(werkzeug.PROGRESS_PREFIX, gesammelt)


class VerklemmungTests(unittest.TestCase):
    """Eine Ausnahme im Arbeitsfaden darf das Fenster nicht totlegen.

    Am 04.09.2026 fiel ``lauf()`` mit einem ``UnboundLocalError`` aus. Die
    Ursache ist behoben (siehe :class:`AufrufwegTests`), die Folge war aber
    eine eigene: Beide ``_arbeit()``-Rümpfe setzten ``laeuft["aktiv"]`` erst
    **nach** dem Aufruf zurück, ohne ``finally``. Flog dazwischen etwas,
    blieb das Kennzeichen für immer auf ``True`` - und beide Wächter (in
    ``_einlesen`` und ``_erstellen``) lehnen danach jeden weiteren Druck
    stillschweigend ab. Das Fenster ist dann tot, nur „Schließen" geht noch.

    Das galt für **jede** Ausnahme, nicht nur die eine behobene. Geprüft
    wird deshalb die Absicherung selbst, am Syntaxbaum: Beide Rümpfe müssen
    in einem ``try`` liegen, dessen ``finally`` das Kennzeichen freigibt.
    """

    QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

    @classmethod
    def setUpClass(cls) -> None:
        import ast

        cls.ast = ast
        cls.baum = ast.parse(cls.QUELLE.read_text(encoding="utf-8", errors="replace"))

    def _arbeitsrümpfe(self):
        """Die ``_arbeit()``-Funktionen aus dem PS4-Fenster, sonst keine.

        Über die Fenstermethode statt über ``ast.walk`` auf der ganzen
        Datei: ``_arbeit`` ist ein verbreiteter Name, und die Prüfung soll
        nicht an einem fremden Fenster hängenbleiben.
        """
        ast = self.ast
        klasse = next(k for k in self.baum.body
                      if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        fenster = next(k for k in klasse.body
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_show_ps4_pkg_converter")
        return [f for f in ast.walk(fenster)
                if isinstance(f, ast.FunctionDef) and f.name == "_arbeit"]

    @staticmethod
    def _gibt_frei(block, ast) -> bool:
        """Steht in diesem Block ``laeuft["aktiv"] = False``?"""
        for k in ast.walk(ast.Module(body=list(block), type_ignores=[])):
            if not isinstance(k, ast.Assign):
                continue
            for ziel in k.targets:
                if (isinstance(ziel, ast.Subscript)
                        and getattr(ziel.value, "id", "") == "laeuft"
                        and getattr(ziel.slice, "value", None) == "aktiv"
                        and k.value.value is False):
                    return True
        return False

    def test_es_gibt_ueberhaupt_zwei_arbeitsfaeden(self) -> None:
        """Ohne das liefe die Prüfung unten leer und meldete Erfolg."""
        self.assertEqual(
            2, len(self._arbeitsrümpfe()),
            "Erwartet werden die zwei Arbeitsfaeden (Einlesen, Erstellen) - "
            "die Auswertung greift nicht mehr.")

    def test_jeder_arbeitsfaden_gibt_im_finally_frei(self) -> None:
        ast = self.ast
        for funktion in self._arbeitsrümpfe():
            with self.subTest(zeile=funktion.lineno):
                self.assertEqual(
                    1, len(funktion.body),
                    "Der Rumpf in Zeile %d liegt nicht als Ganzes im try."
                    % funktion.lineno)
                versuch = funktion.body[0]
                self.assertIsInstance(
                    versuch, ast.Try,
                    "Der Rumpf in Zeile %d steht ungeschuetzt." % funktion.lineno)
                self.assertTrue(
                    self._gibt_frei(versuch.finalbody, ast),
                    'In Zeile %d gibt kein finally laeuft["aktiv"] frei - eine '
                    "Ausnahme legt das Fenster dauerhaft lahm."
                    % funktion.lineno)

    def test_die_pruefung_wuerde_einen_verstoss_melden(self) -> None:
        """Gegenprobe: der alte Aufbau muss durchfallen."""
        ast = self.ast
        alt = ast.parse(
            "def _arbeit():\n"
            "    rc = tuwas()\n"
            '    laeuft["aktiv"] = False\n').body[0]
        self.assertNotIsInstance(alt.body[0], ast.Try)
        neu = ast.parse(
            "def _arbeit():\n"
            "    try:\n"
            "        rc = tuwas()\n"
            "    finally:\n"
            '        laeuft["aktiv"] = False\n').body[0]
        self.assertTrue(self._gibt_frei(neu.body[0].finalbody, ast))
        # Ein finally, das etwas anderes tut, zaehlt nicht.
        leer = ast.parse(
            "def _arbeit():\n"
            "    try:\n"
            "        rc = tuwas()\n"
            "    finally:\n"
            "        aufraeumen()\n").body[0]
        self.assertFalse(self._gibt_frei(leer.body[0].finalbody, ast))

    def test_die_meldungen_gibt_es_in_beiden_sprachen(self) -> None:
        """Sonst stünde im Fenster der Schlüsselname."""
        for name in ("ps4pkg.status_scan_crashed", "ps4pkg.status_build_crashed"):
            with self.subTest(schluessel=name):
                self.assertIn(name, STRINGS)
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[name].get(sprache, "").strip())
                    self.assertIn("{error}", STRINGS[name][sprache])


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
        """Die Pruefung steht seit dem 30.08.2026 in ps4_werkzeug.

        Im Monolithen blieb die Weiterleitung; der Rumpf, um den es hier
        geht, liegt im Modul.
        """
        self.assertIn("_ps4ffpsc_abbild_pruefen", self.quelltext)
        rumpf = (PROJEKT / "ps5_validator" / "utils"
                 / "ps4_werkzeug.py").read_text(encoding="utf-8")
        anfang = rumpf.index("def abbild_pruefen(")
        rumpf = rumpf[anfang:rumpf.index("\ndef ", anfang + 10)]
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

    def test_die_trophaeengrenze_ist_dokumentiert(self) -> None:
        """Am 22.08.2026 an zwei Titeln gemessen, mit je mehreren Starts.

        Ein PS4-Titel aus einem Abbild registriert seine Trophaeen nie:
        Sonys Pruefkette (0x80551618) verlangt ein regulaer installiertes
        Paket, und ein eingehaengtes Abbild ist keines. Der Zustand steht
        auf der Konsole unter /user/trophy/conf/ - dort legte nur der ueber
        den Package Installer installierte Titel einen Ordner an.

        v1.8.80 hatte hier das Gegenteil behauptet: Nachlegen von
        npbind.dat behebe es. Das war aus einem einzelnen Lauf geschlossen
        und wurde spaeter widerlegt - weder npbind.dat noch param.sfo in
        appmeta aendern etwas. Dieser Test haelt fest, dass die Behauptung
        weg ist und der belegte Text an ihrer Stelle steht.
        """
        self.assertNotIn("ps4pkg.check_np_note", STRINGS,
                         "Der widerlegte Hinweis ist wieder da.")
        self.assertIn("ps4pkg.check_trophy_note", STRINGS)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                text = STRINGS["ps4pkg.check_trophy_note"][sprache]
                self.assertIn("0x80551618", text)
                self.assertIn("Package Installer", text)
        # Nach dem Bau gemeldet, wenn ein PS4-Titel erkannt wurde.
        rumpf = self._methode("_show_ps4_pkg_converter")
        self.assertIn("ps4pkg.check_trophy_note", rumpf)
        # Und im Handbuch erklaert.
        handbuch = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(
            encoding="utf-8")
        self.assertIn("0x80551618", handbuch)
        self.assertIn("/user/trophy/conf/", handbuch)

    def test_der_np_knopf_ist_ausgebaut(self) -> None:
        """Er legte die Datei richtig ab und bewirkte trotzdem nichts.

        Ein Knopf, der messbar folgenlos bleibt, ist schlimmer als keiner:
        Er verspricht eine Loesung, die es nicht gibt. Draussen bleiben
        muessen der Knopf, seine elf Meldungen und die beiden Methoden.
        """
        self.assertNotIn("_npbind", self.quelltext,
                         "Die NP-Bindungs-Maschinerie ist wieder eingebaut.")
        uebrig = [s for s in STRINGS if "npbind" in s]
        self.assertEqual(uebrig, [], "Es stehen noch NP-Meldungen im Text.")
        handbuch = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(
            encoding="utf-8")
        self.assertNotIn("NP-BINDUNG", handbuch)

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

    #: Was im unguenstigen Fall unterhalb des Arbeitsordners entsteht:
    #: der Ordnername mit dem Spieltitel (~52), der DLC-Zweig (42), das
    #: ".partial" waehrend des Laufs (8) und der tiefste spielinterne
    #: Pfad (~100). Am 23.08.2026 an Tetris Ultimate gemessen: 64 und 73.
    AUFSCHLAG_UNTEN = 210

    def test_grenze_laesst_dem_schlechtesten_fall_luft(self) -> None:
        """Die Schranke muss den gemessenen Aufschlag verkraften.

        Der frueher hier stehende Wert 110 rechnete den Spieltitel im
        Ordnernamen nicht mit und liess nur 10 Zeichen Luft. Ein Titel mit
        laengerem Namen waere gescheitert - und zwar mit der Meldung
        "Paket nicht unterstuetzt oder verschluesselt".
        """
        grenze = hauptprogramm._PS4FFPSC_MAX_ARBEITSPFAD
        self.assertIsInstance(grenze, int)
        self.assertLessEqual(grenze + self.AUFSCHLAG_UNTEN, 259)
        # Kurze Ziele sollen am gewaehlten Ort bleiben duerfen.
        self.assertGreaterEqual(grenze, 30)

    def test_hinweistext_nennt_laenge_und_ausweichpfad(self) -> None:
        from ps5_validator.utils.i18n import translate  # noqa: PLC0415

        text = translate("de", "ps4pkg.short_workdir", laenge=180, pfad=r"C:\ps4ffpsc_arbeit")
        self.assertIn("180", text)
        self.assertIn("ps4ffpsc_arbeit", text)


class AusweichordnerTests(unittest.TestCase):
    """Der Ausweichpfad gehoert auf das Laufwerk des Ziels.

    Frueher ging er immer auf das Systemlaufwerk. Dort ist der Platz am
    knappsten - auf diesem Rechner am 23.08.2026 nur 16 GB frei -, waehrend
    der Nutzer sein Ziel bewusst auf ein grosses Laufwerk gelegt hat.
    """

    def test_bleibt_auf_dem_laufwerk_des_ziels(self) -> None:
        if os.name != "nt":
            self.skipTest("Laufwerksbuchstaben gibt es nur unter Windows")
        geprueft = 0
        for buchstabe in ("C:", "D:", "E:", "F:"):
            if not os.path.isdir(buchstabe + os.sep):
                continue
            tief = os.path.join(buchstabe + os.sep, "irgendwo", "sehr", "tief")
            ziel = hauptprogramm._ps4ffpsc_kurzer_arbeitsordner(tief)
            self.assertTrue(ziel.upper().startswith(buchstabe))
            self.assertIn("ps4ffpsc_arbeit", ziel)
            geprueft += 1
        self.assertGreater(geprueft, 0, "kein Laufwerk zum Pruefen gefunden")

    def test_ergebnis_ist_wirklich_kurz(self) -> None:
        """Der Sinn der Uebung: Der Ausweichpfad muss Platz schaffen."""
        lang = os.path.join(os.path.abspath(os.sep), "a" * 150)
        ziel = hauptprogramm._ps4ffpsc_kurzer_arbeitsordner(lang)
        self.assertLessEqual(len(ziel), 30)


class PfadgrenzeTests(unittest.TestCase):
    """Ein zu langer Zielpfad darf nicht als Paketfehler gemeldet werden.

    Der mitgelieferte Entpacker traegt kein "longPathAware" in seinem
    Manifest und bricht deshalb an MAX_PATH ab - gemessen am 23.08.2026:
    bis 183 Zeichen laeuft er durch, ab 186 nicht mehr. Dabei meldet er
    Rueckgabewert 3, also "nicht unterstuetzt oder verschluesselt". Wer das
    ungeprueft uebernimmt, schickt den Nutzer zur Suche in die falsche Datei.
    """

    def setUp(self) -> None:
        if str(PS4_ORDNER) not in sys.path:
            sys.path.insert(0, str(PS4_ORDNER))
        from ps4ffpsc import util  # noqa: PLC0415

        self.util = util

    def test_spielraum_nur_unter_windows(self) -> None:
        frei = self.util.windows_path_headroom(Path("C:/kurz"))
        if os.name == "nt":
            self.assertEqual(frei, self.util.WINDOWS_MAX_PATH - len(str(Path("C:/kurz"))))
        else:
            self.assertIsNone(frei)

    def test_marker_erkennt_die_grenze_auch_ohne_pfadlaenge(self) -> None:
        """Der Fehlertext allein genuegt - unabhaengig von der Systemsprache.

        Der Windows-Text dahinter kommt uebersetzt, der Name der Operation
        nicht. Deshalb wird auf ``create_directories`` geprueft.
        """
        kurz = Path("C:/k")
        self.assertTrue(self.util.looks_like_path_length_failure(
            kurz, r'create_directories: Der Dateiname ist zu lang.: "C:/x"'))
        self.assertFalse(self.util.looks_like_path_length_failure(
            kurz, "Invalid PKG magic"))

    def test_enger_zielpfad_zaehlt_auch_ohne_marker(self) -> None:
        """Genau an der Grenze meldet der Entpacker gar keinen Hinweis.

        Er schreibt dort nur "Failed to open PKG extraction input or
        output". Ohne die Laengenpruefung bliebe der Fall unerkannt.
        """
        if os.name != "nt":
            self.skipTest("MAX_PATH gibt es nur unter Windows")
        eng = Path("C:/" + "x" * 240)
        self.assertTrue(self.util.looks_like_path_length_failure(
            eng, "Failed to open PKG extraction input or output"))

    def test_hinweis_nennt_zahlen_und_ausweg(self) -> None:
        if os.name != "nt":
            self.skipTest("MAX_PATH gibt es nur unter Windows")
        pfad = Path("C:/" + "x" * 200)
        text = self.util.path_length_hint(pfad)
        self.assertIn(str(len(str(pfad))), text)
        self.assertIn(str(self.util.WINDOWS_MAX_PATH), text)
        self.assertIn("shorter", text)


class AlleOhneSpielTests(unittest.TestCase):
    """``--all`` darf nicht nach ``--all`` verlangen.

    Frueher lautete die Meldung immer "provide TITLE_ID or --all" - auch
    dann, wenn der Nutzer ``--all`` gerade angegeben hatte und nur kein
    brauchbares Spiel gefunden wurde.
    """

    def setUp(self) -> None:
        if str(PS4_ORDNER) not in sys.path:
            sys.path.insert(0, str(PS4_ORDNER))
        from ps4ffpsc import cli  # noqa: PLC0415

        self.melden = cli._no_title_ids_message

    def test_ohne_all_bleibt_die_alte_aufforderung(self) -> None:
        self.assertEqual(self.melden({"games": {}, "unsupported": []}, False),
                         "provide TITLE_ID or --all")

    def test_leeres_inventar_sagt_das_auch(self) -> None:
        text = self.melden({"games": {}, "unsupported": []}, True)
        self.assertIn("inventory is empty", text)
        self.assertNotIn("provide TITLE_ID", text)

    def test_abgelehnte_pakete_werden_gezaehlt(self) -> None:
        text = self.melden({"games": {}, "unsupported": [1, 2, 3]}, True)
        self.assertIn("3 package(s) were rejected", text)
        self.assertNotIn("provide TITLE_ID", text)



class HelferProPlattformTests(unittest.TestCase):
    """Auf dem Mac wurde die Windows-Datei gewaehlt.

    Gemeldet am 23.08.2026 von einem Nutzer mit Apple Silicon:

        ps4ffpsc: [Errno 13] Permission denied:
        '.../Contents/Frameworks/PS4FFPFSC-0__dot__2__dot__8/bin/
        ps4_pkg_extract.exe'

    In ``bin/`` liegen beide Fassungen nebeneinander. ``find_extractor``
    hatte die Namen fest als ``("ps4_pkg_extract.exe", "ps4_pkg_extract")``
    stehen - die Windows-Datei zuerst, auf jeder Plattform. Sie hat auf dem
    Mac kein Ausfuehrungsrecht, daher Errno 13.
    """

    #: Plattform und Architektur zusammen entscheiden. Die Mac-Fassung gibt
    #: es nur fuer Apple Silicon; fuer Intel-Macs und Linux liefert der
    #: Hersteller keine, dort darf deshalb NICHTS herauskommen. Am
    #: 23.08.2026 auf einem echten Intel-Laeufer belegt: Wer dort die
    #: arm64-Datei anbietet, erntet "Bad CPU type in executable".
    ERWARTET = {
        ("win32", "AMD64"): ("ps4_pkg_extract.exe", "ps4-dlc-patch.exe"),
        ("darwin", "arm64"): ("ps4_pkg_extract", "ps4-dlc-patch"),
        ("darwin", "x86_64"): (None, None),
        ("linux", "x86_64"): (None, None),
    }

    def setUp(self) -> None:
        if str(PS4_ORDNER) not in sys.path:
            sys.path.insert(0, str(PS4_ORDNER))
        from ps4ffpsc.dlc_embed import find_dlc_helper  # noqa: PLC0415
        from ps4ffpsc.inventory import find_extractor  # noqa: PLC0415

        self.entpacker = find_extractor
        self.dlc_helfer = find_dlc_helper

    def test_jede_plattform_bekommt_ihre_datei(self) -> None:
        for (plattform, cpu), (entpacker, helfer) in self.ERWARTET.items():
            with self.subTest(plattform=plattform, cpu=cpu):
                with mock.patch.object(sys, "platform", plattform),                         mock.patch.object(platform, "machine",
                                          lambda c=cpu: c):
                    gefunden = self.entpacker(PS4_ORDNER)
                    if entpacker is None:
                        self.assertIsNone(gefunden)
                        continue
                    self.assertIsNotNone(gefunden, "kein Entpacker gefunden")
                    self.assertEqual(gefunden.name, entpacker)
                    self.assertEqual(self.dlc_helfer(PS4_ORDNER).name, helfer)

    def test_windows_datei_nie_ausserhalb_von_windows(self) -> None:
        """Der Kern des ersten Fehlers: keine .exe auf Mac oder Linux.

        Wo gar nichts angeboten wird, ist die Bedingung ebenfalls erfuellt -
        und richtig, denn dort gibt es keinen brauchbaren Bau.
        """
        for plattform, cpu in (("darwin", "arm64"), ("darwin", "x86_64"),
                               ("linux", "x86_64")):
            with self.subTest(plattform=plattform, cpu=cpu):
                with mock.patch.object(sys, "platform", plattform),                         mock.patch.object(platform, "machine",
                                          lambda c=cpu: c):
                    gefunden = self.entpacker(PS4_ORDNER)
                    if gefunden is not None:
                        self.assertFalse(gefunden.name.endswith(".exe"))
                    try:
                        helfer = self.dlc_helfer(PS4_ORDNER)
                    except Exception:
                        helfer = None
                    if helfer is not None:
                        self.assertFalse(helfer.name.endswith(".exe"))


class AusfuehrungsrechtTests(unittest.TestCase):
    """Aus dem Buendel kommen die Helfer ohne Ausfuehrungsrecht.

    PyInstaller legt den Ordner unter ``datas`` ab, und dabei geht das
    Recht verloren. Fuer UFS2Tool zieht das Hauptprogramm es laengst nach;
    fuer die PS4-Helfer fehlte dasselbe.
    """

    def setUp(self) -> None:
        if str(PS4_ORDNER) not in sys.path:
            sys.path.insert(0, str(PS4_ORDNER))
        from ps4ffpsc.util import ensure_executable  # noqa: PLC0415

        self.ensure_executable = ensure_executable

    def test_unter_windows_ist_nichts_zu_tun(self) -> None:
        if os.name != "nt":
            self.skipTest("gilt nur unter Windows")
        self.assertTrue(self.ensure_executable(PS4_ORDNER / "bin"
                                               / "ps4_pkg_extract"))

    def test_fehlende_datei_wirft_nicht(self) -> None:
        """Auch ein Fehlschlag muss eine Antwort sein, keine Ausnahme."""
        try:
            self.ensure_executable(PS4_ORDNER / "bin" / "gibtsnicht")
        except Exception as exc:  # noqa: BLE001
            self.fail("ensure_executable warf %r" % exc)

    def test_hauptprogramm_zieht_das_recht_nach(self) -> None:
        """Die Vorpruefung der Oberflaeche muss "startbar" heissen."""
        quelltext = inspect.getsource(hauptprogramm._ps4ffpsc_entpacker)
        self.assertIn("chmod", quelltext)
        self.assertIn("0o111", quelltext)


class AbsturzmeldungTests(unittest.TestCase):
    """Ein abgestuerzter Entpacker muss das auch sagen.

    Am 23.08.2026 an einem echten Retail-Patch nachgestellt
    (EP0001-CUSA00775_00-TETRISGAME000000-A0102-V0100.pkg): Der Entpacker
    stuerzt mit 0xC0000005 ab und hinterlaesst keine Ausgabe. Die Meldung
    lautete deshalb

        extractor failed (3221225477) for ...pkg:

    - eine nackte Zahl, und hinter dem Doppelpunkt nichts. Wer das liest,
    sucht den Fehler bei sich oder in der Datei; er liegt aber im
    mitgelieferten Entpacker.
    """

    def setUp(self) -> None:
        if str(PS4_ORDNER) not in sys.path:
            sys.path.insert(0, str(PS4_ORDNER))
        from ps4ffpsc.util import crash_description  # noqa: PLC0415

        self.beschreiben = crash_description

    def test_gemessene_codes_werden_benannt(self) -> None:
        """Beide sind an echten Paketen aufgetreten."""
        for code, wort in ((3221225477, "memory access violation"),
                           (3221225725, "stack overflow")):
            with self.subTest(code=code):
                text = self.beschreiben(code)
                self.assertIn("crashed", text)
                self.assertIn(wort, text)
                self.assertIn("0x%08X" % code, text,
                              "Die Zahl gehoert als Hex dazu, nicht dezimal.")

    def test_unbekannter_absturz_wird_trotzdem_erkannt(self) -> None:
        """Die Liste kann nicht vollstaendig sein - der Bereich schon."""
        text = self.beschreiben(0xC0000094)
        self.assertIn("crashed", text)
        self.assertIn("0xC0000094", text)

    def test_gewoehnliche_rueckgabewerte_sind_kein_absturz(self) -> None:
        """Sonst waere jeder normale Fehlschlag ploetzlich ein Absturz."""
        for code in (0, 1, 2, 3, 255):
            with self.subTest(code=code):
                self.assertEqual(self.beschreiben(code), "")
        self.assertEqual(self.beschreiben(None), "")

    def test_der_pfad_wird_wirklich_durchlaufen(self) -> None:
        """Nicht nur der Quelltext - der Aufruf selbst.

        Hier fehlte einmal der Import von crash_description in
        inventory.py. Uebersetzen liess sich das trotzdem, und keine
        Pruefung fiel darauf herein: Der Zweig laeuft nur, wenn der
        Entpacker gar nichts ausgibt. Erst pyflakes fand es. Dieser Test
        stellt genau den Fall nach - ein Entpacker, der immer abstuerzt.
        """
        import tempfile  # noqa: PLC0415

        from ps4ffpsc.inventory import inspect_package  # noqa: PLC0415

        with tempfile.TemporaryDirectory(prefix="ps4_crash_") as ordner:
            basis = Path(ordner)
            paket = basis / "spiel.pkg"
            paket.write_bytes(bytes((0x7F,)) + b"CNT" + os.urandom(2048))
            skript = basis / "immer_ab.py"
            skript.write_text(
                "import sys" + chr(10) + "sys.exit(3221225477)" + chr(10),
                encoding="utf-8")
            starter = basis / ("start.cmd" if os.name == "nt"
                               else "start.sh")
            if os.name == "nt":
                starter.write_text(
                    '@"%s" "%s" %%*' % (sys.executable, skript) + chr(10),
                    encoding="utf-8")
            else:
                starter.write_text(
                    "#!/bin/sh" + chr(10)
                    + 'exec "%s" "%s" "$@"' % (sys.executable, skript)
                    + chr(10), encoding="utf-8")
                starter.chmod(0o755)

            befund = inspect_package(starter, paket, compute_sha256=False)

        self.assertFalse(befund.get("supported"))
        grund = befund.get("reason", "")
        self.assertIn("crashed", grund,
                      "Der Absturz muss beim Namen genannt werden: %r" % grund)
        self.assertIn("0xC0000005", grund)

    def test_die_pipeline_nennt_den_schuldigen(self) -> None:
        """Der Nutzer soll nicht bei sich suchen."""
        quelle = (PS4_ORDNER / "ps4ffpsc" / "pipeline.py").read_text(
            encoding="utf-8")
        self.assertIn("extractor_crashed", quelle)
        self.assertIn("fault in the bundled extractor", quelle)


class ArchitekturTests(unittest.TestCase):
    """Die Mac-Fassung gibt es nur fuer Apple Silicon.

    Am 23.08.2026 auf einem echten Intel-Laeufer gemessen: Nachdem die
    Auswahl plattformbewusst geworden war, aber noch nicht
    architekturbewusst, bot sie dort die arm64-Datei an. Der Start endete
    mit

        OSError: [Errno 86] Bad CPU type in executable: .../ps4_pkg_extract

    Also derselbe Fehler wie zuvor mit der .exe, nur eine Stufe spaeter.
    Dasselbe gilt unter Linux, wo dieselbe Datei danebenliegt.
    """

    def setUp(self) -> None:
        if str(PS4_ORDNER) not in sys.path:
            sys.path.insert(0, str(PS4_ORDNER))
        from ps4ffpsc.dlc_embed import find_dlc_helper  # noqa: PLC0415
        from ps4ffpsc.inventory import find_extractor  # noqa: PLC0415
        from ps4ffpsc.util import (  # noqa: PLC0415
            executable_architectures,
            runs_on_this_cpu,
        )

        self.architekturen = executable_architectures
        self.laeuft_hier = runs_on_this_cpu
        self.entpacker = find_extractor
        self.dlc_helfer = find_dlc_helper

    def test_die_mitgelieferten_dateien_werden_erkannt(self) -> None:
        bin_ordner = PS4_ORDNER / "bin"
        for name in ("ps4_pkg_extract", "ps4-dlc-patch"):
            with self.subTest(datei=name):
                self.assertEqual(self.architekturen(bin_ordner / name),
                                 {"arm64"})
        for name in ("ps4_pkg_extract.exe", "ps4-dlc-patch.exe"):
            with self.subTest(datei=name):
                self.assertEqual(self.architekturen(bin_ordner / name), set(),
                                 "Eine PE-Datei ist kein Mach-O.")

    def test_keine_datei_ist_kein_absturz(self) -> None:
        self.assertEqual(self.architekturen(PS4_ORDNER / "gibtsnicht"), set())
        self.assertTrue(self.laeuft_hier(PS4_ORDNER / "gibtsnicht"),
                        "Ohne Mach-O entscheidet der Dateiname.")

    def test_auswahl_je_plattform_und_architektur(self) -> None:
        """Vier Faelle, und nur bei zweien darf etwas herauskommen."""
        faelle = {
            ("win32", "AMD64"): "ps4_pkg_extract.exe",
            ("darwin", "arm64"): "ps4_pkg_extract",
            ("darwin", "x86_64"): None,
            ("linux", "x86_64"): None,
        }
        for (plattform, cpu), erwartet in faelle.items():
            with self.subTest(plattform=plattform, cpu=cpu):
                with mock.patch.object(sys, "platform", plattform),                         mock.patch.object(platform, "machine",
                                          lambda c=cpu: c):
                    gefunden = self.entpacker(PS4_ORDNER)
                    if erwartet is None:
                        self.assertIsNone(
                            gefunden,
                            "Fuer diese Architektur gibt es keinen Bau - es "
                            "darf keiner angeboten werden.")
                    else:
                        self.assertIsNotNone(gefunden)
                        self.assertEqual(gefunden.name, erwartet)

    def test_der_dlc_helfer_haelt_sich_daran_auch(self) -> None:
        for plattform, cpu in (("darwin", "x86_64"), ("linux", "x86_64")):
            with self.subTest(plattform=plattform, cpu=cpu):
                with mock.patch.object(sys, "platform", plattform),                         mock.patch.object(platform, "machine",
                                          lambda c=cpu: c):
                    with self.assertRaises(Exception):
                        self.dlc_helfer(PS4_ORDNER)





class ZwischengespeicherterBestandTests(unittest.TestCase):
    """Ein zweites Backup bekam die Spiele des ersten.

    Aus der Praxis gemeldet am 23.08.2026: Ein PKG-Backup einlesen - alles
    richtig angezeigt. Ein zweites einlesen - Fehler. Danach scheiterte auch
    das erste, das eben noch ging.

    Ursache: ``list`` war der einzige Befehl ohne ``refresh=True``, und
    ``load_or_scan`` gab jeden vorhandenen ``package_inventory.json``
    ungeprueft zurueck. Weil die Oberflaeche fuer jede Quelle **denselben**
    Arbeitsordner benutzt, traf das dort immer zu.
    """

    @classmethod
    def setUpClass(cls) -> None:
        wurzel = PROJEKT / "PS4FFPFSC-0.2.8"
        if str(wurzel) not in sys.path:
            sys.path.insert(0, str(wurzel))
        from ps4ffpsc.pipeline import Settings, inventory_matches_source
        cls.Settings = Settings
        cls.passt = staticmethod(inventory_matches_source)

    def _einstellungen(self, ordner: Path, pkgs=(), dumps=()):
        return self.Settings(
            root=ordner, pkg_dir=ordner / "pkg", unpacked_dir=ordner / "unpacked",
            output_dir=ordner / "out", work_dir=ordner, temp_dir=ordner,
            pkg_files=tuple(Path(p) for p in pkgs),
            dump_dirs=tuple(Path(d) for d in dumps))

    def test_derselbe_bestand_wird_weiterbenutzt(self) -> None:
        """Sonst waere der Zwischenspeicher wertlos."""
        with TemporaryDirectory() as tmp:
            ordner = Path(tmp)
            bestand = {"selected_pkg_files": [str(ordner / "a.pkg")],
                       "pkg_dir": str(ordner / "pkg")}
            self.assertTrue(self.passt(
                bestand, self._einstellungen(ordner, [ordner / "a.pkg"])))

    def test_eine_andere_quelle_loest_neuen_scan_aus(self) -> None:
        """Der gemeldete Fehler."""
        with TemporaryDirectory() as tmp:
            ordner = Path(tmp)
            bestand = {"selected_pkg_files": [str(ordner / "a.pkg")],
                       "pkg_dir": str(ordner / "pkg")}
            self.assertFalse(self.passt(
                bestand, self._einstellungen(ordner, [ordner / "b.pkg"])))

    def test_schreibweise_des_pfades_ist_egal(self) -> None:
        """Sonst scannt das Werkzeug bei jedem Einlesen neu.

        Windows meldet Pfade mal mit C:, mal mit c:, mal mit Schraegstrich.
        """
        with TemporaryDirectory() as tmp:
            ordner = Path(tmp)
            roh = str(ordner / "a.pkg")
            bestand = {"selected_pkg_files": [roh.upper().replace("\\", "/")],
                       "pkg_dir": str(ordner / "pkg")}
            self.assertTrue(self.passt(
                bestand, self._einstellungen(ordner, [roh])))

    def test_auch_ein_anderer_dump_ordner_faellt_auf(self) -> None:
        with TemporaryDirectory() as tmp:
            ordner = Path(tmp)
            bestand = {"selected_pkg_files": [],
                       "selected_dump_dirs": [str(ordner / "spielA")]}
            self.assertTrue(self.passt(
                bestand, self._einstellungen(ordner, dumps=[ordner / "spielA"])))
            self.assertFalse(self.passt(
                bestand, self._einstellungen(ordner, dumps=[ordner / "spielB"])))

    def test_list_darf_den_bestand_weiter_benutzen(self) -> None:
        """Die Behebung gehoert in load_or_scan, nicht in die Kommandozeile.

        Mit ``refresh=True`` bei ``list`` wuerde jedes Einlesen neu scannen -
        auch das wiederholte Einlesen derselben Quelle, das Minuten kostet.
        """
        kommandozeile = (PROJEKT / "PS4FFPFSC-0.2.8" / "ps4ffpsc"
                         / "cli.py").read_text(encoding="utf-8")
        self.assertIn('if args.command == "list":\n            inventory = '
                      'load_or_scan(settings)', kommandozeile)


if __name__ == "__main__":
    unittest.main(verbosity=2)
