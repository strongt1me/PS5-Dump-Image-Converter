"""Regressionstests: Die Auswahl KOMPRESSION (PFS) muss auch wirken.

Gemeldet beim Benutzen: Die Stufen 1, 3, 6 und 9 aendern nichts am Ergebnis.

Zwei Ursachen, beide unabhaengig vom Betriebssystem:

1. ``_resolve_pack_profile`` setzte die Stufe immer aus ``PACK_PROFILE_MATRIX``
   (9 bei Aufgabe 1, 8 bei Aufgabe 3/6, 7 bei Aufgabe 4) und ueberschrieb damit
   ``self.zstd_level``, den Wert aus dem Auswahlfeld. Da alle mkpfs-Aufrufe
   ihren Wert aus ``profile["level"]`` beziehen, erreichte die Auswahl den
   Packvorgang nie.
2. Die Groessenschaetzung rechnete mit **zstd** auf der gewaehlten Stufe,
   waehrend mkpfs mit **zlib** auf der festen Stufe packte. Die Vorhersage
   reagierte also auf die Auswahl, das Ergebnis nicht - dieser Widerspruch war
   das, was auffiel.
"""
from __future__ import annotations

import os
import random
import sys
import tempfile
import threading
import time
import unittest
import zlib
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils.i18n import ZSTD_LEVEL_KEYS

ANGEBOTENE_STUFEN = tuple(level for _key, level in ZSTD_LEVEL_KEYS)


class _Var:
    """Ersatz fuer tk.StringVar - der Test kommt ohne Fenster aus."""

    def __init__(self, wert: str = "") -> None:
        self._wert = wert

    def get(self) -> str:
        return self._wert

    def set(self, wert: str) -> None:
        self._wert = wert


class _Wurzel:
    """Ersatz fuer das Tk-Fenster: sammelt die ``after``-Rueckrufe ein.

    Die Schaetzung laeuft in einem Hintergrund-Thread und meldet ihr Ergebnis
    ueber ``root.after`` zurueck. Der Test wartet, bis dort etwas ankommt, und
    arbeitet es dann ab - so braucht es weder eine Ereignisschleife noch das
    Beitreten fremder Threads.
    """

    def __init__(self) -> None:
        self._rueckrufe: list = []
        self._sperre = threading.Lock()

    def after(self, _verzoegerung, rueckruf=None, *args):
        if rueckruf is None:
            return None
        with self._sperre:
            self._rueckrufe.append((rueckruf, args))
        return "nachher"

    def warten(self, sekunden: float = 5.0) -> bool:
        """Wartet, bis mindestens ein Rueckruf vorliegt."""
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            with self._sperre:
                if self._rueckrufe:
                    return True
            time.sleep(0.02)
        return False

    def abarbeiten(self) -> None:
        with self._sperre:
            offen, self._rueckrufe = self._rueckrufe, []
        for rueckruf, args in offen:
            rueckruf(*args)


def _profil(modus: str, stufe: object, groesse: int = 8 * 1024**3) -> dict:
    """Ruft _resolve_pack_profile ohne Fenster auf, mit gesetzter Stufe."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    if stufe is not None:
        gui.zstd_level = stufe
    return APP.PS5ConverterGUI._resolve_pack_profile(gui, modus, groesse)


class StufeErreichtDenPackvorgang(unittest.TestCase):
    """Der Kern des Fehlers: Die Auswahl muss in profile["level"] ankommen."""

    def test_jede_angebotene_stufe_kommt_an(self) -> None:
        for modus in ("pack_folder", "pack_file", "ffpkg_to_ffpfsc"):
            for stufe in ANGEBOTENE_STUFEN:
                with self.subTest(modus=modus, stufe=stufe):
                    self.assertEqual(_profil(modus, stufe)["level"], stufe)

    def test_verschiedene_stufen_ergeben_verschiedene_profile(self) -> None:
        """Der eigentliche Beschwerdegrund: vorher war das Ergebnis immer gleich."""
        stufen = {_profil("pack_folder", s)["level"] for s in ANGEBOTENE_STUFEN}
        self.assertEqual(stufen, set(ANGEBOTENE_STUFEN))

    def test_ohne_auswahl_gilt_ueberall_die_vorgabe(self) -> None:
        """Die Werte je Aufgabe (9/8/7) sind weg - es gibt nur noch eine Vorgabe.

        Sie waren tot, sobald die Auswahl Vorrang bekam: Es ist immer eine
        gueltige Stufe gespeichert, der Rueckfall griff also nie. Der
        ps5-exfat-builder haelt es genauso - eine Einstellung fuer alle Wege.
        """
        for modus in ("pack_folder", "pack_file", "ffpkg_to_ffpfsc"):
            with self.subTest(modus=modus):
                self.assertEqual(_profil(modus, None)["level"], APP.ZSTD_VORGABE)

    def test_die_tabelle_kennt_keine_stufe_mehr(self) -> None:
        for modus, cfg in APP.PACK_PROFILE_MATRIX.items():
            with self.subTest(modus=modus):
                self.assertNotIn("level", cfg)

    def test_unsinnige_stufe_faellt_auf_die_vorgabe_zurueck(self) -> None:
        """Ein Wert ausserhalb der angebotenen Stufen darf nichts verbiegen."""
        for stufe in (0, 5, 7, 42, -1, "6", None):
            with self.subTest(stufe=stufe):
                self.assertEqual(_profil("pack_folder", stufe)["level"], APP.ZSTD_VORGABE)

    def test_stufen_bleiben_im_von_mkpfs_erlaubten_bereich(self) -> None:
        """mkpfs nimmt --compression-level nur von 0 bis 9 an."""
        for stufe in ANGEBOTENE_STUFEN:
            self.assertGreaterEqual(stufe, 0)
            self.assertLessEqual(stufe, 9)


class VorgabeUndAuswahlPassenZusammen(unittest.TestCase):
    def test_vorgabe_ist_eine_angebotene_stufe(self) -> None:
        """Der Startwert stand auf 7 - das bot das Auswahlfeld nie an.

        Seit dem Abgleich mit den Referenzen ist die Vorgabe 9: mkpfs selbst
        hat --compression-level auf 9, der ps5-exfat-builder nennt sie
        "Stable / safest (default)".
        """
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self.zstd_level: int = ZSTD_VORGABE", quelltext)
        self.assertNotIn("self.zstd_level: int = 7", quelltext)
        self.assertIn(APP.ZSTD_VORGABE, APP.ZSTD_STUFEN)
        del gui

    def test_zstd_stufen_stammen_aus_derselben_quelle_wie_das_auswahlfeld(self) -> None:
        self.assertEqual(APP.ZSTD_STUFEN, frozenset(ANGEBOTENE_STUFEN))


class SchaetzungPasstZumPackverfahren(unittest.TestCase):
    """Die Vorhersage muss mit demselben Verfahren rechnen, das auch packt."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        # Textaehnliche Daten aus einem festen Zufallsstrom: Sie landen mit rund
        # 30-40 % mitten im Gueltigkeitsbereich der Funktion. Stark wiederholte
        # Muster taugen hier nicht - die schrumpfen unter die 5-%-Untergrenze,
        # auf die die Funktion begrenzt, und dann liegen alle Stufen gleichauf.
        wuerfel = random.Random(20260817)
        woerter = [f"wort{n:04d}" for n in range(400)]
        self.quelle = os.path.join(self._tmp.name, "probe.bin")
        with open(self.quelle, "wb") as datei:
            for _ in range(600):
                zeile = " ".join(wuerfel.choice(woerter) for _ in range(64))
                datei.write((zeile + "\n").encode("ascii"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _verhaeltnis(self, stufe: int) -> float:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        return APP.PS5ConverterGUI._estimate_compression_ratio(gui, self.quelle, level=stufe)

    def _stichprobe(self) -> bytes:
        """Derselbe Ausschnitt, den die Funktion aus einer Einzeldatei liest.

        Sie setzt bewusst bei einem Viertel der Datei auf, weil der Anfang
        (Kopfdaten, Nullbereiche) nicht fuer den Rest steht.
        """
        rohdaten = Path(self.quelle).read_bytes()
        return rohdaten[len(rohdaten) // 4:]

    def test_schaetzung_liegt_im_gueltigen_bereich(self) -> None:
        for stufe in ANGEBOTENE_STUFEN:
            with self.subTest(stufe=stufe):
                wert = self._verhaeltnis(stufe)
                self.assertGreater(wert, 0.0)
                self.assertLessEqual(wert, 0.99)

    def test_die_hoechste_stufe_schaetzt_kleiner_als_die_niedrigste(self) -> None:
        """Nur die Spanne wird geprueft, nicht jeder einzelne Schritt.

        zlib sucht auf hoeheren Stufen laenger, findet aber nicht zwangslaeufig
        ein besseres Ergebnis: Zwischen 6 und 9 lagen auf einem Linux-Lauf
        0,2184 gegen 0,2187 - die hoehere Stufe also minimal darueber. Eine
        Zusicherung ueber jeden Nachbarschritt haette an dieser Eigenart von
        zlib gelegen, nicht am Programm. Ueber die volle Spanne ist der
        Unterschied dagegen eindeutig.
        """
        stufen = sorted(ANGEBOTENE_STUFEN)
        niedrigste = self._verhaeltnis(stufen[0])
        hoechste = self._verhaeltnis(stufen[-1])
        self.assertLess(hoechste, niedrigste)

    def test_schaetzung_entspricht_zlib_nicht_zstd(self) -> None:
        """Belegt die zweite Ursache: Es wird zlib gerechnet, wie mkpfs es tut."""
        probe = self._stichprobe()
        for stufe in ANGEBOTENE_STUFEN:
            with self.subTest(stufe=stufe):
                erwartet = len(zlib.compress(probe, stufe)) / len(probe)
                self.assertAlmostEqual(self._verhaeltnis(stufe), erwartet, places=3)

    def test_die_stufen_ergeben_messbar_verschiedene_schaetzungen(self) -> None:
        """Ohne Unterschied waere der Test oben auch mit einer Konstante gruen."""
        werte = {self._verhaeltnis(stufe) for stufe in ANGEBOTENE_STUFEN}
        self.assertGreater(len(werte), 1)

    def test_alter_name_ist_verschwunden(self) -> None:
        self.assertFalse(hasattr(APP.PS5ConverterGUI, "_estimate_zstd_ratio"))


class StufenwechselRechnetDieSchaetzungNeu(unittest.TestCase):
    """Beim Umstellen der Stufe muss die angezeigte Zielgroesse mitgehen.

    Beim Test der fertigen Anwendung aufgefallen: Der Packvorgang bekam die neue
    Stufe zwar, die Anzeige blieb aber auf dem alten Wert stehen. Grund war, dass
    die Schaetzung ausschliesslich beim Wechsel der Quelle lief. Fuer den
    Benutzer sah die Auswahl damit weiterhin wirkungslos aus.
    """

    def _gui(self, modus: str, quelle: str, groesse: int = 700 * 1024**2):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.is_running = False
        gui.zstd_level = 6
        gui._calc_generation = 0
        gui._last_source_size_bytes = groesse
        gui.current_mode = _Var(modus)
        gui.source_path = _Var(quelle)
        gui.compression_level_var = _Var("6 – Ausgewogen")
        gui._zstd_level_options = {"1 – Schnellste": 1, "6 – Ausgewogen": 6}
        gui._save_setting = lambda *a, **k: None
        gui._fmt_bytes = lambda n: f"{n} B"
        gui._estimate_compression_ratio = lambda pfad, level=6: {1: 0.80, 6: 0.55}[level]
        self.gesetzt: list[str] = []
        gui._set_size_label_idle = self.gesetzt.append
        gui.root = _Wurzel()
        return gui

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.quelle = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _umstellen_auf_stufe_1(self, gui, erwartet_anzeige: bool = True) -> None:
        gui.compression_level_var.set("1 – Schnellste")
        APP.PS5ConverterGUI._on_compression_level_changed(gui)
        # Bei den Faellen, in denen bewusst nichts passieren soll, waere ein
        # Warten reine Wartezeit - dort genuegt eine kurze Frist.
        gui.root.warten(5.0 if erwartet_anzeige else 0.5)
        gui.root.abarbeiten()

    def test_aufgabe_1_aktualisiert_die_anzeige(self) -> None:
        gui = self._gui("pack_folder", self.quelle)
        self._umstellen_auf_stufe_1(gui)
        self.assertTrue(self.gesetzt, "Die Anzeige wurde gar nicht angefasst")
        self.assertIn("~587202560 B", self.gesetzt[-1])  # 700 MiB * 0.80

    def test_aufgabe_3_aktualisiert_die_anzeige(self) -> None:
        datei = os.path.join(self._tmp.name, "quelle.exfat")
        open(datei, "wb").write(b"x")
        gui = self._gui("pack_file", datei)
        self._umstellen_auf_stufe_1(gui)
        self.assertTrue(self.gesetzt)
        self.assertIn("~587202560 B", self.gesetzt[-1])

    def test_ohne_schaetzung_in_der_aufgabe_passiert_nichts(self) -> None:
        """Aufgabe 8 zeigt keine Zielgroesse - dort darf nichts gerechnet werden."""
        gui = self._gui("dump_validator", self.quelle)
        self._umstellen_auf_stufe_1(gui, erwartet_anzeige=False)
        self.assertEqual(self.gesetzt, [])

    def test_waehrend_eines_laufs_wird_nicht_gerechnet(self) -> None:
        """Eine laufende Aufgabe darf nicht durch die Stichprobe gestoert werden."""
        gui = self._gui("pack_folder", self.quelle)
        gui.is_running = True
        self._umstellen_auf_stufe_1(gui, erwartet_anzeige=False)
        self.assertEqual(self.gesetzt, [])

    def test_ohne_bekannte_quellgroesse_wird_nicht_gerechnet(self) -> None:
        gui = self._gui("pack_folder", self.quelle, groesse=0)
        self._umstellen_auf_stufe_1(gui, erwartet_anzeige=False)
        self.assertEqual(self.gesetzt, [])

    def test_schnelles_umschalten_laesst_keinen_alten_wert_stehen(self) -> None:
        """Die zuletzt gewaehlte Stufe gewinnt, nicht die zuletzt fertige.

        Ohne eigenen Zaehler haengt das Ergebnis davon ab, welche Stichprobe
        zuerst durchlaeuft - bei schnellem Hin und Her bliebe ein ueberholter
        Wert stehen.
        """
        gui = self._gui("pack_folder", self.quelle)
        langsam = threading.Event()

        def _messen(pfad, level=6):
            if level == 6:
                # Die zuerst gestartete Rechnung kommt absichtlich zu spaet.
                langsam.wait(timeout=3)
                return 0.55
            return 0.80

        gui._estimate_compression_ratio = _messen

        gui.compression_level_var.set("6 – Ausgewogen")
        APP.PS5ConverterGUI._on_compression_level_changed(gui)   # startet die langsame
        gui.compression_level_var.set("1 – Schnellste")
        APP.PS5ConverterGUI._on_compression_level_changed(gui)   # ueberholt sie
        gui.root.warten(5.0)
        gui.root.abarbeiten()
        langsam.set()
        time.sleep(0.3)
        gui.root.abarbeiten()

        self.assertTrue(self.gesetzt)
        self.assertIn("~587202560 B", self.gesetzt[-1],
                      "Der Wert der ueberholten Stufe 6 hat sich durchgesetzt")

    def test_die_stufe_wird_trotzdem_uebernommen(self) -> None:
        """Auch wo keine Anzeige folgt, muss der Wert selbst ankommen."""
        gui = self._gui("dump_validator", self.quelle)
        self._umstellen_auf_stufe_1(gui, erwartet_anzeige=False)
        self.assertEqual(gui.zstd_level, 1)


class KompressionsschalterTests(unittest.TestCase):
    """Jeder ``pack file``-Aufruf sagt ausdruecklich, ob komprimiert wird.

    In mkpfs hat ``--compress`` die Vorgabe ``default=True``
    (MkPFS-0.0.9/mkpfs/cli.py). Eine Aufrufstelle ohne Angabe erzeugt also
    dasselbe wie eine mit ``--compress`` - aber nur so lange, wie diese
    Vorgabe steht. Bis v1.8.55 drueckten die vier Stellen dieselbe Sache auf
    drei verschiedene Arten aus, eine davon gar nicht.
    """

    QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

    def test_jede_pack_file_stelle_nennt_die_kompression(self):
        text = self.QUELLE.read_text(encoding="utf-8")
        zeilen = text.splitlines()
        stellen = [i for i, z in enumerate(zeilen) if '"pack", "file",' in z]
        self.assertGreaterEqual(len(stellen), 4,
                                "Es wurden kaum pack-file-Aufrufe gefunden.")
        for i in stellen:
            block = "\n".join(zeilen[i:i + 12])
            self.assertTrue(
                '"--compress"' in block or '"--no-compress"' in block,
                "Der pack-file-Aufruf in Zeile %d verlaesst sich auf die "
                "Vorgabe von mkpfs, statt die Kompression zu nennen." % (i + 1))

    def test_keine_listenentpackung_mehr(self):
        # *(["--no-compress"] if uncompressed else []) liess im komprimierten
        # Fall gar nichts stehen und sah dabei aus wie eine Angabe.
        text = self.QUELLE.read_text(encoding="utf-8")
        self.assertNotIn('*(["--no-compress"]', text)

    def test_die_innere_stufe_bleibt_unkomprimiert(self):
        # pack folder erzeugt das innere PFS; komprimiert wird erst der
        # aeussere Container. Faellt das um, entsteht doppelt komprimierter
        # Inhalt.
        text = self.QUELLE.read_text(encoding="utf-8")
        zeilen = text.splitlines()
        stellen = [i for i, z in enumerate(zeilen) if '"pack", "folder",' in z]
        self.assertGreaterEqual(len(stellen), 2)
        for i in stellen:
            block = "\n".join(zeilen[i:i + 10])
            self.assertIn('"--no-compress",', block,
                          "Die innere Stufe in Zeile %d komprimiert." % (i + 1))
            self.assertIn('"--raw",', block,
                          "Ohne --raw entsteht ein dreifach verschachteltes "
                          "Abbild (Zeile %d)." % (i + 1))


class PruefstufeTests(unittest.TestCase):
    """Die mkpfs-Pruefung nach dem Packen ist waehlbar.

    Bis v1.8.55 stand in jedem Packaufruf fest "--no-verify-structure":
    mkpfs prueft von sich aus, das Programm schaltete es ab, und niemand
    konnte das sehen oder aendern. Die offizielle Anleitung in
    "PS5 SDK usw/README.md" und das Referenzprogramm lassen die Pruefung
    laufen.
    """

    QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

    def _gui(self, stufe):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.mkpfs_verify = stufe
        return gui

    def test_die_drei_stufen_liefern_die_richtigen_schalter(self):
        self.assertEqual(self._gui("aus")._mkpfs_pruef_argumente(),
                         ["--no-verify-structure"])
        # Schnell = Vorgabe von mkpfs, also gar kein Schalter.
        self.assertEqual(self._gui("schnell")._mkpfs_pruef_argumente(), [])
        self.assertEqual(self._gui("voll")._mkpfs_pruef_argumente(), ["--verify"])

    def test_unbekannte_stufe_faellt_auf_schnell_zurueck(self):
        self.assertEqual(self._gui("kaese")._mkpfs_pruef_argumente(), [])
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        # Attribut fehlt ganz - darf nicht scheitern.
        self.assertEqual(gui._mkpfs_pruef_argumente(), [])

    def test_kein_aufruf_verdrahtet_die_pruefung_mehr_fest(self):
        text = self.QUELLE.read_text(encoding="utf-8")
        self.assertNotIn(chr(34) + "--no-verify-structure" + chr(34) + ",", text,
                         "Eine Stelle schaltet die Pruefung wieder fest ab.")

    def test_jede_pack_stelle_fragt_die_stufe(self):
        text = self.QUELLE.read_text(encoding="utf-8")
        zeilen = text.splitlines()
        stellen = [i for i, z in enumerate(zeilen)
                   if chr(39) + "pack" + chr(39) not in z
                   and (chr(34) + "pack" + chr(34) + ", " + chr(34) + "file" + chr(34) + "," in z
                        or chr(34) + "pack" + chr(34) + ", " + chr(34) + "folder" + chr(34) + "," in z)]
        self.assertGreaterEqual(len(stellen), 6)
        for i in stellen:
            block = chr(10).join(zeilen[i:i + 12])
            self.assertIn("_mkpfs_pruef_argumente()", block,
                          "Der Packaufruf in Zeile %d fragt die Stufe nicht." % (i + 1))

    def test_stufen_sind_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS, VERIFY_STUFEN

        self.assertEqual([k for _, k in VERIFY_STUFEN], ["aus", "schnell", "voll"])
        for schluessel, _kennung in VERIFY_STUFEN:
            self.assertIn(schluessel, STRINGS)
            for sprache in ("de", "en"):
                self.assertTrue(STRINGS[schluessel].get(sprache), schluessel)
        for schluessel in ("verify.hint", "main.verify_label"):
            self.assertIn(schluessel, STRINGS)

    def test_vorgabe_ist_schnell(self):
        text = self.QUELLE.read_text(encoding="utf-8")
        self.assertIn(chr(34) + "mkpfs_verify" + chr(34) + ", " + chr(34) + "schnell" + chr(34), text,
                      "Die Vorgabe ist nicht mehr die schnelle Pruefung.")


class TempoHinweisTests(unittest.TestCase):
    """Der Hinweis zur Entpackgeschwindigkeit haengt am Zielformat.

    Grundlage ist die ShadowMountPlus-Anleitung 1.7alpha7: Die Entpackung
    liegt bei rund 150-250 MB/s, etwa ein Drittel eines USB-Laufwerks.
    Spiele, die viel nachladen, koennen dadurch ruckeln - das steht dem
    Nutzer vor der Wahl zu, nicht hinterher.
    """

    QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

    def _gui(self, format_label):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._MODE_SOURCE_TYPES = {"pack_folder": ("folder",)}
        gui.target_format = _Var(format_label)
        return gui

    def test_pfs_ziele_bekommen_den_hinweis(self):
        for schluessel in ("ffpfsc", "ffpfs"):
            gui = self._gui(APP.PS5ConverterGUI._FORMAT_LABELS[schluessel])
            hinweis = gui._zielformat_hinweis("pack_folder")
            self.assertIn("150", hinweis, schluessel)
            self.assertIn("250", hinweis, schluessel)

    def test_andere_ziele_bekommen_ihn_nicht(self):
        for schluessel in ("exfat", "ffpkg", "folder"):
            label = APP.PS5ConverterGUI._FORMAT_LABELS.get(schluessel)
            if not label:
                continue
            gui = self._gui(label)
            hinweis = gui._zielformat_hinweis("pack_folder")
            self.assertNotIn("150", hinweis, schluessel)

    def test_quellenzeile_bleibt_erhalten(self):
        # Der Hinweis kommt dazu, er ersetzt die Angabe der Quellarten nicht.
        gui = self._gui(APP.PS5ConverterGUI._FORMAT_LABELS["ffpfsc"])
        hinweis = gui._zielformat_hinweis("pack_folder")
        self.assertIn(chr(10), hinweis, "Zwei Zeilen erwartet")
        self.assertTrue(hinweis.splitlines()[0].strip())

    def test_hinweis_haengt_an_der_formatwahl(self):
        # Ohne Bindung an die Liste aendert sich der Text erst beim
        # naechsten Aufgabenwechsel - also praktisch nie.
        quelle = self.QUELLE.read_text(encoding="utf-8")
        self.assertIn("self.format_combo.bind(", quelle)
        self.assertIn("_format_hinweis_setzen()", quelle)

    def test_hinweis_ist_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS

        self.assertIn("main.pfs_speed_hint", STRINGS)
        for sprache in ("de", "en"):
            self.assertTrue(STRINGS["main.pfs_speed_hint"].get(sprache))


if __name__ == "__main__":
    unittest.main(verbosity=2)
