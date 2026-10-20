# -*- coding: utf-8 -*-
""""12. Y2JB Updater" als Seite rechts in der Ansicht KONSOLE (18.10.2026, Nutzerwunsch).

Ins Netz geht kein Test: ``werkzeug_updates.Netz`` ist durch ``FakeNetz`` aus
``test_werkzeug_updates`` ersetzt - die echte Freigaben-Liste wurde von Hand am
laufenden Programm gegen GitHub geprueft (18.10.2026, beide Dateien je Freigabe
gefunden, Pruefsumme der kleinen ``y2jb_update.zip`` byte-genau bestaetigt).

Bewacht wird hier vor allem der Fund vom selben Tag: ``_releases_laden`` rief
``werkzeug_updates.adresse_der_quelle()`` auf, baute daraus schon die fertige
Adresse - und reichte **die** an ``Netz.abfragen()`` weiter, das intern
nochmals ``adresse_der_quelle()`` aufruft (es erwartet die rohe
"Besitzer/Repo"-Kennung). Das Ergebnis war eine doppelt verschachtelte Adresse
und immer 404 - nur am echten GitHub bemerkt, keine Ausnahme, kein Testfehler
(``FakeNetz`` haette dasselbe gezeigt, waere es benutzt worden - seitdem ist es
das).
"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("konsole_y2jb_seite")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import werkzeug_updates as wu      # noqa: E402
from ps5_validator.utils import y2jb_updater as yu          # noqa: E402
from test_werkzeug_updates import FakeNetz                  # noqa: E402

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

KLASSE = APP.PS5ConverterGUI
#: Zwei Freigaben, je mit download0.dat UND y2jb_update.zip - wie am echten Repo (18.10.2026).
_FREIGABEN = [
    ("v1.0.2-254c85f", False, "2026-10-14", ["download0.dat", "y2jb_update.zip"]),
    ("v1.0.1-0866fb4", False, "2026-10-13", ["download0.dat", "y2jb_update.zip"]),
    ("v1.0.0-dev-fb17d16", True, "2026-10-08", ["download0.dat", "y2jb_update.zip"]),
]


def _rollbares_canvas(widget):
    if isinstance(widget, tk.Canvas) and str(widget.cget("yscrollcommand")):
        return widget
    for kind in widget.winfo_children():
        treffer = _rollbares_canvas(kind)
        if treffer is not None:
            return treffer
    return None


def _suchen(widget, art):
    treffer = []
    for kind in widget.winfo_children():
        if isinstance(kind, art):
            treffer.append(kind)
        treffer.extend(_suchen(kind, art))
    return treffer


def _warten(bedingung, grenze: float = 20.0) -> bool:
    """Eine echte Hauptschleife - ``update()`` allein liefert .after()-Rueckrufe aus
    Arbeitsfaeden nicht zuverlaessig aus (siehe test_webkit_seite.py)."""
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if bedingung() or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(20, _takt)

    _WURZEL.after(0, _takt)
    _WURZEL.mainloop()
    # Verbleibende _takt-Rueckrufe aus der Queue abarbeiten, damit ihr
    # quit() nicht die mainloop() des naechsten Tests sofort beendet.
    try:
        _WURZEL.update()
    except Exception:
        pass
    return bool(bedingung())


@unittest.skipUnless(_TK_DA, "ohne Anzeige keine Seite")
class SeiteTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = KLASSE(_WURZEL)
        cls.app._current_language = "de"
        cls.app._ansicht_beschriften()

    def setUp(self) -> None:
        self.app._ansicht_setzen("konsole")
        self.app._konsole_seite_setzen("y2jbupdater")
        _WURZEL.update()
        self.seite = self.app._konsole_y2jb
        self.ordner = tempfile.mkdtemp(prefix="y2jb_seite_")
        self.addCleanup(lambda: APP._rmtree_force(self.ordner, ignore_errors=True))
        self.addCleanup(lambda: self.app._konsole_seite_setzen("uebersicht"))

    def _knopf(self, text: str, index: int = 0):
        treffer = [k for k in _suchen(self.seite, APP.RoundedButton) if str(k.cget("text")) == text]
        return treffer[index]

    def test_die_seite_hat_ein_rollbares_canvas_und_vier_comboboxen(self) -> None:
        self.assertIsNotNone(_rollbares_canvas(self.seite), "Die Seite hat kein rollbares Canvas.")
        # Fassung (download0.dat), Titel-ID, Fassung (y2jb_update.zip), USB-Ziel.
        boxen = _suchen(self.seite, ttk.Combobox)
        self.assertEqual(4, len(boxen))

    def test_knoepfe_elf_und_zwoelf_fuehren_zur_seite_bzw_zum_fenster(self) -> None:
        self.assertIn(("konsole.btn_y2jbupdater", "y2jbupdater"), KLASSE._KONSOLE_KNOEPFE)
        self.assertIn(("konsole.btn_assetpack", "assetpack"), KLASSE._KONSOLE_KNOEPFE)
        self.assertEqual("_show_asset_pack_werkzeug", KLASSE._KONSOLE_FENSTER.get("assetpack"))
        self.assertEqual("_konsole_y2jb_zeigen", KLASSE._KONSOLE_SEITEN.get("y2jbupdater"))

    def test_fassungen_laden_befuellt_beide_listen_ueber_dieselbe_abfrage(self) -> None:
        """Regressionstest: adresse_der_quelle() darf hier nicht zweimal angewandt werden."""
        netz = FakeNetz(releases={yu.QUELLE: _FREIGABEN})
        with mock.patch.object(wu, "Netz", lambda: netz), \
                mock.patch.object(self.app, "_updates_payload_ordner", return_value=self.ordner):
            laden_knopf = self._knopf("Fassungen laden")
            laden_knopf._command()
            self.assertTrue(_warten(lambda: str(laden_knopf.cget("state")) == "normal"),
                            "Der Knopf blieb gesperrt - der Hintergrundfaden ist nie fertig geworden.")
        self.assertEqual([(yu.QUELLE, "")], netz.gefragt, "Netz.abfragen() bekam nicht die rohe Quelle.")
        # Alle 3 Freigaben haben beide Dateien, Vorabfassungen zaehlen mit (y2jb_updater.angebote laesst
        # nur Entwuerfe heraus) - also 3 Eintraege in beiden Fassungslisten.
        boxen = _suchen(self.seite, ttk.Combobox)
        fassungs_boxen = [b for b in boxen if str(b.cget("state")) == "readonly" and len(b.cget("values")) == 3]
        self.assertEqual(2, len(fassungs_boxen), "Beide Fassungslisten (download0.dat, y2jb_update.zip) "
                                                  "sollten 3 Eintraege haben.")

    def test_herunterladen_legt_die_echte_datei_mit_passender_pruefsumme_ab(self) -> None:
        netz = FakeNetz(releases={yu.QUELLE: _FREIGABEN})
        with mock.patch.object(wu, "Netz", lambda: netz), \
                mock.patch.object(self.app, "_updates_payload_ordner", return_value=self.ordner), \
                mock.patch.object(self.app, "_get_runtime_temp_dir", return_value=self.ordner):
            laden_knopf = self._knopf("Fassungen laden")
            laden_knopf._command()
            self.assertTrue(_warten(lambda: str(laden_knopf.cget("state")) == "normal"))

            dl_knopf = self._knopf("Herunterladen", 0)         # Karte 1: download0.dat
            dl_knopf._command()
            self.assertTrue(_warten(lambda: str(dl_knopf.cget("state")) == "normal"))
            # Regressionstest (19.10.2026): Der Download-Hintergrundfaden rief am Ende
            # ``release_laden_knopf.configure({"state": "normal"})`` auf - ein Diktat als
            # erstes Argument statt eines Schluesselworts. RoundedButton.configure() nimmt
            # aber nur Schluesselworte, nicht einen einzelnen positionsgebundenen Diktat-Wert
            # (anders als ttk-Widgets). Das flog nur als unbehandelte Ausnahme im Tk-Ereignis
            # auf - "Fassungen laden" blieb gesperrt, ohne dass ein Test das bisher bemerkte.
            self.assertTrue(_warten(lambda: str(laden_knopf.cget("state")) == "normal"),
                            "„Fassungen laden“ blieb nach dem Download gesperrt.")

        eintraege = [p for p in Path(self.ordner).rglob("download0_*.dat")]
        self.assertEqual(1, len(eintraege), "Es sollte genau eine heruntergeladene download0.dat liegen.")
        self.assertTrue(eintraege[0].stat().st_size > 0)

    def test_update_zip_herunterladen_nutzt_den_anderen_anhang(self) -> None:
        netz = FakeNetz(releases={yu.QUELLE: _FREIGABEN})
        with mock.patch.object(wu, "Netz", lambda: netz), \
                mock.patch.object(self.app, "_updates_payload_ordner", return_value=self.ordner), \
                mock.patch.object(self.app, "_get_runtime_temp_dir", return_value=self.ordner):
            laden_knopf = self._knopf("Fassungen laden")
            laden_knopf._command()
            self.assertTrue(_warten(lambda: str(laden_knopf.cget("state")) == "normal"))

            dl_knopf = self._knopf("Herunterladen", 1)         # Karte 3: y2jb_update.zip
            dl_knopf._command()
            self.assertTrue(_warten(lambda: str(dl_knopf.cget("state")) == "normal"))

        eintraege = [p for p in Path(self.ordner).rglob("y2jb_update_*.zip")]
        self.assertEqual(1, len(eintraege), "Es sollte genau eine heruntergeladene y2jb_update.zip liegen.")


if __name__ == "__main__":
    unittest.main()
