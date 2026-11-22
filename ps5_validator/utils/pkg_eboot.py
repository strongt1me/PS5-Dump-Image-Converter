# -*- coding: utf-8 -*-
"""Das SDK der ``eboot.bin`` in einem PS5-Paket (``.pkg``) - gelesen, ohne das Paket zu entpacken.

Warum das Programm das selbst liest: Die Rueckfrage "BACKPORT noetig?" urteilt nach dem SDK der Programme (:mod:`programm_sdk`), nicht
nach der ``param.json``. Dump Forges ``inspect`` nennt das SDK der Programme nur bei einem Spiel mit ``fakelib/``; ein Paket, das ein
schon herabgesetztes Spiel ohne ``fakelib/`` traegt, blieb deshalb "nicht zu sagen" und wurde nach der ``param.json`` beurteilt.

Der Leseweg ist der von Dump Forge (``crates/ps5-dump-forge-fpkg``, GPL-3.0-or-later, wie dieses Programm; der Kraken-Teil folgt
``vendor/ps5upload-fpkg``), nach Python uebertragen und auf das Noetige beschnitten - eine Datei, ein paar KiB:

1. ``\\x7fFIH``-Kopf und ``\\x7fCNT``-Behaelter: wo das aeussere Abbild liegt, die Pruefsummen (``imagedigs``) und die Inhalts-Kennung.
2. Das aeussere PFS (``pfs_image.dat``, ``naps_pkg_layout.dat``): 64-KiB-Bloecke, bei einem Paket mit AES-128-XTS verschluesselt
   (Schluessel aus Inhalts-Kennung und Passcode, Vorgabe ``00000000000000000000000000000000``), jeder Block gegen seine SHA3-256 geprueft.
3. Das innere Abbild: in Bloecken zu 256 KiB mit Kraken verdichtet. Die Beschreibung (``naps_pkg_layout.dat``) sagt, wo jeder Block
   liegt; gelesen und entpackt werden nur die Bloecke, die ein Bereich beruehrt.
4. Das innere Dateisystem: Oberblock an der Metadatenbasis, Inode-Tabelle, ein Verzeichnisstrom je Ordner; die Dateien liegen am Stueck
   an ihrer logischen Stelle. Von der ``eboot.bin`` werden nur die ersten KiB gebraucht.

Gelesen wird nur ein Debug-Paket (``.pkg`` aus Forge oder anderen Bauwerkzeugen mit dem Vorgabe-Passcode) mit Kraken-Bloecken. Alles
andere - Verkaufsfassung, fremder Passcode, Update-Paket (``\\x7fLIH``), flaches Abbild, ein Kraken-Verfahren, das Forge selbst nicht
liest, ein beschaedigtes Paket - ergibt ``""`` ("nicht zu sagen"), nie eine Vermutung. Es wird nichts veraendert.

Das Modul kennt keine Oberflaeche.
"""
from __future__ import annotations

import bisect
import hashlib
import hmac
import logging
import struct
from typing import Any

from . import programm_sdk

logger = logging.getLogger(__name__)

BLOCK = 0x10000
#: Der Passcode, mit dem Debug-Pakete ohne eigene Wahl gebaut werden.
STANDARD_PASSCODE = "0" * 32
_KLARTEXT_MARKE = b"PPRPLAIN-NOAUTH!"
_SIGNIERT = 1 << 47
_FIH_LEN = 0x100
_CNT_KOPF = 0x1000
_CNT_MAGIC = 0x7F434E54
_CNT_EINTRAG = 0x20
_MAX_EINTRAEGE = 4096
_ID_BILDPRUEFSUMMEN = 0x040A
_OBERBLOCK_MAGIC = 20130315
_DINODE_LEN = 0x2C8
_DIREKT_AB = 0x64
_INDIREKT_AB = _DIREKT_AB + 12 * 36
_PRO_TABELLE = BLOCK // 36
_INODE_LEN = 0xA8
_INODES_JE_BLOCK = 390
_ERSTER_ORDNER = 4
_EINTRAG_DATEI = 2
_EINTRAG_ORDNER = 3
_EINTRAG_PUNKT = 4
_EINTRAG_PUNKTPUNKT = 5
#: So viel von der Beschreibung (``naps_pkg_layout.dat``) wird gelesen: die groessten bekannten Titel haben 10-34 MB (Spider-Man 2: 10 MB,
#: Final Fantasy VII Rebirth: 34 MB). Gemessen: 450.835 Bloecke (LEGO Batman) brauchen ~150 MB, die Spitze liegt bei ~175 MB; 48 MiB halten
#: die Spitze unter etwa 1 GB.
_MAX_BESCHREIBUNG = 48 << 20
#: Leerbereiche (Dateien ohne gespeicherte Daten, Art 0x40) in der Beschreibung: echte Pakete haben eine Handvoll (LEGO Batman: 1 von 176
#: Eintraegen). Jeder wird zu eigenen Bloecken - die Grenze haelt eine gebaute Beschreibung mit Millionen davon fern.
_MAX_LEERBEREICHE = 100_000
#: ... und hoechstens so viele Bloecke daraus (256 KiB je Block: 64 GiB ohne gespeicherte Daten).
_MAX_LEERBLOECKE = 262_144
_AUSSEN_ZWISCHENSPEICHER = 48
_ENTPACKT_ZWISCHENSPEICHER = 6

_HALB = 0x20000
_UBLOCK = 0x40000
_FENSTER = 0x40000
_MIN_ABSTAND = 8
_SAAT = 8
_HUFF_MAX = 11
_HUFF_LUT = 1 << _HUFF_MAX

#: Die 13 Byte-Mischungen von PFS v3 (Feldgroessen eines 8- oder 16-Byte-Vektors); 0 = keine.
_MISCHUNGEN: "tuple[tuple[int, ...], ...]" = (
    (), (4, 4), (2, 2, 4), (1, 1, 6), (1, 1, 1, 1, 1, 1, 1, 1), (8, 2, 2, 4), (1, 1, 6, 2, 2, 4), (1, 1, 6, 1, 1, 6),
    (4, 4, 4, 4), (8, 8), (8, 4, 4), (2, 6), (2, 6, 2, 6),
)
_MISCHUNG_EINHEIT = 0x10000


class PaketFehler(ValueError):
    """Das Paket laesst sich so nicht lesen. ``art``: ``"kein-ps5"``, ``"verkauf"``, ``"update"``, ``"passcode"``, ``"verfahren"``, ``"beschaedigt"``."""

    def __init__(self, art: str, text: str) -> None:
        super().__init__("%s: %s" % (art, text))
        self.art = art


def _le16(b: bytes, ab: int) -> int:
    return struct.unpack_from("<H", b, ab)[0]


def _le32(b: bytes, ab: int) -> int:
    return struct.unpack_from("<I", b, ab)[0]


def _le64(b: bytes, ab: int) -> int:
    return struct.unpack_from("<Q", b, ab)[0]


def _be32(b: bytes, ab: int) -> int:
    return struct.unpack_from(">I", b, ab)[0]


def _sha3(daten: bytes) -> bytes:
    return hashlib.sha3_256(daten).digest()


def _beschaedigt(text: str) -> PaketFehler:
    return PaketFehler("beschaedigt", text)


# --------------------------------------------------------------------------------------------------------------- Schluessel, XTS

def _hmac(schluessel: bytes, *teile: bytes) -> bytes:
    h = hmac.new(schluessel, digestmod=hashlib.sha256)
    for teil in teile:
        h.update(teil)
    return h.digest()


def schluessel_ableiten(inhalts_id: str, passcode: str, saat: bytes) -> bytes:
    """Die 32 Byte AES-128-XTS-Schluessel (Daten-, dann Tweak-Schluessel) eines Abbilds - ``derive_ekpfs`` und ``derive_xts_keys`` von Forge."""
    kennung = inhalts_id.encode("utf-8")[:48].ljust(48, b"\0")
    ekpfs = _sha3(_sha3(struct.pack(">I", 1)) + _sha3(kennung) + passcode.encode("utf-8"))
    k = _hmac(ekpfs, saat)
    enc = _hmac(k, struct.pack("<I", 1), saat)
    return enc[16:] + enc[:16]                          # Forge: tweak = enc[:16], data = enc[16:]; hier Daten zuerst, wie ``modes.XTS`` es erwartet


def _xts_entschluesseln(schluessel: bytes, sektor: int, daten: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    tweak = struct.pack("<Q", sektor) + bytes(8)
    d = Cipher(algorithms.AES(schluessel), modes.XTS(tweak)).decryptor()
    return d.update(daten) + d.finalize()


# ------------------------------------------------------------------------------------------------------------- Paket, Kopf, Behaelter

class _Paket:
    """Die Paketdatei, jeder Lesevorgang vorher gegen die Laenge geprueft."""

    def __init__(self, fh: Any) -> None:
        self.fh = fh
        fh.seek(0, 2)
        self.laenge = fh.tell()

    def lesen(self, ab: int, n: int) -> bytes:
        if ab < 0 or n < 0 or ab + n > self.laenge:
            raise _beschaedigt("ein Lesevorgang von %d Bytes bei %#x geht ueber das Paketende %#x (abgeschnitten?)" % (n, ab, self.laenge))
        self.fh.seek(ab)
        daten = self.fh.read(n)
        if len(daten) != n:
            raise _beschaedigt("das Paket liefert weniger Bytes als verlangt")
        return daten


class _Kopf:
    __slots__ = ("pfs_ab", "aussen_bloecke", "ober_index", "spiel_pruefsumme", "cnt_ab", "meta_basis", "format")


def _kopf_lesen(paket: _Paket) -> _Kopf:
    if paket.laenge < _FIH_LEN:
        raise PaketFehler("kein-ps5", "%d Bytes, kuerzer als ein Paketkopf" % paket.laenge)
    kopf = paket.lesen(0, _FIH_LEN)
    magie = kopf[:4]
    if magie == b"\x7fCNT":
        raise PaketFehler("kein-ps5", "ein PS4-Paket")
    if magie == b"\x7fLIH":
        raise PaketFehler("update", "ein Update-Paket (LIH)")
    if magie != b"\x7fFIH":
        raise PaketFehler("kein-ps5", "keine \\x7fFIH-Kennung am Anfang")
    if kopf[5] != 0:
        raise PaketFehler("verkauf", "das Signaturbyte ist %#04x (Debug-Pakete tragen 0x00)" % kopf[5])
    pfs_ab, pfs_groesse = _le64(kopf, 0x10), _le64(kopf, 0x18)
    if pfs_ab < _FIH_LEN or pfs_ab % BLOCK:
        raise _beschaedigt("Anfang des aeusseren Abbilds %#x" % pfs_ab)
    if pfs_groesse == 0 or pfs_groesse % BLOCK:
        raise _beschaedigt("Groesse des aeusseren Abbilds %#x ist keine ganze Zahl Bloecke" % pfs_groesse)
    if pfs_ab + pfs_groesse > paket.laenge:
        raise _beschaedigt("das aeussere Abbild geht ueber das Paketende (abgeschnitten?)")
    bloecke = pfs_groesse // BLOCK
    oberblock_abs = _le64(kopf, 0x20)
    rel = oberblock_abs - pfs_ab
    if rel < 0 or rel % BLOCK or rel // BLOCK >= bloecke:
        raise _beschaedigt("der Oberblock %#x liegt ausserhalb des aeusseren Abbilds" % oberblock_abs)
    cnt_ab = _le64(kopf, 0x58)
    if cnt_ab + _CNT_KOPF > paket.laenge:
        raise _beschaedigt("der Behaelter %#x liegt hinter dem Paketende" % cnt_ab)
    if _le64(kopf, 0x60) != BLOCK:
        raise _beschaedigt("Blockgroesse im Kopf %#x" % _le64(kopf, 0x60))
    k = _Kopf()
    k.pfs_ab, k.aussen_bloecke, k.ober_index = pfs_ab, bloecke, rel // BLOCK
    k.spiel_pruefsumme = bytes(kopf[0x30:0x50])
    k.cnt_ab = cnt_ab
    k.meta_basis = _le32(kopf, 0x50) * BLOCK
    k.format = _le16(kopf, 6)
    return k


class _Behaelter:
    __slots__ = ("inhalts_id", "eintraege")

    def eintrag(self, nummer: int) -> "tuple[int, int] | None":
        """``(Anfang im Paket, Groesse)`` des Eintrags ``nummer``."""
        for n, ab, groesse in self.eintraege:
            if n == nummer:
                return ab, groesse
        return None


def _behaelter_lesen(paket: _Paket, cnt_ab: int) -> _Behaelter:
    kopf = paket.lesen(cnt_ab, _CNT_KOPF)
    if _be32(kopf, 0) != _CNT_MAGIC:
        raise _beschaedigt("kein \\x7fCNT-Behaelter bei %#x" % cnt_ab)
    anzahl = _be32(kopf, 0x10)
    if anzahl > _MAX_EINTRAEGE:
        raise _beschaedigt("der Behaelter meldet %d Eintraege (hoechstens %d)" % (anzahl, _MAX_EINTRAEGE))
    tabelle = cnt_ab + _be32(kopf, 0x18)
    zeilen = paket.lesen(tabelle, anzahl * _CNT_EINTRAG)
    b = _Behaelter()
    b.eintraege = []
    for i in range(anzahl):
        z = zeilen[i * _CNT_EINTRAG:(i + 1) * _CNT_EINTRAG]
        ab, groesse = cnt_ab + _be32(z, 16), _be32(z, 20)
        if ab + groesse > paket.laenge:
            raise _beschaedigt("ein Behaelter-Eintrag geht ueber das Paketende")
        b.eintraege.append((_be32(z, 0), ab, groesse))
    b.inhalts_id = bytes(kopf[0x40:0x64]).split(b"\0", 1)[0].decode("utf-8", "replace")
    return b


# --------------------------------------------------------------------------------------------------------------- aeusseres Abbild

class _Dinode:
    __slots__ = ("groesse", "direkt", "indirekt")

    def __init__(self, tabelle: bytes, ab: int) -> None:
        self.groesse = _le64(tabelle, ab + 8)
        self.direkt = [self._sig(tabelle, ab + _DIREKT_AB + k * 36) for k in range(12)]
        self.indirekt = [self._sig(tabelle, ab + _INDIREKT_AB + k * 36) for k in range(5)]

    @staticmethod
    def _sig(tabelle: bytes, ab: int) -> "tuple[bytes, int]":
        return bytes(tabelle[ab:ab + 32]), _le32(tabelle, ab + 32)


def _dinodes(tabelle: bytes, anzahl: int) -> "list[_Dinode]":
    # Die Zahl kommt aus dem Oberblock (u64): gezaehlt wird nur, was in der Tabelle Platz hat - nicht bis 2**64 (ein gebautes Paket
    # mit stimmigen Pruefsummen kaeme an Forges ``inspect`` vorbei, das selbst mit ``take_while`` zaehlt).
    return [_Dinode(tabelle, j * _DINODE_LEN) for j in range(min(max(0, anzahl), len(tabelle) // _DINODE_LEN))]


def _aussen_verzeichnis(block: bytes, groesse: int) -> "list[tuple[int, int, str]]":
    """Die Eintraege eines Verzeichnisses des aeusseren PFS: ``(Inode, Art, Name)``."""
    grenze = min(groesse, len(block))
    aus, o = [], 0
    while o + 16 <= grenze:
        namenlaenge, eintraglaenge = _le32(block, o + 8), _le32(block, o + 12)
        if eintraglaenge == 0 or o + 16 + namenlaenge > grenze:
            break
        aus.append((_le32(block, o), struct.unpack_from("<i", block, o + 4)[0], block[o + 16:o + 16 + namenlaenge].decode("utf-8", "replace")))
        o += eintraglaenge
    return aus


class _Aussen:
    """Das aeussere Abbild als Bloecke zu 64 KiB: gelesen, bei einem verschluesselten Paket entschluesselt, gegen ``imagedigs`` geprueft."""

    def __init__(self, paket: _Paket, kopf: _Kopf, pruefsummen_ab: int) -> None:
        self.paket, self.kopf, self.pruefsummen_ab = paket, kopf, pruefsummen_ab
        self.bloecke = kopf.aussen_bloecke
        self.schluessel: "bytes | None" = None
        self._zwischen: "dict[int, bytes]" = {}

    def schluessel_setzen(self, schluessel: "bytes | None") -> None:
        self.schluessel = schluessel
        self._zwischen.clear()

    def laden(self, index: int) -> "bytes | None":
        """Block ``index`` als Klartext; ``None``, wenn keine Lesart zu seiner Pruefsumme passt (falscher Schluessel oder beschaedigt)."""
        if index >= self.bloecke:
            raise _beschaedigt("der Aussenblock %d liegt hinter den %d Bloecken des Abbilds" % (index, self.bloecke))
        roh = self.paket.lesen(self.kopf.pfs_ab + index * BLOCK, BLOCK)
        soll = bytes(reversed(self.paket.lesen(self.pruefsummen_ab + index * 32, 32)))
        if self.schluessel is None or index == self.kopf.ober_index:
            return roh if _sha3(roh) == soll else None
        erst, zweit = (index, _SIGNIERT | index) if index < self.kopf.ober_index else (_SIGNIERT | index, index)
        for sektor in (erst, zweit):
            klar = _xts_entschluesseln(self.schluessel, sektor, roh)
            if _sha3(klar) == soll:
                return klar
        return None

    def block(self, index: int) -> bytes:
        gefunden = self._zwischen.get(index)
        if gefunden is not None:
            return gefunden
        klar = self.laden(index)
        if klar is None:
            raise _beschaedigt("der Aussenblock %d passt nicht zu seinem imagedigs-Eintrag" % index)
        if len(self._zwischen) >= _AUSSEN_ZWISCHENSPEICHER:
            del self._zwischen[next(iter(self._zwischen))]
        self._zwischen[index] = klar
        return klar


class _AussenDatei:
    """Eine Datei des aeusseren PFS (``pfs_image.dat``, ``naps_pkg_layout.dat``). Die Bloecke werden erst beim Lesen aufgeloest."""

    def __init__(self, aussen: _Aussen, dinode: _Dinode, name: str) -> None:
        self.aussen, self.dinode, self.name = aussen, dinode, name
        self.groesse = dinode.groesse
        self.noetig = -(-self.groesse // BLOCK)
        self._geprueft: "set[int]" = set()
        if self.noetig > aussen.bloecke:
            raise _beschaedigt("%s meldet %d Bytes, mehr als das aeussere Abbild hat" % (name, self.groesse))

    def blocknummer(self, k: int) -> int:
        """Die Nummer des Aussenblocks hinter dem ``k``-ten Block der Datei."""
        if k < 12:
            return self._pruefen(self.dinode.direkt[k][1])
        j = k - 12
        for stufe in range(5):
            umfang = _PRO_TABELLE ** (stufe + 1)
            if j < umfang:
                digest, block = self.dinode.indirekt[stufe]
                if block == 0:
                    raise _beschaedigt("%s: die Blocktabelle der Stufe %d fehlt" % (self.name, stufe))
                return self._abstieg(stufe, block, digest, j)
            j -= umfang
        raise _beschaedigt("%s: Block %d liegt hinter allen Blocktabellen" % (self.name, k))

    def _abstieg(self, stufe: int, block: int, digest: bytes, j: int) -> int:
        self._pruefen(block)
        tabelle = self.aussen.block(block)
        if block not in self._geprueft:
            if _sha3(tabelle) != digest:
                raise _beschaedigt("%s: die Blocktabelle bei Block %d passt nicht zu ihrem Eintrag" % (self.name, block))
            self._geprueft.add(block)
        teil = _PRO_TABELLE ** stufe
        platz, rest = divmod(j, teil)
        ab = platz * 36
        kind = _le32(tabelle, ab + 32)
        if kind == 0:
            raise _beschaedigt("%s: die Blocktabelle bei Block %d endet zu frueh" % (self.name, block))
        if stufe == 0:
            return self._pruefen(kind)
        return self._abstieg(stufe - 1, kind, bytes(tabelle[ab:ab + 32]), rest)

    def _pruefen(self, block: int) -> int:
        if block >= self.aussen.bloecke:
            raise _beschaedigt("%s zeigt auf den Aussenblock %d, hinter das Abbild" % (self.name, block))
        return block

    def lesen(self, ab: int, n: int) -> bytes:
        if ab < 0 or n < 0 or ab + n > self.groesse:
            raise _beschaedigt("ein Lesevorgang von %d Bytes bei %#x geht ueber die %#x Bytes von %s" % (n, ab, self.groesse, self.name))
        aus = bytearray()
        k = ab // BLOCK
        innen = ab % BLOCK
        while len(aus) < n:
            block = self.aussen.block(self.blocknummer(k))
            nimm = min(BLOCK - innen, n - len(aus))
            aus += block[innen:innen + nimm]
            innen = 0
            k += 1
        return bytes(aus)


# ---------------------------------------------------------------------------------------------------------------------------- Kraken

class _BitLeser:
    """Bits MSB zuerst aus ``q[start:ende]``, vorwaerts oder rueckwaerts (``kraken.rs BitReader``)."""

    __slots__ = ("q", "pos", "ende", "rueck", "bits", "bitpos")

    def __init__(self, q: bytes, start: int, ende: int, rueck: bool) -> None:
        self.q = q
        self.pos = ende if rueck else start
        self.ende = start if rueck else ende
        self.rueck = rueck
        self.bits = 0
        self.bitpos = 24
        self._auffuellen()

    def _auffuellen(self) -> None:
        q = self.q
        while self.bitpos > 0:
            if self.rueck:
                self.pos -= 1
                byte = q[self.pos] if self.pos >= self.ende else 0
            else:
                byte = q[self.pos] if self.pos < self.ende else 0
                self.pos += 1
            self.bits |= byte << self.bitpos
            self.bitpos -= 8

    def holen(self, n: int) -> int:
        if n == 0:
            return 0
        v, links = 0, n
        while links > 0:
            nimm = links if links < 24 else 24
            r = self.bits >> (32 - nimm)
            self.bits = (self.bits << nimm) & 0xFFFFFFFF
            self.bitpos += nimm
            self._auffuellen()
            v = (v << nimm) | r
            links -= nimm
        return v

    def nullen(self) -> int:
        return 32 - self.bits.bit_length()

    def laenge_holen(self) -> int:
        nullen = self.nullen()
        if nullen > 12:
            raise PaketFehler("verfahren", "kraken: ungueltige Laengenkennung")
        self.holen(nullen)
        return self.holen(nullen + 7) - 64

    def naht(self) -> int:
        ausstehend = (24 - self.bitpos) >> 3
        return self.pos + ausstehend if self.rueck else self.pos - ausstehend


def _verfahren(text: str) -> PaketFehler:
    return PaketFehler("verfahren", "kraken: " + text)


def _gamma(r: _BitLeser) -> int:
    nullen = r.nullen()
    if nullen > 7:
        raise _verfahren("ungueltiger Lauf in der Huffman-Tabelle")
    return r.holen(2 * (nullen + 1)) - 1


_REV11: "list[int] | None" = None


def _rev11() -> "list[int]":
    global _REV11
    if _REV11 is None:
        _REV11 = [int(format(i, "011b")[::-1], 2) for i in range(_HUFF_LUT)]
    return _REV11


def _lsb_strom(q: bytes, start: int, ende: int, rueck: bool, anzahl: int, lut_symbol: "list[int]", lut_laenge: "list[int]") -> "tuple[bytes, int]":
    """Eine der drei LSB-zuerst-Huffman-Stroeme: ``anzahl`` Symbole und die Zahl der gelesenen Bytes (aufgerundet)."""
    acc = n = 0
    links = ende - start
    pos = ende if rueck else start
    aus = bytearray(anzahl)
    benutzt = 0
    for k in range(anzahl):
        if n < _HUFF_MAX:
            if links >= 4:
                if rueck:
                    wort = int.from_bytes(q[pos - 4:pos], "big")
                    pos -= 4
                else:
                    wort = int.from_bytes(q[pos:pos + 4], "little")
                    pos += 4
                acc |= wort << n
                n += 32
                links -= 4
            else:
                while n < _HUFF_MAX:
                    if links == 0:
                        byte = 0
                    else:
                        links -= 1
                        if rueck:
                            pos -= 1
                            byte = q[pos]
                        else:
                            byte = q[pos]
                            pos += 1
                    acc |= byte << n
                    n += 8
        idx = acc & (_HUFF_LUT - 1)
        laenge = lut_laenge[idx]
        aus[k] = lut_symbol[idx]
        acc >>= laenge
        n -= laenge
        benutzt += laenge
    return bytes(aus), -(-benutzt // 8)


def _huffman(q: bytes, n: int) -> bytes:
    """Ein Huffman-Feld (Art 2) mit der alten Tabelle in ``n`` Bytes - ``kraken/huff.rs decode``."""
    r = _BitLeser(q, 0, len(q), False)
    if r.holen(1) != 0:
        raise _verfahren("nicht unterstuetzte Huffman-Tabellenform")
    je_laenge: "list[list[int]]" = [[] for _ in range(_HUFF_MAX + 1)]
    if r.holen(1) == 1:
        fb = r.holen(2)
        grenze = 20 >> fb
        ueberspringen = r.holen(1) == 1
        sym, mittel, zahl = 0, 32, 0
        while sym != 256:
            if ueberspringen:
                ueberspringen = False
            else:
                sym += _gamma(r)
                if sym >= 256:
                    break
            lauf = _gamma(r)
            if sym + lauf > 256:
                raise _verfahren("die Huffman-Tabelle laeuft ueber")
            zahl += lauf
            for _ in range(lauf):
                nullen = r.nullen()
                if nullen > grenze:
                    raise _verfahren("ungueltige Huffman-Codelaenge")
                r.holen(nullen + 1)
                v = (nullen << fb) | r.holen(fb)
                laenge = ((-(v & 1)) ^ (v >> 1)) + ((mittel + 2) >> 2)
                if not 1 <= laenge <= _HUFF_MAX:
                    raise _verfahren("ungueltige Huffman-Codelaenge")
                mittel = laenge + ((3 * mittel + 2) >> 2)
                je_laenge[laenge].append(sym)
                sym += 1
        if sym != 256 or zahl < 2:
            raise _verfahren("ungueltige Huffman-Tabelle")
    else:
        zahl = r.holen(8)
        if zahl == 0:
            raise _verfahren("leere Huffman-Tabelle")
        if zahl == 1:
            symbol = r.holen(8)
            if r.naht() != len(q):
                raise _verfahren("die Ein-Symbol-Tabelle hat die falsche Groesse")
            return bytes([symbol]) * n
        cb = r.holen(3)
        if cb > 4:
            raise _verfahren("ungueltige Huffman-Tabelle")
        for _ in range(zahl):
            s = r.holen(8)
            laenge = r.holen(cb) + 1
            if laenge > _HUFF_MAX:
                raise _verfahren("ungueltige Huffman-Codelaenge")
            je_laenge[laenge].append(s)
    rev = _rev11()
    lut_symbol = [0] * _HUFF_LUT
    lut_laenge = [0] * _HUFF_LUT
    platz = 0
    for laenge in range(1, _HUFF_MAX + 1):
        schritt = 1 << (_HUFF_MAX - laenge)
        for s in je_laenge[laenge]:
            if platz + schritt > _HUFF_LUT:
                raise _verfahren("Huffman-Code ueberbelegt")
            for k in range(platz, platz + schritt):
                lut_symbol[rev[k]] = s
                lut_laenge[rev[k]] = laenge
            platz += schritt
    if platz != _HUFF_LUT:
        raise _verfahren("unvollstaendiger Huffman-Code")
    start = r.naht()
    if start + 3 > len(q):
        raise _verfahren("abgeschnittenes Huffman-Feld")
    teilung = struct.unpack_from("<H", q, start)[0]
    a0 = start + 2
    if a0 + teilung > len(q):
        raise _verfahren("ungueltige Huffman-Teilung")
    n_a, n_b, n_c = (n + 2) // 3, (n + 1) // 3, n // 3
    a, bytes_a = _lsb_strom(q, a0, a0 + teilung, False, n_a, lut_symbol, lut_laenge)
    b, bytes_b = _lsb_strom(q, a0 + teilung, len(q), True, n_b, lut_symbol, lut_laenge)
    c, bytes_c = _lsb_strom(q, a0 + teilung, len(q), False, n_c, lut_symbol, lut_laenge)
    if bytes_a != teilung or bytes_b + bytes_c != len(q) - a0 - teilung:
        raise _verfahren("die Huffman-Stroeme treffen sich nicht")
    aus = bytearray(n)
    aus[0::3] = a
    aus[1::3] = b
    aus[2::3] = c
    return bytes(aus)


def _feld(q: bytes, ab: int, ende: int, hoechstens: int) -> "tuple[bytes, int]":
    """Ein Feld bei ``ab``, roh (Art 0) oder Huffman (Art 2): ``(Bytes, Kopf + Nutzlast)``."""
    if ende < ab + 2:
        raise _verfahren("abgeschnittenes Feld")
    b0 = q[ab]
    art = (b0 >> 4) & 7
    if art == 0:
        if b0 >= 0x80:
            n, kopf = (((b0 << 8) | q[ab + 1]) & 0xFFF), 2
        else:
            if ende < ab + 3:
                raise _verfahren("abgeschnittenes Feld")
            n = (b0 << 16) | (q[ab + 1] << 8) | q[ab + 2]
            if n & ~0x3FFFF:
                raise _verfahren("ungueltige Feldgroesse")
            kopf = 3
        if n > hoechstens or ab + kopf + n > ende:
            raise _verfahren("ein Feld laeuft ueber seinen Abschnitt")
        return bytes(q[ab + kopf:ab + kopf + n]), kopf + n
    if art == 2:
        if b0 >= 0x80:
            if ende < ab + 3:
                raise _verfahren("abgeschnittenes Feld")
            v = (b0 << 16) | (q[ab + 1] << 8) | q[ab + 2]
            quelle = v & 0x3FF
            ziel, kopf = quelle + ((v >> 10) & 0x3FF) + 1, 3
        else:
            if ende < ab + 5:
                raise _verfahren("abgeschnittenes Feld")
            v = struct.unpack_from(">I", q, ab + 1)[0]
            quelle = v & 0x3FFFF
            ziel, kopf = (((v >> 18) | (b0 << 14)) & 0x3FFFF) + 1, 5
        if quelle >= ziel or ziel > hoechstens or ab + kopf + quelle > ende:
            raise _verfahren("ungueltige Huffman-Feldgroesse")
        return _huffman(bytes(q[ab + kopf:ab + kopf + quelle]), ziel), kopf + quelle
    raise _verfahren("nicht unterstuetzte Feldart")


def _lz_haelfte(q: bytes, aus: bytearray, ab: int, laenge: int, delta: bool) -> None:
    """Eine LZ-Haelfte nach ``aus[ab:ab + laenge]`` entpacken; ``aus[:ab]`` ist die Vorgeschichte (``kraken.rs decode_half``)."""
    ende = ab + laenge
    p = 0
    ziel = ab
    if ab == 0:
        if len(q) < _SAAT or laenge < _SAAT:
            raise _verfahren("abgeschnittene Saat")
        aus[:_SAAT] = q[:_SAAT]
        p = ziel = _SAAT
    if len(q) < p + 13:
        raise _verfahren("Stueck zu kurz")
    marke = q[p]
    if marke & 0xC0 != 0x80:
        raise _verfahren("die Ueberlauf-Rahmung fehlt")
    p += 1
    ueberlauf = marke & 0x3F
    if ueberlauf > 0x1F:
        ueberlauf += q[p] * 0x20
        p += 1
    if ueberlauf > len(q) - p:
        raise _verfahren("der Ueberlauf geht ueber das Stueck")
    haupt_ende = len(q) - ueberlauf
    lits, n = _feld(q, p, haupt_ende, laenge)
    p += n
    befehle, n = _feld(q, p, haupt_ende, laenge)
    p += n
    if p >= haupt_ende:
        raise _verfahren("abgeschnittene Abstaende")
    skaliert = q[p] == 0x80
    if skaliert:
        p += 1
    codes, n = _feld(q, p, haupt_ende, len(befehle))
    p += n
    laengen, n = _feld(q, p, haupt_ende, laenge // 4)
    p += n

    a = _BitLeser(q, p, haupt_ende, False)
    b = _BitLeser(q, p, haupt_ende, True)
    abstaende: "list[int]" = []
    for k, c in enumerate(codes):
        r = a if k % 2 == 0 else b
        if skaliert:
            nb = c >> 3
            if nb > 26:
                raise _verfahren("ungueltiger Abstandscode")
            abstaende.append((((8 + (c & 7)) << nb) | r.holen(nb)) - 8)
        else:
            if c >= 0xF0:
                raise _verfahren("Abstand hinter dem Block")
            nn = (c >> 4) + 4
            abstaende.append(((((1 << nn) | r.holen(nn)) << 4) + (c & 0xF)) - 248)
    if a.naht() != b.naht():
        raise _verfahren("die Abstandsstroeme treffen sich nicht")
    n_esc = sum(1 for v in laengen if v == 255)
    ea = _BitLeser(q, haupt_ende, len(q), False)
    eb = _BitLeser(q, haupt_ende, len(q), True)
    esc: "list[int]" = []
    for k in range(n_esc):
        esc.append((ea if k % 2 == 0 else eb).laenge_holen())
    if ea.naht() != eb.naht():
        raise _verfahren("die Ueberlaufstroeme treffen sich nicht")
    esc_pos = 0
    laengen_pos = 0
    n_laengen = len(laengen)

    lit_ab = 0
    abst_pos = 0
    zuletzt = [8, 8, 8]
    for f in befehle:
        lit = f & 3
        if lit == 3:
            if laengen_pos >= n_laengen:
                raise _verfahren("Laenge fehlt")
            v = laengen[laengen_pos]
            laengen_pos += 1
            if v == 255:
                if esc_pos >= len(esc):
                    raise _verfahren("Ueberlauf fehlt")
                v = 255 + esc[esc_pos]
                esc_pos += 1
            lit = 3 + v
        art = f >> 6
        code = (f >> 2) & 0xF
        if lit_ab + lit > len(lits) or ziel + lit > ende:
            raise _verfahren("ein Literallauf laeuft ueber")
        if lit:
            if delta:
                letzte = zuletzt[0]
                if letzte >= lit:
                    folge = lits[lit_ab:lit_ab + lit]
                    basis = aus[ziel - letzte:ziel - letzte + lit]
                    aus[ziel:ziel + lit] = bytes([(x + y) & 0xFF for x, y in zip(folge, basis)])
                else:
                    for j in range(lit):
                        aus[ziel + j] = (lits[lit_ab + j] + aus[ziel + j - letzte]) & 0xFF
            else:
                aus[ziel:ziel + lit] = lits[lit_ab:lit_ab + lit]
        ziel += lit
        lit_ab += lit
        if art == 3:
            if abst_pos >= len(abstaende):
                raise _verfahren("Abstand fehlt")
            d = abstaende[abst_pos]
            abst_pos += 1
            zuletzt = [d, zuletzt[0], zuletzt[1]]
        else:
            d = zuletzt[art]
            for j in range(art, 0, -1):
                zuletzt[j] = zuletzt[j - 1]
            zuletzt[0] = d
        if code == 15:
            if laengen_pos >= n_laengen:
                raise _verfahren("Laenge fehlt")
            v = laengen[laengen_pos]
            laengen_pos += 1
            if v == 255:
                if esc_pos >= len(esc):
                    raise _verfahren("Ueberlauf fehlt")
                v = 255 + esc[esc_pos]
                esc_pos += 1
            mlaenge = 14 + 3 + v
        else:
            mlaenge = code + 2
        if d < _MIN_ABSTAND or d > ziel or ziel + mlaenge > ende:
            raise _verfahren("Treffer ausserhalb der Grenzen")
        if d >= mlaenge:
            aus[ziel:ziel + mlaenge] = aus[ziel - d:ziel - d + mlaenge]
        else:
            muster = bytes(aus[ziel - d:ziel])
            wiederholt, rest = divmod(mlaenge, d)
            aus[ziel:ziel + mlaenge] = muster * wiederholt + muster[:rest]
        ziel += mlaenge
    rest = ende - ziel
    if len(lits) - lit_ab != rest:
        raise _verfahren("die uebrigen Literale fuellen die Haelfte nicht")
    if rest:
        if delta:
            letzte = zuletzt[0]
            for j in range(rest):
                aus[ziel + j] = (lits[lit_ab + j] + aus[ziel + j - letzte]) & 0xFF
        else:
            aus[ziel:ziel + rest] = lits[lit_ab:]
    if abst_pos != len(abstaende) or laengen_pos != n_laengen:
        raise _verfahren("unbenutzte Abstaende oder Laengen")


def _entropie_haelfte(q: bytes, laenge: int) -> bytes:
    aus, benutzt = _feld(q, 0, len(q), laenge)
    if benutzt != len(q) or len(aus) != laenge:
        raise _verfahren("die Entropie-Haelfte hat die falsche Laenge oder Reste")
    return aus


def _entmischen(daten: bytearray, muster: int) -> None:
    """Die Byte-Mischung ``muster`` je 64-KiB-Einheit rueckgaengig machen (``kraken_image.rs deshuffle``)."""
    if not 0 <= muster < len(_MISCHUNGEN):
        raise _verfahren("Mischung %d ist keine der 13 bekannten" % muster)
    felder = _MISCHUNGEN[muster]
    schritt = sum(felder)
    if schritt == 0:
        return
    for anfang in range(0, len(daten), _MISCHUNG_EINHEIT):
        stueck = daten[anfang:anfang + _MISCHUNG_EINHEIT]
        vektoren = len(stueck) // schritt
        if vektoren == 0:
            continue
        einheit = bytes(stueck)
        ziel = bytearray(stueck)
        innen = 0
        ab = 0
        for f in felder:
            for j in range(f):
                ziel[innen + j:vektoren * schritt:schritt] = einheit[ab + j:ab + vektoren * f:f]
            ab += vektoren * f
            innen += f
        daten[anfang:anfang + len(stueck)] = ziel


class _Beschrieben:
    """Ein Block, wie die Beschreibung ihn nennt."""

    __slots__ = ("logisch", "laenge", "abgelegt_ab", "gerade_laenge", "abgelegt_laenge", "gerade_lz", "ungerade_lz", "modus", "mischung")


def _block_entpacken(gespeichert: bytes, b: _Beschrieben) -> bytes:
    """Block ``b`` aus seinen abgelegten Bytes - ``kraken_image.rs decode_described``."""
    if b.laenge == 0 or b.laenge > _UBLOCK:
        raise _verfahren("ein Block von %#x Bytes ist kein Kraken-Block" % b.laenge)
    if b.abgelegt_laenge == 0:
        if not (b.abgelegt_ab == 0 and b.gerade_laenge == 0 and not b.gerade_lz and not b.ungerade_lz and b.modus == 0 and b.mischung == 0):
            raise _verfahren("ein Block ohne abgelegte Bytes ist kein Leerblock")
        return bytes(b.laenge)
    if b.abgelegt_laenge > 2 * _FENSTER or b.gerade_laenge > b.abgelegt_laenge or len(gespeichert) != b.abgelegt_laenge:
        raise _verfahren("ein Block in %#x abgelegten Bytes (%#x gerade) ist kein Kraken-Block" % (b.abgelegt_laenge, b.gerade_laenge))
    gerade_logisch = min(b.laenge, _HALB)
    e, o = gespeichert[:b.gerade_laenge], gespeichert[b.gerade_laenge:]

    def haelfte(roh: bytes, laenge: int, lz: bool, delta: bool) -> "tuple[bytes, bool, bool]":
        if lz or len(roh) == laenge:
            return roh, lz, delta
        return _entropie_haelfte(roh, laenge), False, False

    haelften = [haelfte(e, gerade_logisch, b.gerade_lz, bool(b.modus & 1))]
    if b.laenge > _HALB:
        haelften.append(haelfte(o, b.laenge - _HALB, b.ungerade_lz, bool(b.modus & 0b1000)))
    elif o:
        raise _verfahren("unerwartete ungerade Haelfte")
    aus = bytearray(b.laenge)
    ab = 0
    for roh, lz, delta in haelften:
        hl = min(b.laenge - ab, _HALB)
        if lz:
            _lz_haelfte(roh, aus, ab, hl, delta)
        else:
            if len(roh) != hl:
                raise _verfahren("eine rohe Haelfte hat die falsche Laenge")
            aus[ab:ab + hl] = roh
        ab += hl
    if ab != b.laenge:
        raise _verfahren("die Haelften decken den Block nicht")
    _entmischen(aus, b.mischung)
    return bytes(aus)


# --------------------------------------------------------------------------------------------------------------------- Beschreibung

def _form(blob: bytes, w0: int, w1: int) -> str:
    """``"kraken"``, ``"flach"`` oder ``"beides"`` - woran die Beschreibung erkennbar ist (``mount.rs shape``)."""
    dateien = (w0 & 0xFFFFFF) + 1
    mischung = (w0 >> 28) & 0xF
    ublocks = (w0 >> 32) & 0xFFFFFF
    aussen = w1 & 0xFFFFFF
    saetze = ((w1 >> 24) & 0xFFFFFF) + 2
    fidx_ende = 16 + (aussen + mischung) * 8 + dateien * 6
    satz_ab = (-(-(fidx_ende + (ublocks // 8 + 1) * 10) // 8)) * 8 + 3
    flach_laenge = fidx_ende + (-(-ublocks // 8) + 1) * 10 + saetze * 9
    marke = blob[satz_ab - 3:satz_ab] if satz_ab <= len(blob) else b""
    if marke == b"\x00\x00\x04":
        return "kraken"
    if len(marke) == 3 and len(blob) >= satz_ab + saetze * 9:
        return "beides" if len(blob) == flach_laenge else "kraken"
    return "flach"


def _beschreiben(blob: bytes) -> "tuple[list[_Beschrieben], int]":
    """Die Beschreibung abgehen, wie die Konsole es tut: Saetze der Reihe nach, Anker setzen die Ablageposition, Bloecke fuellen den Einhaengepunkt
    (``kraken_image.rs describe``). Gibt die Bloecke und die Groesse des Einhaengepunkts."""
    if len(blob) < 16:
        raise _beschaedigt("die Beschreibung ist kuerzer als ihr Kopf")
    w0, w1 = struct.unpack_from("<QQ", blob, 0)
    dateien = (w0 & 0xFFFFFF) + 1
    ublocks = (w0 >> 32) & 0xFFFFFF
    aussen = w1 & 0xFFFFFF
    mischung = (w0 >> 28) & 0xF
    saetze = ((w1 >> 24) & 0xFFFFFF) + 2
    fidx_ab = 16 + (aussen + mischung) * 8
    u2c_ende = fidx_ab + dateien * 6 + (ublocks // 8 + 1) * 10
    satz_ab = (-(-u2c_ende // 8)) * 8 + 3
    if len(blob) < satz_ab + saetze * 9:
        raise _beschaedigt("die Beschreibung ist kuerzer als ihre Saetze")
    tabelle: "list[int]" = []
    for p in range(mischung):
        e = blob[16 + (aussen + p) * 8:16 + (aussen + p) * 8 + 8]
        benutzt = next((i for i, x in enumerate(e) if x == 0), 8)
        gefunden = next((i for i, m in enumerate(_MISCHUNGEN) if all(x == 0 for x in e[benutzt:]) and bytes(m) == e[:benutzt]), None)
        if gefunden is None:
            raise _verfahren("Mischung %d: unbekannte Beschreibung %s" % (p, e.hex()))
        tabelle.append(gefunden)
    eintraege: "list[tuple[int, int]]" = []
    for i in range(dateien):
        r = blob[fidx_ab + i * 6:fidx_ab + i * 6 + 6]
        eintraege.append((int.from_bytes(r[:5], "little"), r[5]))
    einhaengen = eintraege[-1][0]
    if -(-einhaengen // _UBLOCK) != ublocks or any(e[0] > einhaengen for e in eintraege):
        raise _beschaedigt("die Grenztabelle widerspricht der Groesse des Einhaengepunkts")
    grenzen = sorted({e[0] for e in eintraege})

    def naechste_grenze(x: int) -> int:
        i = bisect.bisect_right(grenzen, x)
        return grenzen[i] if i < len(grenzen) else einhaengen

    leer = {}
    leer_bloecke = 0
    for ab, art in eintraege:
        if art == 0x40 and ab < einhaengen and ab not in leer:
            leer[ab] = naechste_grenze(ab)
            leer_bloecke += -(-max(0, leer[ab] - ab) // _UBLOCK)
            if len(leer) > _MAX_LEERBEREICHE or leer_bloecke > _MAX_LEERBLOECKE:
                # Jeder Leerbereich wird zu eigenen Bloecken; eine gebaute Beschreibung mit Millionen davon brauchte Gigabytes
                # (gemessen: 2 Mio. -> 598 MB, 19 s), ebenso ein einziger Bereich ueber Terabytes (1 Mio. Bloecke -> 155 MB).
                # Echte Pakete haben eine Handvoll (LEGO Batman: einen).
                raise _verfahren("die Beschreibung nennt zu viele Leerbereiche (%d, %d Bloecke)" % (len(leer), leer_bloecke))
    aus: "list[_Beschrieben]" = []

    def fuellen(logisch: int) -> int:
        while logisch in leer:
            ende = leer[logisch]
            while logisch < ende:
                laenge = min(ende - logisch, _UBLOCK)
                blk = _Beschrieben()
                blk.logisch, blk.laenge, blk.abgelegt_ab, blk.gerade_laenge, blk.abgelegt_laenge = logisch, laenge, 0, 0, 0
                blk.gerade_lz = blk.ungerade_lz = False
                blk.modus = blk.mischung = 0
                aus.append(blk)
                logisch += laenge
        return logisch

    streng = blob[satz_ab - 3:satz_ab] == b"\x00\x00\x04"
    roh = memoryview(blob)
    s = [int.from_bytes(roh[satz_ab + i * 9:satz_ab + i * 9 + 9], "little") for i in range(saetze)]
    cursor = logisch = 0
    naechster_anker = True
    getragen = 0
    for i in range(saetze - 1):
        v = s[i]
        nibble, getragen = getragen, (v >> 68) & 0xF
        anker = naechster_anker
        lauf_ende = (v >> 66) & 1
        naechster_anker = lauf_ende == 1 and not anker
        if anker:
            cursor = (((v >> 26) & 0x3FFFFF) << 18) | ((v >> 48) & 0x3FFFF)
            abschluss = i + 2 == saetze
            if streng and i > 0 and not abschluss and nibble != (cursor >> 16) & 0xF:
                raise _beschaedigt("Satz %d: das Nibble der Ankerposition widerspricht" % i)
            continue
        logisch = fuellen(logisch)
        if streng and i > 0 and nibble != logisch & 0xF:
            raise _beschaedigt("Satz %d: das Nibble des genauen Anfangs widerspricht" % i)
        if logisch >= einhaengen:
            raise _beschaedigt("Satz %d: ein Block beginnt bei %#x, am oder hinter dem Ende %#x" % (i, logisch, einhaengen))
        if (logisch % _FENSTER) >> 4 != (v & 0x3FFF):
            raise _beschaedigt("Satz %d: der logische Anfang widerspricht" % i)
        deckel = logisch + min(min(naechste_grenze(logisch), einhaengen) - logisch, _UBLOCK)
        folge = i + 2 if lauf_ende == 1 else i + 1
        if folge + 1 < saetze:
            ab16 = (logisch & ~(_FENSTER - 1)) | ((s[folge] & 0x3FFF) << 4)
            if ab16 <= logisch & ~0xF:
                ab16 += _FENSTER
            tief = ((s[folge - 1] >> 68) & 0xF) if streng else logisch & 0xF
            genau = ab16 | tief
            if ab16 + 16 <= deckel or (streng and genau < deckel):
                laenge = genau - logisch
            else:
                laenge = deckel - logisch
        else:
            laenge = deckel - logisch
        ende = (cursor & ~(_FENSTER - 1)) | ((v >> 48) & 0x3FFFF)
        if ende < cursor:
            ende += _FENSTER
        gerade_laenge = ((v >> 14) & 0x1FFFF) + 1
        gerade_roh = ((v >> 33) & 1) == 0 and gerade_laenge == min(laenge, _HALB)
        ungerade_roh = ((v >> 36) & 1) == 0
        if ende == cursor and gerade_roh and ungerade_roh and laenge > _HALB:
            ende += _FENSTER
        if ende == cursor:
            raise _beschaedigt("Satz %d: ein Block ohne abgelegte Bytes" % i)
        k = (v >> 44) & 0xF
        if k == 0:
            mischung_nr = 0
        elif k - 1 < len(tabelle):
            mischung_nr = tabelle[k - 1]
        else:
            raise _beschaedigt("Satz %d: Mischungsindex %d hinter der Tabelle (%d)" % (i, k, len(tabelle)))
        blk = _Beschrieben()
        blk.logisch, blk.laenge, blk.abgelegt_ab = logisch, laenge, cursor
        blk.gerade_laenge, blk.abgelegt_laenge = gerade_laenge, ende - cursor
        blk.gerade_lz, blk.ungerade_lz = ((v >> 33) & 1) == 1, ((v >> 36) & 1) == 1
        blk.modus, blk.mischung = (v >> 32) & 0x1F, mischung_nr
        aus.append(blk)
        cursor = ende
        logisch += laenge
    logisch = fuellen(logisch)
    if logisch != einhaengen:
        raise _beschaedigt("die Bloecke fuellen %#x, der Einhaengepunkt hat %#x" % (logisch, einhaengen))
    return aus, einhaengen


class _Einhaengepunkt:
    """Das innere Abbild, wie die Konsole es sieht: Bloecke zu hoechstens 256 KiB, nach Bedarf aus den Aussenbloecken geholt und entpackt."""

    def __init__(self, bild: _AussenDatei, bloecke: "list[_Beschrieben]", groesse: int) -> None:
        self.bild, self.bloecke, self.groesse = bild, bloecke, groesse
        self._starts = [b.logisch for b in bloecke]
        self._zwischen: "dict[int, bytes]" = {}
        for b in bloecke:
            if b.abgelegt_ab + b.abgelegt_laenge > bild.groesse:
                raise _beschaedigt("der Block bei %#x laeuft ueber das abgelegte Abbild" % b.logisch)

    def _block(self, i: int) -> bytes:
        gefunden = self._zwischen.get(i)
        if gefunden is not None:
            return gefunden
        b = self.bloecke[i]
        gespeichert = self.bild.lesen(b.abgelegt_ab, b.abgelegt_laenge) if b.abgelegt_laenge else b""
        daten = _block_entpacken(gespeichert, b)
        if len(daten) != b.laenge:
            raise _verfahren("der Block bei %#x ergibt %d statt %d Bytes" % (b.logisch, len(daten), b.laenge))
        if len(self._zwischen) >= _ENTPACKT_ZWISCHENSPEICHER:
            del self._zwischen[next(iter(self._zwischen))]
        self._zwischen[i] = daten
        return daten

    def lesen(self, ab: int, n: int) -> bytes:
        if ab < 0 or n < 0 or ab + n > self.groesse:
            raise _beschaedigt("ein Lesevorgang von %d Bytes bei %#x geht ueber den Einhaengepunkt (%#x)" % (n, ab, self.groesse))
        aus = bytearray()
        i = bisect.bisect_right(self._starts, ab) - 1
        while len(aus) < n:
            b = self.bloecke[i]
            innen = ab + len(aus) - b.logisch
            nimm = min(b.laenge - innen, n - len(aus))
            aus += self._block(i)[innen:innen + nimm]
            i += 1
        return bytes(aus)


# ------------------------------------------------------------------------------------------------------------------ inneres Dateisystem

class _Inneres:
    """Das Dateisystem im Einhaengepunkt: Oberblock an der Metadatenbasis, Inode-Tabelle einen Block dahinter, ein Verzeichnisstrom je Ordner."""

    def __init__(self, punkt: _Einhaengepunkt, meta_basis: int) -> None:
        self.punkt, self.meta_basis = punkt, meta_basis
        if meta_basis + BLOCK > punkt.groesse:
            raise _beschaedigt("die Metadatenbasis %#x liegt hinter dem Einhaengepunkt" % meta_basis)
        ob = punkt.lesen(meta_basis, 0x40)
        if _le64(ob, 0) != 2 or _le64(ob, 8) != _OBERBLOCK_MAGIC:
            raise _beschaedigt("innerer Oberblock: Fassung oder Kennung stimmen nicht")
        if _le32(ob, 0x20) != BLOCK:
            raise _beschaedigt("innere Blockgroesse %#x" % _le32(ob, 0x20))
        self.inodes = _le64(ob, 0x30)
        if self.inodes <= _ERSTER_ORDNER or self.inodes > 4_000_000:
            raise _beschaedigt("unplausible Inode-Zahl %d" % self.inodes)
        self.tabelle_ab = meta_basis + BLOCK

    def inode(self, nr: int) -> "tuple[int, int, int]":
        """``(Modus, Groesse, logische Stelle)`` des Inodes ``nr``."""
        if nr >= self.inodes:
            raise _beschaedigt("Inode %d liegt hinter der Tabelle (%d)" % (nr, self.inodes))
        ab = (nr // _INODES_JE_BLOCK) * BLOCK + (nr % _INODES_JE_BLOCK) * _INODE_LEN
        roh = self.punkt.lesen(self.tabelle_ab + ab, _INODE_LEN)
        return _le16(roh, 0), _le64(roh, 8), _le64(roh, 0x60)

    def verzeichnis(self, nr: int) -> "list[tuple[int, int, str]]":
        modus, groesse, logisch = self.inode(nr)
        if modus & 0xF000 != 0x4000:
            raise _beschaedigt("Inode %d ist kein Ordner" % nr)
        if groesse > (64 << 20) or logisch + groesse > self.punkt.groesse:
            raise _beschaedigt("ein Ordner meldet %d Bytes bei %#x" % (groesse, logisch))
        roh = self.punkt.lesen(logisch, groesse)
        aus, o = [], 0
        while o + 16 <= len(roh):
            ino, art, namenlaenge, eintraglaenge = _le32(roh, o), struct.unpack_from("<i", roh, o + 4)[0], _le32(roh, o + 8), _le32(roh, o + 12)
            if eintraglaenge == 0:
                break
            if eintraglaenge < 16 + namenlaenge or o + 16 + namenlaenge > len(roh):
                raise _beschaedigt("ein Verzeichniseintrag ist fehlerhaft")
            name = roh[o + 16:o + 16 + namenlaenge].decode("utf-8", "replace")
            o += eintraglaenge
            if art in (_EINTRAG_PUNKT, _EINTRAG_PUNKTPUNKT):
                continue
            aus.append((ino, art, name))
        return aus

    def datei(self, pfad: str, gleich_gross: bool = False) -> "tuple[int, int] | None":
        """``(logische Stelle, Groesse)`` der Datei ``pfad`` (mit ``/``); ``None``, wenn es sie nicht gibt.

        ``gleich_gross``: Gross- und Kleinschreibung der Namen gilt nicht (wie bei der ``eboot.bin`` in Ordnern und Abbildern, ``programm_sdk``).
        """
        teile = [t for t in pfad.split("/") if t]
        ordner = _ERSTER_ORDNER
        for stufe, teil in enumerate(teile):
            letzte = stufe == len(teile) - 1
            treffer = next(((ino, art) for ino, art, name in self.verzeichnis(ordner)
                            if name == teil or (gleich_gross and name.lower() == teil.lower())), None)
            if treffer is None:
                return None
            ino, art = treffer
            if letzte:
                if art != _EINTRAG_DATEI:
                    return None
                modus, groesse, logisch = self.inode(ino)
                if modus & 0xF000 != 0x8000 or logisch + groesse > self.meta_basis:
                    raise _beschaedigt("%s: Inode %d ist keine regulaere Datei oder liegt hinter dem Datenbereich" % (pfad, ino))
                return logisch, groesse
            if art != _EINTRAG_ORDNER:
                return None
            ordner = ino
        return None

    def lesen(self, pfad: str, ab: int, n: int, gleich_gross: bool = False) -> bytes:
        stelle = self.datei(pfad, gleich_gross)
        if stelle is None:
            raise FileNotFoundError(pfad)
        logisch, groesse = stelle
        if ab >= groesse:
            return b""
        return self.punkt.lesen(logisch + ab, min(n, groesse - ab))


# ----------------------------------------------------------------------------------------------------------------------- Oeffnen, SDK

class _Aussenwelt:
    """Das aeussere PFS eines Pakets, geoeffnet: Kopf, Bloecke und ``kind(ordner, name)`` fuer die Namen darin."""

    __slots__ = ("kopf", "aussen", "knoten", "kind")


def _aussenwelt(fh: Any, passcode: str) -> _Aussenwelt:
    """Kopf, Behaelter, Oberblock und Inode-Tabelle des aeusseren PFS lesen (und entschluesseln)."""
    paket = _Paket(fh)
    kopf = _kopf_lesen(paket)
    behaelter = _behaelter_lesen(paket, kopf.cnt_ab)
    pruefsummen = behaelter.eintrag(_ID_BILDPRUEFSUMMEN)
    if pruefsummen is None:
        raise _beschaedigt("der Behaelter hat keinen imagedigs-Eintrag")
    if pruefsummen[1] != kopf.aussen_bloecke * 32:
        raise _beschaedigt("imagedigs hat %d Bytes fuer %d Aussenbloecke" % (pruefsummen[1], kopf.aussen_bloecke))
    aussen = _Aussen(paket, kopf, pruefsummen[0])
    ober = aussen.laden(kopf.ober_index)
    if ober is None or _sha3(ober) != kopf.spiel_pruefsumme:
        raise _beschaedigt("der aeussere Oberblock passt nicht zu seinen Pruefsummen")
    if len(ober) < 0x5A0 or _le64(ober, 0) != 2 or _le64(ober, 8) != _OBERBLOCK_MAGIC:
        raise _beschaedigt("aeusserer Oberblock: Fassung oder Kennung stimmen nicht")
    pruef = bytearray(ober[:0x5A0])
    pruef[0x380:0x3A0] = bytes(32)
    if _sha3(bytes(pruef)) != ober[0x380:0x3A0]:
        raise _beschaedigt("aeusserer Oberblock: ICV stimmt nicht")
    saat = bytes(ober[0x370:0x380])
    dinode_zahl = _le64(ober, 0x30)
    tabelle_block = _le32(ober, 0xD8)
    tabelle_digest = bytes(ober[0xB8:0xD8])
    if saat != _KLARTEXT_MARKE:
        aussen.schluessel_setzen(schluessel_ableiten(behaelter.inhalts_id, passcode, saat))
    if tabelle_block == kopf.ober_index:
        raise _beschaedigt("die aeussere Inode-Tabelle ist der Oberblock")
    tabelle = aussen.laden(tabelle_block)
    if tabelle is None or _sha3(tabelle) != tabelle_digest:
        if saat == _KLARTEXT_MARKE:
            raise _beschaedigt("die aeussere Inode-Tabelle passt nicht zu ihrer Pruefsumme")
        raise PaketFehler("passcode", "die Aussenbloecke lassen sich mit diesem Passcode nicht entschluesseln")
    knoten = _dinodes(tabelle, dinode_zahl)

    def kind(ordner: int, name: str) -> int:
        if ordner >= len(knoten):
            raise _beschaedigt("das aeussere Dinode %d fehlt" % ordner)
        wurzel = knoten[ordner]
        for ino, _art, n in _aussen_verzeichnis(aussen.block(wurzel.direkt[0][1]), wurzel.groesse):
            if n == name and ino < len(knoten):
                return ino
        raise _beschaedigt("das aeussere Abbild hat kein %s" % name)

    welt = _Aussenwelt()
    welt.kopf, welt.aussen, welt.knoten, welt.kind = kopf, aussen, knoten, kind
    return welt


def _beschreibungsdatei(welt: _Aussenwelt) -> _AussenDatei:
    """``naps_pkg_layout.dat`` des aeusseren PFS."""
    uroot = welt.kind(0, "uroot")
    dinode = welt.knoten[welt.kind(uroot, "naps_pkg_layout.dat")]
    if dinode.groesse > _MAX_BESCHREIBUNG:
        raise _verfahren("die Beschreibung ist %d Bytes gross (hoechstens %d werden gelesen)" % (dinode.groesse, _MAX_BESCHREIBUNG))
    return _AussenDatei(welt.aussen, dinode, "naps_pkg_layout.dat")


def oeffnen(fh: Any, passcode: str = STANDARD_PASSCODE) -> _Inneres:
    """Das innere Dateisystem eines Debug-Pakets; wirft :class:`PaketFehler` (ein ``ValueError``), wenn es sich so nicht lesen laesst."""
    welt = _aussenwelt(fh, passcode)
    uroot = welt.kind(0, "uroot")
    bild = _AussenDatei(welt.aussen, welt.knoten[welt.kind(uroot, "pfs_image.dat")], "pfs_image.dat")
    beschreibung = _beschreibungsdatei(welt)
    blob = beschreibung.lesen(0, beschreibung.groesse)
    return _inneres_aus(bild, blob, welt.kopf.meta_basis)


def _inneres_aus(bild: _AussenDatei, blob: bytes, meta_basis: int) -> _Inneres:
    """Das innere Dateisystem aus dem Bild und der Beschreibung ``blob``."""
    if len(blob) < 16:
        raise _beschaedigt("die Beschreibung ist kuerzer als ihr Kopf")
    w0, w1 = struct.unpack_from("<QQ", blob, 0)
    verdichtung = (w0 >> 24) & 3
    if verdichtung != 2:
        raise PaketFehler("verfahren", "das innere Abbild meldet Verdichtung %d, gelesen wird nur Kraken" % verdichtung)
    form = _form(blob, w0, w1)
    if form == "flach":
        raise PaketFehler("verfahren", "ein flaches inneres Abbild (ohne Kraken) wird nicht gelesen")
    try:
        bloecke, groesse = _beschreiben(blob)
    except PaketFehler:
        if form == "beides":
            raise PaketFehler("verfahren", "ein flaches inneres Abbild (ohne Kraken) wird nicht gelesen") from None
        raise
    return _Inneres(_Einhaengepunkt(bild, bloecke, groesse), meta_basis)


def eboot_sdk(pfad: str, passcode: str = STANDARD_PASSCODE) -> str:
    """Das SDK der ``eboot.bin`` eines Pakets als Text (``"10.00"``); ``""``, wenn nichts zu lesen ist. Wirft nie.

    Liest nur die Aussenbloecke und Kraken-Bloecke, die der Weg zur ``eboot.bin`` und deren erste KiB beruehren.
    """
    try:
        with open(pfad, "rb") as fh:
            inneres = oeffnen(fh, passcode)
            stelle = inneres.datei("eboot.bin", True)
            if stelle is None:
                return ""

            def lesen(ab: int, laenge: int) -> bytes:
                return inneres.lesen("eboot.bin", ab, laenge, True)

            return programm_sdk.sdk_text(programm_sdk.sdk_wort_lesen(lesen))
    except PaketFehler as exc:
        logger.debug("Paket nicht gelesen (%s): %s", pfad, exc)
    except (OSError, ValueError, KeyError, IndexError, struct.error, OverflowError, ImportError, MemoryError,
            RecursionError) as exc:
        logger.debug("Paket nicht gelesen (%s): %s: %s", pfad, type(exc).__name__, exc)
    return ""
