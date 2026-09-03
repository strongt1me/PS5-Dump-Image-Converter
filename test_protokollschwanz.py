# -*- coding: utf-8 -*-
"""Prueft den Ringpuffer, aus dem der Diagnosebericht schoepft.

Der Diagnosebericht zeigt im Abschnitt ``report_section_log_tail`` die
letzten 60 Protokollzeilen. Sie stammen aus ``_build_log_tail``.

**Der Fehler, den diese Datei festhaelt:** Es gibt zwei Wege ins
Protokollfeld. ``_append_to_log`` fuellte den Puffer,
``_log_engine_zeilen`` nicht - der schrieb unmittelbar ins Feld. Ueber
den zweiten laeuft die gebuendelte Ausgabe von mkpfs und UFS2Tool, also
der Hauptteil eines Laufs, und er hat sieben Aufrufer.

Die Folge: Ein Lauf, der an der Engine scheitert, zeigte im
Diagnosebericht nur die Rahmenzeilen - nicht die Fehlerausgabe, um die
es geht. Ausgerechnet dann, wenn der Bericht gefragt ist.
"""
from __future__ import annotations

import unittest
from pathlib import Path


class _Traeger:
    """Das Wenigste, was das Merken braucht - ohne Oberflaeche."""

    def __init__(self) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as APP

        self._APP = APP
        self._LOG_SCHWANZ_ZEILEN = APP.PS5ConverterGUI._LOG_SCHWANZ_ZEILEN

    def merken(self, zeilen) -> None:
        self._APP.PS5ConverterGUI._protokollschwanz_merken(self, zeilen)


class MerkenTests(unittest.TestCase):
    def test_zeilen_landen_im_puffer(self) -> None:
        t = _Traeger()
        t.merken(["erste", "zweite"])
        self.assertEqual(t._build_log_tail, ["erste", "zweite"])

    def test_leere_zeilen_werden_uebergangen(self) -> None:
        t = _Traeger()
        t.merken(["echt", "", "   ", "auch echt"])
        self.assertEqual(t._build_log_tail, ["echt", "auch echt"])

    def test_der_puffer_waechst_nicht_unbegrenzt(self) -> None:
        t = _Traeger()
        t.merken(["Zeile %d" % i for i in range(200)])
        self.assertEqual(len(t._build_log_tail), t._LOG_SCHWANZ_ZEILEN)

    def test_die_juengsten_bleiben(self) -> None:
        t = _Traeger()
        t.merken(["Zeile %d" % i for i in range(200)])
        self.assertEqual(t._build_log_tail[-1], "Zeile 199")

    def test_mehrere_aufrufe_haengen_an(self) -> None:
        t = _Traeger()
        t.merken(["a"])
        t.merken(["b"])
        self.assertEqual(t._build_log_tail, ["a", "b"])

    def test_ein_fehler_haelt_das_protokoll_nicht_an(self) -> None:
        """Ein voller Puffer darf nie einen Lauf anhalten."""
        t = _Traeger()

        class _Boese:
            def __iter__(self):
                raise RuntimeError("kaputt")

        t.merken(_Boese())          # darf nicht werfen


class BeideWegeTests(unittest.TestCase):
    """Der Kern: es gibt zwei Wege, und beide muessen fuellen."""

    QUELLE = Path("PS5ImageConverter_Pro_FINAL_revised.py")

    def _methode(self, name: str):
        import ast

        quelle = self.QUELLE.read_text(encoding="utf-8", errors="replace")
        klasse = next(k for k in ast.walk(ast.parse(quelle))
                      if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")
        return next(m for m in klasse.body
                    if isinstance(m, ast.FunctionDef) and m.name == name)

    def test_beide_protokollwege_fuellen_den_puffer(self) -> None:
        """Ueber den Baum geprueft, nicht ueber den Wortlaut.

        _log_engine_zeilen traegt die Ausgabe von mkpfs und UFS2Tool.
        Fuellt es den Puffer nicht, fehlt im Diagnosebericht genau
        das, wofuer man ihn aufmacht.
        """
        import ast

        for name in ("_append_to_log", "_log_engine_zeilen"):
            with self.subTest(weg=name):
                methode = self._methode(name)
                rufe = [c for c in ast.walk(methode)
                        if isinstance(c, ast.Call)
                        and getattr(c.func, "attr", "")
                        == "_protokollschwanz_merken"]
                self.assertTrue(
                    rufe,
                    "%s fuellt den Puffer fuer den Diagnosebericht "
                    "nicht - was ueber diesen Weg laeuft, fehlt dort."
                    % name)

    def test_nur_eine_stelle_setzt_den_puffer(self) -> None:
        """Sonst laufen zwei Fassungen der Kuerzung auseinander."""
        quelle = self.QUELLE.read_text(encoding="utf-8", errors="replace")
        self.assertEqual(
            quelle.count("self._build_log_tail = "), 2,
            "Der Puffer wird an mehr als der einen Stelle gesetzt "
            "(Anlegen und Kuerzen in _protokollschwanz_merken).")

    def test_der_bericht_liest_den_puffer_als_rueckruf(self) -> None:
        """Er wird beim Kuerzen neu zugewiesen - eine Referenz zeigte
        danach ins Leere."""
        quelle = self.QUELLE.read_text(encoding="utf-8", errors="replace")
        self.assertIn("protokollschwanz=lambda:", quelle)


if __name__ == "__main__":
    unittest.main()
