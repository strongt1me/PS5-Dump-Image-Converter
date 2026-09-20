# -*- coding: utf-8 -*-
"""Waechter fuer die Werkzeugpflege (17.09.2026).

Anlass: Am 17.09.2026 fielen beim Nachsehen drei Abweichungen auf, die seit
Monaten niemandem aufgefallen waren - die Lizenzdatei nannte eine falsche
Fassung von PS5Upload, eine ShadowMount+-Bezeichnung, die es beim Autor nie
gab, und fuenf Nutzlasten fehlten dort ganz. Seitdem vergleicht der
Diagnosebericht Ordner und Lizenzdatei bei jedem Lauf.

Gemessen wird an echten Dateien in einem Wegwerfordner und an einer
mitgelieferten Liste - **nie am Netz**: Ein Testlauf darf nicht davon
abhaengen, ob GitHub gerade erreichbar ist, und soll auch nichts dorthin
schicken.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("werkzeugstaende")

from ps5_validator.utils import werkzeugstaende as ws       # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

#: Ein Ausschnitt der oeffentlichen Liste, wie sie am 17.09.2026 aussah.
LISTE = [
    {"name": "ftpsrv", "filename": "ftpsrv-ps5_v0.21.1.elf", "version": "v0.21.1",
     "source": "https://github.com/ps5-payload-dev/ftpsrv/releases"},
    {"name": "kstuff-lite", "filename": "kstuff_lite_v1.10.elf", "version": "v1.10",
     "source": "https://github.com/EchoStretch/kstuff-lite/releases"},
    {"name": "ShadowMountPlus", "filename": "ShadowMountPlus_1.6beta16.zip",
     "version": "1.6beta16",
     "source": "https://github.com/drakmor/ShadowMountPlus/releases"},
    {"name": "ps5upload", "filename": "ps5upload_v5.28.0.elf", "version": "v5.28.0",
     "source": "https://github.com/phantomptr/ps5upload/releases"},
]


class FassungAusNamenTests(unittest.TestCase):
    """Die Fassung steht im Dateinamen - in mehreren Schreibweisen."""

    def test_uebliche_schreibweisen(self) -> None:
        for name, erwartet in (
                ("elfldr-ps5_v0.26.elf", "0.26"),
                ("ps5upload-5.28.0.elf", "5.28.0"),
                ("game-compressor_v1.0.4.elf", "1.0.4"),
                ("shadowmountplus_v1.7alpha13fix1.elf", "1.7alpha13fix1"),
                ("kstuff_lite_v1.2-dr_Beta2.elf", "1.2"),
                ("ProsperoMgr.elf", ""),
                ("", "")):
            with self.subTest(name=name):
                self.assertEqual(ws.fassung_aus_name(name), erwartet)


class KennungTests(unittest.TestCase):
    """Zwei Reihen mit aehnlichem Namen duerfen nicht zusammenfallen."""

    def test_eigene_reihen_bleiben_getrennt(self) -> None:
        self.assertNotEqual(ws.kennung_aus_name("kstuff_lite_v1.2-dr_Beta2.elf"),
                            ws.kennung_aus_name("kstuff_lite_v1.10_Beta.elf"))
        self.assertNotEqual(ws.kennung_aus_name("ftpsrv-ps5_v1.15-ng.elf"),
                            ws.kennung_aus_name("ftpsrv-ps5_v0.21.elf"))
        self.assertNotEqual(ws.kennung_aus_name("zftpd-ps5-zhttp-v1.5.0.elf"),
                            ws.kennung_aus_name("zftpd-ps5-v1.5.0.elf"))

    def test_beta_unterscheidet_nichts(self) -> None:
        self.assertEqual(ws.kennung_aus_name("kstuff_lite_v1.10_Beta.elf"),
                         ws.kennung_aus_name("kstuff_lite_v1.10.elf"))
        self.assertEqual(ws.kennung_aus_name("ps5-app-dumper_v1.11_Beta.elf"),
                         ws.kennung_aus_name("ps5-app-dumper_v1.11.elf"))

    def test_schreibweise_des_spiegels_trifft_unsere(self) -> None:
        for spiegel, unser in (("elfldr", "elfldr-ps5_v0.26.elf"),
                               ("ftpsrv", "ftpsrv-ps5_v0.21.elf"),
                               ("klogsrv", "klogsrv-ps5_v0.9.elf"),
                               ("websrv", "websrv-ps5_v0.34.elf"),
                               ("zftpd", "zftpd-ps5-v1.5.0.elf")):
            with self.subTest(spiegel=spiegel):
                self.assertEqual(ws.kennung_aus_name(spiegel),
                                 ws.kennung_aus_name(unser))


class VergleichTests(unittest.TestCase):
    """Nur eindeutige Faelle gelten - sonst wird nichts behauptet."""

    def test_zahlen_werden_als_zahlen_verglichen(self) -> None:
        self.assertEqual(ws.vergleiche("1.2", "1.10"), "aelter")
        self.assertEqual(ws.vergleiche("0.21", "0.21.1"), "aelter")
        self.assertEqual(ws.vergleiche("5.28.0", "5.28.0"), "gleich")
        self.assertEqual(ws.vergleiche("1.7alpha13fix1", "1.6beta16"), "neuer")

    def test_unvergleichbares_bleibt_unklar(self) -> None:
        self.assertEqual(ws.vergleiche("1.7alpha13", "1.7beta2"), "unklar")
        self.assertEqual(ws.vergleiche("", "1.0"), "unklar")
        self.assertEqual(ws.vergleiche("1.0", ""), "unklar")


class BestandAbgleichTests(unittest.TestCase):
    """Ordner gegen Lizenzdatei - an echten Dateien gemessen."""

    LIZENZ = (
        "# Lizenzen\n\n"
        "## Payloads im Ordner `helloworld/`\n\n"
        "| Datei | Projekt |\n| --- | --- |\n"
        "| `alpha_v1.0.elf` | Alpha |\n"
        "| `fehlt_v2.0.elf` | Fehlt im Ordner |\n\n"
        "## Verfahren, die nachgebaut wurden\n\n"
        "| **BestPig** | Starter `ps5-backpork.elf` |\n"
    )

    def _aufbau(self, basis: str) -> tuple[str, str]:
        ordner = os.path.join(basis, "helloworld")
        os.makedirs(ordner)
        for name in ("alpha_v1.0.elf", "ohne_zeile_v3.0.elf"):
            with open(os.path.join(ordner, name), "wb") as fh:
                fh.write(b"\x7fELF")
        lizenz = os.path.join(basis, "THIRD_PARTY_LICENSES.md")
        with open(lizenz, "w", encoding="utf-8") as fh:
            fh.write(self.LIZENZ)
        return ordner, lizenz

    def test_beide_richtungen_werden_gemeldet(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            ordner, lizenz = self._aufbau(basis)
            befund = ws.bestand_abgleichen(ordner, lizenz)
            self.assertEqual(befund["ohne_zeile"], ["ohne_zeile_v3.0.elf"])
            self.assertEqual(befund["ohne_datei"], ["fehlt_v2.0.elf"])

    def test_andere_abschnitte_zaehlen_nicht_mit(self) -> None:
        """``ps5-backpork.elf`` steht in der Danksagung und liegt woanders.

        Der erste Lauf am 17.09.2026 meldete genau diese Datei als fehlend.
        """
        with tempfile.TemporaryDirectory() as basis:
            _ordner, lizenz = self._aufbau(basis)
            self.assertNotIn("ps5-backpork.elf", ws.dokumentierte_dateien(lizenz))

    def test_ohne_abschnitt_wird_nichts_behauptet(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            lizenz = os.path.join(basis, "leer.md")
            with open(lizenz, "w", encoding="utf-8") as fh:
                fh.write("# Ohne Payload-Abschnitt\n\n`irgendwas.elf`\n")
            self.assertEqual(ws.dokumentierte_dateien(lizenz), set())

    def test_unlesbarer_ordner_liefert_nichts(self) -> None:
        self.assertEqual(ws.payloads_lesen(os.path.join(str(PROJEKT), "gibt-es-nicht")), {})


class RueckstandTests(unittest.TestCase):
    """Der Vergleich gegen die Liste - ohne Netz, mit fester Liste."""

    def test_aeltere_fassung_wird_gemeldet(self) -> None:
        befunde = ws.rueckstaende({"ftpsrv-ps5_v0.21.elf": "0.21"}, LISTE)
        self.assertEqual(len(befunde), 1, befunde)
        datei, unsere, ihre, quelle = befunde[0]
        self.assertEqual((datei, unsere, ihre), ("ftpsrv-ps5_v0.21.elf", "0.21", "0.21.1"))
        self.assertIn("github.com", quelle)

    def test_neuere_und_gleiche_bleiben_stumm(self) -> None:
        self.assertEqual(ws.rueckstaende({"ps5upload-5.28.0.elf": "5.28.0"}, LISTE), [])
        self.assertEqual(ws.rueckstaende(
            {"shadowmountplus_v1.7alpha13fix1.elf": "1.7alpha13fix1"}, LISTE), [])

    def test_fremde_reihe_wird_nicht_verglichen(self) -> None:
        """Die dr-Fassung von kstuff lite gehoert nicht zur Reihe 1.10."""
        self.assertEqual(ws.rueckstaende({"kstuff_lite_v1.2-dr_Beta2.elf": "1.2"}, LISTE), [])

    def test_ohne_fassung_kein_urteil(self) -> None:
        self.assertEqual(ws.rueckstaende({"ProsperoMgr.elf": ""}, LISTE), [])

    def test_leere_liste_meldet_nichts(self) -> None:
        self.assertEqual(ws.rueckstaende({"ftpsrv-ps5_v0.21.elf": "0.21"}, []), [])


class EchterBestandTests(unittest.TestCase):
    """Der wirkliche Bestand dieses Projekts, nicht nur ein Nachbau.

    Die uebrigen Pruefungen arbeiten mit Wegwerfordnern - sie wuerden nicht
    merken, wenn jemand eine Nutzlast hinzulegt und die Zeile in
    THIRD_PARTY_LICENSES.md vergisst. Genau das war am 17.09.2026 fuenfmal der
    Fall. Diese Pruefung sieht in den echten Ordner.
    """

    def test_helloworld_und_lizenzdatei_stimmen_ueberein(self) -> None:
        befund = ws.bestand_abgleichen(str(PROJEKT / "helloworld"),
                                       str(PROJEKT / "THIRD_PARTY_LICENSES.md"))
        self.assertEqual(befund, {"ohne_zeile": [], "ohne_datei": []})

    def test_es_gibt_ueberhaupt_nutzlasten(self) -> None:
        """Gegenprobe: Ein leerer Ordner bestuende die Pruefung oben immer."""
        payloads = ws.payloads_lesen(str(PROJEKT / "helloworld"))
        self.assertGreater(len(payloads), 20)
        ohne_fassung = [n for n, f in payloads.items() if not f]
        self.assertLessEqual(len(ohne_fassung), 4,
                             "Mehr Dateien ohne Fassung im Namen als erwartet: %s"
                             % ohne_fassung)


class FremdwerkzeugFassungTests(unittest.TestCase):
    """Der Bericht nennt die Fassung selbst installierter Werkzeuge.

    Anlass: Die hier installierte OSFMount-Fassung war 3.1.1003 vom Maerz
    2024, waehrend der Hersteller in 3.2 einen Treiberabsturz behoben hat. Im
    Programm stand davon nichts - nur der Pfad.
    """

    def test_ohne_datei_keine_fassung(self) -> None:
        from ps5_validator.utils.diagnose_befund import Diagnosebericht
        self.assertEqual(Diagnosebericht._dateifassung(""), "")
        self.assertEqual(Diagnosebericht._dateifassung(
            str(PROJEKT / "gibt-es-nicht-xyz.exe")), "")

    @unittest.skipUnless(os.name == "nt", "Fassungsangaben gibt es nur unter Windows")
    def test_windows_programm_hat_eine_fassung(self) -> None:
        from ps5_validator.utils.diagnose_befund import Diagnosebericht
        fassung = Diagnosebericht._dateifassung(sys.executable)
        self.assertRegex(fassung, r"^\d+\.\d+\.\d+\.\d+$",
                         "Keine Fassung aus %s gelesen" % sys.executable)

    def test_der_bericht_nennt_sie(self) -> None:
        """Am Syntaxbaum: Der Abschnitt der Fremdwerkzeuge fragt danach."""
        bericht = ast.parse(
            (PROJEKT / "ps5_validator" / "utils" / "diagnose_befund.py").read_text(
                encoding="utf-8"))
        abschnitt = next(k for k in ast.walk(bericht)
                         if isinstance(k, ast.FunctionDef)
                         and k.name == "_diagnose_werkzeuge")
        self.assertIn("_dateifassung",
                      {k.func.attr for k in ast.walk(abschnitt)
                       if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)})


class EingehaengtTests(unittest.TestCase):
    """Die Pruefung muss im Bericht und an der Kommandozeile ankommen."""

    def test_abschnitt_steht_im_bericht(self) -> None:
        from ps5_validator.utils import diagnose_befund
        namen = [bauer for _schluessel, bauer in diagnose_befund.Diagnosebericht.ABSCHNITTE]
        self.assertIn("_diagnose_werkzeugpflege", namen)
        self.assertTrue(hasattr(diagnose_befund.Diagnosebericht, "_diagnose_werkzeugpflege"))

    def test_hauptfenster_reicht_den_abschnitt_durch(self) -> None:
        """Ohne Weiterleitung faellt der Abschnitt im Fenster stillschweigend aus."""
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        namen = {k.name for k in ast.walk(baum) if isinstance(k, ast.FunctionDef)}
        self.assertIn("_diagnose_werkzeugpflege", namen)
        self.assertIn("_run_werkzeugpflege", namen)

    def test_der_schalter_ist_verdrahtet(self) -> None:
        text = HAUPTDATEI.read_text(encoding="utf-8")
        stelle = text.index('"--werkzeuge-pruefen"')
        self.assertIn("_run_werkzeugpflege", text[stelle:stelle + 200])

    def test_ohne_schalter_kein_netz(self) -> None:
        """Nur ``spiegel_holen`` darf ins Netz - und nur von dort gerufen."""
        quelle = (PROJEKT / "ps5_validator" / "utils" / "werkzeugstaende.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.FunctionDef):
                continue
            text = ast.unparse(knoten)
            if knoten.name == "spiegel_holen":
                self.assertIn("urlopen", text)
            else:
                self.assertNotIn("urlopen", text,
                                 "%s geht selbst ins Netz" % knoten.name)
        # Am Syntaxbaum, nicht am Wortlaut: Der Abschnitt **erklaert** in
        # seinem Kommentar, dass er nicht ins Netz geht, und nennt dabei die
        # Funktion, die es taete. Eine Textsuche schlug genau darauf an.
        bericht = ast.parse(
            (PROJEKT / "ps5_validator" / "utils" / "diagnose_befund.py").read_text(
                encoding="utf-8"))
        abschnitt = next(k for k in ast.walk(bericht)
                         if isinstance(k, ast.FunctionDef)
                         and k.name == "_diagnose_werkzeugpflege")
        gerufen = {k.func.attr for k in ast.walk(abschnitt)
                   if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)}
        self.assertTrue(gerufen, "Keine Aufrufe gefunden - der Test misst nichts")
        for netz in ("spiegel_holen", "urlopen", "urlretrieve"):
            with self.subTest(aufruf=netz):
                self.assertNotIn(netz, gerufen,
                                 "Der Diagnosebericht geht von selbst ins Netz")


class NennungTests(unittest.TestCase):
    """Wird jeder mitgelieferte Fremdbestand in THIRD_PARTY_LICENSES.md genannt?

    Gemessen am 20.09.2026: Zwei Ordner lagen in jeder Auslieferung, ohne in
    der Lizenzdatei zu stehen - ``AMPR_PackTools-4.0`` (Werkzeugkette zum AMPR
    EMU, 13 Dateien in der EXE) und ``PS5-AppInstall`` (appinst.elf, abgeleitet
    vom PS5 Payload SDK, GPL-3). Dieser Waechter zwingt bei jedem neuen Ordner
    zu einer Entscheidung: eigener Bestand oder Nennung.
    """

    #: Fremdbestand: Ordner -> ein Text, der dafuer in der Lizenzdatei steht.
    FREMD = {
        "AMPR_PackTools-4.0": "AMPR PackTools",
        "Backport_Fakelibs": "Backport_Fakelibs",
        "MkPFS-1.0.0": "MkPFS 1.0.0",
        "PS4FFPFSC-0.2.9": "PS4 FFPFSC",
        "PS5-AppInstall": "PS5-AppInstall",
        "PS5-Wee-Tools-0.1.8": "PS5 Wee Tools",
        "PS5 WebKit Autoloader": "PS5 WebKit Autoloader",
        "PlayGo & AMPR_EMU": "libScePlayGo-Stub",
        "ProsperoPkg-2.5": "LibProsperoPkg",
        "UFS2Tool-4.1": "UFS2Tool",
        "helloworld": "helloworld",
    }
    #: Eigener Bestand - hier gibt es nichts zu nennen.
    EIGEN = {"ps5_validator", "Hintergrundbilder", "Anleitungen", ".github"}

    @classmethod
    def setUpClass(cls) -> None:
        import subprocess
        roh = subprocess.run(["git", "ls-files"], cwd=str(PROJEKT), capture_output=True,
                             text=True, encoding="utf-8", errors="replace", check=False)
        cls.ordner = {zeile.split("/", 1)[0] for zeile in roh.stdout.splitlines()
                      if "/" in zeile}
        cls.lizenzen = (PROJEKT / "THIRD_PARTY_LICENSES.md").read_text(
            encoding="utf-8", errors="replace")

    def test_die_pruefung_sieht_die_ordner_ueberhaupt(self) -> None:
        """Anker - ohne Git-Arbeitskopie waere alles darunter stumm richtig."""
        if not self.ordner:
            self.skipTest("keine Git-Arbeitskopie")
        self.assertIn("ps5_validator", self.ordner)

    def test_jeder_ordner_ist_eingeordnet(self) -> None:
        if not self.ordner:
            self.skipTest("keine Git-Arbeitskopie")
        unbekannt = sorted(self.ordner - set(self.FREMD) - self.EIGEN)
        self.assertEqual(
            [], unbekannt,
            "Neuer mitgelieferter Ordner: entweder in FREMD mit einer Nennung "
            "in THIRD_PARTY_LICENSES.md oder in EIGEN aufnehmen:\n  "
            + "\n  ".join(unbekannt))

    def test_jeder_fremdordner_steht_in_der_lizenzdatei(self) -> None:
        for ordner, nennung in sorted(self.FREMD.items()):
            with self.subTest(ordner=ordner):
                self.assertIn(nennung, self.lizenzen,
                              "%s liegt bei, wird aber nicht genannt" % ordner)

    def test_die_credits_nennen_die_werkzeuge(self) -> None:
        """Das Fenster CREDITS nennt die Werkzeuge, nicht nur die Lizenzdatei."""
        from ps5_validator.utils.i18n import STRINGS
        zeile = STRINGS["credits.tools_line"]
        for name in ("UFS2Tool", "LibProsperoPkg", "PS4 FFPFSC", "PS5 Wee Tools",
                     "AMPR PackTools", "PS5 Payload SDK"):
            for sprache in ("de", "en"):
                with self.subTest(name=name, sprache=sprache):
                    self.assertIn(name, zeile[sprache])


if __name__ == "__main__":
    unittest.main()
