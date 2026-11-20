# -*- coding: utf-8 -*-
"""BACKPORT-Erkennung am SDK der Programme (gemeldet 20.11.2026).

Meldung eines Anwenders: Beim Umwandeln von ``.ffpkg`` in ein PKG verlange das Programm "manchmal" einen Backport fuer seine Firmware 12,
obwohl seine Abbilder schon herabgesetzt seien und unter Firmware 12 liefen. Ursache: Die Rueckfrage urteilte nach den Angaben der
``param.json`` (Dump Forges ``sdk`` und ``firmware``). Ein Backport senkt aber das SDK der **Programme** (``eboot.bin``, ``.prx``) und
laesst die ``param.json`` oft unberuehrt - gemessen an echten Spielen: Fallout 4 (``eboot.bin`` 4.00, ``sdkVersion`` 8.00), Trackmania
(4.00 gegen 6.00), Big Helmet Heroes (4.00 gegen 9.00) tragen Ersatzbibliotheken, Ghost of Yotei (8.00 gegen 11.00) in ``fakelib/`` nur
AMPR EMU - und Forge nennt das SDK der Programme nur bei einem Spiel mit ``fakelib/`` (``backport_firmware``).

Geprueft wird hier: der Leser fuer das SDK der ``eboot.bin`` (Ordner, ``.ffpkg``, ``.exfat``, ``.ffpfs``, ``.ffpfsc`` in jeder Bauform; nur
einige KiB gelesen, nichts entpackt; ein ``.pkg`` bleibt unlesbar), die Bewertung in
``forge_cli.QuellFakten``, der Plan der Rueckfrage und der Bericht - jeweils mit Gegenprobe (ein nicht herabgesetztes Spiel wird
weiter beanstandet). Der Durchlauf mit der echten Forge-Befehlszeile stellt die Meldung nach.
"""
from __future__ import annotations

import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "tests"))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402,F401
from mkpfs import consts                                     # noqa: E402
from mkpfs.exfat import ExfatReader                          # noqa: E402
from mkpfs.exfat_writer import iter_exfat_image              # noqa: E402
from mkpfs.pfs import build_pfs, build_pfs_stream_single_file   # noqa: E402
from ps5_validator.utils import forge_cli as fc              # noqa: E402
from ps5_validator.utils import programm_sdk as ps           # noqa: E402
from ps5_validator.utils import ps5_backport as bp           # noqa: E402
from ps5_validator.utils import quellbericht as qb           # noqa: E402
from ps5_validator.utils import ufs2_leser as ul             # noqa: E402
from ps5_validator.utils import ufs2_schreiber as w          # noqa: E402

LOAD_GROESSE = 0x200
PARAM_IM_SEGMENT = 0x90
COMMENT_GROESSE = 0x40


def baue_elf(sdk: int, *, davor: int = 0, art: int = bp.PT_SCE_PROCPARAM, kennung_zuerst: bool = False) -> bytes:
    """Ein 64-Bit-ELF wie in echten Dumps: ein ``PT_LOAD`` mit dem Modulkopf darin (+0x90), dahinter ``PT_SCE_COMMENT``.

    ``davor`` Bytes Code (ein weiterer ``PT_LOAD``, ein Vielfaches von 0x4000) liegen vor dem Modulkopf: So liegt er in einer grossen
    ``eboot.bin`` weit hinter den ersten 64 KiB - auch in der signierten Datei (deren Segmente der Signierer unveraendert uebernimmt).
    ``kennung_zuerst``: der Modulkopf beginnt mit der Kennung statt mit einem Groessenfeld (Dump Forge liest beide Formen).
    """
    versatz = 0x4000 + davor
    segment = bytearray(LOAD_GROESSE)
    magic = bp.SCE_PROCESS_PARAM_MAGIC if art == bp.PT_SCE_PROCPARAM else bp.SCE_MODULE_PARAM_MAGIC
    if kennung_zuerst:
        struct.pack_into("<I", segment, PARAM_IM_SEGMENT, magic)
        struct.pack_into("<I", segment, PARAM_IM_SEGMENT + 0xC, sdk)
    else:
        struct.pack_into("<I", segment, PARAM_IM_SEGMENT, 0x40)
        struct.pack_into("<I", segment, PARAM_IM_SEGMENT + bp.PARAM_MAGIC_OFFSET, magic)
        struct.pack_into("<I", segment, PARAM_IM_SEGMENT + bp.PARAM_PS4_SDK_OFFSET, 0x11590001)
        struct.pack_into("<I", segment, PARAM_IM_SEGMENT + bp.PARAM_PS5_SDK_OFFSET, sdk)
    comment = versatz + LOAD_GROESSE
    koepfe = []
    if davor:
        koepfe.append((bp.PT_LOAD, 0x5, 0x4000, 0x10000000, 0, davor, davor, 0x4000))
    koepfe += [
        (bp.PT_LOAD, 0x5, versatz, 0x400000, 0, LOAD_GROESSE, LOAD_GROESSE, 0x4000),
        (art, 0x4, versatz + PARAM_IM_SEGMENT, 0x400000 + PARAM_IM_SEGMENT, 0, 0x40, 0x40, 8),
        (bp.PT_SCE_COMMENT, 0x4, comment, 0, 0, COMMENT_GROESSE, 0, 1),
    ]
    puffer = bytearray(comment + COMMENT_GROESSE)
    struct.pack_into(bp.ELF_HEADER_FMT, puffer, 0, b"\x7fELF", 2, 1, 1, 0, 0, 0)
    struct.pack_into(bp.ELF_HEADER_EX_FMT, puffer, 16, 0xFE10, 0x3E, 1, 0x400000, 0x40, 0, 0, 0x40, bp.PHDR_SIZE, len(koepfe), 0x40, 0, 0)
    for i, k in enumerate(koepfe):
        struct.pack_into(bp.PHDR_FMT, puffer, 0x40 + i * bp.PHDR_SIZE, *k)
    puffer[versatz:versatz + LOAD_GROESSE] = segment
    puffer[comment:comment + COMMENT_GROESSE] = bytes(range(COMMENT_GROESSE))
    return bytes(puffer)


def als_self(elf: bytes) -> bytes:
    """Das ELF als signierte Datei (fSELF), so wie das Programm sie beim Backport schreibt."""
    return bp.elf_signieren(elf)


def herabgesetzt(elf: bytes, firmware: int) -> bytes:
    """``eboot.bin`` nach dem Weg des Programms (``datei_verarbeiten``) auf die Firmware-Hauptversion herabgesetzt."""
    ps5, ps4 = bp.sdk_paar(firmware)
    ergebnis, neu, text = bp.datei_verarbeiten(als_self(elf), ziel_ps5=ps5, ziel_ps4=ps4)
    assert ergebnis == bp.ERG_GEPATCHT, text
    return neu


def lese(daten: bytes):
    return lambda ab, laenge: daten[ab:ab + laenge]


PARAM_JSON = b'{"titleId":"PPSA25872","sdkVersion":"0x1000000000000000","requiredSystemSoftwareVersion":"0x1120000000000000"}'
#: Ein UFS2-Abbild darf nicht kleiner als 16 Bloecke sein; diese Datei macht jedes Testabbild gross genug.
FUELLUNG = bytes(1_200_000)


class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="progsdk_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def pfad(self, *teile: str) -> str:
        return os.path.join(self.tmp, *teile)

    def spielordner(self, name: str, eboot: "bytes | None", param: bytes = PARAM_JSON, eboot_name: str = "eboot.bin") -> str:
        ordner = self.pfad(name)
        os.makedirs(os.path.join(ordner, "sce_sys"))
        Path(ordner, "sce_sys", "param.json").write_bytes(param)
        if eboot is not None:
            Path(ordner, eboot_name).write_bytes(eboot)
        return ordner

    def ffpkg(self, name: str, inhalte: "dict[str, bytes]") -> str:
        def oeffner(d: bytes):
            return lambda: iter([d[i:i + 70_000] for i in range(0, len(d), 70_000)])
        eintraege = [(rel, len(d), oeffner(d)) for rel, d in inhalte.items()]
        plan = w.planen(eintraege, (), profil=w.Ufs2Profil(65536, 65536, 4096, 0, 262144))
        ziel = self.pfad(name)
        plan.schreiben(ziel)
        return ziel


class SdkLeserTests(_Grundlage):
    """``programm_sdk.sdk_wort_lesen``: ELF und fSELF, Modulkopf nah und fern, nichts Lesbares."""

    def test_elf_stimmt_mit_dem_vollleser_ueberein(self) -> None:
        for sdk in (0x07000038, 0x09000040, 0x10000038, 0x12500000, 0x04000033):
            for art in (bp.PT_SCE_PROCPARAM, bp.PT_SCE_MODULE_PARAM):
                with self.subTest(sdk=hex(sdk), art=hex(art)):
                    elf = baue_elf(sdk, art=art)
                    self.assertEqual(sdk, ps.sdk_wort_lesen(lese(elf)))
                    self.assertEqual(sdk, bp.sdk_lesen(elf)[0], "der vorhandene Vollleser sagt dasselbe")

    def test_modulkopf_mit_der_kennung_am_anfang_wird_auch_gelesen(self) -> None:
        for art in (bp.PT_SCE_PROCPARAM, bp.PT_SCE_MODULE_PARAM):
            with self.subTest(art=hex(art)):
                elf = baue_elf(0x09000040, art=art, kennung_zuerst=True)
                self.assertEqual(0x09000040, ps.sdk_wort_lesen(lese(elf)))
                self.assertEqual(0x09000040, ps.sdk_wort_lesen(lese(als_self(elf))))

    def test_eine_kennung_der_falschen_art_wird_nicht_gelesen(self) -> None:
        """Ein ``PT_SCE_PROCPARAM`` mit der Kennung eines Modulkopfs (oder umgekehrt) ist keine verlaessliche Angabe."""
        elf = bytearray(baue_elf(0x10000038))
        struct.pack_into("<I", elf, 0x4000 + PARAM_IM_SEGMENT + bp.PARAM_MAGIC_OFFSET, bp.SCE_MODULE_PARAM_MAGIC)
        self.assertIsNone(ps.sdk_wort_lesen(lese(bytes(elf))))

    def test_signierte_datei_wird_ueber_die_segmenttabelle_gelesen(self) -> None:
        for sdk in (0x10000038, 0x07000038):
            with self.subTest(sdk=hex(sdk)):
                signiert = als_self(baue_elf(sdk))
                self.assertEqual(bp.TYP_SELF, bp.dateityp(signiert))
                self.assertEqual(sdk, ps.sdk_wort_lesen(lese(signiert)))

    def test_ein_vom_programm_herabgesetztes_programm_traegt_die_zielstufe(self) -> None:
        for firmware in (4, 5, 6, 7):
            with self.subTest(firmware=firmware):
                neu = herabgesetzt(baue_elf(0x10000038), firmware)
                self.assertEqual(bp.sdk_paar(firmware)[0] >> 24, ps.sdk_wort_lesen(lese(neu)) >> 24)
                self.assertEqual("%d.00" % firmware, ps.sdk_text(ps.sdk_wort_lesen(lese(neu))))

    def test_der_modulkopf_hinter_dem_kopf_wird_gezielt_gelesen_nicht_alles(self) -> None:
        """Der Modulkopf einer grossen ``eboot.bin`` liegt hinter dem Code: Gelesen werden nur Kopf (64 KiB) und die 32 Bytes dort."""
        for umwandeln in (lambda e: e, als_self):
            elf = baue_elf(0x10000038, davor=0x300000)
            daten = umwandeln(elf)
            anfragen: list[tuple[int, int]] = []

            def lesen(ab: int, laenge: int, daten=daten, anfragen=anfragen) -> bytes:
                anfragen.append((ab, laenge))
                return daten[ab:ab + laenge]

            self.assertEqual(0x10000038, ps.sdk_wort_lesen(lesen))
            self.assertGreater(len(daten), 0x300000)
            self.assertLessEqual(sum(n for _ab, n in anfragen), ps.KOPF + ps.MODULKOPF, anfragen)
            self.assertEqual(2, len(anfragen))

    def test_nichts_lesbares_ist_none_und_wirft_nie(self) -> None:
        elf = baue_elf(0x10000038)
        signiert = als_self(elf)
        verschluesselt = bytearray(signiert)
        segmente = struct.unpack_from("<H", verschluesselt, 0x18)[0]
        for k in range(segmente):
            eigenschaften = struct.unpack_from("<Q", verschluesselt, 0x20 + k * 0x20)[0]
            struct.pack_into("<Q", verschluesselt, 0x20 + k * 0x20, eigenschaften | (1 << 1))
        ohne_param = bytearray(elf)
        struct.pack_into("<I", ohne_param, 0x40 + bp.PHDR_SIZE, bp.PT_SCE_COMMENT)       # der Programmkopf des Modulkopfs ist keiner mehr
        falsche_kennung = bytearray(elf)
        struct.pack_into("<I", falsche_kennung, 0x4000 + PARAM_IM_SEGMENT + bp.PARAM_MAGIC_OFFSET, 0xDEADBEEF)   # ohne ``davor`` liegt der Modulkopf bei 0x4000
        for name, daten in (("leer", b""), ("Muell", b"nicht viel davon"), ("nur Kopf", elf[:0x30]), ("abgeschnitten", elf[:0x60]),
                            ("verschluesselt", bytes(verschluesselt)), ("ohne Modulkopf", bytes(ohne_param)),
                            ("falsche Kennung", bytes(falsche_kennung)), ("Nullen", bytes(0x20000))):
            with self.subTest(fall=name):
                self.assertIsNone(ps.sdk_wort_lesen(lese(daten)))

    def test_eine_fehlerhafte_lesefunktion_ergibt_none(self) -> None:
        def kaputt(_ab: int, _laenge: int) -> bytes:
            raise OSError("Platte weg")
        self.assertIsNone(ps.sdk_wort_lesen(kaputt))

    def test_die_schreibweise_wie_in_forge(self) -> None:
        for wort, erwartet in ((0x07000038, "7.00"), (0x10500040, "10.50"), (0x12000000, "12.00"), (0x09600000, "9.60"),
                               (0, ""), (None, ""), (0x0A000000, ""), (0x07A00000, ""), (0xFF000000, "")):
            with self.subTest(wort=wort):
                self.assertEqual(erwartet, ps.sdk_text(wort))


class OrdnerUndAbbildTests(_Grundlage):
    """``eboot_sdk``: Spielordner und ``.ffpkg``, sonst nichts."""

    def test_spielordner(self) -> None:
        original, tief = baue_elf(0x10000038), baue_elf(0x10000038, davor=0x180000)
        self.assertEqual("10.00", ps.eboot_sdk(self.spielordner("a", als_self(original))))
        self.assertEqual("10.00", ps.eboot_sdk(self.spielordner("b", als_self(tief))))
        self.assertEqual("7.00", ps.eboot_sdk(self.spielordner("c", herabgesetzt(original, 7))))

    def test_die_schreibweise_des_dateinamens_ist_gleich(self) -> None:
        self.assertEqual("10.00", ps.eboot_sdk(self.spielordner("a", als_self(baue_elf(0x10000038)), eboot_name="EBOOT.BIN")))

    def test_ohne_eboot_ohne_ordner_und_fremde_dateien_ist_es_leer(self) -> None:
        self.assertEqual("", ps.eboot_sdk(self.spielordner("a", None)))
        self.assertEqual("", ps.eboot_sdk(self.pfad("gibt_es_nicht")))
        paket = self.pfad("x.pkg")
        Path(paket).write_bytes(b"\x7fCNT" + bytes(4096))
        self.assertEqual("", ps.eboot_sdk(paket))
        self.assertEqual("", ps.eboot_sdk(""))

    def test_ffpkg_liest_das_sdk_ohne_zu_entpacken(self) -> None:
        for name, elf, erwartet in (("orig.ffpkg", als_self(baue_elf(0x10000038, davor=0x180000)), "10.00"),
                                    ("tief.ffpkg", herabgesetzt(baue_elf(0x10000038, davor=0x180000), 7), "7.00"),
                                    ("nah.ffpkg", herabgesetzt(baue_elf(0x10000038), 5), "5.00")):
            with self.subTest(abbild=name):
                ziel = self.ffpkg(name, {"eboot.bin": elf, "sce_sys/param.json": PARAM_JSON, "Media/x.bin": FUELLUNG})
                self.assertEqual(erwartet, ps.eboot_sdk(ziel))

    def test_ffpkg_ohne_eboot_oder_kaputt_ist_leer(self) -> None:
        ohne = self.ffpkg("ohne.ffpkg", {"sce_sys/param.json": PARAM_JSON, "Media/x.bin": FUELLUNG})
        self.assertEqual("", ps.eboot_sdk(ohne))
        kaputt = self.pfad("kaputt.ffpkg")
        Path(kaputt).write_bytes(os.urandom(200_000))
        self.assertEqual("", ps.eboot_sdk(kaputt))
        self.assertEqual("", ps.eboot_sdk(self.pfad("fehlt.ffpkg")))


def _flach(ordner: str, ziel: str, *, komprimiert: bool) -> None:
    build_pfs(source_root=Path(ordner), output_path=Path(ziel), block_size=65536, pfs_version=consts.PFS_VERSION_PS5,
              inode_bits=32, case_insensitive=True, signed=False, compress=komprimiert, threshold_gain=0, cpu_count=1,
              zlib_level=6, dry_run=False, verbose=False)


def _huelle(innen: str, ziel: str, *, komprimiert: bool) -> None:
    build_pfs_stream_single_file(
        source_file=Path(innen), output_path=Path(ziel), block_size=65536, pfs_version=consts.PFS_VERSION_PS5,
        case_insensitive=True, zlib_level=6, threshold_gain=0, min_file_gain=0, min_compress_size=0, cpu_count=1,
        compress=komprimiert)


class AbbilderTests(unittest.TestCase):
    """``.exfat``, ``.ffpfs`` und ``.ffpfsc`` in jeder Bauform, gebaut mit den Schreibern, die das Programm und Dump Forge benutzen.

    Der Modulkopf der ``eboot.bin`` liegt weit hinter den ersten 64 KiB. Gelesen wird ohne Entpacken: nur Kopf, Verzeichnisse und die
    wenigen Cluster oder Bloecke dort. An echten Abbildern (30 Dateien bis 223 GB, ``.exfat`` und ``.ffpfsc``, dazu Forge-Bauten in allen
    Formaten) gemessen: das SDK stimmt mit dem des Spielordners ueberein."""

    #: Bauform -> (Dateiendung, Huelle um ein inneres Abbild?)
    FORMEN = ("exfat", "ffpkg", "flach_roh", "flach_pfsc", "huelle_exfat_roh", "huelle_exfat_pfsc", "huelle_ffpkg_pfsc", "pfs_in_pfs", "doppelt")
    ENDUNG = {"exfat": ".exfat", "ffpkg": ".ffpkg", "flach_roh": ".ffpfs", "huelle_exfat_roh": ".ffpfs"}

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp(prefix="progsdk_abbild_")
        cls.abbilder: "dict[tuple[str, str], str]" = {}
        cls.ordner: "dict[str, str]" = {}
        cls.erwartet = {"B": "7.00", "O": "10.00"}
        profil = w.Ufs2Profil(65536, 65536, 4096, 0, 262144)
        for kennung, eboot in (("B", herabgesetzt(baue_elf(0x10000038, davor=0x180000), 7)),
                               ("O", als_self(baue_elf(0x10000038, davor=0x180000)))):
            ordner = cls.ordner[kennung] = os.path.join(cls.tmp, "spiel_" + kennung)
            inhalt = {"eboot.bin": eboot, "sce_sys/param.json": PARAM_JSON, "data/a/x.bin": bytes(70_000), "data/b/y.bin": bytes(40_000),
                      "data/c/z.bin": bytes(10_000), "Media/m.bin": bytes(30_000)}
            for rel, daten in inhalt.items():
                voll = os.path.join(ordner, *rel.split("/"))
                os.makedirs(os.path.dirname(voll), exist_ok=True)
                Path(voll).write_bytes(daten)

            def pfad(form: str, endung: "str | None" = None) -> str:
                return os.path.join(cls.tmp, "%s_%s%s" % (kennung, form, endung or cls.ENDUNG.get(form, ".ffpfsc")))

            a = {}
            a["exfat"] = pfad("exfat")
            with open(a["exfat"], "wb") as fh:
                for stueck in iter_exfat_image(Path(ordner)):
                    fh.write(stueck)
            a["ffpkg"] = pfad("ffpkg")
            eintraege = [(rel, len(d), (lambda d=d: iter([d[i:i + 70_000] for i in range(0, len(d), 70_000)]))) for rel, d in inhalt.items()]
            w.planen(eintraege, (), profil=profil).schreiben(a["ffpkg"])
            a["flach_roh"] = pfad("flach_roh")
            _flach(ordner, a["flach_roh"], komprimiert=False)
            a["flach_pfsc"] = pfad("flach_pfsc")
            _flach(ordner, a["flach_pfsc"], komprimiert=True)
            a["huelle_exfat_roh"] = pfad("huelle_exfat_roh")
            _huelle(a["exfat"], a["huelle_exfat_roh"], komprimiert=False)
            a["huelle_exfat_pfsc"] = pfad("huelle_exfat_pfsc")
            _huelle(a["exfat"], a["huelle_exfat_pfsc"], komprimiert=True)
            a["huelle_ffpkg_pfsc"] = pfad("huelle_ffpkg_pfsc")                      # so baut Dump Forge ein ``.ffpfsc`` (inneres ``.ffpkg``)
            _huelle(a["ffpkg"], a["huelle_ffpkg_pfsc"], komprimiert=True)
            a["pfs_in_pfs"] = pfad("pfs_in_pfs")
            _huelle(a["flach_pfsc"], a["pfs_in_pfs"], komprimiert=True)
            a["doppelt"] = pfad("doppelt")
            _huelle(a["huelle_exfat_pfsc"], a["doppelt"], komprimiert=True)
            for form, ziel in a.items():
                cls.abbilder[(kennung, form)] = ziel

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_jede_bauform_liefert_das_sdk_der_eboot(self) -> None:
        for (kennung, form), pfad in self.abbilder.items():
            with self.subTest(spiel=kennung, bauform=form):
                self.assertEqual(self.erwartet[kennung], ps.eboot_sdk(pfad))

    def test_die_art_zaehlt_nicht_die_endung(self) -> None:
        """Dump Forge nennt ein ``.ffpfsc`` mit innerem ``.ffpkg`` so, ein umbenanntes Abbild bleibt lesbar."""
        for form, endung in (("exfat", ".ffpfsc"), ("flach_pfsc", ".ffpfs"), ("huelle_ffpkg_pfsc", ".exfat")):
            with self.subTest(bauform=form, endung=endung):
                kopie = os.path.join(self.tmp, "umbenannt_%s%s" % (form, endung))
                shutil.copyfile(self.abbilder[("B", form)], kopie)
                self.addCleanup(os.remove, kopie)
                self.assertEqual("7.00", ps.eboot_sdk(kopie))

    def test_der_ordner_mit_mkpfs_laesst_sich_angeben_und_merken(self) -> None:
        """Im gebauten Programm liegt MkPFS in einem Arbeitsordner (``_extract_embedded_mkpfs``), nicht im Suchpfad: ohne die Angabe bliebe
        jedes ``.exfat`` und ``.ffpfsc`` ungelesen."""
        pfad = self.abbilder[("B", "huelle_exfat_pfsc")]
        mkpfs = str(PROJEKT / "MkPFS-1.1.0")
        alt = ps._mkpfs_ordner
        self.addCleanup(ps.mkpfs_ordner_merken, alt)
        ohne_mkpfs = [p for p in sys.path if os.path.normcase(os.path.abspath(p)) != os.path.normcase(mkpfs)]

        def vergessen() -> None:
            for name in [n for n in sys.modules if n == "mkpfs" or n.startswith("mkpfs.")]:
                del sys.modules[name]
            sys.path[:] = ohne_mkpfs

        with mock.patch.object(sys, "path", list(ohne_mkpfs)), mock.patch.dict(sys.modules), \
                mock.patch.object(ps._werkzeuge_bereitstellen, "mkpfs_ordner_vorhanden", return_value=""):
            vergessen()
            ps.mkpfs_ordner_merken("")
            self.assertEqual("", ps.eboot_sdk(pfad), "MkPFS ist nicht zu finden")
            self.assertEqual("7.00", ps.eboot_sdk(pfad, mkpfs), "der Ordner als Angabe")
            vergessen()
            ps.mkpfs_ordner_merken(mkpfs)
            self.assertEqual("7.00", ps.eboot_sdk(pfad), "der gemerkte Ordner")

    def test_das_mitgelieferte_mkpfs_wird_auch_ohne_angabe_gefunden(self) -> None:
        """Wer ein Abbild waehlt, bevor das Hauptfenster MkPFS vorgewaermt hat, bekommt trotzdem das SDK (und die Antwort wird nicht als
        "nicht zu sagen" gemerkt)."""
        pfad = self.abbilder[("B", "huelle_exfat_pfsc")]
        mkpfs = str(PROJEKT / "MkPFS-1.1.0")
        self.assertEqual(os.path.normcase(mkpfs), os.path.normcase(ps._werkzeuge_bereitstellen.mkpfs_ordner_vorhanden()))
        alt = ps._mkpfs_ordner
        self.addCleanup(ps.mkpfs_ordner_merken, alt)
        ohne_mkpfs = [p for p in sys.path if os.path.normcase(os.path.abspath(p)) != os.path.normcase(mkpfs)]
        with mock.patch.object(sys, "path", list(ohne_mkpfs)), mock.patch.dict(sys.modules):
            for name in [n for n in sys.modules if n == "mkpfs" or n.startswith("mkpfs.")]:
                del sys.modules[name]
            ps.mkpfs_ordner_merken("")
            self.assertEqual("7.00", ps.eboot_sdk(pfad))

    def test_jede_fehlerart_beim_lesen_ergibt_leer(self) -> None:
        """MkPFS wirft beim Lesen eines beschaedigten Abbilds nicht nur ``ValueError`` (``CompressionError`` ist keiner): ``eboot_sdk`` wirft nie."""
        from mkpfs.compression import CompressionError
        pfad = self.abbilder[("B", "huelle_exfat_pfsc")]
        for fehler in (OSError("x"), ValueError("x"), struct.error("x"), KeyError("x"), IndexError("x"), CompressionError("x")):
            with self.subTest(fehler=type(fehler).__name__), mock.patch.object(ps, "_sdk_im_abbild", side_effect=fehler):
                self.assertEqual("", ps.eboot_sdk(pfad))

    def test_nur_die_bekannten_endungen_werden_gelesen(self) -> None:
        """Ein ``.pkg`` (Forge entschluesselt und entpackt es) und Archive liest das Programm nicht - auch wenn der Inhalt ein Abbild waere."""
        for endung in (".pkg", ".zip", ".7z", ".rar", ".txt", ".bin"):
            with self.subTest(endung=endung):
                ziel = os.path.join(self.tmp, "fremd" + endung)
                shutil.copyfile(self.abbilder[("B", "exfat")], ziel)
                self.addCleanup(os.remove, ziel)
                self.assertEqual("", ps.eboot_sdk(ziel))

    def test_von_exfat_wird_nur_die_wurzel_gelesen(self) -> None:
        """Der ganze Baum dauerte an einem Spiel mit 67.226 Dateien 137 s (HDD, kalt): Es gibt hier drei Unterordner und doch nur einen Zugriff."""
        original = ExfatReader._read_directory_entries
        aufrufe: list[int] = []

        def zaehlend(selbst, *args, **kwargs):
            aufrufe.append(1)
            return original(selbst, *args, **kwargs)

        for form in ("exfat", "huelle_exfat_pfsc"):
            aufrufe.clear()
            with self.subTest(bauform=form), mock.patch.object(ExfatReader, "_read_directory_entries", zaehlend):
                self.assertEqual("7.00", ps.eboot_sdk(self.abbilder[("B", form)]))
                self.assertEqual(1, len(aufrufe), "nur das Wurzelverzeichnis")

    def test_von_der_eboot_kommen_nur_wenige_bytes(self) -> None:
        """Die ``eboot.bin`` ist hier 1,5 MB gross; aus dem Abbild werden Kopf, Verzeichnisse und ein paar Cluster gelesen."""
        for form in ("exfat", "ffpkg", "huelle_ffpkg_pfsc"):
            pfad = self.abbilder[("B", form)]
            gelesen = []
            echt = open

            class Zaehler:
                def __init__(self, fh):
                    self._fh = fh

                def read(self, n=-1):
                    daten = self._fh.read(n)
                    gelesen.append(len(daten))
                    return daten

                def __getattr__(self, name):
                    return getattr(self._fh, name)

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    self._fh.close()

            def oeffnen(datei, modus="r", *a, **k):
                fh = echt(datei, modus, *a, **k)
                return Zaehler(fh) if str(datei) == pfad and "b" in modus else fh

            with self.subTest(bauform=form), mock.patch("builtins.open", oeffnen):
                self.assertEqual("7.00", ps.eboot_sdk(pfad))
            self.assertGreater(sum(gelesen), 0, "der Zaehler muss den Zugriff sehen, sonst misst der Test nichts")
            self.assertLess(sum(gelesen), 600_000, "gelesen: %d Bytes (die eboot.bin allein hat %d)" % (sum(gelesen), 0x180000))

    def test_eine_flache_pfs_nur_mit_der_eboot_ist_keine_huelle(self) -> None:
        """Genau eine Datei im PFS ist nur dann ein umhuelltes Abbild, wenn sie selbst eines ist."""
        ordner = os.path.join(self.tmp, "nur_eboot")
        os.makedirs(ordner)
        Path(ordner, "eboot.bin").write_bytes(herabgesetzt(baue_elf(0x10000038, davor=0x180000), 7))
        for komprimiert in (False, True):
            with self.subTest(komprimiert=komprimiert):
                ziel = os.path.join(self.tmp, "nur_eboot_%s.ffpfsc" % komprimiert)
                _flach(ordner, ziel, komprimiert=komprimiert)
                self.assertEqual("7.00", ps.eboot_sdk(ziel))

    def test_ohne_mkpfs_bleiben_nur_ffpkg_und_ordner(self) -> None:
        with mock.patch.object(ps, "_Mkpfs", side_effect=ImportError("kein mkpfs")):
            self.assertEqual("7.00", ps.eboot_sdk(self.abbilder[("B", "ffpkg")]))
            self.assertEqual("7.00", ps.eboot_sdk(self.ordner["B"]))
            for form in ("exfat", "flach_pfsc", "huelle_ffpkg_pfsc"):
                with self.subTest(bauform=form):
                    self.assertEqual("", ps.eboot_sdk(self.abbilder[("B", form)]))

    def test_kein_abbild_ist_leer_und_wirft_nicht(self) -> None:
        pfad = self.abbilder[("B", "huelle_exfat_pfsc")]
        daten = Path(pfad).read_bytes()
        faelle = {"Zufall.exfat": os.urandom(100_000), "Zufall.ffpfsc": os.urandom(100_000), "Zufall.ffpfs": os.urandom(100_000),
                  "leer.ffpfsc": b"", "abgeschnitten.ffpfsc": daten[:3000], "halb.ffpfsc": daten[:len(daten) // 2],
                  "Nullen.exfat": bytes(100_000), "paket.pkg": b"\x7fCNT" + bytes(9000), "archiv.zip": b"PK\x03\x04" + bytes(100),
                  "notiz.txt": b"keine eboot"}
        for name, inhalt in faelle.items():
            with self.subTest(datei=name):
                ziel = os.path.join(self.tmp, name)
                Path(ziel).write_bytes(inhalt)
                self.addCleanup(os.remove, ziel)
                self.assertEqual("", ps.eboot_sdk(ziel))

    def test_exfat_ohne_eboot_im_stamm_ist_leer(self) -> None:
        """Eine ``eboot.bin`` in einem Unterordner ist keine."""
        ordner = os.path.join(self.tmp, "unterordner")
        os.makedirs(os.path.join(ordner, "data"))
        Path(ordner, "data", "eboot.bin").write_bytes(als_self(baue_elf(0x10000038)))
        Path(ordner, "sce_sys").mkdir()
        Path(ordner, "sce_sys", "param.json").write_bytes(PARAM_JSON)
        ziel = os.path.join(self.tmp, "unterordner.exfat")
        with open(ziel, "wb") as fh:
            for stueck in iter_exfat_image(Path(ordner)):
                fh.write(stueck)
        self.assertEqual("", ps.eboot_sdk(ziel))


class Ufs2GriffTests(unittest.TestCase):
    """``ufs2_leser.Ufs2Leser`` nimmt auch einen schon geoeffneten Griff (die Ansicht auf das innere Abbild einer ``.ffpfsc``)."""

    def setUp(self) -> None:
        import test_ufs2_leser as t
        self.tmp = tempfile.mkdtemp(prefix="ufs2griff_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.abbild = os.path.join(self.tmp, "a.ffpkg")
        self.inhalte = t.baue_abbild(self.abbild)

    def test_ein_fremder_griff_bleibt_offen(self) -> None:
        with open(self.abbild, "rb") as fh:
            with ul.Ufs2Leser(fh) as leser:
                self.assertEqual(self.inhalte["sce_sys/param.json"], leser.datei_lesen("sce_sys/param.json"))
            self.assertFalse(fh.closed, "der Leser darf einen Griff, der ihm nicht gehoert, nicht schliessen")
            self.assertEqual(b"", fh.read(0))

    def test_ein_pfad_wird_wie_bisher_geoeffnet_und_geschlossen(self) -> None:
        with ul.Ufs2Leser(self.abbild) as leser:
            griff = leser._f
            self.assertFalse(griff.closed)
        self.assertTrue(griff.closed)
        for pfad in (Path(self.abbild),):
            with ul.Ufs2Leser(pfad) as leser:
                self.assertEqual(self.inhalte["eboot.bin"], leser.datei_lesen("eboot.bin"))

    def test_ein_fremder_griff_ohne_ufs2_loest_den_fehler_aus_und_bleibt_offen(self) -> None:
        with open(os.path.join(self.tmp, "x.bin"), "w+b") as fh:
            fh.write(os.urandom(200_000))
            with self.assertRaises(ul.Ufs2Fehler):
                ul.Ufs2Leser(fh)
            self.assertFalse(fh.closed)


class BereichTests(unittest.TestCase):
    """``Ufs2Leser.datei_bereich``: ein Stueck einer Datei, ohne sie zu laden - ueber Blockgrenzen und Zeigerbloecke."""

    def setUp(self) -> None:
        import test_ufs2_leser as t                         # das Mini-Abbild: 12 direkte Bloecke + 2 ueber den Zeigerblock
        self.tmp = tempfile.mkdtemp(prefix="ufs2bereich_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.abbild = os.path.join(self.tmp, "a.ffpkg")
        self.inhalte = t.baue_abbild(self.abbild)
        self.gross = self.inhalte["sce_sys/gross.bin"]
        self.bs = t.BS

    def test_bereiche_stimmen_mit_der_ganzen_datei_ueberein(self) -> None:
        bs = self.bs
        faelle = ((0, 10), (5, 100), (bs - 5, 10), (bs, bs), (3 * bs + 17, 2 * bs), (11 * bs - 1, 3), (12 * bs - 4, 8),
                  (12 * bs, 50), (13 * bs - 20, 20), (len(self.gross) - 7, 7), (0, len(self.gross)))
        with ul.Ufs2Leser(self.abbild) as leser:
            for ab, laenge in faelle:
                with self.subTest(ab=ab, laenge=laenge):
                    self.assertEqual(self.gross[ab:ab + laenge], leser.datei_bereich("sce_sys/gross.bin", ab, laenge))

    def test_am_ende_gekuerzt_und_ausserhalb_leer(self) -> None:
        with ul.Ufs2Leser(self.abbild) as leser:
            ende = len(self.gross)
            self.assertEqual(self.gross[ende - 5:], leser.datei_bereich("sce_sys/gross.bin", ende - 5, 100))
            for ab, laenge in ((ende, 10), (ende + 99, 10), (0, 0), (5, -3), (-4, 0)):
                with self.subTest(ab=ab, laenge=laenge):
                    self.assertEqual(b"", leser.datei_bereich("sce_sys/gross.bin", ab, laenge))
            self.assertEqual(self.gross[:4], leser.datei_bereich("sce_sys/gross.bin", -4, 4), "ein negativer Anfang gilt als 0")

    def test_ein_ordner_und_ein_fehlender_pfad(self) -> None:
        with ul.Ufs2Leser(self.abbild) as leser:
            with self.assertRaises(ul.Ufs2Fehler):
                leser.datei_bereich("sce_sys", 0, 10)
            with self.assertRaises(FileNotFoundError):
                leser.datei_bereich("sce_sys/gibt_es_nicht", 0, 10)


# ---------------------------------------------------------------------------------------------------------------------------- Bewertung
def _daten(sdk: str, firmware: str, *, backport: int = 0, backport_firmware: "str | None" = None, emulatoren: tuple = ()) -> dict:
    return {"sdk": sdk, "firmware": firmware, "backport": [{"path": "fakelib/x%d.sprx" % i} for i in range(backport)],
            "backport_firmware": backport_firmware, "emulators": [{"name": n, "path": "fakelib/e.sprx"} for n in emulatoren]}


def _fakten(sdk: str, firmware: str, eboot: str = "", **kw) -> "fc.QuellFakten":
    fakten = fc.quellfakten(_daten(sdk, firmware, **kw))
    fakten.eboot_sdk = eboot
    return fakten


class BewertungTests(unittest.TestCase):
    """Wann ein Spiel als herabgesetzt gilt und was es dann verlangt - an den gemessenen Spielen."""

    #: (Name, Fakten, Konsole, schon_da, noetig, verlangt_text)
    FAELLE = (
        # Ghost of Yotei: SDK 8.00 der Programme, param.json sagt 11.00/12.00, in fakelib nur AMPR EMU (Forge: backport leer)
        ("Ghost of Yotei, Konsole 9.xx", _fakten("11.00", "12.00", "8.00", backport_firmware="8.00", emulatoren=("AMPR",)), "9.99", True, False, "8.00"),
        ("Ghost of Yotei, Konsole 7.xx", _fakten("11.00", "12.00", "8.00", backport_firmware="8.00", emulatoren=("AMPR",)), "7.99", False, True, "8.00"),
        # Das Spiel der Meldung: herabgesetzt, param.json unveraendert, KEIN fakelib - Forge sieht nichts, das Programm liest die eboot.bin
        ("herabgesetzt ohne fakelib, Konsole 12", _fakten("10.00", "11.20", "7.00"), "12.00", True, False, "7.00"),
        ("herabgesetzt ohne fakelib, Konsole 9.xx", _fakten("10.00", "11.20", "7.00"), "9.99", True, False, "7.00"),
        ("herabgesetzt ohne fakelib, Konsole 5.xx", _fakten("10.00", "11.20", "7.00"), "5.99", False, True, "7.00"),
        # Fallout 4: Ersatzbibliotheken, param.json auf den Werten des Originals
        ("Fallout 4 mit Bibliotheken", _fakten("8.00", "9.20", "4.00", backport=2, backport_firmware="4.00"), "4.99", True, False, "4.00"),
        # Gegenproben: nicht herabgesetzt - das Spiel wird weiter beanstandet
        ("Original, Konsole 9.xx", _fakten("10.00", "11.20", "10.00"), "9.99", False, True, "11.20"),
        ("Original, Konsole 12", _fakten("10.00", "11.20", "10.00"), "12.00", False, False, "11.20"),
        ("eboot.bin nicht lesbar", _fakten("10.00", "11.20"), "9.99", False, True, "11.20"),
        ("Original mit AMPR-fakelib", _fakten("10.00", "11.20", "", backport_firmware="10.00", emulatoren=("AMPR",)), "7.99", False, True, "11.20"),
        # Ohne Angaben in der param.json (Arkanoid): das SDK der eboot.bin ist das, was bleibt
        ("ohne param.json-Angaben, Konsole 12", _fakten("", "", "4.00"), "12.00", False, False, "4.00"),
        ("ohne param.json-Angaben, Konsole 3.xx", _fakten("", "", "4.00"), "3.99", False, True, "4.00"),
        ("ohne alles", _fakten("", ""), "7.99", False, False, ""),
    )

    def test_die_gemessenen_faelle(self) -> None:
        for name, fakten, konsole, schon_da, noetig, verlangt in self.FAELLE:
            with self.subTest(fall=name):
                self.assertEqual(noetig, fakten.backport_noetig(konsole), "noetig")
                self.assertEqual(schon_da, fakten.backport_schon_da(konsole), "schon da")
                self.assertEqual(verlangt, fakten.verlangt_text, "verlangt")

    def test_herabgesetzt_heisst_programme_unter_der_angabe(self) -> None:
        for fakten, erwartet in ((_fakten("10.00", "11.20", "7.00"), True), (_fakten("10.00", "11.20", "10.00"), False),
                                 (_fakten("7.00", "9.60", "7.00"), False), (_fakten("10.00", "11.20", "10.01"), False),
                                 (_fakten("", "", "4.00"), False), (_fakten("10.00", "", ""), False),
                                 (_fakten("10.00", "11.20", "", backport_firmware="7.00"), True),
                                 (_fakten("0.00", "0.00", "4.00"), False), (fc.QuellFakten(), False)):
            with self.subTest(sdk=fakten.sdk, eboot=fakten.eboot_sdk, forge=fakten.backport_firmware):
                self.assertIs(erwartet, fakten.herabgesetzt)

    def test_das_hoechste_sdk_der_programme_zaehlt(self) -> None:
        """``eboot.bin`` und Forges ``backport_firmware`` (hoechstes SDK aller Programme): das hoehere gilt."""
        for eboot, forge, erwartet in (("4.00", "9.00", "9.00"), ("9.00", "4.00", "9.00"), ("7.00", "", "7.00"), ("", "7.00", "7.00"),
                                       ("", "", ""), ("0.00", "", "")):
            with self.subTest(eboot=eboot, forge=forge):
                self.assertEqual(erwartet, _fakten("12.00", "12.00", eboot, backport_firmware=forge or None).programme_sdk)

    def test_sind_nur_die_module_nicht_herabgesetzt_gilt_das_hoechste_sdk(self) -> None:
        """Big Helmet Heroes: ``eboot.bin`` 4.00, aber 11 Module auf 9.00 - das hoechste SDK entscheidet, ob es reicht."""
        fakten = _fakten("9.00", "11.00", "4.00", backport_firmware="9.00")
        self.assertFalse(fakten.herabgesetzt, "die Module tragen noch das SDK der param.json")
        self.assertEqual("11.00", fakten.verlangt_text)
        self.assertTrue(fakten.backport_noetig("7.99"))
        self.assertFalse(_fakten("9.00", "11.00", "4.00", backport=3, backport_firmware="9.00").backport_noetig("7.99"),
                         "mit Ersatzbibliotheken gilt der Backport als da (wie bisher)")

    def test_eine_antwort_ohne_ergaenzung_bleibt_wie_bisher(self) -> None:
        """Ohne gelesenes SDK der ``eboot.bin`` urteilt es nach Forges Angaben allein - die bisherigen Tests (``test_backport_empfehlung``)."""
        fakten = fc.quellfakten(_daten("10.00", "11.20"))
        self.assertEqual("", fakten.eboot_sdk)
        self.assertTrue(fakten.backport_noetig("9.99"))


# ------------------------------------------------------------------------------------------------------------------ Plan und Bericht
class PlanUndBerichtTests(unittest.TestCase):
    @staticmethod
    def _gui(bekannt: str):
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI as GUI
        g = GUI.__new__(GUI)
        g._konsole_fw_bekannt = mock.Mock(return_value=bekannt)
        g._konsole_firmware_erfragen = mock.Mock(return_value="")
        g._backport_firmwares = lambda: (4, 5, 6, 7)
        return g

    def test_ein_schon_herabgesetztes_spiel_loest_keine_rueckfrage_aus(self) -> None:
        for fakten in (_fakten("10.00", "11.20", "7.00"),
                       _fakten("11.00", "12.00", "8.00", backport_firmware="8.00", emulatoren=("AMPR",))):
            with self.subTest(eboot=fakten.eboot_sdk):
                self.assertIsNone(self._gui("9.99")._backport_plan(fakten, erfragen=False))

    def test_gegenprobe_das_original_bekommt_den_plan_weiter(self) -> None:
        self.assertEqual(("9.99", 7), self._gui("9.99")._backport_plan(_fakten("10.00", "11.20", "10.00"), erfragen=False))
        self.assertEqual(("9.99", 7), self._gui("9.99")._backport_plan(_fakten("10.00", "11.20"), erfragen=False))

    def test_reicht_die_herabsetzung_nicht_fuer_die_konsole_gibt_es_den_plan(self) -> None:
        self.assertEqual(("5.99", 5), self._gui("5.99")._backport_plan(_fakten("10.00", "11.20", "7.00"), erfragen=False))

    @staticmethod
    def _zeile(fakten, konsole: str) -> "qb.Zeile":
        zeilen = qb.zeilen(fakten, lambda schluessel, **werte: schluessel, konsole)
        return next(z for z in zeilen if z.schluessel == "backport")

    def test_der_bericht_nennt_ein_herabgesetztes_spiel_herabgesetzt(self) -> None:
        for konsole in ("12.00", "9.99", ""):
            with self.subTest(konsole=konsole):
                zeile = self._zeile(_fakten("10.00", "11.20", "7.00"), konsole)
                self.assertEqual((qb.STUFE_OK, "bericht.backport_da"), (zeile.stufe, zeile.text))
                self.assertNotIn("backport", qb.fehlendes([zeile]))

    def test_der_bericht_beanstandet_weiter_was_noch_fehlt(self) -> None:
        for fakten, konsole in ((_fakten("10.00", "11.20", "10.00"), "9.99"), (_fakten("10.00", "11.20"), "9.99"),
                                (_fakten("10.00", "11.20", "7.00"), "5.99")):
            with self.subTest(eboot=fakten.eboot_sdk, konsole=konsole):
                self.assertEqual(qb.STUFE_FEHLT, self._zeile(fakten, konsole).stufe)


# ---------------------------------------------------------------------------------------------------------- Weg von der Quelle zu den Fakten
class WegZuDenFaktenTests(_Grundlage):
    """Beide Stellen, die Forges Antwort lesen, geben den Pfad weiter - sonst bliebe ``eboot_sdk`` leer."""

    def test_die_fakten_tragen_das_sdk_der_eboot_wenn_ein_pfad_da_ist(self) -> None:
        ordner = self.spielordner("a", herabgesetzt(baue_elf(0x10000038), 7))
        daten = _daten("10.00", "11.20")
        self.assertEqual("7.00", fc.quellfakten(daten, ordner).eboot_sdk)
        self.assertEqual("", fc.quellfakten(daten).eboot_sdk, "ohne Pfad rein: nichts wird gelesen")
        self.assertEqual("", fc.quellfakten(daten, self.pfad("gibt_es_nicht")).eboot_sdk)

    def test_quellfakten_lesen_gibt_den_pfad_weiter(self) -> None:
        ordner = self.spielordner("a", herabgesetzt(baue_elf(0x10000038), 7))
        with mock.patch.object(fc, "inspect_daten", return_value=_daten("10.00", "11.20")):
            fakten = fc.quellfakten_lesen("forge", ordner)
        self.assertEqual("7.00", fakten.eboot_sdk)
        self.assertTrue(fakten.herabgesetzt)
        self.assertFalse(fakten.backport_noetig("12.00"))

    def test_lesen_fuer_seite_7_gibt_den_pfad_weiter(self) -> None:
        ordner = self.spielordner("a", herabgesetzt(baue_elf(0x10000038), 7))
        with mock.patch.object(fc, "inspect_daten", return_value=_daten("10.00", "11.20")):
            info = fc.lesen("forge", ordner, arbeitsordner=self.tmp)
        self.addCleanup(shutil.rmtree, info.arbeit or "", True)
        self.assertEqual("7.00", info.fakten.eboot_sdk)

    def test_ein_fehler_beim_lesen_der_eboot_stoert_die_pruefung_nicht(self) -> None:
        ordner = self.spielordner("a", als_self(baue_elf(0x10000038)))
        with mock.patch.object(ps, "sdk_wort_lesen", side_effect=OSError("weg")):
            self.assertEqual("", fc.quellfakten(_daten("10.00", "11.20"), ordner).eboot_sdk)


def _forge_befehlszeile() -> str:
    unter = fc.unterordner()
    pfad = PROJEKT / fc.ORDNER / unter / fc.dateiname() if unter else None
    return str(pfad) if pfad and pfad.is_file() else ""


@unittest.skipUnless(_forge_befehlszeile(), "keine Befehlszeile von Dump Forge fuer diese Plattform")
class MitEchterForgeBefehlszeileTests(_Grundlage):
    """Die Meldung nachgestellt: ein herabgesetztes Spiel mit unveraenderter ``param.json``, wie es Werkzeuge hinterlassen, die nur das SDK
    der Programme senken - einmal ohne ``fakelib/`` (Forge sagt dazu nichts), einmal mit AMPR EMU dort (Forge: ``backport`` leer)."""

    def _lesen(self, ordner: str) -> "fc.QuellFakten":
        fakten = fc.quellfakten_lesen(_forge_befehlszeile(), ordner)
        self.assertIsNotNone(fakten, "Forge liest den Ordner")
        return fakten

    def test_herabgesetzt_ohne_fakelib_wird_nicht_mehr_beanstandet(self) -> None:
        fakten = self._lesen(self.spielordner("b", herabgesetzt(baue_elf(0x10000038), 7)))
        self.assertEqual(("10.00", "11.20", False), (fakten.sdk, fakten.firmware, fakten.backport_vorhanden), "Forge sieht nur die param.json")
        self.assertEqual("7.00", fakten.eboot_sdk)
        self.assertFalse(fakten.backport_noetig("9.99"))
        self.assertTrue(fakten.backport_schon_da("9.99"))

    def test_herabgesetzt_mit_ampr_in_fakelib_wird_nicht_mehr_beanstandet(self) -> None:
        ordner = self.spielordner("d", herabgesetzt(baue_elf(0x10000038), 7))
        os.makedirs(os.path.join(ordner, "fakelib"))
        Path(ordner, "fakelib", "libSceAmpr.sprx").write_bytes(b"\x7fELF" + b"ampr_emu" + bytes(2048))
        fakten = self._lesen(ordner)
        self.assertFalse(fakten.backport_vorhanden, "in fakelib liegt nur ein Emulator")
        self.assertEqual("7.00", fakten.backport_firmware)
        self.assertFalse(fakten.backport_noetig("9.99"))

    def test_gegenprobe_ein_nicht_herabgesetztes_spiel_wird_weiter_beanstandet(self) -> None:
        fakten = self._lesen(self.spielordner("o", als_self(baue_elf(0x10000038))))
        self.assertEqual("10.00", fakten.eboot_sdk)
        self.assertFalse(fakten.herabgesetzt)
        self.assertTrue(fakten.backport_noetig("9.99"))

    def test_dasselbe_in_einer_ffpkg(self) -> None:
        for name, elf, noetig in (("herab.ffpkg", herabgesetzt(baue_elf(0x10000038, davor=0x180000), 7), False),
                                  ("orig.ffpkg", als_self(baue_elf(0x10000038, davor=0x180000)), True)):
            with self.subTest(abbild=name):
                ziel = self.ffpkg(name, {"eboot.bin": elf, "sce_sys/param.json": PARAM_JSON, "Media/x.bin": FUELLUNG})
                fakten = fc.quellfakten_lesen(_forge_befehlszeile(), ziel)
                if fakten is None:
                    self.skipTest("Forge liest das Testabbild nicht")
                self.assertEqual(noetig, fakten.backport_noetig("9.99"))


if __name__ == "__main__":
    unittest.main()
