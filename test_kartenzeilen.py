# -*- coding: utf-8 -*-
"""Tests gegen eine unaufgeraeumte Pfad-Karte.

Am 21.08.2026 gemessener Ausgangszustand des Bereichs unter ZIELFORMAT:

* Die fuenf Elemente der Einbauzeile standen ueber **sechs Pixel** verteilt
  (y=218 bis y=224), weil jedes mit ``rely=0.5`` am *vorherigen* hing. Sind
  die Nachbarn unterschiedlich hoch - Kaestchen 25 px, Klappliste 34 px -,
  rundet Tk bei jedem Schritt um einen halben Pixel, und der Fehler summiert
  sich ueber die Kette.
* Die Abstaende in derselben Zeile waren 5, 8, 15 und 5 px.
* Ueber drei Bedienelementen stand **eine** 387 px breite Ueberschrift
  ("KOMPRESSION (PFS) / WORKER-THREADS / PRUEFUNG") - man sah nicht, welches
  Wort zu welchem Kasten gehoert.
* Der Hinweistext darunter begann bei y=250, die Kaestchen endeten bei y=249.

Die Messungen brauchen einen laufenden Tk-Baum; ohne Anzeige entfallen sie.
Die Quelltextpruefungen laufen immer.
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    tk = None


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class QuelltextTests(unittest.TestCase):
    """Was sich ohne Anzeige pruefen laesst."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as datei:
            cls.quelltext = datei.read()

    def test_ausrichter_haengt_alles_am_ersten_element(self):
        """Kein ``in_=`` auf den jeweiligen Vorgaenger mehr.

        Genau diese Kette war die Ursache der Sechs-Pixel-Treppe.
        """
        for vorgaenger in ("in_=self.worker_knob",
                           "in_=self.ampr_version_combo",
                           "in_=self.ampr_playgo_check"):
            self.assertNotIn(
                vorgaenger, self.quelltext,
                "%s haengt wieder am Vorgaenger - die Rundungsfehler "
                "summieren sich dann erneut." % vorgaenger)

    def test_abstaende_kommen_aus_konstanten(self):
        for name in ("_ZEILE_ABSTAND_ENG", "_ZEILE_ABSTAND_GRUPPE",
                     "_ZEILE_ABSTAND_BESCHRIFTUNG"):
            self.assertIn(name + " = ", self.quelltext)

    def test_nach_dem_aufbau_wird_ausgerichtet(self):
        self.assertIn("self.root.after_idle(self._kartenzeilen_ordnen)",
                      self.quelltext)

    def test_sprachwechsel_richtet_neu_aus(self):
        """Die Textbreiten aendern sich mit der Sprache, die Abstaende auch."""
        anfang = self.quelltext.index("def _apply_language")
        ende = self.quelltext.index("def _get_config_path")
        self.assertIn("_kartenzeilen_ordnen", self.quelltext[anfang:ende])

    def test_wache_zieht_spaetere_breitenaenderungen_nach(self):
        """Das Zahlenfeld wird nach dem ersten Ausrichten noch schmaler."""
        self.assertIn("def _kartenzeilen_ueberwachen", self.quelltext)
        self.assertIn("def _kartenzeilen_nachziehen", self.quelltext)
        rumpf = self.quelltext[self.quelltext.index("def _kartenzeilen_nachziehen"):]
        rumpf = rumpf[:rumpf.index("\n    def ", 10)]
        self.assertIn("_zeilen_ordnen_laeuft", rumpf,
                      "Ohne Sperre richtet sich die Wache selbst wieder aus.")
        self.assertIn("after_cancel", rumpf,
                      "Ohne Abbruch des alten Auftrags laufen mehrere "
                      "Ausrichtungen uebereinander.")

    def test_jedes_bedienelement_hat_seine_eigene_beschriftung(self):
        self.assertNotIn("main.compression_worker_label", self.quelltext,
                         "Die gemeinsame Ueberschrift ueber drei Kaesten "
                         "ist wieder da.")
        for schluessel in ("main.compression_label", "main.worker_label",
                           "main.verify_label"):
            self.assertIn(schluessel, self.quelltext)

    def test_die_drei_beschriftungen_sind_uebersetzt(self):
        from ps5_validator.utils import i18n
        for schluessel in ("main.compression_label", "main.worker_label",
                           "main.verify_label"):
            eintrag = i18n.STRINGS.get(schluessel)
            self.assertIsNotNone(eintrag, "%s fehlt" % schluessel)
            for sprache in i18n.SUPPORTED_LANGUAGES:
                self.assertTrue(eintrag.get(sprache),
                                "%s fehlt auf %s" % (schluessel, sprache))

    def test_hinweistext_hat_luft_nach_oben(self):
        stelle = self.quelltext.index("self.format_info_label.grid(")
        zeile = self.quelltext[stelle:stelle + 250]
        self.assertNotIn("pady=(0,", zeile,
                         "Der Hinweis klebt wieder an den Kaestchen darueber.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class KartenzeilenTests(unittest.TestCase):
    """Misst die fertige Karte aus."""

    @classmethod
    def setUpClass(cls):
        # Eine vorhandene Wurzel mitbenutzen. Laeuft dieser Test gemeinsam
        # mit einem anderen, der beim Import schon ein ``tk.Tk()`` anlegt
        # (test_fensterlayout.py tut das), haengen dessen PhotoImage-Objekte
        # an der ersten Wurzel - eine zweite sieht sie nicht und der Aufbau
        # bricht mit ``image "pyimageNNN" doesn't exist`` ab.
        cls._eigene_wurzel = tk._default_root is None
        cls.wurzel = tk._default_root or tk.Tk()
        cls.wurzel.withdraw()
        haupt = _lade_hauptprogramm()
        cls.haupt = haupt
        for name in ("askopenfilename", "askdirectory", "asksaveasfilename"):
            setattr(haupt.filedialog, name, lambda *a, **k: "")
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(haupt.messagebox, name, lambda *a, **k: None)
        haupt.messagebox.askyesno = lambda *a, **k: False
        cls.app = haupt.PS5ConverterGUI(cls.wurzel)
        # Nichts aus dem Netz holen.
        cls.app._online_nachschlag_erlaubt = lambda: False
        cls._beruhigen(cls.wurzel)

    @classmethod
    def tearDownClass(cls):
        if not cls._eigene_wurzel:
            return
        try:
            cls.wurzel.destroy()
        except Exception:
            pass

    @staticmethod
    def _beruhigen(wurzel, sekunden=1.5):
        """Laesst die verzoegerten Auftraege der Oberflaeche auslaufen."""
        import time
        ende = time.perf_counter() + sekunden
        while time.perf_counter() < ende:
            wurzel.update()
            time.sleep(0.01)

    def _zeilen(self):
        eng = self.haupt.PS5ConverterGUI._ZEILE_ABSTAND_ENG
        gruppe = self.haupt.PS5ConverterGUI._ZEILE_ABSTAND_GRUPPE
        return (
            ("Pruefzeile", [("compression_combo", None),
                            ("worker_knob", gruppe),
                            ("verify_combo", gruppe)]),
            ("Einbauzeile", [("ampr_integrate_check", None),
                             ("ampr_version_combo", eng),
                             ("ampr_playgo_check", eng),
                             ("backport_integrate_check", gruppe),
                             ("backport_fw_combo", eng)]),
        )

    def test_die_abstaende_stimmen_genau(self):
        for name, kette in self._zeilen():
            with self.subTest(zeile=name):
                rechts_vorher = None
                for attribut, soll in kette:
                    widget = getattr(self.app, attribut)
                    links = widget.winfo_rootx()
                    if soll is not None:
                        self.assertEqual(
                            links - rechts_vorher, soll,
                            "%s/%s: Abstand %d statt %d px"
                            % (name, attribut, links - rechts_vorher, soll))
                    rechts_vorher = links + widget.winfo_width()

    def test_jede_zeile_steht_auf_einer_linie(self):
        """Gleich hohe Elemente muessen dieselbe Oberkante haben.

        Unterschiedlich hohe koennen es bauartbedingt nicht - ein 25 px
        hohes Kaestchen und eine 34 px hohe Klappliste haben bei gleicher
        Mitte verschiedene Oberkanten. Geprueft wird deshalb die Mitte, und
        zwar auf ein Pixel genau.
        """
        for name, kette in self._zeilen():
            with self.subTest(zeile=name):
                mitten = []
                for attribut, _soll in kette:
                    widget = getattr(self.app, attribut)
                    mitten.append((attribut,
                                   widget.winfo_rooty()
                                   + widget.winfo_height() / 2.0))
                bezug = mitten[0][1]
                for attribut, mitte in mitten[1:]:
                    self.assertLessEqual(
                        abs(mitte - bezug), 1.0,
                        "%s/%s sitzt %.1f px neben der Zeilenmitte - "
                        "genau so entstand die Sechs-Pixel-Treppe."
                        % (name, attribut, abs(mitte - bezug)))

    def test_jede_beschriftung_steht_ueber_ihrem_bedienelement(self):
        for beschriftung, bedienelement in (("perf_title", "compression_combo"),
                                            ("worker_title", "worker_knob"),
                                            ("verify_title", "verify_combo")):
            with self.subTest(beschriftung=beschriftung):
                oben = getattr(self.app, beschriftung)
                unten = getattr(self.app, bedienelement)
                self.assertEqual(
                    oben.winfo_rootx(), unten.winfo_rootx(),
                    "%s ist gegen %s verschoben" % (beschriftung, bedienelement))
                abstand = unten.winfo_rooty() - (oben.winfo_rooty()
                                                 + oben.winfo_height())
                self.assertGreaterEqual(abstand, 0,
                                        "%s ueberlappt sein Bedienelement"
                                        % beschriftung)
                self.assertLessEqual(abstand, 12,
                                     "%s schwebt %d px ueber seinem "
                                     "Bedienelement" % (beschriftung, abstand))

    def test_die_beschriftungen_ueberlappen_einander_nicht(self):
        folge = ("perf_title", "worker_title", "verify_title")
        for links_name, rechts_name in zip(folge, folge[1:]):
            links = getattr(self.app, links_name)
            rechts = getattr(self.app, rechts_name)
            self.assertLessEqual(
                links.winfo_rootx() + links.winfo_width(),
                rechts.winfo_rootx(),
                "%s laeuft in %s hinein" % (links_name, rechts_name))

    def test_hinweistext_klebt_nicht_an_den_kaestchen(self):
        kaestchen = self.app.ampr_integrate_check
        hinweis = self.app.format_info_label
        abstand = hinweis.winfo_rooty() - (kaestchen.winfo_rooty()
                                           + kaestchen.winfo_height())
        self.assertGreaterEqual(
            abstand, 8,
            "Nur %d px zwischen den Kaestchen und dem Hinweis darunter "
            "(gemessener Ausgangszustand: 1 px)." % abstand)

    def test_beide_zeilen_passen_bei_mindestbreite(self):
        """Bei ``WINDOW_MIN_WIDTH`` darf nichts ueber die Karte hinausragen.

        Geprueft wird beides: hoch (Bildlaufleiste aus) und auf
        ``WINDOW_MIN_HEIGHT`` (Leiste an). Die Leiste nimmt 15 px von der
        Karte - genau daran scheiterte v1.8.73 um einen Pixel, weil die
        Reserve nur fuer den Fall ohne Leiste gerechnet war.
        """
        self.wurzel.deiconify()
        try:
            self.wurzel.state("normal")
        except Exception:
            pass
        try:
            for hoehe in (1050, self.haupt.WINDOW_MIN_HEIGHT):
                self.wurzel.geometry("%dx%d"
                                     % (self.haupt.WINDOW_MIN_WIDTH, hoehe))
                self._beruhigen(self.wurzel, 1.2)
                karte = self.app.path_card
                breite = karte.winfo_width()
                leiste = getattr(self.app, "content_scrollbar", None)
                an = bool(leiste.winfo_ismapped()) if leiste is not None else False
                for name, kette in self._zeilen():
                    letztes = getattr(self.app, kette[-1][0])
                    ende = (letztes.winfo_rootx() - karte.winfo_rootx()
                            + letztes.winfo_width())
                    with self.subTest(hoehe=hoehe, zeile=name):
                        self.assertGreater(breite, 100, "Karte nicht vermessbar")
                        self.assertLessEqual(
                            ende, breite,
                            "%s braucht %d px, die Karte ist bei Mindestbreite "
                            "und Fensterhoehe %d nur %d px breit "
                            "(Bildlaufleiste %s)."
                            % (name, ende, hoehe, breite,
                               "sichtbar" if an else "aus"))
        finally:
            self.wurzel.withdraw()

    def test_die_mindestbreite_rechnet_die_bildlaufleiste_mit(self):
        """Die Leiste ist bei ``WINDOW_MIN_HEIGHT`` immer da.

        Sie nimmt 15 px. Wird die Mindestbreite wieder auf einen Wert
        gesetzt, der nur ohne Leiste aufgeht, faellt das hier auf, bevor es
        jemand am schmalen Fenster bemerkt.
        """
        self.wurzel.deiconify()
        try:
            self.wurzel.state("normal")
        except Exception:
            pass
        try:
            self.wurzel.geometry("%dx%d" % (self.haupt.WINDOW_MIN_WIDTH,
                                            self.haupt.WINDOW_MIN_HEIGHT))
            self._beruhigen(self.wurzel, 1.2)
            karte = self.app.path_card
            verify = self.app.verify_combo
            ende = (verify.winfo_rootx() - karte.winfo_rootx()
                    + verify.winfo_width())
            reserve = karte.winfo_width() - ende
            self.assertGreaterEqual(
                reserve, 8,
                "Nur %d px Reserve rechts neben der Pruefstufe (Karte %d, "
                "Zeile endet %d). Mit der Bildlaufleiste bleibt kein "
                "Spielraum mehr." % (reserve, karte.winfo_width(), ende))
        finally:
            self.wurzel.withdraw()

    def _fenster_auf(self, breite):
        """Stellt das Fenster auf eine Breite und laesst es zur Ruhe kommen."""
        self.wurzel.deiconify()
        try:
            self.wurzel.state("normal")
        except Exception:
            pass
        self.wurzel.geometry("%dx%d" % (breite, self.haupt.WINDOW_MIN_HEIGHT))
        self._beruhigen(self.wurzel, 1.2)

    def test_einbauzeile_wandert_neben_die_pruefstufe(self):
        """Ist rechts Platz, gehoert die Einbauzeile dorthin.

        Das spart eine ganze Zeile Hoehe und nutzt Flaeche, die sonst leer
        bleibt. Der Umschlagpunkt liegt bei rund 1780 px Fensterbreite.
        """
        self._fenster_auf(1900)
        try:
            self.assertTrue(
                self.app._einbauzeile_daneben,
                "Bei 1900 px Fensterbreite ist rechts genug Platz, die "
                "Einbauzeile steht aber immer noch in ihrer eigenen Zeile.")
            pruefstufe = self.app.verify_combo
            kaestchen = self.app.ampr_integrate_check
            abstand = kaestchen.winfo_rootx() - (pruefstufe.winfo_rootx()
                                                 + pruefstufe.winfo_width())
            self.assertEqual(
                abstand, self.haupt.PS5ConverterGUI._ZEILE_ABSTAND_GRUPPE,
                "Abstand zur Pruefstufe ist %d px" % abstand)
        finally:
            self.wurzel.withdraw()

    def test_einbauzeile_faellt_bei_schmalem_fenster_zurueck(self):
        """Reicht die Breite nicht, muss sie zurueck in die eigene Zeile.

        Sonst steht ihr Ende ausserhalb der Karte - unsichtbar und nicht
        anklickbar. Genau dieser Fehler wurde in v1.8.69 behoben.
        """
        self._fenster_auf(self.haupt.WINDOW_MIN_WIDTH)
        try:
            self.assertFalse(
                self.app._einbauzeile_daneben,
                "Bei Mindestbreite passt die Einbauzeile nicht neben die "
                "Pruefstufe, sie steht aber trotzdem dort.")
            karte = self.app.path_card
            letztes = self.app.backport_fw_combo
            ende = (letztes.winfo_rootx() - karte.winfo_rootx()
                    + letztes.winfo_width())
            self.assertLessEqual(ende, karte.winfo_width())
        finally:
            self.wurzel.withdraw()

    def test_der_umbruch_geht_in_beide_richtungen(self):
        """Breiter, schmaler, wieder breiter - der Zustand muss folgen."""
        try:
            for breite, erwartet in ((1900, True),
                                     (self.haupt.WINDOW_MIN_WIDTH, False),
                                     (1900, True)):
                self._fenster_auf(breite)
                with self.subTest(breite=breite):
                    self.assertEqual(bool(self.app._einbauzeile_daneben),
                                     erwartet)
        finally:
            self.wurzel.withdraw()

    def test_alle_beschriftungen_stehen_auf_einer_linie(self):
        """Auch die Einbau-Ueberschrift, wenn die Zeile daneben steht.

        Ihr Kaestchen ist niedriger als die Klapplisten der oberen Zeile und
        sitzt deshalb tiefer. Ueber dem Kaestchen ausgerichtet saesse die
        Ueberschrift acht Pixel unter den anderen.
        """
        self._fenster_auf(1900)
        try:
            namen = ("format_title", "perf_title", "worker_title",
                     "verify_title", "integrate_title")
            hoehen = {n: getattr(self.app, n).winfo_rooty() for n in namen}
            bezug = hoehen["format_title"]
            for name, y in hoehen.items():
                self.assertLessEqual(
                    abs(y - bezug), 1,
                    "%s steht %d px neben der Beschriftungslinie"
                    % (name, abs(y - bezug)))
        finally:
            self.wurzel.withdraw()

    def test_sprachwechsel_laesst_die_zeilen_in_ordnung(self):
        vorher = self.app._current_language
        try:
            for sprache in ("en", "de"):
                self.app._current_language = sprache
                self.app._apply_language()
                self._beruhigen(self.wurzel, 1.2)
                with self.subTest(sprache=sprache):
                    self.test_die_abstaende_stimmen_genau()
                    self.test_die_beschriftungen_ueberlappen_einander_nicht()
        finally:
            self.app._current_language = vorher
            self.app._apply_language()
            self._beruhigen(self.wurzel, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
