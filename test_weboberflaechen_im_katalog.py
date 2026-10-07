# -*- coding: utf-8 -*-
"""Jede mitgelieferte ELF mit eingebauter Weboberflaeche steht in "Konsole & Payloads" (seit 05.10.2026).

Auftrag des Nutzers: "Was eine Weboberflaeche besitzt von den ELFs, die ich in den
helloworld Ordner lege, soll bitte auch bei Konsole & Payloads angezeigt werden wie die
anderen Payloads."

Gelesen wird jede ELF in ``helloworld/`` nach einer eingebetteten HTML-Seite
(``<!DOCTYPE html``; die Fehlerseiten von libmicrohttpd beginnen mit ``<html>`` und zaehlen
nicht - sie stecken in jedem ELF, das den Webserver mitbringt). Trifft ein Katalogeintrag die
Datei - ``payload_muster`` (wird gestartet) oder ``datei_muster`` (nur Anzeige der Version) -,
ist sie abgedeckt. Sonst muss sie in ``AUSNAHMEN`` stehen, mit Grund.

Ein neues ELF mit Weboberflaeche faellt hier auf, bevor es unbemerkt ohne Zeile bleibt:
Port und Pfad aus der Beschreibung des Autors oder aus dem ELF ermitteln, Eintrag in
``konsole_dienste.KATALOG``, zwei Texte (``dienst.<name>``, ``dienst.<name>_zweck``) in i18n.
Das Skript ``weboberflaechen_pruefen.py`` des Projekt-Skills zeigt Kandidaten samt Ports.
"""
from __future__ import annotations

import fnmatch
import re
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import konsole_dienste as kd      # noqa: E402

#: Eine vollstaendige eingebettete Seite - nicht die Fehlerseiten von libmicrohttpd.
HTML_SEITE = re.compile(rb"<!doctype html", re.IGNORECASE)
#: Zweites Merkmal (seit 07.10.2026): die Startadresse einer Medien-App der Konsole, die auf eine
#: eigene Seite des Payloads zeigt. Der WK Autoloader 1.0.16 traegt seine Seiten nicht als Klartext
#: (kein "<!DOCTYPE html"), aber ``"deeplinkUri": "http://127.0.0.1:1022/app/index.html"`` - mit dem
#: ersten Merkmal allein blieb er ohne Zeile, obwohl er eine Weboberflaeche hat.
STARTADRESSE = re.compile(rb'"deeplinkUri"\s*:\s*"http://127\.0\.0\.1:\d+')

#: Dateimuster -> Grund, warum die ELF keine eigene Zeile hat, obwohl sie eine Seite traegt.
AUSNAHMEN: dict[str, str] = {
    "ps5-unified-autoloader-v*.elf": (
        "bringt bei Bedarf den Payload Manager mit - dessen Weboberflaeche steht unter 8084 "
        "in der Zeile \"Payload-Manager\""),
    # Seit 07.10.2026 (zweites Merkmal "deeplinkUri"): Der Installer startet beim Senden einen
    # eigenen Server (Port 18181, "/app/index.html"), dessen Seite der Jailbreak-Host fuer den
    # Browser der Konsole ist (Medien-App).
    "webkit-autoloader-installer_v*.elf": (
        "hat eine eigene Seite in der Ansicht KONSOLE (Knopf \"WebKit Autoloader\" mit "
        "Fassungswahl), die ihn sendet; seine Seite auf 18181 ist der Jailbreak-Host fuer den "
        "Browser der Konsole"),
}


def _abgedeckt(name: str) -> bool:
    for eintrag in kd.KATALOG:
        for muster in (eintrag.payload_muster, eintrag.datei_muster):
            if muster and fnmatch.fnmatch(name, muster):
                return True
    return False


def _ausnahme(name: str) -> str:
    for muster, grund in AUSNAHMEN.items():
        if fnmatch.fnmatch(name, muster):
            return grund
    return ""


def _hat_seite(datei: Path) -> bool:
    daten = datei.read_bytes()
    return bool(HTML_SEITE.search(daten) or STARTADRESSE.search(daten))


class WeboberflaechenImKatalogTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.elfs = sorted((PROJEKT / "helloworld").glob("*.elf"), key=lambda p: p.name.lower())

    def test_es_gibt_ueberhaupt_elfs_zu_pruefen(self) -> None:
        self.assertGreater(len(self.elfs), 30)

    def test_jede_elf_mit_weboberflaeche_hat_eine_zeile(self) -> None:
        offen = [d.name for d in self.elfs
                 if not _abgedeckt(d.name) and not _ausnahme(d.name) and _hat_seite(d)]
        self.assertEqual(
            [], offen,
            "Diese ELFs in helloworld/ tragen eine Weboberflaeche, stehen aber nicht in "
            "\"Konsole & Payloads\" (Auftrag des Nutzers vom 05.10.2026): %s.\n"
            "Port und Pfad aus der Beschreibung des Autors oder dem ELF ermitteln, dann in "
            "konsole_dienste.KATALOG eintragen (payload_muster = startbar, datei_muster = nur "
            "Versionsanzeige) und die beiden Texte in i18n ergaenzen. Kommt die Seite nur "
            "auf der Konsole selbst vor (127.0.0.1) oder gehoert sie zu einer anderen Zeile, "
            "gehoert die Datei samt Grund in AUSNAHMEN." % ", ".join(offen))

    def test_die_ausnahmen_sind_nicht_veraltet(self) -> None:
        """Ein Eintrag fuer eine Datei, die es nicht mehr gibt - oder die inzwischen eine
        Zeile hat -, deckt spaeter versehentlich einen echten Fall mit."""
        for muster in AUSNAHMEN:
            with self.subTest(muster=muster):
                dateien = [d for d in self.elfs if fnmatch.fnmatch(d.name, muster)]
                self.assertTrue(dateien, "Zu %s liegt keine Datei mehr bei." % muster)
                for datei in dateien:
                    self.assertFalse(_abgedeckt(datei.name),
                                     "%s hat inzwischen eine Zeile - Ausnahme streichen." % datei.name)
                    self.assertTrue(_hat_seite(datei),
                                    "%s traegt keine Seite mehr - Ausnahme streichen." % datei.name)

    def test_ohne_zeile_wuerde_dpiv2_auffallen(self) -> None:
        """Gegenprobe zur Pruefung oben: Fehlte die Zeile von DPI v2, stuende die Datei in der
        Liste der Offenen - der Fall, der am 05.10.2026 den Auftrag ausgeloest hat."""
        from unittest import mock
        ohne = tuple(d for d in kd.KATALOG if d.schluessel != "dpiv2")
        self.assertEqual(len(kd.KATALOG) - 1, len(ohne))
        with mock.patch.object(kd, "KATALOG", ohne):
            offen = [d.name for d in self.elfs
                     if not _abgedeckt(d.name) and not _ausnahme(d.name) and _hat_seite(d)]
        self.assertEqual(["dpiv2-13.60-1.00.elf"], offen)

    def test_ohne_zeile_wuerde_der_wk_autoloader_auffallen(self) -> None:
        """Gegenprobe zum zweiten Merkmal: Der WK Autoloader (1.0.16) hat keine Klartextseite, aber
        eine Startadresse - ohne seine Zeile muss er in der Liste der Offenen stehen."""
        from unittest import mock
        ohne = tuple(d for d in kd.KATALOG if d.schluessel != "wkautoloader")
        self.assertEqual(len(kd.KATALOG) - 1, len(ohne))
        wk = [d for d in self.elfs if fnmatch.fnmatch(d.name, "WK-AutoLoader_v*.elf")]
        self.assertTrue(wk)
        self.assertFalse(HTML_SEITE.search(wk[-1].read_bytes()), "Anker: ohne Klartextseite")
        with mock.patch.object(kd, "KATALOG", ohne):
            offen = [d.name for d in self.elfs
                     if not _abgedeckt(d.name) and not _ausnahme(d.name) and _hat_seite(d)]
        self.assertEqual([wk[-1].name], offen)

    def test_die_erkennung_findet_die_bekannten_seiten(self) -> None:
        """Gegenprobe - sonst bestuende die Pruefung oben mit einem blinden Leser."""
        for name in ("pldmgr_v*.elf", "aria2-v*.elf", "dpiv2-*.elf", "shadowmountplus_v*.elf"):
            with self.subTest(muster=name):
                dateien = [d for d in self.elfs if fnmatch.fnmatch(d.name, name)]
                self.assertTrue(dateien, "keine Datei zu %s" % name)
                self.assertTrue(_hat_seite(dateien[-1]), dateien[-1].name)
        # Und eine ohne Seite: der ELF-Loader hat keine Weboberflaeche.
        loader = [d for d in self.elfs if fnmatch.fnmatch(d.name, "elfldr*.elf")]
        self.assertTrue(loader)
        self.assertFalse(_hat_seite(loader[-1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
