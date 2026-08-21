# -*- coding: utf-8 -*-
"""Tests fuer den Backport (SDK herabsetzen, entpacken, neu signieren).

Die Bytelogik wird an einem selbst gebauten ELF geprueft, damit die Tests ohne
Backup laufen. Der Nachweis an echten Dateien lief gesondert: 57 SELF-Dateien
aus fuenf Backups, alle mit erhaltenem Rundlauf.
"""
import io
import os
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils import ps5_backport as bp
from ps5_validator.utils import i18n

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")


# --------------------------------------------------------------------------
# Baukasten fuer ein minimales, aber gueltiges ELF
# --------------------------------------------------------------------------

#: Offsets im gebauten ELF - nachempfunden, wie echte Dumps aufgebaut sind:
#: der Modulkopf liegt *innerhalb* eines PT_LOAD, und der letzte Programmkopf
#: traegt das groesste Offset (daraus ergibt sich die Dateilaenge).
LOAD_OFFSET = 0x4000
LOAD_GROESSE = 0x200
PARAM_IM_SEGMENT = 0x90
COMMENT_OFFSET = LOAD_OFFSET + LOAD_GROESSE      # 0x4200
COMMENT_GROESSE = 0x40
VERSION_OFFSET = COMMENT_OFFSET + COMMENT_GROESSE  # 0x4240
VERSION_DATEN = bytes(range(0x40))


def baue_elf(ps5_sdk=0x09000040, ps4_sdk=0x11590001, *, mit_param=True,
             mit_version=False):
    """Baut ein 64-Bit-ELF mit zwei signierten Segmenten und Modulkopf.

    Aufbau: ELF-Kopf (0x40), Programmkopftabelle ab 0x40, ein PT_LOAD ab 0x4000
    mit dem Modulkopf bei +0x90, dahinter ein PT_SCE_COMMENT und wahlweise ein
    PT_SCE_VERSION als letztes Segment.
    """
    segment = bytearray(LOAD_GROESSE)
    if mit_param:
        # sceModuleParam: Groesse, unbekannt, Kennung, PS4-SDK, PS5-SDK
        p = PARAM_IM_SEGMENT
        struct.pack_into("<I", segment, p + 0x00, 0x20)
        struct.pack_into("<I", segment, p + bp.PARAM_MAGIC_OFFSET, bp.SCE_MODULE_PARAM_MAGIC)
        struct.pack_into("<I", segment, p + bp.PARAM_PS4_SDK_OFFSET, ps4_sdk)
        struct.pack_into("<I", segment, p + bp.PARAM_PS5_SDK_OFFSET, ps5_sdk)

    koepfe = [
        # (typ, flags, offset, vaddr, paddr, filesz, memsz, align)
        (bp.PT_LOAD, 0x5, LOAD_OFFSET, 0x400000, 0, LOAD_GROESSE, LOAD_GROESSE, 0x4000),
    ]
    if mit_param:
        koepfe.append((bp.PT_SCE_MODULE_PARAM, 0x4, LOAD_OFFSET + PARAM_IM_SEGMENT,
                       0x400000 + PARAM_IM_SEGMENT, 0, 0x20, 0x20, 8))
    koepfe.append((bp.PT_SCE_COMMENT, 0x4, COMMENT_OFFSET, 0, 0,
                   COMMENT_GROESSE, 0, 1))
    version_daten = b""
    if mit_version:
        version_daten = VERSION_DATEN
        koepfe.append((bp.PT_SCE_VERSION, 0x4, VERSION_OFFSET, 0, 0,
                       len(version_daten), len(version_daten), 1))

    phnum = len(koepfe)
    phoff = 0x40
    gesamt = (VERSION_OFFSET + len(version_daten) if mit_version
              else COMMENT_OFFSET + COMMENT_GROESSE)
    puffer = bytearray(gesamt)

    struct.pack_into(bp.ELF_HEADER_FMT, puffer, 0, b"\x7fELF", 2, 1, 1, 0, 0, 0)
    struct.pack_into(
        bp.ELF_HEADER_EX_FMT, puffer, 16,
        0xFE10,          # ET_SCE_DYNAMIC
        0x3E,            # EM_X86_64
        1,               # EV_CURRENT
        0x400000,        # entry
        phoff, 0, 0,     # phoff, shoff, flags
        0x40,            # ehsize
        bp.PHDR_SIZE, phnum,
        0x40, 0, 0)      # shentsize, shnum, shstridx

    for i, k in enumerate(koepfe):
        struct.pack_into(bp.PHDR_FMT, puffer, phoff + i * bp.PHDR_SIZE, *k)

    puffer[LOAD_OFFSET:LOAD_OFFSET + len(segment)] = segment
    puffer[COMMENT_OFFSET:COMMENT_OFFSET + COMMENT_GROESSE] = bytes(
        range(COMMENT_GROESSE))
    if version_daten:
        puffer[VERSION_OFFSET:VERSION_OFFSET + len(version_daten)] = version_daten
    return bytes(puffer)


class ErkennungTests(unittest.TestCase):
    """Dateityp und Kandidatenauswahl."""

    def test_elf_erkannt(self):
        self.assertEqual(bp.dateityp(baue_elf()), bp.TYP_ELF)

    def test_beide_self_kennungen(self):
        for kennung in (bp.MAGIC_SELF_A, bp.MAGIC_SELF_B):
            daten = struct.pack("<I", kennung) + b"\0" * 60
            self.assertEqual(bp.dateityp(daten), bp.TYP_SELF, hex(kennung))

    def test_muell_ist_unbekannt(self):
        self.assertEqual(bp.dateityp(b"nicht viel"), bp.TYP_UNBEKANNT)
        self.assertEqual(bp.dateityp(b""), bp.TYP_UNBEKANNT)
        self.assertEqual(bp.dateityp(None), bp.TYP_UNBEKANNT)

    def test_gestripptes_elf(self):
        # Gleiches ELF, aber ohne Kennung am Anfang.
        roh = bytearray(baue_elf())
        roh[0:4] = b"\0\0\0\0"
        self.assertEqual(bp.dateityp(bytes(roh)), bp.TYP_ELF_GESTRIPPT)

    def test_kandidatennamen(self):
        for name in ("eboot.bin", "EBOOT.BIN", "libc.prx", "x.sprx", "a/b/c.PRX"):
            self.assertTrue(bp.ist_kandidat(name), name)
        for name in ("param.json", "icon0.png", "eboot.bin.bak", "x.elf"):
            self.assertFalse(bp.ist_kandidat(name), name)


class OrdnerTests(unittest.TestCase):
    """kandidaten() sammelt rekursiv und laesst fakelib aus."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bp_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _lege_an(self, *teile):
        pfad = os.path.join(self.tmp, *teile)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with io.open(pfad, "wb") as fh:
            fh.write(b"x")
        return pfad

    def test_rekursiv_und_sortiert(self):
        self._lege_an("eboot.bin")
        self._lege_an("sce_module", "libc.prx")
        self._lege_an("Media", "Plugins", "a.sprx")
        self._lege_an("sce_sys", "param.json")
        gefunden = [os.path.relpath(p, self.tmp) for p in bp.kandidaten(self.tmp)]
        self.assertEqual(len(gefunden), 3)
        self.assertEqual(gefunden, sorted(gefunden))
        self.assertNotIn(os.path.join("sce_sys", "param.json"), gefunden)

    def test_fakelib_wird_ausgelassen(self):
        # Die mitgelieferten Bibliotheken passen bereits - sie duerfen nicht
        # noch einmal herabgesetzt werden.
        self._lege_an("eboot.bin")
        self._lege_an(bp.FAKELIB_ORDNER, "libSceAgc.sprx")
        gefunden = [os.path.basename(p) for p in bp.kandidaten(self.tmp)]
        self.assertEqual(gefunden, ["eboot.bin"])

    def test_leerer_ordner(self):
        self.assertEqual(bp.kandidaten(self.tmp), [])
        self.assertEqual(bp.kandidaten(os.path.join(self.tmp, "weg")), [])


class FirmwareTests(unittest.TestCase):
    """SDK-Paare und Schreibweisen."""

    def test_bekannte_paare(self):
        self.assertEqual(bp.sdk_paar(7), (0x07000038, 0x10590001))
        self.assertEqual(bp.sdk_paar(4), (0x04000031, 0x09040001))

    def test_unbekannte_firmware(self):
        with self.assertRaises(bp.BackportFehler):
            bp.sdk_paar(99)

    def test_schreibweise(self):
        self.assertEqual(bp.firmware_text(0x07000038), "7.00")
        self.assertEqual(bp.firmware_text(0x10000040), "10.00")
        self.assertEqual(bp.firmware_text(0x03400027), "3.40")

    def test_nur_herabsetzen(self):
        self.assertTrue(bp.muss_gepatcht_werden(0x09000040, 0x04000031))
        self.assertFalse(bp.muss_gepatcht_werden(0x04000031, 0x09000040))
        self.assertFalse(bp.muss_gepatcht_werden(0x04000031, 0x04000031))

    def test_saetze_nur_fuer_4_bis_7(self):
        self.assertEqual(bp.FIRMWARE_MIT_FAKELIBS, (4, 5, 6, 7))
        self.assertIn(bp.FIRMWARE_STANDARD, bp.FIRMWARE_MIT_FAKELIBS)


class SdkTests(unittest.TestCase):
    """Modulkopf lesen und setzen."""

    def test_lesen(self):
        elf = baue_elf(0x09000040, 0x11590001)
        self.assertEqual(bp.sdk_lesen(elf), (0x09000040, 0x11590001))

    def test_ohne_modulkopf(self):
        with self.assertRaises(bp.SdkNichtGefunden):
            bp.sdk_lesen(baue_elf(mit_param=False))

    def test_setzen_aendert_nur_vier_bytes_je_feld(self):
        elf = baue_elf(0x09000040, 0x11590001)
        neu, alt5, alt4 = bp.sdk_setzen(elf, 0x04000031, 0x09040001)
        self.assertEqual((alt5, alt4), (0x09000040, 0x11590001))
        self.assertEqual(bp.sdk_lesen(neu), (0x04000031, 0x09040001))
        self.assertEqual(len(neu), len(elf))
        abweichungen = sum(1 for a, b in zip(elf, neu) if a != b)
        self.assertLessEqual(abweichungen, 8)

    def test_setzen_ohne_modulkopf(self):
        with self.assertRaises(bp.SdkNichtGefunden):
            bp.sdk_setzen(baue_elf(mit_param=False), 1, 2)

    def test_falsche_kennung_wird_abgelehnt(self):
        # Typtreffer allein genuegt nicht - sonst wuerde ins Leere geschrieben.
        roh = bytearray(baue_elf())
        struct.pack_into("<I", roh, LOAD_OFFSET + PARAM_IM_SEGMENT + bp.PARAM_MAGIC_OFFSET, 0xDEADBEEF)
        with self.assertRaises(bp.SdkNichtGefunden):
            bp.sdk_lesen(bytes(roh))


class SignierenTests(unittest.TestCase):
    """ELF -> SELF und wieder zurueck."""

    def test_ergebnis_ist_ein_self(self):
        sig = bp.elf_signieren(baue_elf())
        self.assertEqual(bp.dateityp(sig), bp.TYP_SELF)
        self.assertEqual(sig[:4], bp.SELF_MAGIC)

    def test_rundlauf_erhaelt_segment_und_sdk(self):
        elf = baue_elf(0x09000040, 0x11590001)
        zurueck = bp.self_zu_elf(bp.elf_signieren(elf))
        self.assertEqual(bp.dateityp(zurueck), bp.TYP_ELF)
        self.assertEqual(len(zurueck), len(elf))
        self.assertEqual(bp.sdk_lesen(zurueck), (0x09000040, 0x11590001))
        self.assertEqual(zurueck[LOAD_OFFSET:COMMENT_OFFSET], elf[LOAD_OFFSET:COMMENT_OFFSET])

    def test_abschnittskoepfe_werden_entfernt(self):
        # Bewusstes Verhalten, wie im Original make_fself.py.
        zurueck = bp.self_zu_elf(bp.elf_signieren(baue_elf()))
        self.assertEqual(struct.unpack_from("<H", zurueck, 0x3C)[0], 0)

    def test_versionssegment_wird_mitgefuehrt(self):
        elf = baue_elf(mit_version=True)
        sig = bp.elf_signieren(elf)
        self.assertTrue(sig.endswith(VERSION_DATEN))

    def test_kopfangaben_sind_stimmig(self):
        sig = bp.elf_signieren(baue_elf())
        anzahl = struct.unpack_from("<H", sig, 0x18)[0]
        # zwei signierte Segmente (PT_LOAD, PT_SCE_COMMENT) -> je Meta + Daten
        self.assertEqual(anzahl, 4)
        self.assertEqual(anzahl % 2, 0)
        # Jedes Paar: erst Meta (Pruefsummen), dann Daten (mit Bloecken)
        meta_props = struct.unpack_from("<Q", sig, 0x20)[0]
        daten_props = struct.unpack_from("<Q", sig, 0x40)[0]
        self.assertTrue((meta_props >> bp.PROPS_HAS_DIGESTS_SHIFT) & 1)
        self.assertFalse((meta_props >> bp.PROPS_HAS_BLOCKS_SHIFT) & 1)
        self.assertTrue((daten_props >> bp.PROPS_HAS_BLOCKS_SHIFT) & 1)

    def test_zu_kurz(self):
        with self.assertRaises(bp.BackportFehler):
            bp.elf_signieren(b"kurz")

    def test_kein_self_beim_entpacken(self):
        with self.assertRaises(bp.BackportFehler):
            bp.self_zu_elf(baue_elf())
        with self.assertRaises(bp.BackportFehler):
            bp.self_zu_elf(b"")

    def test_meta_eintraege_werden_beim_entpacken_uebergangen(self):
        # Ihr segment_index zeigt auf den Partner-Eintrag, nicht auf einen
        # Programmkopf. Werden sie mitkopiert, landen 32 Byte Pruefsumme an
        # falscher Stelle - in einem echten Backup traf das Offset 0.
        elf = baue_elf()
        sig = bytearray(bp.elf_signieren(elf))
        # Meta-Eintrag auf Segmentindex 0 umbiegen: ohne Filter wuerde er
        # jetzt ueber den Anfang des ersten Segments schreiben.
        props = struct.unpack_from("<Q", sig, 0x20)[0]
        props &= ~(bp.PROPS_SEGMENT_INDEX_MASK << bp.PROPS_SEGMENT_INDEX_SHIFT)
        struct.pack_into("<Q", sig, 0x20, props)
        zurueck = bp.self_zu_elf(bytes(sig))
        self.assertEqual(zurueck[0x4000:0x4200], elf[0x4000:0x4200])


class LibcTests(unittest.TestCase):
    """Der Zeichenkettenpatch fuer 6.xx."""

    def test_erkennung_der_datei(self):
        self.assertTrue(bp.ist_libc(r"C:\x\sce_module\libc.prx"))
        self.assertTrue(bp.ist_libc("LIBC.PRX"))
        self.assertFalse(bp.ist_libc("libc.sprx"))
        self.assertFalse(bp.ist_libc("libSceFace.prx"))

    def test_muster_wird_ersetzt(self):
        daten = b"vorne" + bp.LIBC_ALT + b"hinten"
        neu, stelle = bp.libc_patchen(daten)
        self.assertEqual(stelle, 5)
        self.assertIn(bp.LIBC_NEU, neu)
        self.assertNotIn(bp.LIBC_ALT, neu)
        self.assertEqual(len(neu), len(daten))

    def test_bereits_gepatcht(self):
        _neu, stelle = bp.libc_patchen(b"x" + bp.LIBC_NEU)
        self.assertEqual(stelle, -2)

    def test_muster_fehlt(self):
        daten = b"nichts dergleichen"
        neu, stelle = bp.libc_patchen(daten)
        self.assertEqual(stelle, -1)
        self.assertEqual(neu, daten)

    def test_beide_folgen_gleich_lang(self):
        # Sonst verschoebe sich alles dahinter.
        self.assertEqual(len(bp.LIBC_ALT), len(bp.LIBC_NEU))


class AblaufTests(unittest.TestCase):
    """datei_verarbeiten entscheidet richtig und schreibt nichts."""

    def setUp(self):
        self.ziel_ps5, self.ziel_ps4 = bp.sdk_paar(4)

    def test_hoeheres_sdk_wird_herabgesetzt(self):
        quelle = bp.elf_signieren(baue_elf(0x09000040, 0x11590001))
        kennung, neu, grund = bp.datei_verarbeiten(
            quelle, ziel_ps5=self.ziel_ps5, ziel_ps4=self.ziel_ps4)
        self.assertEqual(kennung, bp.ERG_GEPATCHT)
        self.assertEqual(bp.sdk_lesen(bp.self_zu_elf(neu)),
                         (self.ziel_ps5, self.ziel_ps4))
        self.assertIn("9.00", grund)
        self.assertIn("4.00", grund)

    def test_niedrigeres_sdk_bleibt(self):
        quelle = bp.elf_signieren(baue_elf(0x02000009, 0x08050001))
        kennung, neu, _grund = bp.datei_verarbeiten(
            quelle, ziel_ps5=self.ziel_ps5, ziel_ps4=self.ziel_ps4)
        self.assertEqual(kennung, bp.ERG_UEBERSPRUNGEN)
        self.assertEqual(neu, quelle)

    def test_ohne_sdk_bleibt(self):
        quelle = bp.elf_signieren(baue_elf(mit_param=False))
        kennung, neu, _g = bp.datei_verarbeiten(
            quelle, ziel_ps5=self.ziel_ps5, ziel_ps4=self.ziel_ps4)
        self.assertEqual(kennung, bp.ERG_UEBERSPRUNGEN)
        self.assertEqual(neu, quelle)

    def test_fremde_datei_bleibt(self):
        quelle = b"das ist keine ausfuehrbare Datei" * 4
        kennung, neu, _g = bp.datei_verarbeiten(
            quelle, ziel_ps5=self.ziel_ps5, ziel_ps4=self.ziel_ps4)
        self.assertEqual(kennung, bp.ERG_UEBERSPRUNGEN)
        self.assertEqual(neu, quelle)

    def test_ergebnis_ist_immer_signiert(self):
        # Eine unsignierte Datei darf nie herauskommen.
        quelle = bp.elf_signieren(baue_elf(0x09000040, 0x11590001))
        kennung, neu, _g = bp.datei_verarbeiten(
            quelle, ziel_ps5=self.ziel_ps5, ziel_ps4=self.ziel_ps4)
        self.assertEqual(kennung, bp.ERG_GEPATCHT)
        self.assertEqual(bp.dateityp(neu), bp.TYP_SELF)

    def test_rohes_elf_wird_ebenfalls_verarbeitet(self):
        kennung, neu, _g = bp.datei_verarbeiten(
            baue_elf(0x09000040, 0x11590001),
            ziel_ps5=self.ziel_ps5, ziel_ps4=self.ziel_ps4)
        self.assertEqual(kennung, bp.ERG_GEPATCHT)
        self.assertEqual(bp.dateityp(neu), bp.TYP_SELF)

    def test_libc_nur_bei_gesetztem_schalter(self):
        elf = bytearray(baue_elf(0x09000040, 0x11590001))
        elf[LOAD_OFFSET + 0x150:LOAD_OFFSET + 0x150 + len(bp.LIBC_ALT)] = bp.LIBC_ALT
        quelle = bp.elf_signieren(bytes(elf))
        _k, ohne, grund_ohne = bp.datei_verarbeiten(
            quelle, ziel_ps5=self.ziel_ps5, ziel_ps4=self.ziel_ps4,
            libc_zusatz=False, ist_libc_datei=True)
        self.assertNotIn("libc", grund_ohne)
        self.assertIn(bp.LIBC_ALT, bp.self_zu_elf(ohne))

        _k, mit, grund_mit = bp.datei_verarbeiten(
            quelle, ziel_ps5=self.ziel_ps5, ziel_ps4=self.ziel_ps4,
            libc_zusatz=True, ist_libc_datei=True)
        self.assertIn("libc", grund_mit)
        self.assertIn(bp.LIBC_NEU, bp.self_zu_elf(mit))


class FakelibTests(unittest.TestCase):
    """Die mitgelieferten Ersatzbibliotheken."""

    BASIS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "Backport_Fakelibs")

    def test_pfadbau(self):
        self.assertTrue(bp.fakelib_quelle("/x", 7).endswith(
            os.path.join("7", "fakelib")))
        self.assertTrue(bp.fakelib_ziel("/spiel").endswith("fakelib"))

    def test_fehlender_ordner_ist_leer(self):
        self.assertEqual(bp.fakelib_dateien("/gibt/es/nicht", 7), [])

    def test_alle_vier_saetze_liegen_bei(self):
        for fw in bp.FIRMWARE_MIT_FAKELIBS:
            dateien = bp.fakelib_dateien(self.BASIS, fw)
            self.assertTrue(dateien, f"Firmware {fw} ohne Bibliotheken")

    def test_fw7_satz_enthaelt_die_elf_noch_auf_der_platte(self):
        """Die Datei liegt weiter im mitgelieferten Satz - nur nicht mehr im Spiel.

        Frueher hiess dieser Test "enthaelt den Starter" und verlangte die Datei
        in der Kopierliste. Der Name war eine Deutung, kein Beleg: Es ist der
        Payload von PS5 BACKPORK KITCHEN (ET_DYN, Zeichenketten "backpork" und
        "kernel"), und drei der vier Saetze haben sie gar nicht - waere sie
        noetig, waeren Backports auf FW4 bis FW6 alle kaputt. Seit dem Filter
        auf .sprx/.prx wandert sie nicht mehr in das Spiel.
        """
        ordner = bp.fakelib_quelle(self.BASIS, 7)
        self.assertTrue(os.path.isfile(os.path.join(ordner, "ps5-backpork.elf")))
        namen = [os.path.basename(p).lower()
                 for p in bp.fakelib_dateien(self.BASIS, 7)]
        self.assertNotIn("ps5-backpork.elf", namen)


class VerdrahtungTests(unittest.TestCase):
    """Einbindung im Hauptprogramm."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_menueeintrag(self):
        self.assertIn('("titlebar.backport", "_show_backport")', self.quelle)

    def test_modul_eingebunden(self):
        self.assertIn("from ps5_validator.utils import ps5_backport", self.quelle)

    def test_methoden_vorhanden(self):
        for name in ("_show_backport", "_render_backport_window",
                     "_backport_worker", "_backport_fakelib_basis"):
            self.assertIn(f"def {name}(", self.quelle, name)

    def test_original_wird_atomar_ersetzt(self):
        # Erst vollstaendig schreiben, dann umbenennen - nie teilweise.
        self.assertIn('zwischen = pfad + ".neu"', self.quelle)
        self.assertIn("os.replace(zwischen, pfad)", self.quelle)

    def test_sicherung_vor_der_arbeit(self):
        self.assertIn("shutil.copytree(ordner, sicherungsordner)", self.quelle)

    def test_ruecksicherung_wird_abgefragt(self):
        self.assertIn("backport.confirm_message", self.quelle)

    def test_bibliotheken_im_build(self):
        with io.open("PS5ImageConverter_Pro.spec", encoding="utf-8") as fh:
            spec = fh.read()
        self.assertIn("Backport_Fakelibs", spec)


class I18nTests(unittest.TestCase):
    """Jeder benutzte Schluessel existiert in beiden Sprachen."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_benutzte_schluessel_vollstaendig(self):
        benutzt = set(re.findall(r'_t\(\s*["\'](backport\.[a-z_0-9]+)', self.quelle))
        benutzt |= {f"backport.type_{t}" for t in
                    (bp.TYP_SELF, bp.TYP_ELF, bp.TYP_ELF_GESTRIPPT, bp.TYP_UNBEKANNT)}
        benutzt.add("titlebar.backport")
        fehlend = sorted(k for k in benutzt if k not in i18n.STRINGS)
        self.assertEqual(fehlend, [], f"Nicht uebersetzt: {fehlend}")
        for sprache in ("de", "en"):
            luecken = sorted(k for k in benutzt if sprache not in i18n.STRINGS[k])
            self.assertEqual(luecken, [], f"{sprache} fehlt: {luecken}")

    def test_protokollzeilen_enden_mit_umbruch(self):
        for k in ("backport.log_backup", "backport.log_patched",
                  "backport.log_failed", "backport.log_libs"):
            for sprache in ("de", "en"):
                self.assertTrue(i18n.STRINGS[k][sprache].endswith("\n"), f"{k}/{sprache}")

    def test_platzhalter_stimmen_zwischen_den_sprachen(self):
        muster = re.compile(r"\{([a-z_]+)")
        for k, werte in i18n.STRINGS.items():
            if not k.startswith("backport."):
                continue
            self.assertEqual(set(muster.findall(werte["de"])),
                             set(muster.findall(werte["en"])), k)


class FirmwareAnzeigeTests(unittest.TestCase):
    """Die Firmware-Angabe aus param.json ist BCD-kodiert.

    Die Hex-ZEICHEN sind die gedruckten Ziffern, keine Hexzahl: 0x1270...
    heisst 12.70. Frueher entfernte die Zeichenklasse nur das "x" des Praefixes
    "0x" - die fuehrende 0 blieb stehen und verschob alles um eine Stelle. Aus
    0x1001000000000000 (10.01) wurde "01.00.10.00". Eine Rotation bei
    fuehrenden Nullen glich das aus, aber nur bei einstelliger Hauptversion.
    Gemessen an 32 echten Dumps waren 13 davon falsch angezeigt.
    """

    def test_zweistellige_hauptversion(self) -> None:
        for roh, erwartet in (
            ("0x1001000000000000", "10.01.00.00"),
            ("0x1270000000000000", "12.70.00.00"),
            ("0x1120000000000000", "11.20.00.00"),
            ("0x1060000000000000", "10.60.00.00"),
        ):
            with self.subTest(roh=roh):
                self.assertEqual(APP.PS5ConverterGUI._normalize_required_firmware(roh), erwartet)

    def test_einstellige_hauptversion_bleibt_richtig(self) -> None:
        for roh, erwartet in (
            ("0x0900000000000000", "09.00.00.00"),
            ("0x0250000000000000", "02.50.00.00"),
            ("0x0403000000000000", "04.03.00.00"),
            ("0x0100000000000000", "01.00.00.00"),
        ):
            with self.subTest(roh=roh):
                self.assertEqual(APP.PS5ConverterGUI._normalize_required_firmware(roh), erwartet)

    def test_praefix_wird_entfernt(self) -> None:
        """Mit und ohne 0x muss dasselbe herauskommen."""
        self.assertEqual(
            APP.PS5ConverterGUI._normalize_required_firmware("0x1001000000000000"),
            APP.PS5ConverterGUI._normalize_required_firmware("1001000000000000"))

    def test_klartext_bleibt_unangetastet(self) -> None:
        self.assertEqual(
            APP.PS5ConverterGUI._normalize_required_firmware("12.70.00.00"), "12.70.00.00")


class SdkStandTests(unittest.TestCase):
    """Ein Backport aendert nur die ELF-Kopfdaten, nicht die param.json.

    Deshalb ist einem zurueckportierten Dump in den Metadaten nichts anzusehen.
    Auch die Konsole hilft nicht: ShadowMount+ meldet "Spiel backportiert",
    sobald ein fakelib-Ordner eingehaengt wurde - ein AMPR-EMU-Paket loest
    dieselbe Meldung aus, obwohl es nicht zurueckportiert ist.
    """

    def test_typvergleich_nutzt_die_modulkonstante(self) -> None:
        """dateityp() liefert 'self' klein - ein Vergleich mit "SELF" scheitert still."""
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        stelle = quelle.index("def _sdk_stand_lesen")
        block = quelle[stelle:stelle + 2600]
        self.assertIn("ps5_backport.TYP_SELF", block)
        self.assertNotIn('== "SELF"', block)

    def test_konstante_ist_kleingeschrieben(self) -> None:
        from ps5_validator.utils import ps5_backport as bp
        self.assertEqual(bp.TYP_SELF, bp.TYP_SELF.lower())

    def test_zeile_erscheint_im_fenster(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn('("sdk_stand", self._t("info_popup.meta.sdk"))', quelle)
        self.assertIn('self._meta_labels["sdk_stand"].set', quelle)

    def test_beide_texte_sind_zweisprachig(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("info_popup.meta.sdk", "info_popup.sdk_backported"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[schluessel].get(sprache, "").strip())

    def test_hinweis_hat_den_platzhalter(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for sprache in ("de", "en"):
            self.assertIn("{v0}", STRINGS["info_popup.sdk_backported"][sprache])


class FakelibOrdnerwahlTests(unittest.TestCase):
    """fakelib oder fakelib2 - eine Wahl, zwei Fenster, ein gespeicherter Wert.

    Aus der config.ini von ShadowMount+ 1.7alpha6:
        "mount app0/fakelib2 when present, otherwise app0/fakelib, into common/lib"

    Es wird also nur EINER der beiden eingehaengt, und fakelib2 gewinnt. Wuerden
    Backport und AMPR EMU in verschiedene Ordner schreiben, blieb der Inhalt des
    anderen wirkungslos - ohne jede Meldung. Deshalb lesen beide denselben Wert.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")

    # -- Modulebene --------------------------------------------------------

    def test_beide_namen_bekannt(self) -> None:
        self.assertEqual(bp.FAKELIB_ORDNERNAMEN, (bp.FAKELIB_ORDNER, bp.FAKELIB2_ORDNER))
        self.assertEqual(bp.FAKELIB2_ORDNER, "fakelib2")

    def test_zielordner_folgt_der_wahl(self) -> None:
        for wahl, erwartet in (("fakelib", "fakelib"), ("fakelib2", "fakelib2"),
                               ("FAKELIB2", "fakelib2")):
            with self.subTest(wahl=wahl):
                self.assertTrue(bp.fakelib_ziel("D:/Spiel", wahl).endswith(erwartet))

    def test_unsinniger_name_faellt_zurueck(self) -> None:
        """Ein Tippfehler duerfte sonst einen Ordner anlegen, den niemand einhaengt."""
        for wahl in ("fakelib3", "quatsch", "", None):
            with self.subTest(wahl=wahl):
                self.assertTrue(bp.fakelib_ziel("D:/Spiel", wahl).endswith("fakelib"))

    def test_kandidatensuche_ueberspringt_beide_ordner(self) -> None:
        """Der Inhalt beider Ordner passt schon - er darf nicht gepatcht werden."""
        stelle = self.quelle_modul.index("def kandidaten")
        block = self.quelle_modul[stelle:stelle + 900]
        self.assertIn("FAKELIB_ORDNERNAMEN", block)

    @property
    def quelle_modul(self) -> str:
        return (PROJEKT / "ps5_validator" / "utils" / "ps5_backport.py").read_text(
            encoding="utf-8")

    def test_vorhandene_ordner_werden_gemeldet(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            self.assertEqual(bp.fakelib_vorhandene_ordner(ordner), [])
            os.makedirs(os.path.join(ordner, "fakelib"))
            self.assertEqual(bp.fakelib_vorhandene_ordner(ordner), ["fakelib"])
            os.makedirs(os.path.join(ordner, "fakelib2"))
            self.assertEqual(bp.fakelib_vorhandene_ordner(ordner),
                             ["fakelib", "fakelib2"])

    # -- Programmebene -----------------------------------------------------

    def test_die_wahl_steht_in_beiden_fenstern(self) -> None:
        """Einmal im BACKPORT-Fenster, einmal im AMPR EMU Manager."""
        self.assertEqual(self.quelle.count('values=list(ps5_backport.FAKELIB_ORDNERNAMEN)'), 2)
        self.assertEqual(self.quelle.count('self._save_setting("fakelib_variante", wahl)'), 2)

    def test_beide_fenster_nutzen_denselben_schluessel(self) -> None:
        """Genau ein Leser - sonst koennten die Fenster auseinanderlaufen.

        Geprueft wird die Absicht, nicht die Schreibweise: Der Schluessel darf im
        ganzen Programm nur dreimal vorkommen - einmal lesend in
        ``_fakelib_ordnername`` und zweimal schreibend (die zwei Klapplisten).
        """
        self.assertEqual(self.quelle.count('"fakelib_variante"'), 3)
        stelle = self.quelle.index("def _fakelib_ordnername")
        block = self.quelle[stelle:stelle + 1400]
        self.assertIn('"fakelib_variante"', block, "Der Leser sitzt nicht dort")
        # Und er muss eine fehlende _load_setting ueberleben: Tests bauen die
        # Instanz ohne __init__, und eine AttributeError wurde von Aufrufern als
        # "keine Sicherung vorhanden" gedeutet.
        self.assertIn('getattr(self, "_load_setting", None)', block)

    def test_ampr_hat_keinen_festen_ordnernamen_mehr(self) -> None:
        """Zwoelf Stellen bauten den Pfad vorher fest zusammen."""
        self.assertNotIn('/ "fakelib"', self.quelle)
        self.assertNotIn('"fakelib")', self.quelle.replace(
            'ps5_backport.FAKELIB_ORDNER', ""))

    def test_kollisionswarnung_nennt_den_gewinner(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for sprache in ("de", "en"):
            text = STRINGS["fakelib.collision_warning"][sprache]
            self.assertIn("{v0}", text)
            self.assertIn("{v1}", text)

    def test_texte_sind_zweisprachig(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("backport.fakelib_folder_label", "fakelib.folder_chosen",
                           "fakelib.collision_warning", "fakelib.shared_hint"):
            with self.subTest(schluessel=schluessel):
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[schluessel].get(sprache, "").strip())

    def test_umstellen_im_ampr_fenster_liest_den_zustand_neu(self) -> None:
        """Sonst nennt der Zustandstext weiter den alten Ordner."""
        stelle = self.quelle.index("def _ampr_ordner_gewaehlt")
        block = self.quelle[stelle:stelle + 900]
        self.assertIn("_refresh_versions()", block)


class BibliothekssatzFilterTests(unittest.TestCase):
    """Nur Bibliotheken gehoeren in den fakelib-Ordner des Spiels.

    Der mitgelieferte Satz ist wortgleich von PS5 BACKPORK KITCHEN 2.3.1
    uebernommen, und dessen Form1.vb kopiert den Ordner ungefiltert
    (CopyRelative). Im FW7-Satz liegt dadurch eine ps5-backpork.elf - der
    Payload des Werkzeugs selbst, 116 KB, technisch ET_DYN. In den Saetzen FW4
    bis FW6 fehlt sie, es ist also ein Versehen.

    ShadowMount+ haengt den Ordner nach common/lib; der Lader holt Bibliotheken
    nach Namen. Nach der .elf fragt kein Spiel.
    """

    BASIS = str(PROJEKT / "Backport_Fakelibs")

    def test_elf_kommt_nicht_mit(self) -> None:
        namen = [os.path.basename(p) for p in bp.fakelib_dateien(self.BASIS, 7)]
        self.assertNotIn("ps5-backpork.elf", namen)

    def test_uebersprungenes_wird_benannt(self) -> None:
        """Sonst waere die Aussage im Protokoll nicht belegbar."""
        self.assertEqual(bp.fakelib_uebersprungene(self.BASIS, 7), ["ps5-backpork.elf"])

    def test_alle_bibliotheken_kommen_mit(self) -> None:
        for firmware in bp.FIRMWARE_MIT_FAKELIBS:
            with self.subTest(firmware=firmware):
                ordner = bp.fakelib_quelle(self.BASIS, firmware)
                erwartet = {n for n in os.listdir(ordner)
                            if n.lower().endswith(bp.FAKELIB_ENDUNGEN)}
                genommen = {os.path.basename(p)
                            for p in bp.fakelib_dateien(self.BASIS, firmware)}
                self.assertTrue(erwartet <= genommen, f"fehlen: {erwartet - genommen}")

    def test_markierung_bleibt_erhalten(self) -> None:
        """Die leere FW<n>-Datei kostet nichts und verraet den Satz."""
        for firmware in bp.FIRMWARE_MIT_FAKELIBS:
            with self.subTest(firmware=firmware):
                namen = [os.path.basename(p)
                         for p in bp.fakelib_dateien(self.BASIS, firmware)]
                self.assertIn(f"FW{firmware}", namen)

    def test_die_uebrigen_saetze_verlieren_nichts(self) -> None:
        """FW4 bis FW6 enthalten nur .sprx - dort darf sich nichts aendern."""
        for firmware in (4, 5, 6):
            with self.subTest(firmware=firmware):
                self.assertEqual(bp.fakelib_uebersprungene(self.BASIS, firmware), [])

    def test_endungen_sind_die_erwarteten(self) -> None:
        self.assertEqual(bp.FAKELIB_ENDUNGEN, (".sprx", ".prx"))

    def test_meldung_ist_zweisprachig_und_hat_platzhalter(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        eintrag = STRINGS["backport.log_libs_skipped"]
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertIn("{count}", eintrag[sprache])
                self.assertIn("{names}", eintrag[sprache])


class NidTests(unittest.TestCase):
    """Der NID-Algorithmus aus dem backport-helper.

    Nachgerechnet, nicht uebernommen: Ohne diese drei Gegenproben waere die
    ganze Deckungspruefung eine Behauptung.
    """

    def test_bekannte_kennungen(self):
        for name, soll in (("sceKernelLoadStartModule", "wzvqT4UqKX8"),
                           ("sceKernelDlsym", "LwG8g3niqwA"),
                           ("sceKernelAllocateDirectMemory", "rTXw65xmLIA")):
            self.assertEqual(bp.nid_von_name(name), soll, name)

    def test_kennung_ist_elf_zeichen_lang(self):
        for name in ("sceRtcGetCurrentTick", "sceKernelGetOperationMode", "a"):
            self.assertEqual(len(bp.nid_von_name(name)), 11, name)

    def test_symbol_zerlegen(self):
        nid, bib, mod = bp.symbol_zerlegen("N+mr7GjTvr8#E#A")
        self.assertEqual(nid, "N+mr7GjTvr8")
        self.assertEqual(bib, 4)   # 'E' ist der fuenfte Buchstabe -> 4
        self.assertEqual(mod, 0)   # 'A' -> 0, das Modul selbst

    def test_symbol_ohne_kennungen_wird_erkannt(self):
        # Ein Klartextname ist kein PRX-Symbol und darf nicht mitgezaehlt werden.
        _nid, bib, mod = bp.symbol_zerlegen("memcpy")
        self.assertEqual((bib, mod), (-1, -1))


class DeckungTests(unittest.TestCase):
    """Was das Spiel verlangt gegen das, was die Ersatzbibliothek liefert.

    Gebaut am 19.08.2026, nachdem der backport-helper den NID-Algorithmus
    lieferte. Bis dahin hiess "backportiert" nur: Die Dateien liegen im
    Ordner - siehe die Warnung im Kopf von deckung_pruefen.
    """

    FAKELIB = str(PROJEKT / "Backport_Fakelibs" / "7" / "fakelib" / "libSceNpAuth.sprx")

    def setUp(self):
        if not os.path.isfile(self.FAKELIB):
            self.skipTest("Bibliothekssatz FW7 liegt nicht bei")

    def test_echte_bibliothek_wird_gelesen(self):
        symbole = bp.symbole_aus_datei(self.FAKELIB)
        # Die Namen stehen im Modul, nicht im Dateinamen - und genau das ist
        # der Punkt: libSceNpAuth.sprx fuehrt drei Bibliotheken.
        self.assertIn("libSceNpAuth", symbole["exporte"])
        self.assertTrue(symbole["importe"], "Keine Importe gelesen")

    def test_bekannte_funktion_steht_in_der_exporttabelle(self):
        # Der Beweis, dass Kennungsrechnung und Tabellenlesen zusammenpassen.
        symbole = bp.symbole_aus_datei(self.FAKELIB)
        self.assertIn(bp.nid_von_name("sceNpAuthCreateAsyncRequest"),
                      symbole["exporte"]["libSceNpAuth"])

    def test_bibliotheken_werden_nicht_zusammengeworfen(self):
        # libSceNpAuth.sprx fuehrt libSceNpAuth, libSceNpAuthAuthorizedApp und
        # libSceNpAuthCompat. Wuerde man deren Exporte in einen Topf werfen,
        # gaelte ein Symbol als geliefert, das unter anderem Namen steht.
        symbole = bp.symbole_aus_datei(self.FAKELIB)
        namen = set(symbole["export_bibliotheken"].values())
        self.assertGreaterEqual(len(namen), 2, namen)
        mengen = [m for n, m in symbole["exporte"].items() if n != "?"]
        self.assertGreater(len(mengen), 1)
        self.assertNotEqual(mengen[0], mengen[1],
                            "Zwei Bibliotheken mit identischem Export - verdaechtig")

    def test_fehlende_funktion_wird_benannt(self):
        # Kunstlage: Das Spiel verlangt eine Funktion, die die Bibliothek
        # nicht hat. Genau dieser Fall soll auffallen.
        echt = bp.symbole_aus_datei(self.FAKELIB)
        vorhanden = sorted(echt["exporte"]["libSceNpAuth"])[:2]
        fehlt = bp.nid_von_name("sceNpAuthGibtEsNicht")

        class _Falsch:
            @staticmethod
            def lesen(pfad):
                if pfad == "spiel":
                    return {"importe": {"libSceNpAuth": set(vorhanden) | {fehlt}},
                            "exporte": {}, "import_bibliotheken": {},
                            "export_bibliotheken": {}}
                return {"importe": {}, "exporte": {"libSceNpAuth": set(vorhanden)},
                        "import_bibliotheken": {}, "export_bibliotheken": {}}

        alt = bp.symbole_aus_datei
        bp.symbole_aus_datei = _Falsch.lesen
        try:
            bericht = bp.deckung_pruefen(["spiel"], ["lib"])
        finally:
            bp.symbole_aus_datei = alt

        self.assertEqual(bericht["geprueft"], 1)
        self.assertIn("libSceNpAuth", bericht["bibliotheken"])
        self.assertEqual(bericht["bibliotheken"]["libSceNpAuth"]["fehlend"], {fehlt})

    def test_fremde_bibliotheken_sind_kein_befund(self):
        # libkernel kommt von der Konsole. Sie als "fehlend" zu melden waere
        # ein Fehlalarm bei jedem einzelnen Spiel.
        def _lesen(pfad):
            if pfad == "spiel":
                return {"importe": {"libkernel": {"AAAAAAAAAAA"}},
                        "exporte": {}, "import_bibliotheken": {},
                        "export_bibliotheken": {}}
            return {"importe": {}, "exporte": {"libSceNpAuth": {"BBBBBBBBBBB"}},
                    "import_bibliotheken": {}, "export_bibliotheken": {}}

        alt = bp.symbole_aus_datei
        bp.symbole_aus_datei = _lesen
        try:
            bericht = bp.deckung_pruefen(["spiel"], ["lib"])
        finally:
            bp.symbole_aus_datei = alt
        self.assertEqual(bericht["bibliotheken"], {})
        self.assertEqual(bericht["unbeteiligt"], ["libkernel"])

    def test_statisch_gebundene_datei_wird_gezaehlt_nicht_gemeldet(self):
        # Die Homebrew in helloworld/ hat keine NID-Importtabelle. Das ist
        # kein Fehler, muss aber sichtbar sein - sonst sagt der Bericht
        # "alles in Ordnung" ueber Dateien, die er nie gelesen hat.
        elf = PROJEKT / "helloworld" / "ftpsrv-ps5_v1.16-ng.elf"
        if not elf.is_file():
            self.skipTest("Homebrew liegt nicht bei")
        bericht = bp.deckung_pruefen([str(elf)], [])
        self.assertEqual(bericht["geprueft"], 0)
        self.assertEqual(bericht["ohne_tabelle"], 1)

    def test_bibliotheksname_aus_dateinamen(self):
        self.assertEqual(bp.bibliotheksname("libSceAgc.sprx"), "libSceAgc")
        self.assertEqual(bp.bibliotheksname("libSceSaveData.native.sprx"),
                         "libSceSaveData.native")
        self.assertEqual(bp.bibliotheksname("/pfad/libScePsml.prx"), "libScePsml")

    def test_unlesbare_datei_wirft_nicht(self):
        # Der Backport ist zum Zeitpunkt der Pruefung schon durch - ein
        # Lesefehler darf ihn nicht nachtraeglich entwerten.
        with tempfile.TemporaryDirectory() as ordner:
            muell = os.path.join(ordner, "kaputt.sprx")
            with open(muell, "wb") as fh:
                fh.write(b"nicht einmal ein Kopf")
            bericht = bp.deckung_pruefen([muell], [muell])
            self.assertEqual(bericht["geprueft"], 0)


class DeckungVerdrahtungTests(unittest.TestCase):
    """Der Weg vom Haken im Fenster bis ins Protokoll."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_haken_vorhanden(self):
        self.assertIn('(deckung_var, "backport.option_coverage")', self.quelle)

    def test_wert_wird_an_den_worker_gereicht(self):
        self.assertIn("win, deckung_var.get()", self.quelle)

    def test_geprueft_wird_was_im_zielordner_liegt(self):
        # Gegen die Quellen zu pruefen waere wertlos: Aussagen soll der
        # Bericht ueber die Dateien, die tatsaechlich neben dem Spiel liegen.
        self.assertIn("installiert = [os.path.join(ziel, os.path.basename(q))",
                      self.quelle)

    def test_alle_texte_uebersetzt(self):
        for schluessel in ("backport.option_coverage", "backport.coverage_start",
                           "backport.coverage_files", "backport.coverage_line",
                           "backport.coverage_ok", "backport.coverage_none",
                           "backport.coverage_console", "backport.coverage_unreadable",
                           "backport.coverage_failed"):
            self.assertIn(schluessel, i18n.STRINGS, schluessel)
            for sprache in ("de", "en"):
                self.assertTrue(i18n.STRINGS[schluessel].get(sprache),
                                "%s/%s fehlt" % (schluessel, sprache))


class SymboltabelleGrenzeTests(unittest.TestCase):
    """Die Symboltabelle hat ein Ende - und das steht in der Hashtabelle.

    Bis v1.8.65 las prx_symbole() bis zum Dateiende weiter. Bei einer echten
    eboot.bin waren das 37468 statt 744 Eintraege; alles dahinter sind fremde
    Bytes, deren st_name zufaellig in die Zeichenkettentabelle zeigt - mitten
    in einen Namen. Heraus kamen Bruchstuecke wie "+mr7GjTvr8" (ein Stueck von
    "N+mr7GjTvr8"), die als eigene Kennungen zaehlten.

    Folge: Die Deckungspruefung meldete Funktionen als fehlend, die es nie
    gab. An 32 echten Spielen gemessen verschwanden nach der Reparatur
    **alle** gemeldeten Luecken.
    """

    FAKELIB = str(PROJEKT / "Backport_Fakelibs" / "7" / "fakelib" / "libSceAgcDriver.sprx")

    def setUp(self):
        if not os.path.isfile(self.FAKELIB):
            self.skipTest("Bibliothekssatz FW7 liegt nicht bei")

    def _nchain(self, elf):
        """Zahl der .dynsym-Eintraege, unabhaengig von prx_symbole berechnet."""
        lade, dynamik = [], None
        for typ, offset, vaddr, groesse in bp._programmkoepfe(elf):
            if typ == 1:
                lade.append((vaddr, offset, groesse))
            elif typ == 2:
                dynamik = (offset, groesse)
        werte = {}
        off, gr = dynamik
        for i in range(gr // 16):
            tag, wert = struct.unpack_from("<QQ", elf, off + i * 16)
            if tag == 0:
                break
            werte.setdefault(tag, wert)
        adresse = werte[bp.DT_HASH]
        for vaddr, offset, groesse in lade:
            if vaddr <= adresse < vaddr + groesse:
                stelle = offset + (adresse - vaddr)
                _nbucket, nchain = struct.unpack_from("<II", elf, stelle)
                return nchain
        self.fail("Hashtabelle nicht auffindbar")

    def test_nicht_mehr_symbole_als_die_hashtabelle_nennt(self):
        roh = io.open(self.FAKELIB, "rb").read()
        elf = bp.self_zu_elf(roh)
        nchain = self._nchain(elf)
        symbole = bp.prx_symbole(elf)
        gelesen = (sum(len(v) for v in symbole["importe"].values())
                   + sum(len(v) for v in symbole["exporte"].values()))
        self.assertLessEqual(
            gelesen, nchain,
            "%d Symbole gelesen, die Hashtabelle nennt nur %d - es wird ueber "
            "das Ende der Tabelle hinaus gelesen." % (gelesen, nchain))
        # Und nicht so wenige, dass die Begrenzung selbst der Fehler waere.
        self.assertGreater(gelesen, nchain * 0.5, "Verdaechtig wenige Symbole")

    def test_keine_bruchstuecke_als_kennung(self):
        # Jede echte Kennung ist elf Zeichen lang. Kuerzere sind Reste aus
        # dem Ueberlesen - genau das Fehlerbild von v1.8.65.
        symbole = bp.symbole_aus_datei(self.FAKELIB)
        alle = set()
        for gruppe in (symbole["importe"], symbole["exporte"]):
            for menge in gruppe.values():
                alle |= menge
        kurz = sorted(n for n in alle if len(n) != 11)
        self.assertEqual(kurz, [], "Bruchstuecke statt Kennungen: %s" % kurz[:8])

    def test_die_grenze_steht_im_quelltext(self):
        quelle = io.open(str(PROJEKT / "ps5_validator" / "utils" / "ps5_backport.py"),
                         encoding="utf-8").read()
        self.assertIn("while i < anzahl and symtab", quelle,
                      "Die Schleife laeuft wieder ohne Obergrenze aus der Hashtabelle.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
