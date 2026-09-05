# -*- coding: utf-8 -*-
"""Die Vorgaben des Config-Editors stimmen mit der Anleitung ueberein.

``_SHADOWMOUNT_DEFAULTS`` ist keine blosse Anzeige: Baut der Editor die
``config.ini`` neu auf, landen diese Werte auf der Konsole. Zwei davon
stimmten bis v1.9.5 nicht mit der Anleitung ueberein, sondern mit dem
Fremdwerkzeug ``ps5-exfat-builder 4.0.2``, aus dem sie erkennbar stammen::

    Schluessel              hier (bis v1.9.5)   README alpha6/11/12
    lvd_pfs_sector_size     32768               4096 / 4096 / 4096
    md_ufs_sector_size      512                 4096 / 512 legacy / 4096

Gemessen wird gegen die **vorliegenden Anleitungen** im Referenzordner, nicht
gegen eine abgeschriebene Tabelle: Kommt eine neuere Fassung dazu, prueft der
Test von selbst gegen sie.

alpha11 nennt fuer ``md_ufs_sector_size`` zwei Werte ("512 with the legacy UFS
profile, 4096 with the optimized profile"). Der Test verlangt deshalb nur,
dass die eigene Vorgabe in **irgendeiner** vorliegenden Anleitung als Vorgabe
steht - nicht, dass alle Fassungen sich einig sind.
"""
from __future__ import annotations

import io
import re
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("shadowmount_vorgaben")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

REFERENZ = PROJEKT / "PS5 SDK usw"

#: ``- `schluessel=<value>` (default: `4096`; ...)`` - die Form, in der die
#: Anleitung ihre Vorgaben nennt.
_ZEILE = re.compile(
    r"^-\s*`(?P<name>[a-z0-9_]+)=<[^>]*>`\s*\((?P<rest>.*)\)\s*$", re.MULTILINE)
_WERT = re.compile(r"`(\d+)`")


def _anleitungen() -> list[tuple[str, str]]:
    """Alle vorliegenden ShadowMount+-READMEs, neueste zuerst."""
    gefunden: list[tuple[str, str]] = []
    if not REFERENZ.is_dir():
        return gefunden
    for ordner in sorted(REFERENZ.glob("ShadowMountPlus*"), reverse=True):
        for readme in list(ordner.glob("README.md")) + list(ordner.glob("*/README.md")):
            try:
                with io.open(readme, encoding="utf-8", errors="replace") as fh:
                    gefunden.append((ordner.name, fh.read()))
            except OSError:
                continue
            break
    return gefunden


def _vorgaben(text: str) -> dict[str, set[str]]:
    """Zieht ``schluessel -> {genannte Zahlen}`` aus einer Anleitung."""
    raus: dict[str, set[str]] = {}
    for treffer in _ZEILE.finditer(text):
        rest = treffer.group("rest")
        if "default" not in rest:
            continue
        # Nur der Teil vor dem ersten Semikolon: Danach stehen Nebensaetze
        # ("the optimized profile uses a 65536-byte LVD mapping unit"), deren
        # Zahlen keine Vorgaben sind.
        vorne = rest.split(";")[0]
        zahlen = set(_WERT.findall(vorne))
        if zahlen:
            raus.setdefault(treffer.group("name"), set()).update(zahlen)
    return raus


class VorgabenTests(unittest.TestCase):
    """Jede eigene Zahl muss in einer Anleitung stehen."""

    #: Schluessel, die eine Zahl tragen und in der Anleitung vorkommen. Andere
    #: Vorgaben (Pfade, Schalter) prueft dieser Test nicht.
    ZU_PRUEFEN = (
        "lvd_exfat_sector_size",
        "lvd_ufs_sector_size",
        "lvd_pfs_sector_size",
        "md_exfat_sector_size",
        "md_ufs_sector_size",
        "scan_interval_seconds",
        "kstuff_pause_delay_image_seconds",
        "kstuff_pause_delay_direct_seconds",
    )

    @classmethod
    def setUpClass(cls):
        cls.anleitungen = _anleitungen()
        cls.eigene = dict(APP.PS5ConverterGUI._SHADOWMOUNT_DEFAULTS)

    def setUp(self):
        if not self.anleitungen:
            self.skipTest("Keine ShadowMount+-Anleitung im Referenzordner")

    def test_es_liegen_ueberhaupt_anleitungen_vor(self):
        """Ohne diese Zusicherung waere die Datei ein Scheinriese."""
        self.assertGreaterEqual(len(self.anleitungen), 3)
        irgendeine = _vorgaben(self.anleitungen[0][1])
        self.assertIn("lvd_ufs_sector_size", irgendeine,
                      "Die Anleitung wird nicht mehr richtig ausgewertet - "
                      "hat sich ihre Schreibweise geaendert?")

    def test_jede_eigene_zahl_steht_in_einer_anleitung(self):
        abweichend: list[str] = []
        for schluessel in self.ZU_PRUEFEN:
            eigen = self.eigene.get(schluessel)
            if eigen is None:
                continue                  # Vorgabe gibt es hier nicht (mehr)
            genannt: dict[str, set[str]] = {}
            for name, text in self.anleitungen:
                werte = _vorgaben(text).get(schluessel)
                if werte:
                    genannt[name] = werte
            if not genannt:
                continue                  # Schluessel steht in keiner Anleitung
            if not any(eigen in werte for werte in genannt.values()):
                abweichend.append(
                    "%s: hier %r, Anleitungen nennen %s"
                    % (schluessel, eigen,
                       ", ".join("%s=%s" % (n, "/".join(sorted(w)))
                                 for n, w in sorted(genannt.items()))))
        self.assertEqual([], abweichend, "\n".join(abweichend))

    def test_die_beiden_berichtigten_werte_bleiben_berichtigt(self):
        """Namentlich, damit der Ruecksprung auffaellt.

        Beide standen auf den Werten von ps5-exfat-builder 4.0.2 statt auf
        denen der Anleitung.
        """
        self.assertEqual("4096", self.eigene.get("lvd_pfs_sector_size"))
        self.assertEqual("4096", self.eigene.get("md_ufs_sector_size"))


if __name__ == "__main__":
    unittest.main()
