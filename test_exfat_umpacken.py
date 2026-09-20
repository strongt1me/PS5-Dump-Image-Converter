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


class WegIstErreichbarTests(unittest.TestCase):
    """Die Sperre gibt genau dann nach, wenn ein Asset-Pack gebaut wird."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def _probe(self, mit_pack: bool):
        haupt = self.haupt

        class _Probe:
            pass

        p = _Probe()
        p._t = lambda s, **w: s
        for name in ("_SELBSTZIEL_MIT_ASSETPACK", "_SAME_FORMAT_ALLOWED",
                     "_MODE_TARGET_OPTIONS", "_UNSUPPORTED_TARGET_HINTS"):
            setattr(p, name, getattr(haupt.PS5ConverterGUI, name))
        p._selbstziel_erlaubt = lambda: mit_pack
        p._detect_source_format = lambda _pfad: ""
        p._conversion_block_reason = (
            haupt.PS5ConverterGUI._conversion_block_reason.__get__(p))
        return p

    def test_exfat_zu_exfat_nur_mit_assetpack(self):
        frei = self._probe(mit_pack=True)
        self.assertEqual(
            frei._conversion_block_reason("exfat", "exfat",
                                          mode="universal_convert"), "")
        gesperrt = self._probe(mit_pack=False)
        self.assertEqual(
            gesperrt._conversion_block_reason("exfat", "exfat",
                                              mode="universal_convert"),
            "conversion.same_format",
            "Ohne Asset-Pack waere der Lauf eine Kopie derselben Datei.")

    def test_der_ffpfsc_weg_bleibt_wie_er_war(self):
        """Die Umbenennung darf den Weg von v1.9.20 nicht mitnehmen."""
        frei = self._probe(mit_pack=True)
        self.assertEqual(
            frei._conversion_block_reason("ffpfsc", "ffpfsc",
                                          mode="unpack_to_exfat"), "")
        gesperrt = self._probe(mit_pack=False)
        self.assertNotEqual(
            gesperrt._conversion_block_reason("ffpfsc", "ffpfsc",
                                              mode="unpack_to_exfat"), "")

    def test_in_der_falschen_aufgabe_bleibt_es_gesperrt(self):
        """Aufgabe 2 ist für .ffpfsc da, nicht für exFAT."""
        frei = self._probe(mit_pack=True)
        self.assertEqual(
            frei._conversion_block_reason("exfat", "exfat",
                                          mode="unpack_to_exfat"),
            "conversion.same_format")

    def test_aufgabe_sechs_kann_alle_drei(self):
        """„Die Aufgabe für alle Fälle" ließ zwei von drei Formaten nicht zu.

        Am 20.09.2026 beim Durchzählen aufgefallen: Die Wege für
        ``ffpfsc -> ffpfsc`` und ``ffpkg -> ffpkg`` liegen längst in
        ``_execute_conversion_by_type``; nur die Sperre stand davor. In
        Aufgabe 4 ging dieselbe ``.ffpkg``-Umwandlung anstandslos.
        """
        frei = self._probe(mit_pack=True)
        for fmt in ("ffpfsc", "exfat", "ffpkg"):
            self.assertEqual(
                frei._conversion_block_reason(fmt, fmt,
                                              mode="universal_convert"), "",
                "Aufgabe 6 sperrt %s -> %s" % (fmt, fmt))

    def test_ohne_pack_bleibt_nur_die_ffpkg_neuvalidierung(self):
        """.ffpkg wird bewusst neu aufgebaut - das ist auch ohne Pack sinnvoll.

        Für .ffpfsc und .exFAT wäre ein Selbst-Ziel ohne Pack dagegen nur
        eine Kopie derselben Datei.
        """
        ohne = self._probe(mit_pack=False)
        self.assertEqual(
            ohne._conversion_block_reason("ffpkg", "ffpkg",
                                          mode="universal_convert"), "")
        for fmt in ("ffpfsc", "exfat"):
            self.assertEqual(
                ohne._conversion_block_reason(fmt, fmt,
                                              mode="universal_convert"),
                "conversion.same_format", fmt)

    def test_die_tabelle_nennt_alle_faelle(self):
        G = self.haupt.PS5ConverterGUI
        for eintrag in (("unpack_to_exfat", "ffpfsc"),
                        ("universal_convert", "exfat"),
                        ("universal_convert", "ffpfsc")):
            self.assertIn(eintrag, G._SELBSTZIEL_MIT_ASSETPACK, str(eintrag))
        # .ffpkg braucht keinen Pack - es wird ohnehin neu aufgebaut.
        self.assertIn("ffpkg", G._SAME_FORMAT_ALLOWED["ffpkg_to_ffpfsc"])
        self.assertIn("ffpkg", G._SAME_FORMAT_ALLOWED["universal_convert"])

    def test_zu_jedem_freigegebenen_selbstziel_gibt_es_einen_weg(self):
        """Eine Freigabe ohne Weg wäre der Fehler von v1.9.20 bis v1.9.24.

        Damals bot die Liste ``ffpfsc -> ffpfsc`` an, und starten ließ es
        sich nie.
        """
        import ast

        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        weiche = next(k for k in ast.walk(ast.parse(quelle))
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_execute_conversion_by_type")
        text = ast.unparse(weiche)
        for fmt in ("ffpfsc", "exfat", "ffpkg"):
            self.assertIn(
                "source_type == '%s' and target_type == '%s'" % (fmt, fmt),
                text, "Kein Zweig fuer %s -> %s" % (fmt, fmt))

    def test_aufgabe_sechs_bietet_exfat_als_quelle_und_ziel(self):
        """Sonst waere die Freigabe unerreichbar."""
        G = self.haupt.PS5ConverterGUI
        self.assertIn("exfat", G._MODE_SOURCE_TYPES["universal_convert"])
        self.assertIn("exfat", G._MODE_TARGET_OPTIONS["universal_convert"])


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
