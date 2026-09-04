# -*- coding: utf-8 -*-
"""Das Fenster startet in der zuletzt benutzten Groesse.

Bis v1.9.2 rief der Aufbau ``geometry(...)`` und danach ``state("zoomed")`` -
das Fenster nahm also **immer** den ganzen Bildschirm ein. Auf einem grossen
Schirm hiess das: bei jedem Start von Hand an der Ecke kleiner ziehen.

Geprueft wird die Rechnung, nicht die Anzeige: ``_fenstergeometrie_wieder-
herstellen`` bekommt eine Attrappe als ``root`` und einen vorgegebenen
Einstellungsbestand; gemessen wird, welche Geometrie sie setzt. Ein echtes
Fenster waere dafuer unnoetig und haenge an der Bildschirmgroesse des
Pruefrechners.

Die drei Sicherungen sind der eigentliche Gegenstand. Ein gemerkter Stand
darf nie zur Falle werden - besonders die dritte: Wird ein zweiter
Bildschirm abgezogen, liegt der gemerkte Ort ausserhalb, und ohne Korrektur
startet das Fenster unsichtbar. Der Anwender haette dann kein Mittel, es
zurueckzuholen.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP  # noqa: E402

G = APP.PS5ConverterGUI


class _Wurzel:
    """So viel Fenster, wie die Rechnung anfasst."""

    def __init__(self, schirm=(3440, 1440), zustand="normal",
                 geometrie="1366x820+10+20", flaeche=None):
        self._schirm = schirm
        self._zustand = zustand
        self._geometrie = geometrie
        #: Die gesamte Flaeche ueber alle Bildschirme. Ohne Angabe ist sie
        #: der erste Schirm - der Einzelbildschirm-Fall.
        self._flaeche = flaeche or (0, 0, schirm[0], schirm[1])
        self.gesetzt: list[str] = []
        self.maximiert = False

    def geometry(self, wert=None):
        if wert is None:
            return self._geometrie
        self.gesetzt.append(wert)
        return None

    def winfo_geometry(self):
        return self._geometrie

    def winfo_screenwidth(self):
        return self._schirm[0]

    def winfo_screenheight(self):
        return self._schirm[1]

    def state(self, wert=None):
        if wert is None:
            return self._zustand
        if wert == "zoomed":
            self.maximiert = True
        return None


class _Traeger:
    """Nur die zwei Nahtstellen zur Einstellungsdatei."""

    _GEOMETRIE_SCHLUESSEL = G._GEOMETRIE_SCHLUESSEL
    _MAXIMIERT_SCHLUESSEL = G._MAXIMIERT_SCHLUESSEL
    _fenstergeometrie_wiederherstellen = G._fenstergeometrie_wiederherstellen
    _maximieren_versuchen = G._maximieren_versuchen
    _fenstergeometrie_merken = G._fenstergeometrie_merken
    _fensterzustand_verfolgen = G._fensterzustand_verfolgen
    #: Aus der echten Klasse uebernommen, nicht hier erfunden - sonst
    #: pruefte die Reihe gegen eigene Vorgaben statt gegen die des Programms.
    _letzter_fensterzustand = G._letzter_fensterzustand
    _letzte_fenstergeometrie = G._letzte_fenstergeometrie

    def _arbeitsflaeche(self):
        """Statt der echten Messung der vorgegebene Wert.

        Die Messung selbst haengt an Windows und an der Zahl der
        angeschlossenen Bildschirme - hier geht es um die **Rechnung**
        darueber.
        """
        return self.root._flaeche

    def __init__(self, bestand=None, **kwargs):
        self._bestand = dict(bestand or {})
        self.root = _Wurzel(**kwargs)
        self.geschrieben: dict = {}

    def _load_setting(self, name, vorgabe):
        return self._bestand.get(name, vorgabe)

    def _save_setting(self, name, wert):
        self.geschrieben[name] = wert


def _masse(text: str) -> tuple[int, int, int | None, int | None]:
    """Zerlegt ``BxH+X+Y`` in Zahlen."""
    import re

    m = re.match(r"^(\d+)x(\d+)(?:\+(-?\d+)\+(-?\d+))?$", text)
    assert m, "Unbrauchbare Geometrie: %r" % text
    return (int(m.group(1)), int(m.group(2)),
            int(m.group(3)) if m.group(3) else None,
            int(m.group(4)) if m.group(4) else None)


class OhneGemerktenStandTests(unittest.TestCase):
    """Beim ersten Start bleibt alles wie bisher."""

    def test_es_wird_maximiert(self) -> None:
        t = _Traeger()
        t._fenstergeometrie_wiederherstellen()
        self.assertTrue(t.root.maximiert,
                        "Ohne gemerkten Stand muss maximiert werden.")

    def test_die_vorgabegroesse_wird_gesetzt(self) -> None:
        t = _Traeger()
        t._fenstergeometrie_wiederherstellen()
        b, h, _, _ = _masse(t.root.gesetzt[0])
        self.assertEqual((APP.WINDOW_WIDTH, APP.WINDOW_HEIGHT), (b, h))

    def test_unbrauchbarer_text_faellt_auf_die_vorgabe_zurueck(self) -> None:
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "riesig bitte"})
        t._fenstergeometrie_wiederherstellen()
        self.assertTrue(t.root.maximiert)
        b, h, _, _ = _masse(t.root.gesetzt[0])
        self.assertEqual((APP.WINDOW_WIDTH, APP.WINDOW_HEIGHT), (b, h))


class GemerkterStandTests(unittest.TestCase):
    def test_groesse_und_ort_kommen_zurueck(self) -> None:
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "1600x900+120+80"})
        t._fenstergeometrie_wiederherstellen()
        self.assertEqual("1600x900+120+80", t.root.gesetzt[-1])
        self.assertFalse(t.root.maximiert,
                         "Ohne gemerkte Maximierung darf nicht maximiert werden.")

    def test_maximiert_wird_wieder_maximiert(self) -> None:
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "1600x900+120+80",
                      G._MAXIMIERT_SCHLUESSEL: True})
        t._fenstergeometrie_wiederherstellen()
        self.assertTrue(t.root.maximiert)


class SicherungenTests(unittest.TestCase):
    """Die drei Faelle, in denen ein gemerkter Stand nicht gelten darf."""

    def test_zu_klein_wird_angehoben(self) -> None:
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "300x200+0+0"})
        t._fenstergeometrie_wiederherstellen()
        b, h, _, _ = _masse(t.root.gesetzt[-1])
        self.assertGreaterEqual(b, APP.WINDOW_MIN_WIDTH)
        self.assertGreaterEqual(h, APP.WINDOW_MIN_HEIGHT)

    def test_groesser_als_der_schirm_wird_begrenzt(self) -> None:
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "9000x5000+0+0"},
                     schirm=(1920, 1080))
        t._fenstergeometrie_wiederherstellen()
        b, h, _, _ = _masse(t.root.gesetzt[-1])
        self.assertLessEqual(b, 1920)
        self.assertLessEqual(h, 1080)

    def test_ort_ausserhalb_wird_mittig_gesetzt(self) -> None:
        """Der wichtigste Fall: zweiter Bildschirm abgezogen.

        Ohne Korrektur startet das Fenster bei x=3000 auf einem Schirm mit
        1920 Pixeln - unsichtbar, und ohne Mittel es zurueckzuholen.
        """
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "1600x900+3000+200"},
                     schirm=(1920, 1080))
        t._fenstergeometrie_wiederherstellen()
        b, h, x, y = _masse(t.root.gesetzt[-1])
        self.assertLess(x, 1920 - 40, "Das Fenster stuende ausserhalb.")
        self.assertEqual((1920 - b) // 2, x, "Nicht mittig gesetzt.")
        self.assertEqual((1080 - h) // 2, y)

    def test_ein_wenig_ueberstand_bleibt_erlaubt(self) -> None:
        """Wer sein Fenster halb ueber den Rand schiebt, will das so."""
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "1600x900+1500+100"},
                     schirm=(1920, 1080))
        t._fenstergeometrie_wiederherstellen()
        _, _, x, _ = _masse(t.root.gesetzt[-1])
        self.assertEqual(1500, x, "Der Ort wurde unnoetig verschoben.")

    def test_negatives_y_wird_korrigiert(self) -> None:
        """Ueber dem oberen Rand ist die Titelleiste nicht mehr zu fassen."""
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "1600x900+100+-300"},
                     schirm=(1920, 1080))
        t._fenstergeometrie_wiederherstellen()
        _, _, _, y = _masse(t.root.gesetzt[-1])
        self.assertGreaterEqual(y, 0)


class MerkenTests(unittest.TestCase):
    def test_die_groesse_wird_geschrieben(self) -> None:
        t = _Traeger(geometrie="1500x850+60+40")
        t._fenstergeometrie_merken()
        self.assertEqual("1500x850+60+40", t.geschrieben[G._GEOMETRIE_SCHLUESSEL])
        self.assertFalse(t.geschrieben[G._MAXIMIERT_SCHLUESSEL])

    def test_maximiert_ueberschreibt_die_groesse_nicht(self) -> None:
        """Sonst stuende beim naechsten Start die Bildschirmgroesse drin.

        Wer maximiert arbeitet und spaeter verkleinert, soll seine alte
        Groesse wiederfinden - nicht den Vollbildwert.
        """
        t = _Traeger(zustand="zoomed", geometrie="3440x1440+0+0")
        t._fenstergeometrie_merken()
        self.assertTrue(t.geschrieben[G._MAXIMIERT_SCHLUESSEL])
        self.assertNotIn(G._GEOMETRIE_SCHLUESSEL, t.geschrieben,
                         "Die Vollbildgroesse wurde als Startwert gemerkt.")

    def test_ein_fehler_haelt_das_schliessen_nicht_auf(self) -> None:
        class Bockig(_Wurzel):
            def state(self, wert=None):
                raise RuntimeError("kein Fenster mehr")

        t = _Traeger()
        t.root = Bockig()
        t._fenstergeometrie_merken()   # darf nicht werfen
        self.assertEqual({}, t.geschrieben)


class _Ereignis:
    """So viel Ereignis, wie die Verfolgung anfasst."""

    def __init__(self, widget):
        self.widget = widget


class MinimiertTests(unittest.TestCase):
    """Der Fehler, den v1.9.3 und v1.9.4 ausgeliefert haben.

    ``_fenstergeometrie_merken`` fragte ``state() == 'zoomed'``. Ein
    minimiertes Fenster meldet aber ``'iconic'`` - auch wenn es aus dem
    Maximum heraus minimiert wurde. Die Abfrage griff daneben, und dann
    landete genau das in der Datei, was sie ausschliessen soll: die volle
    Bildschirmgroesse als gewoehnliche Geometrie, dazu ``maximiert=False``.

    Am 04.09.2026 gemessen. Ueber die Taskleiste geschlossen passiert es
    **nicht** - Windows stellt vorher wieder her. Erreichbar ist es, wenn
    das ``WM_CLOSE`` beim minimierten Fenster ankommt: Herunterfahren oder
    Abmelden.

    Warum die 21 Pruefungen davor nichts merkten: Keine kannte den Zustand
    ``'iconic'``. Sie pruefte ``normal`` gegen ``zoomed`` - dieselben zwei
    Faelle, die auch der Code kannte.
    """

    def test_aus_dem_maximum_minimiert_bleibt_maximiert(self) -> None:
        """Der eigentliche Fehler: die Bildschirmgroesse darf nicht in die Datei."""
        t = _Traeger(zustand="zoomed", geometrie="3440x1440+-8+-8")
        t._fensterzustand_verfolgen()          # der Stand vor dem Minimieren
        t.root._zustand = "iconic"             # der Anwender minimiert
        t._fenstergeometrie_merken()           # und faehrt den Rechner herunter
        self.assertTrue(t.geschrieben[G._MAXIMIERT_SCHLUESSEL])
        self.assertNotIn(
            G._GEOMETRIE_SCHLUESSEL, t.geschrieben,
            "Die Vollbildgroesse wurde als gewoehnliche Geometrie gemerkt.")

    def test_aus_normaler_groesse_minimiert_merkt_die_groesse(self) -> None:
        """Der gutartige Fall darf nicht mit verlorengehen."""
        t = _Traeger(zustand="normal", geometrie="1040x680+300+180")
        t._fensterzustand_verfolgen()
        t.root._zustand = "iconic"
        t._fenstergeometrie_merken()
        self.assertEqual("1040x680+300+180",
                         t.geschrieben[G._GEOMETRIE_SCHLUESSEL])
        self.assertFalse(t.geschrieben[G._MAXIMIERT_SCHLUESSEL])

    def test_maximiert_verkleinert_minimiert(self) -> None:
        """Der Weg des Anwenders: gross, dann klein gezogen, dann weggeklickt."""
        t = _Traeger(zustand="zoomed", geometrie="3440x1440+-8+-8")
        t._fensterzustand_verfolgen()
        t.root._zustand, t.root._geometrie = "normal", "1200x700+120+80"
        t._fensterzustand_verfolgen()          # das Verkleinern loest ein Configure aus
        t.root._zustand = "iconic"
        t._fenstergeometrie_merken()
        self.assertEqual("1200x700+120+80",
                         t.geschrieben[G._GEOMETRIE_SCHLUESSEL])
        self.assertFalse(t.geschrieben[G._MAXIMIERT_SCHLUESSEL])

    def test_ohne_je_ein_configure_wird_nichts_erfunden(self) -> None:
        """Minimiert geschlossen, bevor je ein Configure kam.

        Dann gibt es keinen verlaesslichen Wert - und lieber gar keine
        Geometrie als eine falsche. Der zuletzt gespeicherte Stand bleibt
        damit stehen.
        """
        t = _Traeger(zustand="iconic", geometrie="3440x1440+-8+-8")
        t._fenstergeometrie_merken()
        self.assertNotIn(G._GEOMETRIE_SCHLUESSEL, t.geschrieben)
        self.assertFalse(t.geschrieben[G._MAXIMIERT_SCHLUESSEL])

    def test_die_verfolgung_ueberspringt_den_minimierten_zustand(self) -> None:
        """Sonst schriebe sie genau den Wert fest, der vermieden werden soll."""
        t = _Traeger(zustand="zoomed", geometrie="3440x1440+-8+-8")
        t._fensterzustand_verfolgen()
        t.root._zustand, t.root._geometrie = "iconic", "3440x1440+-8+-8"
        t._fensterzustand_verfolgen()
        self.assertEqual("zoomed", t._letzter_fensterzustand)

    def test_die_verfolgung_geht_fremde_widgets_nichts_an(self) -> None:
        """Am Hauptfenster haengen Kindflaechen, die ebenfalls Configure melden."""
        t = _Traeger(zustand="zoomed", geometrie="3440x1440+-8+-8")
        t._fensterzustand_verfolgen()
        t.root._zustand, t.root._geometrie = "normal", "800x600+0+0"
        t._fensterzustand_verfolgen(_Ereignis(object()))
        self.assertEqual("zoomed", t._letzter_fensterzustand,
                         "Ein fremdes Configure hat den Stand ueberschrieben.")

    def test_ein_fehler_haelt_die_verfolgung_nicht_auf(self) -> None:
        class Bockig(_Wurzel):
            def state(self, wert=None):
                raise RuntimeError("kein Fenster mehr")

        t = _Traeger()
        t.root = Bockig()
        t._fensterzustand_verfolgen()          # darf nicht werfen
        self.assertEqual("normal", t._letzter_fensterzustand)


class AnbindungTests(unittest.TestCase):
    """Ausgefuehrt statt gelesen waere hier ein ganzes Fenster noetig.

    Deshalb ueber den Syntaxbaum: Beide Methoden muessen an den richtigen
    Stellen gerufen werden, sonst laeuft die Rechnung oben ins Leere.
    """

    QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

    @classmethod
    def setUpClass(cls) -> None:
        import ast

        cls.baum = ast.parse(cls.QUELLE.read_text(encoding="utf-8", errors="replace"))
        cls.ast = ast

    def _methode(self, name):
        """Die Methode **aus PS5ConverterGUI**, nicht die erste im Baum.

        Ein blosses ``ast.walk`` findet das ``__init__`` irgendeiner
        Hilfsklasse weiter oben - die Pruefung liefe dann ins Leere und
        meldete einen Fehler, der keiner ist. Beim Schreiben genau so
        passiert.
        """
        klasse = next(k for k in self.baum.body
                      if isinstance(k, self.ast.ClassDef)
                      and k.name == "PS5ConverterGUI")
        for k in klasse.body:
            if isinstance(k, self.ast.FunctionDef) and k.name == name:
                return k
        self.fail("Methode %s nicht in PS5ConverterGUI gefunden" % name)

    def _ruft(self, methode, name):
        return any(getattr(k.func, "attr", "") == name
                   for k in self.ast.walk(methode) if isinstance(k, self.ast.Call))

    def test_der_aufbau_stellt_wieder_her(self) -> None:
        self.assertTrue(
            self._ruft(self._methode("__init__"), "_fenstergeometrie_wiederherstellen"),
            "Der Aufbau setzt die gemerkte Groesse nicht.")

    def test_das_schliessen_merkt_sich_die_groesse(self) -> None:
        self.assertTrue(
            self._ruft(self._methode("on_closing"), "_fenstergeometrie_merken"),
            "Beim Schliessen wird nichts gemerkt.")

    def test_der_aufbau_maximiert_nicht_mehr_unbedingt(self) -> None:
        """Der alte Zweizeiler darf nicht daneben stehenbleiben."""
        import ast

        aufbau = ast.unparse(self._methode("__init__"))
        self.assertNotIn("'zoomed'", aufbau)
        self.assertNotIn('"zoomed"', aufbau)

    def test_configure_fuehrt_den_fensterzustand_nach(self) -> None:
        self.assertTrue(
            self._ruft(self._methode("_on_root_configure"),
                       "_fensterzustand_verfolgen"),
            "Der letzte nicht minimierte Zustand wird nirgends nachgefuehrt.")

    def test_die_nachfuehrung_steht_vor_dem_fruehen_ausstieg(self) -> None:
        """Sonst laeuft sie bei Anwendern ohne Hintergrundbild nie.

        ``_on_root_configure`` steigt aus, sobald ``_bg_image_cache`` leer
        ist. Alles, was immer laufen muss, gehoert davor - genau wie
        ``_dpi_wechsel_festhalten`` mit derselben Begruendung.
        """
        import ast

        methode = self._methode("_on_root_configure")
        nachfuehrung = ausstieg = None
        for stelle, knoten in enumerate(methode.body):
            if nachfuehrung is None and any(
                    getattr(k.func, "attr", "") == "_fensterzustand_verfolgen"
                    for k in ast.walk(knoten) if isinstance(k, ast.Call)):
                nachfuehrung = stelle
            if ausstieg is None and isinstance(knoten, ast.If) \
                    and "_bg_image_cache" in ast.unparse(knoten.test) \
                    and any(isinstance(k, ast.Return) for k in knoten.body):
                ausstieg = stelle

        self.assertIsNotNone(nachfuehrung, "Nachfuehrung nicht gefunden.")
        self.assertIsNotNone(ausstieg, "Der fruehe Ausstieg ist weg - Test pruefen.")
        self.assertLess(
            nachfuehrung, ausstieg,
            "Die Nachfuehrung steht hinter dem Ausstieg und laeuft damit "
            "nur, wenn ein Hintergrundbild gesetzt ist.")


class ZweiBildschirmeTests(unittest.TestCase):
    """Der Fehler, den v1.9.3 ausgeliefert hat.

    ``winfo_screenwidth()`` meldet nur den **ersten** Bildschirm. Die
    Sichtbarkeitspruefung mass daran - und hielt damit jedes Fenster auf dem
    zweiten Monitor fuer "ausserhalb". Ergebnis: Wer zwei Schirme hat, fand
    sein Fenster bei jedem Start auf dem falschen.

    Bitter daran: Es war die Sicherung gegen den **abgezogenen** zweiten
    Bildschirm, die den haeufigeren Fall zerbrach.

    Und warum die 16 Pruefungen davor nichts merkten: Sie rechneten mit
    **einem** Bildschirm - derselben Annahme wie der Code. Ein Test, der die
    Annahme des Codes teilt, prueft sie nicht.
    """

    #: Zwei Schirme zu je 1920 nebeneinander: Flaeche 3840 breit ab x=0.
    NEBENEINANDER = (0, 0, 3840, 1080)
    #: Der zweite steht **links**: Die Flaeche beginnt bei x=-1920.
    ZWEITER_LINKS = (-1920, 0, 3840, 1080)

    def test_ein_fenster_auf_dem_zweiten_schirm_bleibt_dort(self) -> None:
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "1600x900+2100+100"},
                     schirm=(1920, 1080), flaeche=self.NEBENEINANDER)
        t._fenstergeometrie_wiederherstellen()
        _, _, x, _ = _masse(t.root.gesetzt[-1])
        self.assertEqual(2100, x,
                         "Das Fenster wurde vom zweiten Bildschirm geholt.")

    def test_auch_wenn_der_zweite_links_steht(self) -> None:
        """Dann ist x negativ - und trotzdem voellig in Ordnung."""
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "1600x900+-1800+100"},
                     schirm=(1920, 1080), flaeche=self.ZWEITER_LINKS)
        t._fenstergeometrie_wiederherstellen()
        _, _, x, _ = _masse(t.root.gesetzt[-1])
        self.assertEqual(-1800, x, "Der linke Bildschirm wurde verworfen.")

    def test_abgezogener_zweiter_schirm_holt_es_zurueck(self) -> None:
        """Die Sicherung muss weiterhin greifen.

        Derselbe gemerkte Ort, aber die Flaeche ist nur noch ein Schirm -
        das Fenster stuende im Nichts.
        """
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "1600x900+2100+100"},
                     schirm=(1920, 1080), flaeche=(0, 0, 1920, 1080))
        t._fenstergeometrie_wiederherstellen()
        b, _, x, _ = _masse(t.root.gesetzt[-1])
        self.assertEqual((1920 - b) // 2, x,
                         "Nicht auf den ersten Bildschirm zurueckgeholt.")

    def test_zurueckgeholt_wird_auf_den_ersten_schirm(self) -> None:
        """Nicht in die Mitte der Gesamtflaeche - dort waere es wieder weg."""
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "1600x900+9000+100"},
                     schirm=(1920, 1080), flaeche=self.NEBENEINANDER)
        t._fenstergeometrie_wiederherstellen()
        b, _, x, _ = _masse(t.root.gesetzt[-1])
        self.assertLess(x + b, 1920 + 40,
                        "Landete nicht auf dem ersten Bildschirm.")

    def test_ein_breites_fenster_ueber_beide_schirme_bleibt_breit(self) -> None:
        """Wer sein Fenster ueber beide zieht, will das so."""
        t = _Traeger({G._GEOMETRIE_SCHLUESSEL: "3600x1000+100+40"},
                     schirm=(1920, 1080), flaeche=self.NEBENEINANDER)
        t._fenstergeometrie_wiederherstellen()
        b, _, _, _ = _masse(t.root.gesetzt[-1])
        self.assertEqual(3600, b, "Die Breite wurde auf einen Schirm gestutzt.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
