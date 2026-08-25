# -*- coding: utf-8 -*-
"""Die zwei AMPR-EMU-Knoepfe: Automatik und erklaerte Fragen.

Zwei Zusagen werden hier festgenagelt:

1. Die Knoepfe erledigen alles selbst - das Fenster ist keine Eingabemaske
   mehr, sondern startet seinen Lauf beim Oeffnen.
2. Wo doch entschieden werden muss, steht **zu jeder Moeglichkeit** eine
   Erklaerung. Eine Frage ohne Begruendung waelzt die Entscheidung nur ab,
   statt sie abzunehmen.

Der zweite Punkt laesst sich strukturell pruefen: Zu jedem Fragetext gibt
es einen ``_why``-Text, und jede Antwortmoeglichkeit hat ihren eigenen.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils.i18n import STRINGS
from ps5_validator.utils import shadowmount_generation as sg

QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
    encoding="utf-8")


class KnoepfeTests(unittest.TestCase):
    """Zwei Wege, je einer pro Generation - seit v1.8.98 im Auswahlfenster."""

    def _auswahl(self) -> str:
        """Der Rumpf von ``_show_ampr_auswahl``."""
        anfang = QUELLE.index("    def _show_ampr_auswahl(self)")
        naechste = QUELLE.index(chr(10) + "    def ", anfang + 10)
        return QUELLE[anfang:naechste]

    def test_beide_beschriftungen_gibt_es(self) -> None:
        for schluessel in ("titlebar.ampr_alt", "titlebar.ampr_neu"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)

    def test_beide_stehen_im_auswahlfenster(self) -> None:
        """Seit v1.8.98 fuehrt nur noch Knopf 7 dorthin."""
        rumpf = self._auswahl()
        for methode in ("_show_ampr_alte_methode", "_show_ampr_neue_methode"):
            with self.subTest(methode=methode):
                self.assertIn(methode, rumpf)

    def test_die_titelleiste_hat_sie_nicht_mehr(self) -> None:
        """Sie standen dort provisorisch, bis das Auswahlfenster stand.

        Gegenprobe zum Test darueber: Kaeme einer der Knoepfe zurueck,
        gaebe es zwei Wege zum selben Fenster - und der eine liesse den
        anderen nicht mehr zu, weil beide dasselbe Toplevel bauen.
        """
        anfang = QUELLE.index("_FALTBARE_TITELKNOEPFE")
        block = QUELLE[anfang:QUELLE.index(")", QUELLE.index("(", anfang + 40))]
        self.assertNotIn("ampr", block)
        for attribut in ("_btn_ampr_alt_title", "_btn_ampr_neu_title"):
            with self.subTest(attribut=attribut):
                self.assertNotIn(attribut, QUELLE)

    def test_die_auswahl_geht_ueber_den_umschalter(self) -> None:
        """Sonst oeffnet der zweite Druck ein zweites Fenster.

        ``_show_ampr_generation`` baut jedes Mal ein neues Toplevel. Bis
        v1.8.97 hingen die Titelleisten-Knoepfe am Umschalter und haben das
        abgefangen; seit sie weg sind, muss es das Auswahlfenster tun.
        """
        rumpf = self._auswahl()
        self.assertIn("self._werkzeugfenster_umschalten(methode)", rumpf)
        self.assertNotIn("getattr(self, methode)()", rumpf)

    def test_jeder_knopf_fuehrt_auf_seine_generation(self) -> None:
        for methode, kennung in (("_show_ampr_alte_methode", "sm_gen.ALT"),
                                 ("_show_ampr_neue_methode", "sm_gen.NEU")):
            with self.subTest(methode=methode):
                stelle = QUELLE.index("def %s(self)" % methode)
                rumpf = QUELLE[stelle:stelle + 260]
                self.assertIn("_show_ampr_generation(%s)" % kennung, rumpf)

    def test_die_beschriftungen_nennen_die_methode(self) -> None:
        self.assertIn("alte Methode", STRINGS["titlebar.ampr_alt"]["de"])
        self.assertIn("neue Methode", STRINGS["titlebar.ampr_neu"]["de"])


class AutomatikTests(unittest.TestCase):
    """Das Fenster arbeitet, statt ausgefuellt zu werden."""

    def _fenster(self) -> str:
        anfang = QUELLE.index("def _show_ampr_generation(self, generation: str)")
        ende = QUELLE.index("\n    # ==", anfang)
        return QUELLE[anfang:ende]

    def test_der_lauf_startet_beim_oeffnen(self) -> None:
        self.assertIn("_spaeter_im_fenster(win, _starten)", self._fenster())

    def test_das_fenster_hat_keine_eingabemaske_mehr(self) -> None:
        """Kein Feld fuer Title-ID, Scan-Pfad oder Spielordner."""
        fenster = self._fenster()
        for rest in ("tid_var", "scan_var", "wurzel_var", "ort_var", "lokal_var"):
            with self.subTest(rest=rest):
                self.assertNotIn(rest, fenster)

    def test_der_lauf_geht_in_einen_eigenen_faden(self) -> None:
        """Sonst friert das Fenster waehrend der FTP-Arbeit ein."""
        self.assertIn("threading.Thread(target=_lauf, daemon=True)", self._fenster())

    def test_die_automatik_hat_alle_sechs_schritte(self) -> None:
        for schluessel in ("amprgen.step_console", "amprgen.step_version",
                           "amprgen.step_game", "amprgen.step_target",
                           "amprgen.step_libs", "amprgen.step_config"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertIn(schluessel, QUELLE)

    def test_auf_jede_frage_folgt_ein_ausstieg(self) -> None:
        """Wer abbricht, muss sofort draussen sein - ohne dass etwas passiert.

        Der Dialog liefert bei Abbruch einen leeren Wert zurueck. Wird der
        nicht geprueft, laeuft die Automatik mit einer leeren Antwort
        weiter und legt womoeglich am falschen Ort ab. Deshalb: Hinter
        jedem Aufruf von _ampr_gen_frage muss der Abbruchweg stehen.
        """
        stelle = QUELLE.index("def _ampr_gen_automatik(")
        rumpf = QUELLE[stelle:QUELLE.index(chr(10) + "    def ", stelle + 10)]
        aufrufe = [m.start() for m in re.finditer(r"self\._ampr_gen_frage\(", rumpf)]
        self.assertTrue(aufrufe, "Die Automatik stellt gar keine Frage.")
        for versatz in aufrufe:
            danach = rumpf[versatz:versatz + 1200]
            with self.subTest(zeile=rumpf[:versatz].count(chr(10)) + 1):
                self.assertIn("amprgen.cancelled", danach,
                              "Nach dieser Frage fehlt der Abbruchweg.")
                self.assertIn("return", danach)


class ErklaerteFragenTests(unittest.TestCase):
    """Jede Frage bringt ihre Begruendung mit - und jede Antwort ihre eigene."""

    #: Die Fragen, die die Automatik stellen kann.
    FRAGEN = ("q_offline", "q_wrong_gen", "q_game", "q_playgo",
              "q_config", "q_which_console", "q_save_addr")

    def test_zu_jeder_frage_gibt_es_ein_warum(self) -> None:
        for frage in self.FRAGEN:
            with self.subTest(frage=frage):
                self.assertIn("amprgen.%s" % frage, STRINGS)
                self.assertIn("amprgen.%s_why" % frage, STRINGS,
                              "Frage ohne Begruendung: %s" % frage)

    def test_jede_begruendung_ist_ein_ganzer_satz(self) -> None:
        """Ein Stichwort hilft niemandem bei der Entscheidung."""
        for frage in self.FRAGEN:
            with self.subTest(frage=frage):
                text = STRINGS["amprgen.%s_why" % frage]["de"]
                self.assertGreater(len(text), 90,
                                   "Begruendung zu knapp: %s" % frage)
                self.assertIn(".", text)

    def test_jede_antwortmoeglichkeit_hat_ihre_erklaerung(self) -> None:
        """Im Dialog steht unter jedem Knopf, was er bedeutet."""
        paare = {
            "q_offline": ("local", "stop"),
            "q_wrong_gen": ("stop", "go"),
            "q_playgo": ("no", "yes"),
            "q_config": ("yes", "no"),
            "q_save_addr": ("yes", "no"),
        }
        for frage, antworten in paare.items():
            for antwort in antworten:
                with self.subTest(frage=frage, antwort=antwort):
                    self.assertIn("amprgen.%s_%s" % (frage, antwort), STRINGS)
                    self.assertIn("amprgen.%s_%s_why" % (frage, antwort), STRINGS,
                                  "Antwort ohne Erklaerung: %s_%s"
                                  % (frage, antwort))

    def test_die_spielauswahl_erklaert_jeden_eintrag(self) -> None:
        """Dort ist jede Zeile ein Spiel - die Erklaerung nennt den Pfad."""
        self.assertIn("amprgen.q_game_entry", STRINGS)
        self.assertIn("{path}", STRINGS["amprgen.q_game_entry"]["de"])

    def test_der_dialog_zeigt_erklaerung_und_empfehlung(self) -> None:
        stelle = QUELLE.index("def _ampr_gen_dialog(")
        rumpf = QUELLE[stelle:QUELLE.index("\n    def ", stelle + 10)]
        self.assertIn("erklaerung", rumpf, "Der Dialog zeigt keine Begruendung.")
        self.assertIn("erlaeuterung", rumpf,
                      "Der Dialog zeigt keine Erklaerung je Moeglichkeit.")
        self.assertIn("amprgen.recommended", rumpf,
                      "Die empfohlene Moeglichkeit ist nicht gekennzeichnet.")

    def test_die_erste_moeglichkeit_ist_die_empfohlene(self) -> None:
        """Der Dialog hebt sie hervor - also muss sie vorn stehen."""
        stelle = QUELLE.index("def _ampr_gen_dialog(")
        rumpf = QUELLE[stelle:QUELLE.index("\n    def ", stelle + 10)]
        self.assertIn("if nummer == 0", rumpf)

    def test_alle_texte_sind_zweisprachig(self) -> None:
        for schluessel, werte in STRINGS.items():
            if not schluessel.startswith("amprgen."):
                continue
            with self.subTest(schluessel=schluessel):
                for sprache in ("de", "en"):
                    self.assertTrue(str(werte.get(sprache, "")).strip(),
                                    "%s fehlt in %s" % (schluessel, sprache))


class BausteineTests(unittest.TestCase):
    """Die Teile, die die Automatik selbst entscheiden lassen."""

    @classmethod
    def setUpClass(cls) -> None:
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        cls.GUI = PS5ConverterGUI

    def test_die_title_id_kommt_aus_der_param_json(self) -> None:
        roh = b'{"titleId": "ppsa01234", "titleName": "X"}'
        self.assertEqual(
            self.GUI._ampr_gen_titel_aus_json(self.GUI, roh), "PPSA01234")

    def test_kaputte_param_json_gibt_leer_statt_zu_scheitern(self) -> None:
        for roh in (b"", b"{kein json", b'{"anderes": 1}'):
            with self.subTest(roh=roh):
                self.assertEqual(
                    self.GUI._ampr_gen_titel_aus_json(self.GUI, roh), "")

    def test_gewaehlt_wird_je_bibliothek_die_erste(self) -> None:
        """Der Speicher ist absteigend sortiert - die erste ist die neueste."""
        vorrat = [
            {"lib": "libSceAmpr.sprx", "version": "0.2.8"},
            {"lib": "libSceAmpr.sprx", "version": "0.2.7"},
            {"lib": "libScePlayGo.sprx", "version": "0.5"},
        ]
        gewaehlt = self.GUI._ampr_gen_auswahl_bibliotheken(
            self.GUI, vorrat, False)
        self.assertEqual(len(gewaehlt), 1)
        self.assertEqual(gewaehlt[0]["version"], "0.2.8")

    def test_playgo_kommt_nur_auf_wunsch_mit(self) -> None:
        """Es stammt aus einem anderen Projekt und wird selten gebraucht."""
        vorrat = [{"lib": "libSceAmpr.sprx", "version": "0.2.8"},
                  {"lib": "libScePlayGo.sprx", "version": "0.5"}]
        ohne = self.GUI._ampr_gen_auswahl_bibliotheken(self.GUI, vorrat, False)
        mit = self.GUI._ampr_gen_auswahl_bibliotheken(self.GUI, vorrat, True)
        self.assertEqual([e["lib"] for e in ohne], ["libSceAmpr.sprx"])
        self.assertEqual(len(mit), 2)

    def test_nur_gesetzte_und_abweichende_schluessel_zaehlen(self) -> None:
        """Ein nicht gesetzter Schluessel ist keine Abweichung.

        Am 22.08.2026 an der echten Konsole gemessen: Deren config.ini
        besteht aus 146 Zeilen, die **alle** Kommentar sind - kein
        Schluessel ist gesetzt, ShadowMount+ nimmt seine eingebauten
        Vorgaben. Die erste Fassung meldete daraufhin vier Abweichungen
        und haette den Nutzer eine Datei aendern lassen, an der nichts
        falsch war.
        """
        # Gesetzt und falsch -> echte Abweichung.
        abw = self.GUI._ampr_gen_config_pruefen(
            self.GUI, sg.ALT, "backport_fakelib=0\n")
        self.assertEqual([k for k, _i, _s in abw], ["backport_fakelib"])

        # Gesetzt und richtig -> keine.
        abw = self.GUI._ampr_gen_config_pruefen(
            self.GUI, sg.ALT, "backport_fakelib=1\n")
        self.assertEqual(abw, [])

        # Gar nicht gesetzt -> keine, egal wie viele Schluessel es gibt.
        for generation in (sg.ALT, sg.NEU):
            with self.subTest(generation=generation):
                self.assertEqual(
                    self.GUI._ampr_gen_config_pruefen(self.GUI, generation, ""), [])

    def test_die_reine_kommentardatei_gibt_keine_abweichung(self) -> None:
        """Genau der Fall, der auf der Konsole steht."""
        text = "\n".join([
            "# Sandbox fakelib backport watcher:",
            "# backport_fakelib=1",
            "# global_fakelib=1",
            "# global_fakelib_path=/data/shadowmount/fakelib",
        ])
        self.assertEqual(
            self.GUI._ampr_gen_config_pruefen(self.GUI, sg.ALT, text), [])

    def test_die_vorgaben_werden_trotzdem_benannt(self) -> None:
        """Zur Ansicht: Welche Schluessel laufen auf der Vorgabe?"""
        auf_vorgabe = self.GUI._ampr_gen_config_vorgaben(self.GUI, sg.ALT, "")
        self.assertIn("backport_fakelib", auf_vorgabe)
        gesetzt = self.GUI._ampr_gen_config_vorgaben(
            self.GUI, sg.ALT, "backport_fakelib=1\n")
        self.assertNotIn("backport_fakelib", gesetzt)

    def test_eine_antwort_kann_nicht_ewig_ausbleiben(self) -> None:
        """Sonst haengt der Arbeitsfaden, wenn das Fenster zugeht."""
        self.assertGreater(self.GUI._AMPR_GEN_ANTWORT_GRENZE, 0)
        stelle = QUELLE.index("def _ampr_gen_frage(")
        rumpf = QUELLE[stelle:QUELLE.index("\n    def ", stelle + 10)]
        self.assertIn("_AMPR_GEN_ANTWORT_GRENZE", rumpf)


class _Netzstueck:
    """Traegt nur, was die Adresssuche von "self" braucht.

    Die beiden Methoden greifen intern weiter (auf _get_config_path und
    aufeinander); mit der blossen Klasse als "self" scheitern sie.
    """

    def __init__(self, profil_datei: str = "") -> None:
        self._profil_datei = profil_datei

    def _get_config_path(self) -> str:
        # Der echte Ordner, damit die echte ftp_profiles.json gefunden wird.
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        return self._profil_datei or PS5ConverterGUI._get_config_path(self)

    # _ampr_gen_eigene_netze ruft das hier auf - also muss es dran sein.
    def _ampr_gen_profil_adressen(self):
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        return PS5ConverterGUI._ampr_gen_profil_adressen(self)



class AdresssucheTests(unittest.TestCase):
    """Die Konsole wird gesucht, nicht vorausgesetzt.

    Am 22.08.2026 gemessen: In den Einstellungen stand keine Adresse, und
    das einzige gespeicherte FTP-Profil nannte eine vom Juni, unter der
    nichts mehr antwortete. Ohne Suche waere der Knopf bei jedem Druck an
    Schritt 1 gescheitert.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        cls.GUI = PS5ConverterGUI

    def test_schritt_eins_sucht_die_adresse(self) -> None:
        stelle = QUELLE.index("def _ampr_gen_automatik(")
        rumpf = QUELLE[stelle:QUELLE.index(chr(10) + "    def ", stelle + 10)]
        self.assertIn("_ampr_gen_adresse_finden", rumpf,
                      "Schritt 1 setzt die Adresse wieder voraus.")

    def test_die_reihenfolge_steht_fest(self) -> None:
        """Einstellung, dann Profile, dann Netzsuche - nicht umgekehrt."""
        stelle = QUELLE.index("def _ampr_gen_adresse_finden(")
        rumpf = QUELLE[stelle:QUELLE.index(chr(10) + "    def ", stelle + 10)]
        self.assertLess(rumpf.index("_ps5_ip()"),
                        rumpf.index("_ampr_gen_profil_adressen"))
        self.assertLess(rumpf.index("_ampr_gen_profil_adressen"),
                        rumpf.index("_ampr_gen_netz_absuchen"))

    def test_eine_tote_adresse_haelt_nicht_auf(self) -> None:
        """Steht etwas in den Einstellungen, muss es trotzdem antworten."""
        stelle = QUELLE.index("def _ampr_gen_adresse_finden(")
        rumpf = QUELLE[stelle:QUELLE.index(chr(10) + "    def ", stelle + 10)]
        self.assertIn("_ampr_gen_ist_ps5(eingestellt", rumpf)
        self.assertIn("amprgen.addr_setting_dead", rumpf)

    def test_ein_offener_port_allein_genuegt_nicht(self) -> None:
        """Im Heimnetz horcht auch mal ein Drucker auf dem Port."""
        stelle = QUELLE.index("def _ampr_gen_ist_ps5(")
        rumpf = QUELLE[stelle:QUELLE.index(chr(10) + "    def ", stelle + 10)]
        for pfad in ("/system_data", "/mnt/sandbox", "/user"):
            with self.subTest(pfad=pfad):
                self.assertIn(pfad, rumpf)

    def test_die_netze_kommen_aus_mehreren_quellen(self) -> None:
        """Nur die erste eigene Adresse reicht nicht.

        Auf einem Rechner mit WSL liefert gethostbyname_ex zuerst den
        virtuellen Adapter - hier gemessen 172.25.128.x, waehrend die
        Konsole in 192.168.1.x stand.
        """
        stelle = QUELLE.index("def _ampr_gen_eigene_netze(")
        rumpf = QUELLE[stelle:QUELLE.index(chr(10) + "    def ", stelle + 10)]
        self.assertIn("_ampr_gen_profil_adressen", rumpf,
                      "Die Netze der FTP-Profile werden nicht genutzt.")
        self.assertIn("gethostbyname_ex", rumpf)
        self.assertIn("SOCK_DGRAM", rumpf)

    def test_die_netze_sind_eindeutig_und_ohne_schleife(self) -> None:
        netze = self.GUI._ampr_gen_eigene_netze(_Netzstueck())
        self.assertEqual(len(netze), len(set(netze)), "Netz doppelt genannt.")
        for netz in netze:
            with self.subTest(netz=netz):
                self.assertFalse(netz.startswith("127."))
                self.assertEqual(len(netz.split(".")), 3)

    def test_kaputte_profile_stuerzen_nicht_ab(self) -> None:
        """Die Datei kann fehlen oder Unsinn enthalten."""
        adressen = self.GUI._ampr_gen_profil_adressen(_Netzstueck())
        self.assertIsInstance(adressen, list)

    def test_die_suche_bleibt_schnell(self) -> None:
        """Bei 1 s je Adresse braeuchte ein Netz ueber vier Minuten."""
        self.assertLessEqual(self.GUI._AMPR_GEN_SUCHE_TIMEOUT, 0.5)
        self.assertGreaterEqual(self.GUI._AMPR_GEN_SUCHE_FAEDEN, 16)

    def test_gespeichert_wird_nur_nach_ruecksprache(self) -> None:
        """Eine Einstellung dauerhaft zu aendern ist nichts Nebenbeiges."""
        stelle = QUELLE.index("def _ampr_gen_adresse_merken(")
        rumpf = QUELLE[stelle:QUELLE.index(chr(10) + "    def ", stelle + 10)]
        self.assertIn("_ampr_gen_frage", rumpf)
        self.assertLess(rumpf.index("_ampr_gen_frage"),
                        rumpf.index('_save_setting("ps5_ip"'))



class SpielsucheTests(unittest.TestCase):
    """Spiele werden auf der Konsole selbst gesucht."""

    @classmethod
    def setUpClass(cls) -> None:
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        cls.GUI = PS5ConverterGUI

    def test_der_backports_ordner_zaehlt_nicht_als_spiel(self) -> None:
        stelle = QUELLE.index("def _ampr_gen_spiele_finden(")
        rumpf = QUELLE[stelle:QUELLE.index("\n    def ", stelle + 10)]
        self.assertIn('"backports"', rumpf,
                      "Der backports-Ordner wird nicht uebersprungen.")

    def test_nur_echte_spiele_zaehlen(self) -> None:
        """eboot.bin und sce_sys - dieselbe Pruefung wie beim AMPR-Index."""
        stelle = QUELLE.index("def _ampr_gen_spiele_finden(")
        rumpf = QUELLE[stelle:QUELLE.index("\n    def ", stelle + 10)]
        self.assertIn("_ampr_ftp_validate_app0", rumpf)

    def test_gesucht_wird_in_allen_scan_pfaden(self) -> None:
        pfade = self.GUI._AMPR_GEN_SCANPFADE
        self.assertIn("/data/homebrew", pfade)
        self.assertIn("/mnt/usb0", pfade)
        self.assertIn("/data/etaHEN/games", pfade)


if __name__ == "__main__":
    unittest.main(verbosity=2)
