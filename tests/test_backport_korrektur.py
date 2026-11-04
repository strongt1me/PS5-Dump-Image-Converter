# -*- coding: utf-8 -*-
"""BACKPORT-Zusaetze: Stubs fuer unaufgeloeste Importe und Korrekturprofile (``backport_korrektur``).

Die Tests bauen ein kleines ELF mit PLT, Relocations und Symbolen selbst, so dass alles ohne Originaldateien
pruefbar ist. Dazu ein Waechter gegen die echten Dateien von Anno 117 (uebersprungen, wenn sie fehlen): Das Profil muss
auf das Original passen und das Ergebnis muss dem am Geraet bestaetigten Stand (Test Z3, 04.11.2026) gleichen.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("backport_korrektur")

from ps5_validator.utils import ps5_backport as bp          # noqa: E402
from ps5_validator.utils import backport_korrektur as bk    # noqa: E402

BASIS = 0x4000           # wie bei echten Modulen: das erste Segment beginnt hinter dem ELF-Kopf (VA 0 = Offset 0x4000)
ANFANG = 0x100
SCHLUSS = 16             # kleines Schlusssegment: Nach ihm richtet sich die Laenge des entpackten ELF


def baue_elf(importe, code: bytes = b"") -> "tuple[bytes, dict]":
    """Ein ELF mit PLT-Importen. ``importe``: Liste ``(Bibliothek, NID, schwach)``.

    Alles liegt in einem Segment: virtuelle Adresse + ``BASIS`` = Dateioffset. Rueckgabe: (Bytes, Info) mit ``plt``
    (Index -> Dateioffset), ``plt_va``, ``got`` (virtuelle Adressen), ``code`` (Dateioffset), ``code_va``.
    """
    bibliotheken: list[str] = []
    for lib, _nid, _schwach in importe:
        if lib not in bibliotheken:
            bibliotheken.append(lib)
    strtab = bytearray(b"\0")
    lib_namen = {}
    for lib in bibliotheken:
        lib_namen[lib] = len(strtab)
        strtab += lib.encode("latin1") + b"\0"
    sym_namen = []
    for lib, nid, _schwach in importe:
        sym_namen.append(len(strtab))
        kennzahl = bibliotheken.index(lib)
        strtab += ("%s#%s#A" % (nid, bp.NID_ALPHABET[kennzahl])).encode("latin1") + b"\0"
    n = len(importe)

    def aufrunden(x, a):
        return (x + a - 1) // a * a

    tags = [(0x61000049, (bibliotheken.index(lib) << 48) | lib_namen[lib]) for lib in bibliotheken]
    dyn_off = ANFANG
    dyn_groesse = (len(tags) + 7 + 1) * 16
    symtab_off = aufrunden(dyn_off + dyn_groesse, 8)
    strtab_off = symtab_off + 24 * (n + 1)
    rela_off = aufrunden(strtab_off + len(strtab), 8)
    plt_off = aufrunden(rela_off + 24 * n, 16)
    got_off = aufrunden(plt_off + 16 * n, 8)
    code_off = aufrunden(got_off + 8 * n, 16)
    gesamt = code_off + len(code)

    tags += [(bk.DT_SYMTAB, symtab_off), (bk.DT_STRTAB, strtab_off), (bk.DT_STRSZ, len(strtab)),
             (bk.DT_JMPREL, rela_off), (bk.DT_PLTRELSZ, 24 * n), (bk.DT_PLTREL, bk.DT_RELA), (0, 0)]
    puffer = bytearray(BASIS + gesamt + SCHLUSS)
    puffer[0:64] = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01\x09" + b"\0" * 8, 3, 0x3E, 1, 0, 0x40, 0, 0,
                               0x40, 0x38, 3, 0x40, 0, 0)
    # Das Ende des entpackten ELF richtet sich nach dem LETZTEN Programmkopf - das grosse Segment muss zuletzt stehen.
    puffer[0x40:0x40 + 0x38] = struct.pack("<2I6Q", 2, 6, BASIS + dyn_off, dyn_off, dyn_off, dyn_groesse, dyn_groesse, 8)
    puffer[0x78:0x78 + 0x38] = struct.pack("<2I6Q", 1, 5, BASIS, 0, 0, gesamt, gesamt, 0x4000)
    puffer[0xB0:0xB0 + 0x38] = struct.pack("<2I6Q", 4, 4, BASIS + gesamt, 0, 0, SCHLUSS, SCHLUSS, 1)
    for i, (tag, wert) in enumerate(tags):
        struct.pack_into("<QQ", puffer, BASIS + dyn_off + 16 * i, tag, wert)
    for i, (lib, nid, schwach) in enumerate(importe):
        struct.pack_into("<IBBHQQ", puffer, BASIS + symtab_off + 24 * (i + 1), sym_namen[i], 0x22 if schwach else 0x12, 0, 0, 0, 0)
    puffer[BASIS + strtab_off:BASIS + strtab_off + len(strtab)] = strtab
    plt, plt_va, got = {}, {}, {}
    for i in range(n):
        va, g = plt_off + 16 * i, got_off + 8 * i
        puffer[BASIS + va:BASIS + va + 16] = (b"\xff\x25" + struct.pack("<i", g - (va + 6)) + b"\x68" + struct.pack("<I", i)
                              + b"\xe9" + struct.pack("<i", -(va + 16)))
        struct.pack_into("<QQq", puffer, BASIS + rela_off + 24 * i, g, ((i + 1) << 32) | bk.R_JUMP_SLOT, 0)
        plt[i], plt_va[i], got[i] = BASIS + va, va, g
    puffer[BASIS + code_off:BASIS + code_off + len(code)] = code
    return bytes(puffer), {"plt": plt, "plt_va": plt_va, "got": got, "code": BASIS + code_off, "code_va": code_off}


IMPORTE = [("libkernel", "AAAAAAAAAAA", False), ("libkernel", "NH6xARDOVv8", False),
           ("libSceAcm", "BBBBBBBBBBB", False), ("libSceFoo", "CCCCCCCCCCC", True),
           ("libSceFoo", "DDDDDDDDDDD", False)]
CODE = bytes.fromhex("90 90 75 26 48 c7 85 78 ff ff ff ff ff ff ff 90".replace(" ", ""))


def _elf():
    return baue_elf(IMPORTE, CODE)


class PltTests(unittest.TestCase):

    def test_alle_importe_mit_ihrem_eintrag_gefunden(self):
        elf, info = _elf()
        eintraege = bk.plt_eintraege(elf)
        self.assertEqual([(e.bibliothek, e.nid) for e in eintraege], [(l, n) for l, n, _s in IMPORTE])
        for e in eintraege:
            self.assertEqual(e.plt_offset, info["plt"][e.index])
            self.assertEqual(e.plt_va, info["plt_va"][e.index])
            self.assertEqual(e.got_va, info["got"][e.index])
        self.assertEqual([e.schwach for e in eintraege], [s for _l, _n, s in IMPORTE])

    def test_kein_elf_oder_ohne_dynamik_ergibt_nichts(self):
        self.assertEqual(bk.plt_eintraege(b""), [])
        self.assertEqual(bk.plt_eintraege(b"MZ" + b"\0" * 200), [])
        elf, _ = _elf()
        ohne = bytearray(elf)
        ohne[0x78:0x78 + 4] = struct.pack("<I", 0)         # PT_DYNAMIC -> PT_NULL
        self.assertEqual(bk.plt_eintraege(bytes(ohne)), [])

    def test_ein_eintrag_mit_falschem_got_wird_nicht_geraten(self):
        """Der Stub muss genau dorthin springen, wohin die Relocation zeigt - sonst ist er nicht der Eintrag."""
        elf, info = _elf()
        kaputt = bytearray(elf)
        va = info["plt"][1]
        kaputt[va + 2:va + 6] = struct.pack("<i", 0x1234)
        namen = {(e.bibliothek, e.nid) for e in bk.plt_eintraege(bytes(kaputt))}
        self.assertNotIn(("libkernel", "NH6xARDOVv8"), namen)
        self.assertIn(("libkernel", "AAAAAAAAAAA"), namen)

    def test_va_zu_offset(self):
        elf, info = _elf()
        self.assertEqual(bk.va_zu_offset(elf, info["code_va"]), info["code"])
        self.assertIsNone(bk.va_zu_offset(elf, len(elf) + 10))
        self.assertIsNone(bk.va_zu_offset(elf, len(elf) - BASIS - 2, 4), "ueber das Segmentende hinaus")


class StubTests(unittest.TestCase):

    def test_standardstub_ersetzt_nur_den_anfang_des_eintrags(self):
        elf, info = _elf()
        neu, erg = bk.stubs_setzen(elf, {("libSceAcm", "BBBBBBBBBBB"): None})
        va = info["plt"][2]
        self.assertEqual(neu[va:va + 3], bytes.fromhex("31c0c3"))
        self.assertEqual(neu[va + 3:va + 16], elf[va + 3:va + 16])
        self.assertEqual(neu[:va], elf[:va])
        self.assertEqual(neu[va + 16:], elf[va + 16:])
        self.assertEqual([(e.nid, e.art, e.status) for e in erg], [("BBBBBBBBBBB", "standard", bk.STATUS_GESETZT)])

    def test_ausnahme_nh6_schreibt_beide_ausgaben(self):
        """Der Aufrufer von NH6xARDOVv8 liest zwei Ausgabeparameter (rdi, rsi); das Original schreibt -1 hinein."""
        elf, info = _elf()
        neu, erg = bk.stubs_setzen(elf, {("libkernel", "NH6xARDOVv8"): None})
        va = info["plt"][1]
        self.assertEqual(neu[va:va + 15], bytes.fromhex("c707ffffffffc706ffffffff31c0c3"))
        self.assertEqual(len(bk.STUB_AUSGABEN_MINUS1.bytes_), 15)
        self.assertEqual(erg[0].art, "ausgaben_minus1")
        # dieselbe NID in einer anderen Bibliothek bekommt den Standard
        self.assertEqual(bk.stub_art("libFremd", "NH6xARDOVv8"), bk.STUB_STANDARD)

    def test_zweiter_lauf_erkennt_gesetzte_stubs(self):
        """Der Stub ueberschreibt den Anfang des Eintrags; ohne Nachsuche waere er danach unauffindbar."""
        elf, info = _elf()
        ziele = {("libkernel", "NH6xARDOVv8"): None, ("libSceAcm", "BBBBBBBBBBB"): None,
                 ("libkernel", "AAAAAAAAAAA"): None}
        neu, _ = bk.stubs_setzen(elf, ziele)
        nochmal, erg = bk.stubs_setzen(neu, ziele)
        self.assertIs(nochmal, neu)
        self.assertEqual({e.status for e in erg}, {bk.STATUS_BEREITS})
        self.assertEqual(len(erg), 3)

    def test_schwacher_import_bleibt_unberuehrt(self):
        elf, _ = _elf()
        neu, erg = bk.stubs_setzen(elf, {("libSceFoo", "CCCCCCCCCCC"): None})
        self.assertIs(neu, elf)
        self.assertEqual(erg, [])
        neu, erg = bk.stubs_setzen(elf, {("libSceFoo", "CCCCCCCCCCC"): None}, schwache_auslassen=False)
        self.assertEqual(erg[0].status, bk.STATUS_GESETZT)

    def test_unbekanntes_ziel_taucht_nicht_auf(self):
        elf, _ = _elf()
        neu, erg = bk.stubs_setzen(elf, {("libkernel", "ZZZZZZZZZZZ"): None})
        self.assertIs(neu, elf)
        self.assertEqual(erg, [])

    def test_gesetzter_stub_anderer_art_wird_gemeldet_nicht_ueberschrieben(self):
        elf, info = _elf()
        neu, _ = bk.stubs_setzen(elf, {("libkernel", "NH6xARDOVv8"): "standard"})
        wieder, erg = bk.stubs_setzen(neu, {("libkernel", "NH6xARDOVv8"): "ausgaben_minus1"})
        self.assertIs(wieder, neu)
        self.assertEqual(erg[0].status, bk.STATUS_ABWEICHEND)

    def test_luecken_neutralisieren_nur_was_die_datei_importiert_und_nur_lib(self):
        elf, info = _elf()
        luecken = {"libkernel": ["NH6xARDOVv8", "NICHT-IMPORT"], "libSceAcm": ["BBBBBBBBBBB"],
                   "ulobjmgr": ["DDDDDDDDDDD"], "libSceFremd": ["EEEEEEEEEEE"]}
        neu, erg = bk.luecken_neutralisieren(elf, luecken)
        self.assertEqual({(e.bibliothek, e.nid) for e in erg},
                         {("libkernel", "NH6xARDOVv8"), ("libSceAcm", "BBBBBBBBBBB")})
        va = info["plt"][4]       # libSceFoo DDDDDDDDDDD steht nicht unter "ulobjmgr" in der Datei, bleibt ganz
        self.assertEqual(neu[va:va + 16], elf[va:va + 16])

    def test_nie_liste_hat_vorrang(self):
        elf, _ = _elf()
        alt = bk.STUB_NIE
        bk.STUB_NIE = frozenset({("libSceAcm", "BBBBBBBBBBB")})
        try:
            neu, erg = bk.luecken_neutralisieren(elf, {"libSceAcm": ["BBBBBBBBBBB"]})
        finally:
            bk.STUB_NIE = alt
        self.assertIs(neu, elf)
        self.assertEqual(erg, [])


def _profil_dict(sha: str, **zusatz) -> dict:
    d = {
        "format": 1, "titel_id": "PPSA00001", "name": "Test", "fassung": "01.000", "firmware": [4],
        "dateien": [{
            "pfad": "eboot.bin", "sha256_elf": sha,
            "patches": [
                {"zweck": "a", "va": hex(0), "alt": "7526", "neu": "eb26"},
            ],
            "plt_stubs": [{"bibliothek": "libkernel", "nid": "NH6xARDOVv8", "art": "ausgaben_minus1"},
                          {"bibliothek": "libSceAcm", "nid": "BBBBBBBBBBB"}],
        }],
    }
    d.update(zusatz)
    return d


def _gueltiges_profil(elf: bytes, info: dict):
    d = _profil_dict(hashlib.sha256(elf).hexdigest())
    stelle = info["code"] + 2           # Dateioffset von "75 26" im Codebereich
    d["dateien"][0]["patches"][0]["va"] = hex(stelle - BASIS)
    return bk.profil_aus_dict(d, "test"), stelle


class ProfilPruefungTests(unittest.TestCase):

    def setUp(self):
        self.elf, self.info = _elf()
        self.sha = hashlib.sha256(self.elf).hexdigest()

    def _fehler(self, d):
        with self.assertRaises(bk.ProfilFehler):
            bk.profil_aus_dict(d)

    def test_gueltiges_profil(self):
        profil = bk.profil_aus_dict(_profil_dict(self.sha))
        self.assertEqual(profil.titel_id, "PPSA00001")
        self.assertEqual(profil.firmware, (4,))
        datei = profil.dateien[0]
        self.assertEqual(datei.patches[0].alt, b"\x75\x26")
        self.assertEqual([s.art for s in datei.stubs], ["ausgaben_minus1", "standard"])

    def test_form_und_werte_werden_streng_geprueft(self):
        self._fehler([])
        self._fehler(_profil_dict(self.sha, format=2))
        self._fehler(_profil_dict(self.sha, titel_id="anno"))
        self._fehler(_profil_dict(self.sha, firmware=[]))
        self._fehler(_profil_dict(self.sha, firmware=["4"]))
        self._fehler(_profil_dict(self.sha, dateien=[]))
        self._fehler(_profil_dict("abc"))
        self._fehler(_profil_dict(self.sha.upper() + "0"))

    def test_pfade_nur_relativ_im_spielordner(self):
        for pfad in ("/eboot.bin", "C:/x/eboot.bin", "../eboot.bin", "sce_module/../../x", "a//b", ""):
            d = _profil_dict(self.sha)
            d["dateien"][0]["pfad"] = pfad
            with self.subTest(pfad=pfad):
                self._fehler(d)

    def test_doppelter_pfad(self):
        d = _profil_dict(self.sha)
        d["dateien"].append(copy.deepcopy(d["dateien"][0]))
        d["dateien"][1]["pfad"] = "EBOOT.BIN"
        self._fehler(d)

    def test_patchwerte(self):
        for feld, wert in (("va", "xyz"), ("alt", "7"), ("alt", ""), ("neu", "eb"), ("neu", "7526")):
            d = _profil_dict(self.sha)
            d["dateien"][0]["patches"][0][feld] = wert
            with self.subTest(feld=feld, wert=wert):
                self._fehler(d)

    def test_ueberlappende_aenderungen(self):
        d = _profil_dict(self.sha)
        d["dateien"][0]["patches"].append({"zweck": "b", "va": "0x1", "alt": "2600", "neu": "2601"})
        self._fehler(d)

    def test_stubwerte(self):
        for stub in ({"bibliothek": "", "nid": "AAAAAAAAAAA"}, {"bibliothek": "libX", "nid": "kurz"},
                     {"bibliothek": "libX", "nid": "AAAAAAAAAAA", "art": "gibts_nicht"}):
            d = _profil_dict(self.sha)
            d["dateien"][0]["plt_stubs"] = [stub]
            with self.subTest(stub=stub):
                self._fehler(d)

    def test_datei_ohne_aenderungen(self):
        d = _profil_dict(self.sha)
        d["dateien"][0]["patches"] = []
        d["dateien"][0]["plt_stubs"] = []
        self._fehler(d)


class ProfilLadenTests(unittest.TestCase):

    def test_kaputte_datei_wird_gemeldet_die_anderen_zaehlen(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "gut.json").write_text(json.dumps(_profil_dict("a" * 64)), encoding="utf-8")
            Path(t, "kaputt.json").write_text("{nicht json", encoding="utf-8")
            Path(t, "falsch.json").write_text(json.dumps({"format": 9}), encoding="utf-8")
            Path(t, "notiz.txt").write_text("egal", encoding="utf-8")
            profile, fehler = bk.profile_laden([t, os.path.join(t, "gibt-es-nicht"), ""])
        self.assertEqual([p.titel_id for p in profile], ["PPSA00001"])
        self.assertEqual(len(fehler), 2)
        self.assertTrue(any(f.startswith("kaputt.json") for f in fehler))
        self.assertTrue(any(f.startswith("falsch.json") for f in fehler))

    def test_utf8_mit_bom(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "bom.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(_profil_dict("a" * 64)).encode("utf-8"))
            profile, fehler = bk.profile_laden([t])
        self.assertEqual((len(profile), fehler), (1, []))

    def test_mitgeliefertes_anno_profil_ist_gueltig(self):
        profile, fehler = bk.profile_laden([str(PROJEKT / "Backport_Fakelibs" / bk.PROFIL_ORDNER)])
        self.assertEqual(fehler, [])
        anno = [p for p in profile if p.titel_id == "PPSA23559"]
        self.assertEqual(len(anno), 1)
        self.assertEqual(anno[0].firmware, (4,))
        daten = {pfad_.pfad: (len(pfad_.patches), len(pfad_.stubs)) for pfad_ in anno[0].dateien}
        self.assertEqual(daten, {"eboot.bin": (2, 5), "sce_module/libc.prx": (0, 7)})
        # Jeder Eintrag nennt seinen Zweck - ein Profil ohne Begruendung ist nicht nachpruefbar.
        for datei in anno[0].dateien:
            for patch in datei.patches:
                self.assertTrue(patch.zweck.strip())


class ProfilAnwendenTests(unittest.TestCase):

    def setUp(self):
        self.elf, self.info = _elf()
        self.sha = hashlib.sha256(self.elf).hexdigest()
        self.profil, self.stelle = _gueltiges_profil(self.elf, self.info)
        self.datei = self.profil.dateien[0]

    def test_passende_datei_wird_ganz_geaendert(self):
        neu, erg = bk.profil_datei_anwenden(self.elf, self.sha, self.datei)
        self.assertEqual((erg.status, erg.patches, erg.stubs), (bk.P_ANGEWENDET, 1, 2))
        self.assertEqual(neu[self.stelle:self.stelle + 2], b"\xeb\x26")
        va_nh6, va_acm = self.info["plt"][1], self.info["plt"][2]
        self.assertEqual(neu[va_nh6:va_nh6 + 15], bk.STUB_AUSGABEN_MINUS1.bytes_)
        self.assertEqual(neu[va_acm:va_acm + 3], bk.STUB_STANDARD.bytes_)
        geaendert = [i for i in range(len(self.elf)) if self.elf[i] != neu[i]]
        erlaubt = set(range(self.stelle, self.stelle + 2)) | set(range(va_nh6, va_nh6 + 15)) | set(range(va_acm, va_acm + 3))
        self.assertTrue(set(geaendert) <= erlaubt, "ausserhalb der genannten Stellen wurde etwas veraendert")

    def test_zweiter_lauf_ist_bereits_angewendet(self):
        neu, _ = bk.profil_datei_anwenden(self.elf, self.sha, self.datei)
        sha_neu = hashlib.sha256(neu).hexdigest()
        nochmal, erg = bk.profil_datei_anwenden(neu, sha_neu, self.datei)
        self.assertIs(nochmal, neu)
        self.assertEqual((erg.status, erg.patches, erg.stubs), (bk.P_BEREITS, 1, 2))

    def test_andere_fassung_bleibt_unveraendert(self):
        """SHA-256 weicht ab, die Stellen tragen den alten Zustand: nicht anfassen."""
        neu, erg = bk.profil_datei_anwenden(self.elf, "0" * 64, self.datei)
        self.assertIs(neu, self.elf)
        self.assertEqual(erg.status, bk.P_SHA)

    def test_stimmt_die_sha_aber_nicht_der_alte_zustand_wird_nichts_geschrieben(self):
        kaputt = bytearray(self.elf)
        kaputt[self.stelle + 1] = 0x99                     # die alten Bytes stehen dort nicht
        neu, erg = bk.profil_datei_anwenden(bytes(kaputt), self.sha, self.datei)
        self.assertEqual((erg.status, erg.stelle), (bk.P_BYTES, "0x%X" % (self.stelle - BASIS)))
        self.assertEqual(neu, bytes(kaputt), "ganz oder gar nicht - auch die Stubs duerfen nicht gesetzt sein")

    def test_stub_im_zustand_unbekannt_wird_nichts_geschrieben(self):
        kaputt = bytearray(self.elf)
        va = self.info["plt"][2]
        kaputt[va:va + 2] = b"\x90\x90"                    # weder Sprung noch Stub
        neu, erg = bk.profil_datei_anwenden(bytes(kaputt), self.sha, self.datei)
        self.assertIn(erg.status, (bk.P_STUB, bk.P_BYTES))
        self.assertEqual(neu, bytes(kaputt))

    def test_adresse_ausserhalb(self):
        d = _profil_dict(self.sha)
        d["dateien"][0]["patches"][0]["va"] = hex(len(self.elf) + 0x1000)
        pd = bk.profil_aus_dict(d).dateien[0]
        neu, erg = bk.profil_datei_anwenden(self.elf, self.sha, pd)
        self.assertEqual(erg.status, bk.P_ADRESSE)
        self.assertIs(neu, self.elf)

    def test_fehlender_import(self):
        d = _profil_dict(self.sha)
        d["dateien"][0]["patches"][0]["va"] = hex(self.stelle - BASIS)
        d["dateien"][0]["plt_stubs"] = [{"bibliothek": "libkernel", "nid": "ZZZZZZZZZZZ"}]
        pd = bk.profil_aus_dict(d).dateien[0]
        neu, erg = bk.profil_datei_anwenden(self.elf, self.sha, pd)
        self.assertEqual((erg.status, erg.stelle), (bk.P_STUB, "libkernel ZZZZZZZZZZZ"))
        self.assertIs(neu, self.elf)


class VorbereitungTests(unittest.TestCase):

    def test_waehlt_nach_titel_und_firmware_und_hasht_das_original(self):
        elf, info = _elf()
        profil, _ = _gueltiges_profil(elf, info)
        with tempfile.TemporaryDirectory() as t:
            Path(t, "eboot.bin").write_bytes(elf)
            ergebnis = bk.profile_vorbereiten(t, [profil], "PPSA00001", 4)
            self.assertEqual(len(ergebnis.aktiv), 1)
            self.assertEqual(ergebnis.aktiv[0].sha["eboot.bin"], hashlib.sha256(elf).hexdigest())
            self.assertEqual(bk.profile_vorbereiten(t, [profil], "PPSA99999", 4), bk.Vorbereitung((), ()))
            falsche_fw = bk.profile_vorbereiten(t, [profil], "PPSA00001", 7)
            self.assertEqual((falsche_fw.aktiv, len(falsche_fw.uebergangen)), ((), 1))

    def test_fehlende_datei_gibt_leere_sha(self):
        elf, info = _elf()
        profil, _ = _gueltiges_profil(elf, info)
        with tempfile.TemporaryDirectory() as t:
            ergebnis = bk.profile_vorbereiten(t, [profil], "PPSA00001", 4)
        self.assertEqual(ergebnis.aktiv[0].sha["eboot.bin"], "")


class GesamtlaufTests(unittest.TestCase):
    """``korrekturen_anwenden`` an einem Dump auf der Platte."""

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.ordner = self.t.name
        self.elf, self.info = _elf()
        self.pfad = os.path.join(self.ordner, "eboot.bin")
        Path(self.pfad).write_bytes(self.elf)
        self.profil, self.stelle = _gueltiges_profil(self.elf, self.info)
        self.aktive = bk.profile_vorbereiten(self.ordner, [self.profil], "PPSA00001", 4).aktiv

    def _lesen(self):
        return bk.elf_aus_bytes(Path(self.pfad).read_bytes())

    def test_profil_und_stubs_werden_signiert_geschrieben(self):
        bericht = bk.korrekturen_anwenden(
            self.ordner, [self.pfad], aktive=self.aktive, luecken={"libkernel": ["AAAAAAAAAAA"]})
        self.assertEqual(bericht.fehler, [])
        self.assertEqual(bericht.geaendert, ["eboot.bin"])
        self.assertEqual(bp.dateityp(Path(self.pfad).read_bytes()), bp.TYP_SELF)
        elf = self._lesen()
        self.assertEqual(elf[self.stelle:self.stelle + 2], b"\xeb\x26")
        va = self.info["plt"][0]                            # allgemeine Luecke AAAAAAAAAAA
        self.assertEqual(elf[va:va + 3], bk.STUB_STANDARD.bytes_)
        self.assertEqual([(e.status) for _p, e in bericht.profile], [bk.P_ANGEWENDET])
        # die allgemeine Luecke AAAA und die beiden Stubs des Profils (NH6x, BBBB)
        self.assertEqual(bericht.neutralisiert, {("libkernel", "AAAAAAAAAAA"), ("libkernel", "NH6xARDOVv8"),
                                                 ("libSceAcm", "BBBBBBBBBBB")})
        self.assertEqual([n for n in os.listdir(self.ordner)], ["eboot.bin"], "keine Zwischendatei darf liegen bleiben")

    def test_zweiter_lauf_aendert_nichts_mehr(self):
        bk.korrekturen_anwenden(self.ordner, [self.pfad], aktive=self.aktive, luecken={"libkernel": ["AAAAAAAAAAA"]})
        vorher = Path(self.pfad).read_bytes()
        aktive = bk.profile_vorbereiten(self.ordner, [self.profil], "PPSA00001", 4).aktiv
        bericht = bk.korrekturen_anwenden(
            self.ordner, [self.pfad], aktive=aktive, luecken={"libkernel": ["AAAAAAAAAAA"]})
        self.assertEqual(Path(self.pfad).read_bytes(), vorher)
        self.assertEqual(bericht.geaendert, [])
        self.assertEqual([e.status for _p, e in bericht.profile], [bk.P_BEREITS])
        self.assertEqual({s.status for _r, s in bericht.stubs}, {bk.STATUS_BEREITS})

    def test_ohne_profil_und_ohne_luecken_wird_nichts_gelesen(self):
        bericht = bk.korrekturen_anwenden(self.ordner, [os.path.join(self.ordner, "gibt-es-nicht")])
        self.assertEqual((bericht.fehler, bericht.geaendert), ([], []))

    def test_schreibfehler_laesst_die_datei_wie_sie_war_und_meldet_ihn(self):
        def kaputt(_pfad, _daten):
            raise OSError("Platte voll")

        bericht = bk.korrekturen_anwenden(
            self.ordner, [self.pfad], aktive=self.aktive, luecken={"libkernel": ["AAAAAAAAAAA"]}, schreiben=kaputt)
        self.assertEqual(Path(self.pfad).read_bytes(), self.elf)
        self.assertEqual(bericht.geaendert, [])
        self.assertEqual(bericht.fehler, [("eboot.bin", "Platte voll")])
        self.assertEqual([e.status for _p, e in bericht.profile], [bk.P_SCHREIBEN])
        self.assertEqual({s.status for _r, s in bericht.stubs}, {bk.STATUS_FEHLT})
        self.assertEqual(bericht.neutralisiert, set(), "was nicht geschrieben wurde, ist nicht neutralisiert")

    def test_abbruch_zwischen_zwei_dateien(self):
        bericht = bk.korrekturen_anwenden(
            self.ordner, [self.pfad], aktive=self.aktive, luecken={"libkernel": ["AAAAAAAAAAA"]},
            laeuft=lambda: False)
        self.assertEqual(Path(self.pfad).read_bytes(), self.elf)
        self.assertEqual(bericht.geaendert, [])

    def test_datei_die_kein_elf_ist(self):
        Path(self.pfad).write_bytes(b"kein ELF " * 20)
        bericht = bk.korrekturen_anwenden(self.ordner, [self.pfad], aktive=self.aktive)
        self.assertEqual([e.status for _p, e in bericht.profile], [bk.P_DATEI])
        self.assertEqual(Path(self.pfad).read_bytes(), b"kein ELF " * 20)

    def test_profil_greift_nicht_bei_anderer_fassung(self):
        """Eine andere Fassung der Datei (andere SHA-256) wird nicht angefasst, auch wenn die Stellen passen."""
        anders = bytearray(self.elf)
        anders[-1] ^= 0xFF
        Path(self.pfad).write_bytes(bytes(anders))
        aktive = bk.profile_vorbereiten(self.ordner, [self.profil], "PPSA00001", 4).aktiv
        bericht = bk.korrekturen_anwenden(self.ordner, [self.pfad], aktive=aktive)
        self.assertEqual([e.status for _p, e in bericht.profile], [bk.P_SHA])
        self.assertEqual(Path(self.pfad).read_bytes(), bytes(anders))


ANNO = Path(r"E:\Game Dumps\PPSA23559-Anno_117_-_Pax_Romana\PPSA23559-app0")


@unittest.skipUnless((ANNO / "sce_module" / "libc.prx").is_file(), "Original-Dump von Anno 117 liegt nicht vor")
class AnnoOriginalTests(unittest.TestCase):
    """Das Profil gegen die echten Originale: passt die SHA-256, sitzen die Stubs, und die Folgen sind die, die am
    Geraet liefen (Test Z3). Alles nur lesend im Speicher."""

    @classmethod
    def setUpClass(cls):
        profile, _ = bk.profile_laden([str(PROJEKT / "Backport_Fakelibs" / bk.PROFIL_ORDNER)])
        cls.profil = next(p for p in profile if p.titel_id == "PPSA23559")

    def _datei(self, pfad):
        return next(d for d in self.profil.dateien if d.pfad == pfad)

    def test_libc_passt_und_bekommt_sieben_stubs_an_den_gemessenen_stellen(self):
        roh = (ANNO / "sce_module" / "libc.prx").read_bytes()
        sha = bk.elf_sha256(roh)
        pd = self._datei("sce_module/libc.prx")
        self.assertEqual(sha, pd.sha256_elf)
        elf = bk.elf_aus_bytes(roh)
        neu, erg = bk.profil_datei_anwenden(elf, sha, pd)
        self.assertEqual((erg.status, erg.stubs), (bk.P_ANGEWENDET, 7))
        # Offsets aus der REA-Analyse der Anno-Sitzung (ELF-Offsets der sieben PLT-Eintraege)
        for offset in (0x11A8F0, 0x11A910, 0x11A9A0, 0x11AB80, 0x11AB90, 0x11ABA0, 0x11ABB0):
            self.assertEqual(neu[offset:offset + 3], bk.STUB_STANDARD.bytes_, hex(offset))
        unterschiede = sum(1 for a, b in zip(elf, neu) if a != b)
        self.assertLessEqual(unterschiede, 7 * 3)

    def test_eboot_passt_und_die_bytes_stehen_dort_wo_sie_gemessen_wurden(self):
        roh = (ANNO / "eboot.bin").read_bytes()
        sha = bk.elf_sha256(roh)
        pd = self._datei("eboot.bin")
        self.assertEqual(sha, pd.sha256_elf)
        elf = bk.elf_aus_bytes(roh)
        del roh
        neu, erg = bk.profil_datei_anwenden(elf, sha, pd)
        self.assertEqual((erg.status, erg.patches, erg.stubs), (bk.P_ANGEWENDET, 2, 5))
        self.assertEqual(neu[0x179607:0x179609], bytes.fromhex("eb26"))         # VA 0x175607
        self.assertEqual(neu[0x278B3FF:0x278B403], bytes(4))                    # VA 0x27873ff, systemBlocks = 0
        self.assertEqual(neu[0x6DCEBA0:0x6DCEBA0 + 15], bk.STUB_AUSGABEN_MINUS1.bytes_)   # NH6xARDOVv8


if __name__ == "__main__":
    unittest.main()
