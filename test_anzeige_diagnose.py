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

    def test_canvas_knopf_zu_klein_meldet_sich(self):
        """Die Knoepfe dieses Programms sind Canvas-Knoepfe (RoundedButton).

        Bis zum 15.09.2026 fielen sie doppelt aus der Pruefung: "Canvas"
        stand nicht in den Textklassen, und ein Canvas hat keine
        ``text``-Option, also blieb ``hat_text`` falsch. Ausgerechnet bei
        ihnen faellt es auf - die Schrift waechst mit der Anzeigeskalierung,
        die fest eingetragene Knopfhoehe nicht.
        """
        befunde = ad.pruefe_flaechen(
            FENSTER, [_flaeche(klasse="Canvas", breite=150, hoehe=44,
                               wunschbreite=150, wunschhoehe=58)])
        self.assertEqual(_kennungen(befunde), ["text_beschnitten"])
        self.assertIn("14 px", befunde[0].text)

    def test_zeichenflaeche_ohne_text_bleibt_still(self):
        """Gegenprobe - sonst melden die Hintergrundbilder Fehlalarme.

        Sie liegen absichtlich ueber ihren Rand hinaus und tragen keinen
        Text; ``hat_text`` muss sie weiterhin heraushalten.
        """
        self.assertEqual(
            ad.pruefe_flaechen(FENSTER, [_flaeche(klasse="Canvas",
                                                  hat_text=False,
                                                  breite=150, hoehe=44,
                                                  wunschbreite=150,
                                                  wunschhoehe=58)]),
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


class HochrechnungsMessungTests(unittest.TestCase):
    """Eine Hochrechnung ist nur ein Mangel, wenn man sie sieht (02.10.2026).

    Anlass: Auf einem 1920x1200-Schirm (Fenster 1920x1111) meldete der Bericht
    drei Warnungen - Hintergrund und Inhaltsflaeche mit dem eigenen
    ChatGPT-Bild des Nutzers (1672x941, +18 %) und die mitgelieferte
    Seitenleiste (640x1020, +9 %). Gemessen kostete keine davon mehr als 0,8
    von 255 Stufen; die Groessenzahl allein sagte nichts darueber, ob jemand
    etwas sieht. Eine Pruefung, die auf jedem normalen Schirm anschlaegt,
    sagt nichts.
    """

    def test_der_gemessene_nutzerfall_gibt_nichts(self):
        """+18 %, Verlust 0,39: das eigene Bild auf dem 1200er Schirm."""
        lage = ad.Bildlage("Hintergrund", (1672, 941), (1920, 1111), (1920, 1111), 0.39)
        self.assertEqual(ad.pruefe_bilder([lage]), [])

    def test_die_mitgelieferte_seitenleiste_gibt_nichts(self):
        lage = ad.Bildlage("Seitenleiste", (640, 1020), (493, 1111), (493, 1111), 0.59)
        self.assertEqual(ad.pruefe_bilder([lage]), [])

    def test_gemessen_sichtbar_ist_eine_warnung(self):
        """Das alte bg_19 (1424x752, +35 %) galt als sichtbar weich: Verlust 2,12."""
        befunde = ad.pruefe_bilder([ad.Bildlage(
            "Hintergrund", (1424, 752), (1920, 991), (1920, 991), 2.12)])
        self.assertEqual(_kennungen(befunde), ["bild_hochgerechnet"])
        self.assertEqual(befunde[0].schwere, ad.WARNUNG)
        self.assertIn("2.1 von 255 Stufen", befunde[0].text)
        self.assertIn("+35 %", befunde[0].text)

    def test_zwischenbereich_ist_ein_hinweis(self):
        """Zwischen den beiden Schwellen: erwaehnt, aber kein Mangel."""
        lage = ad.Bildlage("Hintergrund", (1672, 941), (1920, 1111), (1920, 1111), 1.5)
        befunde = ad.pruefe_bilder([lage])
        self.assertEqual([b.schwere for b in befunde], [ad.HINWEIS])
        self.assertTrue(ad.pruefe_alles(bilder=[lage]).sauber)

    def test_harte_grenze_gilt_trotz_kleinem_verlust(self):
        """Die alten 320x1000-Leisten (+54 %) verloren nur 1,0 - und waren weich."""
        befunde = ad.pruefe_bilder([ad.Bildlage(
            "Seitenleiste", (320, 1000), (493, 991), (493, 991), 0.98)])
        self.assertEqual([b.schwere for b in befunde], [ad.WARNUNG])

    def test_ohne_messwert_gilt_die_groessenzahl(self):
        """Nicht gemessen heisst: wie frueher - jede Hochrechnung ist eine Warnung."""
        befunde = ad.pruefe_bilder([ad.Bildlage(
            "Hintergrund", (1920, 1020), (1920, 1111), (1920, 1111))])
        self.assertEqual([b.schwere for b in befunde], [ad.WARNUNG])
        self.assertNotIn("Detailverlust", befunde[0].text)

    def test_die_grenzen_im_einzelnen(self):
        """Die Schwellen sind scharf: ``>`` heisst, der Wert selbst bleibt still."""
        bewerte = ad.bewerte_hochrechnung
        self.assertIsNone(bewerte(ad.BILD_FAKTOR_GRENZE, 99.0))
        self.assertIsNone(bewerte(1.10, ad.BILD_VERLUST_HINWEIS))
        self.assertEqual(bewerte(1.10, ad.BILD_VERLUST_HINWEIS + 0.01), ad.HINWEIS)
        self.assertEqual(bewerte(1.10, ad.BILD_VERLUST_WARNUNG), ad.HINWEIS)
        self.assertEqual(bewerte(1.10, ad.BILD_VERLUST_WARNUNG + 0.01), ad.WARNUNG)
        self.assertIsNone(bewerte(ad.BILD_FAKTOR_HART, 0.0))
        self.assertEqual(bewerte(ad.BILD_FAKTOR_HART + 0.01, 0.0), ad.WARNUNG)
        self.assertEqual(bewerte(1.10, None), ad.WARNUNG)

    def test_beschreibung_nennt_zahl_und_urteil(self):
        text = ad.beschreibe_hochrechnung(ad.Bildlage(
            "Hintergrund", (1672, 941), (1920, 1111), (1920, 1111), 0.39))
        self.assertIn("+18 %", text)
        self.assertIn("1672x941", text)
        self.assertIn("0.4 von 255 Stufen", text)
        self.assertIn("nicht zu sehen", text)

    def test_beschreibung_kennt_alle_drei_urteile(self):
        def _text(verlust):
            return ad.beschreibe_hochrechnung(ad.Bildlage(
                "x", (1672, 941), (1920, 1111), (1920, 1111), verlust))
        self.assertIn("nicht zu sehen", _text(0.5))
        self.assertIn("kaum zu sehen", _text(1.5))
        self.assertIn("sichtbar weich", _text(2.5))
        self.assertIn("nicht gemessen", ad.beschreibe_hochrechnung(ad.Bildlage(
            "x", (1672, 941), (1920, 1111), (1920, 1111))))

    def test_beschreibung_schweigt_ohne_hochrechnung(self):
        self.assertEqual(ad.beschreibe_hochrechnung(ad.Bildlage(
            "x", (1920, 1200), (1920, 1111), (1920, 1111))), "")
        self.assertEqual(ad.beschreibe_hochrechnung(ad.Bildlage("x")), "")

    # --- die Messung selbst -------------------------------------------------

    @staticmethod
    def _verlauf(breite=400, hoehe=300):
        from PIL import Image
        bild = Image.new("RGB", (breite, hoehe))
        bild.putdata([(x * 255 // max(1, breite - 1), 40, 90)
                      for _y in range(hoehe) for x in range(breite)])
        return bild

    @staticmethod
    def _schachbrett(breite=400, hoehe=300):
        from PIL import Image
        bild = Image.new("RGB", (breite, hoehe))
        bild.putdata([(255, 255, 255) if (x + y) % 2 else (0, 0, 0)
                      for y in range(hoehe) for x in range(breite)])
        return bild

    def test_ein_glatter_verlauf_verliert_nichts(self):
        verlust = ad.messe_hochrechnungsverlust(self._verlauf(), 1.18)
        self.assertLess(verlust, 0.5)

    def test_feine_zeichnung_verliert_viel(self):
        """Das unterscheidet das Mass von der Groessenzahl: Ein Pixelraster stirbt."""
        verlust = ad.messe_hochrechnungsverlust(self._schachbrett(), 1.18)
        self.assertGreater(verlust, 20.0)

    def test_ohne_hochrechnung_kein_verlust(self):
        self.assertEqual(ad.messe_hochrechnungsverlust(self._schachbrett(), 1.0), 0.0)
        self.assertEqual(ad.messe_hochrechnungsverlust(self._schachbrett(), 0.5), 0.0)

    def test_ohne_bild_wird_nichts_behauptet(self):
        self.assertIsNone(ad.messe_hochrechnungsverlust(None, 1.5))

    def test_gemessen_wird_der_mittlere_ausschnitt(self):
        """Gross gezogen waere die Feinzeichnung weg - gemessen wird in Originalgroesse."""
        from PIL import Image
        bild = Image.new("RGB", (600, 600), (30, 30, 60))
        bild.paste(self._schachbrett(200, 200), (200, 200))
        vorher = ad._MESS_AUSSCHNITT
        try:
            ad._MESS_AUSSCHNITT = (200, 200)
            mitte = ad.messe_hochrechnungsverlust(bild, 1.18)
        finally:
            ad._MESS_AUSSCHNITT = vorher
        ganz = ad.messe_hochrechnungsverlust(bild, 1.18)
        self.assertGreater(mitte, ganz * 2)

    # --- der Waechter ueber den echten Bestand ------------------------------

    #: (Fenster, Seitenleiste) wie am Nutzerrechner gemessen (125 %): auf dem
    #: 1200er Schirm 1920x1111 und 493x1111. QHD mit 150 % macht die Leiste
    #: 593 breit.
    SCHIRME = (
        ("FHD 1080p", (1920, 991), (493, 991)),
        ("WUXGA 1200p", (1920, 1111), (493, 1111)),
        ("QHD 1440p", (2560, 1391), (593, 1391)),
    )

    def test_kein_mitgeliefertes_bild_wird_zum_mangel(self):
        """Gemessen an allen 40 Bildern: Auf FHD, WUXGA und QHD ist keins sichtbar weich.

        Ein neues Bild, das auf einem dieser Schirme sichtbar weich wuerde (zu
        klein oder zu fein gezeichnet), faellt hier auf - nicht erst im Bericht
        eines Anwenders. Auf FHD passen die Bilder genau und melden gar nichts.
        """
        from PIL import Image

        ordner = os.path.join(os.path.dirname(HAUPTDATEI), "Hintergrundbilder")
        namen = sorted(n for n in os.listdir(ordner) if n.lower().endswith(".png"))
        self.assertGreaterEqual(len(namen), 40, "Bildbestand nicht gefunden")
        for name in namen:
            with Image.open(os.path.join(ordner, name)) as roh:
                bild = roh.convert("RGB")
            for schirm, fenster, leiste in self.SCHIRME:
                flaeche = leiste if name.startswith("sidebar_") else fenster
                lage = ad.Bildlage(name, bild.size, None, flaeche)
                faktor = ad.hochrechnungsfaktor(lage)
                verlust = (ad.messe_hochrechnungsverlust(bild, faktor)
                           if faktor is not None else None)
                befunde = ad.pruefe_bilder([ad.Bildlage(
                    name, bild.size, None, flaeche, verlust)])
                with self.subTest(bild=name, schirm=schirm):
                    self.assertEqual(
                        [b for b in befunde if b.schwere != ad.HINWEIS], [],
                        "%s auf %s: %s" % (name, schirm, befunde))
                    if schirm == "FHD 1080p":
                        self.assertEqual(befunde, [])


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


class BedienungTests(unittest.TestCase):
    """Das Mausrad darf keine Auswahlliste verstellen."""

    def test_leere_liste_gibt_nichts(self):
        self.assertEqual(ad.pruefe_bedienung(ad.Bedienlage()), [])

    def test_eine_verstellende_klasse_warnt(self):
        befunde = ad.pruefe_bedienung(ad.Bedienlage(rad_verstellt=("TCombobox",)))
        self.assertEqual(len(befunde), 1)
        self.assertEqual(befunde[0].schwere, ad.WARNUNG)
        self.assertIn("TCombobox", befunde[0].text)

    def test_die_klassen_stehen_im_befund(self):
        befunde = ad.pruefe_bedienung(
            ad.Bedienlage(rad_verstellt=("TCombobox", "TSpinbox")))
        self.assertIn("TCombobox", befunde[0].text)
        self.assertIn("TSpinbox", befunde[0].text)

    def test_ins_gesamturteil_eingebunden(self):
        ergebnis = ad.pruefe_alles(
            bedienung=ad.Bedienlage(rad_verstellt=("TCombobox",)))
        self.assertFalse(ergebnis.sauber)
        self.assertEqual(len(ergebnis.warnungen), 1)


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

    def test_die_bildmessung_ist_eingehaengt(self):
        """Ohne sie faellt der Bericht still auf die Groessenzahl zurueck.

        Dann stuenden auf jedem Schirm ueber FHD wieder Warnungen, die niemand
        sehen kann (02.10.2026) - und kein Test der reinen Regeln wuerde es
        merken, denn die rechnen mit erfundenen Zahlen.
        """
        sammler = self._wache("_diagnose_bilder_sammeln")
        self.assertIn("messe_hochrechnungsverlust", sammler)
        self.assertIn("verlust=", sammler)
        self.assertIn("beschreibe_hochrechnung", self._wache("_diagnose_anzeige"))

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
