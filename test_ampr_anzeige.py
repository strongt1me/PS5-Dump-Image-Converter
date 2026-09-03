#!/usr/bin/env python3
"""Sichert die AMPR-EMU-Anzeige in der Spiel-Infobox ab.

Die Anzeige beantwortet eine Frage, die vorher niemand beantworten konnte:
Steckt in dieser Quelle schon ein AMPR EMU? Drei Wege fuehren dorthin, und
jeder hat seine eigene Fehlerquelle:

* **Dump-Ordner** - der Marker liegt im Dateisystem, ``_fakelib_pfad``
  entscheidet ueber den Ordnernamen.
* **exFAT-basiertes Abbild** - ``mkpfs.game_metadata.read_game_metadata()``.
* **PFS-in-PFS** - dort liest die Engine nichts; der Rueckfall geht ueber
  ``open_inner_file_view`` und den vorhandenen PFS-Adapter.

Der wichtigste Fall ist der vierte: **Wenn nichts gelesen werden konnte, darf
nicht "nicht eingebaut" dastehen.** Genau das lieferte die Engine bei
UFS2-basierten ``.ffpkg`` - ein Nein ueber etwas, in das sie nie hineingesehen
hat.
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import PS5ImageConverter_Pro_FINAL_revised as hauptprogramm  # noqa: E402

GUI = hauptprogramm.PS5ConverterGUI


def _attrappe(**felder) -> types.SimpleNamespace:
    """Baut ein GameMetadata-aehnliches Objekt."""
    vorgabe = {
        "game_title": "", "content_id": "", "has_apr_emu": False, "error": "",
        "title_id": "", "package_type": "", "version": "", "region": "",
        "icon_bytes": None, "file_size": 0, "file_name": "", "file_path": "",
    }
    vorgabe.update(felder)
    return types.SimpleNamespace(**vorgabe)


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
                           "info_popup.ampr_nicht_eingebaut", "info_popup.ampr_unlesbar"):
            with self.subTest(schluessel=schluessel):
                eintrag = i18n.STRINGS.get(schluessel)
                self.assertIsNotNone(eintrag, f"{schluessel} fehlt")
                for sprache in ("de", "en"):
                    self.assertTrue(str(eintrag.get(sprache, "")).strip(),
                                    f"{schluessel} hat keine {sprache}-Fassung")

    def test_wird_beim_aktualisieren_gesetzt(self) -> None:
        self.assertIn('self._meta_labels["ampr_emu"].set(_ampr_text)', self.quelltext,
                      "Die Zeile wird nie befuellt")


class ErkennungTests(unittest.TestCase):
    """Der Weg zur Antwort - mit Attrappen statt echter Abbilder."""

    def setUp(self) -> None:
        self.gui = GUI.__new__(GUI)
        self.gui.mkpfs_dir = ""
        # _t gibt den Schluessel zurueck: so ist die Entscheidung pruefbar,
        # ohne an einer Uebersetzung zu haengen.
        self.gui._t = lambda key, **kw: key

    # -- Ordner ------------------------------------------------------------
    def test_ordner_mit_marker(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "fakelib"
            fake.mkdir()
            (fake / GUI._AMPR_SPRX_NAME).write_bytes(b"x")
            self.gui._fakelib_pfad = lambda wurzel: fake
            self.assertEqual("info_popup.ampr_eingebaut", self.gui._ampr_emu_stand(tmp))

    def test_ordner_ohne_marker(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "fakelib"
            fake.mkdir()
            self.gui._fakelib_pfad = lambda wurzel: fake
            self.assertEqual("info_popup.ampr_nicht_eingebaut", self.gui._ampr_emu_stand(tmp))

    # -- Nicht vorhandene Quellen -----------------------------------------
    def test_leerer_pfad(self) -> None:
        self.assertEqual("–", self.gui._ampr_emu_stand(""))

    def test_pfad_gibt_es_nicht(self) -> None:
        self.assertEqual("–", self.gui._ampr_emu_stand(str(ROOT / "gibt-es-nicht.ffpfsc")))


class LeeresErgebnisTests(unittest.TestCase):
    """Der Kern: ein leeres Ergebnis ist kein Nein.

    Bei UFS2-basierten .ffpkg liest ``read_game_metadata`` gar nichts und
    meldet trotzdem ``has_apr_emu=False``. Wer das anzeigt, behauptet etwas
    ueber eine Datei, in die niemand hineingesehen hat.
    """

    def setUp(self) -> None:
        self.gui = GUI.__new__(GUI)
        self.gui.mkpfs_dir = ""
        self.gui._t = lambda key, **kw: key
        # Container-Rueckfall abschalten, damit nur der Metadatenweg zaehlt.
        self.gui._ampr_marker_im_container = lambda pfad: None
        self.datei = ROOT / "test_ampr_anzeige.py"      # existiert, Inhalt egal

    def _mit_antwort(self, antwort) -> str:
        modul = types.ModuleType("mkpfs.game_metadata")
        modul.read_game_metadata = lambda pfad: antwort
        paket = types.ModuleType("mkpfs")
        paket.__path__ = []
        alt = {k: sys.modules.get(k) for k in ("mkpfs", "mkpfs.game_metadata")}
        sys.modules["mkpfs"] = paket
        sys.modules["mkpfs.game_metadata"] = modul
        try:
            return self.gui._ampr_emu_stand(str(self.datei))
        finally:
            for k, v in alt.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_leeres_ergebnis_ist_kein_nein(self) -> None:
        """Kein Titel, keine Content-ID, kein Fehlertext - trotzdem kein Nein."""
        erg = self._mit_antwort(_attrappe(has_apr_emu=False, package_type="FFPKG"))
        self.assertEqual("info_popup.ampr_unlesbar", erg)

    def test_fehlertext_ist_kein_nein(self) -> None:
        erg = self._mit_antwort(_attrappe(error="missing exFAT file system signature"))
        self.assertEqual("info_popup.ampr_unlesbar", erg)

    def test_gelesenes_nein_gilt(self) -> None:
        """Mit Titel ist das Nein belastbar."""
        erg = self._mit_antwort(_attrappe(game_title="Irgendein Spiel", has_apr_emu=False))
        self.assertEqual("info_popup.ampr_nicht_eingebaut", erg)

    def test_gelesenes_ja_gilt(self) -> None:
        erg = self._mit_antwort(_attrappe(game_title="Irgendein Spiel", has_apr_emu=True))
        self.assertEqual("info_popup.ampr_eingebaut", erg)

    def test_content_id_genuegt_als_beleg(self) -> None:
        """Auch ohne Titel ist eine Content-ID ein Zeichen, dass gelesen wurde."""
        erg = self._mit_antwort(_attrappe(content_id="UP1234-PPSA00001_00-000", has_apr_emu=True))
        self.assertEqual("info_popup.ampr_eingebaut", erg)


class ContainerRueckfallTests(unittest.TestCase):
    """Der Rueckfall fuer PFS-in-PFS."""

    def setUp(self) -> None:
        self.gui = GUI.__new__(GUI)
        self.gui.mkpfs_dir = ""
        self.gui._t = lambda key, **kw: key

    def test_rueckfall_greift_wenn_metadaten_schweigen(self) -> None:
        self.gui._ampr_marker_im_container = lambda pfad: True
        modul = types.ModuleType("mkpfs.game_metadata")
        modul.read_game_metadata = lambda pfad: _attrappe(error="missing exFAT file system signature")
        paket = types.ModuleType("mkpfs")
        paket.__path__ = []
        alt = {k: sys.modules.get(k) for k in ("mkpfs", "mkpfs.game_metadata")}
        sys.modules["mkpfs"] = paket
        sys.modules["mkpfs.game_metadata"] = modul
        try:
            erg = self.gui._ampr_emu_stand(str(ROOT / "test_ampr_anzeige.py"))
        finally:
            for k, v in alt.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        self.assertEqual("info_popup.ampr_eingebaut", erg)

    def test_rueckfall_setzt_den_engine_pfad_selbst(self) -> None:
        """Sonst scheitert der Import still und alles heisst 'nicht ermittelbar'."""
        quelle = Path(hauptprogramm.__file__).read_text(encoding="utf-8", errors="replace")
        anfang = quelle.index("def _ampr_marker_im_container")
        ende = quelle.index("def ", anfang + 10)
        rumpf = quelle[anfang:ende]
        self.assertIn("mkpfs_dir", rumpf,
                      "Der Container-Weg setzt den Engine-Pfad nicht selbst")

    def test_sicherung_orig_zaehlt_nicht_als_einbau(self) -> None:
        """`.orig` ist die weggelegte Originaldatei, kein eingebauter Emulator."""
        quelle = Path(hauptprogramm.__file__).read_text(encoding="utf-8", errors="replace")
        anfang = quelle.index("def _ampr_marker_im_container")
        ende = quelle.index("\n    def ", anfang + 10)
        rumpf = quelle[anfang:ende]
        self.assertIn('rel.endswith("/" + marke) or rel == marke', rumpf,
                      "Der Vergleich trifft sonst auch libSceAmpr.sprx.orig")


class DreiZustaendeTests(unittest.TestCase):
    """Der Metadatenleser muss "kein Marker" von "nicht nachgesehen" trennen.

    ``AbbildMetadaten`` traegt den AMPR-Befund als ``meta["ampr_emu"]``
    im Vorbeigehen mit, waehrend es den Baum nach param.json, param.sfo
    und icon0.png durchsucht. Sind diese drei beisammen, **bricht die
    Schleife ab** - bei grossen Titeln waere das Weiterlesen teuer.

    Daraus folgen drei Zustaende, und bis zum 03.09.2026 gab es hier nur
    einen: Ohne Marker blieb das Feld leer, und "es ist keiner drin" sah
    genauso aus wie "wurde gar nicht zu Ende gesucht".

    Geprueft wird die Weiche selbst, nicht ein ganzes Abbild: Ein
    Probecontainer mit mehreren tausend Dateien waere fuer diese eine
    Unterscheidung unverhaeltnismaessig.
    """

    QUELLE = Path("ps5_validator/utils/abbild_metadaten.py")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
