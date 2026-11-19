# -*- coding: utf-8 -*-
"""Der Bau eines Pakets mit Dump Forge im Fenster „PS5 PKG Dump & Image Converter“ (seit 16.11.2026).

Auftrag: ``.ffpkg``, ``.ffpfsc``, ``.ffpfs``, ``.exfat`` und Dump-Ordner werden im Bereich „PKG / FPKG“ zu einem Paket
(FPKG) gebaut - mit der Befehlszeile von Dump Forge, die das Programm mitliefert. Hier wird das **Fenster** geprueft, am
wirklichen Programm; die Befehlszeile selbst ist durch eine Attrappe ersetzt (``forge_cli.lesen``/``forge_cli.bauen``).
Die Huelle um die echte Befehlszeile prueft ``test_forge_cli.py``.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

# Die Hilfen und die Anzeige (ein Tk-Wurzelfenster je Prozess) kommen aus dem Test des Fensters; der Import lenkt auch
# den Einstellungsordner um.
import test_ps5_pkg_fenster as basis                        # noqa: E402

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.ui import pkg_einbau_karte as einbau_ui  # noqa: E402
from ps5_validator.ui import ps5_pkg_fenster as fz          # noqa: E402
from ps5_validator.utils import forge_cli as fc             # noqa: E402
from ps5_validator.utils import ps5_pkg_optionen as opt     # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz      # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402


def _de(schluessel: str, **kw) -> str:
    return STRINGS[schluessel]["de"].format(**kw)


class _ForgeBasis(unittest.TestCase):
    """Das Fenster mit einer Attrappe fuer Dump Forge - die Grundlage von ``ForgeFensterTests`` und ``EinbauSeiteTests``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(basis._WURZEL)
        cls.app._current_language = "de"
        # Der Einstellungsordner der Pruefung bleibt von Lauf zu Lauf stehen (``pruefumgebung.umlenken``): Hat ein Test die AMPR-Methode
        # "Asset-Pack" gespeichert (``_ampr_fuer_lauf_einschalten``), beginnt jeder spaetere Lauf, der diesen Ordner nimmt, mit ihr - und
        # ``test_die_felder_sind_kompakt...`` mass "Asset-Pack" (82 px) in einer Pille fuer "Normal" (74 px). Mit dem Stand von
        # ``HEAD`` und der Dateiauswahl "Forge, dann test_sprachtexte" in 4 s zu wiederholen (Gegenlese 19.11.2026).
        cls.app._save_setting("integrate_ampr_methode", APP.AMPR_METHODE_NORMAL)
        cls.app.ampr_methode_var.set(cls.app._t("ampr_pack.methode_normal"))

    def setUp(self) -> None:
        if basis._WURZEL.state() == "iconic":
            basis._WURZEL.deiconify()
            basis._pumpen(0.2)
        self.app._current_language = "de"
        self.ordner = tempfile.mkdtemp(prefix="ps5forge_test_")
        self.addCleanup(lambda: APP._rmtree_force(self.ordner, ignore_errors=True))
        self.infos: dict[str, wz.PaketInfo] = {}
        self.aufrufe: list[dict] = []
        # Weder ffpfsc-pkg-tool noch .NET: Der Forge-Weg braucht beides nicht (das ist ein Teil dessen, was geprueft wird).
        self._patcher = {
            "werkzeug": mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value=""),
            "forge": mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value="forge-exe"),
            "dotnet": mock.patch.object(wz, "dotnet_ordner", return_value=""),
            # Die Firmware der Konsole ist hier "nicht angegeben": Sonst fragte schon der erste Bau eines Spiels, das
            # eine Firmware verlangt (die echte Befehlszeile liest 2.00), mit einem echten Auswahlfenster danach - der
            # Vorschlag zu BACKPORT hat seine eigenen Tests (test_backport_empfehlung.py).
            "konsole": mock.patch.object(APP.PS5ConverterGUI, "_konsole_fw_bekannt", return_value=""),
            "lesen": mock.patch.object(fc, "lesen", side_effect=lambda exe, pfad, arbeit=None, **k: self.infos[pfad]),
            "ordner_lesen": mock.patch.object(wz, "ordner_lesen",
                                              side_effect=lambda ordner, arbeit=None, **k: self.infos[ordner]),
        }
        for p in self._patcher.values():
            p.start()
            self.addCleanup(p.stop)
        self.dialoge: dict[str, list] = {"info": [], "fehler": [], "frage": [], "auswahl": []}
        for name, ziel, antwort in (("showinfo", "info", None), ("showerror", "fehler", None), ("askyesno", "frage", True)):
            m = mock.patch.object(fz.messagebox, name, side_effect=lambda *a, _z=ziel, _r=antwort, **k: (
                self.dialoge[_z].append(a), _r)[1])
            m.start()
            self.addCleanup(m.stop)
        # Bei einem Spielordner bietet die Frage "In der Quelle fehlt etwas" seit 17.11.2026 einen Auswahldialog an (als Abbild
        # mit Einbau oder trotzdem als Paket); hier antwortet der Test mit dem Paket, wie zuvor mit "Ja".
        m = mock.patch.object(APP.PS5ConverterGUI, "_auswahl_dialog", side_effect=lambda _s, *a, **k: (
            self.dialoge["auswahl"].append(a), _de("ps5pkg.emu_wahl_paket"))[1])
        m.start()
        self.addCleanup(m.stop)
        for schluessel, wert in ((fz.EINST_AKTION, fz.AKTION_UMWANDELN), (fz.EINST_FORMAT, "ffpfsc"),
                                 (fz.EINST_BIBLIOTHEK, []), (fz.EINST_ZIEL, ""),
                                 (opt.FORGE_KRAKEN, "fast"), (opt.FORGE_VOLL_PRUEFEN, False),
                                 (opt.FORGE_BACKPORT_ENTFERNEN, False), (opt.KRAKEN_KERNE, 0)):
            self.app._save_setting(schluessel, wert)
        self.f = fz.oeffnen(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
        self.addCleanup(self._schliessen)
        self.ziel = os.path.join(self.ordner, "ziel")
        os.makedirs(self.ziel)
        self.f.ziel_var.set(self.ziel)

    def _schliessen(self) -> None:
        try:
            if self.f.win.winfo_exists():
                self.f._job = None
                self.f._uebergabe = None
                self.f.win.destroy()
        except Exception:  # noqa: BLE001
            pass
        basis._pumpen(0.05)

    # ---------------- Quellen ----------------
    def _abbild(self, name: str = "Testspiel.exfat", tid: str = "PPSA00009", titel: str = "Neun Spiel") -> str:
        pfad = os.path.join(self.ordner, name)
        Path(pfad).write_bytes(b"x" * 4096)
        art = fc.abbild_art(pfad)
        self.infos[pfad] = wz.PaketInfo(
            pfad=pfad, groesse=4096, typ=wz.TYP_ABBILD, content_id="EP0000-%s_00-TESTTESTTESTTEST" % tid, title_id=tid,
            titel=titel, param={"contentVersion": "01.000.000"}, abbild=art, befunde=["Beispielbefund"])
        return pfad

    def _spielordner(self, name: str = "Spielordner", tid: str = "PPSA00003", titel: str = "Gamma Spiel") -> str:
        ordner = os.path.join(self.ordner, name)
        os.makedirs(os.path.join(ordner, "sce_sys"))
        Path(ordner, "sce_sys", "param.json").write_text("{}", encoding="utf-8")
        self.infos[ordner] = wz.PaketInfo(
            pfad=ordner, groesse=8192, typ=wz.TYP_ORDNER, content_id="EP0000-%s_00-TESTTESTTESTTEST" % tid, title_id=tid,
            titel=titel, param={"contentVersion": "01.000.000"})
        return ordner

    def _laden(self, pfad: str, warten: bool = True) -> None:
        # Einen Spielordner liest weiterhin ffpfsc-pkg-tool-seitig ``wz.ordner_lesen`` (hier ersetzt); das Fenster verlangt
        # dafuer wie bisher das Werkzeug. Ein Abbild braucht nur Forge.
        # ``warten``: bis die Pruefung der Karte fertig ist - bis dahin ist STARTEN gesperrt (``_pruefung_laeuft``, 19.11.2026).
        # Ein Test, der die Pruefung absichtlich haengen laesst (langsame Attrappe), uebergibt ``False``.
        werkzeug = "werkzeug" if os.path.isdir(pfad) else ""
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value=werkzeug):
            self.f._pakete_hinzufuegen([pfad], waehlen=True)
        self.assertTrue(basis._warten(lambda: self.f.aktuell is not None and self.f.aktuell.pfad == pfad))
        if warten:
            self.assertTrue(basis._warten(lambda: not self.f._pruefung_laeuft(self.f.aktuell) and not self.f._pruefung_war, 20),
                            "die Pruefung der Karte wurde nicht fertig (und der Takt hat STARTEN noch nicht freigegeben)")

    def _attrappe(self, schreibt: bytes = b"pkg", warten=None, fehler: "Exception | None" = None, nachher=None):
        """Ersetzt ``forge_cli.bauen``: schreibt die Datei (wie Forge nach bestandener Pruefung) und meldet Fortschritt.

        ``nachher``: wird gerufen, wenn die Datei geschrieben ist und Forge zurueckkehrt (der Bau ist dann fertig, abgelegt ist noch nichts).
        """
        def bauen(exe, quelle, ziel, **kw):
            self.aufrufe.append(dict(kw, exe=exe, quelle=quelle, ziel=ziel, temp_da=os.path.isdir(os.path.dirname(ziel))))
            kw["fortschritt"](40, "compress")
            kw["zeile"]("package: content id X, about 1 MiB")
            if warten is not None:
                warten(kw["abbruch"])
            if fehler is not None:
                raise fehler
            Path(ziel).write_bytes(schreibt)
            if nachher is not None:
                nachher()
            return fc.ForgeBau(pfad=ziel, bytes=len(schreibt), dateien=2, pruefungen=["fpkg verify: a", "check: b"],
                               modus=kw.get("voll_pruefen") and "full" or "fast", geprueft_bytes=1, gesamt_bytes=2, proben=1)
        return mock.patch.object(fc, "bauen", side_effect=bauen)

    def _behalten(self, name: str) -> str:
        """Der Pfad des fertigen Pakets, das nach einem gescheiterten Ablegen im Arbeitsordner liegen blieb ("" ohne ein solches)."""
        for eintrag in os.listdir(self.ziel):
            kandidat = os.path.join(self.ziel, eintrag, name)
            if eintrag.startswith("ps5conv_forge_") and os.path.isfile(kandidat):
                return kandidat
        return ""

    def _ohne_arbeitsordner(self) -> list:
        """Was im Ziel liegt, ohne die Arbeitsordner von Dump Forge."""
        return [e for e in os.listdir(self.ziel) if not e.startswith("ps5conv_forge_")]

    def _starten_und_warten(self, grenze: float = 20.0) -> None:
        self.f._starten()
        self.assertTrue(basis._warten(lambda: self.f._job is None, grenze), "der Auftrag ist nicht zu Ende gegangen")


@unittest.skipUnless(basis._TK_DA, "ohne Anzeige kein Fenster")
class ForgeFensterTests(_ForgeBasis):

    # ---------------- Lesen und Anzeige ----------------
    def test_ein_abbild_wird_ohne_net_werkzeug_gelesen_und_angezeigt(self) -> None:
        pfad = self._abbild()
        self._laden(pfad)
        f, info = self.f, self.f.aktuell
        self.assertTrue(info.ist_abbild)
        self.assertEqual("Abbild EXFAT", f.paket_typ.cget("text"))
        self.assertEqual(_de("ps5pkg.src_image", art="exfat"), dict(f.tech.item(i, "values") for i in f.tech.get_children())["Quelle"])
        self.assertIn("[Dump Forge] Beispielbefund", f.protokoll.get("1.0", "end"))
        self.assertEqual([], self.dialoge["fehler"])

    def test_aus_einem_abbild_geht_nur_das_paket_der_rest_hat_eine_klare_absage(self) -> None:
        self._laden(self._abbild())
        f = self.f
        self.assertEqual("pkg", f.format_schluessel, "das Auswahlfeld springt auf Paket")
        self.assertTrue(f._format_moeglich("pkg"))
        for anderes in ("ffpkg", "ffpfsc", "ffpfs", "exfat"):
            with self.subTest(format=anderes):
                self.assertFalse(f._format_moeglich(anderes))
        for aktion in ("extrahieren", "pruefen"):
            with self.subTest(aktion=aktion):
                self.assertFalse(f._aktion_moeglich(aktion))
        self.assertTrue(f._aktion_moeglich("umwandeln"))
        f._format_waehlen("ffpfsc")
        self.assertEqual(_de("ps5pkg.format_only_package"), f.status_var.get())
        self.assertEqual("pkg", f.format_schluessel)

    def test_das_datei_durchsuchen_im_ordner_nimmt_abbilder_mit_und_laesst_anderes_liegen(self) -> None:
        a = self._abbild("a.ffpkg", tid="PPSA00001")
        b = self._abbild("b.FFPFSC", tid="PPSA00002")
        Path(self.ordner, "text.txt").write_text("nichts")
        Path(self.ordner, "c.zip").write_bytes(b"zip")
        gefunden = self.f._quellen_in(self.ordner)
        self.assertEqual([a, b], gefunden)

    def test_ohne_die_forge_befehlszeile_fehlt_dem_abbild_das_werkzeug_mit_klarer_meldung(self) -> None:
        pfad = self._abbild()
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value=""):
            self.f._pakete_hinzufuegen([pfad], waehlen=True)
        self.assertEqual(1, len(self.dialoge["fehler"]))
        self.assertIn("Dump-Forge-CLI", self.dialoge["fehler"][0][1])
        self.assertEqual([], self.f.pakete)

    # ---------------- Bauen ----------------
    def test_ein_abbild_wird_mit_forge_zu_einem_paket_im_zielordner(self) -> None:
        pfad = self._abbild()
        self._laden(pfad)
        f = self.f
        with self._attrappe(), mock.patch.object(wz, "pruefen") as pruefen:
            self._starten_und_warten()
        pruefen.assert_not_called()
        self.assertEqual(1, len(self.aufrufe))
        aufruf = self.aufrufe[0]
        self.assertEqual(("forge-exe", pfad), (aufruf["exe"], aufruf["quelle"]))
        name = "Neun Spiel [PPSA00009].pkg"
        self.assertEqual(name, os.path.basename(aufruf["ziel"]))
        self.assertEqual(self.ziel, os.path.dirname(os.path.dirname(aufruf["ziel"])), "Arbeitsordner im Zielordner")
        self.assertTrue(aufruf["temp_da"])
        self.assertEqual([name], os.listdir(self.ziel), "das Paket liegt im Zielordner, der Arbeitsordner ist weg")
        self.assertEqual(b"pkg", Path(self.ziel, name).read_bytes())
        self.assertEqual(_de("ps5pkg.job_done_build", datei=name), f.auftrag_var.get())
        log = f.protokoll.get("1.0", "end")
        self.assertIn("package: content id X, about 1 MiB", log, "Forges Protokollzeilen kommen im Fenster an")
        self.assertIn("[OK] Dump Forge: 2 Prüfungen bestanden", log)
        self.assertIn("Stichproben", log)
        self.assertIn(_de("ps5pkg.forge_note"), log, "der Konsolenhinweis nennt Dump Forge")
        self.assertEqual(self.ziel, f._z.get("ausgabe"))
        self.assertEqual(100.0, float(f.balken_gesamt["value"]))

    def test_die_optionen_kommen_bei_forge_an(self) -> None:
        for schluessel, wert in ((opt.FORGE_KRAKEN, "smallest"), (opt.FORGE_VOLL_PRUEFEN, True),
                                 (opt.FORGE_BACKPORT_ENTFERNEN, True), (opt.KRAKEN_KERNE, 4)):
            self.app._save_setting(schluessel, wert)
        self._laden(self._abbild())
        with self._attrappe():
            self._starten_und_warten()
        a = self.aufrufe[0]
        self.assertEqual(("smallest", True, True, 4), (a["kraken"], a["voll_pruefen"], a["backport_entfernen"], a["kerne"]))
        self.assertIn("jedes Byte geprüft", self.f.protokoll.get("1.0", "end"), "die vollstaendige Pruefung steht im Ergebnis")

    def test_eine_unbekannte_gespeicherte_stufe_faellt_auf_die_schnelle_zurueck(self) -> None:
        self.app._save_setting(opt.FORGE_KRAKEN, "irgendwas")
        self._laden(self._abbild())
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual("fast", self.aufrufe[0]["kraken"])

    def test_ein_spielordner_baut_bei_forge_als_paketersteller_mit_forge(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual(ordner, self.aufrufe[0]["quelle"])
        self.assertEqual(["Gamma Spiel [PPSA00003].pkg"], os.listdir(self.ziel))

    def test_ohne_dump_forge_wird_nicht_gebaut_und_der_grund_steht_da(self) -> None:
        """Es gibt keinen zweiten Paketersteller mehr: Fehlt die Befehlszeile, meldet die Seite es und baut nichts."""
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value=""):
            self.f._starten()
        for name in ("bauen", "fw_hex", "param_json_setzen", "bau_fortschritt"):
            self.assertFalse(hasattr(wz, name), "der Bau mit LibProsperoPkg ist weg: wz.%s" % name)
        self.assertEqual([], self.aufrufe)
        self.assertEqual(1, len(self.dialoge["fehler"]))
        self.assertIn("Dump-Forge-CLI", self.dialoge["fehler"][0][1])

    def test_ohne_zielordner_wird_nicht_gebaut(self) -> None:
        self._laden(self._abbild())
        self.f.ziel_var.set(os.path.join(self.ordner, "gibt-es-nicht"))
        with self._attrappe():
            self.f._starten()
        self.assertEqual([], self.aufrufe)
        self.assertEqual(1, len(self.dialoge["fehler"]))

    # ---------------- vorhandenes Paket ----------------
    def test_ein_vorhandenes_paket_gleichen_namens_wird_nur_mit_haken_ersetzt(self) -> None:
        name = "Neun Spiel [PPSA00009].pkg"
        Path(self.ziel, name).write_bytes(b"alt")
        self._laden(self._abbild())
        with self._attrappe(schreibt=b"neu"):
            self.f._starten()
        self.assertEqual([], self.aufrufe, "ohne den Haken wird nicht einmal begonnen")
        self.assertEqual(1, len(self.dialoge["info"]))
        self.assertEqual(b"alt", Path(self.ziel, name).read_bytes())
        self.f.ueberschreiben_var.set(True)
        with self._attrappe(schreibt=b"neu"):
            self._starten_und_warten()
        self.assertEqual(b"neu", Path(self.ziel, name).read_bytes())
        self.assertEqual([name], os.listdir(self.ziel))

    def test_scheitert_ein_ersetzender_bau_bleibt_das_alte_paket_unversehrt(self) -> None:
        name = "Neun Spiel [PPSA00009].pkg"
        Path(self.ziel, name).write_bytes(b"alt")
        self._laden(self._abbild())
        self.f.ueberschreiben_var.set(True)
        with self._attrappe(fehler=wz.Fehler("Dump Forge sagt nein")):
            self._starten_und_warten()
        self.assertEqual(b"alt", Path(self.ziel, name).read_bytes())
        self.assertEqual([name], os.listdir(self.ziel), "und kein Arbeitsordner bleibt liegen")

    def test_scheitert_das_ersetzen_selbst_bleibt_die_alte_datei(self) -> None:
        """Die alte Datei wird nicht vor dem Umbenennen geloescht: Ist sie gesperrt (Virenscanner), bleibt sie, wie sie war (18.11.2026)."""
        name = "Neun Spiel [PPSA00009].pkg"
        Path(self.ziel, name).write_bytes(b"alt")
        self._laden(self._abbild())
        self.f.ueberschreiben_var.set(True)
        echt_replace = os.replace

        def replace(quelle, ziel, *a, **k):
            if os.path.basename(str(ziel)) == name:
                raise PermissionError("gesperrt")
            return echt_replace(quelle, ziel, *a, **k)

        with self._attrappe(schreibt=b"neu"), mock.patch.object(os, "replace", side_effect=replace):
            self._starten_und_warten()
        self.assertEqual(b"alt", Path(self.ziel, name).read_bytes())
        self.assertEqual(_de("ps5pkg.job_failed"), self.f.auftrag_var.get())
        self.assertEqual([name], self._ohne_arbeitsordner(), "nichts Halbes: kein Zwischenstand")
        behalten = self._behalten(name)
        self.assertEqual(b"neu", Path(behalten).read_bytes() if behalten else b"", "das fertige Paket ist nicht verloren (18.11.2026)")
        self.assertIn(_de("ps5pkg.paket_behalten", pfad=behalten), self.f.protokoll.get("1.0", "end"), "und das Protokoll nennt seinen Platz")

    def _ersetzen_ueber_kopie(self, kopie_scheitert: bool) -> str:
        """``os.replace`` von der Arbeitsdatei geht nicht (anderes Laufwerk); ersetzt wird ueber eine Kopie neben dem Ziel."""
        name = "Neun Spiel [PPSA00009].pkg"
        Path(self.ziel, name).write_bytes(b"alt")
        self._laden(self._abbild())
        self.f.ueberschreiben_var.set(True)
        echt_replace, echt_copy2 = os.replace, shutil.copy2

        def replace(quelle, ziel, *a, **k):
            if os.path.basename(str(quelle)) == name and os.path.basename(str(ziel)) == name:
                raise OSError(18, "anderes Laufwerk")
            return echt_replace(quelle, ziel, *a, **k)

        def copy2(quelle, ziel, *a, **k):
            if str(ziel).endswith(".ps5conv_neu") and kopie_scheitert:
                Path(ziel).write_bytes(b"halb")
                raise OSError(28, "Platte voll")
            return echt_copy2(quelle, ziel, *a, **k)

        with self._attrappe(schreibt=b"neu"), mock.patch.object(os, "replace", side_effect=replace), \
                mock.patch.object(shutil, "copy2", side_effect=copy2):
            self._starten_und_warten()
        return name

    def test_bricht_die_kopie_beim_ersetzen_ab_bleibt_die_alte_datei_unversehrt(self) -> None:
        """``shutil.move`` haette die alte Datei unter Windows schon mitten in der Kopie ueberschrieben (Pruefung 18.11.2026)."""
        name = self._ersetzen_ueber_kopie(kopie_scheitert=True)
        self.assertEqual(b"alt", Path(self.ziel, name).read_bytes())
        self.assertEqual([name], self._ohne_arbeitsordner(), "die halbe Kopie ist weg")
        behalten = self._behalten(name)
        self.assertEqual(b"neu", Path(behalten).read_bytes() if behalten else b"", "das fertige Paket liegt im Arbeitsordner weiter")

    def test_geht_os_replace_nicht_wird_ueber_eine_kopie_ersetzt(self) -> None:
        name = self._ersetzen_ueber_kopie(kopie_scheitert=False)
        self.assertEqual(b"neu", Path(self.ziel, name).read_bytes())
        self.assertEqual([name], os.listdir(self.ziel))

    def test_ein_nicht_entfernbarer_kopierrest_steht_im_log(self) -> None:
        """Haelt ein Virenscanner die halbe Kopie fest, bleibt sie liegen - dann soll wenigstens im Log stehen, welche Datei es ist."""
        echt_remove = os.remove

        def remove(pfad, *a, **k):
            if str(pfad).endswith(".ps5conv_neu"):
                raise PermissionError("gehalten")
            return echt_remove(pfad, *a, **k)

        with mock.patch.object(os, "remove", side_effect=remove), self.assertLogs(fz.logger, "WARNING") as protokoll:
            name = self._ersetzen_ueber_kopie(kopie_scheitert=True)
        self.assertEqual(b"alt", Path(self.ziel, name).read_bytes())
        self.assertTrue(any(".ps5conv_neu" in zeile for zeile in protokoll.output), protokoll.output)

    def test_eine_waehrend_des_baus_entstandene_datei_wird_ohne_haken_nicht_ueberschrieben(self) -> None:
        """Die Pruefung \"Datei da, Haken aus\" lief nur beim Start; der Bau dauert Stunden, ein anderer Lauf kann dieselbe Datei anlegen."""
        name = "Neun Spiel [PPSA00009].pkg"
        self._laden(self._abbild())
        self.assertFalse(self.f.ueberschreiben_var.get())
        with self._attrappe(schreibt=b"neu", warten=lambda _abbruch: Path(self.ziel, name).write_bytes(b"fremd")):
            self._starten_und_warten()
        self.assertEqual(b"fremd", Path(self.ziel, name).read_bytes(), "die Datei, die inzwischen da war, ist unberuehrt")
        self.assertEqual(_de("ps5pkg.job_failed"), self.f.auftrag_var.get())
        self.assertIn(_de("ps5pkg.err_exists_pkg", pfad=os.path.join(self.ziel, name)), self.f.protokoll.get("1.0", "end"))
        self.assertEqual([name], self._ohne_arbeitsordner())
        behalten = self._behalten(name)
        self.assertEqual(b"neu", Path(behalten).read_bytes() if behalten else b"",
                         "das fertige Paket ist nicht verloren: Ein Bau von Stunden geht nicht an einer gleichnamigen Datei zugrunde")
        self.assertIn(_de("ps5pkg.paket_behalten", pfad=behalten), self.f.protokoll.get("1.0", "end"))

    def test_mit_dem_haken_wird_eine_waehrend_des_baus_entstandene_datei_ersetzt(self) -> None:
        name = "Neun Spiel [PPSA00009].pkg"
        self._laden(self._abbild())
        self.f.ueberschreiben_var.set(True)
        with self._attrappe(schreibt=b"neu", warten=lambda _abbruch: Path(self.ziel, name).write_bytes(b"fremd")):
            self._starten_und_warten()
        self.assertEqual(b"neu", Path(self.ziel, name).read_bytes())

    def test_abbrechen_nach_dem_fertigen_bau_legt_nichts_ab(self) -> None:
        """ABBRECHEN kommt, als Forge schon zurueckgekehrt ist: Es steht nicht \"fertig\" da, und im Ziel liegt nichts Neues."""
        self._laden(self._abbild())
        with self._attrappe(nachher=lambda: setattr(self.f, "_abbruch", True)):
            self._starten_und_warten()
        self.assertEqual(_de("ps4pkg.status_cancelled"), self.f.auftrag_var.get())
        self.assertEqual([], os.listdir(self.ziel))

    def test_ein_abbruch_beim_ablegen_zaehlt_als_abbruch_nicht_als_fehlschlag(self) -> None:
        self._laden(self._abbild())

        def replace(*_a, **_k):
            self.f._abbruch = True                       # ABBRECHEN kommt mitten im Ablegen
            raise PermissionError("gesperrt")

        with self._attrappe(), mock.patch.object(os, "replace", side_effect=replace):
            self._starten_und_warten()
        self.assertEqual(_de("ps4pkg.status_cancelled"), self.f.auftrag_var.get())
        self.assertNotEqual(_de("ps5pkg.job_failed"), self.f.auftrag_var.get())
        self.assertEqual([], os.listdir(self.ziel), "nach ABBRECHEN bleibt nichts liegen, auch nicht das fertige Paket")

    def test_ein_fehler_des_baus_selbst_hebt_nichts_auf(self) -> None:
        """Nur ein fertiges Paket wird behalten; scheitert Forge selbst, bleibt kein Arbeitsordner und kein Hinweis darauf."""
        self._laden(self._abbild())
        with self._attrappe(fehler=wz.Fehler("Dump Forge sagt nein")):
            self._starten_und_warten()
        self.assertEqual([], os.listdir(self.ziel))
        self.assertNotIn(_de("ps5pkg.paket_behalten", pfad=""), self.f.protokoll.get("1.0", "end"))

    def test_eine_manipulierte_kennung_fuehrt_nie_aus_dem_zielordner_heraus(self) -> None:
        """Die Kennung steht in Dateinamen. Eine param.json mit ``X\\..\\..\\Y`` darf kein Paket ausserhalb des Ziels ablegen (18.11.2026;
        die Pruefung im frueheren Bau von LibProsperoPkg war mit diesem entfallen)."""
        echt = wz.PaketInfo(pfad=os.path.join(self.ordner, "Spiel.pkg"), titel="Spiel", title_id="PPSA01234")
        self.assertEqual("Spiel [PPSA01234]", fz.anzeigename(echt), "eine echte Kennung bleibt")
        for boese in ("X\\..\\..\\..\\Y", "../../Y", "A/B", "PPSA0000", "PPSA000099", "..", "PP SA01234", "PPSA01234\\.."):
            with self.subTest(kennung=boese):
                info = wz.PaketInfo(pfad=os.path.join(self.ordner, "Spiel.pkg"), titel="Spiel", title_id=boese)
                self.assertEqual("", info.title_id)
                for name in (fz.anzeigename(info), fz.Ps5PkgFenster._forge_dateiname(info)):
                    pfad = os.path.normpath(os.path.join(self.ziel, name))
                    self.assertEqual(self.ziel, os.path.dirname(pfad), name)

    # ---------------- Fehler und Abbruch ----------------
    def test_ein_fehler_von_forge_steht_im_protokoll_und_hinterlaesst_nichts(self) -> None:
        self._laden(self._abbild())
        with self._attrappe(fehler=wz.Fehler("the output name is too long")):
            self._starten_und_warten()
        f = self.f
        self.assertEqual(_de("ps5pkg.job_failed"), f.auftrag_var.get())
        self.assertIn("the output name is too long", f.protokoll.get("1.0", "end"))
        self.assertEqual([], os.listdir(self.ziel))

    def test_abbrechen_beendet_den_bau_ohne_fehlschlag_und_ohne_reste(self) -> None:
        self._laden(self._abbild())
        begonnen = []

        def warten(abbruch) -> None:
            begonnen.append(True)
            ende = time.monotonic() + 15
            while not abbruch() and time.monotonic() < ende:
                time.sleep(0.02)
            if abbruch():
                raise wz.Fehler("abgebrochen")

        with self._attrappe(warten=warten):
            self.f._starten()
            self.assertTrue(basis._warten(lambda: bool(begonnen), 10), "der Bau laeuft")
            self.f._abbrechen()
            self.assertTrue(basis._warten(lambda: self.f._job is None, 20))
        self.assertEqual(_de("ps4pkg.status_cancelled"), self.f.auftrag_var.get())
        self.assertNotEqual(_de("ps5pkg.job_failed"), self.f.auftrag_var.get())
        self.assertEqual([], os.listdir(self.ziel), "kein Paket, kein Arbeitsordner")

    def test_der_balken_zeigt_die_stufen_in_der_sprache_des_programms(self) -> None:
        self.assertEqual(_de("ps5pkg.forge_stage_compress"), self.f._forge_stufe_text("compress"))
        self.assertEqual("unbekannt", self.f._forge_stufe_text("unbekannt"), "fremde Stufen bleiben, wie sie sind")
        for stufe in fz.FORGE_STUFEN:
            with self.subTest(stufe=stufe):
                for sprache in ("de", "en", "es", "it", "fr"):
                    self.assertTrue(STRINGS["ps5pkg.forge_stage_" + stufe][sprache].strip())

    # ---------------- Ende zu Ende mit der echten Befehlszeile ----------------
    @unittest.skipUnless(fc.werkzeug_suchen([str(PROJEKT)]), "fuer diese Plattform liegt keine Dump-Forge-Befehlszeile bei")
    def test_vom_abbild_bis_zum_paket_mit_der_echten_befehlszeile_durch_das_fenster(self) -> None:
        """Nichts ersetzt: ``forge.lesen`` und ``forge.bauen`` laufen gegen die mitgelieferte Befehlszeile."""
        import json
        import subprocess
        exe = fc.werkzeug_suchen([str(PROJEKT)])
        spiel = os.path.join(self.ordner, "Echtes Spiel")
        os.makedirs(os.path.join(spiel, "sce_sys"))
        param = {"contentId": "EP9999-PPSA99999_00-TESTSPIEL0000001", "titleId": "PPSA99999", "contentVersion": "01.000.000",
                 "masterVersion": "01.00", "applicationCategoryType": 0, "applicationDrmType": "standard",
                 "conceptId": "100000", "requiredSystemSoftwareVersion": "0x0200000000000000",
                 "sdkVersion": "0x0200000000000000",
                 "localizedParameters": {"defaultLanguage": "en-US", "en-US": {"titleName": "Echtes Spiel"}}}
        Path(spiel, "sce_sys", "param.json").write_text(json.dumps(param), encoding="utf-8")
        Path(spiel, "eboot.bin").write_bytes(os.urandom(4096))
        Path(spiel, "daten.bin").write_bytes(b"abc" * 4000)
        bild = os.path.join(self.ordner, "Echtes Spiel.ffpfsc")
        self.assertEqual(0, subprocess.run([exe, "convert", spiel, "--to", "ffpfsc", "-o", bild], capture_output=True).returncode)
        for name in ("lesen", "forge"):
            self._patcher[name].stop()
        self.addCleanup(self._patcher["lesen"].start)
        self.addCleanup(self._patcher["forge"].start)
        f = self.f
        f._pakete_hinzufuegen([bild], waehlen=True)
        self.assertTrue(basis._warten(lambda: f.aktuell is not None and f.aktuell.pfad == bild, 30), "Forge hat das Abbild gelesen")
        self.assertEqual(("PPSA99999", "Echtes Spiel", "ffpfsc"), (f.aktuell.title_id, f.aktuell.titel, f.aktuell.abbild))
        self.assertEqual("pkg", f.format_schluessel)
        # STARTEN ist gesperrt, solange die Pruefung der Karte (echtes ``inspect``) liest (``_pruefung_laeuft``, 19.11.2026).
        self.assertTrue(basis._warten(lambda: not f._pruefung_laeuft(f.aktuell), 60), "die Pruefung der Karte wurde nicht fertig")
        self._starten_und_warten(60)
        name = "Echtes Spiel [PPSA99999].pkg"
        self.assertEqual([name], os.listdir(self.ziel))
        with open(os.path.join(self.ziel, name), "rb") as datei:
            self.assertEqual(b"FIH", datei.read(4))
        self.assertEqual(_de("ps5pkg.job_done_build", datei=name), f.auftrag_var.get())
        log = f.protokoll.get("1.0", "end")
        self.assertIn("[OK] Dump Forge:", log)
        self.assertIn("fpkg: verifying", log, "Forges eigene Protokollzeilen kommen durch das Fenster an")

    # ---------------- Emulatoren (DLC EMU, PlayGo) ----------------
    _DLC = dict(dlc_vorhanden=True, dlc_emuliert=False, dlc_merkmal="addcont0")
    _PLAYGO = dict(playgo_merkmal="sce_sys/playgo-scenario.json")

    def _abbild_mit_fakten(self, **fakten) -> str:
        pfad = self._abbild()
        self.infos[pfad].fakten = fc.QuellFakten(**fakten)
        return pfad

    def _fragen(self) -> list:
        return [a for a in self.dialoge["frage"] if a and a[0] == _de("ps5pkg.emu_titel")]

    def test_fehlt_dlc_emu_wird_vor_dem_bau_gefragt_und_mit_ja_gebaut(self) -> None:
        self._laden(self._abbild_mit_fakten(**self._DLC))
        with self._attrappe():
            self._starten_und_warten()
        fragen = self._fragen()
        self.assertEqual(1, len(fragen))
        self.assertIn(_de("ps5pkg.emu_zeile_dlc", merkmal="addcont0"), fragen[0][1])
        self.assertNotIn("• PlayGo:", fragen[0][1], "nur die fehlende Zeile steht in der Liste")
        self.assertEqual(1, len(self.aufrufe), "mit Ja wird gebaut")
        self.assertIn(_de("ps5pkg.emu_log"), self.f.protokoll.get("1.0", "end"))

    def test_fehlt_der_playgo_stub_wird_ebenso_gefragt(self) -> None:
        self._laden(self._abbild_mit_fakten(**self._PLAYGO))
        with self._attrappe():
            self._starten_und_warten()
        fragen = self._fragen()
        self.assertEqual(1, len(fragen))
        self.assertIn(_de("ps5pkg.emu_zeile_playgo", merkmal="sce_sys/playgo-scenario.json"), fragen[0][1])
        self.assertNotIn("• DLC EMU:", fragen[0][1])
        self.assertEqual(1, len(self.aufrufe))

    def test_fehlen_beide_steht_es_in_einer_frage(self) -> None:
        self._laden(self._abbild_mit_fakten(**self._DLC, **self._PLAYGO))
        with self._attrappe():
            self._starten_und_warten()
        fragen = self._fragen()
        self.assertEqual(1, len(fragen), "eine Frage, nicht zwei")
        self.assertIn(_de("ps5pkg.emu_zeile_dlc", merkmal="addcont0"), fragen[0][1])
        self.assertIn(_de("ps5pkg.emu_zeile_playgo", merkmal="sce_sys/playgo-scenario.json"), fragen[0][1])

    def test_mit_nein_wird_nicht_gebaut_und_nichts_bleibt_liegen(self) -> None:
        self._laden(self._abbild_mit_fakten(**self._DLC))
        with self._attrappe(), mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage:
            self.f._starten()
        frage.assert_called_once()
        self.assertEqual([], self.aufrufe)
        self.assertIsNone(self.f._job)
        self.assertEqual(_de("ps5pkg.emu_abgebrochen"), self.f.status_var.get())
        self.assertEqual([], os.listdir(self.ziel), "kein Arbeitsordner, kein Paket")
        self.assertNotIn(_de("ps5pkg.emu_log"), self.f.protokoll.get("1.0", "end"))

    def test_liegen_die_emulatoren_in_der_quelle_oder_braucht_sie_das_spiel_nicht_keine_frage(self) -> None:
        faelle = {
            "DLC schon emuliert": dict(dlc_vorhanden=True, dlc_emuliert=True, dlc_merkmal="addcont0"),
            "PlayGo-Stub liegt darin": dict(playgo_merkmal="sce_sys/playgo-scenario.json", emulatoren=("playgo",)),
            "weder DLC noch PlayGo": dict(),
            "AMPR fehlt (legt Forge selbst dazu)": dict(ampr_importiert=True, ampr_fehlt=True),
        }
        for name, fakten in faelle.items():
            with self.subTest(fall=name):
                self.dialoge["frage"].clear()
                self.aufrufe.clear()
                self._laden(self._abbild_mit_fakten(**fakten))
                with self._attrappe():
                    self._starten_und_warten()
                self.assertEqual([], self._fragen())
                self.assertEqual(1, len(self.aufrufe))
                for p in os.listdir(self.ziel):
                    os.remove(os.path.join(self.ziel, p))

    def test_ohne_forges_fakten_wird_nicht_gefragt(self) -> None:
        self._laden(self._abbild())
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual([], self._fragen())

    def test_ein_spielordner_wird_vor_dem_bau_von_forge_gelesen_und_das_nur_einmal(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        with self._attrappe(), mock.patch.object(fc, "quellfakten_lesen",
                                                 return_value=fc.QuellFakten(**self._DLC)) as lesen:
            self._starten_und_warten()
            self.assertEqual(1, lesen.call_count)
            self.assertEqual(("forge-exe", ordner), lesen.call_args.args)
            self.assertEqual(1, len(self.dialoge["auswahl"]), "ein Spielordner bekommt die Wahl Abbild oder Paket")
            self.assertEqual([], self._fragen(), "und keine Ja/Nein-Frage")
            self.assertIsNotNone(self.f.aktuell.fakten, "die Antwort bleibt an der Quelle")
            for p in os.listdir(self.ziel):
                os.remove(os.path.join(self.ziel, p))
            self._starten_und_warten()
            self.assertEqual(1, lesen.call_count, "ein zweiter Bau liest nicht noch einmal")

    def test_kann_forge_den_spielordner_nicht_lesen_wird_trotzdem_gebaut(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        with self._attrappe(), mock.patch.object(fc, "quellfakten_lesen", return_value=None):
            self._starten_und_warten()
        self.assertEqual([], self._fragen())
        self.assertEqual(1, len(self.aufrufe))

    def test_die_frage_steht_nach_der_platzpruefung_und_vor_dem_ersten_arbeitsordner(self) -> None:
        text = Path(fz.__file__).read_text(encoding="utf-8")
        start = text.index("def _forge_bauen_starten")
        # Seit 17.11.2026 nimmt dieselbe Zeile fuer ein Abbild aus einem Paket den Faktor des Entpackens statt FORGE_PLATZ_FAKTOR, seit
        # 18.11.2026 fuer ein gepacktes Spiel den des entpackten Spiels (``faktor`` in der Zeile davor).
        text.index("faktor = ENTPACKT_FAKTOR if abbild else FORGE_PLATZ_FAKTOR_ENTPACKT if entpacken else FORGE_PLATZ_FAKTOR", start)
        platz = text.index("self._platz_reicht(ziel, int(info.groesse * faktor)", start)
        frage = text.index("self._emulatoren_fragen(info)", start)
        temp = text.index("tempfile.mkdtemp(prefix=\"ps5conv_forge_\"", start)
        self.assertLess(platz, frage)
        self.assertLess(frage, temp, "bei Nein darf kein Arbeitsordner entstehen")

    # ---------------- Zielformat ----------------
    def test_ohne_gespeicherte_wahl_gilt_ffpkg_eine_gespeicherte_bleibt(self) -> None:
        """Bis 16.11.2026 galt ``ffpfsc``; das Programm empfiehlt ``ffpkg`` selbst. Wer gewaehlt hat, behaelt seine Wahl."""
        for gespeichert, erwartet in ((None, "ffpkg"), ("ffpfsc", "ffpfsc"), ("exfat", "exfat"), ("kaputt", "ffpkg")):
            with self.subTest(gespeichert=gespeichert):
                self._schliessen()
                with mock.patch.object(fz.Ps5PkgFenster, "_einstellung",
                                       side_effect=lambda k, v, _g=gespeichert: _g if (k == fz.EINST_FORMAT and _g) else v):
                    self.f = fz.oeffnen(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
                self.assertEqual(erwartet, self.f.format_schluessel)

    def test_ffpfsc_und_ffpfs_nennen_das_tempo_ffpkg_und_exfat_und_paket_nicht(self) -> None:
        """Wie im Hauptfenster: Nach der Wahl von ``ffpfsc``/``ffpfs`` steht ein Satz zu Tempo und Empfehlung."""
        self._laden(self._spielordner())
        hinweis = _de("main.pfs_speed_hint")
        for schluessel, erwartet in (("ffpfsc", True), ("ffpfs", True), ("ffpkg", False), ("exfat", False), ("pkg", False)):
            with self.subTest(format=schluessel):
                self.f._status("vorher")
                self.f._format_waehlen(schluessel)
                self.assertEqual(schluessel, self.f.format_schluessel)
                self.assertEqual(hinweis if erwartet else "vorher", self.f.status_var.get())

    # ---------------- Namen ----------------
    def test_der_name_kommt_aus_titel_und_kennung_und_bleibt_in_63_bytes(self) -> None:
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "x.exfat"), typ=wz.TYP_ABBILD, title_id="PPSA12345",
                            titel="Ein sehr langer Spieltitel " * 6)
        name = fz.Ps5PkgFenster._forge_dateiname(info)
        self.assertTrue(name.endswith(" [PPSA12345].pkg"))
        self.assertLessEqual(len(name[:-4].encode("utf-8")), 63)

    def test_ohne_titel_gilt_der_name_der_quelle_ohne_endung(self) -> None:
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "Mein Abbild.exfat"), typ=wz.TYP_ABBILD, title_id="PPSA12345")
        self.assertEqual("Mein Abbild [PPSA12345].pkg", fz.Ps5PkgFenster._forge_dateiname(info))

    def test_das_ergebnisfeld_zeigt_den_namen_den_das_programm_vergibt(self) -> None:
        self._laden(self._abbild())
        self.assertEqual("Neun Spiel [PPSA00009].pkg", self.f.ergebnis_var["output"].get())


@unittest.skipUnless(basis._TK_DA, "ohne Anzeige kein Fenster")
class EinbauSeiteTests(_ForgeBasis):
    """Seite 7 wie die Aufgaben 1 bis 6 (17.11.2026): Einbau-Karte, Pruefung der Quelle, Rueckfragen vor dem Bau, Umwandeln eines
    Pakets ohne Zwischenordner, Lebenszeichen.

    Die Felder der Karte sind Zwillinge der Felder im Hauptfenster (gleiche Tk-Variablen, gleiche Befehle); die Befehle
    selbst pruefen die Tests der Aufgaben 1 bis 6 - hier zaehlt, dass die Karte sie ruft und ihre Listen und Sperren uebernimmt.
    """

    _DLC = dict(dlc_vorhanden=True, dlc_emuliert=False, dlc_merkmal="addcont0")

    def setUp(self) -> None:
        super().setUp()
        # Die Kaestchen und Felder der Aufgaben 1 bis 6 behalten nach dem Test, was sie vorher hatten.
        app = self.app
        for name in ("ampr_integrate_var", "ampr_playgo_var", "dlc_integrate_var", "backport_integrate_var"):
            var = getattr(app, name)
            self.addCleanup(var.set, var.get())
        # Auch die gespeicherten Haken: Die Rueckfragen schalten ein Kaestchen ein UND speichern es (``_dlc_einschalten``,
        # ``_playgo_einschalten`` ...). Ohne das baut jede spaetere App-Instanz im selben Prozess mit angehaktem Haken auf:
        # ``test_ffpfsc_asset_umhuellen`` sah dann ``ffpfsc -> ffpfsc`` ohne Asset-Pack (Bisektion 18.11.2026; im Volllauf in
        # alphabetischer Reihenfolge fiel es nie auf).
        for name in ("zstd_level", "worker_count", "mkpfs_verify", "integrate_ampr", "integrate_playgo", "integrate_backport",
                     "integrate_dlc", "integrate_ampr_methode", "integrate_ampr_version", "ampr_pack_verfahren"):
            self.addCleanup(app._save_setting, name, app._load_setting(name, None))
        # Der Faden, der das PlayGo-Merkmal eines Pakets im Archiv sucht, soll hier nichts starten.
        m = mock.patch.object(wz, "playgo_erklaert_archiv", return_value="")
        m.start()
        self.addCleanup(m.stop)
        self.karte = self.f.einbau
        self.assertIsNotNone(self.karte, "die Seite hat die Einbau-Karte")

    # ---------------- Quellen ----------------
    def _paket(self, name: str = "Alpha.pkg", tid: str = "PPSA00007", titel: str = "Sieben") -> "wz.PaketInfo":
        pfad = os.path.join(self.ordner, name)
        Path(pfad).write_bytes(b"pkg")
        info = basis._info(name, titel, tid, 4096, pfad)
        self.infos[pfad] = info
        self.f.pakete.append(info)
        self.f._paket_waehlen(info, aus_liste=True)
        # STARTEN ist gesperrt, solange die Pruefung der Karte im Hintergrund liest (``_pruefung_laeuft``, 19.11.2026): abwarten.
        self.assertTrue(basis._warten(lambda: not self.f._pruefung_laeuft(info) and not self.f._pruefung_war, 20),
                        "die Pruefung der Karte wurde nicht fertig (und der Takt hat STARTEN noch nicht freigegeben)")
        return info

    def _protokoll_text(self) -> str:
        return self.f.protokoll.get("1.0", "end")

    def _schliessen_nicht_abwarten(self) -> None:
        basis._pumpen(0.1)

    # ---------------- die Karte ----------------
    def test_die_felder_haengen_an_denselben_variablen_wie_in_den_aufgaben_1_bis_6(self) -> None:
        app = self.app
        haken = {"ampr": "ampr_integrate_var", "voll": "_ampr_voll_var", "playgo": "ampr_playgo_var",
                 "dlc": "dlc_integrate_var", "backport": "backport_integrate_var"}
        combos = {"kompression": "compression_level_var", "pruefung": "verify_var", "version": "ampr_version_var",
                  "methode": "ampr_methode_var", "packverfahren": "_ampr_pack_var", "packstufe": "_ampr_stufe_var",
                  "backport_fw": "backport_fw_var"}
        for name, var in haken.items():
            with self.subTest(haken=name):
                self.assertEqual(str(getattr(app, var)), self.karte.felder[name].cget("variable"))
        for name, var in combos.items():
            with self.subTest(combo=name):
                self.assertEqual(str(getattr(app, var)), self.karte.felder[name].cget("textvariable"))
        self.assertIn("worker", self.karte.felder)

    def test_ein_klick_aufs_kaestchen_ist_ein_klick_in_den_aufgaben_1_bis_6(self) -> None:
        app = self.app
        for name, var in (("dlc", "dlc_integrate_var"), ("playgo", "ampr_playgo_var"), ("backport", "backport_integrate_var")):
            with self.subTest(haken=name), mock.patch.object(app, "_on_integration_changed") as befehl:
                vorher = getattr(app, var).get()
                self.karte.felder[name].invoke()
                self.assertEqual(not vorher, getattr(app, var).get(), "dieselbe Variable wie im Hauptfenster")
                befehl.assert_called_once_with()

    def test_eine_wahl_in_einer_liste_ruft_den_befehl_des_hauptfensters(self) -> None:
        befehle = {"kompression": "_on_compression_level_changed", "pruefung": "_on_verify_stufe_changed",
                   "version": "_ampr_version_gewaehlt", "methode": "_ampr_methode_gewaehlt",
                   "packverfahren": "_ampr_pack_gewaehlt", "packstufe": "_ampr_stufe_gewaehlt",
                   "backport_fw": "_backport_fw_gewaehlt"}
        for name, befehl in befehle.items():
            with self.subTest(liste=name), mock.patch.object(self.app, befehl) as m:
                self.karte.felder[name].event_generate("<<ComboboxSelected>>")
                m.assert_called_once()

    def test_die_befehle_der_listen_stehen_im_hauptfenster_und_nicht_mehr_als_lambda(self) -> None:
        """Die Liste im Hauptfenster und die Zwillingsliste hier rufen dieselbe Methode - eine Stelle fuer beide."""
        text = Path(APP.__file__).read_text(encoding="utf-8")
        for name in ("_ampr_version_gewaehlt", "_ampr_methode_gewaehlt", "_backport_fw_gewaehlt"):
            with self.subTest(befehl=name):
                self.assertIn("def %s(self)" % name, text)
                self.assertIn("lambda _e: self.%s()" % name, text)

    def test_die_methode_ruft_wie_bisher_alle_drei_nachfolger(self) -> None:
        """Der Wechsel der Methode prueft die Voraussetzungen, schaltet die Packfelder und bewertet die Zielformat-Liste neu."""
        with mock.patch.object(self.app, "_on_ampr_methode_changed") as a, \
                mock.patch.object(self.app, "_ampr_pack_combo_schalten") as b, \
                mock.patch.object(self.app, "_refresh_target_format_options") as c:
            self.app._ampr_methode_gewaehlt()
        for m in (a, b, c):
            m.assert_called_once_with()

    def test_listen_und_sperren_kommen_aus_dem_hauptfenster(self) -> None:
        app, karte = self.app, self.karte
        alt_werte = tuple(app.ampr_version_combo.cget("values"))
        alt_zustand = str(app.backport_fw_combo.cget("state"))
        self.addCleanup(app.ampr_version_combo.configure, values=alt_werte)
        self.addCleanup(app.backport_fw_combo.configure, state=alt_zustand)
        app.ampr_version_combo.configure(values=("Alpha 1", "Beta 2"))
        app.backport_fw_combo.configure(state="disabled")
        karte.abgleichen(True, True)
        self.assertEqual(("Alpha 1", "Beta 2"), karte.felder["version"].values)
        self.assertEqual("disabled", karte.felder["backport_fw"].cget("state"))
        app.backport_fw_combo.configure(state="readonly")
        karte.abgleichen(True, True)
        self.assertEqual("readonly", karte.felder["backport_fw"].cget("state"))

    def test_die_kompression_ist_nur_beim_container_frei(self) -> None:
        karte = self.karte
        karte.abgleichen(True, False)
        self.assertEqual("disabled", karte.felder["kompression"].cget("state"))
        self.assertEqual(str(self.app.compression_combo.cget("state")), karte.felder["pruefung"].cget("state"),
                         "die Pruefung bleibt wie im Hauptfenster")
        self.f._format_waehlen("ffpfsc")
        self.f._einbau_abgleichen()
        self.assertNotEqual("disabled", karte.felder["kompression"].cget("state"))
        self.f._format_waehlen("exfat")
        self.f._einbau_abgleichen()
        self.assertEqual("disabled", karte.felder["kompression"].cget("state"), "bei .exFAT kennt das Format keine Stufe")

    def test_ein_paket_nimmt_den_einbau_nicht_auf_felder_gesperrt_und_der_hinweis_sagt_es(self) -> None:
        karte = self.karte
        self._laden(self._spielordner())
        self.f._format_waehlen("pkg")
        self.f._einbau_abgleichen()
        felder = [n for n in karte.felder if n != "worker"]
        self.assertTrue(all(str(karte.felder[n].cget("state")) == "disabled" for n in felder), "alle gesperrt")
        self.assertEqual(_de("ps5pkg.einbau_nur_abbild"), karte.format_hinweis.cget("text"), "der Hinweis erklaert es")
        self.f._format_waehlen("ffpkg")
        self.f._einbau_abgleichen()
        self.assertNotIn(_de("ps5pkg.einbau_nur_abbild"), karte.format_hinweis.cget("text"), "bei einem Abbild steht er nicht da")
        self.assertTrue(any(str(karte.felder[n].cget("state")) != "disabled" for n in felder))

    def test_der_hinweis_unter_dem_zielformat_ist_der_des_hauptfensters(self) -> None:
        """Wie ``format_info_label`` der Aufgaben 1 bis 6: das Ziel, bei den PFS-Containern Tempo und Empfehlung, sonst die
        Einstufung des Autors von ShadowMount+."""
        karte = self.karte
        erwartet = {
            "ffpfsc": "\n".join((_de("main.ziel_hint", formats="ffpfsc/ffpfs"), _de("main.pfs_speed_hint"))),
            "ffpfs": "\n".join((_de("main.ziel_hint", formats="ffpfsc/ffpfs"), _de("main.pfs_speed_hint"))),
            "ffpkg": "\n".join((_de("main.ziel_hint", formats=".ffpkg"), _de("main.smp_rang_ffpkg"))),
            "exfat": "\n".join((_de("main.ziel_hint", formats=".exfat"), _de("main.smp_rang_exfat"))),
            "pkg": _de("ps5pkg.einbau_nur_abbild"),
        }
        for format_, text in erwartet.items():
            with self.subTest(format=format_):
                self.f._format_waehlen(format_)
                self.f._einbau_abgleichen()
                self.assertEqual(text, karte.format_hinweis.cget("text"))
        self.f.aktion_var.set("pruefen")
        self.f._einbau_abgleichen()
        self.assertEqual("", karte.format_hinweis.cget("text"), "bei einer Aktion ohne Zielformat steht nichts da")
        self.f.aktion_var.set("umwandeln")

    def test_auch_extrahieren_und_pruefen_nehmen_keinen_einbau(self) -> None:
        self._paket()
        for aktion in ("extrahieren", "pruefen"):
            with self.subTest(aktion=aktion):
                self.f.aktion_var.set(aktion)
                self.assertFalse(self.f._einbau_gilt())
        self.f.aktion_var.set("umwandeln")
        self.f.format_schluessel = "ffpkg"
        self.assertTrue(self.f._einbau_gilt())

    def test_die_einbau_gruppe_hat_die_zwei_zeilen_der_aufgaben_1_bis_6(self) -> None:
        """Zeile 1: AMPR EMU, Methode, Pfeil, Fassung, PlayGo, BACKPORT, Firmware. Zeile 2: DLC EMU, Packverfahren, Pfeil,
        Packstufe, vollstaendige Pruefung - in einem Raster, die Spalten stehen buendig untereinander."""
        self.karte._schmal_setzen(False)               # die breite Form (bei schmaler Karte steht der Rest in Zeile 3)
        felder = self.karte.felder
        ort = {n: (felder[n].grid_info()["row"], felder[n].grid_info()["column"]) for n in felder
               if n in ("ampr", "methode", "version", "playgo", "backport", "backport_fw", "dlc", "packverfahren", "packstufe", "voll")}
        self.assertEqual({"ampr": (1, 0), "methode": (1, 1), "version": (1, 3), "playgo": (1, 4), "backport": (1, 5),
                          "backport_fw": (1, 6), "dlc": (2, 0), "packverfahren": (2, 1), "packstufe": (2, 3), "voll": (2, 5)}, ort)
        self.assertEqual({"methode", "pack", "kompression", "worker", "pruefung"}, set(self.karte._pfeile),
                         "ein Pfeil zwischen Methode und Fassung, Verfahren und Stufe und in der Zeile des Zielformats")

    def _wo(self) -> "dict[str, tuple[int, int]]":
        felder = self.karte.felder
        return {n: (felder[n].grid_info()["row"], felder[n].grid_info()["column"])
                for n in ("playgo", "backport", "backport_fw", "voll")}

    def test_die_gruppe_steht_rechts_neben_der_zeile_und_bei_schmaler_karte_darunter(self) -> None:
        """Nutzerwunsch 17.11.2026: BEIM ERSTELLEN EINBAUEN steht rechts neben PRUEFUNG in zwei Zeilen, wie bei Aufgabe 1. Reicht die
        Breite nicht: daneben in drei Zeilen, dann darunter (in zwei Zeilen, wenn sie so passen, sonst in drei)."""
        karte = self.karte
        self.f.win.update_idletasks()                  # erst dann kennt Tk die Breite der Felder
        reihe = karte.reihe.winfo_reqwidth() + einbau_ui.GRUPPE_LUFT
        breit, schmal = karte._gruppe_breiten()
        self.assertGreater(breit, schmal, "in drei Zeilen ist die Gruppe schmaler")
        self.assertLessEqual(reihe + breit, 1295, "daneben passt sie bei einem 1920er Fenster (Karte 1295 px) in zwei Zeilen")
        drei = {"playgo": (1, 4), "backport": (3, 0), "backport_fw": (3, 1), "voll": (3, 3)}
        zwei = {"playgo": (1, 4), "backport": (1, 5), "backport_fw": (1, 6), "voll": (2, 5)}
        faelle = ((3000, True, zwei, (0, 1)),                       # Platz: daneben, zwei Zeilen
                  (reihe + breit, True, zwei, (0, 1)),              # gerade noch
                  (reihe + breit - 1, True, drei, (0, 1)),          # knapp nicht mehr: daneben, drei Zeilen
                  (reihe + schmal, True, drei, (0, 1)),
                  (reihe + schmal - 1, False, zwei, (2, 0)),        # darunter, zwei Zeilen
                  (breit, False, zwei, (2, 0)),
                  (breit - 10, False, drei, (2, 0)),                # zu schmal fuer zwei Zeilen: drei
                  (3000, True, zwei, (0, 1)))
        for breite, neben, ort, grid in faelle:
            with self.subTest(breite=breite), mock.patch.object(karte.rahmen, "winfo_width", return_value=breite):
                karte._platz_pruefen()
                self.assertEqual(neben, karte._neben)
                info = karte.rechts.grid_info()
                self.assertEqual(grid, (info["row"], info["column"]))
                self.assertEqual(ort, self._wo())

    def test_daneben_steht_die_gruppe_oben_rechts_von_der_pruefung(self) -> None:
        karte = self.karte
        with mock.patch.object(karte.rahmen, "winfo_width", return_value=3000):
            karte._platz_pruefen()
            self.f.win.update_idletasks()
            pruefung = karte.felder["pruefung"]
            self.assertGreaterEqual(karte.rechts.winfo_rootx(), pruefung.winfo_rootx() + pruefung.winfo_width(),
                                    "rechts neben PRUEFUNG")
            self.assertLessEqual(abs(karte.rechts.winfo_rooty() - karte.reihe.winfo_rooty()), 2, "in Hoehe der Zeile")
            self.assertLessEqual(abs(karte.rechts.winfo_rootx() - karte.reihe.winfo_rootx() - karte.reihe.winfo_width()
                                     - einbau_ui.GRUPPE_LUFT), 2, "mit dem Abstand der Aufgaben 1 bis 6")

    def test_bei_mindestgroesse_ragt_nichts_aus_der_karte_und_nichts_springt_hin_und_her(self) -> None:
        """Bei Mindestgroesse (1245 px) ragte die Zeile 39 px aus der Karte (``test_pkg_fpkg_seite``)."""
        karte = self.karte
        self.f.win.update_idletasks()
        breit, schmal = karte._gruppe_breiten()
        with mock.patch.object(karte.rahmen, "winfo_width", return_value=breit - 20):
            karte._platz_pruefen()
            self.f.win.update_idletasks()
            self.assertEqual({"playgo": (1, 4), "backport": (3, 0), "backport_fw": (3, 1), "voll": (3, 3)}, self._wo())
            self.assertLessEqual(karte.rechts.winfo_reqwidth(), breit - 20, "danach passt die Gruppe in die Karte")
            gemessen = karte._gruppe_breiten()
            karte._platz_pruefen()
            self.assertEqual(gemessen, karte._gruppe_breiten(), "die Messung haengt nicht davon ab, wie die Gruppe gerade liegt")
            self.assertEqual((3, 0), self._wo()["backport"], "und nichts springt zurueck, solange es eng ist")

    def test_die_leiste_hat_nur_starten_und_abbrechen_wie_aufgabe_1(self) -> None:
        """Nutzerwunsch 17.11.2026: die Knopfleiste "ist nicht gleich" - ohne "Updates Online", "Dateien anzeigen", "Details", "Optionen"."""
        f = self.f
        self.assertEqual(self.app._t("action.start"), str(f.start_knopf.cget("text")), "derselbe Text wie bei Aufgabe 1")
        kinder = set(f.leiste.winfo_children())
        self.assertEqual({f.start_knopf, f.abbrechen_knopf, f.balken_gesamt, f.prozent_label, f.groesse_label}, kinder,
                         "STARTEN, ABBRECHEN, Fortschrittsbalken, Prozentzahl und Text - wie die Aktionsleiste der Aufgabe 1")
        for name in ("update_knopf", "browser_knopf", "detail_knopf", "optionen_knopf"):
            self.assertFalse(hasattr(f, name), name)

    def test_fortschrittsbalken_prozent_und_text_stehen_wie_in_den_aufgaben_1_bis_6(self) -> None:
        """Nutzerwunsch 17.11.2026: Balken samt Prozentzahl nur im Lauf (``progress``/``percent_label``), der Text rechts daneben
        (``size_label``: im Leerlauf die Groesse der Quelle, im Lauf die Dateizeile), die Statuszeile rechts unten, kursiv."""
        f = self.f
        self._laden(self._spielordner())
        f._takt_arbeiten()
        f.win.update_idletasks()
        self.assertFalse(f.balken_gesamt.winfo_manager(), "im Leerlauf ist der Balken nicht da")
        self.assertFalse(f.prozent_label.winfo_manager())
        self.assertEqual(f._fmt(8192), f.groesse_var.get(), "im Leerlauf steht die Groesse der Quelle da")
        f._job = {"art": "bauen", "info": f.aktuell, "ziel": "", "start": time.monotonic() - 169,
                  "letzte": time.monotonic(), "zeichen": None}
        try:
            f._anzeige_setzen(45, 30)
            f.datei_var.set("Komprimieren · 11.4 GB / 37.6 GB")
            f._takt_arbeiten()
            f.win.update_idletasks()
            self.assertEqual("grid", f.balken_gesamt.winfo_manager(), "im Lauf ist er da")
            self.assertEqual("grid", f.prozent_label.winfo_manager())
            self.assertEqual("30 %", f.prozent_var.get(), "die Prozentzahl gehoert zum sichtbaren Balken (Gesamtstand)")
            self.assertEqual(30.0, float(f.balken_gesamt.cget("value")))
            self.assertEqual("Komprimieren · 11.4 GB / 37.6 GB", f.groesse_var.get(), "im Lauf die Dateizeile")
            self.assertIn("2:49", f.lebt_var.get())
            self.assertEqual("grid", f.lebt_label.winfo_manager(), "das Lebenszeichen steht unter der Statuszeile")
        finally:
            f._job = None
        f._takt_arbeiten()
        f.win.update_idletasks()
        self.assertFalse(f.balken_gesamt.winfo_manager(), "nach dem Lauf wieder weg")
        self.assertFalse(f.lebt_label.winfo_manager())
        self.assertEqual("e", str(f.status_label.cget("anchor")), "die Statuszeile steht rechts")
        self.assertIn("italic", str(f.status_label.cget("font")), "und kursiv, wie bei den Aufgaben 1 bis 6")

    def test_das_protokoll_hat_schrift_und_zeilenabstand_der_aufgaben_1_bis_6(self) -> None:
        f = self.f
        self.assertEqual(0, int(float(f.protokoll.cget("spacing3") or 0)), "Zeile an Zeile, ohne Abstand nach jeder Meldung")

    def test_der_zaehler_steht_nur_bei_mehreren_quellen_da(self) -> None:
        f = self.f
        self._laden(self._spielordner("A", "PPSA00011", "Eins"))
        f._liste_fuellen()
        self.assertFalse(f.zaehler_label.winfo_manager(), "bei einer Quelle steht kein Zaehler da")
        self._laden(self._spielordner("B", "PPSA00012", "Zwei"))
        f._liste_fuellen()
        self.assertEqual("grid", f.zaehler_label.winfo_manager(), "bei zwei Quellen steht er links unten")

    def test_zu_wenig_platz_macht_nur_das_feld_zielformat_schmaler(self) -> None:
        """Bei Mindestgroesse (1245 px) war die Zeile bis PRUEFUNG 18 px zu breit (``test_pkg_fpkg_seite``)."""
        karte, box = self.karte, self.f.format_box
        self.f.win.update_idletasks()
        karte._eng = False
        voll = box.winfo_reqwidth()
        reihe = karte.reihe.winfo_reqwidth()
        with mock.patch.object(karte.rahmen, "winfo_width", return_value=reihe - 10):
            karte._platz_pruefen()
            self.f.win.update_idletasks()
            self.assertTrue(karte._eng)
            self.assertLess(box.winfo_reqwidth(), voll, "das Feld ZIELFORMAT ist schmaler")
            self.assertLessEqual(karte.reihe.winfo_reqwidth(), reihe - 10, "die Zeile passt")
            karte._platz_pruefen()
            self.assertTrue(karte._eng, "und springt nicht zurueck, solange es eng ist")
        with mock.patch.object(karte.rahmen, "winfo_width", return_value=3000):
            karte._platz_pruefen()
            self.f.win.update_idletasks()
        self.assertFalse(karte._eng)
        self.assertEqual(voll, box.winfo_reqwidth(), "bei Platz wieder nach dem laengsten Eintrag")

    def test_die_zusatzfunktionen_liegen_im_rechtsklick_menue_des_protokolls(self) -> None:
        f = self.f
        namen = {"update": "ps5pkg.btn_update", "browser": "ps5pkg.browser_button", "detail": "ps5pkg.detail_button",
                 "optionen": "ps5pkg.nav_options"}
        for name, schluessel in namen.items():
            with self.subTest(eintrag=name):
                self.assertEqual(_de(schluessel), f.protokoll_menue.entrycget(f._menue_eintraege[name], "label"))
        zustand = lambda n: str(f.protokoll_menue.entrycget(f._menue_eintraege[n], "state"))   # noqa: E731
        self._laden(self._spielordner())                       # ein Spielordner mit PS5-Kennung
        f._knoepfe_pruefen()
        self.assertEqual(("normal", "normal", "normal"), (zustand("update"), zustand("detail"), zustand("optionen")))
        self._laden(self._abbild())                            # ein Abbild hat keine Detailansicht eines Ordners
        f._knoepfe_pruefen()
        self.assertEqual(("normal", "disabled", "normal"), (zustand("update"), zustand("detail"), zustand("optionen")))
        for aufruf, eintrag in (("_updates_online", "update"), ("_browser_oeffnen", "browser"), ("_detail_oeffnen", "detail")):
            with self.subTest(aufruf=aufruf), mock.patch.object(fz.Ps5PkgFenster, aufruf) as m:
                # Der Befehl des Eintrags wird hier ersetzt; sein Zustand ist oben geprueft (ein gesperrter Eintrag ruft nichts).
                f.protokoll_menue.entryconfigure(f._menue_eintraege[eintrag], command=m, state="normal")
                f.protokoll_menue.invoke(f._menue_eintraege[eintrag])
                m.assert_called_once_with()

    def test_die_felder_sind_kompakt_und_zeigen_ihren_text_vollstaendig(self) -> None:
        """Nutzerwunsch 17.11.2026 (Bild der Aufgabe 1): so schmale Felder wie dort - mit engem Rand und kleinem Pfeil; der Text bleibt
        ganz (kein "..." im Feld) fuer jeden Wert, den die Liste anbietet."""
        karte = self.karte
        self.f.win.update_idletasks()
        for name in ("kompression", "pruefung", "version", "methode", "packverfahren", "packstufe", "backport_fw"):
            with self.subTest(feld=name):
                feld = karte.felder[name]
                self.assertTrue(feld._kompakt, "die Pille ist kompakt")
        self.assertTrue(self.f.format_box._kompakt)
        # Der laengste Wert, der in der Liste steht, ohne Auslassung: Breite - Rand (30 design px) reicht fuer die Schrift.
        z = self.f.format_box._z
        # JEDER Wert der Liste, auch von Methode, Packverfahren und Packstufe: Bis zum 19.11.2026 pruefte der Test dort nur, was gerade
        # gewaehlt war - "Asset-Pack" (82 px in einer Pille fuer 74 px) und "12 · am kleinsten" (128 px in 119 px) standen unbemerkt als
        # "Asset-P..." und "12 · am..." in der Pille. Gemessen am echten Fenster (``knopf_zeichnen`` kuerzt zu langen Text mit "...").
        for name in ("kompression", "pruefung", "methode", "packverfahren", "packstufe", "backport_fw"):
            feld = karte.felder[name]
            for wert in list(feld.values):
                with self.subTest(feld=name, wert=wert):
                    self.assertLessEqual(z.messen("knopf", wert), int(feld.winfo_reqwidth()) - z.px(30),
                                         "der Text passt in die Pille")
                    variable = getattr(self.app, einbau_ui.COMBOS[name][0])
                    vorher = variable.get()
                    self.addCleanup(variable.set, vorher)
                    variable.set(wert)
                    self.assertEqual(wert, feld.itemcget(feld._knopf.text, "text"), "die Pille zeigt den Wert ganz, ohne Auslassung")
                    variable.set(vorher)
        self.assertLessEqual(karte.reihe.winfo_reqwidth() + einbau_ui.GRUPPE_LUFT + karte._gruppe_breiten()[0], 1295,
                             "die Gruppe passt in zwei Zeilen neben die Zeile (Karte 1295 px beim 1920er Fenster)")

    def test_die_breite_der_gruppe_rechnet_mit_den_spannen(self) -> None:
        """Die Packstufe reicht ueber die Spalten 3 und 4, die Pruefung ueber 5 und 6: Sie schieben Zeile 1 nur, wenn sie dort nicht mehr
        Platz finden. Mit festen Breiten gerechnet (die Felder selbst sind so breit, dass die Pruefung gerade hineinpasst)."""
        class Feld:
            def __init__(self, breite: int) -> None:
                self.breite = breite

            def winfo_reqwidth(self) -> int:
                return self.breite

        karte = self.karte
        alt = karte.felder
        basis_breiten = dict(ampr=100, dlc=90, methode=110, packverfahren=90, version=120, packstufe=170, playgo=70, backport=100,
                             backport_fw=60)
        try:
            karte.felder = {n: Feld(w) for n, w in dict(basis_breiten, voll=100).items()}
            klein = karte._gruppe_breiten()
            karte.felder = {n: Feld(w) for n, w in dict(basis_breiten, voll=400).items()}
            gross = karte._gruppe_breiten()
        finally:
            karte.felder = alt
        pfeil = 20 if karte._pfeile.get("methode") is not None else 0
        links = 100 + 8 + 110 + pfeil                         # AMPR/DLC, Luft, Methode/Verfahren, Pfeil
        schmal = links + 120 + max(10 + 70, 170 - 120)        # Fassung, dann PlayGo oder der Rest der Packstufe
        self.assertEqual((schmal + max(14 + 100 + 6 + 60, 10 + 100) + 4, schmal + 4), klein,
                         "die Pruefung passt hinter BACKPORT und Firmware: Zeile 1 bleibt, wie sie ist")
        self.assertEqual((schmal + 10 + 400 + 4, schmal + 4), gross, "ist sie breiter, schiebt sie die Zeile")

    def test_der_sichtbare_balken_wandert_mit_wenn_die_dauer_unbekannt_ist(self) -> None:
        f = self.f
        f._balken_wandern(True)
        try:
            self.assertEqual("indeterminate", str(f.balken_gesamt.cget("mode")), "der Balken in der Leiste wandert")
            self.assertEqual("…", f.prozent_var.get())
        finally:
            f._balken_wandern(False)
        self.assertEqual("determinate", str(f.balken_gesamt.cget("mode")))

    def test_die_pfeile_sind_blass_wenn_das_feld_rechts_gesperrt_ist(self) -> None:
        karte = self.karte
        karte.abgleichen(False, False)                 # ein Paket: alles gesperrt
        self.assertFalse(karte._pfeile["kompression"]._aktiv)
        self.assertFalse(karte._pfeile["methode"]._aktiv)
        self.assertTrue(karte._pfeile["worker"]._aktiv, "der Drehknopf hat keine Sperre")
        karte.abgleichen(True, True)
        self.assertTrue(karte._pfeile["kompression"]._aktiv)

    def test_die_kurzinfos_der_karte_haengen_nicht_am_hauptfenster(self) -> None:
        """``g._tooltip`` haelt jede Kurzinfo samt Feld fuer immer fest - je Fenster blieben 4 GDI-Objekte stehen
        (``test_fenster_leck``, 17.11.2026). Die Karte legt ihre Kurzinfos selbst an."""
        vorher = len(getattr(self.app, "_tooltip_schluessel", []))
        # ``oeffnen`` gibt die vorhandene Seite zurueck - ein zweites, eigenes Fenster baut nur der Konstruktor.
        zweites = fz.Ps5PkgFenster(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt, "")
        try:
            self.assertIsNot(zweites, self.f)
            self.assertGreater(len(zweites.einbau._kurzinfos), 5, "die Karte hat ihre Kurzinfos")
            self.assertEqual(vorher, len(getattr(self.app, "_tooltip_schluessel", [])))
        finally:
            zweites._schliesst = True
            zweites.win.destroy()
            basis._pumpen(0.05)

    def test_die_kurzinfos_mit_wechselndem_text_folgen_dem_hauptfenster(self) -> None:
        app, karte = self.app, self.karte
        alt = app._ampr_pack_tooltip.text
        self.addCleanup(setattr, app._ampr_pack_tooltip, "text", alt)
        app._ampr_pack_tooltip.text = "Gesperrt, weil kein Asset-Pack"
        karte.abgleichen(True, True)
        self.assertEqual("Gesperrt, weil kein Asset-Pack", karte._kurzinfos["packverfahren"].text)

    def test_der_takt_gleicht_ab_aber_nur_wenn_die_seite_zu_sehen_ist(self) -> None:
        with mock.patch.object(self.karte, "abgleichen") as abgleichen:
            self.f._takt_arbeiten()
            abgleichen.assert_called_once()
            abgleichen.reset_mock()
            self.f._rest_sichtbar = False
            try:
                self.f._takt_arbeiten()
            finally:
                self.f._rest_sichtbar = True
            abgleichen.assert_not_called()

    def test_kompression_worker_und_pruefung_stehen_in_der_zeile_des_zielformats(self) -> None:
        self.f._seite_zeigen("umwandeln")
        basis._pumpen(0.3)
        self.f.win.update_idletasks()
        y = self.f.format_box.winfo_rooty()
        for name in ("kompression", "worker", "pruefung"):
            with self.subTest(feld=name):
                feld = self.karte.felder[name]
                self.assertEqual(self.f.format_box.master.master, feld.master.master, "in derselben Zeile")
                self.assertGreater(feld.winfo_rootx(), self.f.format_box.winfo_rootx())
                self.assertLess(abs(feld.winfo_rooty() - y), 12, "auf gleicher Hoehe wie das Zielformat")

    # ---------------- die Pruefung der Quelle: wie in den Aufgaben 1 bis 6 im Protokoll ----------------
    def test_nach_der_wahl_steht_die_pruefung_der_aufgaben_1_bis_6_im_protokoll(self) -> None:
        """Nutzerwunsch 17.11.2026: "automatisch im Spiel nach DLC, PlayGo, LZ4, zstd und AMPR EMU Inhalt gesucht, wie in
        Aufgabe 1-6 bereits" - dieselben ``[Pruefung]``-Zeilen, sobald die Quelle gewaehlt ist (kein eigenes Feld)."""
        ordner = self._spielordner()
        with mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten()):
            self._laden(ordner)
            self.assertTrue(basis._warten(lambda: "[Prüfung]" in self._protokoll_text(), 8), "die Pruefung kommt von selbst")
        text = self._protokoll_text()
        self.assertIn(_de("einbau_pruefung.nichts", name="Spielordner").strip(), text)
        self.assertIn(_de("einbau_pruefung.playgo_nicht_noetig").strip(), text)

    def test_die_zeilen_sind_die_der_aufgaben_1_bis_6_und_kommen_aus_einer_stelle(self) -> None:
        zeilen = ["[Prüfung] Alpha: bereits eingebaut – AMPR EMU.\n", "[Prüfung] PlayGo nicht nötig: keine PlayGo-Dateien im Spiel.\n"]
        ordner = self._spielordner()
        with mock.patch.object(self.app, "_quelle_einbauten_zeilen", return_value=zeilen) as m, \
                mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten()):
            self._laden(ordner)
            self.assertTrue(basis._warten(lambda: "bereits eingebaut" in self._protokoll_text(), 8))
        self.assertEqual(ordner, m.call_args[0][0])
        self.assertEqual(self.f._ist_aktive_aufgabe, m.call_args[0][2],
                         "nur die aktive Aufgabe 7 darf die gemeinsamen Haken setzen (dritter Parameter ``haken_gilt``)")
        self.assertIn("[Prüfung] Alpha: bereits eingebaut – AMPR EMU.\n", self._protokoll_text())
        self.assertNotIn("AMPR EMU.\n\n", self._protokoll_text(), "das Zeilenende der Meldung kommt nicht doppelt")

    def test_dieselbe_quelle_wird_nur_einmal_gemeldet(self) -> None:
        ordner = self._spielordner()
        with mock.patch.object(self.app, "_quelle_einbauten_zeilen", return_value=["[Prüfung] X\n"]) as m, \
                mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten()):
            self._laden(ordner)
            self.assertTrue(basis._warten(lambda: "[Prüfung] X" in self._protokoll_text(), 8))
            self.f._bericht_aktualisieren()
            self.f._bericht_aktualisieren()
            basis._pumpen(0.3)
        self.assertEqual(1, m.call_count)
        self.assertEqual(1, self._protokoll_text().count("[Prüfung] X"))

    def test_kommt_die_seite_wieder_nach_vorn_werden_nur_die_haken_nachgezogen(self) -> None:
        """Aufgabe 1 hakt PlayGo/DLC fuer ihr Spiel an, die Seite zeigt noch ihr eigenes: Beim erneuten Zeigen gehoeren die Haken wieder
        zum Spiel der Seite (Gegenlese 19.11.2026). Ohne neue ``[Pruefung]``-Zeilen und ohne zweites ``inspect``."""
        ordner = self._spielordner()
        # ``None``: Die Fakten gelten als nicht gelesen (``info.fakten`` bleibt leer) - ein zweiter Lauf, der sie nicht ausdruecklich
        # auslaesst, riefe ``inspect`` noch einmal.
        with mock.patch.object(self.app, "_quelle_einbauten_zeilen", return_value=["[Prüfung] X\n"]) as m, \
                mock.patch.object(fc, "quellfakten_lesen", return_value=None) as fakten:
            self._laden(ordner)
            self.assertTrue(basis._warten(lambda: "[Prüfung] X" in self._protokoll_text(), 8))
            self.assertTrue(basis._warten(lambda: not self.f._pruefung_laeuft(self.f.aktuell), 8))
            self.assertIsNone(self.f.aktuell.fakten)
            self.f.haken_nachziehen()
            self.assertTrue(basis._warten(lambda: m.call_count == 2, 8), "die Pruefung der Haken laeuft noch einmal")
            self.assertTrue(basis._warten(lambda: not self.f._pruefung_laeuft(self.f.aktuell), 8))
            basis._pumpen(0.3)
        self.assertEqual(1, self._protokoll_text().count("[Prüfung] X"), "die Zeilen stehen nicht doppelt im Protokoll")
        self.assertEqual(1, fakten.call_count, "kein zweites inspect")
        self.assertEqual("normal", str(self.f.start_knopf.cget("state")))

    def test_ohne_spiel_nimmt_die_seite_beim_zeigen_die_automatischen_haken_zurueck(self) -> None:
        self.assertIsNone(self.f.aktuell)
        with mock.patch.object(self.app, "_haken_auto_zuruecknehmen") as zurueck:
            self.f.haken_nachziehen()
        zurueck.assert_called_once_with()

    def test_waehrend_eines_laufs_wird_nichts_nachgezogen(self) -> None:
        self._laden(self._spielordner())
        with mock.patch.object(self.app, "_quelle_einbauten_zeilen", return_value=["x\n"]) as m:
            self.f._job = {"art": "bauen"}
            try:
                self.f.haken_nachziehen()
            finally:
                self.f._job = None
            basis._pumpen(0.3)
        self.assertEqual(0, m.call_count)

    def test_ein_spielordner_wird_im_hintergrund_geprueft_und_der_bau_liest_nicht_noch_einmal(self) -> None:
        def langsam(*a, **k):
            time.sleep(1.5)
            return fc.QuellFakten(**self._DLC)
        ordner = self._spielordner()
        with mock.patch.object(fc, "quellfakten_lesen", side_effect=langsam) as lesen:
            self._laden(ordner, warten=False)
            info = self.f.aktuell
            self.assertIsNone(info.fakten)
            fakten = self.f._quellfakten(info)                       # ein Bau, der jetzt startet, wartet auf den Faden
            self.assertIsNotNone(fakten)
            self.assertEqual(1, lesen.call_count, "nicht noch einmal gelesen")

    def test_die_pruefmeldung_steht_schon_waehrend_des_wartens_auf_den_faden_der_karte(self) -> None:
        """Ein Bau, der startet, solange die Karte die Quelle noch liest, wartet bis zu 60 s auf sie (Ghost of Yotei: ``inspect`` rund
        230 s). Die Meldung "Pruefe, was der Quelle fehlt" muss davor stehen, nicht erst nach dem Warten."""
        def langsam(*a, **k):
            time.sleep(1.5)
            return fc.QuellFakten(**self._DLC)
        ordner = self._spielordner()
        zeitpunkte: list = []
        with mock.patch.object(fc, "quellfakten_lesen", side_effect=langsam):
            self._laden(ordner, warten=False)
            info = self.f.aktuell
            self.assertIsNone(info.fakten)
            faden = self.f._bericht_faden[1]
            meldung = self.f.t("ps5pkg.emu_pruefen")
            with mock.patch.object(self.f, "_status", side_effect=lambda text: zeitpunkte.append((text, faden.is_alive()))):
                self.assertIsNotNone(self.f._quellfakten(info))
        self.assertEqual([(meldung, True)], zeitpunkte, "einmal, und zwar noch waehrend der Faden liest")

    def test_waehrend_dump_forge_im_hintergrund_liest_zeigt_die_seite_ein_lebenszeichen(self) -> None:
        """Nutzerwunsch 18.11.2026: ``inspect`` meldet bei einem sehr grossen Spielordner (Ghost of Yotei: rund 230 s) nichts, die Seite
        zeigte keinen Fortschritt. Jetzt steht rechts unten, seit wann geprueft wird - und danach ist die Zeile wieder weg."""
        frei = threading.Event()
        self.addCleanup(frei.set)

        def langsam(*a, **k):
            frei.wait(20)
            return fc.QuellFakten(**self._DLC)
        ordner = self._spielordner()
        with mock.patch.object(fz.Ps5PkgFenster, "PRUEFUNG_LEBT_AB", 0.2), \
                mock.patch.object(fc, "quellfakten_lesen", side_effect=langsam):
            self._laden(ordner, warten=False)
            self.assertTrue(basis._warten(lambda: "Dump Forge prüft das Spiel seit" in self.f.lebt_var.get(), 8), self.f.lebt_var.get())
            self.assertTrue(self.f.lebt_label.winfo_manager(), "das Lebenszeichen steht im Raster")
            self.assertRegex(self.f.lebt_var.get(), r"seit \d+:\d\d ")
            frei.set()
            self.assertTrue(basis._warten(lambda: self.f.lebt_var.get() == "", 8), "nach dem Lesen verschwindet es wieder")

    def test_ein_schnelles_spiel_bekommt_kein_lebenszeichen(self) -> None:
        """Die meisten Spiele sind nach weniger als einer Sekunde durch - fuer sie blitzt keine Zeile auf (Schwelle ``PRUEFUNG_LEBT_AB``)."""
        def kurz(*a, **k):
            time.sleep(1.0)                              # liest eine Weile, aber unter der Schwelle (hier 30 s statt 3 s)
            return fc.QuellFakten(**self._DLC)
        ordner = self._spielordner()
        gesehen: list = []
        with mock.patch.object(fz.Ps5PkgFenster, "PRUEFUNG_LEBT_AB", 30.0), \
                mock.patch.object(fc, "quellfakten_lesen", side_effect=kurz):
            self._laden(ordner, warten=False)
            ende = time.monotonic() + 10.0
            while time.monotonic() < ende and self.f.aktuell.fakten is None:
                basis._pumpen(0.05)
                gesehen.append(self.f.lebt_var.get())
            basis._pumpen(0.2)
            gesehen.append(self.f.lebt_var.get())
        self.assertIsNotNone(self.f.aktuell.fakten, "die Pruefung wurde fertig")
        self.assertGreater(len(gesehen), 10, "die Seite wurde waehrend des Lesens beobachtet")
        self.assertEqual({""}, set(gesehen))

    def test_das_lebenszeichen_zeigt_nie_die_pruefung_einer_anderen_quelle(self) -> None:
        frei = threading.Event()
        self.addCleanup(frei.set)
        fremd = threading.Thread(target=frei.wait, args=(20,), daemon=True)
        fremd.start()
        self.addCleanup(fremd.join, 1)
        ordner = self._spielordner()
        self._laden(ordner)
        with mock.patch.object(fz.Ps5PkgFenster, "PRUEFUNG_LEBT_AB", 0.0):
            self.f._bericht_faden, self.f._bericht_start = (object(), fremd), time.monotonic() - 30
            self.assertEqual("", self.f._pruefung_lebt(), "ein Faden, der zu einer anderen Quelle gehoert")
            self.f._bericht_faden = (self.f.aktuell, fremd)
            self.assertIn("0:3", self.f._pruefung_lebt(), "derselbe Faden, jetzt zur gewaehlten Quelle")

    def test_das_lebenszeichen_gehoert_zur_gewaehlten_quelle(self) -> None:
        """Wurde inzwischen ein anderes Spiel gewaehlt, zeigt die Seite nicht mehr die Zeit der alten Pruefung."""
        a, b = self._spielordner("A", "PPSA00011", "Eins"), self._spielordner("B", "PPSA00012", "Zwei")
        frei = threading.Event()
        self.addCleanup(frei.set)

        def langsam(werkzeug, pfad, **k):
            if pfad == a:
                frei.wait(20)
            return fc.QuellFakten(**self._DLC)
        with mock.patch.object(fz.Ps5PkgFenster, "PRUEFUNG_LEBT_AB", 0.2), \
                mock.patch.object(fc, "quellfakten_lesen", side_effect=langsam):
            self._laden(a, warten=False)
            self.assertTrue(basis._warten(lambda: "Dump Forge prüft" in self.f.lebt_var.get(), 8))
            self._laden(b)
            self.assertTrue(basis._warten(lambda: self.f.aktuell is not None and self.f.aktuell.pfad == b, 8))
            self.assertTrue(basis._warten(lambda: self.f.lebt_var.get() == "", 8), self.f.lebt_var.get())

    def test_das_lebenszeichen_hat_in_jeder_sprache_dieselbe_dauer_marke(self) -> None:
        for sprache in ("de", "en", "es", "it", "fr"):
            with self.subTest(sprache=sprache):
                self.assertIn("{dauer}", STRINGS["ps5pkg.pruefung_lebt"][sprache])

    def test_starten_ist_gesperrt_solange_dump_forge_das_spiel_prueft_und_danach_frei(self) -> None:
        """Ein Bau, der waehrenddessen startete, wartete im Hauptfaden auf die Pruefung und las danach ein zweites Mal (``_quellfakten``):
        bei Ghost of Yotei (``inspect`` rund 216 s) Minuten ohne Rueckmeldung. Seit die Groesse in 14 s gezaehlt ist, deckte die
        Groessensperre das nicht mehr zu."""
        frei = threading.Event()
        self.addCleanup(frei.set)

        def langsam(*a, **k):
            frei.wait(20)
            return fc.QuellFakten(**self._DLC)
        ordner = self._spielordner()
        with mock.patch.object(fc, "quellfakten_lesen", side_effect=langsam):
            self._laden(ordner, warten=False)
            self.assertTrue(basis._warten(lambda: not self.f.aktuell.groesse_offen), "die Groesse ist gezaehlt")
            self.assertTrue(self.f._pruefung_laeuft(self.f.aktuell))
            self.assertEqual("disabled", str(self.f.start_knopf.cget("state")))
            self.f._starten()
            self.assertEqual(self.f.t("ps5pkg.pruefung_wait"), self.f.status_var.get())
            self.assertIsNone(self.f._job)
            frei.set()
            self.assertTrue(basis._warten(lambda: str(self.f.start_knopf.cget("state")) == "normal", 10),
                            "nach der Pruefung ist STARTEN frei")

    def test_eine_haengende_pruefung_sperrt_starten_nicht_fuer_immer(self) -> None:
        """``inspect`` hat keine Zeitgrenze (``PRUEFUNG_SPERRE_MAX``): Nach ihr gibt der Knopf frei, auch wenn der Faden noch haengt."""
        frei = threading.Event()
        self.addCleanup(frei.set)
        ordner = self._spielordner()
        with mock.patch.object(fz.Ps5PkgFenster, "PRUEFUNG_SPERRE_MAX", 0.4), \
                mock.patch.object(fc, "quellfakten_lesen", side_effect=lambda *a, **k: frei.wait(20)):
            self._laden(ordner, warten=False)
            self.assertTrue(basis._warten(lambda: not self.f.aktuell.groesse_offen))
            self.assertTrue(basis._warten(lambda: str(self.f.start_knopf.cget("state")) == "normal", 10), "die Sperre endet nach der Grenze")
            self.assertTrue(self.f._bericht_faden[1].is_alive(), "der Faden haengt noch")
            self.assertFalse(self.f._pruefung_laeuft(self.f.aktuell))

    def test_die_pruefmeldung_nennt_die_dauer_bei_sehr_grossen_spielen(self) -> None:
        """Gemessen 230 s fuer einen Ordner mit 84.218 Dateien; die Meldung sagt es in jeder Sprache (Minuten)."""
        wort = {"de": "Minuten", "en": "minutes", "es": "minutos", "it": "minuti", "fr": "minutes"}
        for sprache, minuten in wort.items():
            with self.subTest(sprache=sprache):
                self.assertIn(minuten, STRINGS["ps5pkg.emu_pruefen"][sprache])

    def test_die_antwort_einer_veralteten_quelle_steht_nicht_im_protokoll(self) -> None:
        a, b = self._spielordner("A", "PPSA00011", "Eins"), self._spielordner("B", "PPSA00012", "Zwei")

        frei = threading.Event()                       # die Antwort der Quelle A kommt erst, wenn B schon gewaehlt ist

        def zeilen(pfad, aktuell=None, haken_gilt=None):
            if pfad == a:
                frei.wait(20)
            return ["[Prüfung] Quelle %s\n" % ("A" if pfad == a else "B")]
        with mock.patch.object(self.app, "_quelle_einbauten_zeilen", side_effect=zeilen), \
                mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten()):
            self._laden(a, warten=False)
            self._laden(b)
            frei.set()
            self.assertTrue(basis._warten(lambda: "Quelle B" in self._protokoll_text(), 8))
            basis._pumpen(1.0)
        self.assertNotIn("Quelle A", self._protokoll_text(), "die Antwort der Quelle A gehoert nicht mehr hierher")

    def test_ein_paket_wird_ueber_dump_forge_geprueft_wenn_die_eigene_sicht_es_nicht_liest(self) -> None:
        """Die eigene Sicht der Aufgaben 1 bis 6 liest kein ``.pkg`` - Dump Forge schon (``inspect``, wie fuer ein ``.ffpkg``)."""
        pfad = os.path.join(self.ordner, "Paket.pkg")
        Path(pfad).write_bytes(b"pkg")
        fakten = fc.QuellFakten(emulatoren=("ampr", "playgo"), gepackt="zstd", backport_vorhanden=True)
        with mock.patch.object(APP.PS5ConverterGUI, "_quellfakten_der_quelle", return_value=fakten):
            zeilen = self.app._quelle_einbauten_zeilen(pfad)
        text = "".join(zeilen)
        self.assertIn(_de("einbau_pruefung.schon_drin", name="Paket.pkg", liste="BACKPORT (?), AMPR EMU, Asset-Pack (zstd), PlayGo").strip(),
                      text, "das Protokoll nennt das Verfahren des Packs (Nutzerwunsch 17.11.2026)")

    # ---------------- Hinweise im Protokoll statt unter der Quelle (Nutzerwunsch 18.11.2026) ----------------
    def _hinweiszeilen(self) -> "list[str]":
        """Die Zeilen mit der Textmarke ``hinweis`` (Tk fasst aneinanderliegende markierte Zeilen zu einem Bereich zusammen)."""
        markiert = self.f.protokoll.tag_ranges("hinweis")
        return [z.strip() for a, e in zip(markiert[0::2], markiert[1::2])
                for z in self.f.protokoll.get(str(a), str(e)).splitlines() if z.strip()]

    def test_die_hinweise_zu_playgo_und_dlc_stehen_orange_im_protokoll_und_nicht_unter_der_quelle(self) -> None:
        """"⚠ PlayGo-Dateien gefunden (...) - PlayGo beim Backup einbinden!" stand als Etikett unter der Quelle; jetzt, wie bei den
        Aufgaben 1 bis 6, im Protokoll - in der Warnfarbe - und mit demselben Hinweis fuer Zusatzinhalte (DLC)."""
        ordner = self._spielordner()
        Path(ordner, "sce_sys", "playgo-scenario.json").write_text("{}", encoding="utf-8")
        os.makedirs(os.path.join(ordner, "addcont0"))
        Path(ordner, "addcont0", "inhalt.pkg").write_bytes(b"x")
        for name in ("ampr_playgo_var", "dlc_integrate_var"):             # das Nachziehen der Haken gehoert nicht in andere Tests
            self.addCleanup(getattr(self.app, name).set, False)
        self.addCleanup(self.app.__dict__.pop, "_haken_auto", None)
        with mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten()):
            self._laden(ordner)
            self.assertTrue(basis._warten(lambda: "⚠ DLC-Inhalte gefunden" in self._protokoll_text(), 10), self._protokoll_text())
        text = self._protokoll_text()
        self.assertIn(_de("pkg.playgo_hinweis", datei="sce_sys/playgo-scenario.json"), text, "wortgleich, wie das Etikett es zeigte")
        self.assertIn(_de("einbau_pruefung.dlc_gefunden", merkmal="addcont0/").strip(), text)
        self.assertEqual("", str(self.f.paket_playgo.cget("text")), "nichts mehr unter der Quelle")
        # Beide Zeilen tragen die Textmarke mit der Warnfarbe.
        zeilen = self._hinweiszeilen()
        self.assertTrue(any(z.startswith("⚠ PlayGo-Dateien gefunden") for z in zeilen), zeilen)
        self.assertTrue(any(z.startswith("⚠ DLC-Inhalte gefunden") for z in zeilen), zeilen)
        self.assertEqual(self.app._COLORS.get("fg_warning", "#f0a32e"), str(self.f.protokoll.tag_cget("hinweis", "foreground")))

    def test_nur_hinweiszeilen_sind_orange(self) -> None:
        self.f._protokoll("[Prüfung] eine gewöhnliche Zeile")
        self.f._protokoll("⚠ ein Hinweis")
        self.assertEqual(["⚠ ein Hinweis"], self._hinweiszeilen())

    def test_ohne_playgo_und_dlc_steht_kein_hinweis_da(self) -> None:
        ordner = self._spielordner()
        with mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten()):
            self._laden(ordner)
            self.assertTrue(basis._warten(lambda: "[Prüfung]" in self._protokoll_text(), 8))
        self.assertNotIn("⚠ PlayGo-Dateien gefunden", self._protokoll_text())
        self.assertNotIn("⚠ DLC-Inhalte gefunden", self._protokoll_text())

    # ---------------- die Rueckfrage vor dem Paketbau ----------------
    def _auswahl(self, antwort: str):
        return mock.patch.object(APP.PS5ConverterGUI, "_auswahl_dialog", side_effect=lambda _t, *a, **k: (
            self.dialoge["auswahl"].append(a), antwort)[1])

    def test_fehlt_im_spielordner_etwas_geht_der_weg_ueber_ein_abbild_mit_einbau(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        self.f.aktuell.fakten = fc.QuellFakten(**self._DLC)
        gemerkt = self.app._load_setting(fz.EINST_FORMAT, None)
        self.app.dlc_integrate_var.set(False)
        with self._auswahl(_de("ps5pkg.emu_wahl_abbild")), mock.patch.object(self.app, "_launch_task") as a1, \
                self._attrappe(), mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value="werkzeug"), \
                mock.patch.object(wz, "dotnet_ordner", return_value="dotnet"):
            self.f._starten()
            self.assertEqual([], self.aufrufe, "es wird kein Paket gebaut")
            self.assertTrue(self.app.dlc_integrate_var.get(), "DLC EMU ist angehakt wie in Aufgabe 1")
            self.assertEqual("ffpkg", self.f.format_schluessel)
            self.assertEqual(gemerkt, self.app._load_setting(fz.EINST_FORMAT, None), "die Formatwahl des Anwenders bleibt")
            self.assertIn(_de("ps5pkg.emu_abbild_log", liste="DLC EMU"), self.f.protokoll.get("1.0", "end"))
            self.assertTrue(basis._warten(lambda: a1.call_count == 1, 5), "der Lauf geht als Abbild an Aufgabe 1")
        self.assertEqual(1, len(self.dialoge["auswahl"]))
        eintraege = self.dialoge["auswahl"][0][1]
        self.assertEqual([_de("ps5pkg.emu_wahl_abbild"), _de("ps5pkg.emu_wahl_paket")], eintraege)
        self.assertIn(_de("ps5pkg.emu_zeile_dlc", merkmal="addcont0"), self.dialoge["auswahl"][0][0])

    def test_wer_trotzdem_als_paket_baut_bekommt_es_und_wer_schliesst_bricht_ab(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        self.f.aktuell.fakten = fc.QuellFakten(**self._DLC)
        with self._auswahl(_de("ps5pkg.emu_wahl_paket")), self._attrappe():
            self._starten_und_warten()
        self.assertEqual(1, len(self.aufrufe))
        self.assertIn(_de("ps5pkg.emu_log"), self.f.protokoll.get("1.0", "end"))
        for p in os.listdir(self.ziel):
            os.remove(os.path.join(self.ziel, p))
        self.aufrufe.clear()
        with self._auswahl(""), self._attrappe():
            self.f._starten()
        self.assertEqual([], self.aufrufe)
        self.assertEqual(_de("ps5pkg.emu_abgebrochen"), self.f.status_var.get())
        self.assertEqual([], os.listdir(self.ziel), "kein Arbeitsordner")

    def test_ein_abbild_als_quelle_bietet_den_weg_ueber_ein_abbild_nicht_an(self) -> None:
        """Aus einem Abbild geht hier nur das Paket - Ja/Nein, wie zuvor."""
        pfad = self._abbild()
        self._laden(pfad)
        self.f.aktuell.fakten = fc.QuellFakten(**self._DLC)
        self.assertFalse(self.f._abbild_mit_einbau_moeglich(self.f.aktuell))
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual([], self.dialoge["auswahl"])
        self.assertEqual(1, len([a for a in self.dialoge["frage"] if a and a[0] == _de("ps5pkg.emu_titel")]))

    def test_der_weg_ueber_ein_abbild_ist_gesperrt_solange_aufgabe_1_arbeitet(self) -> None:
        self._laden(self._spielordner())
        with mock.patch.object(self.app, "is_running", True, create=True):
            self.assertFalse(self.f._abbild_mit_einbau_moeglich(self.f.aktuell))
        self.assertTrue(self.f._abbild_mit_einbau_moeglich(self.f.aktuell))

    def test_ampr_fehlt_fragt_nicht_weil_dump_forge_ihn_selbst_dazulegt(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        info = self.f.aktuell
        info.fakten = fc.QuellFakten(ampr_importiert=True, ampr_fehlt=True)
        with self._auswahl(_de("ps5pkg.emu_wahl_paket")):
            self.assertTrue(self.f._emulatoren_fragen(info))
        self.assertEqual([], self.dialoge["auswahl"], "Dump Forge legt ihn selbst dazu: keine Frage")
        self.assertIn(_de("bericht.ampr_forge"), self.f.protokoll.get("1.0", "end"))

    def test_der_bericht_steht_auch_dann_im_protokoll_wenn_nichts_fehlt(self) -> None:
        pfad = self._abbild()
        self._laden(pfad)
        self.f.aktuell.fakten = fc.QuellFakten()          # ungepackt: ein gepacktes Spiel wird nicht zum FPKG (siehe unten)
        with self._attrappe():
            self._starten_und_warten()
        log = self.f.protokoll.get("1.0", "end")
        for text in (_de("bericht.titel"), "[OK] " + _de("bericht.packs_keine"), "[OK] " + _de("bericht.playgo_nicht_noetig"),
                     _de("bericht.einbau_paket")):
            with self.subTest(text=text):
                self.assertIn(text, log)
        self.assertEqual([], self.dialoge["auswahl"])

    # ---------------- gepackte Spiele (LZ4, zstd) werden fuers FPKG entpackt - wie in Dump Forge ----------------
    def _nichts_gemeldet(self) -> None:
        """Weder ein Fehlerdialog noch eine Rueckfrage: Das Entpacken ist keine Stoerung, Dump Forge tut es ohne Frage."""
        self.assertEqual([], self.dialoge["fehler"])
        self.assertEqual([], self.dialoge["frage"] + self.dialoge["auswahl"])

    def test_ein_gepacktes_abbild_wird_beim_bauen_entpackt(self) -> None:
        """Nutzerwunsch 18.11.2026 ("schau es dir bei Dump Forge ab"): Forge erkennt ein LZ4- oder zstd-gepacktes Spiel und entpackt
        die Packs, waehrend es das FPKG schreibt (Reiter Pack, Aktion Unpack, Ziel .pkg: ``--lz4-unpack`` / ``--zstd-unpack``)."""
        for verfahren, name in (("lz4", "LZ4"), ("zstd", "zstd")):
            with self.subTest(verfahren=verfahren):
                self.aufrufe.clear()
                self.dialoge["fehler"].clear()
                kennung = "PPSA0001%d" % (1 if verfahren == "lz4" else 2)
                pfad = self._abbild(name="Gepackt_%s.exfat" % verfahren, tid=kennung)
                self.infos[pfad].fakten = fc.QuellFakten(gepackt=verfahren)
                self._laden(pfad)
                with self._attrappe():
                    self._starten_und_warten()
                self.assertEqual(1, len(self.aufrufe), "gebaut wird, nichts wird gesperrt")
                self.assertEqual(verfahren, self.aufrufe[0]["entpacken"], "Forge bekommt das Verfahren der Packs")
                self.assertTrue(self.aufrufe[0]["temp_da"])
                self.assertIn(_de("ps5pkg.packs_entpacken_log", verfahren=name), self.f.protokoll.get("1.0", "end"))
                self.assertIn("Neun Spiel [%s].pkg" % kennung, [p for p in os.listdir(self.ziel) if p.endswith(".pkg")])
                self._nichts_gemeldet()

    def test_ein_spielordner_mit_pack_index_wird_auch_ohne_befund_von_forge_entpackt(self) -> None:
        """Forge liest ein beschaedigtes Manifest nicht als gepackt - die Baender liegen trotzdem im Spiel: Mit der Option meldet
        Forge selbst, was nicht stimmt, statt ein Paket mit unlesbaren Packs zu bauen."""
        for index, verfahren in (("ampr_assets.index", "lz4"), ("ampr_zstd.index", "zstd")):
            with self.subTest(index=index):
                self.aufrufe.clear()
                ordner = self._spielordner(name="Spiel_" + index.split(".")[0], tid="PPSA0002%d" % (1 if verfahren == "lz4" else 2))
                Path(ordner, index).write_bytes(b"AMPRPAK4")
                self._laden(ordner)
                self.f._format_waehlen("pkg")
                self.f.aktuell.fakten = fc.QuellFakten()                  # Forge sieht nichts
                with self._attrappe():
                    self._starten_und_warten()
                self.assertEqual(1, len(self.aufrufe))
                self.assertEqual(verfahren, self.aufrufe[0]["entpacken"])

    def test_ein_ungepacktes_spiel_wird_nicht_entpackt(self) -> None:
        pfad = self._abbild()
        self.infos[pfad].fakten = fc.QuellFakten()
        self._laden(pfad)
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual(1, len(self.aufrufe))
        self.assertEqual("", self.aufrufe[0]["entpacken"])
        self.assertNotIn(_de("ps5pkg.packs_entpacken_log", verfahren="LZ4"), self.f.protokoll.get("1.0", "end"))
        self.assertNotIn(_de("ps5pkg.packs_entpacken_log", verfahren="zstd"), self.f.protokoll.get("1.0", "end"))

    def test_nur_das_fpkg_wird_entpackt_nicht_das_abbild(self) -> None:
        """Ein gepacktes Spiel laeuft als Abbild (dort liest AMPR EMU die Packs): ein Paket geht im Strom in ein ``.ffpkg``."""
        info = self._umwandeln_vorbereiten("ffpkg")
        info.fakten = fc.QuellFakten(gepackt="lz4")
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual(1, len(self.aufrufe))
        self.assertEqual("ffpkg", self.aufrufe[0]["format"])
        self.assertNotIn("entpacken", self.aufrufe[0], "der Abbildweg kennt die Option nicht")
        for verfahren in ("LZ4", "zstd"):
            self.assertNotIn(_de("ps5pkg.packs_entpacken_log", verfahren=verfahren), self.f.protokoll.get("1.0", "end"),
                             "kein Hinweis auf ein Entpacken, das nicht stattfindet")
        self.assertEqual("", self.f._bau.get("entpacken", "") if self.f._bau else "")

    def test_das_entpacken_wird_erst_nach_der_rueckfrage_gemeldet(self) -> None:
        """Sagt der Anwender bei der Rueckfrage zu fehlendem PlayGo "Nein", wird nichts gebaut - und nichts vom Entpacken gesagt."""
        pfad = self._abbild()
        self.infos[pfad].fakten = fc.QuellFakten(gepackt="zstd", playgo_merkmal="sce_sys/playgo-scenario.json")
        self._laden(pfad)
        with self._attrappe(), mock.patch.object(fz.messagebox, "askyesno", return_value=False):
            self._starten_und_warten()
        self.assertEqual([], self.aufrufe)
        self.assertNotIn(_de("ps5pkg.packs_entpacken_log", verfahren="zstd"), self.f.protokoll.get("1.0", "end"))

    def test_der_platz_wird_fuer_das_entpackte_spiel_gerechnet(self) -> None:
        """Das Paket entsteht aus den entpackten Dateien: Die gepackte Quelle ist kleiner als das Spiel."""
        gesehen: "list[int]" = []
        for gepackt, erwartet in (("zstd", fz.FORGE_PLATZ_FAKTOR_ENTPACKT), ("", fz.FORGE_PLATZ_FAKTOR)):
            with self.subTest(gepackt=gepackt):
                gesehen.clear()
                pfad = self._abbild(name="Platz_%s.exfat" % (gepackt or "ohne"), tid="PPSA0003%d" % (1 if gepackt else 2))
                self.infos[pfad].fakten = fc.QuellFakten(gepackt=gepackt)
                self._laden(pfad)
                gross = 10 * 1024 ** 3
                self.f.aktuell.groesse = gross
                with self._attrappe(), mock.patch.object(fz.Ps5PkgFenster, "_platz_reicht",
                                                         side_effect=lambda ordner, noetig, nachfragen=False: gesehen.append(noetig) or True):
                    self._starten_und_warten()
                self.assertEqual([int(gross * erwartet)], gesehen)
                for p in os.listdir(self.ziel):
                    os.remove(os.path.join(self.ziel, p))
        self.assertGreater(fz.FORGE_PLATZ_FAKTOR_ENTPACKT, fz.FORGE_PLATZ_FAKTOR)

    def test_die_sperre_gibt_es_nicht_mehr(self) -> None:
        self.assertFalse(hasattr(fz.Ps5PkgFenster, "_gepackt_sperren"))
        self.assertNotIn("ps5pkg.packs_gesperrt", STRINGS)

    def test_der_hilfsmann_erkennt_pack_indexe_an_der_wurzel(self) -> None:
        self.assertEqual("", fc.gepackt_im_ordner(self.ordner))
        self.assertEqual("", fc.gepackt_im_ordner(os.path.join(self.ordner, "gibt_es_nicht")))
        Path(self.ordner, "ampr_assets.index").write_bytes(b"x")
        self.assertEqual("lz4", fc.gepackt_im_ordner(self.ordner))
        Path(self.ordner, "ampr_zstd.index").write_bytes(b"x")
        self.assertEqual("zstd", fc.gepackt_im_ordner(self.ordner), "zstd vor LZ4: ein Spiel mit beiden ist zstd-gepackt")

    def test_die_indexnamen_sind_die_der_packmodule(self) -> None:
        from ps5_validator.utils import ampr_assetpakete as ap
        from ps5_validator.utils import ampr_zstdpack as zp
        self.assertEqual({"zstd": zp.INDEX_NAME, "lz4": ap.MANIFEST_NAME}, {v: n for n, v in fc.PACK_INDEXE})

    def test_ein_spielordner_ohne_fakten_schreibt_dass_er_nicht_zu_pruefen_war(self) -> None:
        self._laden(self._spielordner())
        self.f._format_waehlen("pkg")
        with mock.patch.object(fc, "quellfakten_lesen", return_value=None), self._attrappe():
            self._starten_und_warten()
        self.assertIn(_de("bericht.nicht_pruefbar"), self.f.protokoll.get("1.0", "end"))

    def test_die_frage_nach_dem_backport_fragt_nach_der_firmware_nur_einmal(self) -> None:
        self._laden(self._spielordner())
        self.f.aktuell.fakten = fc.QuellFakten(sdk="10.00", firmware="11.20")
        with self._auswahl(_de("ps5pkg.emu_wahl_paket")), \
                mock.patch.object(APP.PS5ConverterGUI, "_backport_plan", return_value=("7.99", 7)) as plan, \
                mock.patch.object(APP.PS5ConverterGUI, "_konsole_fw_bekannt", return_value="7.99"):
            self.assertTrue(self.f._emulatoren_fragen(self.f.aktuell))
        plan.assert_called_once()
        self.assertIn(_de("ps5pkg.emu_zeile_backport", spiel="11.20", konsole="7.xx"), self.dialoge["auswahl"][0][0])

    # ---------------- ein Paket ohne Zwischenordner in ein Abbild ----------------
    def _umwandeln_vorbereiten(self, format: str = "ffpkg") -> "wz.PaketInfo":
        info = self._paket()
        self.f.aktion_var.set("umwandeln")
        self.f._format_waehlen(format)
        for name in ("ampr_integrate_var", "ampr_playgo_var", "dlc_integrate_var", "backport_integrate_var"):
            getattr(self.app, name).set(False)
        return info

    def test_ein_paket_geht_im_strom_in_das_abbild_ohne_entpacken_und_ohne_arbeitsordner(self) -> None:
        info = self._umwandeln_vorbereiten("ffpkg")
        with self._attrappe(), mock.patch.object(wz, "extrahieren") as entpacken, \
                mock.patch.object(self.app, "_launch_task") as aufgabe1, \
                mock.patch.object(fz.tempfile, "mkdtemp", wraps=fz.tempfile.mkdtemp) as ordner_anlegen:
            self._starten_und_warten()
        entpacken.assert_not_called()
        aufgabe1.assert_not_called()
        self.assertEqual(1, len(self.aufrufe))
        aufruf = self.aufrufe[0]
        self.assertEqual("ffpkg", aufruf["format"])
        self.assertEqual(info.pfad, aufruf["quelle"])
        name = "Sieben [PPSA00007].ffpkg"
        self.assertEqual([name], os.listdir(self.ziel))
        self.assertTrue(aufruf["temp_da"])
        self.assertEqual(["ps5conv_forge_"], [c.kwargs["prefix"] for c in ordner_anlegen.call_args_list],
                         "nur der Arbeitsordner neben dem Ziel, nie der Temp-Ordner des Systems")
        self.assertEqual(_de("ps5pkg.job_done_convert"), self.f.auftrag_var.get())
        log = self.f.protokoll.get("1.0", "end")
        self.assertIn(_de("ps5pkg.log_start_abbild", name="Alpha.pkg"), log)
        self.assertIn(_de("ps5pkg.log_done_convert", name=name), log)
        self.assertEqual([], [p for p in os.listdir(self.ziel) if p.startswith("ps5conv_")], "nichts bleibt liegen")

    def test_alle_vier_abbildformate_gehen_direkt_und_die_felder_der_karte_kommen_an(self) -> None:
        self.app._save_setting("zstd_level", 3)
        self.app._save_setting("worker_count", 2)
        self.app._save_setting("mkpfs_verify", "voll")
        for format, endung in (("ffpkg", ".ffpkg"), ("ffpfsc", ".ffpfsc"), ("ffpfs", ".ffpfs"), ("exfat", ".exfat")):
            with self.subTest(format=format):
                self.aufrufe.clear()
                for p in os.listdir(self.ziel):
                    os.remove(os.path.join(self.ziel, p))
                self._umwandeln_vorbereiten(format)
                with self._attrappe():
                    self._starten_und_warten()
                aufruf = self.aufrufe[0]
                self.assertEqual(format, aufruf["format"])
                self.assertEqual((3, 2, True), (aufruf["stufe"], aufruf["kerne"], aufruf["voll_pruefen"]),
                                 "KOMPRESSION, WORKER und PRUEFUNG der Karte")
                self.assertEqual(["Sieben [PPSA00007]" + endung], os.listdir(self.ziel))

    def test_mit_angehaktem_einbau_bleibt_es_beim_entpacken_und_das_protokoll_sagt_warum(self) -> None:
        info = self._umwandeln_vorbereiten("ffpkg")
        self.app.ampr_playgo_var.set(True)
        self.assertFalse(self.f._abbild_direkt_moeglich(info))
        self.assertIn(_de("ps5pkg.log_einbau_braucht_ordner", liste="PlayGo"), self.f.protokoll.get("1.0", "end"))

    def test_fehlt_dem_paket_etwas_fragt_das_fenster_ob_entpackt_und_eingebaut_wird(self) -> None:
        info = self._umwandeln_vorbereiten("ffpkg")
        info.fakten = fc.QuellFakten(**self._DLC)
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True) as frage:
            self.assertFalse(self.f._abbild_direkt_moeglich(info), "Ja: der Weg ueber den Arbeitsordner und Aufgabe 1")
        self.assertEqual(_de("ps5pkg.emu_frage_entpacken", liste=_de("ps5pkg.emu_zeile_dlc", merkmal="addcont0")),
                         frage.call_args.args[1])
        self.assertTrue(self.app.dlc_integrate_var.get(), "DLC EMU ist angehakt")
        with mock.patch.object(fz.messagebox, "askyesno", return_value=False):
            self.app.dlc_integrate_var.set(False)
            self.assertTrue(self.f._abbild_direkt_moeglich(info), "Nein: direkt, ohne Einbau")
        self.assertFalse(self.app.dlc_integrate_var.get())

    def test_bauform_steht_nur_beim_zielformat_ffpfsc_da_und_ist_ein_zwilling(self) -> None:
        """Nutzerwunsch 17.11.2026: Ein ``.ffpfsc`` ist ein Abbild-Container - die BAUFORM (Container) gilt dort wie bei Aufgabe 1
        und steht nur beim Zielformat ``.ffpfsc`` da (``_BAUFORM_WIRKT_BEI``). Dieselbe Variable und derselbe Befehl wie dort."""
        f, app = self.f, self.app
        self.addCleanup(app.bauform_var.set, app.bauform_var.get())
        self.addCleanup(setattr, app, "bauform", app.bauform)
        self.addCleanup(app._save_setting, "bauform", app._load_setting("bauform", app.bauform))
        self.assertEqual(str(app.bauform_var), f.bauform_box.cget("textvariable"), "dieselbe Variable wie dort")
        for format_, erwartet in (("ffpkg", ""), ("ffpfsc", "pack"), ("ffpfs", ""), ("exfat", ""), ("pkg", ""), ("ffpfsc", "pack")):
            with self.subTest(format=format_):
                f._format_waehlen(format_)
                f._einbau_abgleichen()
                self.assertEqual(erwartet, f.bauform_reihe.winfo_manager())
        f.aktion_var.set("pruefen")
        f._einbau_abgleichen()
        self.assertEqual("", f.bauform_reihe.winfo_manager(), "Pruefen baut nichts")
        f.aktion_var.set("umwandeln")
        f._einbau_abgleichen()
        self.assertEqual("pack", f.bauform_reihe.winfo_manager())
        self.assertEqual(app._bauform_erklaerung(), f._bauform_tooltip.text, "derselbe Vergleich beider Formen im Tooltip")
        f.bauform_box._gewaehlt(app._t("bauform.pfs"))
        self.assertEqual("pfs", app.bauform, "dieselbe Wirkung wie die Liste bei Aufgabe 1")
        self.assertEqual("pfs", app._load_setting("bauform", ""), "und dieselbe Einstellung")
        vorher = f._bauform_tooltip.text
        f._einbau_abgleichen()
        self.assertEqual(app._bauform_erklaerung(), f._bauform_tooltip.text, "der Satz zur gewaehlten Form steht voran")
        self.assertNotEqual(vorher, f._bauform_tooltip.text, "und wechselt mit der Wahl")
        f.bauform_box._gewaehlt(app._t("bauform.exfat"))
        self.assertEqual("exfat", app.bauform)

    def test_pfs_im_container_geht_nicht_im_strom_sondern_ueber_aufgabe_1(self) -> None:
        """Dump Forge baut ``.ffpfsc`` im Strom nur als exFAT im Container (wie ``_strom_nach_container_gewaehlt`` dort): Wer "PFS im
        Container" gewaehlt hat, bekommt die gewaehlte Form vom Weg ueber den Arbeitsordner und Aufgabe 1 - nicht still die andere."""
        info = self._umwandeln_vorbereiten("ffpfsc")
        app = self.app
        self.addCleanup(setattr, app, "bauform", app.bauform)
        app.bauform = "exfat"
        self.assertTrue(self.f._abbild_direkt_moeglich(info), "exFAT im Container: im Strom")
        app.bauform = "pfs"
        self.assertFalse(self.f._abbild_direkt_moeglich(info), "PFS im Container: ueber Aufgabe 1")
        self.assertIn(_de("ps5pkg.log_bauform_braucht_ordner"), self.f.protokoll.get("1.0", "end"))
        self.f.format_schluessel = "ffpkg"
        self.assertTrue(self.f._abbild_direkt_moeglich(info), "die Bauform gilt nur fuer den .ffpfsc-Container")

    def test_wann_der_strom_nicht_gilt(self) -> None:
        info = self._umwandeln_vorbereiten("ffpkg")
        self.assertTrue(self.f._abbild_direkt_moeglich(info))
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value=""):
            self.assertFalse(self.f._abbild_direkt_moeglich(info), "ohne Dump Forge")
        self.f.format_schluessel = "pkg"
        self.assertFalse(self.f._abbild_direkt_moeglich(info), "kein Abbildformat")
        self.f.format_schluessel = "ffpkg"
        ordner = self._spielordner("Ordner2")
        self._laden(ordner)
        self.assertFalse(self.f._abbild_direkt_moeglich(self.f.aktuell), "ein Spielordner geht an Aufgabe 1")
        stumm = os.path.join(self.ordner, "x.pkg")
        info2 = basis._info("x.pkg", "X", "PPSA00001", 10, stumm)
        self.assertFalse(self.f._abbild_direkt_moeglich(info2), "die Datei gibt es nicht")

    def test_ein_langer_titel_wird_auf_die_grenze_von_forge_gekuerzt(self) -> None:
        info = self._paket("Lang.pkg", "PPSA00008", "Ein langer Spieltitel " * 5)
        self.assertLessEqual(len(os.path.splitext(self.f._forge_abbild_name(info, "ffpkg"))[0].encode("utf-8")), 63)
        self.assertLessEqual(len(os.path.splitext(self.f._forge_abbild_name(info, "ffpfsc"))[0].encode("utf-8")), 58)
        self.assertTrue(self.f._forge_abbild_name(info, "exfat").endswith(".exfat"))

    def test_ein_vorhandenes_abbild_wird_nur_mit_dem_haken_ersetzt(self) -> None:
        self._umwandeln_vorbereiten("ffpkg")
        vorhanden = os.path.join(self.ziel, "Sieben [PPSA00007].ffpkg")
        Path(vorhanden).write_bytes(b"alt")
        self.f.ueberschreiben_var.set(False)
        with self._attrappe():
            self.f._starten()
        self.assertEqual([], self.aufrufe)
        self.assertEqual(_de("ps5pkg.err_exists_abbild", pfad=vorhanden), self.dialoge["info"][-1][1])
        self.assertEqual(b"alt", Path(vorhanden).read_bytes())
        self.f.ueberschreiben_var.set(True)
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual(b"pkg", Path(vorhanden).read_bytes())

    def test_extrahieren_leert_den_alten_ordner_erst_nach_der_frage_zum_loeschen(self) -> None:
        """Mit "Vorhandenes ueberschreiben" wurde der alte Entpackordner geleert, bevor die Frage "Quelle nach Erfolg loeschen?" kam: Wer
        dort "Abbrechen" waehlte, hatte den Ordner trotzdem verloren (Pruefung 18.11.2026)."""
        info = self._paket()
        self.f.aktion_var.set("extrahieren")
        alt = os.path.join(self.ziel, fz.anzeigename(info))
        os.makedirs(alt)
        Path(alt, "alt.txt").write_bytes(b"alt")
        self.f.ueberschreiben_var.set(True)
        faeden: list = []
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value="ppt"), \
                mock.patch.object(wz, "dotnet_ordner", return_value="dotnet"), \
                mock.patch.object(fz.Ps5PkgFenster, "_lauf_extrahieren", side_effect=lambda *a: faeden.append(a)):
            with mock.patch.object(fz.Ps5PkgFenster, "_loeschen_vorbereiten", return_value=(False, False)):
                self.f._starten()
            self.assertEqual(b"alt", Path(alt, "alt.txt").read_bytes(), "Abbrechen bei der Frage laesst den alten Ordner unberuehrt")
            self.assertEqual([], faeden)
            self.assertIsNone(self.f._job)
            # Gegenprobe: Nach der Bestaetigung wird er geleert, und der Lauf beginnt.
            with mock.patch.object(fz.Ps5PkgFenster, "_loeschen_vorbereiten", return_value=(True, False)):
                self.f._starten()
            self.assertTrue(basis._warten(lambda: bool(faeden), 5.0), "der Lauf hat begonnen")
            self.assertFalse(os.path.exists(os.path.join(alt, "alt.txt")), "der alte Inhalt ist weg")
        self.f._job = None

    def test_der_rueckfall_des_formats_ist_die_vorgabe_ffpkg(self) -> None:
        """Ein gespeichertes Format, das fuer die Quelle nicht geht, springt auf die Vorgabe - nicht auf .ffpfsc (Pruefung 18.11.2026)."""
        self.assertEqual("ffpkg", opt.STANDARD_FORMAT)
        self.f.format_schluessel = "pkg"           # fuer ein .pkg nicht moeglich (nur fuer Spielordner und Abbilder)
        self._paket()
        self.assertEqual(opt.STANDARD_FORMAT, self.f.format_schluessel)

    def test_ohne_zielordner_kommt_der_fehler_vor_jeder_rueckfrage(self) -> None:
        """Fehlt das Ziel, soll weder eine Rueckfrage (BACKPORT, "Entpacken und einbauen?") noch ein gesetzter Haken von Aufgabe 1 vorangehen."""
        self._umwandeln_vorbereiten("ffpkg")
        self.f.ziel_var.set(os.path.join(self.ordner, "gibt-es-nicht"))
        with mock.patch.object(fz.Ps5PkgFenster, "_abbild_direkt_moeglich", side_effect=AssertionError("vor dem Ziel gefragt")) as frage:
            self.f._starten()
        frage.assert_not_called()                  # ein ``except Exception`` im Programm schluckte sonst den Fehler des Stubs
        self.assertEqual([_de("ps5pkg.err_no_target")], [d[1] for d in self.dialoge["fehler"]])
        # Pruefen braucht kein Ziel: Es laeuft weiter bis zum Auftrag.
        self.f.aktion_var.set("pruefen")
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value="ppt"), \
                mock.patch.object(wz, "dotnet_ordner", return_value="dotnet"), \
                mock.patch.object(fz.Ps5PkgFenster, "_job_starten") as job:
            self.f._starten()
        job.assert_called_once()
        self.assertEqual(1, len(self.dialoge["fehler"]), "kein zweiter Fehler")

    def test_ein_fehler_von_forge_beim_abbild_hinterlaesst_nichts(self) -> None:
        self._umwandeln_vorbereiten("exfat")
        with self._attrappe(fehler=wz.Fehler("kaputt")):
            self._starten_und_warten()
        self.assertEqual([], os.listdir(self.ziel))
        self.assertIn("kaputt", self.f.protokoll.get("1.0", "end"))
        self.assertEqual(_de("ps5pkg.job_failed"), self.f.auftrag_var.get())

    def test_abbrechen_beim_abbild_raeumt_den_arbeitsordner_weg(self) -> None:
        self._umwandeln_vorbereiten("ffpkg")

        def warten(abbruch):
            self.f._abbruch = True
            raise wz.Fehler("abgebrochen")
        with self._attrappe(warten=warten):
            self._starten_und_warten()
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], self.f._staging)

    # ---------------- das Lebenszeichen ----------------
    def _job(self, art: str, info, laeuft_seit: float, letzte_vor: float) -> None:
        jetzt = time.monotonic()
        self.f._job = {"art": art, "info": info, "ziel": self.ziel, "start": jetzt - laeuft_seit,
                       "letzte": jetzt - letzte_vor, "zeichen": None}

    def test_das_lebenszeichen_nennt_die_dauer_und_das_werkzeug(self) -> None:
        info = self._spielordner()
        self._laden(info)
        self._job("bauen", self.f.aktuell, laeuft_seit=125, letzte_vor=3)
        self.f._lebenszeichen_zeigen()
        self.assertEqual(_de("ps5pkg.lebt_zeit", dauer="2:05", werkzeug="Dump Forge"), self.f.lebt_var.get())

    def test_wird_es_still_sagt_die_seite_seit_wann_nichts_Neues_kam(self) -> None:
        self._laden(self._spielordner())
        self._job("bauen", self.f.aktuell, laeuft_seit=3725, letzte_vor=45)
        self.f._lebenszeichen_zeigen()
        text = self.f.lebt_var.get()
        self.assertIn("1:02:05", text)
        self.assertIn(_de("ps5pkg.lebt_still", still="0:45"), text)
        self._job("bauen", self.f.aktuell, laeuft_seit=3725, letzte_vor=fz.Ps5PkgFenster.STILLE_AB - 2)
        self.f._lebenszeichen_zeigen()
        self.assertNotIn(_de("ps5pkg.lebt_still", still="0:18"), self.f.lebt_var.get(), "erst ab der Grenze")

    def test_ohne_auftrag_ist_die_zeile_leer(self) -> None:
        self.f.lebt_var.set("Rest")
        self.f._job = None
        self.f._lebenszeichen_zeigen()
        self.assertEqual("", self.f.lebt_var.get())

    def test_eine_neue_meldung_oder_ein_neuer_prozentwert_setzt_die_stille_zurueck(self) -> None:
        self._laden(self._spielordner())
        faelle = {"Zeile des Werkzeugs": {"zeilen": ["fpkg: writing"]}, "anderer Prozentwert": {"prozent": 42.0},
                  "andere Dateizeile": {"schritt_text": "data/d001.bin"}}
        for name, aenderung in faelle.items():
            with self.subTest(fall=name):
                self._job("bauen", self.f.aktuell, laeuft_seit=100, letzte_vor=60)
                alt = self.f._job["letzte"]
                with self.f._sperre:
                    self.f._z.update(dict({"zeilen": [], "prozent": None, "schritt_text": None}, **aenderung))
                self.f._takt_arbeiten()
                self.assertGreater(self.f._job["letzte"], alt)

    def test_ohne_neues_bleibt_die_zeit_der_letzten_meldung_stehen(self) -> None:
        self._laden(self._spielordner())
        self._job("bauen", self.f.aktuell, laeuft_seit=100, letzte_vor=60)
        with self.f._sperre:
            self.f._z.update({"zeilen": [], "prozent": 10.0, "schritt_text": "x"})
        self.f._takt_arbeiten()
        gemerkt = self.f._job["letzte"]
        self.f._takt_arbeiten()                       # dasselbe noch einmal: nichts Neues
        self.assertEqual(gemerkt, self.f._job["letzte"])

    def test_das_werkzeug_wird_beim_namen_genannt(self) -> None:
        info = self._spielordner()
        self._laden(info)
        a = self.f.aktuell
        self.assertEqual("Dump Forge", self.f._werkzeug_name("bauen", a))
        self.assertEqual("Dump Forge", self.f._werkzeug_name("abbild", a))
        for art in ("pruefen", "extrahieren", "umwandeln", "konsole"):
            with self.subTest(art=art):
                self.assertEqual("LibProsperoPkg", self.f._werkzeug_name(art, a), "lesen, pruefen, entpacken: LibProsperoPkg")

    def test_der_start_nennt_dump_forge_als_werkzeug(self) -> None:
        """Gemeldet am 17.11.2026: Mit ProsperoPkgTool stand nur "Staging (0/38'497 MiB)" da - woher das kam, sah man nicht."""
        self._laden(self._spielordner())
        a = self.f.aktuell
        with mock.patch.object(fz.threading, "Thread"):
            self.f._job_starten("bauen", lambda *x: None, a, self.ziel)
        log = self.f.protokoll.get("1.0", "end")
        self.assertIn(_de("ps5pkg.log_bauer", name="Dump Forge"), log)
        self.assertNotIn("ProsperoPkgTool", log)

    def test_die_dauer_als_text(self) -> None:
        for sekunden, text in ((0, "0:00"), (59.9, "0:59"), (60, "1:00"), (125, "2:05"), (3599, "59:59"), (3600, "1:00:00"),
                               (3725, "1:02:05"), (-5, "0:00")):
            with self.subTest(sekunden=sekunden):
                self.assertEqual(text, fz.Ps5PkgFenster._dauer_text(sekunden))



@unittest.skipUnless(basis._TK_DA, "ohne Anzeige kein Fenster")
class NachErfolgTests(_ForgeBasis):
    """Die Haken der Aufgaben 1 bis 6 auf Seite 7 (Nutzerwunsch 17.11.2026): Rechner herunterfahren, Ergebnis an die PS5 senden, Quelle
    nach Erfolg loeschen, Arbeitskopie. Zwillinge der Haken im Hauptfenster; die Auftraege von Seite 7 wenden sie nach einem Erfolg an."""

    HAKEN = {"herunterfahren": "shutdown_after_success", "senden": "senden_nach_erfolg_var", "loeschen": "quelle_loeschen_var",
             "arbeitskopie": "arbeitskopie_vorher"}

    def setUp(self) -> None:
        super().setUp()
        for variable in self.HAKEN.values():
            var = getattr(self.app, variable)
            self.addCleanup(var.set, var.get())
            var.set(False)
        for schluessel in ("shutdown_after_success", "senden_nach_erfolg", "arbeitskopie_vorher"):
            self.addCleanup(self.app._save_setting, schluessel, self.app._load_setting(schluessel, False))
            self.app._save_setting(schluessel, False)

    def _quelle_und_ergebnis(self) -> "tuple[str, str, tuple | None]":
        quelle = os.path.join(self.ordner, "Quelle")
        os.makedirs(os.path.join(quelle, "sce_sys"))
        Path(quelle, "eboot.bin").write_bytes(b"x")
        ergebnis = os.path.join(self.ziel, "Ergebnis.ffpkg")
        Path(ergebnis).write_bytes(b"abc")
        return quelle, ergebnis, fz.quelle_loeschen.stempel_nehmen(quelle)

    def _protokoll_text(self) -> str:
        return self.f.protokoll.get("1.0", "end")

    # ---------------- die Karte ----------------
    def test_die_haken_haengen_an_den_variablen_der_aufgaben_1_bis_6(self) -> None:
        for name, variable in self.HAKEN.items():
            with self.subTest(haken=name):
                self.assertEqual(str(getattr(self.app, variable)), self.f.nach_erfolg_haken[name].cget("variable"))
        texte = {"herunterfahren": "main.shutdown_after_success", "senden": "main.senden_nach_erfolg",
                 "loeschen": "main.quelle_loeschen", "arbeitskopie": "main.arbeitskopie_vorher"}
        for name, schluessel in texte.items():
            with self.subTest(text=name):
                self.assertEqual(self.app._t(schluessel), self.f.nach_erfolg_haken[name].cget("text"), "derselbe Text wie dort")

    def test_ein_klick_speichert_wie_in_den_aufgaben_1_bis_6(self) -> None:
        for name, schluessel in (("herunterfahren", "shutdown_after_success"), ("senden", "senden_nach_erfolg"),
                                 ("arbeitskopie", "arbeitskopie_vorher")):
            with self.subTest(haken=name):
                self.f.nach_erfolg_haken[name].invoke()
                self.assertTrue(self.app._load_setting(schluessel, False), "dieselbe Einstellung wie dort")
        # "Quelle loeschen" wird bewusst nicht gespeichert: jeder Start des Programms beginnt ohne
        self.f.nach_erfolg_haken["loeschen"].invoke()
        self.assertTrue(self.app.quelle_loeschen_var.get())

    REIHE = ("ueberschreiben", "arbeitskopie", "herunterfahren", "senden", "loeschen")

    def _ort(self) -> "dict[str, tuple[int, int]]":
        """(Zeile, Spalte) jedes Hakens im Raster; ein Haken, der nicht im Raster steht, fehlt."""
        h = self.f.nach_erfolg_haken
        return {n: (int(h[n].grid_info()["row"]), int(h[n].grid_info()["column"])) for n in h if h[n].winfo_manager() == "grid"}

    def _breiten(self) -> "tuple[int, int, int]":
        """Die Breite, ab der drei, zwei und eine Spalte nebeneinander passen (Nutzerwunsch 17.11.2026: weniger Hoehe)."""
        f = self.f
        f.win.update_idletasks()
        w = {n: int(h.winfo_reqwidth()) for n, h in f.nach_erfolg_haken.items()}
        a = f.HAKEN_ABSTAND
        drei = max(w["ueberschreiben"], w["arbeitskopie"]) + max(w["herunterfahren"], w["senden"]) + w["loeschen"] + 2 * a
        zwei = max(w["ueberschreiben"], w["arbeitskopie"], w["herunterfahren"]) + max(w["senden"], w["loeschen"]) + a
        return drei, zwei, max(w.values())

    def test_die_haken_stehen_unter_dem_zielordner_nebeneinander_statt_untereinander(self) -> None:
        """Gemeldet am 17.11.2026: Alles stand links untereinander und brauchte Hoehe. Bei genug Breite sind es zwei Zeilen."""
        f = self.f
        f._seite_zeigen("umwandeln")
        basis._pumpen(0.3)
        h = f.nach_erfolg_haken
        self.assertEqual(set(self.REIHE), set(h), "alle fuenf Haken: Ueberschreiben, Arbeitskopie und die drei Haken der Aufgabe 1")
        for name in self.REIHE:
            with self.subTest(haken=name):
                self.assertEqual("grid", h[name].winfo_manager())
                self.assertGreater(h[name].winfo_rooty(), f.ziel_feld.winfo_rooty(), "unter dem Zielordner")
        spalten = f._haken_spalten(list(self.REIHE), int(f.nach_erfolg_rahmen.winfo_width()))
        zeilen = {h[n].winfo_rooty() for n in self.REIHE}
        self.assertEqual(max(len(s) for s in spalten), len(zeilen), "so viele Zeilen wie die laengste Spalte")
        self.assertLess(len(zeilen), len(self.REIHE), "nicht alle untereinander")

    def test_bei_genug_breite_stehen_die_haken_in_drei_spalten_mit_zwei_zeilen(self) -> None:
        f = self.f
        drei, _zwei, _eine = self._breiten()
        for breite in (drei, 3000):
            with self.subTest(breite=breite):
                f._haken_anordnen(breite)
                self.assertEqual({"ueberschreiben": (0, 0), "arbeitskopie": (1, 0), "herunterfahren": (0, 1), "senden": (1, 1),
                                  "loeschen": (0, 2)}, self._ort())

    def test_reicht_die_breite_nicht_fuer_drei_spalten_sind_es_zwei_dann_eine(self) -> None:
        """Bei Mindestgroesse ragte ein Haken rechts aus der Karte (``test_pkg_fpkg_seite``): er rutscht nach unten."""
        f = self.f
        drei, zwei, eine = self._breiten()
        zwei_spalten = {"ueberschreiben": (0, 0), "arbeitskopie": (1, 0), "herunterfahren": (2, 0), "senden": (0, 1), "loeschen": (1, 1)}
        eine_spalte = {n: (i, 0) for i, n in enumerate(self.REIHE)}
        self.assertLess(zwei, drei)
        for breite, erwartet in ((drei - 1, zwei_spalten), (zwei, zwei_spalten), (zwei - 1, eine_spalte), (eine, eine_spalte),
                                 (200, eine_spalte)):
            with self.subTest(breite=breite):
                f._haken_anordnen(breite)
                self.assertEqual(erwartet, self._ort())

    def test_ueberschreiben_gilt_nur_fuer_den_zielordner_auf_dem_pc(self) -> None:
        """Bei "Auf die PS5 entpacken" gibt es keinen Zielordner auf dem PC: der Haken verschwindet, die vier uebrigen ruecken
        zusammen; danach ist er wieder da."""
        f = self.f
        self.addCleanup(lambda: (f.aktion_var.set(fz.AKTION_UMWANDELN), f._konsole_zeilen_zeigen(), f._haken_anordnen(3000)))
        f.aktion_var.set(fz.AKTION_KONSOLE)
        f._konsole_zeilen_zeigen()
        f._haken_anordnen(3000)
        self.assertEqual("", f.nach_erfolg_haken["ueberschreiben"].winfo_manager())
        self.assertEqual({"arbeitskopie": (0, 0), "herunterfahren": (1, 0), "senden": (0, 1), "loeschen": (1, 1)}, self._ort())
        f.aktion_var.set(fz.AKTION_UMWANDELN)
        f._konsole_zeilen_zeigen()
        f._haken_anordnen(3000)
        self.assertEqual("grid", f.nach_erfolg_haken["ueberschreiben"].winfo_manager())
        self.assertEqual((0, 0), self._ort()["ueberschreiben"])

    def test_ueberschreiben_haengt_weiter_an_seiner_variable(self) -> None:
        h = self.f.nach_erfolg_haken["ueberschreiben"]
        self.assertEqual(str(self.f.ueberschreiben_var), h.cget("variable"))
        self.assertIs(h, self.f.ueberschreiben)
        self.assertEqual(self.f.t("ps5pkg.overwrite"), h.cget("text"))

    # ---------------- die Rueckfrage vor dem Start ----------------
    def test_ohne_haken_wird_nicht_gefragt(self) -> None:
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "x"), typ=wz.TYP_ORDNER)
        with mock.patch.object(APP.PS5ConverterGUI, "_quelle_loeschen_bestaetigen") as frage:
            self.assertEqual((True, None), self.f._loeschen_vorbereiten("bauen", info))
        frage.assert_not_called()

    def test_die_rueckfrage_und_ihre_antworten(self) -> None:
        quelle, _ergebnis, _stempel = self._quelle_und_ergebnis()
        info = wz.PaketInfo(pfad=quelle, typ=wz.TYP_ORDNER)
        self.app.quelle_loeschen_var.set(True)
        for antwort, erwartet in ((None, (False, None)), (False, (True, None))):
            with self.subTest(antwort=antwort), mock.patch.object(APP.PS5ConverterGUI, "_quelle_loeschen_bestaetigen",
                                                                 return_value=antwort) as frage:
                self.assertEqual(erwartet, self.f._loeschen_vorbereiten("bauen", info))
                frage.assert_called_once_with("pkg_fpkg", quelle)
        with mock.patch.object(APP.PS5ConverterGUI, "_quelle_loeschen_bestaetigen", return_value=True):
            weiter, loeschen = self.f._loeschen_vorbereiten("bauen", info)
        self.assertTrue(weiter)
        self.assertEqual(quelle, loeschen["quelle"])
        self.assertEqual(fz.quelle_loeschen.stempel_nehmen(quelle), loeschen["stempel"], "der Stempel merkt den Stand beim Start")

    def test_pruefen_und_konsole_fragen_nie_nach_dem_loeschen(self) -> None:
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "x"), typ=wz.TYP_ORDNER)
        self.app.quelle_loeschen_var.set(True)
        with mock.patch.object(APP.PS5ConverterGUI, "_quelle_loeschen_bestaetigen") as frage:
            for art in ("pruefen", "konsole"):
                self.assertEqual((True, None), self.f._loeschen_vorbereiten(art, info))
        frage.assert_not_called()

    def test_abbrechen_der_rueckfrage_startet_nichts(self) -> None:
        quelle, _ergebnis, _stempel = self._quelle_und_ergebnis()
        info = wz.PaketInfo(pfad=quelle, typ=wz.TYP_ORDNER)
        self.app.quelle_loeschen_var.set(True)
        lauf = mock.Mock()
        with mock.patch.object(APP.PS5ConverterGUI, "_quelle_loeschen_bestaetigen", return_value=None):
            self.f._job_starten("bauen", lauf, info, self.ziel)
        basis._pumpen(0.2)
        self.assertIsNone(self.f._job)
        lauf.assert_not_called()

    # ---------------- nach einem Erfolg: Quelle loeschen ----------------
    def _loeschen_und_warten(self, ergebnis: str, loeschen: dict, befund: bool = False) -> None:
        self.f._nach_erfolg("bauen", ergebnis, loeschen, befund)
        self.assertTrue(basis._warten(lambda: not self.f.beschaeftigt(), 15), "das Loeschen ist zu Ende gegangen")
        basis._pumpen(0.2)

    def test_die_quelle_wird_nach_dem_erfolg_geloescht_und_das_protokoll_sagt_es(self) -> None:
        quelle, ergebnis, stempel = self._quelle_und_ergebnis()
        self.f._nach_erfolg("bauen", ergebnis, {"quelle": quelle, "stempel": stempel})
        self.assertTrue(self.f.beschaeftigt(), "waehrend des Loeschens gilt das Fenster als beschaeftigt (Schliessen, Herunterfahren)")
        self.assertTrue(basis._warten(lambda: not self.f.beschaeftigt() and not os.path.exists(quelle), 15))
        basis._pumpen(0.2)
        self.assertFalse(os.path.exists(quelle))
        self.assertTrue(os.path.exists(ergebnis), "das Ergebnis bleibt")
        log = self._protokoll_text()
        self.assertIn(self.app._t("log.quelle_wird_geloescht", pfad=quelle), log)
        self.assertIn(self.app._t("log.quelle_geloescht", pfad=quelle), log)

    def test_bei_einem_befund_bleibt_die_quelle(self) -> None:
        quelle, ergebnis, stempel = self._quelle_und_ergebnis()
        self.f._nach_erfolg("bauen", ergebnis, {"quelle": quelle, "stempel": stempel}, befund=True)
        basis._pumpen(0.3)
        self.assertTrue(os.path.isdir(quelle))
        self.assertFalse(self.f.beschaeftigt())

    def test_fehlt_das_ergebnis_oder_hat_sich_die_quelle_geaendert_bleibt_sie_und_das_protokoll_nennt_den_grund(self) -> None:
        quelle, ergebnis, stempel = self._quelle_und_ergebnis()
        self._loeschen_und_warten(os.path.join(self.ziel, "gibt_es_nicht.ffpkg"), {"quelle": quelle, "stempel": stempel})
        self.assertTrue(os.path.isdir(quelle), "ohne Ergebnis wird nichts geloescht")
        self.assertIn(self.app._t("log.quelle_bleibt", pfad=quelle, grund=self.app._t("quelle_loeschen.grund.ergebnis_fehlt")),
                      self._protokoll_text())
        Path(quelle, "neu.txt").write_text("waehrend des Laufs dazugekommen", encoding="utf-8")
        self._loeschen_und_warten(ergebnis, {"quelle": quelle, "stempel": stempel})
        self.assertTrue(os.path.isdir(quelle), "wer die Quelle waehrend des Laufs aendert, behaelt sie")
        self.assertIn(self.app._t("quelle_loeschen.grund.geaendert"), self._protokoll_text())

    def test_ein_fehler_beim_loeschen_ist_kein_absturz(self) -> None:
        quelle, ergebnis, stempel = self._quelle_und_ergebnis()
        with mock.patch.object(fz.quelle_loeschen, "loeschen", return_value="Zugriff verweigert"):
            self._loeschen_und_warten(ergebnis, {"quelle": quelle, "stempel": stempel})
        self.assertIn(self.app._t("log.quelle_loeschen_fehler", pfad=quelle, fehler="Zugriff verweigert"), self._protokoll_text())

    # ---------------- nach einem Erfolg: an die PS5 senden, herunterfahren ----------------
    def test_senden_fragt_wie_in_den_aufgaben_1_bis_6_und_sendet_nur_bei_ja(self) -> None:
        _quelle, ergebnis, _stempel = self._quelle_und_ergebnis()
        self.app.senden_nach_erfolg_var.set(True)
        name = os.path.basename(ergebnis)
        with mock.patch.object(APP.PS5ConverterGUI, "_nach_erfolg_senden_starten") as senden:
            with mock.patch.object(fz.messagebox, "askyesno", return_value=True) as frage:
                self.f._nach_erfolg("bauen", ergebnis, None)
            self.assertEqual((self.app._t("dialog.title.nach_erfolg_senden"),
                              self.app._t("dialog.msg.nach_erfolg_senden_frage", name=name)), frage.call_args[0])
            senden.assert_called_once_with([ergebnis])
            senden.reset_mock()
            with mock.patch.object(fz.messagebox, "askyesno", return_value=False):
                self.f._nach_erfolg("abbild", ergebnis, None)
            senden.assert_not_called()

    def test_ohne_haken_ueber_aufgabe_1_und_ohne_ergebnis_wird_nichts_gesendet(self) -> None:
        _quelle, ergebnis, _stempel = self._quelle_und_ergebnis()
        with mock.patch.object(APP.PS5ConverterGUI, "_nach_erfolg_senden_starten") as senden, \
                mock.patch.object(fz.messagebox, "askyesno", return_value=True) as frage:
            self.f._nach_erfolg("bauen", ergebnis, None)                 # Haken aus
            self.app.senden_nach_erfolg_var.set(True)
            self.f._nach_erfolg("umwandeln", ergebnis, None)             # Aufgabe 1 hat gesendet
            self.f._nach_erfolg("pruefen", "", None)                     # keine Datei
            self.f._nach_erfolg("konsole", "", None)                     # liegt schon auf der Konsole
        senden.assert_not_called()
        frage.assert_not_called()

    def test_herunterfahren_nach_dem_erfolg_aber_nie_nach_einem_befund_und_ohne_sendefrage(self) -> None:
        _quelle, ergebnis, _stempel = self._quelle_und_ergebnis()
        self.app.shutdown_after_success.set(True)
        self.app.senden_nach_erfolg_var.set(True)
        gemerkt: list = []
        with mock.patch.object(APP.PS5ConverterGUI, "_maybe_shutdown_after_task",
                               side_effect=lambda: gemerkt.append(bool(self.app._last_task_ok))), \
                mock.patch.object(fz.messagebox, "askyesno", return_value=True) as frage:
            self.f._nach_erfolg("bauen", ergebnis, None, befund=True)
            self.assertEqual([], gemerkt, "nach einem Befund bleibt der Rechner an")
            self.f._nach_erfolg("bauen", ergebnis, None)
            self.f._nach_erfolg("pruefen", "", None)
            self.f._nach_erfolg("konsole", "", None)
            self.f._nach_erfolg("extrahieren", ergebnis, None)
        self.assertEqual([True, True, True, True], gemerkt, "bei Erfolg: der Merker steht auf Erfolg")
        frage.assert_not_called()                                          # niemand koennte antworten - wie in den Aufgaben 1 bis 6

    def test_der_rechner_faehrt_erst_nach_dem_loeschen_herunter(self) -> None:
        quelle, ergebnis, stempel = self._quelle_und_ergebnis()
        self.app.shutdown_after_success.set(True)
        stand: list = []
        with mock.patch.object(APP.PS5ConverterGUI, "_maybe_shutdown_after_task",
                               side_effect=lambda: stand.append(os.path.exists(quelle))):
            self.f._nach_erfolg("bauen", ergebnis, {"quelle": quelle, "stempel": stempel})
            self.assertTrue(basis._warten(lambda: bool(stand), 15))
        self.assertEqual([False], stand, "die Quelle war schon weg, als das Herunterfahren begann")

    # ---------------- die Erfolgsmeldung wie nach den Aufgaben 1 bis 6 ----------------
    def _erfolgsmeldungen(self) -> list:
        """Die Meldungen "Erfolg - Vorgang erfolgreich abgeschlossen!", die das Fenster bisher gezeigt hat."""
        paar = (self.app._t("dialog.title.success"), self.app._t("dialog.msg.task_completed_successfully"))
        return [a for a in self.dialoge["info"] if tuple(a[:2]) == paar]

    def test_bauen_abbild_und_entpacken_melden_den_erfolg_wie_die_aufgaben_1_bis_6(self) -> None:
        """Nutzerwunsch 17.11.2026: Nach einem erfolgreich erstellten Ergebnis erscheint dieselbe Meldung wie nach den Aufgaben 1 bis 6
        (Titel "Erfolg", Text "Vorgang erfolgreich abgeschlossen!") - einmal je Auftrag."""
        _quelle, ergebnis, _stempel = self._quelle_und_ergebnis()
        for art in self.f.MELDUNG_ARTEN:
            with self.subTest(art=art):
                self.dialoge["info"].clear()
                self.f._nach_erfolg(art, ergebnis, None)
                self.assertEqual(1, len(self._erfolgsmeldungen()))
        self.assertEqual(("bauen", "abbild", "extrahieren"), self.f.MELDUNG_ARTEN)

    def test_der_ganze_auftrag_meldet_den_erfolg(self) -> None:
        """Ueber ``_job_beendet`` mit dem echten ``_nach_erfolg``: Bauen, Abbild und Extrahieren zeigen die Meldung am Ende."""
        f = self.f
        _quelle, ergebnis, _stempel = self._quelle_und_ergebnis()
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "Q"), typ=wz.TYP_ORDNER)
        for art, ende in (("bauen", {"ok": True, "pkg": ergebnis, "pruefung": "p", "befund": False}),
                          ("abbild", {"ok": True, "pkg": ergebnis, "pruefung": "p", "befund": False}),
                          ("extrahieren", {"ok": True, "text": "t"})):
            with self.subTest(art=art), mock.patch.object(type(f), "_ausgabe_nach_erfolg"):
                self.dialoge["info"].clear()
                f._job = {"art": art, "info": info, "ziel": self.ordner, "start": time.monotonic(), "letzte": time.monotonic(),
                          "zeichen": None, "loeschen": None}
                f._job_beendet(ende)
                self.assertEqual(1, len(self._erfolgsmeldungen()))

    def test_keine_meldung_bei_umwandeln_pruefen_konsole_befund_und_herunterfahren(self) -> None:
        """Ueber Aufgabe 1 meldet Aufgabe 1 selbst (sonst doppelt); Pruefen und "auf die PS5 entpacken" erstellen nichts; ein Befund ist
        kein Erfolg; beim Herunterfahren wuerde die Meldung auf eine Bestaetigung warten, die niemand gibt."""
        _quelle, ergebnis, _stempel = self._quelle_und_ergebnis()
        self.f._nach_erfolg("umwandeln", ergebnis, None)
        self.f._nach_erfolg("pruefen", "", None)
        self.f._nach_erfolg("konsole", "", None)
        self.f._nach_erfolg("bauen", ergebnis, None, befund=True)
        self.assertEqual([], self._erfolgsmeldungen())
        self.app.shutdown_after_success.set(True)
        with mock.patch.object(APP.PS5ConverterGUI, "_maybe_shutdown_after_task"):
            for art in self.f.MELDUNG_ARTEN:
                self.f._nach_erfolg(art, ergebnis, None)
        self.assertEqual([], self._erfolgsmeldungen(), "beim Herunterfahren steht der Erfolg nur in Statuszeile und Protokoll")

    def test_die_meldung_kommt_vor_der_sendefrage(self) -> None:
        """Wie im Hauptfenster: erst "Vorgang erfolgreich abgeschlossen!", dann die Frage, ob das Ergebnis an die PS5 geht."""
        _quelle, ergebnis, _stempel = self._quelle_und_ergebnis()
        self.app.senden_nach_erfolg_var.set(True)
        reihenfolge: list = []
        with mock.patch.object(type(self.f), "_erfolg_melden", side_effect=lambda: reihenfolge.append("meldung")), \
                mock.patch.object(type(self.f), "_senden_fragen", side_effect=lambda e: reihenfolge.append("senden")):
            self.f._nach_erfolg("bauen", ergebnis, None)
        self.assertEqual(["meldung", "senden"], reihenfolge)

    def test_nach_dem_loeschen_der_quelle_kommt_die_meldung(self) -> None:
        quelle, ergebnis, stempel = self._quelle_und_ergebnis()
        self.f._nach_erfolg("bauen", ergebnis, {"quelle": quelle, "stempel": stempel})
        self.assertEqual([], self._erfolgsmeldungen(), "erst wird die Quelle geloescht")
        self.assertTrue(basis._warten(lambda: not self.f.beschaeftigt() and not os.path.exists(quelle), 15))
        basis._pumpen(0.2)
        self.assertEqual(1, len(self._erfolgsmeldungen()))

    # ---------------- der Weg ueber Aufgabe 1 ----------------
    def test_die_uebergabe_fragt_nicht_noch_einmal_nach_dem_arbeitsordner(self) -> None:
        """Seite 7 hat beim Start nach dem Paket gefragt; Aufgabe 1 bekommt nur den Arbeitsordner und soll nicht nach ihm fragen."""
        self.app.quelle_loeschen_var.set(True)
        gesehen: list = []
        with mock.patch.object(self.app, "_launch_task", side_effect=lambda: gesehen.append(self.app.quelle_loeschen_var.get())):
            self.assertTrue(self.f._uebergeben(self.ordner, quelle_schon_gefragt=True))
            self.assertTrue(self.app.quelle_loeschen_var.get(), "der Haken bleibt, wie er war")
            self.assertTrue(self.f._uebergeben(self.ordner))
        self.assertEqual([False, True], gesehen, "ein Spielordner als Quelle: Aufgabe 1 fragt selbst")

    def test_nach_der_uebergabe_loescht_seite_7_die_quelle_des_pakets(self) -> None:
        quelle, ergebnis, stempel = self._quelle_und_ergebnis()
        loeschen = {"quelle": quelle, "stempel": stempel}
        f = self.f
        f._uebergabe = {"staging": "", "gesehen": True, "info": None, "ziel": self.ziel, "ziel_vorher": None, "name": "Quelle",
                        "loeschen": loeschen}
        self.app._last_task_ok = True
        self.app.task_final_output_path = ergebnis
        aufrufe: list = []
        with mock.patch.object(type(f), "_a1_arbeitet_noch", return_value=False), \
                mock.patch.object(self.app, "is_running", False), \
                mock.patch.object(type(f), "_nach_erfolg", side_effect=lambda *a, **k: aufrufe.append(a)):
            f._uebergabe_beobachten()
        self.assertEqual([("umwandeln", ergebnis, loeschen)], aufrufe)

    def test_jeder_auftrag_meldet_seinen_erfolg_mit_dem_richtigen_ergebnis(self) -> None:
        """Bauen, Abbild, Extrahieren, Pruefen und Auf-die-PS5-entpacken rufen am Ende ``_nach_erfolg``: mit dem Ergebnis auf dem
        Rechner (Paket, Abbild, Ordner), der Loeschung vom Start und - bei einem Befund - dem Befund."""
        f = self.f
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "Q"), typ=wz.TYP_ORDNER)
        loeschen = {"quelle": info.pfad, "stempel": None}
        faelle = (
            ("bauen", {"ok": True, "pkg": "P.pkg", "pruefung": "p", "befund": False}, loeschen, ("bauen", "P.pkg", loeschen, False)),
            ("abbild", {"ok": True, "pkg": "A.ffpkg", "pruefung": "p", "befund": True}, loeschen, ("abbild", "A.ffpkg", loeschen, True)),
            ("extrahieren", {"ok": True, "text": "t"}, loeschen, ("extrahieren", self.ordner, loeschen)),
            ("pruefen", {"ok": True, "text": "t", "befund": True}, None, ("pruefen", "", None, True)),
            ("konsole", {"ok": True, "text": "t"}, None, ("konsole", "", None)),
        )
        aufrufe: list = []
        for art, ende, loesch, erwartet in faelle:
            with self.subTest(art=art), mock.patch.object(type(f), "_nach_erfolg", side_effect=lambda *a, **k: aufrufe.append(a)), \
                    mock.patch.object(type(f), "_ausgabe_nach_erfolg"):
                aufrufe.clear()
                f._job = {"art": art, "info": info, "ziel": self.ordner, "start": time.monotonic(), "letzte": time.monotonic(),
                          "zeichen": None, "loeschen": loesch}
                f._job_beendet(ende)
                self.assertEqual([erwartet], aufrufe)

    def test_das_entpacken_gibt_die_loeschung_an_die_uebergabe_weiter(self) -> None:
        """Ein Paket wird erst entpackt (Arbeitsordner) und geht dann an Aufgabe 1: Die Rueckfrage zur Quelle - dem Paket - stand
        beim Start; sie wandert mit in die Uebergabe, und Aufgabe 1 fragt nicht noch einmal."""
        f = self.f
        loeschen = {"quelle": os.path.join(self.ordner, "Paket.pkg"), "stempel": None}
        info = wz.PaketInfo(pfad=loeschen["quelle"], typ=wz.TYP_ORDNER)
        f._job = {"art": "umwandeln", "info": info, "ziel": self.ordner, "start": time.monotonic(), "letzte": time.monotonic(),
                  "zeichen": None, "loeschen": loeschen}
        self.addCleanup(setattr, f, "_uebergabe", None)
        aufrufe: list = []
        with mock.patch.object(type(f), "_uebergeben", side_effect=lambda staging, quelle_schon_gefragt=False: (
                aufrufe.append((staging, quelle_schon_gefragt)), True)[1]):
            f._job_beendet({"ok": True, "text": "entpackt"})
        self.assertEqual(loeschen, f._uebergabe["loeschen"])
        self.assertEqual([(self.ordner, True)], aufrufe)

    def test_ein_fehlschlag_wegen_einer_verbindung_im_spielordner_steht_in_der_sprache_des_fensters_im_protokoll(self) -> None:
        """Dump Forge lehnt einen Spielordner mit Verknuepfung, Junction oder Reparsepunkt englisch ab ("symlink (not followed)", gemessen
        19.11.2026); das Protokoll zeigte den Text bisher so. Jetzt steht er in der Sprache des Fensters da."""
        f = self.f
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "Q"), typ=wz.TYP_ORDNER)
        f._job = {"art": "bauen", "info": info, "ziel": self.ordner, "start": time.monotonic(), "letzte": time.monotonic(),
                  "zeichen": None, "loeschen": None}
        zeilen: list = []
        text = "C:\\Spiele\\Spiel holds entries that cannot be converted:\n  symlink (not followed): Verbindung"
        with mock.patch.object(f, "_protokoll", side_effect=zeilen.append):
            f._job_beendet({"ok": False, "text": text})
        self.assertEqual(1, len(zeilen), zeilen)
        self.assertIn(f.t("ps5pkg.forge_scan_kopf", ordner="C:\\Spiele\\Spiel"), zeilen[0])
        self.assertIn(f.t("ps5pkg.forge_scan_link") + ": Verbindung", zeilen[0])
        self.assertNotIn("C:\\Spiele\\Spiel holds entries", zeilen[0], "Forges Kopfzeile ist ersetzt (in jeder Sprache)")

    def test_ein_anderer_fehlschlag_bleibt_unveraendert_im_protokoll(self) -> None:
        f = self.f
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "Q"), typ=wz.TYP_ORDNER)
        f._job = {"art": "bauen", "info": info, "ziel": self.ordner, "start": time.monotonic(), "letzte": time.monotonic(),
                  "zeichen": None, "loeschen": None}
        zeilen: list = []
        with mock.patch.object(f, "_protokoll", side_effect=zeilen.append):
            f._job_beendet({"ok": False, "text": "Das Ziel gibt es schon: x.pkg"})
        self.assertEqual([f.t("ps5pkg.log_failed", grund="Das Ziel gibt es schon: x.pkg")], zeilen)


if __name__ == "__main__":
    unittest.main()
