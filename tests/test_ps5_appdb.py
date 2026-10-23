"""Auslesen der VERSION_FILE_URI aus der app.db der Konsole (beide Tabellenformen)."""

import json
import os
import sqlite3
import tempfile
import unittest

from ps5_validator.utils import ps5_appdb

URI = "https://sgst.prod.dl.playstation.net/sgst/prod/00/np/PPSA01552_00/abc-version.xml"


def _db_bytes(aufbau) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "app.db")
        con = sqlite3.connect(pfad)
        aufbau(con)
        con.commit()
        con.close()
        with open(pfad, "rb") as fh:
            return fh.read()


class AppDbTests(unittest.TestCase):
    def test_neue_firmware_json_feld_mit_auffuellung(self):
        def aufbau(con):
            con.execute("CREATE TABLE tbl_contentinfo (titleId TEXT, AppInfoJson TEXT)")
            gepolstert = json.dumps({"VERSION_FILE_URI": URI + " " * 40})
            con.execute("INSERT INTO tbl_contentinfo VALUES ('PPSA01552', ?)", (gepolstert,))
            con.execute("INSERT INTO tbl_contentinfo VALUES ('PPSA00001', ?)", (json.dumps({"TITLE": "x"}),))
        mapping = ps5_appdb._app_db_auslesen(_db_bytes(aufbau))
        self.assertEqual({"PPSA01552": URI}, mapping)

    def test_alte_firmware_tabelle_appbrowse(self):
        def aufbau(con):
            con.execute("CREATE TABLE tbl_appbrowse (TITLE_ID TEXT, VERSION_FILE_URI TEXT)")
            con.execute("INSERT INTO tbl_appbrowse VALUES ('ppsa01552', ?)", (URI,))
        mapping = ps5_appdb._app_db_auslesen(_db_bytes(aufbau))
        self.assertEqual({"PPSA01552": URI}, mapping)


if __name__ == "__main__":
    unittest.main()
