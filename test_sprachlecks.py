# -*- coding: utf-8 -*-
"""Was der Anwender liest, geht durch die Uebersetzung - ohne Ausnahme.

``test_sprachtexte.py`` prueft, dass die **Trennung** haelt: kein Helfermodul
bindet ``i18n`` ein. Diese Datei prueft das Gegenstueck - dass die
Uebersetzung an jeder sichtbaren Stelle auch wirklich **angewandt** wird.

Die Werkzeugpruefung vom 06.09.2026 fand mehrere Stellen, an denen sie es
nicht wurde. Sie sind alle von einer Bauart: Neben einer Zeile mit
``self._t(...)`` steht eine ohne. Der Nachbar ist uebersetzt, diese eine
nicht - und beim Lesen des Quelltextes faellt genau das nicht auf.

**Warum ein Waechter und nicht nur die Korrektur.** Die Lecks sind ueber
41.000 Zeilen verteilt und entstehen immer wieder neu: Wer eine Statuszeile
ergaenzt, schreibt den Satz hin, weil er ihn im Kopf hat. Ein Test, der
danach sucht, meldet es beim naechsten Lauf.

**Die Vorgehensweise.** Gesucht wird ueber den Syntaxbaum, nicht ueber
Zeichenketten im Quelltext - eine Suche nach ``"_set_status("`` findet die
Stelle nicht mehr, sobald jemand die Zeile umbricht. Der Baum ueberlebt das.
Zusaetzlich wird gemessen: Die Oberflaeche wird auf Englisch nachgebaut und
abgelesen, was wirklich herauskommt. Nur das beweist etwas.
"""
from __future__ import annotations

import ast
import io
import os
import re
import sys
import unittest

PROJEKT = os.path.dirname(os.path.abspath(__file__))
if PROJEKT not in sys.path:
    sys.path.insert(0, PROJEKT)

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("sprachlecks")

from ps5_validator.utils.i18n import STRINGS, translate     # noqa: E402
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

G = APP.PS5ConverterGUI

#: Woran ein deutscher Satz zu erkennen ist. Umlaute allein genuegen nicht -
#: viele Meldungen kommen ohne aus ("Fehler.", "Quelle nicht gefunden").
DEUTSCH = re.compile(
    r"[äöüÄÖÜß]|\b(?:der|die|das|und|nicht|wird|wurde|werden|kann|koennen|"
    r"bitte|Datei|Dateien|Ordner|Fehler|Abbruch|abgeschlossen|Erstelle|"
    r"Entpacke|Vorbereitung|gefunden|vorhanden|Sekunden|Speicher|laeuft|"
    r"pruefen|waehlen|Quelle|Ziel|erfordert|akzeptiert)\b")

#: Methoden, deren Text der Anwender liest. ``logger.*`` steht bewusst nicht
#: dabei - das geht in die Protokolldatei und darf deutsch bleiben.
SICHTBARE_SCHREIBER = {
    "_set_status", "set_status", "_status", "_append_to_log", "_protokoll",
    "showinfo", "showwarning", "showerror", "askyesno", "askokcancel",
    "askretrycancel",
}

#: Stellen, die bewusst so bleiben. Jede braucht eine Begruendung - eine
#: Ausnahmeliste ohne Begruendung waechst, bis der Test nichts mehr meldet.
ERLAUBT: dict[str, str] = {
}


def _quelltext() -> str:
    with io.open(APP.__file__, "rb") as fh:
        return fh.read().decode("utf-8")


def _fester_text(knoten: ast.AST) -> str | None:
    """Der feste Textanteil eines Ausdrucks - auch aus f-String und ``+``."""
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
        return knoten.value
    if isinstance(knoten, ast.JoinedStr):
        teile = [w.value for w in knoten.values
                 if isinstance(w, ast.Constant) and isinstance(w.value, str)]
        return "".join(teile) if teile else None
    if isinstance(knoten, ast.BinOp) and isinstance(knoten.op, ast.Add):
        links = _fester_text(knoten.left) or ""
        rechts = _fester_text(knoten.right) or ""
        return (links + rechts) or None
    return None


def _deutsche_stellen() -> list[tuple[int, str, str]]:
    """Alle Stellen, an denen fester deutscher Text sichtbar wird."""
    baum = ast.parse(_quelltext())
    gefunden: list[tuple[int, str, str]] = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        name = (getattr(knoten.func, "attr", None)
                or getattr(knoten.func, "id", None) or "")

        def _melde(wie: str, ausdruck: ast.AST) -> None:
            text = _fester_text(ausdruck)
            if not text or not DEUTSCH.search(text):
                return
            if text in STRINGS or text in ERLAUBT:
                return
            gefunden.append((knoten.lineno, wie, text))

        if name in SICHTBARE_SCHREIBER:
            for arg in knoten.args:
                _melde(name, arg)
        if name == "set" and isinstance(knoten.func, ast.Attribute) and knoten.args:
            ziel = (getattr(knoten.func.value, "id", "")
                    or getattr(knoten.func.value, "attr", ""))
            if ziel.endswith("_var") or ziel.endswith("_label"):
                _melde(ziel + ".set", knoten.args[0])
        for schluesselwort in knoten.keywords:
            if schluesselwort.arg in ("text", "title") and name not in ("_t", "translate"):
                _melde("%s(%s=)" % (name, schluesselwort.arg), schluesselwort.value)
    return sorted(gefunden)


class KeinFesterTextInDerOberflaecheTests(unittest.TestCase):
    """Der Rundumschlag ueber den Syntaxbaum."""

    def test_nichts_sichtbares_steht_fest_auf_deutsch(self):
        stellen = _deutsche_stellen()
        bericht = "\n".join("  %s:%d  %s  %r"
                            % (os.path.basename(APP.__file__), z, wie, t[:90])
                            for z, wie, t in stellen)
        self.assertEqual(
            [], stellen,
            "%d Stellen schreiben festen deutschen Text in die Oberflaeche. "
            "Wer das Programm auf Englisch stellt, liest dort trotzdem "
            "Deutsch. Jede Stelle braucht einen Schluessel in i18n.STRINGS "
            "und einen Aufruf ueber self._t(...):\n%s"
            % (len(stellen), bericht))


class VorabpruefungTests(unittest.TestCase):
    """Die Meldungen, die vor dem Start einer Aufgabe erscheinen."""

    AUFGABEN = ("pack_folder", "unpack_to_exfat", "pack_file",
                "ffpkg_to_ffpfsc", "batch_convert", "universal_convert",
                "dump_validator")

    def _gui(self):
        gui = G.__new__(G)
        gui._t = lambda s, **w: translate("en", s, **w)
        gui._fmt_bytes = lambda n: "%d B" % n
        gui._get_runtime_temp_dir = lambda: PROJEKT
        gui._find_osfmount = lambda: None            # nicht gefunden
        gui._missing_critical_dump_files = lambda m, s: ["eboot.bin"]
        gui._estimate_unpack_space_requirement = lambda s: None
        return gui

    def test_auf_englisch_kommt_kein_deutsch_zurueck(self):
        """Gemessen, nicht gelesen: der Weg wird wirklich gegangen."""
        schlecht: list[str] = []
        for aufgabe in self.AUFGABEN:
            fehler, warnungen = G._run_preflight_checks(
                self._gui(), aufgabe, PROJEKT, PROJEKT)
            for satz in list(fehler) + list(warnungen):
                if DEUTSCH.search(satz):
                    schlecht.append("%s: %r" % (aufgabe, satz[:100]))
        self.assertEqual([], schlecht,
                         "Die englische Oberflaeche bekommt deutsche "
                         "Vorabmeldungen:\n  " + "\n  ".join(schlecht))


class QuellenpruefungTests(unittest.TestCase):
    """``_validate_source_path`` meldet, warum eine Quelle nicht taugt."""

    FAELLE = (
        ("pack_folder", os.path.join(PROJEKT, "README.md")),
        ("unpack_to_exfat", PROJEKT),
        ("unpack_to_exfat", os.path.join(PROJEKT, "README.md")),
        ("pack_file", PROJEKT),
        ("pack_file", os.path.join(PROJEKT, "README.md")),
        ("ffpkg_to_ffpfsc", PROJEKT),
        ("ffpkg_to_ffpfsc", os.path.join(PROJEKT, "README.md")),
        ("inspect", PROJEKT),
        ("dump_validator", os.path.join(PROJEKT, "README.md")),
        ("exfat_to_folder", PROJEKT),
        ("unpack_to_game_folder", PROJEKT),
    )

    def test_auf_englisch_kommt_kein_deutsch_zurueck(self):
        gui = G.__new__(G)
        gui._t = lambda s, **w: translate("en", s, **w)
        schlecht: list[str] = []
        for aufgabe, pfad in self.FAELLE:
            meldung = gui._validate_source_path(pfad, aufgabe)
            if meldung and DEUTSCH.search(meldung):
                schlecht.append("%s: %r" % (aufgabe, meldung[:100]))
        self.assertEqual([], schlecht,
                         "Die englische Oberflaeche bekommt deutsche "
                         "Quellenmeldungen:\n  " + "\n  ".join(schlecht))

    def test_es_kommt_ueberhaupt_eine_meldung(self):
        """Gegenprobe: Ein Test, der nur auf 'kein Deutsch' prueft, waere
        auch mit lauter leeren Meldungen gruen."""
        gui = G.__new__(G)
        gui._t = lambda s, **w: translate("en", s, **w)
        leer = [a for a, p in self.FAELLE
                if not gui._validate_source_path(p, a)]
        self.assertEqual([], leer,
                         "Diese Faelle melden gar nichts: %s" % leer)


class VorlagenWerdenGefuettertTests(unittest.TestCase):
    """Helfer mit Vorlagen-Parameter muessen ihn an JEDER Stelle bekommen."""

    def _aufrufe(self, funktionsname: str) -> list[ast.Call]:
        baum = ast.parse(_quelltext())
        return [k for k in ast.walk(baum)
                if isinstance(k, ast.Call)
                and getattr(k.func, "attr", "") == funktionsname]

    def test_beanstandungen_bekommt_ueberall_texte(self):
        aufrufe = self._aufrufe("beanstandungen")
        self.assertGreaterEqual(len(aufrufe), 3, "Aufrufstellen verschwunden?")
        ohne = [k.lineno for k in aufrufe
                if not any(w.arg == "texte" for w in k.keywords)]
        self.assertEqual([], ohne,
                         "beanstandungen() ohne texte= in Zeile %s - dort "
                         "faellt die deutsche Vorgabe des Moduls durch." % ohne)

    def test_der_pruefstand_bekommt_ueberall_einen_uebersetzer(self):
        aufrufe = [k for k in ast.walk(ast.parse(_quelltext()))
                   if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "Pruefstand"]
        self.assertGreaterEqual(len(aufrufe), 1)
        ohne = [k.lineno for k in aufrufe
                if not any(w.arg == "text" for w in k.keywords)]
        self.assertEqual([], ohne,
                         "Pruefstand ohne text= in Zeile %s - dann meldet er "
                         "rohe Schluessel oder deutsche Vorgaben." % ohne)


class NeueSchluesselTests(unittest.TestCase):
    """Was dazukommt, kommt in beiden Sprachen dazu."""

    def test_jeder_schluessel_hat_beide_sprachen(self):
        unvollstaendig = [k for k, v in STRINGS.items()
                          if not v.get("de") or not v.get("en")]
        self.assertEqual([], unvollstaendig)

    def test_platzhalter_stimmen_zwischen_den_sprachen_ueberein(self):
        """Ein {pfad} auf Deutsch und {path} auf Englisch wirft zur Laufzeit."""
        muster = re.compile(r"\{([a-zA-Z_][a-zA-Z_0-9]*)\}")
        schief = []
        for schluessel, werte in STRINGS.items():
            de = set(muster.findall(werte.get("de", "")))
            en = set(muster.findall(werte.get("en", "")))
            if de != en:
                schief.append("%s: de=%s en=%s" % (schluessel,
                                                   sorted(de), sorted(en)))
        self.assertEqual([], schief, "\n  ".join(schief))


if __name__ == "__main__":
    unittest.main(verbosity=2)
