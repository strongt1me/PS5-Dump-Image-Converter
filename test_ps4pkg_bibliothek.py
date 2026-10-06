# -*- coding: utf-8 -*-
"""Tests fuer ``ps5_validator.utils.ps4pkg_bibliothek`` - die PS4-Paketsammlung.

Die Pakete entstehen hier synthetisch: ein Kopf von 0x5A0 Byte, eine
Eintragstabelle und eine echte ``param.sfo`` - so wie ein PS4-Paket sie
traegt. Die Werte (Kopfflags ``0x40000001``, ``SYSTEM_VER 0x04008000``, die
Eintragskennungen) stammen vom echten Paket ``Mario Kart 64 [PS2toPS4]``
(05.10.2026).
"""
from __future__ import annotations

import csv
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ps4pkg_bibliothek as bib   # noqa: E402


def sfo_bauen(werte: dict) -> bytes:
    """Eine ``param.sfo``: Text als 0x0204, Zahlen als 0x0404."""
    schluessel = sorted(werte)
    key_tabelle = b""
    daten_tabelle = b""
    index = b""
    for name in schluessel:
        wert = werte[name]
        if isinstance(wert, int):
            roh, fmt = struct.pack("<I", wert), 0x0404
        else:
            roh, fmt = wert.encode("utf-8") + b"\x00", 0x0204
        index += struct.pack("<HHIII", len(key_tabelle), fmt, len(roh), len(roh), len(daten_tabelle))
        key_tabelle += name.encode("ascii") + b"\x00"
        daten_tabelle += roh
    key_tabelle += b"\x00" * ((-len(key_tabelle)) % 4)
    key_start = 0x14 + len(index)
    daten_start = key_start + len(key_tabelle)
    kopf = b"\x00PSF" + struct.pack("<IIII", 0x101, key_start, daten_start, len(schluessel))
    return kopf + index + key_tabelle + daten_tabelle


def paket_bauen(pfad: Path, *, titel="Mini Spiel", title_id="CUSA00001", kategorie="gd",
                app_ver="01.00", version="01.00", content_id="UP0000-CUSA00001_00-0000000000000000",
                system_ver=0x04008000, flags=0x40000001, content_type=0x1A, content_flags=0x0A000000,
                mit_sfo=True, sfo_verschluesselt=False, mit_icon=True, mit_namen=False) -> Path:
    sfo = sfo_bauen({"TITLE": titel, "TITLE_ID": title_id, "CATEGORY": kategorie,
                     "APP_VER": app_ver, "VERSION": version, "CONTENT_ID": content_id,
                     "SYSTEM_VER": system_ver})
    icon = b"\x89PNG\r\n\x1a\n" + b"ICON" * 10
    eintraege = []
    tabelle = 0x2000
    ablage = 0x3000
    daten = bytearray()
    namen_offsets: dict[int, int] = {}

    def einlagern(kennung: int, inhalt: bytes, flags1: int = 0) -> None:
        nonlocal ablage
        eintraege.append((kennung, flags1, ablage, len(inhalt)))
        daten.extend(inhalt.ljust(0x1000, b"\x00"))
        ablage += 0x1000

    if mit_namen:
        # Namenstabelle: Der erste Eintrag beginnt bei 1 (Offset 0 heisst "ohne Namen").
        tabelle_namen = b"\x00lizenz-datei\x00param.sfo\x00icon0.png\x00"
        namen_offsets = {0x0400: 1, 0x1000: 14, 0x1200: 24}
        einlagern(0x0200, tabelle_namen)
    einlagern(0x0400, b"lizenz", 0x80000000)
    if mit_sfo:
        einlagern(0x1000, sfo, 0x80000000 if sfo_verschluesselt else 0)
    if mit_icon:
        einlagern(0x1200, icon)
    kopf = bytearray(0x5A0)
    kopf[0:4] = b"\x7fCNT"
    struct.pack_into(">I", kopf, 0x04, flags)
    struct.pack_into(">I", kopf, 0x10, len(eintraege))
    struct.pack_into(">I", kopf, 0x18, tabelle)
    kopf[0x40:0x40 + len(content_id)] = content_id.encode("ascii")
    struct.pack_into(">I", kopf, 0x74, content_type)
    struct.pack_into(">I", kopf, 0x78, content_flags)
    struct.pack_into(">Q", kopf, 0x430, 123456789)
    tabellenbytes = b"".join(struct.pack(">IIIIII8x", k, namen_offsets.get(k, 0), f1, 0, off, gr)
                             for k, f1, off, gr in eintraege)
    inhalt = bytearray(0x3000)
    inhalt[:0x5A0] = kopf
    inhalt[tabelle:tabelle + len(tabellenbytes)] = tabellenbytes
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(bytes(inhalt) + bytes(daten))
    return pfad


class SfoTests(unittest.TestCase):

    def test_text_und_zahlen(self) -> None:
        sfo = bib.sfo_lesen(sfo_bauen({"TITLE": "Pokémon – Test", "SYSTEM_VER": 0x05050000, "APP_VER": "01.05"}))
        self.assertEqual("Pokémon – Test", sfo["TITLE"])
        self.assertEqual(0x05050000, sfo["SYSTEM_VER"])
        self.assertEqual("01.05", sfo["APP_VER"])

    def test_kaputtes_liefert_leer_und_wirft_nicht(self) -> None:
        self.assertEqual({}, bib.sfo_lesen(b""))
        self.assertEqual({}, bib.sfo_lesen(b"kein sfo" * 10))
        abgeschnitten = sfo_bauen({"TITLE": "x"})[:0x18]
        self.assertEqual({}, bib.sfo_lesen(abgeschnitten))

    def test_unsinnige_anzahl_haengt_nichts_auf(self) -> None:
        roh = bytearray(sfo_bauen({"TITLE": "x"}))
        struct.pack_into("<I", roh, 0x10, 0xFFFFFFF0)
        bib.sfo_lesen(bytes(roh))   # darf nicht ewig laufen oder werfen


class FassungTests(unittest.TestCase):

    def test_system_version(self) -> None:
        self.assertEqual("5.05", bib.system_version_text(0x05050000))
        self.assertEqual("4.00", bib.system_version_text(0x04008000))
        self.assertEqual("10.50", bib.system_version_text(0x10500000))
        self.assertEqual("9.00", bib.system_version_text(0x09000000))
        self.assertEqual("", bib.system_version_text(0))
        self.assertEqual("", bib.system_version_text("x"))   # type: ignore[arg-type]

    def test_region(self) -> None:
        self.assertEqual("US", bib.region_aus_content_id("UP9000-X"))
        self.assertEqual("EU", bib.region_aus_content_id("EP4133-CUSA37321_00"))
        self.assertEqual("JP", bib.region_aus_content_id("JP0001-X"))
        self.assertEqual("", bib.region_aus_content_id("ZZ"))
        self.assertEqual("", bib.region_aus_content_id(""))

    def test_typ(self) -> None:
        self.assertEqual(bib.TYP_BASIS, bib.typ_aus_kategorie("gd"))
        self.assertEqual(bib.TYP_UPDATE, bib.typ_aus_kategorie("gp"))
        self.assertEqual(bib.TYP_ZUSATZ, bib.typ_aus_kategorie("ac"))
        self.assertEqual(bib.TYP_APP, bib.typ_aus_kategorie("gde"))
        self.assertEqual(bib.TYP_UNBEKANNT, bib.typ_aus_kategorie("zz"))

    def test_echtheit(self) -> None:
        self.assertEqual(bib.ECHT_FAKE, bib.echtheit_aus_kopf(0x40000001, 0x1A, 0x0A000000))
        self.assertEqual(bib.ECHT_OFFIZIELL, bib.echtheit_aus_kopf(0x83000001, 0x1A, 0x0A000000))
        self.assertEqual(bib.ECHT_OFFIZIELL, bib.echtheit_aus_kopf(0x81000001, 0x1A, 0x0A000000))
        self.assertEqual(bib.ECHT_OFFIZIELL_DP, bib.echtheit_aus_kopf(0x40000001, 0x1E, 0x43000000))
        self.assertEqual(bib.ECHT_FAKE, bib.echtheit_aus_kopf(0x8E000001, 0x1A, 0x0A000000))

    def test_fassungen_werden_als_zahlen_verglichen(self) -> None:
        self.assertLess(bib.fassung_zahlen("01.09"), bib.fassung_zahlen("01.10"))
        self.assertLess(bib.fassung_zahlen("1.05"), bib.fassung_zahlen("01.50"))
        self.assertEqual((-1,), bib.fassung_zahlen(""))


class PaketLesenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ein_paket_wird_gelesen(self) -> None:
        pfad = paket_bauen(self.wo / "a.pkg", titel="Mario Kart 64 [ PS2toPS4 ]", title_id="MOMK27926",
                           content_id="UP9000-MOMK27926_00-SLUS867650000001")
        e = bib.lese_paket(str(pfad))
        self.assertTrue(e.lesbar, e.fehler)
        self.assertEqual("Mario Kart 64 [ PS2toPS4 ]", e.titel)
        self.assertEqual("MOMK27926", e.title_id)
        self.assertEqual(bib.TYP_BASIS, e.typ)
        self.assertEqual("gd", e.kategorie)
        self.assertEqual("01.00", e.app_ver)
        self.assertEqual("4.00", e.system_ver)
        self.assertEqual("US", e.region)
        self.assertEqual(bib.ECHT_FAKE, e.echtheit)
        self.assertEqual(123456789, e.paketgroesse)
        self.assertEqual(pfad.stat().st_size, e.groesse)
        self.assertEqual("a.pkg", e.datei)

    def test_ein_update_und_eine_dlc(self) -> None:
        patch = bib.lese_paket(str(paket_bauen(self.wo / "p.pkg", kategorie="gp", app_ver="01.09")))
        dlc = bib.lese_paket(str(paket_bauen(self.wo / "d.pkg", kategorie="ac")))
        self.assertEqual(bib.TYP_UPDATE, patch.typ)
        self.assertEqual("01.09", patch.app_ver)
        self.assertEqual(bib.TYP_ZUSATZ, dlc.typ)

    def test_ein_offizielles_paket_wird_erkannt(self) -> None:
        e = bib.lese_paket(str(paket_bauen(self.wo / "o.pkg", flags=0x83000001)))
        self.assertEqual(bib.ECHT_OFFIZIELL, e.echtheit)

    def test_eine_fremde_datei_ist_nicht_lesbar(self) -> None:
        pfad = self.wo / "x.pkg"
        pfad.write_bytes(b"kein Paket" * 500)
        e = bib.lese_paket(str(pfad))
        self.assertFalse(e.lesbar)
        self.assertIn("Kennung", e.fehler)

    def test_eine_leere_und_eine_fehlende_datei(self) -> None:
        leer = self.wo / "leer.pkg"
        leer.write_bytes(b"")
        self.assertFalse(bib.lese_paket(str(leer)).lesbar)
        fehlt = bib.lese_paket(str(self.wo / "gibt_es_nicht.pkg"))
        self.assertFalse(fehlt.lesbar)
        self.assertTrue(fehlt.fehler)

    def test_ein_abgeschnittenes_paket_wirft_nicht(self) -> None:
        pfad = paket_bauen(self.wo / "k.pkg")
        pfad.write_bytes(pfad.read_bytes()[:0x2010])   # mitten in der Eintragstabelle
        self.assertFalse(bib.lese_paket(str(pfad)).lesbar)

    def test_ohne_param_sfo_ist_es_nicht_lesbar(self) -> None:
        e = bib.lese_paket(str(paket_bauen(self.wo / "o.pkg", mit_sfo=False)))
        self.assertFalse(e.lesbar)
        self.assertIn("param.sfo", e.fehler)

    def test_eine_verschluesselte_param_sfo_wird_nicht_geraten(self) -> None:
        e = bib.lese_paket(str(paket_bauen(self.wo / "v.pkg", sfo_verschluesselt=True)))
        self.assertFalse(e.lesbar)
        self.assertIn("verschluesselt", e.fehler)

    def test_ein_ps5_title_id_wird_abgewiesen(self) -> None:
        e = bib.lese_paket(str(paket_bauen(self.wo / "ps5.pkg", title_id="PPSA01234")))
        # PPSA01234 hat dieselbe Form - der Kopf allein unterscheidet PS4 und PS5 nicht;
        # die Kategorie (gd) und die Form genuegen hier. Die Regel ist die Form der Kennung.
        self.assertTrue(e.lesbar)
        schlecht = bib.lese_paket(str(paket_bauen(self.wo / "x.pkg", title_id="NICHTS")))
        self.assertFalse(schlecht.lesbar)
        self.assertIn("Title-ID", schlecht.fehler)

    def test_ein_riesiges_paket_wird_nicht_ganz_gelesen(self) -> None:
        """Es werden nur Kopf, Tabelle und param.sfo gelesen - nicht die Datei."""
        pfad = paket_bauen(self.wo / "g.pkg")
        gelesen: list[int] = []
        echte_open = open

        class _Zaehlend:
            def __init__(self, datei) -> None:
                self._d = datei

            def read(self, n=-1):
                daten = self._d.read(n)
                gelesen.append(len(daten))
                return daten

            def __getattr__(self, name):
                return getattr(self._d, name)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self._d.close()

        with mock.patch("builtins.open", lambda p, m="r", *a, **k: _Zaehlend(echte_open(p, m, *a, **k))
                        if str(p) == str(pfad) else echte_open(p, m, *a, **k)):
            self.assertTrue(bib.lese_paket(str(pfad)).lesbar)
        self.assertLess(sum(gelesen), 16384, "Es wurde mehr als Kopf, Tabelle und param.sfo gelesen.")

    def test_bilder_und_eintragsliste(self) -> None:
        pfad = paket_bauen(self.wo / "b.pkg")
        icon = bib.lese_bild(str(pfad))
        self.assertIsNotNone(icon)
        self.assertTrue(icon.startswith(b"\x89PNG"))
        self.assertIsNone(bib.lese_bild(str(pfad), bib.EINTRAG_PIC0))
        liste = bib.lese_eintragsliste(str(pfad))
        self.assertEqual({0x0400, 0x1000, 0x1200}, {e["kennung"] for e in liste})
        verschluesselt = [e for e in liste if e["kennung"] == 0x0400][0]
        self.assertTrue(verschluesselt["verschluesselt"])
        self.assertEqual([], bib.lese_eintragsliste(str(self.wo / "fehlt.pkg")))

    def test_die_eintragsnamen_kommen_aus_der_namenstabelle_oder_der_bekannten_liste(self) -> None:
        ohne = {e["kennung"]: e["name"] for e in bib.lese_eintragsliste(str(paket_bauen(self.wo / "o.pkg")))}
        self.assertEqual({0x0400: "license.dat", 0x1000: "param.sfo", 0x1200: "icon0.png"}, ohne)
        mit = {e["kennung"]: e["name"] for e in
               bib.lese_eintragsliste(str(paket_bauen(self.wo / "m.pkg", mit_namen=True)))}
        self.assertEqual("lizenz-datei", mit[0x0400], "Die Namenstabelle des Pakets gilt zuerst.")
        self.assertEqual("param.sfo", mit[0x1000])
        self.assertEqual("entry_names", mit[0x0200], "Ohne Namensangabe gilt die bekannte Liste.")

    def test_ein_unbekannter_eintrag_heisst_nach_seiner_kennung(self) -> None:
        pfad = paket_bauen(self.wo / "u.pkg")
        roh = bytearray(pfad.read_bytes())
        struct.pack_into(">I", roh, 0x2000, 0x7777)   # erste Kennung ueberschreiben
        pfad.write_bytes(bytes(roh))
        namen = {e["kennung"]: e["name"] for e in bib.lese_eintragsliste(str(pfad))}
        self.assertEqual("0x7777", namen[0x7777])

    def test_ein_verschluesseltes_bild_wird_nicht_geliefert(self) -> None:
        pfad = paket_bauen(self.wo / "b.pkg")
        self.assertIsNone(bib.lese_bild(str(pfad), 0x0400))


class EinlesenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)
        paket_bauen(self.wo / "a" / "eins.pkg", title_id="CUSA00001")
        paket_bauen(self.wo / "a" / "b" / "zwei.PKG", title_id="CUSA00002")
        (self.wo / "a" / "notizen.txt").write_text("x")
        self.cache = str(self.wo / "cache" / "bib.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_dateien_rekursiv_ohne_doppelte(self) -> None:
        gefunden = bib.paket_dateien([str(self.wo / "a"), str(self.wo / "a" / "eins.pkg")])
        self.assertEqual(["eins.pkg", "zwei.PKG"], sorted(os.path.basename(p) for p in gefunden))

    def test_nicht_rekursiv(self) -> None:
        gefunden = bib.paket_dateien([str(self.wo / "a")], rekursiv=False)
        self.assertEqual(["eins.pkg"], [os.path.basename(p) for p in gefunden])

    def test_einlesen_meldet_fortschritt(self) -> None:
        meldungen: list[tuple[int, int, str]] = []
        erg = bib.einlesen([str(self.wo)], fortschritt=lambda a, g, d: meldungen.append((a, g, d)))
        self.assertEqual(2, len(erg))
        # Die Reihenfolge ist die der vollen Pfade (a/b/zwei.PKG vor a/eins.pkg).
        self.assertEqual([(1, 2), (2, 2)], [(a, g) for a, g, _ in meldungen])
        self.assertEqual({"eins.pkg", "zwei.PKG"}, {d for _, _, d in meldungen})

    def test_der_abbruch_haelt_das_einlesen_an(self) -> None:
        erg = bib.einlesen([str(self.wo)], abbruch=lambda: True)
        self.assertEqual([], erg)

    def test_die_suche_meldet_ihren_stand(self) -> None:
        """Ein ganzer Datentraeger kann Minuten brauchen - die Suche darf nicht still sein."""
        meldungen: list[tuple[int, str]] = []
        with mock.patch.object(bib, "SUCHE_TAKT", 0.0):          # sonst wuerde nur gemeldet, was langsam ist
            gefunden = bib.paket_dateien([str(self.wo)], fortschritt=lambda n, ordner: meldungen.append((n, ordner)))
        self.assertEqual(2, len(gefunden))
        self.assertGreaterEqual(len(meldungen), 3, "Je Ordner eine Meldung: Wurzel, a, a/b.")
        self.assertEqual(2, meldungen[-1][0], "Die letzte Meldung nennt alle Treffer.")
        self.assertTrue(all(os.path.isdir(ordner) for _n, ordner in meldungen))
        zaehler = [n for n, _o in meldungen]
        self.assertEqual(sorted(zaehler), zaehler, "Die Zahl der Treffer faellt nie.")

    def test_die_suche_meldet_hoechstens_im_takt(self) -> None:
        meldungen: list[int] = []
        with mock.patch.object(bib, "SUCHE_TAKT", 3600.0):
            bib.paket_dateien([str(self.wo)], fortschritt=lambda n, ordner: meldungen.append(n))
        self.assertEqual(1, len(meldungen), "Nach der ersten Meldung schweigt sie eine Stunde lang.")

    def test_die_suche_laesst_sich_abbrechen(self) -> None:
        schritte = []

        def abbruch() -> bool:
            schritte.append(1)
            return len(schritte) > 1                 # nach dem ersten Ordner

        gefunden = bib.paket_dateien([str(self.wo)], abbruch=abbruch)
        self.assertLess(len(gefunden), 2, "Was bis zum Abbruch gefunden ist, bleibt; der Rest fehlt.")
        self.assertEqual([], bib.paket_dateien([str(self.wo)], abbruch=lambda: True))

    def test_einlesen_reicht_die_suchmeldung_weiter(self) -> None:
        meldungen: list[tuple[int, str]] = []
        with mock.patch.object(bib, "SUCHE_TAKT", 0.0):
            bib.einlesen([str(self.wo)], suche_fortschritt=lambda n, ordner: meldungen.append((n, ordner)))
        self.assertTrue(meldungen)

    def test_der_zwischenspeicher_spart_das_zweite_lesen(self) -> None:
        speicher = bib.Zwischenspeicher(self.cache)
        bib.einlesen([str(self.wo)], zwischenspeicher=speicher)
        self.assertTrue(os.path.isfile(self.cache))
        with mock.patch.object(bib, "lese_paket", side_effect=AssertionError("nicht noch einmal lesen")) as lesen:
            erg = bib.einlesen([str(self.wo)], zwischenspeicher=bib.Zwischenspeicher(self.cache))
        lesen.assert_not_called()
        self.assertEqual({"CUSA00001", "CUSA00002"}, {e.title_id for e in erg})

    def test_ein_geaendertes_paket_wird_neu_gelesen(self) -> None:
        bib.einlesen([str(self.wo)], zwischenspeicher=bib.Zwischenspeicher(self.cache))
        pfad = paket_bauen(self.wo / "a" / "eins.pkg", title_id="CUSA00009", titel="Neu")
        # Dieselbe Groesse, und zwei Schreibvorgaenge innerhalb eines Zeittakts des
        # Dateisystems tragen dieselbe Aenderungszeit - die Zeit wird deshalb gesetzt.
        status = pfad.stat()
        os.utime(pfad, (status.st_atime, status.st_mtime + 10))
        erg = bib.einlesen([str(self.wo)], zwischenspeicher=bib.Zwischenspeicher(self.cache))
        self.assertIn("CUSA00009", {e.title_id for e in erg})

    def test_ein_kaputter_zwischenspeicher_wird_ignoriert(self) -> None:
        os.makedirs(os.path.dirname(self.cache), exist_ok=True)
        Path(self.cache).write_text("{kaputt", encoding="utf-8")
        erg = bib.einlesen([str(self.wo)], zwischenspeicher=bib.Zwischenspeicher(self.cache))
        self.assertEqual(2, len(erg))

    def test_nicht_lesbare_pakete_stehen_trotzdem_in_der_liste(self) -> None:
        (self.wo / "a" / "kaputt.pkg").write_bytes(b"x" * 100)
        erg = bib.einlesen([str(self.wo)])
        kaputt = [e for e in erg if e.datei == "kaputt.pkg"]
        self.assertEqual(1, len(kaputt))
        self.assertFalse(kaputt[0].lesbar)


def _e(**kw) -> bib.PkgEintrag:
    werte = dict(pfad=os.path.join(tempfile.gettempdir(), "x.pkg"), lesbar=True, titel="Titel",
                 title_id="CUSA00001", typ=bib.TYP_BASIS, kategorie="gd", app_ver="01.00",
                 version="01.00", content_id="UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA", region="US",
                 system_ver="5.05", echtheit=bib.ECHT_FAKE)
    werte.update(kw)
    return bib.PkgEintrag(**werte)


class FilternTests(unittest.TestCase):

    def setUp(self) -> None:
        self.liste = [
            _e(pfad="/s/a.pkg", titel="Alpha", title_id="CUSA00001", region="US", system_ver="5.05"),
            _e(pfad="/s/b.pkg", titel="Beta", title_id="CUSA00002", typ=bib.TYP_UPDATE, region="EU",
               system_ver="9.00", echtheit=bib.ECHT_OFFIZIELL),
            _e(pfad="/s/c.pkg", titel="Gamma Spiel", title_id="CUSA00003", typ=bib.TYP_ZUSATZ, region="EU",
               system_ver=""),
        ]

    def test_suche_findet_in_allen_feldern(self) -> None:
        self.assertEqual(["Beta"], [e.titel for e in bib.filtern(self.liste, suche="cusa00002")])
        self.assertEqual(["Gamma Spiel"], [e.titel for e in bib.filtern(self.liste, suche="gamma")])
        self.assertEqual(["Alpha"], [e.titel for e in bib.filtern(self.liste, suche="a.pkg")])

    def test_typ_region_echtheit(self) -> None:
        self.assertEqual(["Beta"], [e.titel for e in bib.filtern(self.liste, typ=bib.TYP_UPDATE)])
        self.assertEqual(["Beta", "Gamma Spiel"], [e.titel for e in bib.filtern(self.liste, region="EU")])
        self.assertEqual(["Beta"], [e.titel for e in bib.filtern(self.liste, echtheit=bib.ECHT_OFFIZIELL)])

    def test_firmware_ist_eine_obergrenze(self) -> None:
        self.assertEqual(["Alpha", "Gamma Spiel"],
                         [e.titel for e in bib.filtern(self.liste, min_firmware="5.05")])
        self.assertEqual(3, len(bib.filtern(self.liste, min_firmware="9.00")))

    def test_bedingungen_verknuepfen(self) -> None:
        self.assertEqual([], bib.filtern(self.liste, region="EU", typ=bib.TYP_BASIS))

    def test_gruppieren(self) -> None:
        gruppen = bib.gruppieren(self.liste, "typ")
        self.assertEqual(["addon", "base", "patch"], [name for name, _ in gruppen])
        with self.assertRaises(ValueError):
            bib.gruppieren(self.liste, "farbe")


class NamenTests(unittest.TestCase):

    def test_bereinigen(self) -> None:
        self.assertEqual("Spiel： Teil 2", bib.dateiname_bereinigen("Spiel: Teil 2"))
        self.assertEqual("a／b", bib.dateiname_bereinigen("a/b"))
        self.assertEqual("_CON", bib.dateiname_bereinigen("CON"))
        self.assertEqual("Titel", bib.dateiname_bereinigen("Titel. . "))
        self.assertEqual("_", bib.dateiname_bereinigen(""))
        self.assertEqual("a_b", bib.dateiname_bereinigen("a\x01b"))
        self.assertLessEqual(len(bib.dateiname_bereinigen("x" * 500)), 180)

    def test_alle_platzhalter(self) -> None:
        e = _e(titel="Spiel: Eins", app_ver="01.05", version="01.00", system_ver="5.05")
        self.assertEqual("Spiel： Eins", bib.namen_ersetzen("{TITLE}", e))
        self.assertEqual("CUSA00001", bib.namen_ersetzen("{TITLE_ID}", e))
        self.assertEqual("1.05", bib.namen_ersetzen("{APP_VERSION}", e))
        self.assertEqual("1.00", bib.namen_ersetzen("{VERSION}", e))
        self.assertEqual("Game", bib.namen_ersetzen("{CATEGORY}", e))
        self.assertEqual("UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA", bib.namen_ersetzen("{CONTENT_ID}", e))
        self.assertEqual("US", bib.namen_ersetzen("{REGION}", e))
        self.assertEqual("5.05", bib.namen_ersetzen("{SYSTEM_VERSION}", e))

    def test_content_id2_nach_der_szenenregel(self) -> None:
        e = _e(app_ver="01.05", version="01.10")
        self.assertEqual("UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA-A0105-V0110", bib.content_id2(e))
        dlc = _e(typ=bib.TYP_ZUSATZ, version="01.10")
        self.assertEqual("UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA-A0000-V0110", bib.content_id2(dlc))

    def test_die_zehn_vorlagen_sind_gueltig(self) -> None:
        self.assertEqual(10, len(bib.VORLAGEN))
        for nummer, vorlage in bib.VORLAGEN:
            with self.subTest(nummer=nummer):
                self.assertTrue(bib.vorlage_gueltig(vorlage)[0], vorlage)

    def test_eigene_vorlage_wird_geprueft(self) -> None:
        self.assertEqual((True, ""), bib.vorlage_gueltig("{TITLE} - {REGION}"))
        self.assertEqual((False, "FARBE"), bib.vorlage_gueltig("{TITLE} {FARBE}"))
        self.assertFalse(bib.vorlage_gueltig("   ")[0])


class PlanTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _pakete(self) -> list[bib.PkgEintrag]:
        pfade = [
            paket_bauen(self.wo / "alt1.pkg", titel="Spiel", title_id="CUSA00001", kategorie="gd"),
            paket_bauen(self.wo / "alt2.pkg", titel="Spiel", title_id="CUSA00001", kategorie="gp", app_ver="01.09"),
            paket_bauen(self.wo / "alt3.pkg", titel="Spiel", title_id="CUSA00001", kategorie="gp", app_ver="01.05"),
            paket_bauen(self.wo / "dlc.pkg", titel="Spiel", title_id="CUSA00001", kategorie="ac"),
        ]
        return [bib.lese_paket(str(p)) for p in pfade]

    def test_umbenennen_nach_muster(self) -> None:
        plan = bib.umbenennen_plan(self._pakete()[:1], "{TITLE} [{TITLE_ID}]")
        self.assertEqual(str(self.wo / "Spiel [CUSA00001].pkg"), plan[0].ziel)
        self.assertTrue(plan[0].aendert)

    def test_gleiche_namen_werden_nummeriert_nicht_ueberschrieben(self) -> None:
        plan = bib.umbenennen_plan(self._pakete(), "{TITLE}")
        ziele = [os.path.basename(s.ziel) for s in plan]
        self.assertEqual(len(set(ziele)), len(ziele), ziele)
        self.assertIn("Spiel.pkg", ziele)
        self.assertIn("Spiel (2).pkg", ziele)

    def test_ein_vorhandenes_ziel_wird_nicht_angefasst(self) -> None:
        (self.wo / "Spiel.pkg").write_bytes(b"fremd")
        plan = bib.umbenennen_plan(self._pakete()[:1], "{TITLE}")
        self.assertEqual("Spiel (2).pkg", os.path.basename(plan[0].ziel))

    def test_ein_schon_richtiger_name_aendert_nichts(self) -> None:
        pfad = paket_bauen(self.wo / "Spiel.pkg", titel="Spiel")
        plan = bib.umbenennen_plan([bib.lese_paket(str(pfad))], "{TITLE}")
        self.assertFalse(plan[0].aendert)

    def test_unlesbare_pakete_bleiben_aussen(self) -> None:
        schlecht = bib.PkgEintrag(pfad=str(self.wo / "x.pkg"), lesbar=False)
        self.assertEqual([], bib.umbenennen_plan([schlecht], "{TITLE}"))

    def test_installationsreihenfolge(self) -> None:
        plan = bib.install_prioritaet_plan(self._pakete())
        namen = {os.path.basename(s.quelle): os.path.basename(s.ziel) for s in plan}
        self.assertEqual("Spiel [CUSA00001] 00 - Base.pkg", namen["alt1.pkg"])
        self.assertEqual("Spiel [CUSA00001] 01 - Update v1.05.pkg", namen["alt3.pkg"])
        self.assertEqual("Spiel [CUSA00001] 02 - Update v1.09.pkg", namen["alt2.pkg"])
        self.assertNotIn("dlc.pkg", namen, "Zusatzinhalte haben keine feste Reihenfolge.")

    def test_verschieben_nach_arten(self) -> None:
        pakete = self._pakete()
        basis = str(self.wo / "sortiert")
        nach_typ = bib.verschieben_plan(pakete, "kategorie", basis)
        unter = {os.path.basename(s.quelle): os.path.basename(os.path.dirname(s.ziel)) for s in nach_typ}
        self.assertEqual({"alt1.pkg": "Base", "alt2.pkg": "Update", "alt3.pkg": "Update", "dlc.pkg": "Addon"}, unter)
        nach_id = bib.verschieben_plan(pakete, "title_id", basis)
        self.assertEqual({"CUSA00001"}, {os.path.basename(os.path.dirname(s.ziel)) for s in nach_id})
        einzeln = bib.verschieben_plan(pakete, "einzelordner", basis, "Alle")
        self.assertEqual({"Alle"}, {os.path.basename(os.path.dirname(s.ziel)) for s in einzeln})
        nach_region = bib.verschieben_plan(pakete, "region", basis)
        self.assertEqual({"US"}, {os.path.basename(os.path.dirname(s.ziel)) for s in nach_region})
        echt = bib.verschieben_plan(pakete, "echtheit", basis)
        self.assertEqual({"Fake"}, {os.path.basename(os.path.dirname(s.ziel)) for s in echt})
        with self.assertRaises(ValueError):
            bib.verschieben_plan(pakete, "farbe", basis)

    def test_ausfuehren_legt_ordner_an_und_benennt_um(self) -> None:
        pakete = self._pakete()[:1]
        plan = bib.verschieben_plan(pakete, "titel", str(self.wo / "sortiert"))
        meldungen: list[tuple[int, int, str]] = []
        fehler = bib.plan_ausfuehren(plan, fortschritt=lambda a, g, d: meldungen.append((a, g, d)))
        self.assertEqual([], fehler)
        self.assertTrue((self.wo / "sortiert" / "Spiel" / "alt1.pkg").is_file())
        self.assertFalse((self.wo / "alt1.pkg").exists())
        self.assertEqual([(1, 1, "alt1.pkg")], meldungen)

    def test_ausfuehren_ueberschreibt_nie(self) -> None:
        pakete = self._pakete()[:1]
        ziel = self.wo / "Spiel.pkg"
        ziel.write_bytes(b"wichtig")
        plan = [bib.Umbenennung(pakete[0].pfad, str(ziel))]
        fehler = bib.plan_ausfuehren(plan)
        self.assertEqual(1, len(fehler))
        self.assertEqual(b"wichtig", ziel.read_bytes())
        self.assertTrue((self.wo / "alt1.pkg").is_file())

    def test_ein_leerer_plan_tut_nichts(self) -> None:
        self.assertEqual([], bib.plan_ausfuehren([]))
        pfad = str(self.wo / "x.pkg")
        self.assertEqual([], bib.plan_ausfuehren([bib.Umbenennung(pfad, pfad)]))


class PruefungenTests(unittest.TestCase):

    def test_duplikate(self) -> None:
        a = _e(pfad="/s/a.pkg")
        b = _e(pfad="/t/b.pkg")
        update = _e(pfad="/s/u.pkg", typ=bib.TYP_UPDATE, app_ver="01.01")
        gruppen = bib.duplikate([a, b, update])
        self.assertEqual(1, len(gruppen))
        self.assertEqual({"/s/a.pkg", "/t/b.pkg"}, {e.pfad for e in gruppen[0]})

    def test_zwei_fassungen_sind_keine_duplikate(self) -> None:
        eins = _e(pfad="/s/1.pkg", typ=bib.TYP_UPDATE, app_ver="01.01")
        zwei = _e(pfad="/s/2.pkg", typ=bib.TYP_UPDATE, app_ver="01.02")
        self.assertEqual([], bib.duplikate([eins, zwei]))

    def test_patches_ohne_basis(self) -> None:
        basis = _e(pfad="/s/b.pkg", title_id="CUSA00001")
        mit = _e(pfad="/s/m.pkg", title_id="CUSA00001", typ=bib.TYP_UPDATE)
        ohne = _e(pfad="/s/o.pkg", title_id="CUSA00002", typ=bib.TYP_UPDATE)
        self.assertEqual(["/s/o.pkg"], [e.pfad for e in bib.patches_ohne_basis([basis, mit, ohne])])

    def test_neuestes_update_und_basis(self) -> None:
        basis = _e(pfad="/s/b.pkg")
        u1 = _e(pfad="/s/1.pkg", typ=bib.TYP_UPDATE, app_ver="01.09")
        u2 = _e(pfad="/s/2.pkg", typ=bib.TYP_UPDATE, app_ver="01.10")
        liste = [basis, u1, u2]
        self.assertEqual("/s/2.pkg", bib.neuestes_update(liste, "CUSA00001").pfad)
        self.assertIsNone(bib.neuestes_update(liste, "CUSA99999"))
        self.assertEqual("/s/b.pkg", bib.passendes_basisspiel(liste, u2).pfad)
        self.assertIsNone(bib.passendes_basisspiel([u1], u1))


class AusgabeTests(unittest.TestCase):

    def test_csv_hat_bom_und_semikolon(self) -> None:
        with tempfile.TemporaryDirectory() as wo:
            pfad = os.path.join(wo, "liste.csv")
            n = bib.als_csv([_e(titel="Pokémon; Teil 2")], pfad)
            roh = open(pfad, "rb").read()
            self.assertTrue(roh.startswith(b"\xef\xbb\xbf"))
            zeilen = list(csv.reader(open(pfad, encoding="utf-8-sig"), delimiter=";"))
        self.assertEqual(1, n)
        self.assertEqual(list(bib.SPALTEN_CSV), zeilen[0])
        self.assertEqual("Pokémon; Teil 2", zeilen[1][1])


if __name__ == "__main__":
    unittest.main()
