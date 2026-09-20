# -*- coding: utf-8 -*-
"""Aufgabe 7 baut ein Asset-Pack — aber nur auf Knopfdruck.

Gewünscht vom Nutzer (20.09.2026): *"Aufgabe 7 sollte ebenfalls AMPR EMU
Asset Pack in die Backups (alle Formate) integrieren können. Kannst du
dafür ein Knopf erstellen und die Funktion so bauen?"*

**Die Vorgeschichte gehört dazu.** Am 17.09.2026 wurde genau das aus
Aufgabe 7 wieder ausgebaut — auf Entscheidung desselben Nutzers. Der Grund
steht im Quelltext: Damals baute die Aufgabe **nach jedem Eingriff**
Bänder, und ein „Asset-Pack entfernen" löschte Manifest und Bänder in der
Annahme, die Originale lägen daneben. Seit gepackte Originale weggelassen
werden können, stimmt das nicht mehr — ohne sie hätte der Rückweg die
Spieldaten gelöscht.

Der Unterschied jetzt ist genau der, an dem es scheiterte:

* Gebaut wird **nur** auf ausdrücklichen Knopfdruck, nie nebenbei nach
  einer anderen Aktion.
* Ein „Asset-Pack entfernen" gibt es weiterhin **nicht**.

Dazu kommt die Bedingung aus der Nutzerentscheidung „Option 1": Gebaut
wird mit der Fassung, die im Dialog **gewählt** ist. Ist sie nicht
pack-fähig, sagt der Dialog das sofort — nicht erst nach einer halben
Stunde Packen.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJEKT = Path(__file__).resolve().parent
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _quelle() -> str:
    return HAUPTDATEI.read_text(encoding="utf-8")


def _methode(name: str) -> ast.FunctionDef:
    baum = ast.parse(_quelle())
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
            return knoten
    raise AssertionError("Funktion %s gibt es nicht mehr" % name)


class KnopfTests(unittest.TestCase):
    """Der Knopf muss da sein - und in der Aktionsreihe stehen."""

    def test_der_knopf_steht_in_der_aktionsreihe(self):
        methode = _methode("_mode_ampr_manager")
        texte = [k.value for k in ast.walk(methode)
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        self.assertIn("ampr.btn_assetpack", texte,
                      "Der Knopf fehlt in Aufgabe 7.")
        # Er muss in derselben Reihe stehen wie die uebrigen Aktionen.
        quelle = ast.unparse(methode)
        self.assertIn("ampr.btn_index_only", quelle)
        self.assertLess(quelle.index("ampr.btn_index_only"),
                        quelle.index("ampr.btn_assetpack"),
                        "Der neue Knopf gehoert ans Ende der Reihe.")

    def test_die_aktion_wird_behandelt(self):
        quelle = ast.unparse(_methode("_mode_ampr_manager"))
        self.assertIn("ampr_assetpack", quelle)
        self.assertIn("_ampr_assetpakete_bauen", quelle,
                      "Die Aktion baut gar kein Pack.")

    def test_gebaut_wird_erst_nach_dem_index(self):
        """``ampr_pack.py`` liest den Index, um die fileIds zu vergeben.

        Ein danach neu gebauter Index macht die fertigen Bänder unbrauchbar
        (siehe ``_ampr_index_neubau_erlaubt``).
        """
        methode = _methode("_mode_ampr_manager")
        bauen = [k.lineno for k in ast.walk(methode)
                 if isinstance(k, ast.Call)
                 and isinstance(k.func, ast.Attribute)
                 and k.func.attr == "_ampr_assetpakete_bauen"]
        index = [k.lineno for k in ast.walk(methode)
                 if isinstance(k, ast.Call)
                 and isinstance(k.func, ast.Attribute)
                 and k.func.attr == "_build_ampr_index_local"]
        self.assertTrue(bauen, "Kein Aufruf von _ampr_assetpakete_bauen")
        self.assertTrue(index, "Kein Index-Aufbau in Aufgabe 7")
        self.assertLess(min(index), min(bauen),
                        "Das Pack entsteht vor dem Index - die fileIds "
                        "passen dann nicht.")

    def test_ohne_index_wird_abgebrochen(self):
        """Lieber ein klarer Satz als Bänder mit falschen fileIds.

        Auch hier die Struktur statt des Textes: Die Meldung allein steht
        auch dann noch im Quelltext, wenn der Riegel davor ausgebaut ist.
        """
        methode = _methode("_mode_ampr_manager")
        treffer = []
        for k in ast.walk(methode):
            if not isinstance(k, ast.If):
                continue
            # `if not <etwas>.is_file():` mit einer Meldung darunter
            if not (isinstance(k.test, ast.UnaryOp)
                    and isinstance(k.test.op, ast.Not)):
                continue
            innen = k.test.operand
            if not (isinstance(innen, ast.Call)
                    and isinstance(innen.func, ast.Attribute)
                    and innen.func.attr == "is_file"):
                continue
            rumpf = " ".join(ast.unparse(s) for s in k.body)
            if "ampr.assetpack_ohne_index" in rumpf and "return False" in rumpf:
                treffer.append(k.lineno)
        self.assertTrue(
            treffer,
            "Kein Riegel `if not <index>.is_file(): melden; return False` - "
            "dann entstehen Baender mit fileIds aus einem fehlenden Index.")


class NurAufKnopfdruckTests(unittest.TestCase):
    """Der Punkt, an dem es am 17.09.2026 scheiterte."""

    def test_kein_automatismus_nach_anderen_aktionen(self):
        """Gebaut wird nur, wenn die Aktion genau das ist.

        Früher baute der Block nach **jedem** Eingriff neue Bänder.

        Geprüft wird die **Struktur**, nicht der Text: Die erste Fassung
        dieser Prüfung suchte "ampr_assetpack" in den Bedingungen und
        fand es auch dann noch, wenn die Aktionsprüfung entfernt war —
        denn der Name steht als Argument in ``spec.get('ampr_assetpack')``.
        Die Gegenprobe blieb dadurch grün.
        """
        methode = _methode("_mode_ampr_manager")
        rufe = [k for k in ast.walk(methode)
                if isinstance(k, ast.Call)
                and isinstance(k.func, ast.Attribute)
                and k.func.attr == "_ampr_assetpakete_bauen"]
        self.assertTrue(rufe, "Kein Aufruf von _ampr_assetpakete_bauen")

        def _prueft_die_aktion(test: ast.expr) -> bool:
            """Ist das ein Vergleich `action == "ampr_assetpack"`?"""
            for k in ast.walk(test):
                if not isinstance(k, ast.Compare):
                    continue
                if not (isinstance(k.left, ast.Name) and k.left.id == "action"):
                    continue
                for op, rechts in zip(k.ops, k.comparators):
                    if (isinstance(op, ast.Eq)
                            and isinstance(rechts, ast.Constant)
                            and rechts.value == "ampr_assetpack"):
                        return True
            return False

        for knoten in rufe:
            eltern = [k for k in ast.walk(methode)
                      if isinstance(k, ast.If)
                      and knoten in list(ast.walk(k))]
            self.assertTrue(
                any(_prueft_die_aktion(k.test) for k in eltern),
                "Das Pack entsteht ohne Vergleich action == 'ampr_assetpack' - "
                "dann baut jeder Eingriff wieder Baender.")

    def test_es_gibt_weiterhin_kein_entfernen(self):
        """„Asset-Pack entfernen" war der gefährliche Teil.

        Ohne Originale neben den Bändern wäre das der Weg, die Spieldaten
        zu löschen.
        """
        quelle = _quelle()
        for verboten in ("ampr_assetpack_remove", "ampr.btn_assetpack_remove",
                         "assetpack_entfernen"):
            self.assertNotIn(verboten, quelle, verboten)


class FassungTests(unittest.TestCase):
    """Option 1 des Nutzers: die **gewählte** Fassung, mit Meckern."""

    def test_die_variante_wird_geprueft(self):
        quelle = ast.unparse(_methode("_mode_ampr_manager"))
        self.assertIn("variante_kann_packen", quelle,
                      "Eine Fassung ohne Pack-Unterstuetzung wuerde Baender "
                      "schreiben, die niemand liest.")
        self.assertIn("ampr.assetpack_variante_kann_nicht", quelle)

    def test_geprueft_wird_im_dialog_und_beim_lauf(self):
        """Im Dialog sofort sichtbar, im Lauf als Riegel.

        Der Dialog kann übersprungen werden (Automatik in Prüfungen), der
        Lauf nicht.
        """
        quelle = ast.unparse(_methode("_mode_ampr_manager"))
        self.assertEqual(
            2, quelle.count("variante_kann_packen"),
            "Erwartet: einmal im Dialog (sofortige Rueckmeldung), einmal "
            "im Lauf (Riegel).")

    def test_das_werkzeug_wird_geprueft(self):
        quelle = ast.unparse(_methode("_mode_ampr_manager"))
        self.assertIn("einsatzbereit", quelle)
        self.assertIn("ampr.assetpack_werkzeug_fehlt", quelle)

    def test_die_texte_gibt_es_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("ampr.btn_assetpack", "progress.prepare.assetpack",
                           "ampr.assetpack_keine_fassung",
                           "ampr.assetpack_variante_kann_nicht",
                           "ampr.assetpack_werkzeug_fehlt",
                           "ampr.assetpack_ohne_index"):
            eintrag = STRINGS[schluessel]
            self.assertIn("de", eintrag, schluessel)
            self.assertIn("en", eintrag, schluessel)


class AlleFormateTests(unittest.TestCase):
    """„in die Backups (alle Formate)" — Aufgabe 7 nimmt alle vier."""

    def test_aufgabe_sieben_nimmt_alle_vier_quellen(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
        modul = sys.modules.get("hauptprogramm")
        if modul is None:
            modul = importlib.util.module_from_spec(spec)
            sys.modules["hauptprogramm"] = modul
            spec.loader.exec_module(modul)
        quellen = modul.PS5ConverterGUI._MODE_SOURCE_TYPES["ampr_manager"]
        for art in ("folder", "ffpfsc", "exfat", "ffpkg"):
            self.assertIn(art, quellen, art)

    def test_container_werden_zurueckgepackt(self):
        """Sonst bliebe das Pack im Temp-Ordner liegen."""
        quelle = ast.unparse(_methode("_mode_ampr_manager"))
        self.assertIn("_repack_nested_ffpfsc", quelle)
        self.assertIn("is_container", quelle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
