"""
PS5 Dump Validator – .ffpfs / .ffpfsc Datei-Prüfung
Streaming-Read, SHA-256, Magic-Header-Check, Verschachtelungsprüfung.

PFS-Image-Header-Struktur (erzeugt von mkpfs pack file):
  Offset 0x00  int64  version  = 2          (PFS-Version)
  Offset 0x08  int64  magic    = 0x1332A0B  (PFS_MAGIC)

PFSC-Block-Header (innerhalb des PFS-Images):
  Offset 0x00  int32  magic    = 0x43534650 (PFSC_MAGIC = "PFSC")
  Offset 0x04  int32  unk4     = 0
  Offset 0x08  int32  unk8     = 6
  Offset 0x0C  int32  block_sz = 65536
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Callable

from ps5_validator.core.validator_base import (
    GEMEINSAME_MELDUNGEN, BaseValidator, ValidationResult,
)
from ps5_validator.utils.hashing import sha256_stream
from ps5_validator.utils.file_io import fmt_bytes
from ps5_validator.utils.logger import get_logger

# ── PFS-Image-Header (äußerer Container, erzeugt von mkpfs pack file) ──────
# Header-Struktur: version (int64) @ 0x00, magic (int64) @ 0x08
PFS_MAGIC_VALUE  = 0x1332A0B   # mkpfs consts.PFS_MAGIC
PFS_VERSION_FFPFSC = 2          # Standard-Version für .ffpfsc

# ── PFSC-Block-Header (innerhalb des PFS-Images) ────────────────────────────
PFSC_MAGIC_VALUE = 0x43534650  # "PFSC" in little-endian

# Bekannte Versionen im PFS-Kopf - als Kennung der Vorlage in MELDUNGEN
# (bis zur Durchsicht, Runde 17, stand hier der deutsche Text selbst).
KNOWN_PFS_VERSIONS = {
    2: "pfs_version_2",
    1: "pfs_version_1",
}

# ── exFAT-Bootsektor ────────────────────────────────────────────────────────
# Ein exFAT-Abbild trägt ab Offset 0x03 die Kennung "EXFAT   " (mit drei
# Leerzeichen). Wird sie auf der innersten Ebene gefunden, steckt dort ein
# exFAT-Abbild statt der Spieldateien – siehe _check_nesting().
EXFAT_SIGNATURE = b"EXFAT   "
EXFAT_SIGNATURE_OFFSET = 0x03

# ── UFS2-Superblock (ein eingebettetes .ffpkg) ──────────────────────────────
# Ein .ffpkg ist ein rohes UFS2-Abbild. Sein Superblock liegt bei 65536, die
# Kennung 0x19540119 darin bei Offset 1372.
UFS2_MAGIC_VALUE = 0x19540119
UFS2_SUPERBLOCK_OFFSET = 65536
UFS2_MAGIC_OFFSET_IN_SB = 1372

# Dateiendungen, die auf der innersten Ebene nichts zu suchen haben: Wer dort
# ein weiteres Abbild findet, hat einen falsch verschachtelten Container.
NESTED_IMAGE_SUFFIXES = (".exfat", ".pfs", ".ffpfs", ".ffpfsc", ".ffpkg", ".img")

_ERNEUT = "Typisch für eine abgebrochene Kopie oder Übertragung – die Datei neu kopieren oder neu erzeugen."
_FFPFS_KEIN_CONTAINER = (
    "Eine .ffpfs ist ein Abbild-Spiel, kein Container – sce_sys/param.json muss direkt "
    "in der Abbildwurzel liegen. ShadowMount+ meldet sonst „missing/invalid param.json“ "
    "und zeigt das Spiel nicht an. Neu bauen lassen oder als .ffpfsc verwenden.")

#: Befunde und Zusammenfassungswerte als Vorlagen (Durchsicht, Runde 17) -
#: deutsch als Vorgabe, uebersetzt ueber ``texte=`` (Praefix "validator.").
#: Die Vorgaben sind wortgleich mit dem frueheren Text: test_validator_nesting
#: und test_ffpfs_bauform lesen sie. "vollstaendig" ist ein Merker, den
#: test_incomplete_dump vergleicht - deshalb in Umschrift.
MELDUNGEN: dict[str, str] = {
    **GEMEINSAME_MELDUNGEN,
    "pfs_abgeschnitten": ("Abbild abgeschnitten: Der PFS-Kopf nennt {soll} ({bloecke} Blöcke "
                          "zu je {blockgroesse}), die Datei hat nur {ist} (es fehlen "
                          "{fehlend}). " + _ERNEUT),
    "pfs_empfohlen_fehlt": "Empfohlene Datei fehlt im Container: {dateien}",
    "pfs_kritisch_vollstaendig": "vollstaendig",
    "pfs_kritisch_unvollstaendig": "unvollständig ({anzahl} fehlen)",
    "pfs_pflicht_fehlt": ("Pflichtdateien fehlen im Container: {dateien}. Der Container wurde "
                          "vermutlich aus einem unvollständigen Dump gebaut und startet auf "
                          "der Konsole nicht."),
    "pfs_innen_dateien_unlesbar": "nicht lesbar ({fehler})",
    "pfs_nesting_exfat_leer": "falsch aufgebaut (exFAT-Abbild ohne Dateien)",
    "pfs_exfat_leer": "Das exFAT-Abbild im Container enthält keine Dateien.",
    "pfs_nesting_ohne_mkpfs": "nicht geprüft (mkpfs nicht verfügbar)",
    "pfs_aussen_befund": "Äußere Ebene: {befund}",
    "pfs_aussen_weitere": "Äußere Ebene: {anzahl} weitere Befunde",
    "pfs_nesting_flach_ffpfs": ("flach aufgebaut ({anzahl} Einträge in der Abbildwurzel) "
                                "– die vorgeschriebene Form für .ffpfs"),
    "pfs_nesting_flach_container": ("flach aufgebaut ({anzahl} Einträge direkt im Container, "
                                    "kein inneres Image)"),
    "pfs_flach_ffpfsc": ("Ungewöhnlicher Aufbau: Der Container enthält {anzahl} Einträge "
                         "direkt statt genau eines inneren PFS-Images. Eine .ffpfsc ist ein "
                         "Container und trägt genau ein inneres Abbild."),
    "pfs_flach_pfs": ("Ungewöhnlicher Aufbau: Der Container enthält {anzahl} Einträge direkt "
                      "statt genau eines inneren PFS-Images. Sieht aus wie das innere Abbild "
                      "eines Containers – dann ist nicht diese Datei zu prüfen, sondern die "
                      ".ffpfsc darum herum."),
    "pfs_nesting_geschachtelt": "geschachtelt (ein eingebettetes Abbild statt der Spieldateien)",
    "pfs_ffpfs_eingebettet_name": ("Ungewöhnlicher Aufbau: In der Wurzel dieser .ffpfs liegt "
                                   "nur „{name}“. " + _FFPFS_KEIN_CONTAINER),
    "pfs_ffpfs_eingebettet": ("Ungewöhnlicher Aufbau: In der Wurzel dieser .ffpfs liegt nur "
                              "ein einzelner Eintrag. " + _FFPFS_KEIN_CONTAINER),
    "pfs_nesting_nicht_zusammenhaengend": "nicht prüfbar (Nutzlast nicht zusammenhängend)",
    "pfs_nesting_ok_exfat": "in Ordnung (exFAT-Abbild im Container)",
    "pfs_nesting_ok_ufs2": "in Ordnung (UFS2-Abbild im Container)",
    "pfs_nesting_weder": "falsch aufgebaut (innen weder PFS- noch exFAT-Abbild)",
    "pfs_innen_weder": ("Innere Ebene ist weder ein PFS- noch ein exFAT-Abbild "
                        "(magic=0x{magic}) - der Container enthält nicht das, was eine der "
                        "beiden regulären Bauformen erwarten lässt."),
    "pfs_innen_befund": "Innere Ebene: {befund}",
    "pfs_nesting_innen_leer": "falsch aufgebaut (innere Ebene leer)",
    "pfs_innen_leer": "Innere Ebene enthält keine Dateien.",
    "pfs_art_exfat": "exFAT-Abbild",
    "pfs_art_pfs": "PFS-Image",
    "pfs_art_weiteres": "weiteres Abbild",
    "pfs_nesting_falsch": "falsch verschachtelt ({name}, {art})",
    "pfs_falsch_verschachtelt": ("Falsch verschachtelt: Auf der innersten Ebene liegt {art} "
                                 "'{name}' statt der Spieldateien. So gebaute Container sind "
                                 "auf der Konsole unbrauchbar. Ursache ist ein inneres Image "
                                 "ohne --raw; die Datei muss neu erzeugt werden."),
    "pfs_nesting_ok": "in Ordnung (Spieldateien auf der innersten Ebene)",
    "pfs_nesting_nicht_pruefbar": "nicht prüfbar ({fehler})",
    "pfs_magic_unbekannt": "unbekannt",
    "pfs_magic_pfs": "PFS-Image ({version})",
    "pfs_version_2": "PFS-Image v2 (ffpfsc, mkpfs pack file)",
    "pfs_version_1": "PFS-Image v1 (ffpfs, unkomprimiert)",
    "pfs_version_andere": "v{version}",
    "pfs_magic_pfsc_ohne": "PFSC-Block (raw, ohne PFS-Container)",
    "pfs_magic_pfsc": "PFSC-Block (raw)",
    "pfs_magic_unbekannt_kopf": "unbekannt (version=0x{version}, magic=0x{magic})",
    "pfs_magic_unbekannt_32": "unbekannt (0x{magic})",
    "pfs_kopf_unbekannt": "Unbekannter PFS-Header: version=0x{version}, magic=0x{magic}",
    "pfs_magic32_unbekannt": "Unbekannter Magic-Header: 0x{magic}",
    "pfs_kopf_lesefehler": "Header-Lesefehler: {fehler}",
}


def _ensure_mkpfs_importable() -> bool:
    """Legt den mitgelieferten MkPFS-Quellordner auf den Importpfad.

    Im Programm hängt mkpfs meist schon im Pfad (die Oberfläche entpackt die
    eingebettete Engine beim Start). Beim eigenständigen Aufruf des Validators
    – etwa aus Tests oder der Kommandozeile – steht der Quellordner dagegen nur
    im Projektstamm, z. B. ``MkPFS-1.0.0/``.

    **Der mitgelieferte Ordner hat Vorrang, und zwar ausdrücklich.** Bis zum
    30.08.2026 stand hier zuerst ein blankes ``import mkpfs`` und die Suche
    nach dem Quellordner erst als Rückfall. Auf einer Anlage mit ``pip install
    mkpfs`` gewann damit die Fassung aus ``site-packages`` – gemessen am
    30.08.2026: beide meldeten Version ``0.0.9``, aber nur die mitgelieferte
    kannte ``fold_inner_name_to_ascii``. Acht Tests fielen deshalb wochenlang,
    und die Ursache wurde als „hypothesis fehlt" fehlgedeutet. Seit dem
    01.09.2026 liegt hier 1.0.0; die installierte Fassung ist damit an der
    Nummer erkennbar – verlassen kann man sich darauf aber nicht, der Vorrang
    gilt weiter.

    Schlimmer als die roten Tests war die stille Wirkung: Das Programm selbst
    lud dann die fremde Engine – dieselbe, gegen die es seine eigenen
    Anpassungen mitliefert.
    """
    projekt_stamm = Path(__file__).resolve().parents[2]
    for kandidat in sorted(projekt_stamm.glob("MkPFS-*"), reverse=True):
        if not (kandidat / "mkpfs" / "__init__.py").is_file():
            continue
        if str(kandidat) not in sys.path:
            sys.path.insert(0, str(kandidat))
        # Hat schon jemand eine fremde Fassung geladen, hält sys.modules sie
        # fest und ein neuer sys.path-Eintrag käme zu spät. Dann muss der
        # Eintrag weichen - aber nur, wenn er wirklich woandershin zeigt.
        geladen = sys.modules.get("mkpfs")
        herkunft = getattr(geladen, "__file__", "") or ""
        if geladen is not None and not str(herkunft).startswith(str(kandidat)):
            for name in [n for n in sys.modules
                         if n == "mkpfs" or n.startswith("mkpfs.")]:
                del sys.modules[name]
        try:
            import mkpfs  # noqa: F401
            return True
        except ImportError:
            continue

    # Kein mitgelieferter Ordner - dann ist eine installierte Fassung besser
    # als gar keine.
    try:
        import mkpfs  # noqa: F401
        return True
    except ImportError:
        return False


def ermittle_bauform(pfad: str | Path) -> dict[str, object] | None:
    """Ermittelt, wie ein ``.ffpfsc``/``.ffpfs`` aufgebaut ist - ohne Urteil.

    Reine Feststellung, gedacht fuer die Anzeige neben dem Quellfeld: Welche
    Ebenen stecken im Container? Gelesen werden nur Kopf, Inode-Tabelle und
    Verzeichnisbloecke, nie Nutzdaten - unabhaengig von der Dateigroesse sind
    das weniger als 1 MB.

    Der Unterschied zu :meth:`FfpfsValidator._check_nesting`: Diese Funktion
    stellt nur fest, *was* da ist. Ob das in Ordnung ist, entscheidet weiterhin
    der Validator - er meldet z. B. die dreifache Verschachtelung als Fehler.

    Args:
        pfad: Pfad zur Container-Datei.

    Returns:
        ``{"bauform": ..., "inneres_abbild": ..., "aeussere_dateien": ...}``
        mit ``bauform`` aus:

        * ``"flach"``     - die Dateien liegen direkt in der Wurzel
                            (``mkpfs pack folder --raw``). Fuer eine ``.ffpfs``
                            ist das die vorgeschriebene Form, fuer eine
                            ``.ffpfsc`` fehlt dann die Containerebene.
        * ``"pfs"``       - Container -> rohes PFS -> Dateien
                            (der Aufbau einer ``.ffpfsc`` aus einem Dump-Ordner)
        * ``"exfat"``     - Container -> exFAT-Abbild -> Dateien
                            (``mkpfs pack folder`` ohne ``--raw``,
                            ``mkpfs pack file`` auf eine ``.exfat``)
        * ``"ufs2"``      - Container -> UFS2-Abbild (eingebettete ``.ffpkg``)
        * ``"dreifach"``  - Container -> PFS -> Abbild -> Dateien, eine Ebene
                            zu viel
        * ``"unbekannt"`` - Aufbau nicht bestimmbar

        ``None``, wenn die Datei kein lesbarer PFS-Container ist.
    """
    if not _ensure_mkpfs_importable():
        return None
    try:
        from mkpfs import pfs as mkpfs_pfs
    except ImportError:
        return None

    fpath = Path(pfad)
    befund: dict[str, object] = {"bauform": "unbekannt", "inneres_abbild": "", "aeussere_dateien": 0}
    handle = None
    try:
        aussen = mkpfs_pfs.inspect_pfs_image(fpath, verify_payloads=False)
        # Ohne gueltige PFS-Kennung ist es kein Container - dann gibt es auch
        # nichts anzuzeigen. parse_image_header liest die Kopfbytes ohne
        # Ruecksicht auf die Magic, eine beliebige Datei kaeme sonst durch.
        if aussen.header is None or aussen.header.magic != PFS_MAGIC_VALUE:
            return None
        befund["aeussere_dateien"] = len(aussen.file_inodes)
        if len(aussen.file_inodes) != 1:
            befund["bauform"] = "flach"
            return befund

        geoeffnet = mkpfs_pfs.open_inner_file_view(fpath)
        if geoeffnet is None:
            return befund
        view, handle, inner_name = geoeffnet
        befund["inneres_abbild"] = inner_name

        view.seek(0)
        kopf = view.read(16)
        if kopf[EXFAT_SIGNATURE_OFFSET:EXFAT_SIGNATURE_OFFSET + len(EXFAT_SIGNATURE)] == EXFAT_SIGNATURE:
            befund["bauform"] = "exfat"
            return befund

        try:
            view.seek(UFS2_SUPERBLOCK_OFFSET + UFS2_MAGIC_OFFSET_IN_SB)
            ufs2_magic = struct.unpack("<i", view.read(4))[0] & 0xFFFFFFFF
        except Exception:
            ufs2_magic = 0
        if ufs2_magic == UFS2_MAGIC_VALUE:
            befund["bauform"] = "ufs2"
            return befund

        view.seek(0)
        inner_header = mkpfs_pfs.parse_image_header(view)
        if inner_header.magic != PFS_MAGIC_VALUE:
            return befund

        inodes = mkpfs_pfs.parse_image_inodes(view, inner_header)
        fehler: list[str] = []
        uroot, _fpt, _dirents, _spezial = mkpfs_pfs.parse_superroot_and_indexes(
            view, inner_header, inodes, fehler)
        dateien, ordner, _rest = mkpfs_pfs.build_tree_from_uroot(
            view, inner_header, inodes, uroot, fehler)
        befund["innere_dateien"] = len(dateien)

        # Genau ein Eintrag ohne Unterordner, und der ist selbst ein Abbild:
        # dann steckt eine Ebene zu viel darin.
        if len(dateien) == 1 and max(0, len(ordner) - 1) == 0:
            rel_name, inode_nummer = next(iter(dateien.items()))
            innerster = FfpfsValidator._read_innermost_head(
                mkpfs_pfs, view, inner_header, inodes[inode_nummer])
            ist_exfat = (innerster[EXFAT_SIGNATURE_OFFSET:EXFAT_SIGNATURE_OFFSET + len(EXFAT_SIGNATURE)]
                         == EXFAT_SIGNATURE)
            ist_pfs = (len(innerster) >= 16
                       and struct.unpack_from("<q", innerster, 0x08)[0] == PFS_MAGIC_VALUE)
            if ist_exfat or ist_pfs or rel_name.lower().endswith(NESTED_IMAGE_SUFFIXES):
                befund["bauform"] = "dreifach"
                return befund

        befund["bauform"] = "pfs"
        return befund
    except Exception:
        return befund if befund["bauform"] != "unbekannt" else None
    finally:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass


class FfpfsValidator(BaseValidator):
    """Validiert eine .ffpfs oder .ffpfsc Datei."""

    MELDUNGEN = MELDUNGEN

    def __init__(
        self,
        progress_cb: Callable | None = None,
        cancel_flag: Callable | None = None,
        verbose: bool = False,
        texte: dict | None = None,
    ) -> None:
        super().__init__(progress_cb, cancel_flag, verbose, texte=texte)
        self._log = get_logger()

    @staticmethod
    def _read_innermost_head(mkpfs_pfs, view, header, inode, size: int = 32) -> bytes:
        """Liest die ersten Bytes einer Datei INNERHALB des inneren Images.

        Unkomprimierte Nutzlasten lassen sich direkt an ihrem Blockversatz
        lesen. Komprimierte brauchen die logische Sicht von mkpfs, die nur die
        angefassten Blöcke entpackt. Fehlt sie in einer künftigen
        mkpfs-Version, liefert die Funktion leere Bytes statt zu scheitern –
        die Entscheidung stützt sich dann auf Anzahl und Namen der Einträge.
        """
        try:
            if not inode.is_compressed and inode.blocks > 0 and inode.db:
                return mkpfs_pfs.read_image_bytes(view, header, inode.db[0] * header.block_size, size)
            view_cls = getattr(mkpfs_pfs, "_LogicalFileView", None)
            if view_cls is None:
                return b""
            return view_cls(view, header, inode).read(size)
        except Exception:
            return b""

    def _check_size(self, fpath: Path, file_size: int, result: ValidationResult) -> bool:
        """Haelt die Dateigroesse gegen die Blockzahl im PFS-Kopf.

        Ein vom Programm gebautes Abbild ist genau ``ndblock * block_size``
        Bytes gross - am 17.09.2026 an 9 von 9 frisch gebauten .ffpfs und
        .ffpfsc (komprimiert und unkomprimiert) gemessen. Ist die Datei
        kleiner, fehlen Bloecke am Ende. Groesser ist kein Fehler (angehaengte
        Bytes liest niemand) und wird nur vermerkt.

        Returns:
            False, wenn das Abbild abgeschnitten ist (Ergebnis ist dann gesetzt).
        """
        if not _ensure_mkpfs_importable():
            return True
        try:
            from mkpfs import pfs as mkpfs_pfs

            with open(fpath, "rb") as fh:
                kopf = mkpfs_pfs.parse_image_header(fh)
        except Exception as exc:
            self._log.info(f"PFS-Kopf für die Größenprüfung nicht lesbar: {exc}")
            return True
        if kopf.magic != PFS_MAGIC_VALUE or kopf.block_size <= 0 or kopf.ndblock <= 0:
            return True

        soll = int(kopf.ndblock) * int(kopf.block_size)
        result.summary["image_size"] = fmt_bytes(soll)
        if file_size >= soll:
            if file_size > soll:
                result.summary["trailing_bytes"] = file_size - soll
            return True

        fehlend = soll - file_size
        result.summary["missing_bytes"] = fehlend
        def _genau(anzahl: int) -> str:
            # Gerundet und byte-genau: ein fehlender Block ginge sonst in der
            # Rundung unter ("nennt 6.2 MB, hat nur 6.2 MB").
            return f"{fmt_bytes(anzahl)} ({anzahl:,} Bytes)".replace(",", ".")

        result.set_corrupted(self._text(
            "pfs_abgeschnitten", soll=_genau(soll), bloecke=kopf.ndblock,
            blockgroesse=fmt_bytes(kopf.block_size), ist=_genau(file_size),
            fehlend=_genau(fehlend)))
        return False

    def _check_critical_files(self, inner_files: dict, result: ValidationResult) -> None:
        """Prüft, ob die Pflichtdateien eines PS5-Dumps im Container liegen.

        Verwendet dieselbe Liste wie die Ordnerprüfung
        (``dump_validator.CRITICAL_FILES``), damit ein Ordner und der daraus
        gebaute Container zum selben Urteil kommen. Vergleich ohne Rücksicht
        auf Groß-/Kleinschreibung, weil PFS Namen unabhängig davon ablegen kann.
        """
        try:
            from ps5_validator.modules.dump_validator import CRITICAL_FILES, RECOMMENDED_FILES
        except Exception as exc:  # pragma: no cover - nur bei kaputter Installation
            self._log.info(f"Kritische Dateiliste nicht ladbar: {exc}")
            return

        vorhanden = {name.replace("\\", "/").lower() for name in inner_files}

        def _fehlend(liste) -> list[str]:
            return [eintrag for eintrag in liste
                    if eintrag.replace("\\", "/").lower() not in vorhanden]

        # Empfohlene Dateien nur als Hinweis - sie fehlen je nach Dumper auch
        # bei einwandfreien Backups (siehe Kommentar in dump_validator.py).
        nur_empfohlen = _fehlend(RECOMMENDED_FILES)
        if nur_empfohlen:
            result.summary["recommended_missing"] = nur_empfohlen
            result.add_error(self._text("pfs_empfohlen_fehlt", dateien=", ".join(nur_empfohlen)))

        fehlend = _fehlend(CRITICAL_FILES)
        if not fehlend:
            result.summary["critical_files"] = self._text("pfs_kritisch_vollstaendig")
            return

        result.summary["critical_missing"] = fehlend
        result.summary["critical_files"] = self._text("pfs_kritisch_unvollstaendig",
                                                      anzahl=len(fehlend))
        result.set_failed(self._text("pfs_pflicht_fehlt", dateien=", ".join(fehlend)))

    def _check_exfat_inner(self, view, result: ValidationResult) -> None:
        """Prueft die Spieldateien in einem exFAT-Abbild innerhalb des Containers.

        So gebaute Container entstehen bei ``mkpfs pack folder`` ohne ``--raw``
        (dann legt mkpfs das exFAT von sich aus dazwischen) und bei
        ``mkpfs pack file`` auf eine ``.exfat``. Beide Wege sind regulaer -
        nur blieb die innerste Ebene bisher ungeprueft, sodass ein aus einem
        unvollstaendigen Dump gebauter Container als fehlerfrei durchging.

        Gelesen werden nur die Verzeichnisbloecke des Abbilds, nicht die
        Nutzdaten; bei einem 117-GB-Container sind das rund 16 Sekunden.
        Scheitert das Auslesen, bleibt es beim Vermerk - die uebrige
        Pruefung soll daran nicht haengen.

        Args:
            view:   Logische Sicht von mkpfs auf das innere Abbild.
            result: Ergebnisobjekt, das ergaenzt wird.
        """
        try:
            from mkpfs.exfat import ExfatReader

            view.seek(0)
            eintraege = list(ExfatReader(view).iter_files())
        except Exception as exc:
            result.summary["inner_files"] = self._text("pfs_innen_dateien_unlesbar", fehler=exc)
            self._log.info(f"exFAT-Innenebene nicht lesbar: {exc}")
            return

        result.summary["inner_files"] = len(eintraege)
        result.summary["inner_bytes"] = sum(max(0, int(e.length)) for e in eintraege)
        if not eintraege:
            result.summary["nesting"] = self._text("pfs_nesting_exfat_leer")
            result.set_failed(self._text("pfs_exfat_leer"))
            return

        self._check_critical_files({e.rel_path: e for e in eintraege}, result)

    def _check_nesting(self, fpath: Path, result: ValidationResult) -> None:
        """Prüft die innere Verschachtelung des Containers (Tiefenprüfung).

        **Die beiden Endungen haben verschiedene Sollformen** - das ist der
        Grund, warum die Prüfung hier gleich zu Anfang verzweigt. ShadowMount+
        (README 1.7alpha12, Z. 229-233 und 533):

        * ``.ffpfsc`` ist ein **Container**: außen genau ein Eintrag, und das
          ist ein Abbild, dessen Inhalt die Spieldateien sind.
        * ``.ffpfs`` ist ein **Abbild-Spiel** wie ``.ffpkg`` und ``.exfat``:
          "sce_sys/param.json must be at image root (no extra top-level
          folder)". Flach ist dort die *richtige* Form, und ein eingebettetes
          Abbild ist der Fehler.

        Bis 05.09.2026 wurden beide gleich behandelt. Eine tadellose, auf der
        Konsole laufende ``.ffpfs`` bekam deshalb den Fehler "Ungewöhnlicher
        Aufbau" - der Anwender verwarf eine gute Datei oder baute sie in genau
        die Form um, mit der ShadowMount+ nichts anfangen kann.

        Für den Container gilt weiter: Ein korrektes ``.ffpfsc`` besteht aus
        zwei Ebenen: dem äußeren Container und darin genau einem rohen,
        unkomprimierten PFS-Image, das die Spieldateien enthält. Fehlt beim
        Bauen des inneren Images ``--raw``, legt mkpfs von sich aus noch ein
        exFAT-Abbild dazwischen. Von außen sieht der Container identisch aus,
        enthält innen aber ein Abbild statt der Spieldateien und ist auf der
        Konsole unbrauchbar.

        ``mkpfs tree`` und ``inspect`` zeigen den Unterschied nicht, weil beide
        nur die äußere Ebene auflisten – dort steht in beiden Fällen genau ein
        Eintrag mit demselben Namen.

        Vollständiges Entpacken wäre dafür unverhältnismäßig, ist aber auch
        nicht nötig: Über die logische Sicht von mkpfs auf die innere Datei
        (``open_inner_file_view``) werden nur Kopf, Inode-Tabelle und
        Verzeichnisblöcke entpackt. Gemessen an einer 392-MB-Datei sind das
        rund 750 KB in 25 Zugriffen und unter 10 ms – unabhängig von der
        Dateigröße, weil der Aufwand an der Zahl der Einträge hängt und nicht
        an den Nutzdaten.
        """
        if not _ensure_mkpfs_importable():
            result.summary["nesting"] = self._text("pfs_nesting_ohne_mkpfs")
            self._log.info("Verschachtelungsprüfung übersprungen: mkpfs nicht importierbar")
            return
        try:
            from mkpfs import pfs as mkpfs_pfs
        except ImportError as exc:
            result.summary["nesting"] = self._text("pfs_nesting_ohne_mkpfs")
            self._log.info(f"Verschachtelungsprüfung übersprungen: {exc}")
            return

        # Drei Faelle, nicht zwei: Neben den beiden Endungen des
        # Programms landet hier auch eine rohe ".pfs" - das innere
        # Abbild, das jemand versehentlich statt des Containers
        # prueft. Fuer die bleibt es beim Hinweis von frueher.
        endung = fpath.suffix.lower()
        ist_container = endung == ".ffpfsc"
        ist_abbildspiel = endung == ".ffpfs"
        handle = None
        try:
            # Aeussere Ebene zuerst: Wie viele Eintraege liegen im Container?
            # verify_payloads=False laesst die teuren Nutzdaten-Durchlaeufe weg.
            aussen = mkpfs_pfs.inspect_pfs_image(fpath, verify_payloads=False)
            # Die Strukturbefunde der aeusseren Ebene (Inode-Bereiche jenseits
            # des Abbilds, Ueberlappungen, Namenstabellen) wurden bis v1.9.24
            # verworfen. Fuer unversehrte Abbilder dieses Programms sind es
            # null (am 17.09.2026 gemessen) - jeder Eintrag ist ein echter Befund.
            for befund in aussen.errors[:5]:
                result.add_error(self._text("pfs_aussen_befund", befund=befund))
            if len(aussen.errors) > 5:
                result.add_error(self._text("pfs_aussen_weitere", anzahl=len(aussen.errors) - 5))
            aussen_dateien = len(aussen.file_inodes)
            result.summary["outer_files"] = aussen_dateien

            if aussen_dateien != 1:
                if ist_abbildspiel:
                    # Eine .ffpfs mit den Spieldateien in der Wurzel: genau so
                    # gehoert es sich. Geprueft wird dann dasselbe wie bei
                    # einem Dump-Ordner - ob die Pflichtdateien da sind.
                    result.summary["nesting"] = self._text("pfs_nesting_flach_ffpfs",
                                                           anzahl=aussen_dateien)
                    self._check_critical_files(aussen.file_inodes, result)
                    return
                # Die von diesem Programm erzeugten Container sind zweistufig:
                # aussen genau ein Eintrag (das rohe innere Image). Liegen die
                # Dateien direkt darin, fehlt diese Stufe.
                result.summary["nesting"] = self._text("pfs_nesting_flach_container",
                                                       anzahl=aussen_dateien)
                result.add_error(self._text(
                    "pfs_flach_ffpfsc" if ist_container else "pfs_flach_pfs",
                    anzahl=aussen_dateien))
                return

            if ist_abbildspiel:
                # Genau ein Eintrag in einer .ffpfs - das ist der Fall, den
                # dieses Programm bis 05.09.2026 selbst gebaut hat: aussen
                # "pfs_image.dat" (oder "Spiel.exfat"/"Spiel.ffpkg"), innen
                # erst die Spieldateien. ShadowMount+ haengt eine .ffpfs als
                # Abbild ein und sucht sce_sys/param.json in der Wurzel - es
                # findet nur dieses eine Abbild und laesst das Spiel weg.
                name_innen = ""
                try:
                    name_innen = next(iter(aussen.file_inodes))
                except StopIteration:
                    pass
                result.summary["nesting"] = self._text("pfs_nesting_geschachtelt")
                result.add_error(
                    self._text("pfs_ffpfs_eingebettet_name", name=name_innen) if name_innen
                    else self._text("pfs_ffpfs_eingebettet"))
                return

            opened = mkpfs_pfs.open_inner_file_view(fpath)
            if opened is None:
                # Einzeldatei, aber nicht als zusammenhaengende, unsignierte
                # Nutzlast abgelegt (z. B. signiert oder verstreut). Kein
                # Fehler - nur nicht auf diesem Weg pruefbar.
                result.summary["nesting"] = self._text("pfs_nesting_nicht_zusammenhaengend")
                return
            view, handle, inner_name = opened
            result.summary["inner_image"] = inner_name

            # Es gibt DREI regulaere Bauformen, je nach Quelle der Konvertierung:
            #   a) aus einem Dump-Ordner: Container -> rohes PFS -> Spieldateien
            #   b) aus einer .exfat:      Container -> exFAT-Abbild
            #   c) aus einer .ffpkg:      Container -> UFS2-Abbild
            # (b) und (c) sind Absicht: Aufgabe 3 und 4 betten die Quelldatei in
            # einem Schritt ein ("mkpfs pack file bettet die .exfat/.ffpkg als
            # einzelne Datei in einen PFS-Container ein"). Wer das als Fehler
            # meldet, erzeugt einen Fehlalarm fuer jeden so gebauten Container.
            view.seek(0)
            kopf = view.read(16)
            if kopf[EXFAT_SIGNATURE_OFFSET:EXFAT_SIGNATURE_OFFSET + len(EXFAT_SIGNATURE)] == EXFAT_SIGNATURE:
                result.summary["nesting"] = self._text("pfs_nesting_ok_exfat")
                result.summary["inner_kind"] = "exfat"
                self._log.info(f"Container enthält ein exFAT-Abbild: {inner_name}")
                self._check_exfat_inner(view, result)
                return

            try:
                view.seek(UFS2_SUPERBLOCK_OFFSET + UFS2_MAGIC_OFFSET_IN_SB)
                ufs2_magic = struct.unpack("<i", view.read(4))[0] & 0xFFFFFFFF
            except Exception:
                ufs2_magic = 0
            if ufs2_magic == UFS2_MAGIC_VALUE:
                result.summary["nesting"] = self._text("pfs_nesting_ok_ufs2")
                result.summary["inner_kind"] = "ffpkg"
                self._log.info(f"Container enthält ein UFS2-Abbild: {inner_name}")
                return

            view.seek(0)
            inner_header = mkpfs_pfs.parse_image_header(view)
            if inner_header.magic != PFS_MAGIC_VALUE:
                result.summary["nesting"] = self._text("pfs_nesting_weder")
                result.set_failed(self._text("pfs_innen_weder",
                                             magic=f"{inner_header.magic:016X}"))
                return
            result.summary["inner_kind"] = "pfs"

            inodes = mkpfs_pfs.parse_image_inodes(view, inner_header)
            parse_errors: list[str] = []
            uroot, _fpt, _dirents, _special = mkpfs_pfs.parse_superroot_and_indexes(
                view, inner_header, inodes, parse_errors
            )
            files, dirs, _ = mkpfs_pfs.build_tree_from_uroot(
                view, inner_header, inodes, uroot, parse_errors
            )
            file_count = len(files)
            dir_count = max(0, len(dirs) - 1)   # der Wurzeleintrag "" zaehlt nicht mit
            result.summary["inner_files"] = file_count
            result.summary["inner_dirs"] = dir_count
            for parse_error in parse_errors[:5]:
                result.add_error(self._text("pfs_innen_befund", befund=parse_error))

            if file_count == 0:
                result.summary["nesting"] = self._text("pfs_nesting_innen_leer")
                result.set_failed(self._text("pfs_innen_leer"))
                return

            # Der eigentliche Fehlerfall: genau ein Eintrag, keine Ordner - und
            # dieser Eintrag ist selbst wieder ein Abbild.
            if file_count == 1 and dir_count == 0:
                rel_name, inode_number = next(iter(files.items()))
                head = self._read_innermost_head(
                    mkpfs_pfs, view, inner_header, inodes[inode_number]
                )
                ist_exfat = head[EXFAT_SIGNATURE_OFFSET:EXFAT_SIGNATURE_OFFSET + len(EXFAT_SIGNATURE)] == EXFAT_SIGNATURE
                ist_pfs = len(head) >= 16 and struct.unpack_from("<q", head, 0x08)[0] == PFS_MAGIC_VALUE
                heisst_wie_abbild = rel_name.lower().endswith(NESTED_IMAGE_SUFFIXES)
                if ist_exfat or ist_pfs or heisst_wie_abbild:
                    art = self._text("pfs_art_exfat" if ist_exfat else (
                        "pfs_art_pfs" if ist_pfs else "pfs_art_weiteres"))
                    result.summary["nesting"] = self._text("pfs_nesting_falsch",
                                                           name=rel_name, art=art)
                    result.set_failed(self._text("pfs_falsch_verschachtelt",
                                                 art=art, name=rel_name))
                    return

            result.summary["nesting"] = self._text("pfs_nesting_ok")
            self._log.info(
                f"Verschachtelung geprüft: {file_count} Dateien in {dir_count} Ordnern "
                f"innerhalb von {inner_name}"
            )

            # Die Namensliste der innersten Ebene liegt jetzt ohnehin vor - also
            # gleich pruefen, ob die Pflichtdateien eines PS5-Dumps enthalten
            # sind. Ein aus einem unvollstaendigen Ordner gebauter Container ist
            # formal gueltig, startet auf der Konsole aber nicht; ohne diese
            # Pruefung faellt das nur auf, wenn man den Ordner selbst prueft.
            self._check_critical_files(files, result)
        except Exception as exc:
            # Eine misslungene Tiefenpruefung darf die uebrige Validierung nicht
            # scheitern lassen - sie wird als Hinweis vermerkt.
            result.summary["nesting"] = self._text("pfs_nesting_nicht_pruefbar", fehler=exc)
            self._log.info(f"Verschachtelungsprüfung fehlgeschlagen: {exc}")
        finally:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass

    def validate(self, path: str) -> ValidationResult:
        result = ValidationResult(mode="ffpfs")
        fpath  = Path(path)

        # ── Existenz prüfen ──────────────────────────────────────────────────
        if not fpath.exists():
            result.set_missing(self._text("datei_fehlt", pfad=path))
            return result
        if not fpath.is_file():
            result.set_failed(self._text("keine_regulaere_datei", pfad=path))
            return result

        try:
            file_size = fpath.stat().st_size
        except OSError as exc:
            result.set_failed(self._text("groesse_unlesbar", fehler=exc))
            return result

        if file_size == 0:
            result.set_corrupted(self._text("datei_leer"))
            return result

        self._log.info(f"Starte FFPFS-Validierung: {fpath.name} ({fmt_bytes(file_size)})")
        result.summary["file_size"] = fmt_bytes(file_size)
        result.summary["files_scanned"] = 1

        # ── Magic-Header prüfen (erste 16 Bytes) ────────────────────────────
        # PFS-Image-Header: version (int64) @ 0x00, magic (int64) @ 0x08
        magic_info = self._text("pfs_magic_unbekannt")
        ist_pfs_abbild = False
        try:
            with open(fpath, "rb") as fh:
                header = fh.read(16)

            if len(header) >= 16:
                # PFS-Image-Header: version @ 0x00 (int64), magic @ 0x08 (int64)
                version = struct.unpack_from("<q", header, 0x00)[0]
                magic   = struct.unpack_from("<q", header, 0x08)[0]

                if magic == PFS_MAGIC_VALUE:
                    # Korrekter PFS-Image-Container (mkpfs pack file)
                    ist_pfs_abbild = True
                    kennung = KNOWN_PFS_VERSIONS.get(version)
                    ver_name = (self._text(kennung) if kennung
                                else self._text("pfs_version_andere", version=version))
                    magic_info = self._text("pfs_magic_pfs", version=ver_name)
                    self._log.info(
                        f"PFS-Header erkannt: version={version}, "
                        f"magic=0x{magic:016X} ({magic_info})"
                    )
                else:
                    # Kein PFS-Image – prüfe ob es ein roher PFSC-Block ist
                    if len(header) >= 4:
                        pfsc_magic = struct.unpack_from("<I", header, 0x00)[0]
                        if pfsc_magic == PFSC_MAGIC_VALUE:
                            magic_info = self._text("pfs_magic_pfsc_ohne")
                            self._log.info(f"PFSC-Magic erkannt (raw): 0x{pfsc_magic:08X}")
                        else:
                            magic_info = self._text("pfs_magic_unbekannt_kopf",
                                                    version=f"{version:016X}",
                                                    magic=f"{magic:016X}")
                            result.add_error(self._text("pfs_kopf_unbekannt",
                                                        version=f"{version:016X}",
                                                        magic=f"{magic:016X}"))
            elif len(header) >= 4:
                # Datei zu kurz für vollständigen Header – nur int32 lesen
                magic32 = struct.unpack_from("<I", header, 0x00)[0]
                if magic32 == PFSC_MAGIC_VALUE:
                    magic_info = self._text("pfs_magic_pfsc")
                else:
                    magic_info = self._text("pfs_magic_unbekannt_32", magic=f"{magic32:08X}")
                    result.add_error(self._text("pfs_magic32_unbekannt", magic=f"{magic32:08X}"))

        except OSError as exc:
            result.add_error(self._text("pfs_kopf_lesefehler", fehler=exc))

        result.summary["magic"] = magic_info

        # ── Groesse gegen den PFS-Kopf ──────────────────────────────────────
        # Vor allem anderen: Einem abgeschnittenen Abbild fehlen die Bloecke am
        # Ende, Kopf und Verzeichnisse am Anfang sind aber da. Bis v1.9.24 kam
        # es deshalb durch alle Pruefungen - gemessen am 17.09.2026: auf 1 MB
        # gekuerzte .ffpfs/.ffpfsc galten als bestanden.
        if ist_pfs_abbild and not self._check_size(fpath, file_size, result):
            return result

        # ── Tiefenprüfung der Verschachtelung ───────────────────────────────
        # Vor dem teuren Streaming-Read, damit ein falsch aufgebauter Container
        # sofort auffällt. Kostet nach Messung unter 1 MB und ~10 ms.
        self._check_nesting(fpath, result)

        # ── Vollständiger Streaming-Read + SHA-256 ───────────────────────────
        read_errors: list[str] = []
        file_hash = ""
        try:
            with open(fpath, "rb") as fh:
                file_hash, read_errors = sha256_stream(
                    fh,
                    total_size=file_size,
                    progress_cb=lambda d, t: self._report_progress(d, t, fpath.name),
                    cancel_cb=self._is_cancelled,
                    lesefehler=self._vorlage("lesefehler_byte"),
                )
        except OSError as exc:
            result.set_corrupted(self._text("datei_unlesbar", fehler=exc))
            return result

        if self._is_cancelled():
            result.set_skipped(self._text("abgebrochen_ungelesen"))
            return result

        result.hashes[fpath.name] = file_hash
        result.summary["read_errors"] = read_errors

        if read_errors:
            for e in read_errors:
                result.add_error(e)
            result.set_corrupted(self._text("lesefehler_beschaedigt", anzahl=len(read_errors)))
        elif not result.errors:
            # Nur OK wenn kein Header-Fehler und keine Lesefehler
            result.status = "OK"

        self._log.info(
            f"FFPFS-Validierung abgeschlossen: {result.status} | "
            f"SHA-256: {file_hash[:16]}..."
        )
        return result
