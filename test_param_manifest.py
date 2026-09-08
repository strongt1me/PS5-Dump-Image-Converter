"""Tests fuer ps5_validator.utils.param_manifest (param.json/manifest.json Editor-Helfer)."""
import json
import os
import tempfile
import unittest
from collections import OrderedDict

from ps5_validator.utils.param_manifest import (
    APPLICATION_DRM_TYPES,
    MANIFEST_KNOWN_KEYS,
    PARAM_KNOWN_KEYS,
    create_default_manifest,
    create_default_param,
    load_json,
    save_manifest_json,
    save_param_json,
)


class ParamManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def _path(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_known_key_tables_are_populated(self) -> None:
        self.assertIn("titleId", PARAM_KNOWN_KEYS)
        self.assertIn("applicationDrmType", PARAM_KNOWN_KEYS)
        self.assertIn("applicationName", MANIFEST_KNOWN_KEYS)
        self.assertEqual(set(APPLICATION_DRM_TYPES), {"standard", "free", "freemium"})

    def test_param_roundtrip_preserves_order_and_unknown_keys(self) -> None:
        path = self._path("param.json")
        data = OrderedDict([
            ("titleId", "PPSA00000"),
            ("contentId", "UP0000-PPSA00000_00-0000000000000000"),
            ("applicationDrmType", "free"),
            ("someFutureKey", {"nested": [1, 2, 3]}),
        ])
        save_param_json(data, path)

        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        self.assertTrue(raw.startswith("{\n  "))  # 2-Leerzeichen-Einrückung
        self.assertFalse(raw.startswith("\ufeff"))  # kein BOM

        loaded = load_json(path)
        self.assertEqual(list(loaded.keys()), list(data.keys()))
        self.assertEqual(loaded["someFutureKey"], {"nested": [1, 2, 3]})
        self.assertEqual(loaded["applicationDrmType"], "free")

    def test_manifest_roundtrip_uses_four_space_indent(self) -> None:
        path = self._path("manifest.json")
        data = create_default_manifest(application_name="MyApp", title_id="PPSA00001")
        save_manifest_json(data, path)

        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        self.assertTrue(raw.startswith("{\n    "))  # 4-Leerzeichen-Einrückung

        loaded = load_json(path)
        self.assertEqual(loaded["applicationName"], "MyApp")
        self.assertEqual(loaded["titleId"], "PPSA00001")

    def test_create_default_param_has_sane_defaults(self) -> None:
        doc = create_default_param(title_id="PPSA00002", content_id="UP0000-PPSA00002_00-0000000000000000")
        self.assertEqual(doc["titleId"], "PPSA00002")
        self.assertEqual(doc["applicationDrmType"], "standard")
        self.assertEqual(doc["masterVersion"], "01.00")

    def test_load_json_handles_bom(self) -> None:
        path = self._path("bom_param.json")
        with open(path, "w", encoding="utf-8-sig") as f:
            json.dump({"titleId": "PPSA00003"}, f)
        loaded = load_json(path)
        self.assertEqual(loaded["titleId"], "PPSA00003")


class DokumenttypTests(unittest.TestCase):
    """Der Dokumenttyp entscheidet sich am Inhalt, nicht am Dateinamen.

    Bis v1.9.10 stand im Editor
    ``doc_type = "manifest" if "manifest" in basename.lower() else "param"``.
    Wer eine Manifestdatei ``param.json`` nannte - oder eine param.json in
    einem Ordner namens ``manifest`` liegen hatte -, bekam die falschen
    Vorgabefelder, die falschen Erklaertexte und beim Speichern das
    falsche Format.
    """

    def test_param_wird_am_inhalt_erkannt(self):
        from ps5_validator.utils.param_manifest import dokumenttyp_erkennen
        daten = {"titleId": "PPSA00000", "contentId": "IV0000-PPSA00000_00-X",
                 "applicationCategoryType": 0}
        # Der Name luegt absichtlich.
        self.assertEqual("param", dokumenttyp_erkennen(daten, "manifest.json"))

    def test_manifest_wird_am_inhalt_erkannt(self):
        from ps5_validator.utils.param_manifest import dokumenttyp_erkennen
        daten = {"applicationName": "Spiel", "applicationData": {},
                 "bootAnimation": True}
        self.assertEqual("manifest", dokumenttyp_erkennen(daten, "param.json"))

    def test_die_vorgabedokumente_erkennen_sich_selbst(self):
        """Anker: Waeren die Schluesselmengen deckungsgleich, entschiede
        immer der Dateiname und die Pruefung darueber waere wertlos.
        """
        from ps5_validator.utils.param_manifest import dokumenttyp_erkennen
        self.assertEqual("param", dokumenttyp_erkennen(create_default_param(), ""))
        self.assertEqual("manifest", dokumenttyp_erkennen(create_default_manifest(), ""))

    def test_ohne_aussagekraft_zaehlt_der_name(self):
        from ps5_validator.utils.param_manifest import dokumenttyp_erkennen
        self.assertEqual("manifest", dokumenttyp_erkennen({}, "mein_manifest.json"))
        self.assertEqual("param", dokumenttyp_erkennen({}, "irgendwas.json"))


if __name__ == "__main__":
    unittest.main()
