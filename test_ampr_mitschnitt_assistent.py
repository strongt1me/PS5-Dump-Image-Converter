# -*- coding: utf-8 -*-
"""Der AMPR-Mitschnitt-Assistent: Packprofil aus echten Konsolen-Laeufen.

Ueberwiegend Quelltextpruefungen, wie test_ampr_generation.py fuer den
aelteren Automatiklauf - keine echte FTP-Verbindung. Anders als dort
verteilt sich die Automatik hier auf mehrere ``_ampr_mitschnitt_*``-Methoden
statt einer einzigen; die Pruefungen scannen deshalb ueber alle diese
Methodenruempfe hinweg, nicht nur ueber einen.

``EchterAufbauTests`` baut das Fenster zusaetzlich **wirklich** auf (echte
PS5ConverterGUI-Instanz, echte Tk-Widgets, Vorbild UmschalterTests in
test_fensterlayout.py) - eine reine Quelltextpruefung haette einen falschen
i18n-Schluessel oder eine falsche Tk-Option nicht gefunden, wie es hier beim
ersten Anlauf tatsaechlich passiert ist (siehe Arbeitsstand).

Fuer ``konsole_ftp.datei_holen`` (den fehlenden Baustein fuer den Download
einzelner Dateien) gibt es eigene Tests in test_konsole_stufe3.py, gegen die
dortige echte FTP-Stube.
"""
from __future__ import annotations

import re
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils.i18n import STRINGS
from ps5_validator.utils import ampr_assetpakete as ap

QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
    encoding="utf-8")

try:
    import tkinter as tk
    # Vorhandene Wurzel weiterbenutzen (Grund siehe test_fensterlayout.py:
    # eine zweite tk.Tk() sieht die Bilder der ersten nicht).
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:                                        # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    pfad = str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
    spec = importlib.util.spec_from_file_location("hauptprogramm", pfad)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul

#: Alle neuen Methoden des Assistenten, in der Reihenfolge, in der die
#: Automatik sie aufruft.
_METHODEN = (
    "_show_ampr_mitschnitt_assistent",
    "_ampr_mitschnitt_automatik",
    "_ampr_mitschnitt_ordner_fragen",
    "_ampr_mitschnitt_titel_aus_ordner",
    "_ampr_mitschnitt_spiel_zuordnen",
    "_ampr_mitschnitt_index_bauen",
    "_ampr_mitschnitt_debug_bibliothek_waehlen",
    "_ampr_mitschnitt_upload_vorbereiten",
    "_ampr_mitschnitt_segment_warten",
    "_ampr_mitschnitt_lauf_herunterladen",
    "_ampr_mitschnitt_profil_erzeugen",
)


def _rumpf(name: str) -> str:
    """Der Quelltext einer Methode - von ihrer ``def``-Zeile bis zur naechsten."""
    anfang = QUELLE.index("    def %s(" % name)
    kandidaten = [i for i in (
        QUELLE.find("\n    def ", anfang + 10),
        QUELLE.find("\n    # ==", anfang + 10),
    ) if i != -1]
    ende = min(kandidaten)
    return QUELLE[anfang:ende]


def _ohne_docstring(rumpf: str) -> str:
    """Entfernt den fuehrenden Dreifach-Anfuehrungszeichen-Block.

    Fuer Pruefungen, die tatsaechlichen Code treffen sollen, nicht Prosa,
    die einen Begriff (z. B. "grab_set()") nur erklaerend nennt.
    """
    treffer = re.search(r'""".*?"""', rumpf, re.S)
    return rumpf[treffer.end():] if treffer else rumpf


class WerkzeugAnbindungTests(unittest.TestCase):
    """Die Ergaenzungen in ampr_assetpakete.py - Voraussetzung fuer das Fenster."""

    def test_profil_werkzeug_konstanten_da(self) -> None:
        self.assertEqual("ampr_pack_profile.py", ap.PACKPROFIL_WERKZEUG)
        self.assertEqual("--ampr-pack-profil", ap.PACKPROFIL_SELBSTAUFRUF)
        self.assertNotEqual(ap.PACKPROFIL_SELBSTAUFRUF, ap.SELBSTAUFRUF,
                            "Sonst faengt der falsche Zweig im __main__-Block ab.")

    def test_werkzeug_finden_nimmt_einen_namen(self) -> None:
        """Alte Aufrufer (ampr_pack.py) muessen ohne Angabe weiterlaufen."""
        pfad_alt = ap.werkzeug_finden()
        pfad_neu = ap.werkzeug_finden(ap.PACKPROFIL_WERKZEUG)
        self.assertTrue(pfad_alt.endswith("ampr_pack.py"))
        self.assertTrue(pfad_neu.endswith("ampr_pack_profile.py"))

    def test_profil_generieren_baut_die_richtigen_argumente(self) -> None:
        """Ohne echten Lauf: leere Traces muessen sofort abgelehnt werden."""
        with self.assertRaises(ap.PackFehler):
            ap.profil_generieren([], "irgendwo.toml")

    def test_frozen_exe_dispatch_ist_verdrahtet(self) -> None:
        self.assertIn("def _run_ampr_pack_profil_subcommand(argv", QUELLE)
        self.assertIn("ampr_assetpakete.PACKPROFIL_SELBSTAUFRUF", QUELLE)
        # Beide Selbstaufrufe muessen im __main__-Block VOR der
        # Rechtepruefung stehen - siehe _run_ps4_subcommand als Vorbild.
        haupt_start = QUELLE.index("if __name__ ==")
        ausschnitt = QUELLE[haupt_start:haupt_start + 4000]
        self.assertIn("ampr_assetpakete.SELBSTAUFRUF", ausschnitt)
        self.assertIn("ampr_assetpakete.PACKPROFIL_SELBSTAUFRUF", ausschnitt)


class EinstiegspunktTests(unittest.TestCase):
    """Der Menueeintrag und seine Beschriftung."""

    def test_eintrag_in_weitere_tools(self) -> None:
        anfang = QUELLE.index("_MORE_TOOLS_ENTRIES: tuple")
        block = QUELLE[anfang:QUELLE.index(")\n", anfang)]
        self.assertIn('("titlebar.ampr_mitschnitt", "_show_ampr_mitschnitt_assistent")',
                      block)

    def test_beschriftung_ist_zweisprachig(self) -> None:
        self.assertIn("titlebar.ampr_mitschnitt", STRINGS)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertTrue(STRINGS["titlebar.ampr_mitschnitt"][sprache])


class AutomatikTests(unittest.TestCase):
    """Das Fenster arbeitet von selbst - Vorbild _show_ampr_generation."""

    def test_der_lauf_startet_beim_oeffnen(self) -> None:
        self.assertIn("self._spaeter_im_fenster(win, _starten)",
                      _rumpf("_show_ampr_mitschnitt_assistent"))

    def test_der_lauf_geht_in_einen_eigenen_faden(self) -> None:
        fenster = _rumpf("_show_ampr_mitschnitt_assistent")
        self.assertIn('threading.Thread(target=_lauf, daemon=True,', fenster)

    def test_schliessen_fragt_nach_solange_der_lauf_aktiv_ist(self) -> None:
        """Kein hartes destroy() waehrend die Automatik noch laeuft."""
        fenster = _rumpf("_show_ampr_mitschnitt_assistent")
        self.assertIn('win.protocol("WM_DELETE_WINDOW", _schliessen_versuchen)',
                      fenster)
        self.assertIn("if not laeuft[\"aktiv\"]:", fenster)
        self.assertIn("_ask_yesno_threadsafe", fenster)

    def test_die_wartephase_hat_kein_grab_set(self) -> None:
        """Kernstueck des Plans: kein Toplevel, kein grab_set()-AUFRUF beim Warten.

        Ein grab_set() wie in _ampr_gen_dialog wuerde das ganze Programm
        sperren, waehrend der Nutzer moeglicherweise Stunden spielt. Geprueft
        wird der tatsaechliche Aufruf (".grab_set(", "= tk.Toplevel(") - die
        Methode nennt beide Begriffe zu Recht in ihrem eigenen Docstring, um
        genau diesen Unterschied zu erklaeren.
        """
        rumpf = _ohne_docstring(_rumpf("_ampr_mitschnitt_segment_warten"))
        self.assertNotIn(".grab_set(", rumpf)
        self.assertNotIn("tk.Toplevel(", rumpf)

    def test_alle_schluessel_stehen_in_strings_und_im_code(self) -> None:
        gefunden = set(re.findall(r'"(amprmitschnitt\.[a-z_]+)"', QUELLE))
        self.assertTrue(gefunden, "Kein einziger amprmitschnitt.*-Schluessel gefunden.")
        for schluessel in sorted(gefunden):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertIn("de", STRINGS[schluessel])
                self.assertIn("en", STRINGS[schluessel])

    def test_jede_erklaerte_frage_hat_einen_pruefbaren_ausgang(self) -> None:
        """Keine _ampr_gen_frage, deren Ergebnis ungeprueft durchlaeuft.

        Anders als bei der ShadowMount+-Automatik (eine einzige Funktion)
        verteilen sich die Fragen hier auf mehrere Methoden - jede wird
        einzeln gescannt.
        """
        traf_mindestens_eine = False
        for name in _METHODEN:
            rumpf = _rumpf(name)
            for treffer in re.finditer(r"self\._ampr_gen_frage\(", rumpf):
                traf_mindestens_eine = True
                danach = rumpf[treffer.start():treffer.start() + 900]
                with self.subTest(methode=name, versatz=treffer.start()):
                    self.assertIn("return", danach,
                                  "Nach dieser Frage fehlt ein Ausgang.")
        self.assertTrue(traf_mindestens_eine, "Keine einzige _ampr_gen_frage gefunden.")

    def test_index_geht_in_die_spielwurzel_nicht_nach_fakelib(self) -> None:
        """Regressionsschutz: der Index gehoert NICHT in den fakelib-Ordner.

        shadowmount_generation.ORT_SPIEL: standardpfad="<Spielordner>/" -
        der Debug-Bau schreibt/liest /app0/ampr_emu.index, nicht
        /app0/<fakelib>/ampr_emu.index.
        """
        rumpf = _rumpf("_ampr_mitschnitt_upload_vorbereiten")
        self.assertIn("_ampr_ftp_upload_file(ftp, spielpfad, index_lokal", rumpf)
        self.assertNotIn("_ampr_ftp_upload_file(ftp, ziel_fakelib, index_lokal", rumpf)

    def test_debug_bibliothek_ist_ein_exakter_filter(self) -> None:
        """Keine "neueste Version" ohne Ruecksicht auf die Variante.

        _ampr_gen_auswahl_bibliotheken waere hier falsch: die waehlt nur
        die neueste je Bibliothek, egal ob Release oder Debug-Bau.
        """
        rumpf = _rumpf("_ampr_mitschnitt_debug_bibliothek_waehlen")
        self.assertIn("_AMPR_VARIANT_ORDER.get(", rumpf)
        self.assertNotIn("_ampr_gen_auswahl_bibliotheken", rumpf)

    def test_segmente_sind_fuenf_und_haben_je_einen_text(self) -> None:
        anfang = QUELLE.index("_AMPR_MITSCHNITT_SEGMENTE: tuple")
        block = QUELLE[anfang:QUELLE.index(")\n", anfang)]
        schluessel = re.findall(r'"(amprmitschnitt\.segment_\d)"', block)
        self.assertEqual(5, len(schluessel))
        for s in schluessel:
            with self.subTest(schluessel=s):
                self.assertIn(s, STRINGS)

    def test_wartegrenze_ist_grosszuegiger_als_bei_sekunden_entscheidungen(self) -> None:
        treffer = re.search(
            r"_AMPR_MITSCHNITT_SPIELZEIT_GRENZE = ([\d.]+)\s*\*\s*([\d.]+)", QUELLE)
        self.assertIsNotNone(treffer, "Konstante nicht im erwarteten Format gefunden.")
        wert = float(treffer.group(1)) * float(treffer.group(2))
        # _AMPR_GEN_ANTWORT_GRENZE (600 s) ist fuer Sekunden-Entscheidungen
        # gedacht - "jetzt spielen" braucht eine ganz andere Groessenordnung.
        self.assertGreater(wert, 600.0)


@unittest.skipUnless(_TK_DA, "keine Anzeige verfuegbar")
class EchterAufbauTests(unittest.TestCase):
    """Baut das Fenster wirklich auf - keine reine Quelltextpruefung.

    Vorbild: UmschalterTests in test_fensterlayout.py. Filedialog und
    Meldungsfenster werden abgeklemmt, damit kein echter Dialog aufgeht; die
    PS5-Suche selbst laeuft echt und findet auf diesem Rechner ohne Konsole
    nichts - genau der Abbruchpfad, der hier gemessen wird. Eine reine
    Quelltextpruefung wuerde weder einen falschen i18n-Schluessel noch eine
    ungueltige Tk-Option bemerken, die erst beim echten Aufbau als Ausnahme
    im Arbeitsfaden auftreten.
    """

    @classmethod
    def setUpClass(cls):
        cls.modul = _lade_hauptprogramm()
        for name in ("askopenfilename", "askdirectory", "asksaveasfilename"):
            setattr(cls.modul.filedialog, name, lambda *a, **k: "")
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(cls.modul.messagebox, name, lambda *a, **k: None)
        setattr(cls.modul.messagebox, "askyesno", lambda *a, **k: False)
        cls.app = cls.modul.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self):
        self.app._werkzeugfenster.clear()
        self._geoeffnet: list = []

    def tearDown(self):
        for fenster in self._geoeffnet:
            try:
                if fenster.winfo_exists():
                    fenster.destroy()
            except tk.TclError:
                pass
        _WURZEL.update()
        self.app._werkzeugfenster.clear()

    def _fenster_oeffnen(self, name: str):
        vorher = set(_WURZEL.winfo_children())
        getattr(self.app, name)()
        _WURZEL.update()
        neu = [w for w in _WURZEL.winfo_children() if w not in vorher]
        self.assertTrue(neu, "%s hat kein Fenster geoeffnet" % name)
        fenster = neu[-1]
        self._geoeffnet.append(fenster)
        return fenster

    @staticmethod
    def _text_inhalte(widget) -> list:
        gefunden: list = []

        def _durch(w) -> None:
            if isinstance(w, tk.Text):
                try:
                    gefunden.append(w.get("1.0", "end"))
                except tk.TclError:
                    pass
            for kind in w.winfo_children():
                _durch(kind)
        _durch(widget)
        return gefunden

    def test_fenster_baut_sich_echt_auf_und_bricht_sauber_ab(self) -> None:
        """Ohne Konsole und ohne gewaehlten Ordner: sauberer, sichtbarer Abbruch.

        **Braucht eine echte laufende ``mainloop()``, kein blosses
        wiederholtes ``update()``**: Tkinter lehnt einen Aufruf aus einem
        Arbeitsfaden (``winfo_exists()``, ``after()`` - genau das, was
        ``_spaeter_im_fenster`` fuer jede Protokollzeile benutzt) mit
        ``RuntimeError: main thread is not in main loop`` ab, wenn der
        Hauptfaden nicht *waehrenddessen* wirklich in ``mainloop()`` steckt -
        ein reines ``update()`` in einer Schleife zaehlt dafuer nicht
        (direkt gemessen: ohne echte ``mainloop()`` blieb das Protokoll bei
        "Lauf gestartet." stehen, ohne jede Fehlermeldung, weil
        ``_spaeter_im_fenster`` genau diese Ausnahme abfaengt und nur
        ``logger.debug`` schreibt). Deshalb hier eine Wache
        (``root.after``-Selbstaufruf), die ``_WURZEL.quit()`` ruft, sobald
        der Arbeitsfaden fertig ist oder eine Notbremse greift - waehrend
        ``mainloop()`` selbst laeuft.

        Eine Ausnahme im Arbeitsfaden wird zusaetzlich direkt am Faden
        abgefangen - im echten Programm landete sie nur im Fehlerbericht,
        nicht im Protokoll, und liesse den Text unten sonst einfach nur
        fehlen, ohne zu sagen, warum.
        """
        fehler: list = []
        fertig = threading.Event()
        echte_automatik = self.app._ampr_mitschnitt_automatik

        def _bewacht(*a, **k):
            try:
                echte_automatik(*a, **k)
            except Exception as exc:                        # noqa: BLE001
                fehler.append(exc)
            finally:
                fertig.set()

        def _wache() -> None:
            if fertig.is_set():
                _WURZEL.quit()
                return
            _WURZEL.after(20, _wache)

        with mock.patch.object(self.app, "_ampr_mitschnitt_automatik", _bewacht):
            fenster = self._fenster_oeffnen("_show_ampr_mitschnitt_assistent")
            self.assertTrue(fenster.winfo_exists())

            _WURZEL.after(20, _wache)
            notbremse = _WURZEL.after(8000, _WURZEL.quit)
            _WURZEL.mainloop()
            try:
                _WURZEL.after_cancel(notbremse)
            except tk.TclError:
                pass

        self.assertTrue(fertig.is_set(), "Der Arbeitsfaden endete nicht innerhalb von 8 s.")
        self.assertEqual([], [str(e) for e in fehler],
                         "Ausnahme im Arbeitsfaden des Assistenten.")
        erwartet = self.app._t("amprmitschnitt.no_dump_chosen")
        gefunden = any(erwartet in text for text in self._text_inhalte(fenster))
        self.assertTrue(gefunden,
                        "Der Abbruchtext fehlt im Protokoll:\n"
                        + "\n".join(self._text_inhalte(fenster)))


if __name__ == "__main__":
    unittest.main()
