# -*- coding: utf-8 -*-
"""Tests für die Darstellungsprüfung im Diagnosebericht.

Die Prüfregeln arbeiten auf schlichten Datensätzen, nicht auf Tk-Widgets.
Deshalb kommen sie hier ohne Fenster aus – erfundene Zahlen genügen, und die
Tests laufen auch auf einem Bauserver ohne Anzeige.

Was am laufenden Fenster gemessen wurde, steht als Zahl in den Tests: Der
Bildschirmmitschnitt vom 20.08.2026 zeigte ein Hintergrundbild von 1424x752
auf einer Fläche von 1920x991 und ein Seitenleistenbild von 320x1000 auf
493x991.

Der zweite Teil prüft am Quelltext nach, dass die vier Configure-Wachen einen
veralteten Auftrag abbestellen, **bevor** sie abkürzen. Genau diese Reihenfolge
war der Fehler: Beim Designwechsel meldete die Inhaltsfläche erst 1600 und
gleich darauf 1427; die zweite Meldung kürzte ab, der für 1600 bestellte
Auftrag lief 80 ms später trotzdem und überschrieb das richtige Bild.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import anzeige_diagnose as ad

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")


def _flaeche(**abweichung):
    """Ein unauffälliges Bedienelement, das einzeln verbogen werden kann."""
    vorgabe = dict(name="knopf", klasse="Button", x=10, y=10,
                   breite=200, hoehe=40, wunschbreite=200, wunschhoehe=40,
                   sichtbar=True, hat_text=True)
    vorgabe.update(abweichung)
    return ad.Flaeche(**vorgabe)


FENSTER = ad.Fensterlage(breite=1920, hoehe=991, x=0, y=0,
                         schirm_breite=1920, schirm_hoehe=1080)


def _kennungen(befunde):
    return sorted(b.kennung for b in befunde)


class FlaechenTests(unittest.TestCase):
    """Abgeschnittene, eingeklappte und zu enge Bedienelemente."""

    def test_heile_flaeche_gibt_nichts(self):
        self.assertEqual(ad.pruefe_flaechen(FENSTER, [_flaeche()]), [])

    def test_eingeklappt_ist_ein_fehler(self):
        """Packreihenfolge quetscht Knopfleisten auf null."""
        befunde = ad.pruefe_flaechen(
            FENSTER, [_flaeche(breite=1, hoehe=1,
                               wunschbreite=473, wunschhoehe=51)])
        self.assertEqual(_kennungen(befunde), ["eingeklappt"])
        self.assertEqual(befunde[0].schwere, ad.FEHLER)
        self.assertIn("473x51", befunde[0].text)

    def test_ohne_wunschmass_kein_fehlalarm(self):
        """Ein Element ohne eigenen Platzbedarf darf 1x1 sein."""
        self.assertEqual(
            ad.pruefe_flaechen(FENSTER, [_flaeche(breite=1, hoehe=1,
                                                  wunschbreite=1, wunschhoehe=1)]),
            [])

    def test_ueber_den_rechten_rand(self):
        befunde = ad.pruefe_flaechen(FENSTER, [_flaeche(x=1800, breite=200)])
        self.assertEqual(_kennungen(befunde), ["abgeschnitten"])
        self.assertIn("80 px", befunde[0].text)

    def test_ueber_den_unteren_rand(self):
        befunde = ad.pruefe_flaechen(FENSTER, [_flaeche(y=970, hoehe=40)])
        self.assertEqual(_kennungen(befunde), ["abgeschnitten"])
        self.assertIn("unteren", befunde[0].text)

    def test_links_ausserhalb(self):
        befunde = ad.pruefe_flaechen(FENSTER, [_flaeche(x=-30)])
        self.assertEqual(_kennungen(befunde), ["abgeschnitten"])

    def test_toleranz_am_rand(self):
        """Zwei Pixel Überstand sind Rahmenbreite, kein Mangel."""
        self.assertEqual(
            ad.pruefe_flaechen(FENSTER, [_flaeche(x=1720, breite=202)]), [])

    def test_zu_schmal_fuer_die_beschriftung(self):
        befunde = ad.pruefe_flaechen(FENSTER, [_flaeche(breite=120,
                                                        wunschbreite=200)])
        self.assertEqual(_kennungen(befunde), ["text_beschnitten"])
        self.assertIn("80 px", befunde[0].text)

    def test_bildlabel_ohne_text_ist_kein_mangel(self):
        """Die Hintergrundlabels liegen absichtlich über ihren Rand hinaus.

        Ohne diese Unterscheidung meldete die Prüfung am 20.08.2026 vier
        Fehlalarme: sidebar_bg_label, content_bg_label, card_bg_label und das
        der Aktionsleiste sind Label ohne Text, nur mit Bild.
        """
        self.assertEqual(
            ad.pruefe_flaechen(FENSTER, [_flaeche(klasse="Label", hat_text=False,
                                                  x=0, y=0,
                                                  breite=493, wunschbreite=497,
                                                  hoehe=991, wunschhoehe=995)]),
            [])

    def test_eingabefeld_darf_kleiner_sein(self):
        """Ein Eingabefeld rollt, ein Knopf nicht."""
        self.assertEqual(
            ad.pruefe_flaechen(FENSTER, [_flaeche(klasse="Entry", breite=80,
                                                  wunschbreite=400)]),
            [])

    def test_unsichtbares_zaehlt_nicht(self):
        self.assertEqual(
            ad.pruefe_flaechen(FENSTER, [_flaeche(sichtbar=False, breite=1,
                                                  hoehe=1, wunschbreite=200,
                                                  wunschhoehe=40)]),
            [])


class BilderTests(unittest.TestCase):
    """Hochgerechnete und stehengebliebene Hintergrundbilder."""

    def test_passendes_bild_gibt_nichts(self):
        self.assertEqual(
            ad.pruefe_bilder([ad.Bildlage("Hintergrund", (1920, 991),
                                          (1920, 991), (1920, 991))]),
            [])

    def test_hochgerechnet_nennt_den_zuschlag(self):
        """Der gemessene Fall: bg_19_ray-burst.png auf einem 1920er Schirm."""
        befunde = ad.pruefe_bilder([ad.Bildlage("Hintergrund", (1424, 752),
                                                (1920, 991), (1920, 991))])
        self.assertEqual(_kennungen(befunde), ["bild_hochgerechnet"])
        self.assertIn("+35 %", befunde[0].text)
        self.assertIn("1920x991", befunde[0].text)

    def test_seitenleiste_hochgerechnet(self):
        befunde = ad.pruefe_bilder([ad.Bildlage("Seitenleiste", (320, 1000),
                                                (493, 991), (493, 991))])
        self.assertIn("+54 %", befunde[0].text)

    def test_zwei_prozent_sind_keine_meldung(self):
        self.assertEqual(
            ad.pruefe_bilder([ad.Bildlage("x", (1900, 991), (1920, 991),
                                          (1920, 991))]),
            [])

    def test_stehengeblieben_ist_ein_fehler(self):
        """Der Fall vom Designwechsel: gezeichnet 1600, Fläche 1427."""
        befunde = ad.pruefe_bilder([ad.Bildlage("Inhaltsflaeche", (1920, 1020),
                                                (1600, 991), (1427, 991))])
        self.assertEqual(_kennungen(befunde), ["bild_nicht_nachgezogen"])
        self.assertEqual(befunde[0].schwere, ad.FEHLER)

    def test_fehlende_messung_meldet_nichts(self):
        self.assertEqual(ad.pruefe_bilder([ad.Bildlage("x")]), [])


class SkalierungTests(unittest.TestCase):
    """DPI-Bewusstsein, tk scaling und Schriftgröße."""

    def test_windows_bei_125_prozent_ist_in_ordnung(self):
        """Der gemessene Normalfall: 120 dpi, tk scaling 1.6683, 20 px hoch."""
        self.assertEqual(
            ad.pruefe_skalierung(ad.Skalierungslage(
                plattform="win32", dpi_bewusstsein=2, fenster_dpi=120,
                tk_skalierung=1.6683, schrifthoehe_px=20, schriftgroesse_pt=9)),
            [])

    def test_ohne_dpi_bewusstsein(self):
        befunde = ad.pruefe_skalierung(ad.Skalierungslage(
            plattform="win32", dpi_bewusstsein=0, fenster_dpi=96,
            tk_skalierung=1.3333, schrifthoehe_px=15))
        self.assertIn("dpi_unbewusst", _kennungen(befunde))
        self.assertEqual([b for b in befunde
                          if b.kennung == "dpi_unbewusst"][0].schwere, ad.FEHLER)

    def test_dpi_bewusstsein_nur_unter_windows(self):
        """Auf dem Mac gibt es die Abfrage nicht – ``None`` darf nicht melden."""
        self.assertEqual(
            ad.pruefe_skalierung(ad.Skalierungslage(
                plattform="darwin", dpi_bewusstsein=None, tk_skalierung=1.3499,
                schrifthoehe_px=20)),
            [])

    def test_skalierung_passt_nicht_zum_dpi(self):
        befunde = ad.pruefe_skalierung(ad.Skalierungslage(
            plattform="win32", dpi_bewusstsein=2, fenster_dpi=192,
            tk_skalierung=1.3333, schrifthoehe_px=15))
        self.assertIn("skalierung_weicht_ab", _kennungen(befunde))

    def test_zu_kleine_schrift(self):
        befunde = ad.pruefe_skalierung(ad.Skalierungslage(
            plattform="darwin", tk_skalierung=1.3499, schrifthoehe_px=9,
            schriftgroesse_pt=6))
        self.assertEqual(_kennungen(befunde), ["schrift_zu_klein"])

    def test_zwoelf_pixel_gelten_noch_als_normal(self):
        """Die Schwelle liegt bewusst unter dem Mac-Befund von 12,1 px.

        Dieselben 12 px sind unter Windows bei 100 % Anzeigeskalierung der
        Normalfall (9 pt x 1,3333). Eine Regel, die den Mac-Fall faengt,
        wuerde also jeden Windows-Rechner ohne Skalierung anmeckern. Was die
        Schrift dort zu klein machte, steht in ``pt()``; hier bleibt nur die
        Untergrenze, unter der es auf keiner Plattform noch lesbar ist.
        """
        self.assertEqual(
            ad.pruefe_skalierung(ad.Skalierungslage(
                plattform="darwin", tk_skalierung=1.3499, schrifthoehe_px=12,
                schriftgroesse_pt=9)),
            [])

    def test_sehr_grosse_schrift_ist_nur_ein_hinweis(self):
        befunde = ad.pruefe_skalierung(ad.Skalierungslage(
            plattform="win32", dpi_bewusstsein=2, schrifthoehe_px=40))
        self.assertEqual(befunde[0].schwere, ad.HINWEIS)


class LaufruheTests(unittest.TestCase):
    """Speicher, angesammelte Bilder, Zeitgeber und Reaktionszeit."""

    def test_normalbetrieb_gibt_nichts(self):
        """Die gemessenen Werte im Leerlauf: 123 MB, 21 Bilder, 1 Zeitgeber."""
        self.assertEqual(
            ad.pruefe_laufruhe(ad.Laufruhelage(
                speicher_mb=123, speicher_start_mb=56, tk_bilder=21,
                offene_zeitgeber=1, schleife_ms=0.0, threads=2)),
            [])

    def test_viel_speicher_warnt(self):
        befunde = ad.pruefe_laufruhe(ad.Laufruhelage(speicher_mb=1800))
        self.assertEqual(_kennungen(befunde), ["speicher_hoch"])
        self.assertEqual(befunde[0].schwere, ad.WARNUNG)

    def test_sehr_viel_speicher_ist_ein_fehler(self):
        befunde = ad.pruefe_laufruhe(ad.Laufruhelage(speicher_mb=3200))
        self.assertEqual(befunde[0].schwere, ad.FEHLER)

    def test_zuwachs_im_leerlauf(self):
        befunde = ad.pruefe_laufruhe(ad.Laufruhelage(
            speicher_mb=1000, speicher_start_mb=120, auftrag_laeuft=False))
        self.assertIn("speicher_waechst", _kennungen(befunde))

    def test_zuwachs_waehrend_eines_auftrags_ist_normal(self):
        """Große Puffer sind beim Packen gewollt und sagen nichts über ein Leck."""
        befunde = ad.pruefe_laufruhe(ad.Laufruhelage(
            speicher_mb=1000, speicher_start_mb=120, auftrag_laeuft=True))
        self.assertNotIn("speicher_waechst", _kennungen(befunde))

    def test_ohne_startwert_kein_zuwachs(self):
        befunde = ad.pruefe_laufruhe(ad.Laufruhelage(
            speicher_mb=1000, speicher_start_mb=0.0))
        self.assertNotIn("speicher_waechst", _kennungen(befunde))

    def test_angesammelte_tk_bilder(self):
        befunde = ad.pruefe_laufruhe(ad.Laufruhelage(tk_bilder=500))
        self.assertEqual(_kennungen(befunde), ["bilder_haeufen_sich"])

    def test_angesammelte_zeitgeber(self):
        befunde = ad.pruefe_laufruhe(ad.Laufruhelage(offene_zeitgeber=200))
        self.assertEqual(_kennungen(befunde), ["zeitgeber_haeufen_sich"])

    def test_traege_schleife(self):
        self.assertEqual(
            ad.pruefe_laufruhe(ad.Laufruhelage(schleife_ms=200))[0].schwere,
            ad.WARNUNG)
        self.assertEqual(
            ad.pruefe_laufruhe(ad.Laufruhelage(schleife_ms=900))[0].schwere,
            ad.FEHLER)


class GesamtTests(unittest.TestCase):
    """Zusammenspiel und Zusammenfassung."""

    def test_fehler_stehen_oben(self):
        ergebnis = ad.pruefe_alles(
            fenster=FENSTER,
            flaechen=[_flaeche(breite=120, wunschbreite=200)],
            bilder=[ad.Bildlage("x", (1920, 1020), (1600, 991), (1427, 991))])
        self.assertEqual(ergebnis.befunde[0].schwere, ad.FEHLER)
        self.assertEqual(len(ergebnis.fehler), 1)
        self.assertEqual(len(ergebnis.warnungen), 1)
        self.assertFalse(ergebnis.sauber)

    def test_fehlende_messung_bricht_nicht_ab(self):
        """Ein Bericht muss auch entstehen, wenn sich etwas nicht auslesen ließ."""
        self.assertTrue(ad.pruefe_alles().sauber)

    def test_hinweise_gelten_nicht_als_mangel(self):
        ergebnis = ad.pruefe_alles(skalierung=ad.Skalierungslage(
            plattform="win32", dpi_bewusstsein=2, schrifthoehe_px=40))
        self.assertTrue(ergebnis.sauber)
        self.assertEqual(len(ergebnis.befunde), 1)

    def test_zusammenfassung_ohne_befund(self):
        self.assertEqual(ad.zusammenfassung(ad.Pruefergebnis()),
                         "Darstellung: keine Auffälligkeit")

    def test_zusammenfassung_zaehlt(self):
        ergebnis = ad.pruefe_alles(
            bilder=[ad.Bildlage("a", (1920, 1020), (1600, 991), (1427, 991)),
                    ad.Bildlage("b", (320, 1000), (493, 991), (493, 991))])
        text = ad.zusammenfassung(ergebnis)
        self.assertIn("1 x FEHLER", text)
        self.assertIn("1 x WARNUNG", text)


class QuelltextTests(unittest.TestCase):
    """Die Reihenfolge in den Configure-Wachen – am laufenden Tk nicht sichtbar.

    Der Fehler lag zwischen zwei Ereignissen, die 80 ms auseinanderliegen. Ein
    Test, der ein Fenster aufbaut, müsste genau dazwischen messen. Am Quelltext
    ist die Bedingung dagegen eindeutig: Das Abbestellen muss vor der Abkürzung
    stehen.
    """

    @classmethod
    def setUpClass(cls):
        with open(HAUPTDATEI, "r", encoding="utf-8") as datei:
            cls.quelltext = datei.read()
        with open(os.path.join(os.path.dirname(HAUPTDATEI),
                               "ps5_validator", "utils", "i18n.py"),
                  "r", encoding="utf-8") as datei:
            cls.i18n_text = datei.read()

    def _faltbare(self):
        """Die Eintraege aus _FALTBARE_TITELKNOEPFE, aus dem Quelltext gelesen."""
        block = self.quelltext[self.quelltext.index("_FALTBARE_TITELKNOEPFE"):]
        block = block[:2000]
        return re.findall(r'\("(_btn_[a-z_]+)", "([\w.]+)", "(\w+)"\)', block)

    def _wache(self, name: str) -> str:
        """Der Rumpf einer Methode bis zur nächsten Methodendefinition."""
        anfang = self.quelltext.index("    def %s(self" % name)
        weiter = self.quelltext.index("\n    def ", anfang + 10)
        return self.quelltext[anfang:weiter]

    def test_abbestellen_steht_vor_der_abkuerzung(self):
        for wache, merker in (("_on_root_configure", "_bg_resize_after_id"),
                              ("_on_content_area_configure", "_content_bg_resize_after_id"),
                              ("_on_action_bar_configure", "_action_bar_bg_resize_after_id"),
                              ("_on_sidebar_configure", "_sidebar_bg_resize_after_id")):
            with self.subTest(wache=wache):
                rumpf = self._wache(wache)
                abbestellen = rumpf.index("after_cancel(self.%s)" % merker)
                abkuerzung = rumpf.index("_hintergrund_ist_aktuell")
                self.assertLess(
                    abbestellen, abkuerzung,
                    "%s kuerzt ab, bevor der veraltete Auftrag weg ist" % wache)

    def test_merker_wird_geleert(self):
        """Sonst bestellt der nächste Durchgang eine bereits gelaufene Kennung ab."""
        for wache, merker in (("_on_root_configure", "_bg_resize_after_id"),
                              ("_on_content_area_configure", "_content_bg_resize_after_id"),
                              ("_on_action_bar_configure", "_action_bar_bg_resize_after_id"),
                              ("_on_sidebar_configure", "_sidebar_bg_resize_after_id")):
            with self.subTest(wache=wache):
                self.assertIn("self.%s = None" % merker, self._wache(wache))

    def test_wachen_fragen_das_bild_nicht_den_merker(self):
        """Der gemerkte Wert kann von der Wirklichkeit abdriften, das Bild nicht."""
        for merker in ("_last_bg_resize_size", "_last_content_bg_resize_size",
                       "_last_action_bar_bg_resize_size",
                       "_last_sidebar_bg_resize_size"):
            with self.subTest(merker=merker):
                self.assertNotIn("if self.%s == (width, height):" % merker,
                                 self.quelltext)

    def test_startphase_zieht_die_hintergruende_nach(self):
        rumpf = self._wache("_finish_startup_phase")
        self.assertIn("_hintergrund_beim_start_nachziehen", rumpf)

    def test_ruhendes_fenster_wird_geprueft(self):
        self.assertIn("_hintergruende_nachziehen", self._wache("_on_layout_settled"))

    def test_diagnosebericht_enthaelt_die_neuen_abschnitte(self):
        """Ausgefuehrt, nicht im Quelltext gesucht.

        Seit dem 22. Schnitt steht der Bericht in
        diagnose_befund.Diagnosebericht. Eine Textsuche im Monolithen
        faende die Schluessel nicht mehr - obwohl die Abschnitte da
        sind. Hier wird der Bericht wirklich gebaut.
        """
        from ps5_validator.utils.diagnose_befund import Diagnosebericht

        text = Diagnosebericht().bericht_text()
        for schluessel in ("diagnostics.report_section_layout",
                           "diagnostics.report_section_stability"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, text)

    def test_integrationen_haben_eine_eigene_rasterzeile(self):
        """Sonst braucht die Zeile 1145 px und ragt aus schmalen Fenstern.

        Bis v1.8.69 hing die ganze Kette an der Pruefstufen-Liste:
        Kompression, Worker, Pruefung, AMPR EMU, Version, PlayGo, BACKPORT,
        Firmware. Bei einem 1366er Fenster standen davon 352 px ausserhalb
        der Karte, bei der damaligen Mindestbreite 1100 sogar 618 px - der
        Teil war weder sichtbar noch bedienbar.
        """
        self.assertIn("self.ampr_integrate_check.grid(row=5, column=0,",
                      self.quelltext)
        self.assertNotIn('self.ampr_integrate_check.place(in_=self.verify_combo',
                         self.quelltext)

    def test_die_zeilen_darunter_sind_mitgerueckt(self):
        """Neue Rasterzeilen - was darunter lag, muss mitruecken.

        Seit dem 03.09.2026 steht die Bauform-Wahl auf Zeile 7; alles
        darunter ist um eine Zeile tiefer gerutscht. Zwei Elemente in
        derselben Zelle waeren kein Fehler, den Tk meldet - sie laegen
        einfach uebereinander.
        """
        for widget, zeile in (("integrate_title", 4),
                              ("ampr_integrate_check", 5),
                              ("format_info_label", 6),
                              ("bauform_title", 7), ("bauform_combo", 7),
                              ("dest_title", 8),
                              ("dest_entry", 9), ("dest_btn", 9),
                              ("temp_title", 10), ("temp_entry", 11),
                              ("temp_btn", 11), ("shutdown_check", 12)):
            with self.subTest(widget=widget):
                self.assertIn("self.%s.grid(row=%d," % (widget, zeile),
                              self.quelltext)

    def test_traegerzeile_bekommt_eine_hoehe(self):
        """Die Bedienelemente liegen per place darauf und zaehlen nicht mit.

        Ohne die Angabe bliebe die Zeile einen Pixel hoch, und die
        Klapplisten ragten in den Hinweistext darunter.
        """
        self.assertIn("_integrationszeile_hoehe_setzen", self.quelltext)
        rumpf = self._wache("_integrationszeile_hoehe_setzen")
        self.assertIn("winfo_reqheight", rumpf)
        self.assertIn("grid_rowconfigure(", rumpf)
        # Ein tk.Frame als Traeger malte einen dunklen Balken ueber das
        # Hintergrundbild - siehe die Aufnahme vom 20.08.2026.
        self.assertNotIn("self.integrate_row = tk.Frame", self.quelltext)

    def test_mindestbreite_traegt_die_obere_zeile(self):
        """Auch ohne die Integrationen braucht sie 625 px Kartenbreite.

        Die Karte ist rund 573 px schmaler als das Fenster (Seitenleiste plus
        Polsterung, bei 125 Prozent Anzeigeskalierung gemessen). Bei 1100 px
        blieben 527 - schon die Pruefstufen-Liste fiel heraus, und das seit
        v1.8.56.
        """
        treffer = re.search(r"^WINDOW_MIN_WIDTH = (\d+)", self.quelltext,
                            re.MULTILINE)
        self.assertIsNotNone(treffer)
        self.assertGreaterEqual(int(treffer.group(1)), 1200)

    def test_titelleiste_faltet_statt_zu_quetschen(self):
        """pack laesst nichts weg - es quetscht, und das war unbedienbar.

        Am 20.08.2026 gemessen: Die dreizehn Knoepfe wollen zusammen rund
        1515 px. Bei einem 1440 px breiten Fenster war "BENUTZERHANDBUCH"
        noch 100 statt 189 px breit, bei 1366 nur noch **26**.
        """
        for name, _schluessel, _befehl in self._faltbare():
            with self.subTest(knopf=name):
                self.assertIn("self.%s = flach_knopf(" % name, self.quelltext)
        rumpf = self._wache("_titelleiste_anpassen")
        self.assertIn("pack_forget()", rumpf)
        self.assertIn("_titelleiste_gefaltet", rumpf)

    def test_eingefaltete_stehen_im_sammelmenue(self):
        """Sonst waeren sie gar nicht mehr erreichbar."""
        rumpf = self._wache("_sammelmenue_bestuecken")
        self.assertIn("_MORE_TOOLS_ENTRIES", rumpf)
        self.assertIn("_FALTBARE_TITELKNOEPFE", rumpf)
        self.assertIn("add_separator", rumpf)
        # Beim Oeffnen bestuecken, nicht einmalig: Welche Knoepfe eingefaltet
        # sind, haengt an der Fensterbreite und aendert sich mit ihr.
        self.assertIn("self._sammelmenue_bestuecken()", self.quelltext)

    def test_faltbare_knoepfe_haben_gueltige_befehle(self):
        """Ein Tippfehler im Methodennamen faellt sonst erst im Menue auf."""
        for _name, schluessel, befehl in self._faltbare():
            with self.subTest(befehl=befehl):
                self.assertIn("def %s(self" % befehl, self.quelltext)
                self.assertIn("'%s':" % schluessel, self.i18n_text)

    def test_leiste_wird_in_urspruenglicher_reihenfolge_gepackt(self):
        """pack haengt ein zurueckkehrendes Element sonst ans linke Ende."""
        rumpf = self._wache("_titelleiste_anpassen")
        self.assertIn("_titelleiste_ordnung", rumpf)
        self.assertIn('knopf.pack(side="right", padx=padx)', rumpf)

    def test_ausfalten_hat_luft(self):
        """Ohne Abstand klappte ein Knopf beim Ziehen im Wechsel ein und aus."""
        self.assertIn("_TITELLEISTE_LUFT", self.quelltext)
        self.assertIn("_TITELLEISTE_LUFT", self._wache("_titelleiste_anpassen"))

    def test_wechselnde_texte_brechen_um(self):
        """Die Statuszeile wollte 860 px, die Karte bot bei 1230 px nur 627."""
        rumpf = self._wache("_inhaltstexte_umbrechen")
        self.assertIn("wraplength", rumpf)
        # Der eingebrannte Bildausschnitt bestimmt bei compound="center" den
        # Platzbedarf. Er misst nur bei Textwechsel neu - eine neue
        # Umbruchbreite aendert den Text aber nicht.
        self.assertIn("_caption_natural_size = None", rumpf)
        self.assertIn("status_label", self.quelltext)

    def test_umbruch_steht_vor_dem_einbrennen(self):
        """Sonst bekommt der Ausschnitt die Breite des ungebrochenen Textes."""
        rumpf = self._wache("_on_layout_settled")
        self.assertLess(rumpf.index("_inhaltstexte_umbrechen"),
                        rumpf.index("_redraw_all_captions"))

    def test_schalter_steht_vor_der_rechtepruefung(self):
        """Eine UAC-Abfrage könnte im Terminal niemand beantworten."""
        block = self.quelltext[self.quelltext.index('if __name__ == "__main__":'):]
        self.assertLess(block.index('sys.argv[1] == "--anzeige-diagnose"'),
                        block.index("_request_elevation()"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
