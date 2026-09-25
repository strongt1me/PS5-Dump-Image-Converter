# -*- coding: utf-8 -*-
"""Ein exFAT-Backup mit Asset-Pack — ohne zweiten Lauf.

Vom Nutzer gemeldet (20.09.2026): *"Wenn ich ein exFAT Backup habe und dort
ein AMPR EMU Asset Pack integrieren möchte … gibt es noch keine
möglichkeit im Programm, diese zu integrieren."*

Er hatte recht: ``exfat -> exfat`` lief in „Quelle und Zielformat sind
identisch", und eine Wegfunktion gab es gar nicht. Der ``.ffpkg``-Fall ging
dagegen schon (Aufgabe 4/6 baut eine ``.ffpkg`` bewusst neu auf).

**Warum der Weg entpackt statt hineinzuschreiben** — gemessen am echten
Abbild, nicht angenommen: Der mitgelieferte exFAT-Schreiber rechnet das
Layout vorab aus und legt alles zusammenhängend ab
(``cluster_count = bitmap_clusters + content_clusters``). Eine Probe mit
5,5 MB Inhalt ergab **95 Cluster gesamt, 95 belegt, 0 frei**. In ein
fertiges Abbild passt also kein Byte mehr; ein Asset-Pack hineinzulegen
hieße, es zu vergrößern — und damit Bootbereich, FAT und Bitmap neu zu
schreiben. Dazu kommt: Das Packwerkzeug des AMPR-Entwicklers arbeitet auf
einem echten Ordnerbaum (``--root <app0>``), nicht auf einem Abbild.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJEKT = Path(__file__).resolve().parent
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class SelbstzielRegelTests(unittest.TestCase):
    """Eine Regel statt einer Liste von Sonderfällen.

    Gewünscht vom Nutzer (20.09.2026): *"Es soll bei Aufgabe 1-6 für alle
    Formate möglich sein, das selbe Format aber mit AMPR EMU Asset Pack zu
    erstellen"* und *"für PlayGo gilt natürlich das selbe"*.

    Also: Quelle und Ziel dürfen dasselbe Format haben, sobald beim Bauen
    **etwas hineinkommt** — Asset-Pack, PlayGo oder BACKPORT. Ohne Einbau
    bleibt es gesperrt: Dann wäre der Lauf eine Kopie derselben Datei,
    Stunden Rechenzeit für nichts.

    Zwei Formate sind davon ausgenommen und immer erlaubt, weil sie ohnehin
    neu aufgebaut und dabei geprüft werden: ``.ffpkg`` (Aufgabe 4 nennt das
    seit jeher „neu validieren") und ``.exFAT`` (seit v1.9.35, auf Wunsch
    ausdrücklich „so wie ffpkg zu ffpkg bei Aufgabe 4").
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    #: Die Aufgaben mit Zielformat - Aufgabe 1 bis 6.
    AUFGABEN = ("pack_folder", "unpack_to_exfat", "pack_file",
                "ffpkg_to_ffpfsc", "batch_convert", "universal_convert")

    def _probe(self, mit_einbau: bool):
        G = self.haupt.PS5ConverterGUI

        class _Probe:
            pass

        p = _Probe()
        p._t = lambda s, **w: s
        for name in ("_SAME_FORMAT_ALLOWED", "_MODE_TARGET_OPTIONS",
                     "_UNSUPPORTED_TARGET_HINTS"):
            setattr(p, name, getattr(G, name))
        p._selbstziel_erlaubt = lambda: mit_einbau
        p._detect_source_format = lambda _pfad: ""
        p._conversion_block_reason = G._conversion_block_reason.__get__(p)
        return p

    def test_mit_einbau_geht_jedes_format_in_jeder_aufgabe(self):
        frei = self._probe(mit_einbau=True)
        G = self.haupt.PS5ConverterGUI
        for mode in self.AUFGABEN:
            for fmt in G._MODE_TARGET_OPTIONS[mode]:
                if fmt == "folder":
                    continue      # ein Ordner ist kein Abbildformat
                with self.subTest(aufgabe=mode, format=fmt):
                    self.assertEqual(
                        frei._conversion_block_reason(fmt, fmt, mode=mode), "",
                        "%s sperrt %s -> %s trotz Einbau" % (mode, fmt, fmt))

    def test_ohne_einbau_bleibt_es_gesperrt(self):
        """Sonst wäre der Lauf eine Kopie derselben Datei."""
        ohne = self._probe(mit_einbau=False)
        G = self.haupt.PS5ConverterGUI
        for mode in self.AUFGABEN:
            for fmt in G._MODE_TARGET_OPTIONS[mode]:
                if fmt == "folder" or fmt in G._SAME_FORMAT_ALLOWED.get(mode, ()):
                    continue
                with self.subTest(aufgabe=mode, format=fmt):
                    self.assertEqual(
                        ohne._conversion_block_reason(fmt, fmt, mode=mode),
                        "conversion.same_format",
                        "%s laesst %s -> %s ohne Einbau zu" % (mode, fmt, fmt))

    def test_ffpkg_und_exfat_gehen_immer(self):
        """Sie werden ohnehin neu aufgebaut und dabei geprüft."""
        ohne = self._probe(mit_einbau=False)
        for mode, fmt in (("ffpkg_to_ffpfsc", "ffpkg"),
                          ("universal_convert", "ffpkg"),
                          ("universal_convert", "exfat"),
                          ("pack_file", "exfat")):
            with self.subTest(aufgabe=mode, format=fmt):
                self.assertEqual(
                    ohne._conversion_block_reason(fmt, fmt, mode=mode), "")

    def test_ausserhalb_der_aufgaben_bleibt_es_gesperrt(self):
        """Aufgabe 7 und 8 haben kein Zielformat - dort gibt es nichts zu bauen."""
        frei = self._probe(mit_einbau=True)
        for mode in ("ampr_manager", "dump_validator", "inspect", ""):
            with self.subTest(aufgabe=mode):
                self.assertEqual(
                    frei._conversion_block_reason("exfat", "exfat", mode=mode),
                    "conversion.same_format")

    def test_playgo_und_backport_zaehlen_mit(self):
        """Der ausdrückliche Wunsch: PlayGo soll genauso zählen.

        Gemessen an der echten Methode, mit gestellten Kästchen — nicht an
        einer Nachbildung.
        """
        import threading

        G = self.haupt.PS5ConverterGUI

        class _Probe:
            pass

        for pack, ampr, playgo, backport, erwartet in (
            (False, False, False, False, False),
            (True, True, False, False, True),      # Asset-Pack
            (False, True, True, False, True),      # PlayGo mit AMPR EMU
            # PlayGo ohne AMPR baut nichts ein - der Stub kommt nur im
            # AMPR-Schritt dazu (Durchsicht 23.09.2026, H7-2).
            (False, False, True, False, False),
            (False, False, False, True, True),     # BACKPORT allein
        ):
            p = _Probe()
            p._assetpack_gewaehlt = lambda w=pack: w
            werte = {"ampr_integrate_var": ampr,
                     "ampr_playgo_var": playgo,
                     "backport_integrate_var": backport}
            p._tk_wert = lambda name, vorgabe=None, _w=werte: _w.get(name, vorgabe)
            p._selbstziel_erlaubt = G._selbstziel_erlaubt.__get__(p)
            with self.subTest(pack=pack, ampr=ampr, playgo=playgo, backport=backport):
                self.assertIs(threading.current_thread(),
                              threading.main_thread())
                self.assertEqual(p._selbstziel_erlaubt(), erwartet)

    def test_im_faden_entscheidet_der_startstand(self):
        """Tk-Variablen dürfen im Aufgabenfaden nicht gelesen werden."""
        import threading

        G = self.haupt.PS5ConverterGUI

        class _Probe:
            pass

        p = _Probe()

        def _verboten(*_a, **_k):
            raise AssertionError("Tk-Auswahl im Aufgabenfaden gelesen")

        p._assetpack_gewaehlt = _verboten
        p._tk_wert = _verboten
        p._umhuellt_neu_packen = True
        p._selbstziel_erlaubt = G._selbstziel_erlaubt.__get__(p)

        ergebnis: list = []
        faden = threading.Thread(
            target=lambda: ergebnis.append(p._selbstziel_erlaubt()))
        faden.start()
        faden.join(10)
        self.assertEqual(ergebnis, [True])


class AuswahllisteTests(unittest.TestCase):
    """Was die Sperre durchlässt, muss die Auswahl auch anbieten.

    Vom Nutzer gemeldet (20.09.2026, nach v1.9.34): *"exFAT zu exFAT (inkl.
    AMPR EMU Asset Pack) wird nicht angezeigt bzw. kann nicht ausgewählt
    werden."*

    Er hatte recht. Es gibt **zwei** Tore, und gemessen war nur das zweite:

    1. ``_get_target_options`` baut die Liste im Auswahlfeld. Für Aufgabe 6
       warf sie das Selbst-Ziel **immer** heraus.
    2. ``_conversion_block_reason`` prüft beim Start. Dort war es längst
       freigegeben.

    Freigabe ohne Listeneintrag heißt: Der Anwender kommt gar nicht erst
    hin. Deshalb prüft diese Klasse das **erste** Tor — und ganz unten, dass
    beide dasselbe sagen.
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def _liste(self, mode: str, pfad: str, mit_einbau: bool) -> tuple:
        G = self.haupt.PS5ConverterGUI

        class _Probe:
            pass

        p = _Probe()
        for name in ("_MODE_TARGET_OPTIONS", "_SAME_FORMAT_ALLOWED"):
            setattr(p, name, getattr(G, name))
        p._selbstziel_erlaubt = lambda: mit_einbau
        for name in ("_detect_source_type", "_detect_source_format",
                     "_get_target_options"):
            setattr(p, name, getattr(G, name).__get__(p))
        return p._get_target_options(mode, pfad)

    def _quelle(self, basis: str, endung: str) -> str:
        pfad = Path(basis) / ("spiel." + endung)
        pfad.write_bytes(b"x" * 64)
        return str(pfad)

    def test_mit_einbau_steht_das_selbstziel_in_der_liste(self):
        G = self.haupt.PS5ConverterGUI
        with tempfile.TemporaryDirectory(prefix="auswahl_") as basis:
            for mode in ("unpack_to_exfat", "pack_file", "ffpkg_to_ffpfsc",
                         "universal_convert"):
                for endung in ("ffpfsc", "ffpfs", "exfat", "ffpkg"):
                    pfad = self._quelle(basis, endung)
                    typ = G._detect_source_type(None, pfad)
                    if typ not in G._MODE_SOURCE_TYPES.get(mode, ()):
                        continue
                    if endung not in G._MODE_TARGET_OPTIONS[mode]:
                        continue
                    with self.subTest(aufgabe=mode, format=endung):
                        self.assertIn(endung, self._liste(mode, pfad, True))

    def test_ohne_einbau_verschwindet_es(self):
        G = self.haupt.PS5ConverterGUI
        with tempfile.TemporaryDirectory(prefix="auswahl_") as basis:
            for mode in ("unpack_to_exfat", "pack_file", "universal_convert"):
                for endung in ("ffpfsc", "ffpfs", "exfat", "ffpkg"):
                    pfad = self._quelle(basis, endung)
                    typ = G._detect_source_type(None, pfad)
                    if typ not in G._MODE_SOURCE_TYPES.get(mode, ()):
                        continue
                    if endung not in G._MODE_TARGET_OPTIONS[mode]:
                        continue
                    if endung in G._SAME_FORMAT_ALLOWED.get(mode, ()):
                        continue    # .ffpkg / .exFAT stehen immer drin
                    with self.subTest(aufgabe=mode, format=endung):
                        self.assertNotIn(endung, self._liste(mode, pfad, False))

    def test_das_selbstziel_ist_beschriftet(self):
        """Ohne Zusatz sähe „.exFAT → .exFAT" wie ein Fehler aus."""
        G = self.haupt.PS5ConverterGUI

        class _Probe:
            pass

        p = _Probe()
        p._SAME_FORMAT_ALLOWED = G._SAME_FORMAT_ALLOWED
        p._SELBSTZIEL_ZUSATZ = G._SELBSTZIEL_ZUSATZ
        p._MODE_SOURCE_TYPES = G._MODE_SOURCE_TYPES
        p._t = lambda s, **w: s
        p._detect_source_format = G._detect_source_format.__get__(p)
        p._detect_source_type = G._detect_source_type.__get__(p)
        p._zielformat_label = G._zielformat_label.__get__(p)

        # Aufgabe 3 und 4 haben genau ein Quellformat - dort steht der
        # Zusatz auch ohne gewaehlte Quelle.
        self.assertEqual(p._zielformat_label("exfat", "pack_file"),
                         "format.exfat format.exfat_neubau_suffix")
        self.assertEqual(p._zielformat_label("ffpkg", "ffpkg_to_ffpfsc"),
                         "format.ffpkg format.ffpkg_revalidate_suffix")
        # Kein Selbst-Ziel: kein Zusatz.
        self.assertEqual(p._zielformat_label("exfat", "pack_folder"),
                         "format.exfat")

    def test_der_zusatz_haengt_an_der_quelle(self):
        """In Aufgabe 6 ist .ffpkg fuer eine .ffpfsc-Quelle ganz normal.

        Beim ersten Anlauf haing der Zusatz nur am Modus - dann haette auch
        eine .ffpfsc-Quelle das Ziel .ffpkg als "(neu validieren)" gezeigt,
        obwohl es eine gewoehnliche Umwandlung ist.
        """
        G = self.haupt.PS5ConverterGUI

        class _Probe:
            pass

        p = _Probe()
        p._SAME_FORMAT_ALLOWED = G._SAME_FORMAT_ALLOWED
        p._SELBSTZIEL_ZUSATZ = G._SELBSTZIEL_ZUSATZ
        p._MODE_SOURCE_TYPES = G._MODE_SOURCE_TYPES
        p._t = lambda s, **w: s
        p._detect_source_format = G._detect_source_format.__get__(p)
        p._detect_source_type = G._detect_source_type.__get__(p)
        p._zielformat_label = G._zielformat_label.__get__(p)

        with tempfile.TemporaryDirectory(prefix="etikett_") as basis:
            ffpfsc = self._quelle(basis, "ffpfsc")
            exfat = self._quelle(basis, "exfat")
            self.assertEqual(
                p._zielformat_label("ffpkg", "universal_convert", ffpfsc),
                "format.ffpkg",
                "Eine .ffpfsc-Quelle macht .ffpkg nicht zum Selbst-Ziel")
            self.assertEqual(
                p._zielformat_label("exfat", "universal_convert", exfat),
                "format.exfat format.exfat_neubau_suffix")

    def test_beide_tore_sind_sich_einig(self):
        """Der eigentliche Befund: Liste und Sperre dürfen nicht auseinanderlaufen.

        Für jede Kombination muss gelten: Steht das Selbst-Ziel in der
        Liste, lässt die Sperre es auch durch — und umgekehrt. Die
        Sammelkonvertierung bleibt außen vor: Sie hat keinen einzelnen
        Quelltyp, ihre Liste wird deshalb nie beschnitten; geprüft wird dort
        je Datei beim Start.
        """
        G = self.haupt.PS5ConverterGUI

        class _Probe:
            pass

        with tempfile.TemporaryDirectory(prefix="auswahl_") as basis:
            for mode in ("unpack_to_exfat", "pack_file", "ffpkg_to_ffpfsc",
                         "universal_convert"):
                for endung in ("ffpfsc", "ffpfs", "exfat", "ffpkg"):
                    pfad = self._quelle(basis, endung)
                    typ = G._detect_source_type(None, pfad)
                    if typ not in G._MODE_SOURCE_TYPES.get(mode, ()):
                        continue
                    if endung not in G._MODE_TARGET_OPTIONS[mode]:
                        continue
                    for mit_einbau in (True, False):
                        in_liste = endung in self._liste(mode, pfad, mit_einbau)

                        p = _Probe()
                        for name in ("_SAME_FORMAT_ALLOWED",
                                     "_MODE_TARGET_OPTIONS",
                                     "_UNSUPPORTED_TARGET_HINTS"):
                            setattr(p, name, getattr(G, name))
                        p._t = lambda s, **w: s
                        p._selbstziel_erlaubt = lambda w=mit_einbau: w
                        p._detect_source_type = G._detect_source_type.__get__(p)
                        p._detect_source_format = (
                            G._detect_source_format.__get__(p))
                        p._conversion_block_reason = (
                            G._conversion_block_reason.__get__(p))
                        frei = not p._conversion_block_reason(
                            typ, endung, mode, pfad)

                        with self.subTest(aufgabe=mode, format=endung,
                                          einbau=mit_einbau):
                            self.assertEqual(
                                in_liste, frei,
                                "Liste sagt %s, Sperre sagt %s"
                                % (in_liste, frei))


class WegWirdGegangenTests(unittest.TestCase):
    """Der Weg muss verdrahtet sein - nicht nur freigegeben."""

    @classmethod
    def setUpClass(cls):
        cls.quelle = HAUPTDATEI.read_text(encoding="utf-8")
        cls.baum = ast.parse(cls.quelle)

    def test_die_weiche_kennt_exfat_zu_exfat(self):
        methode = next(k for k in ast.walk(self.baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_execute_conversion_by_type")
        rufe = {n.func.attr for n in ast.walk(methode)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn("_mode_exfat_umpacken", rufe,
                      "Die Weiche in _execute_conversion_by_type ruft den "
                      "neuen Weg nicht - dann faellt exfat->exfat durch.")

    def test_der_weg_existiert_und_raeumt_auf(self):
        methode = next((k for k in ast.walk(self.baum)
                        if isinstance(k, ast.FunctionDef)
                        and k.name == "_mode_exfat_umpacken"), None)
        self.assertIsNotNone(methode, "_mode_exfat_umpacken fehlt.")
        quelle = ast.unparse(methode)
        # Der Ordner darf nicht liegenbleiben - bei einem grossen Spiel sind
        # das zig Gigabyte im Arbeitsordner.
        self.assertTrue(
            [k for k in ast.walk(methode)
             if isinstance(k, ast.Try) and k.finalbody],
            "Ohne finally bliebe der Temp-Ordner nach einem Fehlschlag stehen.")
        self.assertIn("_rmtree_force", quelle)
        for teil in ("_extract_exfat_to_folder_mkpfs", "_integration_anwenden",
                     "_create_exfat_from_folder"):
            self.assertIn(teil, quelle, teil)

    def test_eingebaut_wird_ohne_zweite_arbeitskopie(self):
        """Der Ordner liegt schon im Temp - und gilt damit als Arbeitskopie.

        Mit ``ist_quellordner=True`` käme die Rückfrage nach einer
        Arbeitskopie **und** eine zweite Kopie des ganzen Spiels.
        """
        methode = next(k for k in ast.walk(self.baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_mode_exfat_umpacken")
        for knoten in ast.walk(methode):
            if (isinstance(knoten, ast.Call)
                    and isinstance(knoten.func, ast.Attribute)
                    and knoten.func.attr == "_integration_anwenden"):
                self.assertFalse(
                    [s for s in knoten.keywords if s.arg == "ist_quellordner"],
                    "ist_quellordner wuerde eine zweite Arbeitskopie anlegen.")

    def test_der_weg_meldet_sich(self):
        """Dauerauftrag: kein langer Vorgang ohne Anzeige."""
        methode = next(k for k in ast.walk(self.baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_mode_exfat_umpacken")
        quelle = ast.unparse(methode)
        for melder in ("_append_to_log", "progress_engine"):
            self.assertIn(melder, quelle, melder)

    def test_ein_selbstziel_wird_nicht_gefragt(self):
        """„Einhüllen oder neu packen?" hätte hier nur eine sinnvolle Antwort.

        Ein Abbild in ein Abbild desselben Formats zu hüllen wäre Unsinn
        (Container im Container). Deshalb muss die Abkürzung **vor** der
        Ja/Nein-Rückfrage stehen — sonst steht der Anwender vor einer Frage
        ohne echte Wahl.
        """
        methode = next(k for k in ast.walk(self.baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_umhuellenden_weg_klaeren")
        abkuerzung = [k.lineno for k in ast.walk(methode)
                      if isinstance(k, ast.Call)
                      and isinstance(k.func, ast.Attribute)
                      and k.func.attr == "_neu_packen_waehlen"]
        frage = [k.lineno for k in ast.walk(methode)
                 if isinstance(k, ast.Call)
                 and isinstance(k.func, ast.Attribute)
                 and k.func.attr == "_ask_yesno_threadsafe"]
        self.assertTrue(abkuerzung)
        self.assertTrue(frage)
        self.assertLess(min(abkuerzung), min(frage),
                        "Die Rueckfrage kommt vor der Abkuerzung.")

    def test_exfat_steht_in_den_einhuellenden_wegen(self):
        """Sonst erreicht der Lauf die Abkürzung gar nicht erst."""
        haupt = _lade_hauptprogramm()
        self.assertIn(("exfat", "exfat"),
                      haupt.PS5ConverterGUI._EINHUELLENDE_WEGE)

    def test_die_texte_gibt_es_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("log.exfat_umpacken_start",
                           "log.exfat_umpacken_leser_scheitert",
                           "log.exfat_umpacken_fertig",
                           "progress.task.exfat_umpacken",
                           "status.prefix_exfat_umpacken"):
            eintrag = STRINGS[schluessel]
            self.assertIn("de", eintrag, schluessel)
            self.assertIn("en", eintrag, schluessel)


class KeinFreierPlatzTests(unittest.TestCase):
    """Warum der Umweg über den Ordner sein muss - am Abbild gemessen."""

    def test_ein_gebautes_abbild_hat_keinen_freien_cluster(self):
        sys.path.insert(0, str(PROJEKT / "MkPFS-1.0.0"))
        from mkpfs.exfat import ExfatReader
        from mkpfs.exfat_writer import write_exfat_image

        with tempfile.TemporaryDirectory(prefix="exfat_frei_") as basis:
            quelle = Path(basis) / "spiel"
            (quelle / "sce_sys").mkdir(parents=True)
            (quelle / "eboot.bin").write_bytes(b"\x7fELF" + b"x" * (1024 * 1024))
            (quelle / "sce_sys" / "param.json").write_text('{"titleId":"PPSA00001"}')
            abbild = Path(basis) / "spiel.exfat"
            write_exfat_image(quelle, abbild)

            with abbild.open("rb") as fh:
                leser = ExfatReader(fh)
                geo = leser.geometry
                fh.seek(leser._cluster_byte_offset(2))
                roh = fh.read((geo.cluster_count + 7) // 8)
                belegt = sum(bin(b).count("1") for b in roh)

        self.assertEqual(
            belegt, geo.cluster_count,
            "Das Abbild hat freie Cluster - dann waere ein Hineinschreiben "
            "zu pruefen, statt neu zu bauen.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
