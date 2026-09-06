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

#: Woran ein deutscher Satz zu erkennen ist. Nur noch fuer die gemessenen
#: Pruefungen weiter unten gebraucht - der Rundumschlag sucht nicht mehr
#: danach, siehe :class:`KeinFesterTextInDerOberflaecheTests`.
DEUTSCH = re.compile(
    r"[äöüÄÖÜß]|\b(?:der|die|das|und|nicht|wird|wurde|werden|kann|koennen|"
    r"bitte|Datei|Dateien|Ordner|Fehler|Abbruch|abgeschlossen|Erstelle|"
    r"Entpacke|Vorbereitung|gefunden|vorhanden|Sekunden|Speicher|laeuft|"
    r"pruefen|waehlen|Quelle|Ziel|erfordert|akzeptiert)\b")

#: Enthaelt der Text ueberhaupt ein Wort? Trennzeichen ("=" * 50), Pfeile
#: und reine Zahlenformate sind sprachfrei und brauchen keinen Schluessel.
EIN_WORT = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}")

#: Methoden, deren Text der Anwender liest. ``logger.*`` steht bewusst nicht
#: dabei - das geht in die Protokolldatei und darf deutsch bleiben.
#: ``start_task``/``begin_prepare``/``begin_payload`` gehoeren dazu: Was sie
#: bekommen, landet in ``ProgressEngine._status_text`` und damit in der
#: Statuszeile.
SICHTBARE_SCHREIBER = {
    "_set_status", "set_status", "_status", "_append_to_log", "_protokoll",
    "showinfo", "showwarning", "showerror", "askyesno", "askokcancel",
    "askretrycancel", "start_task", "begin_prepare", "begin_payload",
}

#: Stellen, die bewusst so bleiben. Jede braucht eine Begruendung - eine
#: Ausnahmeliste ohne Begruendung waechst, bis der Test nichts mehr meldet.
ERLAUBT: dict[str, str] = {
    "PS5 DUMP": "Programmname auf dem Startbild - in beiden Sprachen gleich.",
    "& IMAGE CONVERTER": "Zweite Zeile desselben Namens.",
    "PS5 DUMP & IMAGE CONVERTER": "Programmname im Infofenster.",
    "Homebrew Edition": "Teil des Programmnamens, kein uebersetzbarer Satz.",
    "OSFMount": "Name eines fremden Werkzeugs.",
    "Dokan2": "Name eines fremden Treibers.",
    "FileZilla": "Name eines fremden Werkzeugs.",
    "[INFO] \n\n": "Reines Protokollpraefix, der Inhalt kommt aus einer Variablen.",
    "[INFO] \n": "Dasselbe.",
    "[WARN] \n": "Dasselbe.",
    "[INFO]  -> \n": "Dasselbe, mit Pfeil zwischen zwei Werten.",
    "[UFS2Tool] \n": "Praefix mit dem Namen des fremden Werkzeugs.",
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


def _feste_stellen(mit_ausnahmen: bool = True) -> list[tuple[int, str, str]]:
    """Alle Stellen, an denen fester Text in die Oberflaeche geht.

    Args:
        mit_ausnahmen: Ob :data:`ERLAUBT` angewandt wird. ``False`` liefert
            die ungefilterte Liste - daran prueft der Test, ob die
            Ausnahmen ueberhaupt noch eine Stelle betreffen.
    """
    baum = ast.parse(_quelltext())
    gefunden: list[tuple[int, str, str]] = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        name = (getattr(knoten.func, "attr", None)
                or getattr(knoten.func, "id", None) or "")

        def _melde(wie: str, ausdruck: ast.AST) -> None:
            text = _fester_text(ausdruck)
            if not text or not EIN_WORT.search(text):
                return
            if text in STRINGS:
                return
            if mit_ausnahmen and text in ERLAUBT:
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
            if schluesselwort.arg in ("text", "title", "description") \
                    and name not in ("_t", "translate", "ArgumentParser"):
                _melde("%s(%s=)" % (name, schluesselwort.arg), schluesselwort.value)
    return sorted(gefunden)


class KeinFesterTextInDerOberflaecheTests(unittest.TestCase):
    """Der Rundumschlag ueber den Syntaxbaum.

    **Gesucht wird nicht nach deutschen Woertern.** Der erste Entwurf tat
    das und uebersah dabei genau die Haelfte: "Extrahiere .ffpkg..." und
    "Neustart fehlgeschlagen" enthalten weder Umlaut noch eines der
    gesuchten Woerter, gehen aber genauso an der Uebersetzung vorbei.

    Die Regel ist deshalb einfacher und strenger: **Jeder** feste Text an
    einer sichtbaren Stelle gehoert durch ``self._t``. Ausnahmen sind
    einzeln begruendet (:data:`ERLAUBT`) - Programmname, Namen fremder
    Werkzeuge, Protokollpraefixe.
    """

    def test_nichts_sichtbares_steht_fest_im_quelltext(self):
        stellen = _feste_stellen()
        bericht = "\n".join("  %s:%d  %s  %r"
                            % (os.path.basename(APP.__file__), z, wie, t[:90])
                            for z, wie, t in stellen)
        self.assertEqual(
            [], stellen,
            "%d Stellen schreiben festen Text in die Oberflaeche. Wer das "
            "Programm auf Englisch stellt, liest dort trotzdem, was hier "
            "steht. Jede Stelle braucht einen Schluessel in i18n.STRINGS und "
            "einen Aufruf ueber self._t(...) - oder, wenn sie wirklich "
            "sprachfrei ist, einen begruendeten Eintrag in ERLAUBT:\n%s"
            % (len(stellen), bericht))

    def test_die_ausnahmeliste_ist_nicht_veraltet(self):
        """Eine Ausnahme fuer eine Stelle, die es nicht mehr gibt, deckt
        beim naechsten Mal versehentlich etwas anderes.

        Verglichen wird gegen die Texte, die der Rundumschlag wirklich
        einsammelt - nicht gegen den Rohtext der Datei. Mehrere Ausnahmen
        sind zusammengesetzt ("[INFO] " + Wert + Umbruch) und stehen so
        nirgends im Quelltext.
        """
        gesehen = {t for _z, _w, t in _feste_stellen(mit_ausnahmen=False)}
        verwaist = sorted(t for t in ERLAUBT if t not in gesehen)
        self.assertEqual([], verwaist,
                         "Diese Ausnahmen betreffen keine Stelle mehr: %s"
                         % verwaist)

    def test_die_fortschrittsanzeige_hat_keine_deutschen_vorgaben(self):
        """``begin_prepare``/``begin_payload`` hatten deutsche Vorgabewerte.

        Die Klasse hat keinen Uebersetzer; wer die Beschreibung wegliess,
        bekam "Vorbereitung..." bzw. "Verarbeite..." in die Statuszeile -
        auch auf Englisch. Jetzt gibt es keine Vorgabe mehr.
        """
        baum = ast.parse(_quelltext())
        schlecht = []
        for name in ("begin_prepare", "begin_payload"):
            knoten = next(k for k in ast.walk(baum)
                          if isinstance(k, ast.FunctionDef) and k.name == name)
            for arg, vorgabe in zip(
                    knoten.args.args[-len(knoten.args.defaults):] if knoten.args.defaults else [],
                    knoten.args.defaults):
                if arg.arg != "description":
                    continue
                if isinstance(vorgabe, ast.Constant):
                    schlecht.append("%s(description=%r)" % (name, vorgabe.value))
        self.assertEqual([], schlecht,
                         "Vorgabewert fuer eine sichtbare Beschriftung: %s"
                         % schlecht)


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

    #: Funktionen aus ``shadowmount_generation``, deren Rueckgabe im Fenster
    #: von Aufgabe 7 steht. ``ablageordner``, ``suchreihenfolge``,
    #: ``rangfolge`` und ``cache_pfad`` stehen bewusst NICHT dabei: Sie
    #: liefern Pfade und Schluesselnamen, keine Prosa.
    SMGEN_MIT_PROSA = ("profil", "ablageziel", "generation_erkennen",
                       "stolperfallen")

    #: Felder von ``profil()``, die keine Prosa tragen. Wer nur eines davon
    #: liest, braucht keine Vorlagen - und soll sie auch nicht anfordern:
    #: ``_smgen_texte()`` baut einunddreissig Uebersetzungen auf.
    PROFIL_OHNE_PROSA = ("config_schluessel", "spiel_ordner",
                         "backport_ordner", "orte", "hat_cache", "hat_emus",
                         "kennung", "spiel_fakelib2_wirkt",
                         "backport_erlaubt", "stapelt_schichten",
                         "log_marken")

    def test_shadowmount_generation_bekommt_ueberall_texte(self):
        baum = ast.parse(_quelltext())
        # Welche Aufrufe direkt in ein Feld ohne Prosa greifen?
        harmlos = set()
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Subscript):
                continue
            innen = knoten.value
            if not (isinstance(innen, ast.Call)
                    and getattr(innen.func, "attr", "") == "profil"):
                continue
            schluessel = knoten.slice
            if isinstance(schluessel, ast.Constant) \
                    and schluessel.value in self.PROFIL_OHNE_PROSA:
                harmlos.add((innen.lineno, innen.col_offset))

        ohne = []
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            if getattr(knoten.func, "attr", "") not in self.SMGEN_MIT_PROSA:
                continue
            # Nur die Aufrufe am Modul, nicht gleichnamige Methoden.
            wert = getattr(knoten.func, "value", None)
            if getattr(wert, "id", "") not in ("sm_gen", "shadowmount_generation"):
                continue
            if (knoten.lineno, knoten.col_offset) in harmlos:
                continue
            if not any(w.arg == "texte" for w in knoten.keywords):
                ohne.append((knoten.lineno, knoten.func.attr))
        self.assertEqual([], ohne,
                         "Diese Aufrufe bekommen keine Textvorlagen: %s - "
                         "dort faellt die deutsche Vorgabe des Moduls durch."
                         % ohne)

    def test_die_ausnahme_gilt_nur_fuer_felder_ohne_prosa(self):
        """Gegenprobe zur Ausnahme darueber: ``gilt_fuer`` steht nicht drin.

        Sonst waere die Ausnahme eine Hintertuer - ein Aufruf
        ``profil(g)["gilt_fuer"]`` ohne Vorlagen kaeme durch, und genau der
        ist das Leck.
        """
        from ps5_validator.utils import shadowmount_generation as sm_gen
        prosa = ("gilt_fuer", "nicht_fuer")
        for feld in prosa:
            self.assertNotIn(feld, self.PROFIL_OHNE_PROSA)
            self.assertIn(feld, sm_gen.GENERATIONEN[sm_gen.ALT])

    def test_der_unvollstaendig_bericht_bekommt_texte(self):
        baum = ast.parse(_quelltext())
        aufrufe = [k for k in ast.walk(baum)
                   if isinstance(k, ast.Call)
                   and getattr(k.func, "id", "") == "diagnose_incomplete_extraction"]
        self.assertEqual(1, len(aufrufe), "Aufrufstelle verschwunden?")
        self.assertTrue(any(w.arg == "texte" for w in aufrufe[0].keywords),
                        "Der Bericht ueber einen unvollstaendigen Dump kommt "
                        "wieder fest deutsch aus dem Modul.")

    #: Aufrufe im Hauptprogramm, die ihre Vorlagen mitbringen muessen -
    #: Name der gerufenen Funktion und wie oft sie vorkommt. Die Zahl steht
    #: dabei, damit eine geloeschte Aufrufstelle auffaellt statt still
    #: durchzugehen.
    MIT_VORLAGEN = (
        ("read_self", 1),
        ("abbild_pruefen", 1),
        ("senden", 1),
        ("datei_verarbeiten", 2),
        ("pruefen", 2),            # app_install und prosperopkg
        ("bauen", 1),
        ("homebrew_bauen", 1),
        ("zusammenfassung", 1),    # param_check.Befund
        ("herunterfahren", 1),     # ueber _system_herunterfahren
    )

    def test_die_elf_helfermodule_bekommen_ueberall_vorlagen(self):
        """Jede Aufrufstelle der dritten Welle reicht texte= herein."""
        baum = ast.parse(_quelltext())
        gefunden: dict[str, list[int]] = {}
        ohne: list[tuple[int, str]] = []
        gesucht = {name for name, _ in self.MIT_VORLAGEN}
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            name = (getattr(knoten.func, "attr", None)
                    or getattr(knoten.func, "id", None) or "")
            if name == "_system_herunterfahren":
                name = "herunterfahren"
            if name not in gesucht:
                continue
            # Nur die Aufrufe, die wirklich zu einem Helfermodul gehen -
            # gleichnamige eigene Methoden zaehlen nicht.
            wert = getattr(knoten.func, "value", None)
            am_modul = getattr(wert, "id", "") in (
                "ps4_werkzeug", "payload_versand", "prosperopkg",
                "ps5_backport", "app_install", "param_check", "befund")
            frei = isinstance(knoten.func, ast.Name)
            if not (am_modul or frei):
                continue
            gefunden.setdefault(name, []).append(knoten.lineno)
            if not any(w.arg == "texte" for w in knoten.keywords):
                ohne.append((knoten.lineno, name))
        self.assertEqual([], ohne,
                         "Diese Aufrufe bekommen keine Textvorlagen: %s" % ohne)
        for name, anzahl in self.MIT_VORLAGEN:
            with self.subTest(funktion=name):
                self.assertEqual(anzahl, len(gefunden.get(name, [])),
                                 "%s: %d Aufrufstellen erwartet, %s gefunden"
                                 % (name, anzahl, gefunden.get(name, [])))


class VorlagenHabenSchluesselTests(unittest.TestCase):
    """Jede Kennung eines Helfers braucht ihren Eintrag in STRINGS.

    Die Oberflaeche baut ihre Vorlagen als Schleife ueber das MELDUNGEN-dict
    des Moduls (``_smgen_texte``, ``_pkg_merger_texte``,
    ``_diagnose_incomplete_texte``). Fehlt zu einer Kennung der Schluessel,
    liefert ``translate`` den Schluesselnamen zurueck - und der steht dann
    im Fenster. Das faellt sonst erst dem Anwender auf.
    """

    def _pruefe(self, meldungen: dict, praefix: str) -> None:
        fehlend = [k for k in meldungen if praefix + k not in STRINGS]
        self.assertEqual([], fehlend,
                         "Ohne Schluessel (%s): %s" % (praefix, fehlend))
        halb = [k for k in meldungen
                if not STRINGS[praefix + k].get("de")
                or not STRINGS[praefix + k].get("en")]
        self.assertEqual([], halb, "Nur in einer Sprache: %s" % halb)

    #: Jedes Helfermodul mit Vorlagenmuster und der Praefix seiner
    #: Schluessel. Wer ein weiteres Modul umstellt, traegt es hier ein -
    #: dann prueft der Waechter es mit.
    MODULE = (
        ("ps5_validator.utils.shadowmount_generation", "MELDUNGEN", "smgen."),
        ("ps5_validator.utils.pkg_merger", "MELDUNGEN", "pkg_merger.log_"),
        ("ps5_validator.diagnose_incomplete", "MELDUNGEN", "diagnose.incomplete_"),
        ("ps5_validator.utils.self_reader", "MELDUNGEN", "self_reader."),
        ("ps5_validator.utils.ps4_werkzeug", "MELDUNGEN", "ps4werkzeug."),
        ("ps5_validator.utils.payload_versand", "MELDUNGEN", "payloadmod."),
        ("ps5_validator.utils.prosperopkg", "MELDUNGEN", "prosperopkg."),
        ("ps5_validator.utils.ps5_backport", "MELDUNGEN", "backportmod."),
        ("ps5_validator.utils.param_check", "MELDUNGEN", "paramcheck."),
        ("ps5_validator.utils.app_install", "MELDUNGEN", "appinstallmod."),
        ("ps5_validator.utils.anzeige_diagnose", "MELDUNGEN", "anzeige."),
        ("ps5_validator.utils.plattform", "OEFFNEN_MELDUNGEN", "oeffnen."),
        ("ps5_validator.utils.plattform", "HERUNTERFAHR_MELDUNGEN",
         "shutdown.reason_"),
    )

    def test_jedes_modul_hat_seine_schluessel(self):
        import importlib
        for modulname, dictname, praefix in self.MODULE:
            with self.subTest(modul=modulname, dict=dictname):
                modul = importlib.import_module(modulname)
                self._pruefe(getattr(modul, dictname), praefix)

    #: Je Modul eine Kennung, mit der sich messen laesst, ob die
    #: uebergebenen Vorlagen wirklich benutzt werden - samt der
    #: Platzhalterwerte, die sie braucht. Ein Modul, das ``texte``
    #: entgegennimmt und dann doch seine eingebauten Saetze nimmt, faellt
    #: sonst nicht auf: Schluessel vorhanden, beide Sprachen gefuellt, und
    #: im Fenster steht trotzdem Deutsch. Genau so ist am 06.09.2026 eine
    #: Gegenprobe durchgekommen.
    PROBEN = (
        ("ps5_validator.utils.self_reader", "_satz", "self_reader.",
         "zu_kurz", {"pfad": "x.bin"}),
        ("ps5_validator.utils.ps4_werkzeug", "_satz", "ps4werkzeug.",
         "innenebene_unlesbar", {}),
        ("ps5_validator.utils.payload_versand", "_satz", "payloadmod.",
         "nichts_erreichbar", {"elfldr": 9021, "pldmgr": 8084}),
        ("ps5_validator.utils.prosperopkg", "_satz", "prosperopkg.",
         "nicht_gefunden", {"ordner": "tools", "plattform": "win"}),
        ("ps5_validator.utils.ps5_backport", "_satz", "backportmod.",
         "kein_elf_kein_self", {}),
        ("ps5_validator.utils.param_check", "_satz", "paramcheck.",
         "param_fehlt", {}),
        ("ps5_validator.utils.app_install", "_satz", "appinstallmod.",
         "param_json_fehlt", {}),
        ("ps5_validator.utils.anzeige_diagnose", "_satz", "anzeige.",
         "darstellung_sauber", {}),
        ("ps5_validator.utils.plattform", "_herunterfahr_satz",
         "shutdown.reason_", "kein_befehl", {}),
        ("ps5_validator.utils.shadowmount_generation", "_satz", "smgen.",
         "falle_common_lib", {}),
        ("ps5_validator.utils.pkg_merger", "_text", "pkg_merger.log_",
         "kein_fih_kopf", {}),
    )

    def test_jedes_modul_benutzt_die_vorlagen_auch(self):
        """Gemessen, nicht am Schluesselbestand abgelesen."""
        import importlib
        for modulname, helfer, praefix, kennung, werte in self.PROBEN:
            with self.subTest(modul=modulname):
                modul = importlib.import_module(modulname)
                satz = getattr(modul, helfer)
                englisch = {kennung: translate("en", praefix + kennung)}
                heraus = satz(englisch, kennung, **werte)
                erwartet = translate("en", praefix + kennung).format(**werte)
                self.assertEqual(erwartet, heraus,
                                 "%s benutzt die uebergebene Vorlage nicht."
                                 % modulname)
                # Gegenprobe im selben Atemzug: ohne Vorlagen der deutsche Satz.
                self.assertNotEqual(erwartet, satz(None, kennung, **werte),
                                    "%s liefert auf Deutsch dasselbe wie auf "
                                    "Englisch - taugt als Probe nicht."
                                    % modulname)

    def test_der_diagnosebericht_reicht_die_vorlagen_weiter(self):
        """``diagnose_befund`` ruft ``anzeige_diagnose.zusammenfassung``.

        Es hat seinen Uebersetzer selbst (``text=`` im Erzeuger) und muss
        die Vorlagen daraus bauen. Tut es das nicht, steht die Kopfzeile des
        Diagnoseberichts deutsch in einem englischen Fenster.
        """
        with io.open(os.path.join(PROJEKT, "ps5_validator", "utils",
                                  "diagnose_befund.py"), "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        aufrufe = [k for k in ast.walk(baum)
                   if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "zusammenfassung"]
        self.assertEqual(1, len(aufrufe), "Aufrufstelle verschwunden?")
        self.assertTrue(any(w.arg == "texte" for w in aufrufe[0].keywords),
                        "Die Kopfzeile des Diagnoseberichts kommt wieder "
                        "fest deutsch aus anzeige_diagnose.")

    def test_kein_deutscher_satz_mehr_in_einem_dict_der_oberflaeche(self):
        """Die Klasse, die dem Rundumschlag entgeht.

        Er sieht nur, was direkt an einer sichtbaren Stelle übergeben wird.
        Steht der Satz in einem dict und wird von dort geholt, findet er
        ihn nicht - so blieben die Stufen eines unterbrochenen Laufs und
        die Kurzhinweise der Aufgabenknöpfe bis zuletzt liegen.

        Deshalb hier die Gegenrichtung: gar keine deutschen Sätze mehr in
        dict-Literalen des Hauptprogramms, mit begründeten Ausnahmen.
        """
        baum = ast.parse(_quelltext())
        doks = set()
        for knoten in ast.walk(baum):
            if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef, ast.Module)):
                text = ast.get_docstring(knoten, clean=False)
                if text:
                    doks.add(text)
        gefunden = []
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Dict):
                continue
            for wert in knoten.values:
                if not (isinstance(wert, ast.Constant)
                        and isinstance(wert.value, str)):
                    continue
                text = wert.value
                if len(text) < 8 or text in doks or text in STRINGS:
                    continue
                if text in self.DICTS_ERLAUBT or not DEUTSCH.search(text):
                    continue
                gefunden.append((wert.lineno, text[:80]))
        self.assertEqual([], sorted(gefunden),
                         "Deutsche Sätze in einem dict: %s" % sorted(gefunden))

    #: dict-Werte, die deutsch bleiben dürfen - mit Begründung.
    DICTS_ERLAUBT = {
        "eine benötigte DLL fehlt":
            "Nur --doktor gibt das aus, und der ist bewusst deutsch.",
        "ein Einsprungpunkt fehlt (falsche DLL-Fassung)": "Dasselbe.",
        "falsches Format (32 gegen 64 Bit)": "Dasselbe.",
        "Dump-Ordner":
            "_FORMAT_LABELS ist die Schlüsselliste; angezeigt wird "
            "self._t('format.folder').",
        ".ffpfs (unkomprimiert)": "Dasselbe.",
    }

    def test_die_dict_ausnahmen_sind_nicht_veraltet(self):
        quelle = _quelltext()
        verwaist = sorted(t for t in self.DICTS_ERLAUBT if t not in quelle)
        self.assertEqual([], verwaist,
                         "Diese Ausnahmen betreffen keine Stelle mehr: %s"
                         % verwaist)

    def test_die_kurzhinweise_der_aufgabenknoepfe(self):
        gui = G.__new__(G)
        gui._t = lambda s, **w: translate("en", s, **w)
        for modus in G._MODE_TOOLTIPS:
            with self.subTest(aufgabe=modus):
                schluessel = "mode_tooltip." + modus
                self.assertIn(schluessel, STRINGS)
                self.assertNotEqual(STRINGS[schluessel]["de"],
                                    STRINGS[schluessel]["en"])

    def test_die_stufen_eines_unterbrochenen_laufs(self):
        """Zweiundzwanzig Sätze im Fenster "Fortsetzen?".

        Sie standen in einem dict und entgingen dem Rundumschlag dadurch:
        Er sieht nur, was direkt an einer sichtbaren Stelle uebergeben wird.
        """
        fehlend = [k for k in G._CHECKPOINT_STAGES
                   if "checkpoint.stage_" + k not in STRINGS]
        self.assertEqual([], fehlend, "Ohne Schluessel: %s" % fehlend)
        gui = G.__new__(G)
        gui._t = lambda s, **w: translate("en", s, **w)
        for kennung in G._CHECKPOINT_STAGES:
            with self.subTest(stufe=kennung):
                heraus = gui._checkpoint_stage_label(kennung)
                self.assertEqual(STRINGS["checkpoint.stage_" + kennung]["en"],
                                 heraus)
        self.assertEqual("-", gui._checkpoint_stage_label(""))
        self.assertEqual("aus_einer_alten_fassung",
                         gui._checkpoint_stage_label("aus_einer_alten_fassung"))

    def test_die_beschreibungen_der_param_schluessel(self):
        """Siebenunddreissig Kurzbeschreibungen im PARAM/MANIFEST-Fenster."""
        from ps5_validator.utils.param_manifest import (
            MANIFEST_KNOWN_KEYS, PARAM_KNOWN_KEYS)
        fehlend = [k for d in (PARAM_KNOWN_KEYS, MANIFEST_KNOWN_KEYS)
                   for k in d if "param_manifest.key_" + k not in STRINGS]
        self.assertEqual([], fehlend, "Ohne Schluessel: %s" % fehlend)

    #: Eintraege, die in beiden Sprachen zu Recht gleich lauten. Bisher
    #: genau einer: eine Erfolgszeile aus Zeichen, Namen und Pruefsumme.
    GLEICH_ERLAUBT = {
        "pkg_merger.log_ok": "Nur Symbole, Dateiname, Groesse und SHA-256.",
        "anzeige.darstellung_anzahl":
            "'{anzahl} x {schwere}' - was hier zu uebersetzen waere, steckt "
            "in den Platzhaltern (anzeige.schwere_*).",
        "paramcheck.param_befunde":
            "'param.json: {teile}' - ein Dateiname und ein Platzhalter.",
        "shutdown.reason_fehlgeschlagen":
            "'{befehl}: {grund}' - reine Formatzeile, beide Teile kommen "
            "von aussen.",
    }

    def test_die_englische_fassung_ist_nicht_die_deutsche(self):
        """Ein kopierter deutscher Satz im ``en``-Feld faellt sonst nicht auf.

        Der Schluessel ist dann vorhanden, beide Sprachen sind gefuellt -
        und im englischen Fenster steht trotzdem Deutsch. Genau so hat eine
        Gegenprobe am 06.09.2026 den Waechter ausgehebelt.
        """
        praefixe = ("smgen.", "pkg_merger.log_", "diagnose.incomplete_",
                    "preflight.", "conversion.", "srccheck.", "progress.",
                    "verify.", "werkzeuge.", "self_reader.", "ps4werkzeug.",
                    "payloadmod.", "prosperopkg.", "backportmod.",
                    "paramcheck.", "appinstallmod.", "anzeige.",
                    "shutdown.reason_", "param_manifest.key_")
        gleich = [k for k, v in STRINGS.items()
                  if k.startswith(praefixe)
                  and v.get("de") == v.get("en")
                  and k not in self.GLEICH_ERLAUBT]
        self.assertEqual([], gleich,
                         "In diesen Eintraegen steht auf Englisch dasselbe "
                         "wie auf Deutsch: %s" % gleich)

    def test_die_vorlagen_kommen_wirklich_uebersetzt_an(self):
        """Gemessen: dieselbe Auskunft auf Deutsch und auf Englisch."""
        from ps5_validator.utils import shadowmount_generation as sm_gen
        fassungen = {}
        for sprache in ("de", "en"):
            texte = {k: translate(sprache, "smgen." + k)
                     for k in sm_gen.MELDUNGEN}
            fassungen[sprache] = (
                sm_gen.profil(sm_gen.NEU, texte=texte)["gilt_fuer"],
                sm_gen.ablageziel(sm_gen.NEU, sm_gen.ORT_SPIEL,
                                  wurzel="/data/x", texte=texte)["hinweis"],
                sm_gen.stolperfallen(sm_gen.NEU, texte=texte)[0],
            )
        for deutsch, englisch in zip(fassungen["de"], fassungen["en"]):
            self.assertTrue(deutsch and englisch)
            self.assertNotEqual(deutsch, englisch,
                                "Auf Englisch steht dasselbe wie auf "
                                "Deutsch: %r" % deutsch[:60])

    def test_der_unvollstaendig_bericht_kommt_uebersetzt_an(self):
        """Auch hier gemessen, nicht nur der Schluesselbestand geprueft.

        Ohne diese Pruefung faellt es nicht auf, wenn das Modul die
        uebergebenen Vorlagen ignoriert und seine eingebauten Saetze nimmt -
        eine Gegenprobe am 06.09.2026 ist genau so durchgekommen.
        """
        from ps5_validator.diagnose_incomplete import (
            diagnose_incomplete_extraction, MELDUNGEN)
        berichte = {}
        for sprache in ("de", "en"):
            texte = {k: translate(sprache, "diagnose.incomplete_" + k)
                     for k in MELDUNGEN}
            berichte[sprache] = diagnose_incomplete_extraction(PROJEKT,
                                                               texte=texte)
        self.assertIn(STRINGS["diagnose.incomplete_kopfzeile"]["en"],
                      berichte["en"],
                      "Der Bericht ignoriert die uebergebenen Vorlagen.")
        self.assertNotIn(STRINGS["diagnose.incomplete_kopfzeile"]["de"],
                         berichte["en"])
        for satz in ("ursache", "loesungen", "weitere_infos"):
            self.assertIn(STRINGS["diagnose.incomplete_" + satz]["en"],
                          berichte["en"], satz)


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
