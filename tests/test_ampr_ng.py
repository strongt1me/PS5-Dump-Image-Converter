# -*- coding: utf-8 -*-
"""ampr-emu-ng im Bestand (02.11.2026): waehlbar und als "NG" erkennbar.

Der Nutzer: "Koennen wir diesen AMPR EMU ebenfalls in die Auswahl nehmen [...]? So das man erkennt, dass es
sich um die NG Version handelt" (quer3q/ampr-emu-ng v0.2.0, eigenstaendige Weiterentwicklung von drakmor/ampr_emu).

Bewacht wird hier:

* Die beiden Dateien liegen byte-gleich mit der Freigabe im Bestand (``0.2.0 ng``, ``0.2.0 ng-debug``).
* NG gilt als Ersatzbibliothek, nicht als Sony-Original - im Hauptmodul und in ``ps5_backport``. NG traegt das
  Kennzeichen ``[AMPR_EMU]`` nicht; ohne Anpassung waere es beim naechsten Einbau als ``.orig`` gesichert worden.
* NG steht in beiden Listen als "NG 0.2.0", als eigene Reihe hinter der von drakmor - die Vorgabe bleibt 0.4.2.1.
* Der Aktualisierungsvergleich fuer drakmor wird durch NG nicht verschoben.
"""
from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_ng")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ampr_assetpakete as ap      # noqa: E402
from ps5_validator.utils import ampr_updates as au          # noqa: E402
from ps5_validator.utils import ps5_backport as bp          # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

G = APP.PS5ConverterGUI
BESTAND = PROJEKT / "PlayGo & AMPR_EMU"
NG_DATEIEN = {
    # Ordner im Bestand -> SHA-256 laut GitHub-Digest der Freigabe v0.2.0 (Anhang libSceAmpr.sprx / -debug.sprx)
    "0.2.0 ng": "7acb2173d9691b5dfb94ea4007660920b7250111c5fd7a86c6eb91b763ad3d76",
    "0.2.0 ng-debug": "15fd9e82561f1dcd181126672164aabc8a8954db0d5d79d13641706bfdb31881",
}


def _eintrag(version: str, variante: str, lib: str = "libSceAmpr.sprx") -> dict:
    return {"lib": lib, "version": version, "variant": variante, "size": 1000,
            "path": "/x/%s %s/%s" % (version, variante, lib), "sha256": "", "quelle": "beilage"}


class BestandTests(unittest.TestCase):
    def test_die_dateien_sind_die_der_freigabe(self) -> None:
        for ordner, soll in NG_DATEIEN.items():
            with self.subTest(ordner=ordner):
                datei = BESTAND / "AMPR_EMU" / ordner / "libSceAmpr.sprx"
                self.assertTrue(datei.is_file(), datei)
                self.assertEqual(soll, hashlib.sha256(datei.read_bytes()).hexdigest())

    def test_ng_ist_ersatz_und_kein_original(self) -> None:
        for ordner in NG_DATEIEN:
            datei = BESTAND / "AMPR_EMU" / ordner / "libSceAmpr.sprx"
            with self.subTest(ordner=ordner):
                daten = datei.read_bytes()
                self.assertNotIn(b"[AMPR_EMU]", daten, "Messgrundlage: NG traegt das alte Kennzeichen nicht")
                self.assertIn(b"ampr-emu-ng 0.2.0", daten)
                self.assertTrue(G._ist_ersatzbibliothek(datei))
                self.assertTrue(bp._ist_emu_datei(str(datei)))

    def test_die_ersten_kennzeichen_bleiben_an_ihrem_platz(self) -> None:
        """test_backport greift per Index auf [0] (AMPR EMU) und [1] (PlayGo-Stub) zu."""
        self.assertEqual((b"[AMPR_EMU]", b"playgo_stub.dat"), bp.EMU_KENNZEICHEN[:2])
        self.assertEqual(bp.EMU_KENNZEICHEN, G._ERSATZ_KENNZEICHEN)

    def test_der_scanner_liest_ng_und_die_vorgabe_bleibt_0_4_2_1(self) -> None:
        gui = G.__new__(G)
        eintraege = [e for e in gui._ampr_scan_einen_speicher(str(BESTAND)) if e["lib"] == "libSceAmpr.sprx"]
        paare = [(e["version"], e["variant"]) for e in eintraege]
        self.assertIn(("0.2.0", "ng"), paare)
        self.assertIn(("0.2.0", "ng-debug"), paare)
        self.assertEqual(("0.4.2.1", "test-nopack"), paare[0], "die oberste (= Vorgabe) bleibt drakmor")
        ng = [i for i, e in enumerate(eintraege) if G._ampr_ist_ng(e)]
        self.assertEqual(list(range(len(paare) - 2, len(paare))), ng, "NG steht als eigene Reihe am Ende")


class BeschriftungTests(unittest.TestCase):
    def test_klappliste_aufgabe_1(self) -> None:
        self.assertEqual("NG 0.2.0", G._ampr_beschriftung(_eintrag("0.2.0", "ng")))
        self.assertEqual("NG 0.2.0 debug", G._ampr_beschriftung(_eintrag("0.2.0", "ng-debug")))
        self.assertEqual("0.4.2.1", G._ampr_beschriftung(_eintrag("0.4.2.1", "test-nopack")))

    def test_ng_liest_packs_ist_aber_kein_reiner_packbau(self) -> None:
        for variante in ("ng", "ng-debug", "NG"):
            with self.subTest(variante=variante):
                self.assertTrue(ap.variante_kann_packen(variante))
                self.assertFalse(ap.variante_nur_packbau(variante))
        self.assertTrue(ap.variante_nur_packbau("test-pack"))
        self.assertTrue(ap.variante_nur_packbau("test-debug-pack"))
        self.assertFalse(ap.variante_nur_packbau("test-nopack"))

    def test_aufgabe_7_behaelt_ng_und_laesst_die_packbauten_weg(self) -> None:
        gui = G.__new__(G)
        vorrat = [_eintrag("0.4.2.1", "test-nopack"), _eintrag("0.4.2.1", "test-pack"),
                  _eintrag("0.4.2.1", "test-debug-pack"), _eintrag("0.2.0", "ng"), _eintrag("0.2.0", "ng-debug")]
        self.assertEqual([("0.4.2.1", "test-nopack"), ("0.2.0", "ng"), ("0.2.0", "ng-debug")],
                         [(e["version"], e["variant"]) for e in gui._ampr_gen_fassungen_ohne_pack(vorrat)])

    def test_ng_steht_in_beiden_listen(self) -> None:
        vorrat = sorted([_eintrag("0.4.2.1", "test-nopack"), _eintrag("0.4.2.1", "test-pack"),
                         _eintrag("0.2.0", "ng"), _eintrag("0.2.0", "ng-debug"), _eintrag("0.3.6.6", "no debug")],
                        key=G.__new__(G)._ampr_sortierschluessel)
        for methode, erwartet in ((APP.AMPR_METHODE_NORMAL, ["0.4.2.1", "0.3.6.6 no debug", "NG 0.2.0",
                                                             "NG 0.2.0 debug"]),
                                  (APP.AMPR_METHODE_ASSETPACK, ["0.4.2.1 test-pack", "NG 0.2.0",
                                                                "NG 0.2.0 debug"])):
            with self.subTest(methode=methode):
                app = G.__new__(G)
                app.ampr_version_combo = mock.Mock()
                app.ampr_version_var = mock.Mock()
                app._ampr_methode = lambda m=methode: m
                app._load_setting = lambda schluessel, vorgabe=None: vorgabe
                app._append_to_log = lambda text: None
                app._t = lambda schluessel, **w: schluessel
                app._ampr_versionsliste_fuellen(eintraege=list(vorrat))
                self.assertEqual(erwartet, list(app.ampr_version_combo.configure.call_args.kwargs["values"]))
                app.ampr_version_var.set.assert_called_with(erwartet[0])

    def test_fassungswahl_aufgabe_7(self) -> None:
        class _Text:
            _AMPR_VARIANTEN_TEXTE = G._AMPR_VARIANTEN_TEXTE
            _AMPR_QUELLEN_TEXTE = G._AMPR_QUELLEN_TEXTE
            _AMPR_NG_VARIANTEN = G._AMPR_NG_VARIANTEN
            _AMPR_NG_ZEILENVARIANTE = G._AMPR_NG_ZEILENVARIANTE
            _ampr_ist_ng = G._ampr_ist_ng
            _ampr_anzeige_fassung = G._ampr_anzeige_fassung
            _fmt_bytes = staticmethod(G._fmt_bytes)
            _ampr_fassung_zeile = G._ampr_fassung_zeile
            _ampr_fassung_hinweis = G._ampr_fassung_hinweis

            def _t(self, schluessel, **werte):
                return STRINGS[schluessel]["de"].format(**werte)

        t = _Text()
        zeile = t._ampr_fassung_zeile(_eintrag("0.2.0", "ng"))
        self.assertTrue(zeile.startswith("NG 0.2.0"), zeile)
        self.assertIn("release", zeile)
        self.assertNotIn("· ng ", zeile, "die Variante steht nicht doppelt da")
        self.assertIn("debug", t._ampr_fassung_zeile(_eintrag("0.2.0", "ng-debug")))
        self.assertIn("ampr-emu-ng", t._ampr_fassung_hinweis(_eintrag("0.2.0", "ng")))
        self.assertIn("9090", t._ampr_fassung_hinweis(_eintrag("0.2.0", "ng-debug")))

    def test_die_texte_gibt_es_in_allen_sprachen(self) -> None:
        for schluessel in ("amprgen.variante_ng", "amprgen.variante_ng_debug"):
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel][sprache].strip())


class PackformatTests(unittest.TestCase):
    """Warum NG in der Liste Asset-Pack stehen darf: Das Packwerkzeug schreibt, was NG liest.

    Die Zahlen stammen aus ``crates/ampr-lz4/src/lib.rs`` und ``manifest.rs`` von ampr-emu-ng 0.2.0 (gelesen am
    02.11.2026): Kopf 128 Byte mit Pruefsumme bei 116, Dateieintrag 48, Chunk 12, Pack 32, Datenkopf 64 mit
    Pruefsumme bei 56, Manifest Version 4, Daten Version 3. Aendert das Werkzeug sein Format, muss NG neu
    geprueft werden, bevor es in der Liste bleibt.
    """

    def test_das_werkzeug_schreibt_das_format_das_ng_liest(self) -> None:
        sys.path.insert(0, str(PROJEKT / ap.PACKWERKZEUG_ORDNER))
        try:
            import ampr_pack_format as fmt                  # noqa: PLC0415
        finally:
            sys.path.remove(str(PROJEKT / ap.PACKWERKZEUG_ORDNER))
        self.assertEqual((b"AMPRPAK4", 4, b"AMPRDAT3", 3),
                         (fmt.INDEX_MAGIC, fmt.INDEX_VERSION, fmt.DATA_MAGIC, fmt.DATA_VERSION))
        self.assertEqual((128, 48, 12, 32, 64),
                         (fmt.INDEX_HEADER.size, fmt.FILE_RECORD.size, fmt.CHUNK_RECORD.size,
                          fmt.PACK_RECORD.size, fmt.DATA_HEADER.size))
        self.assertEqual("ampr_assets.index", ap.MANIFEST_NAME)


class HinweisTests(unittest.TestCase):
    """Nach dem Einbau von NG kommt die Meldung "update_emulators=0" (Nutzerwunsch 03.11.2026)."""

    NG = BESTAND / "AMPR_EMU" / "0.2.0 ng" / "libSceAmpr.sprx"
    DRAKMOR = BESTAND / "AMPR_EMU" / "0.4.2.1 test-nopack" / "libSceAmpr.sprx"

    def setUp(self) -> None:
        import tempfile
        self.tmp = tempfile.TemporaryDirectory(prefix="ampr_ng_hinweis_")
        self.addCleanup(self.tmp.cleanup)
        self.log: list[str] = []
        gui = G.__new__(G)
        gui._t = lambda schluessel, **w: STRINGS[schluessel]["de"].format(**w)
        gui._append_to_log = self.log.append
        gui._fakelib_pfad = lambda root: Path(root) / "fakelib"
        gui._ampr_ablage_pruefen = lambda root: []
        gui.root = None
        self.gui = gui
        zeigen = mock.patch.object(APP.messagebox, "showinfo")
        self.showinfo = zeigen.start()
        self.addCleanup(zeigen.stop)

    def _einbauen(self, quelle: Path) -> bool:
        return self.gui._ampr_apply_library(self.tmp.name, str(quelle), "libSceAmpr.sprx")

    def test_ng_bringt_die_meldung(self) -> None:
        self.assertTrue(self._einbauen(self.NG))
        self.assertEqual(1, self.showinfo.call_count)
        titel, text = self.showinfo.call_args.args
        self.assertIn("NG", titel)
        self.assertIn("update_emulators=0", text)
        self.assertTrue(any("update_emulators=0" in z for z in self.log), "auch im Protokoll")

    def test_drakmor_bringt_keine_meldung(self) -> None:
        self.assertTrue(self._einbauen(self.DRAKMOR))
        self.showinfo.assert_not_called()
        self.assertFalse(any("update_emulators" in z for z in self.log))

    def test_playgo_aus_einem_ng_ordner_zaehlt_nicht(self) -> None:
        """Nur libSceAmpr.sprx ist NG - der Name der Zieldatei entscheidet mit."""
        stub = next(BESTAND.rglob("libScePlayGo.sprx"))
        self.assertTrue(self.gui._ampr_apply_library(self.tmp.name, str(stub), "libScePlayGo.sprx"))
        self.showinfo.assert_not_called()

    def test_in_einem_lauf_nur_einmal_im_naechsten_wieder(self) -> None:
        self.gui._lauf_variablen = {}
        self._einbauen(self.NG)
        self._einbauen(self.NG)                          # Sammelkonvertierung: zweites Spiel im selben Lauf
        self.assertEqual(1, self.showinfo.call_count)
        self.assertEqual(2, sum("update_emulators=0" in z for z in self.log), "das Protokoll nennt es je Spiel")
        self.gui._lauf_variablen = {}                    # der naechste Lauf legt einen neuen Stand an
        self._einbauen(self.NG)
        self.assertEqual(2, self.showinfo.call_count)

    def test_im_cli_betrieb_nur_das_protokoll(self) -> None:
        self.gui._cli_mode = True
        self._einbauen(self.NG)
        self.showinfo.assert_not_called()
        self.assertTrue(any("update_emulators=0" in z for z in self.log))

    def test_ftp_picker_bringt_die_meldung(self) -> None:
        eintrag = {"lib": "libSceAmpr.sprx", "version": "0.2.0", "variant": "ng", "path": str(self.NG)}
        self.gui._ampr_scan_version_store = lambda store: [eintrag]
        self.gui._ampr_ftp_upload_file = lambda *a: True
        self.gui._fakelib_ordnername = lambda: "fakelib"
        self.assertEqual((1, 0), self.gui._ampr_ftp_apply_set(object(), "/data/ps5/PPSA00000", "x",
                                                                libs=("libSceAmpr.sprx",)))
        self.assertEqual(1, self.showinfo.call_count)

    def test_die_automatik_von_aufgabe_7_meldet_es_auch(self) -> None:
        import ast
        import inspect
        quelle = ast.unparse(ast.parse(inspect.getsource(G._ampr_gen_automatik).strip()))
        self.assertIn("_ampr_ist_ng_datei", quelle)
        self.assertIn("_ampr_ng_hinweis(eltern=fenster)", quelle)

    def test_die_texte_nennen_den_schalter_in_jeder_sprache(self) -> None:
        for sprache in ("de", "en", "es", "it", "fr"):
            with self.subTest(sprache=sprache):
                self.assertIn("update_emulators=0", STRINGS["ampr.ng_update_emulators"][sprache])
                self.assertIn("ShadowMount+", STRINGS["ampr.ng_update_emulators"][sprache])
                self.assertTrue(STRINGS["ampr.ng_update_emulators_titel"][sprache].strip())


def _ng_antwort(*fassungen: str, vorab: str = "") -> bytes:
    """Eine Releases-Antwort von quer3q/ampr-emu-ng im Aufbau vom 03.11.2026 (gh api .../releases)."""
    import json
    freigaben = []
    for fassung in list(fassungen) + ([vorab] if vorab else []):
        freigaben.append({
            "tag_name": "v" + fassung, "draft": False, "prerelease": fassung == vorab,
            "assets": [{"name": name, "size": 4, "digest": "sha256:" + hashlib.sha256(name.encode()).hexdigest(),
                        "browser_download_url": "http://beispiel.invalid/%s/%s" % (fassung, name)}
                       for name in ("libSceAmpr-debug.sprx", "libSceAmpr.sprx", "SHA256SUMS")]})
    return json.dumps(freigaben).encode("utf-8")


def _drakmor_antwort(fassung: str) -> bytes:
    import json
    return json.dumps([{"tag_name": fassung, "assets": [{
        "name": "libSceAmpr.sprx-%s-test-nopack" % fassung, "size": 4,
        "browser_download_url": "http://beispiel.invalid/d/%s" % fassung}]}]).encode("utf-8")


class NgQuelleTests(unittest.TestCase):
    """Der Updates-Knopf holt auch ampr-emu-ng (Nutzerwunsch 03.11.2026)."""

    def test_leser_nimmt_marke_und_genaue_anhangsnamen(self) -> None:
        angebote = au.ng_angebote_lesen(_ng_antwort("0.2.0", "0.1.0", vorab="0.3.0").decode())
        self.assertEqual([("0.2.0", "ng"), ("0.2.0", "ng-debug"), ("0.1.0", "ng"), ("0.1.0", "ng-debug")],
                         [(a.fassung, a.variante) for a in angebote], "Vorabfassung und SHA256SUMS bleiben draussen")
        a = angebote[0]
        self.assertEqual("libSceAmpr.sprx", a.anhang)
        self.assertEqual(hashlib.sha256(b"libSceAmpr.sprx").hexdigest(), a.sha256)

    def test_die_leser_kreuzen_sich_nicht(self) -> None:
        self.assertEqual([], au.angebote_lesen(_ng_antwort("0.2.0").decode()),
                         "NG-Anhaenge tragen keine Nummer - der drakmor-Leser darf sie nicht nehmen")
        self.assertEqual([], au.ng_angebote_lesen(_drakmor_antwort("0.4.2.2").decode()))

    def test_ablage_heisst_wie_im_mitgelieferten_bestand(self) -> None:
        for angebot in au.ng_angebote_lesen(_ng_antwort("0.2.0").decode()):
            with self.subTest(variante=angebot.variante):
                ordner = Path(au.zielordner("x", angebot.fassung, angebot.variante)).name
                self.assertTrue((BESTAND / "AMPR_EMU" / ordner).is_dir(), ordner)

    def test_ablegen_prueft_den_digest(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ampr_ng_digest_") as wurzel:
            gut = au.Angebot("0.9.0", "ng", "libSceAmpr.sprx", "x", 4, hashlib.sha256(b"abcd").hexdigest())
            self.assertTrue(os.path.isfile(au.ablegen(wurzel, gut, b"abcd")))
            falsch = au.Angebot("0.9.1", "ng", "libSceAmpr.sprx", "x", 4, gut.sha256)
            with self.assertRaises(ValueError):
                au.ablegen(wurzel, falsch, b"abce")          # gleich lang, anderer Inhalt
            self.assertFalse(os.path.exists(au.zielpfad(wurzel, "0.9.1", "ng")), "keine falsche Datei im Bestand")

    def _lauf(self, bestand: list[dict], antworten: dict[str, bytes]):
        gui = G.__new__(G)
        protokoll: list[str] = []
        gui._ampr_alle_fassungen = lambda *a, **k: list(bestand)
        gui._melde_im_hauptstrang = protokoll.append
        gui._t = lambda schluessel, **w: schluessel + (" " + w["neueste"] if "neueste" in w else "")

        def _lade(adresse: str) -> bytes:
            for projekt, antwort in antworten.items():
                if projekt in adresse:
                    if isinstance(antwort, Exception):
                        raise antwort
                    return antwort
            raise AssertionError("unerwartete Adresse " + adresse)

        gui._ampr_lade_adresse = _lade
        gui._ampr_updates_ordner = lambda: os.path.join(os.environ.get("TEMP", "/tmp"),
                                                        "ampr_ng_gibt_es_nicht_%d" % os.getpid())
        geholt: list = []
        with mock.patch.object(au, "holen", lambda _w, a, _l: (geholt.extend(a) or ([], []))):
            gui._ampr_updates_arbeiten()
        return [(a.fassung, a.variante) for a in geholt], protokoll

    DRAKMOR_DA = [_eintrag("0.4.2.1", "test-nopack")]
    NG_DA = [_eintrag("0.2.0", "ng"), _eintrag("0.2.0", "ng-debug")]

    def test_neues_ng_wird_geholt(self) -> None:
        geholt, _p = self._lauf(self.DRAKMOR_DA + self.NG_DA, {
            au.PROJEKT: _drakmor_antwort("0.4.2.1"), au.NG_PROJEKT: _ng_antwort("0.3.0", "0.2.0")})
        self.assertEqual([("0.3.0", "ng"), ("0.3.0", "ng-debug")], geholt)

    def test_vorhandenes_ng_gilt_als_aktuell(self) -> None:
        geholt, protokoll = self._lauf(self.DRAKMOR_DA + self.NG_DA, {
            au.PROJEKT: _drakmor_antwort("0.4.2.1"), au.NG_PROJEKT: _ng_antwort("0.2.0")})
        self.assertEqual([], geholt)
        self.assertIn("ampr.update_aktuell NG 0.2.0", protokoll)

    def test_drakmor_macht_ng_nicht_alt(self) -> None:
        """Gegenprobe: Ohne NG im Bestand ist NG 0.2.0 neu, obwohl 0.4.2.1 dasteht."""
        geholt, _p = self._lauf(self.DRAKMOR_DA, {
            au.PROJEKT: _drakmor_antwort("0.4.2.1"), au.NG_PROJEKT: _ng_antwort("0.2.0")})
        self.assertEqual([("0.2.0", "ng"), ("0.2.0", "ng-debug")], geholt)

    def test_ng_macht_drakmor_nicht_alt(self) -> None:
        """Gegenprobe andersherum: Ein hoeheres NG haelt drakmor 0.4.2.2 nicht zurueck."""
        geholt, _p = self._lauf(self.DRAKMOR_DA + [_eintrag("0.9.0", "ng")], {
            au.PROJEKT: _drakmor_antwort("0.4.2.2"), au.NG_PROJEKT: _ng_antwort("0.9.0")})
        self.assertIn(("0.4.2.2", "test-nopack"), geholt)
        self.assertNotIn(("0.9.0", "ng"), geholt)

    def test_eine_ausgefallene_quelle_haelt_die_andere_nicht_auf(self) -> None:
        geholt, protokoll = self._lauf(self.DRAKMOR_DA, {
            au.PROJEKT: OSError("kein Netz"), au.NG_PROJEKT: _ng_antwort("0.2.0")})
        self.assertIn("ampr.update_fehler", protokoll)
        self.assertEqual([("0.2.0", "ng"), ("0.2.0", "ng-debug")], geholt)


class AktualisierungTests(unittest.TestCase):
    def test_ng_ist_keine_klasse_von_drakmor(self) -> None:
        self.assertEqual("ng", G._ampr_variantenklasse("ng"))
        self.assertEqual("ng-debug", G._ampr_variantenklasse("ng-debug"))

    def test_ng_im_bestand_verschiebt_den_vergleich_nicht(self) -> None:
        angebot = au.Angebot(fassung="0.4.2.2", variante="test-nopack", anhang="libSceAmpr.sprx-0.4.2.2-test-nopack",
                             adresse="http://beispiel.invalid/x", groesse=1)
        ohne = au.neuere([angebot], [("0.4.2.1", "test-nopack")])
        mit = au.neuere([angebot], [("0.4.2.1", "test-nopack"), ("0.2.0", "ng"), ("0.2.0", "ng-debug")])
        self.assertEqual(ohne, mit)
        self.assertEqual([angebot], mit)


if __name__ == "__main__":
    unittest.main()
