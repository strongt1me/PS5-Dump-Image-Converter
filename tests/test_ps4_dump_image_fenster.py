# -*- coding: utf-8 -*-
"""Das Fenster „PS4 PKG Dump & Image Converter“ (``ps5_validator/ui/ps4_dump_image.py``), seit 07.10.2026.

Es ersetzt „PS4 PKG -> OTA“ und „PS4 PKG -> ffpfsc“. Die Arbeit hinter den Knoepfen pruefen
``test_ps4_abbild.py`` und ``test_ps4_fortschritt.py``; hier geht es um das Fenster selbst: Es oeffnet und
schliesst sauber, ein PS5-Titel bekommt beim Update-Suchen den Hinweis statt einer Netzanfrage, ein
bereits entpacktes Spiel wird als Quelle erkannt.

Sonys Update-Adresse antwortet mit dem PS4-Verfahren fuer 16 gemessene PPSA-Titel mit 404 (die Gegenprobe
mit CUSA03877: 200), ein Verfahren fuer die PS5 ist oeffentlich nirgends belegt - das Fenster fragt dort
deshalb nicht, sondern sagt es.
"""
from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

from ps5_validator.ui import ps4_dump_image as fenster_modul   # noqa: E402
from ps5_validator.utils import ps4_abbild as ab               # noqa: E402
from ps5_validator.utils.i18n import STRINGS                   # noqa: E402


class _Probe:
    """Nur die Teile des Fensters, die ``_update_online`` anfasst."""

    def __init__(self, title_id: str) -> None:
        self.spiel = ab.Spiel(title_id=title_id, titel="X")
        self.status: list[str] = []
        self.log: list[str] = []
        self._z: dict = {}
        self.t = lambda schluessel, **w: STRINGS[schluessel]["de"].format(**w)

    def _frei(self) -> bool:
        return True

    def _gewaehlt(self):
        return [self.spiel]

    def _status(self, text: str) -> None:
        self.status.append(text)

    def _protokoll(self, text: str) -> None:
        self.log.append(text)

    def _warnung(self, *a, **k) -> None:
        raise AssertionError("keine Warnung erwartet")

    def _knoepfe_pruefen(self) -> None:
        pass


class Ps5UpdateTests(unittest.TestCase):

    def test_bei_ps5_wird_nicht_im_netz_gefragt(self) -> None:
        f = _Probe("PPSA01284")
        with mock.patch.object(fenster_modul.upd, "nachsehen") as netz, \
                mock.patch.object(fenster_modul.threading, "Thread") as faden:
            fenster_modul.Ps4DumpImageFenster._update_online(f)   # type: ignore[arg-type]
        netz.assert_not_called()
        faden.assert_not_called()
        self.assertEqual(f.status, f.log)
        self.assertIn("PS5-Titel", f.log[0])

    def test_ps4_titel_fragen_weiter_im_netz(self) -> None:
        f = _Probe("CUSA03877")
        with mock.patch.object(fenster_modul.threading, "Thread") as faden:
            fenster_modul.Ps4DumpImageFenster._update_online(f)   # type: ignore[arg-type]
        faden.assert_called_once()
        self.assertTrue(f._z["update_laeuft"])
        self.assertNotIn("PS5-Titel", " ".join(f.log))

    def test_texte_sind_zweisprachig_und_nennen_den_grund(self) -> None:
        text = STRINGS["ps4ota.update_ps5_hinweis"]
        self.assertNotEqual(text["de"], text["en"])
        self.assertIn("PS5", text["en"])


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        # Die Spiel-Info fragt fehlende Angaben online nach (orbispatches.com) - nicht aus den Tests heraus.
        cls._netz = mock.patch.object(cls.app, "_metadaten_online_erlaubt", return_value=False)
        cls._netz.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._netz.stop()

    def _fenster(self):
        f = fenster_modul.oeffnen(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT, self.haupt.pt)
        self.addCleanup(lambda: f.win.winfo_exists() and f.win.destroy())
        _WURZEL.update()
        return f

    def test_ein_einziges_fenster(self) -> None:
        f = self._fenster()
        self.assertIs(f, fenster_modul.oeffnen(self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT,
                                               self.haupt.pt))

    def test_die_formate_stehen_zur_wahl(self) -> None:
        f = self._fenster()
        self.assertEqual(set(ab.FORMATE), set(f._formate))

    def test_ein_entpacktes_spiel_laesst_nur_abbilder_zu(self) -> None:
        """Meldung 07.10.2026: Bei \"Entpacktes PS4-Spiel\" durfte \"Dump-Ordner\" gewaehlt werden."""
        f = self._fenster()
        f.format_var.set(f._formate[ab.FORMAT_DUMP])
        f.art_var.set(fenster_modul.QUELLE_DUMP)
        _WURZEL.update()
        werte = tuple(f.format_box.cget("values"))
        self.assertEqual({f._formate[ab.FORMAT_FFPFSC], f._formate[ab.FORMAT_EXFAT]}, set(werte))
        self.assertEqual(f._formate[ab.FORMAT_FFPFSC], f.format_var.get(), "Ein ungueltiges Format wird ersetzt.")
        f.art_var.set(fenster_modul.QUELLE_ORDNER)
        self.assertEqual(set(ab.FORMATE), set(f._formate))
        self.assertEqual(len(f._formate), len(tuple(f.format_box.cget("values"))))

    def test_ein_druck_auf_einen_quellknopf_oeffnet_die_wahl(self) -> None:
        f = self._fenster()
        for art, dialog in ((fenster_modul.QUELLE_ORDNER, "askdirectory"), (fenster_modul.QUELLE_DATEIEN, "askopenfilenames"),
                            (fenster_modul.QUELLE_DUMP, "askdirectory")):
            with self.subTest(art=art), mock.patch.object(fenster_modul.filedialog, dialog, return_value="") as dlg:
                f.art_var.set(art)
                f._quelle_gewaehlt()
                dlg.assert_called_once()

    def test_die_gewaehlte_quelle_wird_gleich_eingelesen_ohne_eingabefeld(self) -> None:
        """Seit 07.10.2026 gibt es kein Pfadfeld mehr: Die Wahl im Dialog gilt und liest ein."""
        quelle = (PROJEKT / "ps5_validator" / "ui" / "ps4_dump_image.py").read_text(encoding="utf-8")
        self.assertNotIn("pw.Entry(pfad_reihe", quelle)
        f = self._fenster()
        f.art_var.set(fenster_modul.QUELLE_ORDNER)
        with tempfile.TemporaryDirectory() as tmp,                 mock.patch.object(fenster_modul.filedialog, "askdirectory", return_value=tmp),                 mock.patch.object(f, "_einlesen") as lesen:
            f._quelle_waehlen()
            lesen.assert_called_once()
            self.assertEqual(os.path.normpath(tmp), f.quelle_var.get())

    def test_der_balken_zeigt_die_prozentzahl_und_die_suche_wandert(self) -> None:
        f = self._fenster()
        f._balken_setzen(42.4)
        self.assertEqual("42 %", f.prozent_var.get())
        f._balken_setzen(None)
        self.assertEqual("…", f.prozent_var.get())
        self.assertTrue(f._balken_unbestimmt)
        f._balken_setzen(100.0)
        self.assertEqual("100 %", f.prozent_var.get())
        self.assertFalse(f._balken_unbestimmt, "Nach der Suche ist der Balken wieder bestimmt.")
        f._balken_setzen(250)
        self.assertEqual("100 %", f.prozent_var.get())

    def test_nach_dem_einlesen_steht_der_balken_nicht_irgendwo(self) -> None:
        """Meldung 07.10.2026: Der Balken blieb nach dem Einlesen auf dem Wert des letzten Pakets stehen."""
        from ps5_validator.utils import ps4pkg_bibliothek as bib
        f = self._fenster()
        f._balken_setzen(65.0)
        fremd = bib.PkgEintrag(pfad="E:/x.pkg", lesbar=False, fehler="kein PS4-Paket (Kennung fehlt)")
        defekt = bib.PkgEintrag(pfad="E:/y.pkg", lesbar=False, fehler="Pruefsumme falsch")
        f._z.update(scan_fertig=True, scan_fehler="", scan_ergebnis=([fremd, defekt], None))
        f._scan_fertig()
        self.assertEqual("100 %", f.prozent_var.get())
        text = f.protokoll.get("1.0", "end")
        self.assertIn(STRINGS["ps4dib.nicht_ps4_header"]["de"].format(anzahl=1), text)
        self.assertIn(STRINGS["ps4pkg.rejected_header"]["de"].format(anzahl=1), text)

    def test_ein_fehler_beim_einlesen_setzt_den_balken_zurueck(self) -> None:
        f = self._fenster()
        f._balken_setzen(65.0)
        f._z.update(scan_fertig=True, scan_fehler="Absturz", scan_ergebnis=None)
        f._scan_fertig()
        self.assertEqual("0 %", f.prozent_var.get())

    def _zwei_basen(self):
        from ps5_validator.utils import ps4pkg_bibliothek as bib
        eintraege = [bib.PkgEintrag(pfad="E:/a.pkg", lesbar=True, title_id="CUSA00001", titel="X", typ=bib.TYP_BASIS,
                                    app_ver="01.00", groesse=10),
                     bib.PkgEintrag(pfad="E:/b.pkg", lesbar=True, title_id="CUSA00001", titel="X", typ=bib.TYP_BASIS,
                                    app_ver="01.02", groesse=20)]
        f = self._fenster()
        f.pakete = eintraege
        f._gruppieren()
        return f, f.spiele["CUSA00001"]

    def test_bei_mehreren_basispaketen_wird_gefragt_aber_nur_einmal(self) -> None:
        f, spiel = self._zwei_basen()
        self.assertEqual(2, len(spiel.basen))

        def waehle(s):
            s.basis_setzen(s.basen[0])
            f._basis_wahl[s.title_id] = s.basis.pfad
            return True

        with mock.patch.object(f, "_basis_waehlen", side_effect=waehle) as dlg:
            self.assertTrue(f._basen_klaeren([spiel]))
            self.assertTrue(f._basen_klaeren([spiel]))
            dlg.assert_called_once()
        self.assertEqual("E:/a.pkg", spiel.basis.pfad)
        f._basis_wahl.clear()
        with mock.patch.object(f, "_basis_waehlen", return_value=False):
            _, neu = self._zwei_basen()
            self.assertFalse(f._basen_klaeren([neu]), "Abbruch im Dialog bricht den Lauf ab.")

    def test_die_wahl_ueberlebt_ein_neues_gruppieren(self) -> None:
        f, spiel = self._zwei_basen()
        spiel.basis_setzen(spiel.basen[0])
        f._basis_wahl["CUSA00001"] = spiel.basis.pfad
        f._gruppieren()
        neu = f.spiele["CUSA00001"]
        self.assertEqual("E:/a.pkg", neu.basis.pfad)
        self.assertTrue(neu.basis_gewaehlt)

    def test_ein_geladenes_update_meldet_den_erfolg_und_fuellt_den_balken(self) -> None:
        """Meldung 07.10.2026: Der Balken blieb bei 99 %, ein Abschluss wurde nicht gemeldet."""
        from ps5_validator.utils import ps4pkg_aufgaben as au
        with tempfile.TemporaryDirectory() as tmp:
            pkg = os.path.join(tmp, "CUSA00001-patch-v01.02.pkg")
            with open(pkg, "wb") as datei:
                datei.write(b"\x7fCNT" + b"\x00" * 100)
            f = self._fenster()
            f._balken_setzen(99.0)
            a = au.Aufgabe(kennung=7, art="update", titel="Update")
            a.status, a.ergebnis = au.FERTIG, pkg
            with mock.patch.object(fenster_modul.messagebox, "showinfo") as box:
                f._update_geladen(a)
            self.assertEqual("100 %", f.prozent_var.get())
            self.assertIn("✓", f.status_var.get())
            self.assertIn("CUSA00001-patch-v01.02.pkg", f.status_var.get())
            box.assert_called_once()

    def test_nach_dem_abbrechen_zeigt_die_statuszeile_den_abbruch_statt_des_fortschritts(self) -> None:
        """Meldung 09.10.2026: Nach dem Abbrechen lief die Anzeige weiter, als haette der Knopf nichts getan."""
        import time
        from ps5_validator.utils import ps4pkg_aufgaben as au
        f = self._fenster()
        a = au.Aufgabe(kennung=3, art="abbild", titel="Testspiel", status=au.LAEUFT, text="Räume auf …")
        f._batch_beginn = time.monotonic()
        f._stapel_anzeigen([a.kopie()])
        self.assertIn("Rest", f.status_var.get(), "Ohne Abbruch zeigt die Zeile den gewohnten Fortschritt")
        a.abbruch.set()
        f._stapel_anzeigen([a.kopie()])
        text = f.status_var.get()
        self.assertEqual(STRINGS["ps4dib.status_abbruch"]["de"].format(titel="Testspiel", text="Räume auf …"), text)
        self.assertNotIn("Rest", text)

    def test_ausserhalb_des_stapels_gilt_dasselbe(self) -> None:
        from ps5_validator.utils import ps4pkg_aufgaben as au
        f = self._fenster()
        a = au.Aufgabe(kennung=4, art="update", titel="Update", status=au.LAEUFT, text="lade")
        a.abbruch.set()
        f._kurz_laeuft(a.kopie())
        self.assertEqual(STRINGS["ps4dib.status_abbruch"]["de"].format(titel="Update", text="lade"),
                         f.status_var.get())

    def test_die_texte_zum_abbruch_sind_zweisprachig(self) -> None:
        for schluessel in ("ps4dib.status_abbruch", "ps4dib.log_raeumt_spaeter"):
            with self.subTest(schluessel=schluessel):
                self.assertNotEqual(STRINGS[schluessel]["de"], STRINGS[schluessel]["en"])

    def test_die_quellknoepfe_rufen_die_wahl_auf(self) -> None:
        quelle = (PROJEKT / "ps5_validator" / "ui" / "ps4_dump_image.py").read_text(encoding="utf-8")
        self.assertIn("command=self._quelle_gewaehlt", quelle)

    def test_schliessen_setzt_das_programm_zurueck(self) -> None:
        f = self._fenster()
        f._schliessen()
        _WURZEL.update()
        self.assertIsNone(getattr(self.app, fenster_modul.FENSTER_ATTRIBUT, None))

    def test_ein_entpacktes_spiel_wird_als_quelle_erkannt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sfo = Path(tmp) / "sce_sys"
            sfo.mkdir()
            sys.path.insert(0, str(PROJEKT))
            from test_ps4_abbild import _sfo
            (sfo / "param.sfo").write_bytes(_sfo({"TITLE_ID": "CUSA00001", "TITLE": "Testspiel", "APP_VER": "01.05"}))
            f = self._fenster()
            f.art_var.set(fenster_modul.QUELLE_DUMP)
            f.quelle_var.set(tmp)
            f._einlesen()
            self.assertIn("CUSA00001", f.spiele)
            self.assertEqual(os.path.abspath(tmp), f.spiele["CUSA00001"].dump_ordner)
            self.assertEqual(("CUSA00001",), tuple(f.liste.get_children()))

    @staticmethod
    def _png() -> bytes:
        import io
        from PIL import Image
        puffer = io.BytesIO()
        Image.new("RGB", (64, 64), (200, 30, 30)).save(puffer, "PNG")
        return puffer.getvalue()

    def test_ein_gewaehltes_paket_fuellt_seitenleiste_und_spiel_info(self) -> None:
        """Nutzerwunsch 14.10.2026: Cover in der Seitenleiste und Metadaten in "Spiel Info - Updates & Patches"
        wie bei den Aufgaben 1 bis 6 - auch auf der Seite PKG."""
        from test_ps4pkg_bibliothek import paket_bauen
        from ps5_validator.utils import ps4pkg_bibliothek as bib
        with tempfile.TemporaryDirectory() as tmp:
            pfad = paket_bauen(Path(tmp) / "spiel.pkg", titel="Testspiel", title_id="CUSA00001", app_ver="01.02")
            f = self._fenster()
            f.pakete = [bib.lese_paket(str(pfad))]
            with mock.patch.object(fenster_modul.bib, "lese_bild", return_value=self._png()), \
                    mock.patch.object(self.app, "_metadaten_online_erlaubt", return_value=False), \
                    mock.patch.object(self.app, "_update_info_box", wraps=self.app._update_info_box) as box:
                f._gruppieren()
                _WURZEL.update()
            box.assert_called()
            meta, cover = box.call_args[0][0], box.call_args[0][1]
            self.assertEqual("Testspiel", meta["title"])
            self.assertEqual("CUSA00001", meta["title_id"])
            self.assertEqual("UP0000-CUSA00001_00-0000000000000000", meta["content_id"])
            self.assertEqual("01.02", meta["version"])
            self.assertEqual("PS4", meta["platform"])
            self.assertIsNotNone(cover, "Das Cover kommt aus dem Paket (icon0.png).")
            self.assertEqual("CUSA00001", self.app._meta_labels["title_id"].get())
            self.assertEqual("PKG", self.app._info_format_var.get())

    def test_ein_entpacktes_spiel_fuellt_seitenleiste_und_spiel_info(self) -> None:
        from test_ps4_abbild import _sfo
        with tempfile.TemporaryDirectory() as tmp:
            sce = Path(tmp) / "sce_sys"
            sce.mkdir()
            (sce / "param.sfo").write_bytes(_sfo({"TITLE_ID": "CUSA00002", "TITLE": "Dumpspiel", "APP_VER": "01.05"}))
            (sce / "icon0.png").write_bytes(self._png())
            f = self._fenster()
            f.art_var.set(fenster_modul.QUELLE_DUMP)
            f.quelle_var.set(tmp)
            with mock.patch.object(self.app, "_metadaten_online_erlaubt", return_value=False), \
                    mock.patch.object(self.app, "_update_info_box", wraps=self.app._update_info_box) as box:
                f._einlesen()
                _WURZEL.update()
            meta, cover = box.call_args[0][0], box.call_args[0][1]
            self.assertEqual("Dumpspiel", meta["title"])
            self.assertEqual("01.05", meta["version"])
            self.assertIsNotNone(cover)
            self.assertEqual("Dump", self.app._info_format_var.get())

    def test_fehlende_angaben_kommen_online_nach_wie_bei_den_aufgaben(self) -> None:
        """Nutzerhinweis 14.10.2026: PS4-Titel ueber orbispatches.com - derselbe Weg (_enrich_meta_online) wie bei
        den Aufgaben 1 bis 6, im Faden; ohne Erlaubnis (metadata_online) wird nicht gefragt."""
        from ps5_validator.utils import ps4pkg_bibliothek as bib
        f = self._fenster()
        f.pakete = [bib.PkgEintrag(pfad="E:/a.pkg", lesbar=True, title_id="CUSA00003", titel="Netzspiel",
                                   typ=bib.TYP_BASIS, app_ver="01.00", groesse=10)]

        def nachschlag(meta, tid):
            self.assertEqual("CUSA00003", tid)
            return dict(meta, publisher="Testverlag", genre="Rennen"), None

        with mock.patch.object(fenster_modul.bib, "lese_bild", return_value=None), \
                mock.patch.object(self.app, "_metadaten_online_erlaubt", return_value=False), \
                mock.patch.object(self.app, "_enrich_meta_online") as netz:
            f._gruppieren()
            _WURZEL.update()
        netz.assert_not_called()
        with mock.patch.object(fenster_modul.bib, "lese_bild", return_value=None), \
                mock.patch.object(self.app, "_metadaten_online_erlaubt", return_value=True), \
                mock.patch.object(self.app, "_enrich_meta_online", side_effect=nachschlag) as netz:
            f._spielinfo_zeigen()
            # Der Faden meldet sich ueber root.after - das nimmt Tk nur an, solange mainloop() wirklich laeuft.
            import time
            ende = time.monotonic() + 5.0

            def _wache() -> None:
                if self.app._meta_labels["publisher"].get() == "Testverlag" or time.monotonic() >= ende:
                    _WURZEL.quit()
                    return
                _WURZEL.after(20, _wache)

            _WURZEL.after(20, _wache)
            _WURZEL.mainloop()
        netz.assert_called_once()
        self.assertEqual("Testverlag", self.app._meta_labels["publisher"].get())
        self.assertEqual("CUSA00003", self.app._meta_labels["title_id"].get())

    def test_ohne_auswahl_bleibt_die_anzeige_unberuehrt(self) -> None:
        f = self._fenster()
        f.spiele = {}
        f.liste.delete(*f.liste.get_children())
        with mock.patch.object(self.app, "_update_info_box") as box:
            f._spielinfo_zeigen()
        box.assert_not_called()

    def test_die_seite_pkg_zieht_die_spiel_info_nach(self) -> None:
        quelle = (PROJEKT / "ps5_validator" / "ui" / "pkg_fpkg_seite.py").read_text(encoding="utf-8")
        rumpf = quelle.split("def pkg_zeigen", 1)[1].split("def fpkg_zeigen", 1)[0]
        self.assertIn("fenster.spielinfo_nachziehen()", rumpf)

    def test_ein_ordner_ohne_param_sfo_wird_gemeldet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = self._fenster()
            f.art_var.set(fenster_modul.QUELLE_DUMP)
            f.quelle_var.set(tmp)
            f._einlesen()
            self.assertEqual({}, f.spiele)
            self.assertEqual(STRINGS["ps4dib.dump_ohne_sfo"]["de"], f.status_var.get())


if __name__ == "__main__":
    unittest.main()
