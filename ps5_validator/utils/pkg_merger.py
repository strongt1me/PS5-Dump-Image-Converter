"""Reassembliert geteilte PS5-.pkg-Dateisaetze (Split-Packages) zu einer vollstaendigen Datei.

Manche Distributionswege liefern ein finalisiertes PS5-Paket nicht als einzelne .pkg-Datei,
sondern aufgeteilt in nummerierte Teile (<base>_0.pkg .. <base>_N.pkg) plus einen optionalen
Metadaten-Teil (<base>_sc.pkg). Dieses Modul erkennt solche Saetze in einem Ordner, prueft ihre
strukturelle Konsistenz gegen den FIH-Header des ersten Teils und fuegt sie durch reine
Byte-Konkatenation (aufsteigende Reihenfolge, Metadaten-Teil zuletzt) zu einer vollstaendigen
Datei zusammen. Es werden keine Paketinhalte entschluesselt, geprueft (signiert) oder veraendert.

WICHTIG: Das ist NICHT dasselbe wie das Zusammenfuehren von Basisspiel + Update + DLC in ein
gemeinsames Paket - auf der PS5 sind das grundsaetzlich separate, eigenstaendig installierbare
Pakete. "Merge" bezieht sich hier ausschliesslich auf das Wiederzusammensetzen EINES aus
Distributionsgruenden gesplitteten Pakets.

Byte-Layout und Validierungsregeln durch Gegenlesen des quelloffenen LibProsperoPKG-Mergers
(GPL-3.0-or-later, https://github.com/SvenGDK/LibProsperoPKG) ermittelt; eigenstaendige
Python-Neuentwicklung auf Basis der (nicht schutzfaehigen) Format-Fakten, kein Uebersetzen/
Kopieren des dortigen C#-Quellcodes.
"""
from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass, field
from typing import Callable

from ps5_validator.utils.pkg_reader import (
    CNT_MAGIC,
    FIH_EMBEDDED_CNT_OFFSET_OFFSET,
    FIH_FORMAT_VERSION_OFFSET,
    FIH_MAGIC,
    FIH_PFS_IMAGE_OFFSET_OFFSET,
    FIH_PFS_IMAGE_SIZE_OFFSET,
    FIH_REQUIRED_FORMAT_VERSION,
    FIH_SIGNED_BYTE_OFFSET,
)

META_TOKEN = "sc"
MERGED_SUFFIX = "-merged.pkg"

#: Die Protokollzeilen als Vorlagen - damit der Aufrufer sie uebersetzen kann.
#:
#: Dieses Modul bleibt sprachfrei wie alle unter ``ps5_validator/utils``:
#: keines davon bindet i18n ein. Bis zum 05.09.2026 standen die Saetze hier
#: fest auf Deutsch und liefen an ``self._t()`` vorbei - im Fenster des PKG
#: Mergers mischten sich deutsche Zeilen unter eine englische Oberflaeche.
#: Jetzt reicht der Aufrufer eigene Vorlagen herein; ohne die bleibt es beim
#: bisherigen Wortlaut, damit vorhandene Aufrufer unveraendert laufen.
MELDUNGEN = {
    "kein_muster": "[warn] '{name}' entspricht nicht dem Split-Namensschema; uebersprungen.",
    "unbekanntes_token": "[warn] '{name}' hat ein unbekanntes Teil-Token; uebersprungen.",
    "haengt_an": "[work] fuege '{name}' an...",
    "fertig_einer": "[done] Zusammenfuegen abgeschlossen.",
    "kein_wurzelteil": "[warn] kein Wurzelteil (_0) fuer '{name}'; uebersprungen.",
    "fuehrt_zusammen": "[work] fuehre '{name}' zusammen ({teile})...",
    "teile_mit_meta": "{anzahl} nummerierte(s) Teil(e) + Metadaten-Teil",
    "teile_ohne_meta": "{anzahl} nummerierte(s) Teil(e), ohne Metadaten-Teil",
    "fertig_alle": "[done] Alle Split-Sets verarbeitet.",
    # Diese beiden landen nicht im Protokoll, sondern in einem Dialog
    # bzw. in der Fehlerliste des Fensters - und standen deshalb bis zum
    # 06.09.2026 fest deutsch vor einer englischen Oberflaeche.
    "kein_ordner": "'{pfad}' ist kein Ordner.",
    "kein_fih_kopf": "Wurzelteil beginnt nicht mit dem finalisierten FIH-Header.",
    # Ein unlesbares Wurzelteil ist etwas anderes als ein falscher Kopf.
    # Bis v1.9.10 lieferte _read_head bei jedem OSError b"" zurueck, und die
    # Pruefung meldete "beginnt nicht mit dem FIH-Header" - bei einer
    # abgezogenen Platte oder fehlenden Rechten also die falsche Ursache.
    "wurzelteil_unlesbar": "Wurzelteil '{pfad}' laesst sich nicht lesen: {fehler}",
    # Diese beiden standen als f-Zeichenkette fest deutsch im Quelltext.
    "unerwartetes_signed_byte": "Unerwartetes signed byte 0x{wert} im FIH-Header.",
    "unerwartete_formatversion": "Unerwartete Formatversion {version}.",
    "kein_subcontainer_kopf": "Metadaten-Teil beginnt nicht mit dem Subcontainer-Header.",
    # Die uebrigen Pruefgruende standen bis zur Durchsicht (Runde 16,
    # 25.09.2026) als f-Zeichenketten fest im Quelltext und kamen ueber die
    # Fehlerliste im Fenster deutsch vor einer englischen Oberflaeche an.
    "wurzelteil_fehlt": "Mindestens das Wurzelteil (_0) wird benoetigt.",
    "cnt_versatz": "Eingebetteter Subcontainer-Offset {cnt} entspricht nicht Image-Offset+Groesse {soll}.",
    "teil_fehlt": "Teil fehlt: '{pfad}'.",
    "summe_passt_nicht": ("Summe der nummerierten Teile ({summe}) entspricht nicht dem "
                          "eingebetteten Subcontainer-Offset ({cnt})."),
    "meta_fehlt": "Metadaten-Teil fehlt: '{pfad}'.",
    "validierung_fehlgeschlagen": "Split-Set-Validierung fehlgeschlagen: {fehler}",
    # Abbruch durch den Aufrufer (Durchsicht, Runde 19, U1-5). Die .tmp ist
    # dann schon entfernt - im Zielordner liegt nichts Halbes.
    "abgebrochen": "[stop] Zusammenfuegen abgebrochen - '{name}' wurde nicht geschrieben.",
}


def _melde(log, texte, kennung: str, /, **werte) -> None:
    """Schickt eine Meldung ans Protokoll - uebersetzt, wenn moeglich."""
    if not log:
        return
    vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
    log(vorlage.format(**werte))


def _text(texte, kennung: str, /, **werte) -> str:
    """Eine Vorlage, uebersetzt wenn moeglich - fuer Texte ohne Protokoll."""
    vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
    return vorlage.format(**werte)


def _teiletext(anzahl: int, mit_meta: bool, texte) -> str:
    """Die Klammer hinter dem Satznamen: wie viele Teile, mit Metadaten?"""
    kennung = "teile_mit_meta" if mit_meta else "teile_ohne_meta"
    vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
    return vorlage.format(anzahl=anzahl)
_HEAD_READ_SIZE = 0x60
_COPY_CHUNK_SIZE = 1024 * 1024

LogFn = Callable[[str], None]


class PkgMergeError(Exception):
    """Wird ausgeloest, wenn ein Split-Set die strukturelle Validierung nicht besteht."""


class MergeAbgebrochen(PkgMergeError):
    """Der Aufrufer hat abgebrochen; die angefangene ``.tmp`` ist schon entfernt."""


@dataclass
class SplitSet:
    base_name: str
    numbered: dict[int, str] = field(default_factory=dict)
    meta: str | None = None

    @property
    def ordered_numbered(self) -> list[str]:
        return [self.numbered[key] for key in sorted(self.numbered)]

    @property
    def has_root(self) -> bool:
        return 0 in self.numbered


@dataclass
class MergeValidation:
    is_valid: bool
    package_type: str  # "full_retail" | "full_debug"
    format_version: int
    pfs_image_offset: int
    pfs_image_size: int
    embedded_cnt_offset: int
    numbered_size: int
    meta_size: int
    errors: list[str]


@dataclass
class MergeResult:
    output_path: str
    base_name: str
    numbered_pieces: list[str]
    meta_piece: str | None
    total_size: int
    package_type: str
    sha256: str | None = None


def _try_parse_name(file_name: str) -> tuple[str, str] | None:
    """Zerlegt einen Dateinamen in Basisname (vor dem letzten '_') und Teil-Token.

    Das Token endet an der Dateiendung, nicht am ersten Punkt des Namens: Sonst
    fallen alle Basisnamen durch, die selbst einen Punkt enthalten - etwa die
    Versionsklammer ``Spiel (01.003.000)_0.pkg`` oder ``Game.v1.00_0.pkg``.
    Solche Saetze galten als "entspricht nicht dem Split-Namensschema" und
    wurden stillschweigend uebersprungen.
    """
    stem = os.path.splitext(file_name)[0]
    last_underscore = stem.rfind("_")
    if last_underscore < 0:
        return None
    token = stem[last_underscore + 1:]
    if not token:
        return None
    return stem[:last_underscore], token


def _teilnummer(token: str) -> int | None:
    """Die Teilnummer - nur, wenn das Token aus lauter Ziffern besteht.

    Bis zum 17.09.2026 genuegte ein fuehrender Zahlenteil
    (``_try_parse_leading_int``). Ein ungeteiltes Paket heisst aber meist
    nach seiner Content-ID, ``EP4350-PPSA05399_00-TETRIS0000000000.pkg``:
    Hinter dem letzten "_" steht "00-TETRIS...", und daraus wurde Teil 0 -
    ein Scheinsatz, in dem sich Spiel und Update derselben Title-ID
    gegenseitig ueberschrieben. LibProsperoPkg nennt als Kennung den Text
    zwischen "_" und ".", und fuer nummerierte Teile ist das eine Zahl.
    """
    if token.isascii() and token.isdigit():
        return int(token)
    return None


def discover_split_sets(input_dir: str, log: LogFn | None = None,
                        texte: dict | None = None) -> list[SplitSet]:
    """Gruppiert alle `.pkg`-Dateien in `input_dir` nach dem Split-Namensschema."""
    if not os.path.isdir(input_dir):
        raise NotADirectoryError(_text(texte, "kein_ordner", pfad=input_dir))

    sets: dict[str, SplitSet] = {}
    for entry in sorted(os.listdir(input_dir)):
        full = os.path.join(input_dir, entry)
        if not os.path.isfile(full):
            continue
        if os.path.splitext(entry)[1].lower() != ".pkg":
            continue
        if MERGED_SUFFIX in entry:
            continue

        parsed = _try_parse_name(entry)
        if parsed is None:
            _melde(log, texte, "kein_muster", name=entry)
            continue
        base_name, token = parsed

        ist_meta = token.lower() == META_TOKEN
        number = None if ist_meta else _teilnummer(token)
        if not ist_meta and number is None:
            # Erst pruefen, dann den Satz anlegen: Sonst stand fuer "My_Game.pkg"
            # ein leerer Satz "My" in der Liste statt "keine Saetze gefunden".
            _melde(log, texte, "unbekanntes_token", name=entry)
            continue
        split_set = sets.setdefault(base_name, SplitSet(base_name=base_name))
        if ist_meta:
            split_set.meta = full
            continue
        split_set.numbered[number] = full

    return list(sets.values())


def _read_head(path: str, length: int) -> "tuple[bytes, str]":
    """Liest den Dateikopf. Rueckgabe: (Daten, Fehlertext).

    Der Fehlertext ist leer, wenn gelesen werden konnte. Vorher gab es bei
    jedem ``OSError`` nur ``b""``, und der Aufrufer konnte "Datei nicht
    lesbar" nicht von "falscher Kopf" unterscheiden.
    """
    try:
        with open(path, "rb") as f:
            return f.read(length), ""
    except OSError as exc:
        return b"", str(exc)


def validate_split_set(numbered_pieces: list[str], meta_piece: str | None,
                       texte: dict | None = None) -> MergeValidation:
    """Prüft einen Split-Satz gegen das finalisierte FIH-Layout, ohne etwas zu schreiben."""
    if not numbered_pieces:
        raise ValueError(_text(texte, "wurzelteil_fehlt"))

    errors: list[str] = []
    head, lesefehler = _read_head(numbered_pieces[0], _HEAD_READ_SIZE)

    package_type = "full_retail"
    format_version = 0
    pfs_offset = pfs_size = cnt_offset = 0

    if lesefehler:
        errors.append(_text(texte, "wurzelteil_unlesbar",
                            pfad=numbered_pieces[0], fehler=lesefehler))
    elif len(head) < _HEAD_READ_SIZE or head[:4] != FIH_MAGIC:
        errors.append(_text(texte, "kein_fih_kopf"))
    else:
        signed_byte = head[FIH_SIGNED_BYTE_OFFSET]
        if signed_byte == 0x80:
            package_type = "full_retail"
        elif signed_byte == 0x00:
            package_type = "full_debug"
        else:
            errors.append(_text(texte, "unerwartetes_signed_byte",
                                wert="%02X" % signed_byte))

        format_version = struct.unpack_from("<H", head, FIH_FORMAT_VERSION_OFFSET)[0]
        if format_version != FIH_REQUIRED_FORMAT_VERSION:
            errors.append(_text(texte, "unerwartete_formatversion",
                                version=format_version))

        pfs_offset = struct.unpack_from("<Q", head, FIH_PFS_IMAGE_OFFSET_OFFSET)[0]
        pfs_size = struct.unpack_from("<Q", head, FIH_PFS_IMAGE_SIZE_OFFSET)[0]
        cnt_offset = struct.unpack_from("<Q", head, FIH_EMBEDDED_CNT_OFFSET_OFFSET)[0]

        if cnt_offset != pfs_offset + pfs_size:
            errors.append(_text(texte, "cnt_versatz", cnt=cnt_offset,
                                soll=pfs_offset + pfs_size))

    numbered_size = 0
    for piece in numbered_pieces:
        if not os.path.isfile(piece):
            errors.append(_text(texte, "teil_fehlt", pfad=piece))
        else:
            numbered_size += os.path.getsize(piece)

    if not errors and cnt_offset != numbered_size:
        errors.append(_text(texte, "summe_passt_nicht", summe=numbered_size,
                            cnt=cnt_offset))

    meta_size = 0
    if meta_piece is not None:
        if not os.path.isfile(meta_piece):
            errors.append(_text(texte, "meta_fehlt", pfad=meta_piece))
        else:
            meta_size = os.path.getsize(meta_piece)
            meta_head, meta_lesefehler = _read_head(meta_piece, 4)
            if meta_lesefehler:
                errors.append(_text(texte, "wurzelteil_unlesbar",
                                    pfad=meta_piece, fehler=meta_lesefehler))
            elif len(meta_head) < 4 or meta_head[:4] != CNT_MAGIC:
                errors.append(_text(texte, "kein_subcontainer_kopf"))

    return MergeValidation(
        is_valid=not errors,
        package_type=package_type,
        format_version=format_version,
        pfs_image_offset=pfs_offset,
        pfs_image_size=pfs_size,
        embedded_cnt_offset=cnt_offset,
        numbered_size=numbered_size,
        meta_size=meta_size,
        errors=errors,
    )


def _base_name_of(path: str) -> str:
    file_name = os.path.basename(path)
    parsed = _try_parse_name(file_name)
    return parsed[0] if parsed is not None else os.path.splitext(file_name)[0]


def merge_split_set(
    numbered_pieces: list[str],
    meta_piece: str | None,
    output_path: str,
    compute_digest: bool = False,
    log: LogFn | None = None,
    texte: dict | None = None,
    abbruch: Callable[[], bool] | None = None,
) -> MergeResult:
    """Fügt einen validierten Split-Satz per Byte-Konkatenation zu `output_path` zusammen.

    ``abbruch`` wird vor jedem Block (1 MiB) gefragt. Bis zur Durchsicht
    (Runde 19, U1-5) gab es ihn nicht: Ein Satz von 50-100 GB liess sich
    nicht anhalten, das Fenster verweigerte das Schliessen, und damit blieb
    auch das Programm offen - nur ein Beenden des Prozesses half, und dann
    blieb die ``.tmp`` im Zielordner liegen.

    Raises:
        PkgMergeError: Der Satz besteht die strukturelle Validierung nicht.
        MergeAbgebrochen: ``abbruch`` hat True geliefert; die ``.tmp`` ist
            entfernt.
    """
    if not numbered_pieces:
        raise ValueError(_text(texte, "wurzelteil_fehlt"))

    validation = validate_split_set(numbered_pieces, meta_piece, texte)
    if not validation.is_valid:
        raise PkgMergeError(_text(texte, "validierung_fehlgeschlagen",
                                  fehler="; ".join(validation.errors)))

    ordered = list(numbered_pieces)
    if meta_piece is not None:
        ordered.append(meta_piece)

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    sha = hashlib.sha256() if compute_digest else None
    total = 0
    tmp_path = output_path + ".tmp"
    try:
        with open(tmp_path, "wb") as out_f:
            for piece in ordered:
                _melde(log, texte, "haengt_an", name=os.path.basename(piece))
                with open(piece, "rb") as in_f:
                    while True:
                        if abbruch is not None and abbruch():
                            raise MergeAbgebrochen(_text(
                                texte, "abgebrochen",
                                name=_base_name_of(numbered_pieces[0])))
                        chunk = in_f.read(_COPY_CHUNK_SIZE)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        if sha is not None:
                            sha.update(chunk)
                        total += len(chunk)
        os.replace(tmp_path, output_path)
    except Exception:
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise

    _melde(log, texte, "fertig_einer")

    return MergeResult(
        output_path=output_path,
        base_name=_base_name_of(numbered_pieces[0]),
        numbered_pieces=list(numbered_pieces),
        meta_piece=meta_piece,
        total_size=total,
        package_type=validation.package_type,
        sha256=sha.hexdigest() if sha is not None else None,
    )


def merge_directory(
    input_dir: str,
    output_dir: str | None = None,
    compute_digest: bool = False,
    log: LogFn | None = None,
    texte: dict | None = None,
    abbruch: Callable[[], bool] | None = None,
) -> list[MergeResult]:
    """Findet und führt alle vollständigen Split-Sets in `input_dir` zusammen.

    Sets ohne Wurzelteil (`_0`) werden übersprungen und protokolliert.
    ``abbruch`` siehe :func:`merge_split_set`.
    """
    output_dir = output_dir or input_dir
    os.makedirs(output_dir, exist_ok=True)

    results: list[MergeResult] = []
    for split_set in discover_split_sets(input_dir, log, texte):
        if not split_set.has_root:
            _melde(log, texte, "kein_wurzelteil", name=split_set.base_name)
            continue
        output_path = os.path.join(output_dir, split_set.base_name + MERGED_SUFFIX)
        _melde(log, texte, "fuehrt_zusammen", name=split_set.base_name,
               teile=_teiletext(len(split_set.numbered),
                                split_set.meta is not None, texte))
        results.append(
            merge_split_set(split_set.ordered_numbered, split_set.meta, output_path,
                            compute_digest, log, texte, abbruch=abbruch)
        )

    _melde(log, texte, "fertig_alle")
    return results
