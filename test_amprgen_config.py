# -*- coding: utf-8 -*-
"""Der AMPR-Automatiklauf darf die config.ini der Konsole nicht ausraeumen.

**Was schiefging.** Schritt 6 des Laufs vergleicht die ``config.ini`` von
ShadowMount+ gegen das Generationsprofil und bietet an, die Abweichungen
zu setzen. Zurueckgeschrieben wurde bis zum 05.09.2026 mit genau diesen
Abweichungen als Woerterbuch - und ``merge_flat_ini`` kommentiert jede
aktive Zeile aus, deren Schluessel nicht im Woerterbuch steht. Das ist im
Editor richtig (dort steht die ganze Datei drin), hier war es Datenverlust
auf der Konsole: Aus sechs gesetzten Einstellungen wurden sechs
auskommentierte, samt Suchpfaden und Einhaengepunkt.

**Warum es niemandem auffiel.** Die Datei kam nicht kuerzer zurueck, nur
wirkungslos - jede Zeile stand noch da, mit einem ``#`` davor. Und der
Schritt laeuft nur, wenn der Anwender die Rueckfrage mit "ja" beantwortet
und die Konsole ueberhaupt abweicht.

Der Befund stammt aus dem Abgleich mit der zweiten Arbeitskopie, ist aber
gegen diesen Quelltext gemessen worden, nicht abgeschrieben.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("amprgen_config")

from ps5_validator.utils.ini_config import (                # noqa: E402
    parse_flat_ini,
    parse_flat_ini_multi,
)
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


#: Nachgebaut nach der Vorlage auf der Konsole: ein erklaerender Kopf,
#: auskommentierte Beispiele, ein mehrfacher Schluessel und ein paar
#: aktive Einstellungen, die der Anwender selbst gesetzt hat.
VORLAGE = """# ShadowMount+ config.ini
# scanpath=<absolute_path>   (wiederholbar)
# api_bind_address=0.0.0.0

scanpath=/mnt/usb0
scanpath=/data/games
ftp_port=2121
mount_point=/mnt/sandbox
global_fakelib=1
"""


class _FtpNachbau:
    """Nimmt das Zurueckgeschriebene entgegen, statt es zu senden."""

    def __init__(self) -> None:
        self.geschrieben: dict[str, bytes] = {}

    def storbinary(self, befehl: str, strom) -> None:
        self.geschrieben[befehl.split(" ", 1)[1]] = strom.read()


def _zurueckgeschrieben(aenderungen: dict[str, str],
                        vorlage: str = VORLAGE) -> str:
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    ftp = _FtpNachbau()
    gui._ampr_gen_config_schreiben(ftp, vorlage, aenderungen)
    return list(ftp.geschrieben.values())[0].decode("utf-8")


class BestandTests(unittest.TestCase):
    """Was der Anwender gesetzt hat, muss gesetzt bleiben."""

    def test_die_abweichung_wird_gesetzt(self):
        # Die eigentliche Aufgabe - ohne sie sagte der Rest nichts aus.
        neu = _zurueckgeschrieben({"backport_fakelib": "1"})
        self.assertIn("backport_fakelib=1", neu)

    def test_keine_bestehende_einstellung_wird_abgeschaltet(self):
        # Nicht ueber Zeichenkettensuche: "ftp_port=2121" steht auch in
        # "# ftp_port=2121" drin. Gefragt ist, was der Leser danach sieht.
        neu = _zurueckgeschrieben({"backport_fakelib": "1"})
        werte = parse_flat_ini(neu)
        for schluessel, wert in parse_flat_ini(VORLAGE).items():
            self.assertEqual(wert, werte.get(schluessel),
                             "%s ging verloren" % schluessel)

    def test_der_mehrfache_schluessel_behaelt_alle_zeilen(self):
        neu = _zurueckgeschrieben({"backport_fakelib": "1"})
        self.assertEqual(["/mnt/usb0", "/data/games"],
                         parse_flat_ini_multi(neu)["scanpath"])

    def test_auskommentiertes_bleibt_auskommentiert(self):
        # Der Bestand darf nicht dazu fuehren, dass Vorlagenzeilen
        # ploetzlich aktiv werden.
        neu = _zurueckgeschrieben({"backport_fakelib": "1"})
        self.assertNotIn("api_bind_address", parse_flat_ini(neu))

    def test_eine_abweichung_sticht_den_bestand(self):
        neu = _zurueckgeschrieben({"ftp_port": "2121", "global_fakelib": "0"})
        self.assertEqual("0", parse_flat_ini(neu)["global_fakelib"])

    def test_der_erklaerende_kopf_bleibt_stehen(self):
        neu = _zurueckgeschrieben({"backport_fakelib": "1"})
        self.assertIn("# ShadowMount+ config.ini", neu)

    def test_leere_vorlage_stuerzt_nicht_ab(self):
        # Auf einer frischen Konsole gibt es die Datei noch gar nicht.
        neu = _zurueckgeschrieben({"backport_fakelib": "1"}, vorlage="")
        self.assertEqual("1", parse_flat_ini(neu)["backport_fakelib"])


class AufrufTests(unittest.TestCase):
    """Der Lauf gibt wirklich nur die Abweichungen weiter.

    Das ist die Vorbedingung des Fehlers: Stuende dort schon der ganze
    Bestand, waere im Schreiber nichts zu tun. Faellt der Aufruf einmal
    anders aus, soll dieser Test es sagen und nicht stumm gruen bleiben.
    """

    def test_der_lauf_uebergibt_nur_die_abweichungen(self):
        with io.open(APP.__file__, "rb") as fh:
            quelle = fh.read().decode("utf-8")
        self.assertIn("{k: soll for k, _ist, soll in abweichungen}", quelle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
