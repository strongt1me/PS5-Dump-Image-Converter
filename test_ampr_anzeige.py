#!/usr/bin/env python3
"""Sichert die AMPR-EMU-Anzeige in der Spiel-Infobox ab.

Die Anzeige beantwortet: Steckt in dieser Quelle schon ein AMPR EMU - **und
wirkt er?** Seit dem 27.09.2026 nach der Regel von ShadowMount+ 1.7 (final
und 1.7beta2, am Quelltext ``sm_fakelib.c`` gemessen): Im Spiel gilt der erste
vorhandene Ordner, erst ``fakelib2``, dann ``fakelib``; ``fakelib2`` wird
exklusiv eingehaengt. 1.7alpha8 bis alpha13fix1 lasen nur ``fakelib`` - diese
Regel stand bis dahin hier fest.

Die Infobox nimmt dieselbe Auswertung wie die Bibliothek
(``_bibliothek_einbauten`` -> ``bibliothek.einbauten_bewerten``): Ordner
direkt, Abbilder ueber ihre innere Ebene (``_container_dateien``). Die Engine
(``read_game_metadata``) fragt sie nicht mehr - die prueft fest nur
``fakelib/libSceAmpr.sprx`` und sucht bei ``.ffpkg`` den Dateinamen irgendwo
in den ersten 8 MB.

Weiter gilt der Kern von frueher: **Wenn nichts gelesen werden konnte, darf
nicht "nicht eingebaut" dastehen.**
"""

from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import PS5ImageConverter_Pro_FINAL_revised as hauptprogramm  # noqa: E402
from ps5_validator.utils import bibliothek as bib            # noqa: E402

GUI = hauptprogramm.PS5ConverterGUI
MKPFS_ORDNER = ROOT / "MkPFS-1.0.0"


def _gui():
    gui = GUI.__new__(GUI)
    gui.mkpfs_dir = str(MKPFS_ORDNER)
    # _t gibt den Schluessel zurueck: so ist die Entscheidung pruefbar,
    # ohne an einer Uebersetzung zu haengen.
    gui._t = lambda key, **kw: key
    return gui


def _dump(basis: Path, dateien: dict[str, bytes]) -> Path:
    ordner = basis / "PPSA00001"
    (ordner / "sce_sys").mkdir(parents=True)
    (ordner / "sce_sys" / "param.json").write_bytes(b'{"titleId":"PPSA00001"}')
    for rel, inhalt in dateien.items():
        ziel = ordner / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(inhalt)
    return ordner


#: Inhalt des Spielordners -> erwartete Zeile der Infobox (ShadowMount+ 1.7).
FAELLE = (
    ({"fakelib/libSceAmpr.sprx": b"a"}, "info_popup.ampr_eingebaut"),
    ({"fakelib/andere.sprx": b"x"}, "info_popup.ampr_nicht_eingebaut"),
    ({"fakelib2/libSceAmpr.sprx": b"a"}, "info_popup.ampr_eingebaut_fakelib2"),
    ({"fakelib/libSceAmpr.sprx": b"a", "fakelib2/andere.sprx": b"x"},
     "info_popup.ampr_verdeckt"),
    ({"fakelib/libSceAmpr.sprx.orig": b"o"}, "info_popup.ampr_nicht_eingebaut"),
    ({}, "info_popup.ampr_nicht_eingebaut"),
)


class AnzeigeImFensterTests(unittest.TestCase):
    """Die Zeile muss es im Fenster ueberhaupt geben."""

    def setUp(self) -> None:
        self.quelltext = Path(hauptprogramm.__file__).read_text(
            encoding="utf-8", errors="replace"
        )

    def test_feld_ist_angelegt(self) -> None:
        """Die Feldliste steht seit dem 03.09.2026 in bedienzustand.

        Vorher zaehlte die Hauptdatei sie selbst auf. Dass beide Listen
        auseinanderlaufen, war der Fehler, den die Auslagerung behebt -
        deshalb wird jetzt dort nachgesehen.
        """
        from ps5_validator.ui.bedienzustand import METADATENFELDER

        self.assertIn("ampr_emu", METADATENFELDER,
                      "ampr_emu fehlt in bedienzustand.METADATENFELDER")
        self.assertIn("for key in bedienzustand.METADATENFELDER", self.quelltext,
                      "Die Anzeige zieht ihre Felder nicht aus dem Modul")

    def test_zeile_steht_in_der_infobox(self) -> None:
        self.assertIn('("ampr_emu", self._t("info_popup.meta.ampr_emu"))', self.quelltext,
                      "Die Zeile wird nicht in meta_keys aufgebaut")

    def test_uebersetzungen_vollstaendig(self) -> None:
        from ps5_validator.utils import i18n
        for schluessel in ("info_popup.meta.ampr_emu", "info_popup.ampr_eingebaut",
                           "info_popup.ampr_nicht_eingebaut", "info_popup.ampr_unlesbar",
                           "info_popup.ampr_eingebaut_fakelib2", "info_popup.ampr_verdeckt"):
            with self.subTest(schluessel=schluessel):
                eintrag = i18n.STRINGS.get(schluessel)
                self.assertIsNotNone(eintrag, f"{schluessel} fehlt")
                for sprache in ("de", "en"):
                    self.assertTrue(str(eintrag.get(sprache, "")).strip(),
                                    f"{schluessel} hat keine {sprache}-Fassung")

    def test_wird_beim_aktualisieren_gesetzt(self) -> None:
        self.assertIn('self._meta_labels["ampr_emu"].set(_ampr_text)', self.quelltext,
                      "Die Zeile wird nie befuellt")


class OrdnerTests(unittest.TestCase):
    """Dump-Ordner - nach der Regel von ShadowMount+ 1.7."""

    def test_die_faelle(self) -> None:
        gui = _gui()
        for inhalt, erwartet in FAELLE:
            with self.subTest(inhalt=sorted(inhalt)), tempfile.TemporaryDirectory() as tmp:
                ordner = _dump(Path(tmp), inhalt)
                self.assertEqual(erwartet, gui._ampr_emu_stand(str(ordner)))

    def test_leerer_pfad(self) -> None:
        self.assertEqual("–", _gui()._ampr_emu_stand(""))

    def test_pfad_gibt_es_nicht(self) -> None:
        self.assertEqual("–", _gui()._ampr_emu_stand(str(ROOT / "gibt-es-nicht.ffpfsc")))


class AbbildTests(unittest.TestCase):
    """Abbilder - ueber die innere Ebene, nie ueber die Engine."""

    def setUp(self) -> None:
        self._ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self._ordner.cleanup)
        self.basis = Path(self._ordner.name)
        self.gui = _gui()
        speicher = bib.Bildspeicher(str(self.basis / "cover"))
        self.gui._bibliothek_bildspeicher = lambda: speicher

    def _datei(self, name: str) -> str:
        pfad = self.basis / name
        pfad.write_bytes(b"\0" * 64)
        return str(pfad)

    def test_unlesbar_ist_kein_nein(self) -> None:
        """Konnte niemand hineinsehen, heisst es "nicht ermittelbar"."""
        for antwort in (None, []):
            with self.subTest(antwort=antwort), \
                    mock.patch.object(self.gui, "_container_dateien", return_value=antwort):
                self.assertEqual("info_popup.ampr_unlesbar",
                                 self.gui._ampr_emu_stand(self._datei("x%s.ffpfsc" % id(antwort))))

    def test_ffpkg_fragt_die_engine_nicht(self) -> None:
        """Die Engine meldete bei .ffpkg einen blossen Namenstreffer als 'eingebaut'."""
        engine = types.ModuleType("mkpfs.game_metadata")
        engine.read_game_metadata = mock.Mock(side_effect=AssertionError("Engine gefragt"))
        with mock.patch.dict(sys.modules, {"mkpfs.game_metadata": engine}):
            self.assertEqual("info_popup.ampr_unlesbar",
                             self.gui._ampr_emu_stand(self._datei("spiel.ffpkg")))
        engine.read_game_metadata.assert_not_called()

    def test_die_faelle_ueber_die_innere_ebene(self) -> None:
        for nummer, (inhalt, erwartet) in enumerate(FAELLE):
            with self.subTest(inhalt=sorted(inhalt)), \
                    mock.patch.object(self.gui, "_container_dateien",
                                      return_value=["sce_sys/param.json", *inhalt]):
                self.assertEqual(erwartet, self.gui._ampr_emu_stand(
                    self._datei("fall%d.ffpfsc" % nummer)))

    def test_ordner_und_abbild_bekommen_dieselbe_antwort(self) -> None:
        """Derselbe Dump, einmal als Ordner, einmal als echtes exFAT-Abbild.

        Bis zum 06.09.2026 sagten beide Wege fuer dasselbe Spiel Verschiedenes
        (Teilstring ``fakelib`` traf auch ``fakelib2``); am 27.09.2026 lief die
        Bibliothek nach 1.7, die Infobox noch nach alpha8.
        """
        sys.path.insert(0, str(MKPFS_ORDNER))
        self.addCleanup(lambda: sys.path.remove(str(MKPFS_ORDNER))
                        if str(MKPFS_ORDNER) in sys.path else None)
        from mkpfs import exfat_writer                      # noqa: PLC0415
        for nummer, (inhalt, erwartet) in enumerate(FAELLE[:4]):
            with self.subTest(inhalt=sorted(inhalt)):
                ordner = _dump(self.basis / ("f%d" % nummer), {
                    rel: wert * 64 for rel, wert in inhalt.items()})
                abbild = self.basis / ("f%d.exfat" % nummer)
                abbild.write_bytes(b"".join(exfat_writer.iter_exfat_image(ordner)))
                aus_ordner = self.gui._ampr_emu_stand(str(ordner))
                self.assertEqual(erwartet, aus_ordner)
                self.assertEqual(aus_ordner, self.gui._ampr_emu_stand(str(abbild)))


class GemeinsameRegelTests(unittest.TestCase):
    """Infobox und Bibliothek entscheiden an derselben Stelle."""

    @classmethod
    def setUpClass(cls) -> None:
        import ast
        baum = ast.parse(Path(hauptprogramm.__file__).read_text(encoding="utf-8"))

        def _fn(name: str):
            return next(k for k in ast.walk(baum)
                        if isinstance(k, ast.FunctionDef) and k.name == name)

        cls.stand_knoten = _fn("_ampr_emu_stand")
        cls.stand = ast.unparse(cls.stand_knoten)
        cls.lesen = ast.unparse(_fn("_container_dateien"))

    def test_die_infobox_nimmt_die_auswertung_der_bibliothek(self) -> None:
        """Geprueft an Aufrufen und Importen - die Beschreibung darf die Engine nennen."""
        import ast
        self.assertIn("self._bibliothek_einbauten(", self.stand)
        aufrufe = {getattr(k.func, "attr", getattr(k.func, "id", ""))
                   for k in ast.walk(self.stand_knoten) if isinstance(k, ast.Call)}
        importe = {k.module for k in ast.walk(self.stand_knoten)
                   if isinstance(k, ast.ImportFrom)}
        self.assertNotIn("read_game_metadata", aufrufe,
                         "Die Infobox fragt wieder die Engine - die kennt nur fakelib.")
        self.assertNotIn("mkpfs.game_metadata", importe)

    def test_der_container_weg_setzt_den_engine_pfad_selbst(self) -> None:
        """Sonst scheitert der Import still und alles heisst 'nicht ermittelbar'."""
        self.assertIn("getattr(self, 'mkpfs_dir'", self.lesen)

    def test_die_alte_regel_ist_weg(self) -> None:
        """alpha8-Regel (nur fakelib) und der zweite Container-Weg sind entfernt."""
        for name in ("_ist_aktive_ampr_bibliothek", "_ampr_marker_im_container"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(GUI, name))

    def test_sicherung_orig_zaehlt_nicht_als_einbau(self) -> None:
        """`.orig` ist die weggelegte Originaldatei, kein eingebauter Emulator."""
        self.assertFalse(bib.einbauten_bewerten(["fakelib/libSceAmpr.sprx.orig"])["ampr"])
        self.assertFalse(bib.einbauten_bewerten(["fakelib2/libSceAmpr.sprx.orig"])["ampr"])

    def test_verdeckt_heisst_nur_der_verdeckte_ordner(self) -> None:
        erg = bib.einbauten_bewerten(["fakelib/libSceAmpr.sprx", "fakelib2/x.sprx"])
        self.assertEqual((False, True), (erg["ampr"], erg["ampr_verdeckt"]))
        erg = bib.einbauten_bewerten(["fakelib/libSceAmpr.sprx", "fakelib2/libSceAmpr.sprx"])
        self.assertEqual((True, False), (erg["ampr"], erg["ampr_verdeckt"]))

    def test_alte_merker_werden_neu_gelesen(self) -> None:
        """Ergebnisse von vor der neuen Regel (ohne ``regel``) gelten nicht mehr."""
        with tempfile.TemporaryDirectory() as tmp:
            gui = _gui()
            speicher = bib.Bildspeicher(os.path.join(tmp, "cover"))
            gui._bibliothek_bildspeicher = lambda: speicher
            datei = os.path.join(tmp, "spiel.ffpfsc")
            Path(datei).write_bytes(b"x")
            speicher.einbauten_schreiben(datei, {"zustand": "ok", "ampr": True, "ordner": "fakelib"})
            with mock.patch.object(gui, "_container_dateien",
                                   return_value=["fakelib/libSceAmpr.sprx", "fakelib2/a.sprx"]):
                self.assertEqual("info_popup.ampr_verdeckt", gui._ampr_emu_stand(datei))


class DreiZustaendeTests(unittest.TestCase):
    """Der Metadatenleser muss "kein Marker" von "nicht nachgesehen" trennen.

    ``AbbildMetadaten`` traegt den AMPR-Befund als ``meta["ampr_emu"]``
    im Vorbeigehen mit, waehrend es den Baum nach param.json, param.sfo
    und icon0.png durchsucht. Sind diese drei beisammen, **bricht die
    Schleife ab**. (Teuer waere das Weiterlaufen nicht - die Leser haben den
    Baum da schon ganz gelesen, gemessen in test_durchsicht_runde19.)

    Daraus folgen drei Zustaende, und bis zum 03.09.2026 gab es hier nur
    einen: Ohne Marker blieb das Feld leer, und "es ist keiner drin" sah
    genauso aus wie "wurde gar nicht zu Ende gesucht".
    """

    QUELLE = ROOT / "ps5_validator" / "utils" / "abbild_metadaten.py"

    @classmethod
    def setUpClass(cls) -> None:
        import ast

        baum = ast.parse(cls.QUELLE.read_text(encoding="utf-8", errors="replace"))
        cls.weichen = [k for k in ast.walk(baum) if isinstance(k, ast.If)
                       and "ampr_gesehen" in ast.unparse(k.test)]

    def test_es_gibt_die_weiche_ueberhaupt(self) -> None:
        self.assertTrue(self.weichen,
                        "Keine Verzweigung auf ampr_gesehen gefunden.")

    def test_der_zweite_zustand_haengt_am_vollstaendigen_durchlauf(self) -> None:
        """"Nein" darf nur stehen, wenn der Baum ganz gelesen wurde."""
        import ast

        zweig = next((k for k in self.weichen if k.orelse), None)
        self.assertIsNotNone(
            zweig, "Es gibt keinen Zweig fuer \"kein Marker gefunden\".")
        text = ast.unparse(zweig.orelse)
        self.assertIn("durchlauf_vollstaendig", text,
                      "Der Nein-Zweig prueft nicht, ob der Durchlauf "
                      "vollstaendig war - dann behauptet er etwas ueber "
                      "Dateien, die niemand angesehen hat.")
        self.assertIn("ampr_emu_nein", text)

    def test_der_merker_wird_nur_ohne_abbruch_gesetzt(self) -> None:
        """Er gehoert in die ``else``-Klausel der Schleife, nicht in den Rumpf.

        Im Rumpf stuende er auch nach einem ``break`` auf True - und die
        Unterscheidung waere wieder futsch.
        """
        import ast

        baum = ast.parse(self.QUELLE.read_text(encoding="utf-8", errors="replace"))
        treffer = [s for s in ast.walk(baum) if isinstance(s, ast.For)
                   and s.orelse
                   and "durchlauf_vollstaendig" in ast.unparse(s.orelse)]
        self.assertTrue(
            treffer,
            "durchlauf_vollstaendig steht in keiner for-else-Klausel.")

    def test_die_vorbelegung_ist_falsch(self) -> None:
        """Ohne sie waere der Merker beim ersten Abbruch undefiniert."""
        quelle = self.QUELLE.read_text(encoding="utf-8", errors="replace")
        self.assertIn("durchlauf_vollstaendig = False", quelle)

    def test_beide_beschriftungen_gibt_es(self) -> None:
        from ps5_validator.utils import i18n

        for schluessel in ("info_popup.meta.ampr_emu_ja",
                           "info_popup.meta.ampr_emu_nein"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, i18n.STRINGS)


class MetadatenleserRegelTests(unittest.TestCase):
    """Der Metadatenleser nach der 1.7-Regel - an einem nachgebauten Leser."""

    class _Leser:
        def __init__(self, pfade: list[str]) -> None:
            self.pfade = pfade

        def iter_files(self):
            for pfad in self.pfade:
                yield types.SimpleNamespace(rel_path=pfad)

        def read_file(self, _eintrag):
            yield b"{}"

    def _ampr(self, pfade: list[str]) -> str:
        from ps5_validator.utils import abbild_metadaten
        leser = abbild_metadaten.Metadatenleser(text=lambda s, **_w: s)
        meta, _bild = leser._extract_meta_from_exfat_reader(self._Leser(pfade))
        return meta.get("ampr_emu", "")

    def test_ganzer_durchlauf(self) -> None:
        for pfade, erwartet in (
                (["fakelib2/libSceAmpr.sprx"], "info_popup.meta.ampr_emu_ja"),
                (["fakelib/libSceAmpr.sprx"], "info_popup.meta.ampr_emu_ja"),
                (["fakelib/libSceAmpr.sprx", "fakelib2/a.sprx"], "info_popup.meta.ampr_emu_nein"),
                (["fakelib/x.sprx"], "info_popup.meta.ampr_emu_nein")):
            with self.subTest(pfade=pfade):
                self.assertEqual(erwartet, self._ampr(pfade))

    def test_dump_ordner(self) -> None:
        """Der Ordnerweg (``_read_game_meta``): der erste vorhandene Ordner gilt."""
        from ps5_validator.utils import abbild_metadaten
        leser = abbild_metadaten.Metadatenleser(text=lambda s, **_w: s)
        for inhalt, erwartet in (
                ({"fakelib2/libSceAmpr.sprx": b"a"}, "info_popup.meta.ampr_emu_ja"),
                ({"fakelib/libSceAmpr.sprx": b"a"}, "info_popup.meta.ampr_emu_ja"),
                ({"fakelib/libSceAmpr.sprx": b"a", "fakelib2/x.sprx": b"x"},
                 "info_popup.meta.ampr_emu_nein")):
            with self.subTest(inhalt=sorted(inhalt)), tempfile.TemporaryDirectory() as tmp:
                ordner = _dump(Path(tmp), inhalt)
                self.assertEqual(erwartet, leser._read_game_meta(str(ordner), deep_scan=False)
                                 .get("ampr_emu"))

    def test_nach_abbruch_nur_was_sicher_ist(self) -> None:
        """Abbruch nach den drei Zieldateien: ein ungesehenes fakelib2 koennte verdecken."""
        ziel = ["sce_sys/param.json", "sce_sys/param.sfo", "sce_sys/icon0.png"]
        self.assertEqual("", self._ampr(["fakelib/libSceAmpr.sprx"] + ziel + ["fakelib2/a"]),
                         "AMPR in fakelib vor dem Abbruch ist kein sicheres Ja mehr.")
        self.assertEqual("info_popup.meta.ampr_emu_ja",
                         self._ampr(["fakelib2/libSceAmpr.sprx"] + ziel + ["x"]),
                         "AMPR in fakelib2 gewinnt immer - das Ja ist sicher.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
