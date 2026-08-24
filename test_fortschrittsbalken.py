# -*- coding: utf-8 -*-
"""Der Fortschrittsbalken: Abschnitte je Datei und keine Rückwärtsbewegung.

Beides wurde am 24.08.2026 an echten Läufen gemessen, indem die Anzeige alle
100 ms abgelesen wurde - nicht abgeleitet, sondern abgelesen. Zwei frühere
Messansätze über einzelne Setzer griffen zu kurz und meldeten Fehler, die
keine waren.

Was gemessen wurde:

* **Sammelkonvertierung sprang zurück.** Bei zwei Dateien lief der Balken je
  Datei von vorn los: 0 -> 99,75 %, dann 0 -> 100 %. Für den Betrachter sieht
  der Sprung auf 0 aus wie ein Neustart. Der interne Rücksetzer ist nötig -
  ohne ihn blockiert der hohe Endstand der Vorgängerdatei jeden kleineren
  Wert -, deshalb geschieht die Zuordnung erst beim Anzeigen.
* **Ein Rest-Rücksprung von 0,05 Punkten** entstand danach beim Abschalten
  der Zuordnung (99,95 -> 99,90). Die Schranke gilt jetzt für jede Aufgabe.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _Attrappe:
    """Trägt genau die Felder, die ``_balken_anzeigewert`` anfasst."""

    def __init__(self, angezeigt=0.0, von=0.0, bis=100.0, zuletzt=0.0):
        self.task_displayed = angezeigt
        self._batch_von = von
        self._batch_bis = bis
        self._zuletzt_angezeigt = zuletzt


class BalkenabschnitteTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def wert(self, attrappe) -> float:
        """Ruft die Methode am Attrappen-Objekt auf.

        Nicht ueber ein Klassenattribut: Eine dort abgelegte Funktion wuerde
        beim Zugriff an den TestCase gebunden und bekaeme diesen als erstes
        Argument.
        """
        return self.haupt.PS5ConverterGUI._balken_anzeigewert(attrappe)

    def test_ohne_sammelkonvertierung_unveraendert(self) -> None:
        """Der Normalfall darf durch die Rechnung nicht berührt werden."""
        for x in (0.0, 12.5, 57.9, 98.0, 100.0):
            with self.subTest(wert=x):
                self.assertAlmostEqual(self.wert(_Attrappe(x)), x, places=6)

    def test_erste_von_zwei_dateien_fuellt_die_erste_haelfte(self) -> None:
        a = _Attrappe(0.0, von=0.0, bis=50.0)
        self.assertAlmostEqual(self.wert(a), 0.0, places=6)
        a.task_displayed = 50.0
        self.assertAlmostEqual(self.wert(a), 25.0, places=6)
        a.task_displayed = 100.0
        self.assertAlmostEqual(self.wert(a), 50.0, places=6)

    def test_zweite_von_zwei_dateien_fuellt_die_zweite_haelfte(self) -> None:
        a = _Attrappe(0.0, von=50.0, bis=100.0, zuletzt=50.0)
        self.assertAlmostEqual(self.wert(a), 50.0, places=6)
        a.task_displayed = 50.0
        self.assertAlmostEqual(self.wert(a), 75.0, places=6)
        a.task_displayed = 100.0
        self.assertAlmostEqual(self.wert(a), 100.0, places=6)

    def test_drei_dateien_teilen_sich_den_balken_zu_dritteln(self) -> None:
        for nr, (von, bis) in enumerate(((0.0, 100 / 3), (100 / 3, 200 / 3),
                                         (200 / 3, 100.0)), start=1):
            with self.subTest(datei=nr):
                a = _Attrappe(100.0, von=von, bis=bis, zuletzt=von)
                self.assertAlmostEqual(self.wert(a), bis, places=6)

    def test_der_balken_geht_nie_zurueck(self) -> None:
        """Der Kern.

        Genau hier entstand der Rest-Rücksprung: Beim Abschalten der
        Zuordnung nach der letzten Datei fiel der sichtbare Wert um 0,05
        Punkte.
        """
        a = _Attrappe(99.90, von=50.0, bis=100.0, zuletzt=0.0)
        hoch = self.wert(a)                      # 99,95
        a._batch_von, a._batch_bis = 0.0, 100.0  # Zuordnung abgeschaltet
        a.task_displayed = 99.90
        self.assertGreaterEqual(self.wert(a), hoch)

    def test_die_schranke_gilt_in_jeder_aufgabe(self) -> None:
        """Nicht nur in der Sammelkonvertierung - rückwärts ist immer falsch."""
        a = _Attrappe(80.0)
        self.assertAlmostEqual(self.wert(a), 80.0, places=6)
        a.task_displayed = 30.0
        self.assertAlmostEqual(self.wert(a), 80.0, places=6)

    def test_fehlende_felder_werfen_nicht(self) -> None:
        """Die Anzeige darf an keiner Stelle eine Ausnahme auslösen."""
        class Leer:
            pass
        leer = Leer()
        self.assertEqual(self.wert(leer), 0.0)


class RuecksetzungTests(unittest.TestCase):
    """Eine neue Aufgabe beginnt bei null - sonst wirkt die Schranke fort."""

    def test_die_ruecksetzung_loescht_schranke_und_abschnitt(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn("self._zuletzt_angezeigt = 0.0", quelle)
        self.assertIn("self._batch_von, self._batch_bis = 0.0, 100.0", quelle)

    def test_die_sammelkonvertierung_setzt_die_abschnitte(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn("self._batch_von = (idx - 1) * 100.0 / len(sources)", quelle)
        self.assertIn("self._batch_bis = idx * 100.0 / len(sources)", quelle)


class StillstandsUhrTests(unittest.TestCase):
    """Bei langen Prüfphasen läuft die Zeit mit, statt dass alles stillsteht.

    Gemessen am 24.08.2026 ohne Fremdlast: 20,2 s ohne jede Änderung bei
    "Abschlussprüfung läuft..." und 95 %, 12,6 s bei "Verarbeitung laeuft..."
    und 57,9 %. Bei einem 100-GB-Dump sind das Minuten. Nach dem Einbau lag
    der größte Stillstand bei 5,1 s - der Wartezeit, bevor die Uhr einsetzt.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    class _Label:
        def __init__(self, text=""):
            self._text = text
        def cget(self, _was):
            return self._text
        def config(self, text=None, **_k):
            if text is not None:
                self._text = text

    def _app(self, text, wert=50.0, seit=0.0):
        class App:
            pass
        a = App()
        a.status_label = self._Label(text)
        a._uhr_basis = text
        a._uhr_letzter_wert = wert
        a._uhr_seit = seit
        a._STILLSTAND_UHR_AB_S = self.haupt.PS5ConverterGUI._STILLSTAND_UHR_AB_S
        return a

    def _uhr(self, app, wert):
        return self.haupt.PS5ConverterGUI._stillstand_uhr(app, wert)

    def test_kurze_pausen_bleiben_unberuehrt(self) -> None:
        """Sonst würde die Zeile bei jedem Takt flackern."""
        import time as _t
        a = self._app("Phase 2/4 – Verarbeitung laeuft ...", seit=_t.monotonic() - 2.0)
        self._uhr(a, 50.0)
        self.assertEqual(a.status_label.cget("text"), "Phase 2/4 – Verarbeitung laeuft ...")

    def test_nach_der_wartezeit_laeuft_die_uhr(self) -> None:
        import time as _t
        a = self._app("Phase 3/4 – Abschlussprüfung läuft...", seit=_t.monotonic() - 19.0)
        self._uhr(a, 50.0)
        self.assertIn("(0:19)", a.status_label.cget("text"))
        self.assertTrue(a.status_label.cget("text").startswith("Phase 3/4"))

    def test_die_uhr_haengt_sich_nicht_mehrfach_an(self) -> None:
        """Der Kern: Die eigene Ergänzung wird vor dem Neuanhängen abgetrennt."""
        import time as _t
        a = self._app("Prüfung läuft...", seit=_t.monotonic() - 12.0)
        for _ in range(5):
            self._uhr(a, 50.0)
        text = a.status_label.cget("text")
        self.assertEqual(text.count("("), 1, text)

    def test_bewegung_setzt_die_uhr_zurueck(self) -> None:
        import time as _t
        a = self._app("Phase 2/4 – laeuft", seit=_t.monotonic() - 30.0)
        self._uhr(a, 61.0)                      # Balken hat sich bewegt
        self.assertNotIn("(", a.status_label.cget("text"))

    def test_neuer_text_setzt_die_uhr_zurueck(self) -> None:
        import time as _t
        a = self._app("Phase 2/4 – laeuft", seit=_t.monotonic() - 30.0)
        a.status_label.config(text="Phase 3/4 – etwas anderes")
        self._uhr(a, 50.0)
        self.assertNotIn("(", a.status_label.cget("text"))

    def test_ohne_statuszeile_keine_ausnahme(self) -> None:
        class Ohne:
            pass
        self._uhr(Ohne(), 50.0)                 # darf nicht werfen

    def test_minuten_werden_gezeigt(self) -> None:
        import time as _t
        a = self._app("Abschlussprüfung läuft...", seit=_t.monotonic() - 125.0)
        self._uhr(a, 50.0)
        self.assertIn("(2:05)", a.status_label.cget("text"))


class FortschrittsWaechterTests(unittest.TestCase):
    """Der Wächter im Diagnosebericht.

    Er misst während jeder Aufgabe mit, was die Anzeige wirklich zeigt, und
    hält das Ergebnis für den Bericht fest. So fällt eine kaputte Anzeige
    auch auf Rechnern auf, an denen niemand eine Messreihe fährt.

    Die Prüfungen hier stellen die beiden echten Fehler vom 24.08.2026 nach.
    Ein Wächter, der sie nicht findet, ist wertlos.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def _neu(self):
        return self.haupt.FortschrittsWaechter()

    def _lauf(self, punkte):
        """punkte: Liste aus (zeit, balken, prozenttext, statustext)."""
        w = self._neu()
        for t, b, p, s in punkte:
            w.beobachte(b, p, s, jetzt=t)
        return w

    # ── Der gesunde Fall ────────────────────────────────────────────────
    def test_ein_sauberer_lauf_meldet_nichts(self) -> None:
        punkte = [(i * 0.1, i * 2.0, "%d%%" % (i * 2), "Phase %d/4 – laeuft" % (1 + i // 13))
                  for i in range(51)]
        w = self._lauf(punkte)
        w.abschliessen(100.0)
        self.assertEqual(w.befunde(), [])

    # ── Die beiden echten Fehler von damals ─────────────────────────────
    def test_findet_den_festgenagelten_phasenzaehler(self) -> None:
        """Der exFAT-Weg zeigte von Anfang bis Ende nur Phase 2 von 4."""
        punkte = [(i * 0.1, i * 2.0, "%d%%" % (i * 2), "Phase 2/4 – exFAT-Image erstellt")
                  for i in range(51)]
        w = self._lauf(punkte)
        w.abschliessen(100.0)
        text = " | ".join(w.befunde())
        self.assertIn("Phasen nie angezeigt", text)
        self.assertIn("1, 3, 4", text)

    def test_findet_die_eingefrorene_zahl(self) -> None:
        """6.0 KB blieben stehen, während der Balken von 2 auf 98 lief."""
        punkte = [(i * 0.2, i * 2.0, "%d%%" % (i * 2),
                   "Phase 2/4 – exFAT-Image erstellt... 6.0 KB/252.4 MB")
                  for i in range(51)]
        w = self._lauf(punkte)
        self.assertTrue(any("stand fest" in b for b in w.befunde()), w.befunde())

    def test_eine_mitlaufende_zahl_ist_kein_befund(self) -> None:
        """Die Gegenprobe - sonst meldet der Wächter jeden gesunden Lauf."""
        punkte = [(i * 0.2, i * 2.0, "%d%%" % (i * 2),
                   "Phase %d/4 – erstellt... %d.0 MB/252.4 MB" % (1 + i // 13, i))
                  for i in range(51)]
        w = self._lauf(punkte)
        w.abschliessen(100.0)
        self.assertEqual(w.befunde(), [])

    # ── Die übrigen Eigenschaften ───────────────────────────────────────
    def test_findet_den_ruecksprung(self) -> None:
        punkte = [(0.1, 10.0, "10%", "Phase 1/1 – x"), (0.2, 60.0, "60%", "Phase 1/1 – x"),
                  (0.3, 20.0, "20%", "Phase 1/1 – x"), (0.4, 70.0, "70%", "Phase 1/1 – x")]
        self.assertTrue(any("zurueck" in b for b in self._lauf(punkte).befunde()))

    def test_findet_den_ueberlauf(self) -> None:
        punkte = [(i * 0.1, 90.0 + i * 5, "x", "Phase 1/1 – x") for i in range(5)]
        self.assertTrue(any("ueber 100" in b for b in self._lauf(punkte).befunde()))

    def test_findet_auseinanderlaufende_zahlen(self) -> None:
        punkte = [(i * 0.1, float(i * 10), "%d%%" % (i * 5), "Phase 1/1 – x")
                  for i in range(11)]
        self.assertTrue(any("auseinander" in b for b in self._lauf(punkte).befunde()))

    def test_findet_den_stillstand(self) -> None:
        punkte = [(0.1, 50.0, "50%", "Phase 1/1 – x"), (0.2, 50.0, "50%", "Phase 1/1 – x"),
                  (60.0, 50.0, "50%", "Phase 1/1 – x"), (60.1, 60.0, "60%", "Phase 1/1 – x")]
        self.assertTrue(any("still" in b for b in self._lauf(punkte).befunde()))

    def test_endwert_wird_nur_nach_abschluss_bewertet(self) -> None:
        """Sonst meldete jeder Kommandozeilenlauf einen zu kleinen Endwert.

        Der Taktgeber hört auf, bevor der Abschluss die 100 schreibt - er
        kann sie also nie sehen. Erst ``abschliessen`` weiß es besser.
        """
        punkte = [(i * 0.1, float(i), "%d%%" % i, "Phase 1/1 – x") for i in range(99)]
        w = self._lauf(punkte)
        self.assertFalse(any("endete bei" in b for b in w.befunde()))
        w.abschliessen()                       # ohne Endwert
        self.assertTrue(any("endete bei" in b for b in w.befunde()))

    def test_der_abschluss_nimmt_den_endwert_an(self) -> None:
        punkte = [(i * 0.1, float(i), "%d%%" % i, "Phase 1/1 – x") for i in range(99)]
        w = self._lauf(punkte)
        w.abschliessen(100.0)
        self.assertFalse(any("endete bei" in b for b in w.befunde()))

    # ── Robustheit ──────────────────────────────────────────────────────
    def test_unsinn_wirft_nicht(self) -> None:
        """Eine Messung, die den gemessenen Vorgang stört, wäre schlimmer
        als keine."""
        w = self._neu()
        for schrott in (None, "abc", float("nan")):
            w.beobachte(schrott, None, None)
        w.beobachte(50.0, None, None)
        w.abschliessen("unsinn")
        self.assertIsInstance(w.befunde(), list)

    def test_zu_wenige_punkte_ergeben_keinen_befund(self) -> None:
        """Ein Programmstart ohne Aufgabe darf nichts melden."""
        w = self._lauf([(0.1, 0.0, "", "")])
        self.assertEqual(w.befunde(), [])
        self.assertIn("nichts gemessen", " ".join(w.bericht()))

    def test_zuruecksetzen_loescht_alles(self) -> None:
        punkte = [(0.1, 10.0, "10%", "Phase 1/1 – x"), (0.2, 5.0, "5%", "Phase 1/1 – x"),
                  (0.3, 50.0, "50%", "Phase 1/1 – x")]
        w = self._lauf(punkte)
        self.assertTrue(w.befunde())
        w.zuruecksetzen()
        self.assertEqual(w.n, 0)
        self.assertEqual(w.befunde(), [])

    # ── Der Bericht ─────────────────────────────────────────────────────
    def test_der_bericht_nennt_den_phasenweg(self) -> None:
        punkte = [(i * 0.1, i * 2.0, "%d%%" % (i * 2), "Phase %d/3 – x" % (1 + i // 17))
                  for i in range(51)]
        w = self._lauf(punkte)
        w.abschliessen(100.0)
        bericht = " ".join(w.bericht())
        self.assertIn("1/3 -> 2/3 -> 3/3", bericht)
        self.assertIn("keine Auffaelligkeit", bericht)

    def test_der_bericht_zaehlt_die_befunde(self) -> None:
        punkte = [(0.1, 10.0, "10%", "Phase 1/1 – x"), (0.2, 5.0, "5%", "Phase 1/1 – x"),
                  (0.3, 50.0, "50%", "Phase 1/1 – x")]
        self.assertIn("Auffaelligkeit(en)", " ".join(self._lauf(punkte).bericht()))


class WaechterImProgrammTests(unittest.TestCase):
    """Der Wächter muss auch wirklich angeschlossen sein."""

    def test_der_bericht_hat_einen_abschnitt(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn("diagnostics.report_section_progress", quelle)
        self.assertIn("def _diagnose_fortschritt", quelle)

    def test_gemessen_wird_am_anfang_des_takts(self) -> None:
        """Nicht danach.

        ``_set_progress`` reicht die Werte über ``root.after(0, ...)``
        weiter. Wer unmittelbar nach dem Setzen abliest, bekommt die Werte
        des vorigen Takts - gemessen als vermeintliche Abweichung von 7,3
        Punkten, die es nie gab.
        """
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("def _update_progress_gui")
        kopf = quelle[anfang:anfang + 1200]
        self.assertIn("fortschritts_waechter.beobachte", kopf)

    def test_der_abschluss_meldet_den_endwert(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn("fortschritts_waechter.abschliessen(100.0)", quelle)

    def test_die_uebersetzung_gibt_es_zweisprachig(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        eintrag = STRINGS["diagnostics.report_section_progress"]
        self.assertIn("de", eintrag)
        self.assertIn("en", eintrag)


if __name__ == "__main__":
    unittest.main(verbosity=2)
