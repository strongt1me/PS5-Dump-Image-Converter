# -*- coding: utf-8 -*-
"""Aufgabe 7: Welche AMPR-EMU- und welche PlayGo-Fassung? (03.10.2026)

Der Nutzer: "Mir fehlt bei der Aufgabe 7 eine Auswahl, welche AMPR EMU Version bzw.
welche PlayGo Version man benutzen moechte. (Mit der aktuellsten Version bitte immer
oben beginnend in der Liste anzeigen)."

Bis dahin nahmen die beiden Methoden-Fenster von Aufgabe 7 je Bibliothek die neueste
Fassung und fragten nur "PlayGo ja/nein"; eine aeltere Fassung war nicht waehlbar.
Bewacht wird hier:

* Die Listen zeigen die neueste Fassung **zuerst** - auch wenn der Aufrufer sie
  durcheinander gibt - und haben sie vorgewaehlt.
* PlayGo kommt nie von selbst mit (Projektregel), nur auf ausdruecklichen Haken, und
  wird dann in der gewaehlten Fassung abgelegt.
* Abbruch ist Abbruch (``None``); ein Fenster, das sich nicht bauen laesst, ist ein
  Fehler und kein stiller Abbruch; wo nichts zu waehlen ist, kommt keine Rueckfrage.
* Die gewaehlte Fassung landet wirklich im Spielordner (Lauf der Automatik mit Attrappen
  fuer Konsole und Fenster, echte Dateien).
"""
from __future__ import annotations

import ast
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_fassungswahl")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import shadowmount_generation as sg  # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

G = APP.PS5ConverterGUI
AMPR = "libSceAmpr.sprx"
PLAYGO = "libScePlayGo.sprx"


def _eintrag(lib: str, version: str, variant: str, groesse: int = 1000, quelle: str = "beilage",
             pfad: str = "") -> dict:
    return {"lib": lib, "version": version, "variant": variant, "size": groesse, "quelle": quelle,
            "path": pfad or "/vorrat/%s %s/%s" % (version, variant, lib), "sha256": "", "wurzel": "/vorrat"}


def _vorrat_durcheinander() -> list[dict]:
    """Absichtlich unsortiert - die Fenster duerfen sich nicht auf die Reihenfolge verlassen."""
    return [
        _eintrag(AMPR, "0.3.6.6", "no debug", 410000),
        _eintrag(AMPR, "0.4.2.1", "test-nopack", 303878),
        _eintrag(PLAYGO, "0.4", "nolog", 30000, quelle="geholt"),
        _eintrag(AMPR, "0.3.6.4", "debug", 520000),
        _eintrag(AMPR, "0.4.2.1", "test-pack", 423350),
        _eintrag(PLAYGO, "0.5", "log", 36000),
        _eintrag(AMPR, "0.4.2.1", "test-debug-pack", 633094),
        _eintrag(PLAYGO, "0.5", "nolog", 35000),
    ]


# ---------------------------------------------------------------------------
# Die Vermittlung zwischen Arbeitsfaden und Fenster - ohne Tk
# ---------------------------------------------------------------------------

class _Stuetze:
    """Traegt nur, was ``_ampr_gen_fassungen_waehlen`` von ``self`` braucht."""

    _AMPR_SPRX_NAME = G._AMPR_SPRX_NAME
    _PLAYGO_SPRX_NAME = G._PLAYGO_SPRX_NAME
    _AMPR_DEFAULT_APPLY_LIBS = G._AMPR_DEFAULT_APPLY_LIBS
    _AMPR_GEN_ANTWORT_GRENZE = 5.0
    _ampr_gen_fassungen_waehlen = G._ampr_gen_fassungen_waehlen
    _ampr_gen_fassungen_ohne_pack = G._ampr_gen_fassungen_ohne_pack
    _ampr_gen_auswahl_bibliotheken = G._ampr_gen_auswahl_bibliotheken

    def __init__(self, *, antwort=None, fehler: Exception | None = None, planen: bool = True,
                 ausfuehren: bool = True) -> None:
        self.antwort, self.fehler, self.planen, self.ausfuehren = antwort, fehler, planen, ausfuehren
        self.dialoge: list = []

    def _spaeter_im_fenster(self, _fenster, rueckruf, *args) -> bool:
        if not self.planen:
            return False
        if self.ausfuehren:
            rueckruf(*args)
        return True

    def _ampr_gen_fassungen_dialog(self, fenster, vorrat):
        self.dialoge.append((fenster, list(vorrat)))
        if self.fehler is not None:
            raise self.fehler
        return self.antwort


class VermittlungTests(unittest.TestCase):

    def test_ohne_entscheidung_kommt_keine_rueckfrage(self) -> None:
        """Eine AMPR-Fassung und kein PlayGo: Es gibt nichts zu waehlen."""
        stuetze = _Stuetze(antwort="darf nicht gefragt werden")
        nur = _eintrag(AMPR, "0.4.2.1", "test-nopack")
        self.assertEqual([nur], stuetze._ampr_gen_fassungen_waehlen(None, [nur]))
        self.assertEqual([], stuetze.dialoge, "Gefragt wurde trotzdem.")

    def test_ein_leerer_vorrat_gibt_eine_leere_liste(self) -> None:
        stuetze = _Stuetze()
        self.assertEqual([], stuetze._ampr_gen_fassungen_waehlen(None, []))
        self.assertEqual([], stuetze.dialoge)

    def test_mehrere_fassungen_oder_ein_playgo_fragen(self) -> None:
        vorrat = _vorrat_durcheinander()
        for teil in (vorrat, [e for e in vorrat if e["lib"] == AMPR],
                     [_eintrag(AMPR, "0.4.2.1", "test-pack"), _eintrag(PLAYGO, "0.5", "nolog")]):
            with self.subTest(anzahl=len(teil)):
                stuetze = _Stuetze(antwort={"ampr": None, "playgo": None})
                stuetze._ampr_gen_fassungen_waehlen(None, teil)
                self.assertEqual(1, len(stuetze.dialoge))

    def test_die_wahl_wird_in_eintraege_uebersetzt_ampr_zuerst(self) -> None:
        vorrat = _vorrat_durcheinander()
        ampr, playgo = vorrat[0], vorrat[2]
        stuetze = _Stuetze(antwort={"ampr": ampr, "playgo": playgo})
        self.assertEqual([ampr, playgo], stuetze._ampr_gen_fassungen_waehlen(None, vorrat))
        stuetze = _Stuetze(antwort={"ampr": ampr, "playgo": None})
        self.assertEqual([ampr], stuetze._ampr_gen_fassungen_waehlen(None, vorrat),
                         "PlayGo kommt nur mit, wenn es gewaehlt wurde.")

    def test_nur_playgo_gewaehlt_oder_gar_nichts(self) -> None:
        vorrat = _vorrat_durcheinander()
        stuetze = _Stuetze(antwort={"ampr": None, "playgo": vorrat[2]})
        self.assertEqual([vorrat[2]], stuetze._ampr_gen_fassungen_waehlen(None, vorrat))
        stuetze = _Stuetze(antwort={"ampr": None, "playgo": None})
        self.assertEqual([], stuetze._ampr_gen_fassungen_waehlen(None, vorrat),
                         "Eine leere Wahl ist keine Abbruch: Die Automatik meldet 'keine Bibliothek'.")

    def test_abbruch_gibt_none(self) -> None:
        stuetze = _Stuetze(antwort=None)
        self.assertIsNone(stuetze._ampr_gen_fassungen_waehlen(None, _vorrat_durcheinander()))

    def test_ein_fenster_das_nicht_aufgeht_ist_ein_fehler_kein_abbruch(self) -> None:
        stuetze = _Stuetze(fehler=ValueError("kaputt"))
        with self.assertRaises(RuntimeError) as ctx:
            stuetze._ampr_gen_fassungen_waehlen(None, _vorrat_durcheinander())
        self.assertIn("kaputt", str(ctx.exception))

    def test_ohne_fenster_keine_antwort(self) -> None:
        stuetze = _Stuetze(planen=False)
        self.assertIsNone(stuetze._ampr_gen_fassungen_waehlen(None, _vorrat_durcheinander()))
        self.assertEqual([], stuetze.dialoge)

    def test_bleibt_die_antwort_aus_gibt_der_faden_auf(self) -> None:
        """Sonst haengt der Arbeitsfaden fuer immer, wenn das Fenster waehrend der Frage zugeht."""
        stuetze = _Stuetze(ausfuehren=False)
        stuetze._AMPR_GEN_ANTWORT_GRENZE = 0.05
        self.assertIsNone(stuetze._ampr_gen_fassungen_waehlen(None, _vorrat_durcheinander()))

    def test_die_vorgabe_ohne_rueckfrage_ist_die_neueste(self) -> None:
        """Der Weg ohne Fenster nimmt, was auch im Fenster vorgewaehlt waere."""
        vorrat = [_eintrag(AMPR, "0.4.2.1", "test-nopack"), _eintrag(AMPR, "0.3.6.6", "no debug")]
        stuetze = _Stuetze(antwort={"ampr": vorrat[0], "playgo": None})
        self.assertEqual([vorrat[0]], stuetze._ampr_gen_fassungen_waehlen(None, vorrat))
        einzig = [_eintrag(AMPR, "0.4.2.1", "test-nopack")]
        self.assertEqual("0.4.2.1", _Stuetze()._ampr_gen_fassungen_waehlen(None, einzig)[0]["version"])

    # --- Die Pack-Bauten stehen nicht zur Wahl (Wunsch des Nutzers, 03.10.2026) ------------------------
    def test_pack_bauten_zaehlen_nicht_als_wahl(self) -> None:
        """Eine normale Fassung neben zwei Pack-Bauten: Es gibt nichts zu waehlen - keine Rueckfrage."""
        normal = _eintrag(AMPR, "0.4.2.1", "test-nopack")
        vorrat = [_eintrag(AMPR, "0.4.2.1", "test-pack"), normal, _eintrag(AMPR, "0.4.2.1", "test-debug-pack")]
        stuetze = _Stuetze(antwort="darf nicht gefragt werden")
        self.assertEqual([normal], stuetze._ampr_gen_fassungen_waehlen(None, vorrat))
        self.assertEqual([], stuetze.dialoge)

    def test_nur_pack_bauten_im_speicher_geben_eine_leere_liste(self) -> None:
        vorrat = [_eintrag(AMPR, "0.4.2.1", "test-pack"), _eintrag(AMPR, "0.4.2.1", "test-debug-pack")]
        stuetze = _Stuetze(antwort="darf nicht gefragt werden")
        self.assertEqual([], stuetze._ampr_gen_fassungen_waehlen(None, vorrat),
                         "Auch keine Vorgabe, die eine Pack-Fassung nimmt.")
        self.assertEqual([], stuetze.dialoge)

    def test_das_fenster_bekommt_keine_pack_bauten(self) -> None:
        stuetze = _Stuetze(antwort={"ampr": None, "playgo": None})
        stuetze._ampr_gen_fassungen_waehlen(None, _vorrat_durcheinander())
        gezeigt = stuetze.dialoge[0][1]
        self.assertEqual([], [e for e in gezeigt if e["variant"] in ("test-pack", "test-debug-pack")])
        self.assertEqual(6, len(gezeigt), "Drei AMPR-Fassungen und drei PlayGo-Fassungen bleiben.")

    def test_playgo_hat_keine_pack_bauten_und_bleibt_unberuehrt(self) -> None:
        playgo = [_eintrag(PLAYGO, "0.5", "log"), _eintrag(PLAYGO, "0.5", "nolog")]
        self.assertEqual(playgo, _Stuetze()._ampr_gen_fassungen_ohne_pack(playgo))


# ---------------------------------------------------------------------------
# Das Fenster selbst
# ---------------------------------------------------------------------------

@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _bauen(self, vorrat=None) -> dict:
        fenster = self.app._ampr_gen_fassungen_fenster(
            _WURZEL, _vorrat_durcheinander() if vorrat is None else vorrat)
        self.addCleanup(lambda: fenster["fenster"].winfo_exists() and fenster["fenster"].destroy())
        return fenster

    def _versionen(self, eintraege) -> list:
        return [self.app._ampr_version_sort_key(e["version"]) for e in eintraege]

    def test_die_liste_zeigt_die_neueste_fassung_zuerst_auch_bei_unsortierter_vorlage(self) -> None:
        f = self._bauen()
        versionen = self._versionen(f["ampr_liste"])
        self.assertEqual(sorted(versionen, reverse=True), versionen)
        self.assertEqual((("0.4.2.1", "test-nopack"), ("0.3.6.6", "no debug"), ("0.3.6.4", "debug")),
                         tuple((e["version"], e["variant"]) for e in f["ampr_liste"]))
        playgo = self._versionen(f["playgo_liste"])
        self.assertEqual(sorted(playgo, reverse=True), playgo)
        self.assertEqual(("0.5", "0.5", "0.4"), tuple(e["version"] for e in f["playgo_liste"]))

    def test_die_neueste_ist_vorgewaehlt_und_die_zeilen_stehen_in_derselben_reihenfolge(self) -> None:
        f = self._bauen()
        self.assertEqual(0, f["ampr_box"].current())
        self.assertEqual(0, f["playgo_box"].current())
        self.assertEqual([self.app._ampr_fassung_zeile(e) for e in f["ampr_liste"]],
                         list(f["ampr_box"]["values"]))
        self.assertEqual([self.app._ampr_fassung_zeile(e) for e in f["playgo_liste"]],
                         list(f["playgo_box"]["values"]))

    def test_playgo_ist_aus_bis_der_haken_gesetzt_ist(self) -> None:
        f = self._bauen()
        self.assertFalse(f["playgo_an"].get(), "PlayGo kommt nie von selbst mit.")
        self.assertEqual("disabled", str(f["playgo_box"]["state"]))
        f["ok"]()
        self.assertEqual({"ampr": f["ampr_liste"][0], "playgo": None}, f["antwort"]["wert"])

    def test_der_haken_schaltet_die_playgo_liste(self) -> None:
        f = self._bauen()
        f["playgo_haken"].invoke()
        self.assertTrue(f["playgo_an"].get())
        self.assertEqual("readonly", str(f["playgo_box"]["state"]))
        f["playgo_haken"].invoke()
        self.assertEqual("disabled", str(f["playgo_box"]["state"]))

    def test_pack_bauten_stehen_nie_in_der_liste(self) -> None:
        """Wunsch des Nutzers (03.10.2026): "diese zwei mit pack duerfen nicht mit in die Liste"."""
        f = self._bauen()
        self.assertEqual([], [e for e in f["ampr_liste"] if e["variant"] in ("test-pack", "test-debug-pack")])
        for zeile in f["ampr_box"]["values"]:
            with self.subTest(zeile=zeile):
                self.assertNotIn("test-pack", zeile)
                self.assertNotIn("test-debug-pack", zeile)
        self.assertIn("test-nopack", "".join(f["ampr_box"]["values"]),
                      "Die Fassung ohne Pack bleibt - nur die zwei mit Pack fehlen.")

    def test_nur_pack_bauten_im_speicher_geben_keine_ampr_liste(self) -> None:
        f = self._bauen([e for e in _vorrat_durcheinander()
                         if e["lib"] == PLAYGO or e["variant"] in ("test-pack", "test-debug-pack")])
        self.assertIsNone(f["ampr_box"])
        self.assertEqual([], f["ampr_liste"])
        f["ok"]()
        self.assertEqual({"ampr": None, "playgo": None}, f["antwort"]["wert"])

    def test_eine_aeltere_fassung_und_ein_gewaehltes_playgo_kommen_zurueck(self) -> None:
        f = self._bauen()
        f["ampr_box"].current(1)
        f["playgo_haken"].invoke()
        f["playgo_box"].current(2)
        f["ok"]()
        wahl = f["antwort"]["wert"]
        self.assertEqual(("0.3.6.6", "no debug"), (wahl["ampr"]["version"], wahl["ampr"]["variant"]))
        self.assertEqual(("0.4", "nolog"), (wahl["playgo"]["version"], wahl["playgo"]["variant"]))
        self.assertFalse(f["fenster"].winfo_exists(), "Das Fenster schliesst sich.")

    def test_ein_abgewaehlter_haken_legt_kein_playgo_ab_auch_wenn_ein_eintrag_gewaehlt_war(self) -> None:
        f = self._bauen()
        f["playgo_haken"].invoke()
        f["playgo_box"].current(1)
        f["playgo_haken"].invoke()
        f["ok"]()
        self.assertIsNone(f["antwort"]["wert"]["playgo"])

    def test_abbrechen_gibt_none(self) -> None:
        f = self._bauen()
        f["abbrechen"]()
        self.assertIsNone(f["antwort"]["wert"])
        self.assertFalse(f["fenster"].winfo_exists())

    def test_enter_escape_und_das_schliessen_des_fensters_sind_belegt(self) -> None:
        f = self._bauen()
        for taste in ("<Return>", "<KP_Enter>", "<Escape>"):
            with self.subTest(taste=taste):
                self.assertTrue(f["fenster"].bind(taste), "%s ist nicht belegt." % taste)
        self.assertTrue(f["fenster"].protocol("WM_DELETE_WINDOW"), "Das X des Fensters ist nicht belegt.")

    def test_enter_auf_abbrechen_bricht_ab_statt_abzulegen(self) -> None:
        """tkinter-gui-Pruefung 03.10.2026: Die Enter-Bindung sitzt am Fenster - wer mit Tab auf
        "Abbrechen" steht und Enter drueckt, darf nichts ablegen."""
        f = self._bauen()
        f["eingabe"](types.SimpleNamespace(widget=f["abbrechen_knopf"]))
        self.assertIsNone(f["antwort"]["wert"], "Enter auf \"Abbrechen\" hat abgelegt.")
        self.assertFalse(f["fenster"].winfo_exists())

    def test_enter_auf_jedem_anderen_feld_legt_ab(self) -> None:
        for feld in ("ampr_box", "playgo_haken", None):
            with self.subTest(feld=feld):
                f = self._bauen()
                ereignis = None if feld is None else types.SimpleNamespace(widget=f[feld])
                f["eingabe"](ereignis)
                self.assertEqual({"ampr": f["ampr_liste"][0], "playgo": None}, f["antwort"]["wert"])
                self.assertFalse(f["fenster"].winfo_exists())

    def test_ohne_playgo_im_speicher_ist_der_haken_gesperrt(self) -> None:
        f = self._bauen([e for e in _vorrat_durcheinander() if e["lib"] == AMPR])
        self.assertEqual("disabled", str(f["playgo_haken"]["state"]))
        self.assertIsNone(f["playgo_box"])
        f["ok"]()
        self.assertEqual({"ampr": f["ampr_liste"][0], "playgo": None}, f["antwort"]["wert"])

    def test_ohne_ampr_im_speicher_gibt_es_keine_ampr_liste(self) -> None:
        f = self._bauen([e for e in _vorrat_durcheinander() if e["lib"] == PLAYGO])
        self.assertIsNone(f["ampr_box"])
        f["playgo_haken"].invoke()
        f["ok"]()
        self.assertEqual({"ampr": None, "playgo": f["playgo_liste"][0]}, f["antwort"]["wert"])

    def test_der_hinweis_folgt_der_auswahl(self) -> None:
        f = self._bauen()
        debug = next(i for i, e in enumerate(f["ampr_liste"]) if e["variant"] == "debug")
        f["ampr_box"].current(debug)
        f["ampr_box"].event_generate("<<ComboboxSelected>>")
        text = str(f["ampr_hinweis"].cget("text"))
        self.assertIn(self.app._t("amprgen.variante_debug"), text)
        self.assertIn(self.app._t("amprgen.quelle_beilage"), text)
        f["ampr_box"].current(0)
        f["ampr_box"].event_generate("<<ComboboxSelected>>")
        self.assertIn(self.app._t("amprgen.variante_nopack"), str(f["ampr_hinweis"].cget("text")))

    def test_die_fenster_sagen_in_beiden_sprachen_dasselbe_ohne_loecher(self) -> None:
        schluessel = {s for s in STRINGS if s.startswith("amprgen.fassung") or s.startswith("amprgen.q_fassungen")
                      or s.startswith("amprgen.variante_") or s.startswith("amprgen.quelle_")}
        self.assertGreaterEqual(len(schluessel), 18)
        for s in sorted(schluessel):
            with self.subTest(schluessel=s):
                for sprache in ("de", "en"):
                    self.assertTrue(str(STRINGS[s].get(sprache, "")).strip(), "%s fehlt in %s" % (s, sprache))


class ZeilenTests(unittest.TestCase):
    """Die Texte der Liste und des Hinweises - ohne Fenster."""

    @classmethod
    def setUpClass(cls) -> None:
        # Nur ``_t`` und ``_fmt_bytes`` braucht die Stuetze vom Programm.
        class _Text:
            _AMPR_VARIANTEN_TEXTE = G._AMPR_VARIANTEN_TEXTE
            _AMPR_QUELLEN_TEXTE = G._AMPR_QUELLEN_TEXTE
            _fmt_bytes = staticmethod(G._fmt_bytes)
            _ampr_fassung_zeile = G._ampr_fassung_zeile
            _ampr_fassung_hinweis = G._ampr_fassung_hinweis

            def _t(self, schluessel, **werte):
                return STRINGS[schluessel]["de"].format(**werte)

        cls.t = _Text()

    def test_die_zeile_nennt_version_variante_und_groesse(self) -> None:
        zeile = self.t._ampr_fassung_zeile(_eintrag(AMPR, "0.4.2.1", "test-pack", 423350))
        self.assertIn("0.4.2.1", zeile)
        self.assertIn("test-pack", zeile)
        self.assertIn(G._fmt_bytes(423350), zeile)

    def test_fehlende_angaben_stuerzen_nicht(self) -> None:
        zeile = self.t._ampr_fassung_zeile({"lib": AMPR})
        self.assertIn("?", zeile)
        self.assertEqual("", self.t._ampr_fassung_hinweis(None))
        self.assertEqual("", self.t._ampr_fassung_hinweis({}))

    def test_jede_bekannte_variante_hat_einen_hinweis(self) -> None:
        for variante in G._AMPR_VARIANT_ORDER:
            with self.subTest(variante=variante):
                self.assertTrue(self.t._ampr_fassung_hinweis(
                    {"variant": variante, "quelle": "beilage"}).strip())
                self.assertIn(variante, G._AMPR_VARIANTEN_TEXTE,
                              "Eine Variante der Sortierung ohne Beschreibung im Fenster.")

    def test_eine_unbekannte_variante_hat_nur_die_herkunft(self) -> None:
        self.assertEqual(STRINGS["amprgen.quelle_geholt"]["de"],
                         self.t._ampr_fassung_hinweis({"variant": "standard", "quelle": "geholt"}))

    def test_jede_quelle_des_vorrats_hat_einen_text(self) -> None:
        for quelle in G._AMPR_QUELLEN_RANG:
            with self.subTest(quelle=quelle):
                self.assertIn(quelle, G._AMPR_QUELLEN_TEXTE)


# ---------------------------------------------------------------------------
# Die Automatik: die gewaehlte Fassung landet im Spiel
# ---------------------------------------------------------------------------

def _methode(name: str) -> ast.FunctionDef:
    baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8"))
    klasse = next(k for k in baum.body if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
    return next(k for k in klasse.body if isinstance(k, ast.FunctionDef) and k.name == name)


class AutomatikTests(unittest.TestCase):

    def test_die_automatik_fragt_nicht_mehr_nur_nach_playgo(self) -> None:
        knoten = _methode("_ampr_gen_automatik")
        aufrufe = {k.func.attr for k in ast.walk(knoten)
                   if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)}
        konstanten = {k.value for k in ast.walk(knoten)
                      if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        self.assertIn("_ampr_gen_fassungen_waehlen", aufrufe)
        self.assertNotIn("amprgen.q_playgo", konstanten, "Die alte Ja/Nein-Frage ist ersetzt.")
        self.assertNotIn("amprgen.q_playgo", STRINGS)

    def test_die_automatik_liest_den_ganzen_vorrat_und_fragt_danach(self) -> None:
        knoten = _methode("_ampr_gen_automatik")
        zeilen = {k.func.attr: k.lineno for k in ast.walk(knoten)
                  if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
                  and k.func.attr in ("_ampr_alle_fassungen", "_ampr_gen_fassungen_waehlen",
                                      "_ampr_gen_ablegen_mit_ergebnis")}
        self.assertLess(zeilen["_ampr_alle_fassungen"], zeilen["_ampr_gen_fassungen_waehlen"])
        self.assertLess(zeilen["_ampr_gen_fassungen_waehlen"], zeilen["_ampr_gen_ablegen_mit_ergebnis"],
                        "Erst waehlen, dann ablegen.")


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class LaufTests(unittest.TestCase):
    """Die Automatik ohne Konsole, mit echten Dateien: Was gewaehlt wurde, liegt danach im Spiel."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ampr_fassungswahl_")
        self.addCleanup(self._tmp.cleanup)
        wurzel = Path(self._tmp.name)
        self.spiel = wurzel / "spiel"
        (self.spiel / "sce_sys").mkdir(parents=True)
        self.vorrat = []
        for lib, version, variant in ((AMPR, "0.4.2.1", "test-nopack"), (AMPR, "0.3.6.6", "no debug"),
                                      (PLAYGO, "0.5", "nolog")):
            ordner = wurzel / "vorrat" / ("%s %s" % (version, variant)) / lib
            ordner.parent.mkdir(parents=True)
            ordner.write_bytes(("%s-%s-%s" % (lib, version, variant)).encode("ascii"))
            self.vorrat.append(_eintrag(lib, version, variant, ordner.stat().st_size, pfad=str(ordner)))

    def _lauf(self, wahl) -> list[str]:
        """Laeuft die Automatik lokal; ``wahl`` ersetzt das Fenster der Fassungswahl."""
        app = self.app
        meldungen: list[str] = []
        with mock.patch.object(app, "_ampr_gen_adresse_finden", return_value=""), \
                mock.patch.object(app, "_ampr_gen_frage", return_value="lokal"), \
                mock.patch.object(app, "_ampr_gen_ordner_fragen", return_value=str(self.spiel)), \
                mock.patch.object(app, "_ampr_ablage_wahl", return_value=app.ABLAGE_AUTO), \
                mock.patch.object(app, "_ampr_alle_fassungen", return_value=list(self.vorrat)), \
                mock.patch.object(app, "_ampr_gen_fassungen_waehlen", side_effect=wahl) as frage:
            app._ampr_gen_automatik(sg.ALT, None, meldungen.append)
        self.assertEqual(1, frage.call_count, "Die Fassungen werden genau einmal gefragt.")
        self.frage = frage
        return meldungen

    def _abgelegt(self) -> dict:
        ziel = self.spiel / sg.ablageordner(sg.ALT, sg.ORT_SPIEL)
        return {p.name: p.read_bytes() for p in ziel.glob("*.sprx")} if ziel.is_dir() else {}

    def test_die_gewaehlte_aeltere_fassung_landet_im_spiel(self) -> None:
        aelter = self.vorrat[1]
        meldungen = self._lauf(lambda fenster, vorrat: [aelter])
        self.assertEqual({AMPR: b"libSceAmpr.sprx-0.3.6.6-no debug"}, self._abgelegt(),
                         "Die aeltere, nicht die neueste Fassung - und kein PlayGo.")
        self.assertIn(self.app._t("amprgen.lib_chosen", lib=AMPR, version="0.3.6.6", variant="no debug"),
                      meldungen)
        self.assertIn(self.app._t("amprgen.finished"), meldungen)

    def test_playgo_wird_abgelegt_wenn_es_gewaehlt_wurde(self) -> None:
        self._lauf(lambda fenster, vorrat: [self.vorrat[0], self.vorrat[2]])
        abgelegt = self._abgelegt()
        self.assertEqual(b"libSceAmpr.sprx-0.4.2.1-test-nopack", abgelegt[AMPR])
        self.assertEqual(b"libScePlayGo.sprx-0.5-nolog", abgelegt[PLAYGO])

    def test_die_wahl_sieht_den_ganzen_vorrat(self) -> None:
        self._lauf(lambda fenster, vorrat: [vorrat[0]])
        vorrat = self.frage.call_args[0][1]
        self.assertEqual(3, len(vorrat))

    def test_abbruch_legt_nichts_ab_und_sagt_es(self) -> None:
        meldungen = self._lauf(lambda fenster, vorrat: None)
        self.assertEqual({}, self._abgelegt())
        self.assertFalse((self.spiel / sg.ablageordner(sg.ALT, sg.ORT_SPIEL)).exists(),
                         "Nicht einmal der Ordner entsteht.")
        self.assertIn(self.app._t("amprgen.cancelled"), meldungen)
        self.assertNotIn(self.app._t("amprgen.finished"), meldungen)

    def test_eine_leere_wahl_meldet_keine_bibliothek(self) -> None:
        meldungen = self._lauf(lambda fenster, vorrat: [])
        self.assertEqual({}, self._abgelegt())
        self.assertIn(self.app._t("amprgen.no_libs"), meldungen)

    def test_ein_fenster_das_nicht_aufgeht_wird_als_fehler_gemeldet(self) -> None:
        def _kaputt(fenster, vorrat):
            raise RuntimeError("Fenster kaputt")

        meldungen = self._lauf(_kaputt)
        self.assertTrue(any("Fenster kaputt" in m for m in meldungen), meldungen)
        self.assertEqual({}, self._abgelegt())


if __name__ == "__main__":
    unittest.main(verbosity=2)
