# -*- coding: utf-8 -*-
"""Sammelkonvertierung (Aufgabe 5): Dump-Ordner als Quelle waehlen (05.10.2026).

Der Nutzer: "Bei der Sammelkonvertierung fehlt die Auswahl Dump-Ordner als Quelle."
Die Verarbeitung konnte Ordner schon lange (``_sammelquellen_aufloesen``, die
"folder"-Zweige in ``_execute_conversion_by_type``); der Knopf oeffnete aber nur den
Dateidialog, und der zeigt keine Ordner zur Auswahl. Dann die Frage: "Kann man einfach
mehrere Dump Ordner markieren und danach auf Oeffnen klicken?" - unter Windows ja, mit
dem Ordnerdialog des Systems (``ordnerwahl``).

Geprueft wird:

* der Ordnerdialog gegen **echte** Windows-Objekte, soweit das ohne Fenster geht: Optionen
  und Startordner werden zurueckgelesen, eine ``IShellItemArray`` aus drei echten Ordnern
  (Leerzeichen, Umlaute) wird in Pfade zerlegt, der Ablauf bei Abbruch und Fehler,
* der Knopf: Wahl der Quellart, mehrere Ordner, ein Ordner voller Dumps, Dateien wie bisher,
  Abbruch, der Rueckfall von Tk ohne Mehrfachauswahl, Dubletten, ein untauglicher Ordner,
* Groesse, Infobox und Platzpruefung fuer Ordner - an der laufenden Oberflaeche gemessen,
* Texte und die Quellenangabe unter der Formatliste.

Ein Test, der den Systemdialog wirklich zeigt, gehoert nicht in die Reihe (kein Test oeffnet
ein echtes Dialogfenster); der Weg bis ``Show`` ist ueber ``GetOptions``/``GetFolder`` gedeckt.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("sammel_ordner")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ordnerwahl as ow            # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    # Eine Wurzel je Prozess, nie zerstoeren - siehe test_fensterlayout.py.
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    tk = None
    _WURZEL = None
    _TK_DA = False

NUR_WINDOWS = unittest.skipUnless(os.name == "nt", "der Systemdialog mit Mehrfachauswahl ist nur unter Windows da")


def _text(kennung: str, /, **werte) -> str:
    return STRINGS[kennung]["de"].format(**werte)


def _dump(basis: str, name: str, *, mit_eboot: bool = True) -> str:
    """Legt einen Dump-Ordner an: ``eboot.bin`` und ``sce_sys/param.json``."""
    ordner = os.path.join(basis, name)
    os.makedirs(os.path.join(ordner, "sce_sys"), exist_ok=True)
    if mit_eboot:
        Path(ordner, "eboot.bin").write_bytes(b"\x7fELF" + bytes(1020))
    Path(ordner, "sce_sys", "param.json").write_text(
        '{"titleId": "PPSA00000", "localizedParameters": {"defaultLanguage": "de-DE", '
        '"de-DE": {"titleName": "%s"}}}' % name, encoding="utf-8")
    return ordner


# ---------------------------------------------------------------- Ordnerdialog


@NUR_WINDOWS
class OrdnerwahlTests(unittest.TestCase):
    """Der Dialog gegen echte Windows-Objekte - ohne dass ein Fenster aufgeht."""

    def setUp(self) -> None:
        self.basis = tempfile.mkdtemp(prefix="ordnerwahl_")
        self.addCleanup(shutil.rmtree, self.basis, True)
        com = ow._com_einrichten()
        self.assertIsNotNone(com, "Der Hauptfaden muss ein STA sein.")
        self.addCleanup(ow._api()["CoUninitialize"])

    def _ordner(self, *namen: str) -> list[str]:
        pfade = []
        for name in namen:
            pfad = os.path.join(self.basis, name)
            os.makedirs(pfad)
            pfade.append(pfad)
        return pfade

    def test_die_optionen_stehen_im_dialog(self) -> None:
        dialog = ow.dialog_anlegen("Titel")
        self.addCleanup(ow.freigeben, dialog)
        optionen = ow.optionen_lesen(dialog)
        for name, bit in (("FOS_PICKFOLDERS", ow.FOS_PICKFOLDERS),
                          ("FOS_ALLOWMULTISELECT", ow.FOS_ALLOWMULTISELECT),
                          ("FOS_FORCEFILESYSTEM", ow.FOS_FORCEFILESYSTEM),
                          ("FOS_PATHMUSTEXIST", ow.FOS_PATHMUSTEXIST),
                          ("FOS_NOCHANGEDIR", ow.FOS_NOCHANGEDIR)):
            with self.subTest(option=name):
                self.assertTrue(optionen & bit, "%s fehlt: 0x%08X" % (name, optionen))

    def test_der_startordner_wird_gesetzt(self) -> None:
        ziel, = self._ordner("Game Dumps")
        dialog = ow.dialog_anlegen("Titel", ziel)
        self.addCleanup(ow.freigeben, dialog)
        self.assertEqual(os.path.normcase(ziel), os.path.normcase(ow.startordner_lesen(dialog)))

    def test_ein_fehlender_startordner_stoert_nicht(self) -> None:
        dialog = ow.dialog_anlegen("Titel", os.path.join(self.basis, "gibt_es_nicht"))
        self.addCleanup(ow.freigeben, dialog)
        self.assertTrue(ow.optionen_lesen(dialog) & ow.FOS_PICKFOLDERS)

    def test_pfade_aus_einer_echten_liste_in_ihrer_reihenfolge(self) -> None:
        """Drei Ordner mit Leerzeichen und Umlauten durch ``GetCount``/``GetItemAt``/``GetDisplayName``."""
        ordner = self._ordner("Spiel A", "Spiel Ä ü", "Spiel C")
        shell32 = ctypes.WinDLL("shell32")
        shell32.ILCreateFromPathW.argtypes = [ctypes.c_wchar_p]
        shell32.ILCreateFromPathW.restype = ctypes.c_void_p
        shell32.ILFree.argtypes = [ctypes.c_void_p]
        shell32.SHCreateShellItemArrayFromIDLists.argtypes = [
            ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
        shell32.SHCreateShellItemArrayFromIDLists.restype = ctypes.c_long
        pidls = [shell32.ILCreateFromPathW(os.path.normpath(p)) for p in ordner]
        for pidl in pidls:
            self.addCleanup(shell32.ILFree, pidl)
            self.assertTrue(pidl)
        liste = ctypes.c_void_p()
        feld = (ctypes.c_void_p * len(pidls))(*pidls)
        self.assertGreaterEqual(shell32.SHCreateShellItemArrayFromIDLists(
            len(pidls), feld, ctypes.byref(liste)), 0)
        self.addCleanup(ow.freigeben, liste)
        self.assertEqual([os.path.normcase(os.path.normpath(p)) for p in ordner],
                         [os.path.normcase(p) for p in ow.pfade_aus_liste(liste)])

    def test_ein_eintrag_zu_pfad_und_zurueck(self) -> None:
        ordner, = self._ordner("Ordner mit Leerzeichen")
        eintrag = ow.eintrag_zu_pfad(ordner)
        self.addCleanup(ow.freigeben, eintrag)
        self.assertEqual(os.path.normcase(ordner), os.path.normcase(ow._anzeigename(eintrag)))

    def test_die_guid_schreibweise(self) -> None:
        """Die GUID-Strukturen sind bytegenau - eine falsche Byte-Folge liesse CoCreateInstance scheitern."""
        guid = ow._guid(ow.CLSID_FILEOPENDIALOG)
        self.assertEqual(0xDC1C5A9C, guid.Data1)
        self.assertEqual(0xE88A, guid.Data2)
        self.assertEqual(0x4DDE, guid.Data3)
        self.assertEqual([0xA5, 0xA1, 0x60, 0xF8, 0x2A, 0x20, 0xAE, 0xF7], list(guid.Data4))


class OrdnerwahlAblaufTests(unittest.TestCase):
    """``ordner_waehlen`` mit ersetzten Aufrufen: Abbruch, Fehler, Erfolg, Aufraeumen."""

    def setUp(self) -> None:
        self.aufrufe: list[str] = []
        self.show_ergebnis = 0
        self.liste_ergebnis = 0
        self.pfade = ["C:\\Dumps\\A", "C:\\Dumps\\B"]

        def _methode(objekt, stelle, *argtypen, ergebnis=None):
            def _aufruf(*args):
                if stelle == ow._SHOW:
                    self.aufrufe.append("Show")
                    return self.show_ergebnis
                if stelle == ow._GET_RESULTS:
                    self.aufrufe.append("GetResults")
                    return self.liste_ergebnis
                self.aufrufe.append("Stelle%d" % stelle)
                return 0
            return _aufruf

        api = mock.MagicMock()
        api.__getitem__.side_effect = lambda name: (
            lambda *a, **k: self.aufrufe.append(name) or 0)
        for flicken in (
                mock.patch.object(ow, "verfuegbar", return_value=True),
                mock.patch.object(ow, "_methode", _methode),
                mock.patch.object(ow, "_api", return_value=api),
                mock.patch.object(ow, "_com_einrichten", lambda: True),
                mock.patch.object(ow, "dialog_anlegen",
                                  lambda *a, **k: self.aufrufe.append("anlegen") or ctypes.c_void_p(1)),
                mock.patch.object(ow, "_freigeben",
                                  lambda objekt: self.aufrufe.append("freigeben")),
                mock.patch.object(ow, "pfade_aus_liste", lambda liste: list(self.pfade))):
            flicken.start()
            self.addCleanup(flicken.stop)

    def test_ein_erfolg_liefert_die_pfade_und_raeumt_auf(self) -> None:
        self.assertEqual([os.path.normpath(p) for p in self.pfade],
                         ow.ordner_waehlen(titel="T", startordner="C:\\", besitzer=0))
        self.assertEqual(["anlegen", "Show", "GetResults", "freigeben", "freigeben",
                          "CoUninitialize"], self.aufrufe)

    def test_abbruch_ist_eine_leere_liste(self) -> None:
        self.show_ergebnis = ow.HRESULT_ABGEBROCHEN - (1 << 32)   # HRESULT als vorzeichenbehaftete Zahl
        self.assertEqual([], ow.ordner_waehlen())
        self.assertNotIn("GetResults", self.aufrufe)
        self.assertEqual("CoUninitialize", self.aufrufe[-1])
        self.assertIn("freigeben", self.aufrufe)

    def test_ein_anderer_fehler_beim_zeigen_ist_none(self) -> None:
        self.show_ergebnis = -2147467259          # E_FAIL
        self.assertIsNone(ow.ordner_waehlen())
        self.assertEqual("CoUninitialize", self.aufrufe[-1])

    def test_ein_fehler_bei_den_ergebnissen_wirft(self) -> None:
        self.liste_ergebnis = -2147467259
        with self.assertRaises(ow.OrdnerwahlFehler):
            ow.ordner_waehlen()
        self.assertEqual("CoUninitialize", self.aufrufe[-1], "COM blieb eingerichtet.")

    def test_ohne_sta_geht_der_dialog_nicht(self) -> None:
        with mock.patch.object(ow, "_com_einrichten", lambda: None):
            self.assertIsNone(ow.ordner_waehlen())
        self.assertNotIn("anlegen", self.aufrufe)

    def test_laesst_er_sich_nicht_anlegen_ist_es_none(self) -> None:
        def _fehler(*a, **k):
            raise ow.OrdnerwahlFehler("CoCreateInstance", -2147221164)
        with mock.patch.object(ow, "dialog_anlegen", _fehler):
            self.assertIsNone(ow.ordner_waehlen())
        self.assertEqual("CoUninitialize", self.aufrufe[-1])

    def test_ausserhalb_von_windows_gibt_es_ihn_nicht(self) -> None:
        with mock.patch.object(ow, "verfuegbar", return_value=False):
            self.assertIsNone(ow.ordner_waehlen(titel="T"))
        self.assertEqual([], self.aufrufe)

    def test_fehler_tragen_ihren_hresult(self) -> None:
        fehler = ow.OrdnerwahlFehler("x", -2147467259)
        self.assertEqual(0x80004005, fehler.hresult)
        self.assertIn("0x80004005", str(fehler))


# ---------------------------------------------------------------------- Knopf


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class QuellenwahlTests(unittest.TestCase):
    """``_browse_source`` in Aufgabe 5 - am echten Programm, Dialoge aufgezeichnet."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.withdraw()
        for kind in _WURZEL.winfo_children():
            if isinstance(kind, tk.Toplevel):
                kind.withdraw()

    def setUp(self) -> None:
        app = self.app
        self.basis = tempfile.mkdtemp(prefix="sammel_")
        self.addCleanup(shutil.rmtree, self.basis, True)
        self.fragen: list = []          # (titel, text, eintraege) des Auswahlfensters
        self.art = ""                   # was das Auswahlfenster antwortet
        self.dialoge: list = []         # Fehler und Rueckfragen
        self.protokoll: list = []
        # Eigene Variablen ohne Traces: Der Test prueft die Wahl, nicht die Hintergrundmessung.
        for name in ("source_path",):
            flicken = mock.patch.object(app, name, tk.StringVar(master=_WURZEL, value=""))
            flicken.start()
            self.addCleanup(flicken.stop)
        flicken = mock.patch.object(app, "current_mode",
                                    tk.StringVar(master=_WURZEL, value="batch_convert"))
        flicken.start()
        self.addCleanup(flicken.stop)
        app._batch_sources = []
        app._save_setting("batch_quellart", "ordner")
        app._save_setting("last_source_dir", "")

        def _auswahl(titel, frage, eintraege, parent=None):
            self.fragen.append((titel, frage, list(eintraege)))
            return self.art

        for ziel, name, wert in (
                (app, "_auswahl_dialog", _auswahl),
                (app, "_append_to_log", self.protokoll.append)):
            flicken = mock.patch.object(ziel, name, wert)
            flicken.start()
            self.addCleanup(flicken.stop)
        for name in ("showerror", "showwarning", "showinfo"):
            flicken = mock.patch.object(
                APP.messagebox, name, lambda *a, _n=name, **_k: self.dialoge.append((_n,) + a))
            flicken.start()
            self.addCleanup(flicken.stop)
        self.ordner_wahl = mock.Mock(return_value=[])
        flicken = mock.patch.object(ow, "ordner_waehlen", self.ordner_wahl)
        flicken.start()
        self.addCleanup(flicken.stop)

    # -- Hilfen ------------------------------------------------------------

    def _ordner_art(self) -> str:
        return _text("batch.wahl_ordner")

    def _dateien_art(self) -> str:
        return _text("batch.wahl_dateien")

    def _status(self) -> str:
        return str(self.app.status_label.cget("text"))

    # -- Pruefungen --------------------------------------------------------

    def test_der_knopf_fragt_zuerst_nach_der_art(self) -> None:
        self.art = ""
        self.app._browse_source()
        self.assertEqual(1, len(self.fragen))
        titel, frage, eintraege = self.fragen[0]
        self.assertEqual(_text("dialog.title.choose_source_type"), titel)
        self.assertEqual(_text("dialog.msg.choose_source_type_batch"), frage)
        self.assertEqual([self._ordner_art(), self._dateien_art()], eintraege,
                         "Ordner stehen vorn - der Nutzer wollte sie.")
        self.assertEqual([], self.app._batch_sources, "Abbruch aendert nichts.")
        self.assertEqual("", self.app.source_path.get())
        self.ordner_wahl.assert_not_called()

    def test_mehrere_dump_ordner_in_einem_dialog(self) -> None:
        a, b = _dump(self.basis, "Spiel A"), _dump(self.basis, "Spiel B")
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = [a, b]
        self.app._browse_source()
        self.assertEqual([a, b], self.app._batch_sources)
        self.assertEqual(a, self.app.source_path.get())
        self.assertEqual(_text("main.status_batch_quellen", count=2), self._status())
        self.assertEqual([], self.dialoge)
        # Der Dialog bekam Titel und Startordner - und das Hauptfenster als Besitzer.
        aufruf = self.ordner_wahl.call_args.kwargs
        self.assertEqual(_text("filedialog.choose_batch_dump_folders"), aufruf["titel"])
        self.assertIn("startordner", aufruf)
        self.assertIsInstance(aufruf["besitzer"], int)

    def test_das_protokoll_nennt_die_namen(self) -> None:
        a, b = _dump(self.basis, "Spiel A"), _dump(self.basis, "Spiel B")
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = [a, b]
        self.app._browse_source()
        zeilen = [z for z in self.protokoll if "Sammelkonvertierung" in z]
        self.assertEqual(1, len(zeilen))
        self.assertIn("2 Quelle(n)", zeilen[0])
        self.assertIn("Spiel A, Spiel B", zeilen[0])

    def test_viele_quellen_werden_im_protokoll_gekuerzt(self) -> None:
        dumps = [_dump(self.basis, "Spiel %02d" % n) for n in range(15)]
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = dumps
        self.app._browse_source()
        zeile = next(z for z in self.protokoll if "Sammelkonvertierung" in z)
        self.assertIn("Spiel 00", zeile)
        self.assertIn("Spiel 11", zeile)
        self.assertNotIn("Spiel 12", zeile)
        self.assertIn("und 3 weitere", zeile)
        self.assertEqual(15, len(self.app._batch_sources))

    def test_ein_ordner_voller_dumps_steht_fuer_die_dumps_darin(self) -> None:
        eltern = os.path.join(self.basis, "Game Dumps")
        a, b = _dump(eltern, "Spiel A"), _dump(eltern, "Spiel B")
        Path(eltern, "Abbild.ffpkg").write_bytes(b"x" * 64)
        os.makedirs(os.path.join(eltern, "Medienkram"))              # kein Dump - bleibt draussen
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = [eltern]
        self.app._browse_source()
        # Nach Namen sortiert, Gross- und Kleinschreibung egal (_sammel_ordner_inhalt).
        self.assertEqual([os.path.join(eltern, "Abbild.ffpkg"), a, b], self.app._batch_sources)
        self.assertEqual(eltern, self.app.source_path.get())
        self.assertEqual(_text("main.status_batch_quellen", count=3), self._status())

    def test_dubletten_fallen_heraus(self) -> None:
        eltern = os.path.join(self.basis, "Game Dumps")
        a = _dump(eltern, "Spiel A")
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = [eltern, a, a]        # Eltern, Kind und nochmal das Kind
        self.app._browse_source()
        self.assertEqual([a], self.app._batch_sources)

    def test_der_startordner_des_naechsten_mals_ist_der_uebergeordnete(self) -> None:
        """Dort stehen die Geschwister, die man als Naechstes markieren will."""
        eltern = os.path.join(self.basis, "Game Dumps")
        a = _dump(eltern, "Spiel A")
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = [a]
        self.app._browse_source()
        self.assertEqual(os.path.normpath(eltern), self.app._load_setting("last_source_dir", ""))
        # Und der Dialog beim naechsten Mal beginnt dort.
        self.app._browse_source()
        self.assertEqual(os.path.normpath(eltern), self.ordner_wahl.call_args.kwargs["startordner"])

    def test_abbruch_im_ordnerdialog_aendert_nichts(self) -> None:
        vorher = _dump(self.basis, "Vorher")
        self.app._batch_sources = [vorher]
        self.app.source_path.set(vorher)
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = []
        self.app._browse_source()
        self.assertEqual([vorher], self.app._batch_sources)
        self.assertEqual(vorher, self.app.source_path.get())
        self.assertEqual([], self.dialoge)

    def test_ein_untauglicher_ordner_bricht_die_wahl_mit_einer_meldung_ab(self) -> None:
        gut = _dump(self.basis, "Spiel A")
        leer = os.path.join(self.basis, "Leer")
        os.makedirs(leer)
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = [gut, leer]
        self.app._browse_source()
        self.assertEqual([], self.app._batch_sources, "Eine halbe Auswahl bleibt nicht stehen.")
        self.assertEqual(1, len(self.dialoge))
        art, titel, text = self.dialoge[0][:3]
        self.assertEqual("showerror", art)
        self.assertEqual(_text("dialog.title.invalid_source"), titel)
        self.assertIn(leer, text)

    def test_dateien_wie_bisher(self) -> None:
        d1, d2 = os.path.join(self.basis, "a.ffpkg"), os.path.join(self.basis, "b.exfat")
        Path(d1).write_bytes(b"x")
        Path(d2).write_bytes(b"x")
        self.art = self._dateien_art()
        with mock.patch.object(APP.filedialog, "askopenfilenames", return_value=(d2, d1)) as dialog:
            self.app._browse_source()
        self.assertEqual([d2, d1], self.app._batch_sources, "Die Reihenfolge der Wahl bleibt.")
        self.assertEqual(d2, self.app.source_path.get())
        self.assertEqual(_text("main.status_batch_quellen", count=2), self._status())
        self.assertEqual(_text("filedialog.choose_multiple_sources"), dialog.call_args.kwargs["title"])
        self.ordner_wahl.assert_not_called()

    def test_die_gewaehlte_art_ist_beim_naechsten_mal_vorn(self) -> None:
        self.art = self._dateien_art()
        with mock.patch.object(APP.filedialog, "askopenfilenames", return_value=()):
            self.app._browse_source()
        self.assertEqual("dateien", self.app._load_setting("batch_quellart", ""))
        self.art = ""                       # nur hinsehen, was das Fenster anbietet
        self.app._browse_source()
        self.assertEqual([self._dateien_art(), self._ordner_art()], self.fragen[-1][2])
        self.art = self._ordner_art()
        self.app._browse_source()
        self.assertEqual("ordner", self.app._load_setting("batch_quellart", ""))
        self.art = ""
        self.app._browse_source()
        self.assertEqual([self._ordner_art(), self._dateien_art()], self.fragen[-1][2])

    def test_abbruch_im_dateidialog_aendert_nichts(self) -> None:
        vorher = _dump(self.basis, "Vorher")
        self.app._batch_sources = [vorher]
        self.art = self._dateien_art()
        with mock.patch.object(APP.filedialog, "askopenfilenames", return_value=()):
            self.app._browse_source()
        self.assertEqual([vorher], self.app._batch_sources)

    # -- Rueckfall von Tk (Linux, macOS, oder der Systemdialog geht nicht) ---

    def test_ohne_systemdialog_ein_ordner_je_dialog_mit_nachfrage(self) -> None:
        a, b = _dump(self.basis, "Spiel A"), _dump(self.basis, "Spiel B")
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = None
        gewaehlt = iter([a, b, ""])
        fragen: list = []

        def _noch_einer(titel, text, **optionen):
            fragen.append((titel, text, optionen))
            return len(fragen) < 2          # nach dem ersten Ordner: ja, nach dem zweiten: nein

        with mock.patch.object(APP.filedialog, "askdirectory",
                               side_effect=lambda **k: next(gewaehlt)) as ordnerdialog, \
                mock.patch.object(APP.messagebox, "askyesno", _noch_einer):
            self.app._browse_source()
        self.assertEqual([a, b], self.app._batch_sources)
        self.assertEqual(2, len(fragen))
        self.assertEqual(_text("dialog.title.batch_more_folders"), fragen[0][0])
        self.assertEqual(_text("dialog.msg.batch_more_folders", count=1), fragen[0][1])
        self.assertEqual(_text("dialog.msg.batch_more_folders", count=2), fragen[1][1])
        self.assertEqual(APP.messagebox.NO, fragen[0][2].get("default"),
                         "Ohne Zutun endet die Wahl - keine Endlosschleife.")
        # Der zweite Dialog beginnt im uebergeordneten Ordner: dort stehen die Geschwister.
        self.assertEqual(os.path.normpath(self.basis), ordnerdialog.call_args_list[1].kwargs["initialdir"])

    def test_der_rueckfall_prueft_jeden_ordner_sofort(self) -> None:
        gut = _dump(self.basis, "Spiel A")
        leer = os.path.join(self.basis, "Leer")
        os.makedirs(leer)
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = None
        gewaehlt = iter([leer, gut])
        with mock.patch.object(APP.filedialog, "askdirectory",
                               side_effect=lambda **k: next(gewaehlt)), \
                mock.patch.object(APP.messagebox, "askyesno", return_value=False):
            self.app._browse_source()
        self.assertEqual([gut], self.app._batch_sources, "Der untaugliche Ordner kam nicht hinein.")
        self.assertEqual(1, len([d for d in self.dialoge if d[0] == "showerror"]))

    def test_der_rueckfall_endet_mit_abbrechen(self) -> None:
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = None
        with mock.patch.object(APP.filedialog, "askdirectory", return_value=""), \
                mock.patch.object(APP.messagebox, "askyesno",
                                  side_effect=AssertionError("keine Nachfrage ohne Ordner")) as frage:
            self.app._browse_source()
        frage.assert_not_called()
        self.assertEqual([], self.app._batch_sources)

    def test_der_rueckfall_nimmt_einen_ordner_nicht_doppelt(self) -> None:
        a = _dump(self.basis, "Spiel A")
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = None
        gewaehlt = iter([a, a, ""])
        antworten = iter([True, False])
        with mock.patch.object(APP.filedialog, "askdirectory", side_effect=lambda **k: next(gewaehlt)), \
                mock.patch.object(APP.messagebox, "askyesno", side_effect=lambda *a, **k: next(antworten)):
            self.app._browse_source()
        self.assertEqual([a], self.app._batch_sources)

    def test_der_rueckfall_greift_auch_wenn_der_systemdialog_nichts_kann(self) -> None:
        """``None`` heisst "geht hier nicht" - ``[]`` heisst "abgebrochen", und dann kommt kein zweiter Dialog."""
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = []
        with mock.patch.object(APP.filedialog, "askdirectory",
                               side_effect=AssertionError("kein zweiter Dialog nach Abbruch")) as zweiter:
            self.app._browse_source()
        zweiter.assert_not_called()

    def test_der_besitzer_des_dialogs_ist_das_hauptfenster(self) -> None:
        a = _dump(self.basis, "Spiel A")
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = [a]
        with mock.patch.object(self.app.root, "wm_frame", return_value="0x1f2e"):
            self.app._browse_source()
        self.assertEqual(0x1F2E, self.ordner_wahl.call_args.kwargs["besitzer"])

    def test_ohne_fensterkennung_ist_der_besitzer_null(self) -> None:
        a = _dump(self.basis, "Spiel A")
        self.art = self._ordner_art()
        self.ordner_wahl.return_value = [a]
        with mock.patch.object(self.app.root, "wm_frame", return_value=""):
            self.app._browse_source()
        self.assertEqual(0, self.ordner_wahl.call_args.kwargs["besitzer"])


# ---------------------------------------------------------- Groesse und Platz


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class OrdnergroessenTests(unittest.TestCase):
    """Ordner als Sammelquellen: Groesse, Anzeige und Platzpruefung."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.withdraw()
        for kind in _WURZEL.winfo_children():
            if isinstance(kind, tk.Toplevel):
                kind.withdraw()

    def setUp(self) -> None:
        self.basis = tempfile.mkdtemp(prefix="sammel_groesse_")
        self.addCleanup(shutil.rmtree, self.basis, True)
        self.app._sammel_ordnergroessen = {}
        self.app._batch_sources = []

    @staticmethod
    def _schleife_bis(bedingung, frist: float, stabil: float = 0.8) -> bool:
        """Echte mainloop, bis ``bedingung`` ``stabil`` Sekunden lang ununterbrochen gilt.

        Hintergrundfaeden melden sich nur ueber eine laufende mainloop. Und "stabil": Beim Wechsel
        von Aufgabe und Quelle laufen zwei Messungen kurz nacheinander, jede setzt das Feld erst
        auf "..." und dann auf ihren Wert. Wer beim ersten Treffer aufhoerte, sah im Test mal den
        Wert und mal das "...", je nach Zeitlage - das Ergebnis ist erst nach der zweiten Messung fest.
        """
        ende = time.monotonic() + frist
        seit = {"t": None}

        def _wache() -> None:
            jetzt = time.monotonic()
            if bedingung():
                if seit["t"] is None:
                    seit["t"] = jetzt
                if jetzt - seit["t"] >= stabil:
                    _WURZEL.quit()
                    return
            else:
                seit["t"] = None
            if jetzt >= ende:
                _WURZEL.quit()
                return
            _WURZEL.after(20, _wache)

        _WURZEL.after(20, _wache)
        _WURZEL.mainloop()
        return bool(bedingung()) and seit["t"] is not None

    def _dump_mit_inhalt(self, name: str, groesse: int) -> str:
        ordner = _dump(self.basis, name, mit_eboot=False)
        Path(ordner, "eboot.bin").write_bytes(b"\x7fELF" + bytes(groesse - 4))
        return ordner

    @staticmethod
    def _dateigroesse(ordner: str) -> int:
        return sum(p.stat().st_size for p in Path(ordner).rglob("*") if p.is_file())

    def test_die_summe_zaehlt_dateien_und_ordner(self) -> None:
        a, b = self._dump_mit_inhalt("A", 4000), self._dump_mit_inhalt("B", 9000)
        datei = os.path.join(self.basis, "x.ffpkg")
        Path(datei).write_bytes(b"x" * 500)
        summe, je_ordner = self.app._sammel_groessen_ermitteln([a, datei, b])
        self.assertEqual(self._dateigroesse(a) + self._dateigroesse(b) + 500, summe)
        self.assertEqual({os.path.normcase(os.path.abspath(a)): self._dateigroesse(a),
                          os.path.normcase(os.path.abspath(b)): self._dateigroesse(b)}, je_ordner,
                         "Dateien stehen nicht in der Ordnertabelle.")

    def test_die_platzpruefung_kennt_jeden_ordner(self) -> None:
        """Gemerkt wird sonst nur eine Quelle - bei drei Dumps kennte die Pruefung den letzten."""
        a, b = self._dump_mit_inhalt("A", 4000), self._dump_mit_inhalt("B", 9000)
        _summe, je_ordner = self.app._sammel_groessen_ermitteln([a, b])
        self.app._sammel_ordnergroessen = je_ordner
        self.assertEqual(self._dateigroesse(a), self.app._quellgroesse_ermitteln(a))
        self.assertEqual(self._dateigroesse(b), self.app._quellgroesse_ermitteln(b))
        self.app._batch_sources = [a, b]
        beide = self.app._platzbedarf_schaetzen("batch_convert", a, "ffpfsc")
        self.app._sammel_ordnergroessen = {os.path.normcase(os.path.abspath(a)): self._dateigroesse(a)}
        nur_a = self.app._platzbedarf_schaetzen("batch_convert", a, "ffpfsc")
        self.assertGreater(sum(beide), sum(nur_a), "Der zweite Ordner zaehlte nicht mit.")

    def test_ohne_tabelle_bleibt_alles_wie_bisher(self) -> None:
        a = self._dump_mit_inhalt("A", 4000)
        self.assertEqual(0, self.app._quellgroesse_ermitteln(a),
                         "Unbekannt bleibt 0 - lieber keine Aussage als eine geratene.")

    def test_ein_abbruch_liefert_kein_teilergebnis_das_man_merken_koennte(self) -> None:
        a, b = self._dump_mit_inhalt("A", 4000), self._dump_mit_inhalt("B", 9000)
        aufrufe = {"n": 0}

        def _abbruch() -> bool:
            aufrufe["n"] += 1
            return aufrufe["n"] > 3

        _summe, je_ordner = self.app._sammel_groessen_ermitteln([a, b], abbruch=_abbruch)
        self.assertLess(len(je_ordner), 2)
        self.assertNotIn(os.path.normcase(os.path.abspath(b)), je_ordner)

    def test_die_anzeige_misst_ordner_im_hintergrund(self) -> None:
        """An der laufenden Oberflaeche: Ordner gewaehlt, Groessenfeld nennt Anzahl und Summe."""
        app = self.app
        a, b = self._dump_mit_inhalt("A", 4000), self._dump_mit_inhalt("B", 9000)
        app.current_mode.set("batch_convert")
        _WURZEL.update()
        app._batch_sources = [a, b]
        app.source_path.set(a)
        erwartet = app._t("groesse.sammelquellen", anzahl=2,
                          groesse=app._fmt_bytes(self._dateigroesse(a) + self._dateigroesse(b)))
        # Mit echter mainloop: Der Hintergrundfaden meldet sich ueber root.after zurueck, und
        # Tk nimmt das von einem fremden Faden nur an, solange die Schleife laeuft.
        self.assertTrue(self._schleife_bis(
            lambda: str(app.size_label.cget("text")) == erwartet, 15.0),
            "Groessenfeld: %r statt %r" % (str(app.size_label.cget("text")), erwartet))
        # Die Platzpruefung kennt beide Ordner jetzt aus der Messung.
        self.assertEqual(self._dateigroesse(a), app._quellgroesse_ermitteln(a))
        self.assertEqual(self._dateigroesse(b), app._quellgroesse_ermitteln(b))


# ---------------------------------------------------------------------- Texte


class TexteTests(unittest.TestCase):
    """Die Quellenangabe, die Beschriftung und die neuen Saetze."""

    def test_die_quellenangabe_nennt_dump_ordner(self) -> None:
        self.assertEqual(("folder", "ffpfsc", "exfat", "ffpkg"),
                         APP.PS5ConverterGUI._MODE_SOURCE_TYPES["batch_convert"])
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda k, **w: STRINGS[k]["de"].format(**w)
        gui.target_format = types_namespace_get("")
        gui._format_label_to_key = lambda label: ""
        hinweis = gui._zielformat_hinweis("batch_convert")
        self.assertIn("Dump-Ordner", hinweis)
        self.assertIn(".ffpkg", hinweis)

    def test_der_knopf_heisst_quellen_waehlen(self) -> None:
        self.assertEqual("Quellen wählen", STRINGS["main.browse_files_button"]["de"])
        self.assertEqual("Choose sources", STRINGS["main.browse_files_button"]["en"])

    def test_alle_neuen_texte_sind_zweisprachig(self) -> None:
        for schluessel in ("filedialog.choose_batch_dump_folders", "filedialog.choose_batch_dump_folder",
                           "batch.wahl_ordner", "batch.wahl_dateien",
                           "dialog.msg.choose_source_type_batch", "dialog.title.batch_more_folders",
                           "dialog.msg.batch_more_folders", "batch.log_auswahl",
                           "batch.auswahl_weitere", "main.status_batch_quellen"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel].get(sprache, "").strip())

    def test_die_platzhalter_der_neuen_texte(self) -> None:
        import string
        erwartet = {"dialog.msg.batch_more_folders": {"count"},
                    "batch.log_auswahl": {"count", "namen"},
                    "batch.auswahl_weitere": {"count"},
                    "main.status_batch_quellen": {"count"}}
        for schluessel, felder in erwartet.items():
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    gefunden = {f for _t, f, _s, _c in string.Formatter().parse(
                        STRINGS[schluessel][sprache]) if f}
                    self.assertEqual(felder, gefunden)

    def test_die_beschreibung_und_die_meldung_sagen_dump_ordner(self) -> None:
        self.assertIn("Dump-Ordner", STRINGS["mode_tooltip.batch_convert"]["de"])
        self.assertIn("dump folders", STRINGS["mode_tooltip.batch_convert"]["en"])
        self.assertIn("Dump-Ordner", STRINGS["conversion.choose_sources_first"]["de"])
        self.assertIn("{anzahl} Quellen", STRINGS["groesse.sammelquellen"]["de"])

    def test_jeder_aufruf_im_programm_hat_seinen_text(self) -> None:
        """Was ``_t("batch.…")`` oder ``_t("filedialog.choose_batch…")`` nennt, gibt es."""
        import ast
        baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8"))
        genannt = set()
        for knoten in ast.walk(baum):
            if (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
                    and knoten.func.attr == "_t" and knoten.args
                    and isinstance(knoten.args[0], ast.Constant) and isinstance(knoten.args[0].value, str)
                    and knoten.args[0].value.startswith(("batch.wahl_", "batch.log_auswahl",
                                                          "batch.auswahl_", "filedialog.choose_batch",
                                                          "main.status_batch_", "dialog.msg.batch_",
                                                          "dialog.title.batch_",
                                                          "dialog.msg.choose_source_type_batch"))):
                genannt.add(knoten.args[0].value)
        self.assertGreaterEqual(len(genannt), 8)
        for schluessel in sorted(genannt):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)


def types_namespace_get(wert: str):
    """Ein Stand-in fuer eine Tk-Variable: nur ``get()``."""
    import types
    return types.SimpleNamespace(get=lambda: wert)


if __name__ == "__main__":
    unittest.main(verbosity=2)
