# -*- coding: utf-8 -*-
"""y2jb_updater: reine Logik fuer den Y2JB Updater (Konsole-Knopf 12, 18.10.2026)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("y2jb_updater")

from ps5_validator.utils import y2jb_updater as yu          # noqa: E402
from ps5_validator.utils.werkzeug_updates import Anhang, Freigabe  # noqa: E402


class ZielIdTests(unittest.TestCase):
    def test_bekannte_titel_ids_sind_gueltig(self) -> None:
        for ziel_id in yu.ZIEL_IDS:
            with self.subTest(ziel_id=ziel_id):
                self.assertTrue(yu.ziel_id_gueltig(ziel_id))

    def test_kleinschreibung_und_leerraum_werden_toleriert(self) -> None:
        self.assertTrue(yu.ziel_id_gueltig(" ppsa01650 "))

    def test_falsche_laenge_oder_zeichen_sind_ungueltig(self) -> None:
        for ziel_id in ("", "PPSA0165", "PPSA016500", "../../etc", "PPSA-1650", "   "):
            with self.subTest(ziel_id=ziel_id):
                self.assertFalse(yu.ziel_id_gueltig(ziel_id))

    def test_pfad_baut_sich_aus_einer_gueltigen_id(self) -> None:
        self.assertEqual("/user/download/PPSA01650", yu.ziel_pfad("PPSA01650"))
        self.assertEqual("/user/download/PPSA01651", yu.ziel_pfad(" ppsa01651 "))

    def test_pfad_bleibt_leer_bei_einer_ungueltigen_id(self) -> None:
        self.assertEqual("", yu.ziel_pfad(""))
        self.assertEqual("", yu.ziel_pfad("../../etc/passwd"))

    def test_standard_ist_die_erste_bekannte_id(self) -> None:
        self.assertEqual(yu.ZIEL_IDS[0], yu.ZIEL_STANDARD)


class AngeboteTests(unittest.TestCase):
    def _anhang(self, name: str, adresse: str = "https://github.com/x/y/releases/download/v1/" ) -> Anhang:
        return Anhang(name=name, groesse=336789504, digest="sha256:abc", adresse=adresse + name)

    def test_nur_freigaben_mit_download0_dat_kommen_durch(self) -> None:
        mit = Freigabe(tag="v1.0.2", datum="2026-10-14", anhaenge=(self._anhang("download0.dat"),
                                                                   self._anhang("y2jb_update.zip")))
        ohne = Freigabe(tag="v0.1", datum="2025-11-12", anhaenge=(self._anhang("y2jb_update.zip"),))
        erg = yu.angebote([mit, ohne])
        self.assertEqual([(mit, mit.anhaenge[0])], erg)

    def test_entwuerfe_fallen_heraus(self) -> None:
        entwurf = Freigabe(tag="v1.0.3-dev", entwurf=True, anhaenge=(self._anhang("download0.dat"),))
        self.assertEqual([], yu.angebote([entwurf]))

    def test_vorabfassungen_bleiben_drin(self) -> None:
        """Vorab (pre-release) ist etwas anderes als Entwurf (draft, noch unveroeffentlicht)."""
        vorab = Freigabe(tag="v1.0.0-dev-fb17d16", vorab=True, anhaenge=(self._anhang("download0.dat"),))
        self.assertEqual([(vorab, vorab.anhaenge[0])], yu.angebote([vorab]))

    def test_ein_anhang_ohne_adresse_zaehlt_nicht(self) -> None:
        leer = Freigabe(tag="v1", anhaenge=(Anhang(name="download0.dat", adresse=""),))
        self.assertEqual([], yu.angebote([leer]))

    def test_leere_liste_bleibt_leer(self) -> None:
        self.assertEqual([], yu.angebote([]))

    def test_reihenfolge_bleibt_wie_uebergeben(self) -> None:
        neu = Freigabe(tag="v1.0.2", anhaenge=(self._anhang("download0.dat"),))
        alt = Freigabe(tag="v0.9.1", anhaenge=(self._anhang("download0.dat"),))
        erg = yu.angebote([neu, alt])
        self.assertEqual(["v1.0.2", "v0.9.1"], [f.tag for f, _a in erg])


class QuelleTests(unittest.TestCase):
    def test_quelle_ist_eine_eigenstaendige_owner_repo_zeichenkette(self) -> None:
        self.assertEqual("itsPLK/ps5-y2jb-autoloader", yu.QUELLE)
        self.assertNotIn(" ", yu.QUELLE)

    def test_grenze_liegt_ueber_der_allgemeinen_netzgrenze(self) -> None:
        from ps5_validator.utils import werkzeug_updates as wu
        self.assertGreater(yu.GRENZE_BYTES, wu.GRENZE_BYTES)
        # Die gemessene Dateigroesse (18.10.2026, mehrere Fassungen) passt mit Luft.
        self.assertGreater(yu.GRENZE_BYTES, 336789504)


if __name__ == "__main__":
    unittest.main()
