# -*- coding: utf-8 -*-
"""``geraete_suche``: NAS und Rechner im Netz finden (mDNS, WS-Discovery) - Pakete gebaut und gelesen, dazu ein Durchlauf gegen Test-Antworter (14.11.2026)."""
from __future__ import annotations

import socket
import struct
import sys
import threading
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import geraete_suche as gs          # noqa: E402


def _n(name: str) -> bytes:
    return gs._name_kodieren(name)


def _rr(name: bytes, typ: int, rdata: bytes, ttl: int = 120) -> bytes:
    return name + struct.pack(">HHIH", typ, 0x8001, ttl, len(rdata)) + rdata


def _antwort(eintraege: "list[bytes]") -> bytes:
    return struct.pack(">HHHHHH", 0, 0x8400, 0, len(eintraege), 0, 0) + b"".join(eintraege)


def _smb_antwort(instanz: str = "MeinNAS", ziel: str = "meinnas.local", adresse: str = "192.168.1.20", port: int = 445) -> bytes:
    dienst = "_smb._tcp.local"
    voll = instanz + "." + dienst
    return _antwort([
        _rr(_n(dienst), gs._TYP_PTR, _n(voll)),
        _rr(_n(voll), gs._TYP_SRV, struct.pack(">HHH", 0, 0, port) + _n(ziel)),
        _rr(_n(ziel), gs._TYP_A, socket.inet_aton(adresse)),
    ])


class MdnsTests(unittest.TestCase):
    def test_die_anfrage_fragt_alle_dienste_mit_dem_unicast_bit(self) -> None:
        paket = gs.mdns_anfrage()
        _id, flags, fragen, *_rest = struct.unpack_from(">HHHHHH", paket, 0)
        self.assertEqual((0, len(gs.DIENSTE)), (flags, fragen))
        self.assertIn(b"\x04_smb\x04_tcp\x05local\x00", paket)
        # jede Frage endet auf Typ PTR (12) und Klasse IN mit gesetztem QU-Bit (0x8001)
        self.assertEqual(len(gs.DIENSTE), paket.count(b"\x00\x0c\x80\x01"))

    def test_nur_ein_dienst(self) -> None:
        paket = gs.mdns_anfrage(["_ftp._tcp.local"])
        self.assertEqual(1, struct.unpack_from(">H", paket, 4)[0])

    def test_eine_smb_antwort(self) -> None:
        self.assertEqual([gs.Geraet("MeinNAS", "192.168.1.20", "smb", 445)], gs.mdns_antwort_lesen(_smb_antwort(), "192.168.1.99"))

    def test_ohne_adresssatz_gilt_der_absender(self) -> None:
        dienst = "_ftp._tcp.local"
        voll = "Drucker." + dienst
        paket = _antwort([_rr(_n(dienst), gs._TYP_PTR, _n(voll)),
                          _rr(_n(voll), gs._TYP_SRV, struct.pack(">HHH", 0, 0, 21) + _n("drucker.local"))])
        self.assertEqual([gs.Geraet("Drucker", "10.0.0.7", "ftp", 21)], gs.mdns_antwort_lesen(paket, "10.0.0.7"))

    def test_namensverweise_werden_aufgeloest(self) -> None:
        """Echte Geraete kuerzen mit Zeigern (0xC0..) auf frueher genannte Namen."""
        kopf = struct.pack(">HHHHHH", 0, 0x8400, 0, 3, 0, 0)
        dienst = _n("_smb._tcp.local")
        pos_dienst = 12
        ptr = dienst + struct.pack(">HHIH", gs._TYP_PTR, 0x8001, 120, 0)             # Laenge wird unten gesetzt
        instanz = bytes([5]) + b"Heim1" + bytes([0xC0, pos_dienst])                   # "Heim1" + Verweis auf den Dienstnamen
        ptr = dienst + struct.pack(">HHIH", gs._TYP_PTR, 0x8001, 120, len(instanz)) + instanz
        pos_instanz = 12 + len(dienst) + 10
        srv_rdata = struct.pack(">HHH", 0, 0, 445) + bytes([4]) + b"heim" + bytes([5]) + b"local" + b"\x00"
        srv = bytes([0xC0, pos_instanz]) + struct.pack(">HHIH", gs._TYP_SRV, 0x8001, 120, len(srv_rdata)) + srv_rdata
        pos_ziel = 12 + len(ptr) + 2 + 10 + 6
        a = bytes([0xC0, pos_ziel]) + struct.pack(">HHIH", gs._TYP_A, 0x8001, 120, 4) + socket.inet_aton("192.168.5.5")
        self.assertEqual([gs.Geraet("Heim1", "192.168.5.5", "smb", 445)], gs.mdns_antwort_lesen(kopf + ptr + srv + a, ""))

    def test_mehrere_geraete_und_fremde_dienste(self) -> None:
        paket = _antwort([
            _rr(_n("_smb._tcp.local"), gs._TYP_PTR, _n("A._smb._tcp.local")),
            _rr(_n("_smb._tcp.local"), gs._TYP_PTR, _n("B._smb._tcp.local")),
            _rr(_n("_http._tcp.local"), gs._TYP_PTR, _n("Web._http._tcp.local")),            # kein Dienst, der gesucht wird
            _rr(_n("A._smb._tcp.local"), gs._TYP_SRV, struct.pack(">HHH", 0, 0, 445) + _n("a.local")),
            _rr(_n("B._smb._tcp.local"), gs._TYP_SRV, struct.pack(">HHH", 0, 0, 445) + _n("b.local")),
            _rr(_n("a.local"), gs._TYP_A, socket.inet_aton("10.1.1.1")),
            _rr(_n("b.local"), gs._TYP_A, socket.inet_aton("10.1.1.2")),
        ])
        self.assertEqual({("A", "10.1.1.1"), ("B", "10.1.1.2")}, {(g.name, g.adresse) for g in gs.mdns_antwort_lesen(paket, "")})

    def test_eine_frage_und_kaputte_pakete_ergeben_nichts(self) -> None:
        self.assertEqual([], gs.mdns_antwort_lesen(gs.mdns_anfrage(), "1.2.3.4"))               # eine Frage, keine Antwort
        self.assertEqual([], gs.mdns_antwort_lesen(b"", ""))
        self.assertEqual([], gs.mdns_antwort_lesen(b"\x00" * 5, ""))
        voll = _smb_antwort()
        for n in (13, 20, 40, len(voll) - 3):
            with self.subTest(abgeschnitten=n):
                self.assertEqual([], gs.mdns_antwort_lesen(voll[:n], "x") if n < len(voll) - 1 else [])
        schleife = struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 0) + bytes([0xC0, 12]) + b"\x00" * 10             # ein Verweis auf sich selbst
        self.assertEqual([], gs.mdns_antwort_lesen(schleife, ""))


WSD_ANTWORT = (
    '<?xml version="1.0"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
    '<s:Body><d:ProbeMatches><d:ProbeMatch><a:EndpointReference><a:Address>urn:uuid:1234</a:Address></a:EndpointReference>'
    '<d:Types>pub:Computer</d:Types><d:XAddrs>http://192.168.1.50:5357/1234</d:XAddrs><d:MetadataVersion>1</d:MetadataVersion>'
    '</d:ProbeMatch></d:ProbeMatches></s:Body></s:Envelope>')


class WsdTests(unittest.TestCase):
    def test_die_anfrage_ist_ein_probe_mit_eigener_kennung(self) -> None:
        a, b = gs.wsd_probe(), gs.wsd_probe()
        self.assertIn(b"discovery/Probe", a)
        self.assertNotEqual(a, b, "Jede Anfrage hat ihre eigene MessageID")
        self.assertIn(b"urn:uuid:abc", gs.wsd_probe("abc"))

    def test_die_antwort(self) -> None:
        self.assertEqual([gs.Geraet("192.168.1.50", "192.168.1.50", "wsd", 5357)],
                         gs.wsd_antwort_lesen(WSD_ANTWORT.encode(), "192.168.1.50"))

    def test_ohne_xaddrs_gilt_der_absender(self) -> None:
        ohne = WSD_ANTWORT.replace("<d:XAddrs>http://192.168.1.50:5357/1234</d:XAddrs>", "")
        self.assertEqual([gs.Geraet("10.9.9.9", "10.9.9.9", "wsd", 0)], gs.wsd_antwort_lesen(ohne.encode(), "10.9.9.9"))

    def test_kaputtes_und_fremdes(self) -> None:
        self.assertEqual([], gs.wsd_antwort_lesen(b"<kaputt", "1.2.3.4"))
        self.assertEqual([], gs.wsd_antwort_lesen(b"", ""))
        self.assertEqual([], gs.wsd_antwort_lesen(b"<a><b/></a>", "1.2.3.4"))


class UncTests(unittest.TestCase):
    def test_unc_anfang(self) -> None:
        self.assertEqual("\\\\192.168.1.20\\", gs.Geraet("NAS", "192.168.1.20", "smb", 445).unc)


class SuchenTests(unittest.TestCase):
    """``suchen`` mit zwei Antwortern auf der Loopback-Adresse statt der Multicast-Gruppen."""

    def _antworter(self, antwort: bytes) -> "tuple[socket.socket, threading.Thread]":
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        s.settimeout(3.0)

        def lauf() -> None:
            try:
                _daten, absender = s.recvfrom(65535)
                s.sendto(antwort, absender)
            except OSError:
                pass
        t = threading.Thread(target=lauf, daemon=True)
        t.start()
        return s, t

    def test_findet_ueber_beide_verfahren(self) -> None:
        s1, t1 = self._antworter(_smb_antwort("TestNAS", "testnas.local", "192.168.77.1", 445))
        s2, t2 = self._antworter(WSD_ANTWORT.encode())
        self.addCleanup(s1.close)
        self.addCleanup(s2.close)
        gemeldet: list = []
        gefunden = gs.suchen(1.0, schnittstellen=["127.0.0.1"], mdns_ziele=[s1.getsockname()], wsd_ziele=[s2.getsockname()],
                             melden=gemeldet.append)
        t1.join(2)
        t2.join(2)
        self.assertEqual({("TestNAS", "192.168.77.1", "smb"), ("192.168.1.50", "192.168.1.50", "wsd")},
                         {(g.name, g.adresse, g.art) for g in gefunden})
        self.assertEqual(2, len(gemeldet), "Jedes Geraet wird einmal gemeldet, sobald es auftaucht")

    def test_ohne_antwort_ist_die_liste_leer_und_es_endet(self) -> None:
        s, _t = self._antworter(b"")
        self.addCleanup(s.close)
        self.assertEqual([], gs.suchen(0.4, schnittstellen=["127.0.0.1"], mdns_ziele=[s.getsockname()], wsd_ziele=[s.getsockname()]))

    def test_abbruch_beendet_die_suche_sofort(self) -> None:
        import time
        s, _t = self._antworter(b"")
        self.addCleanup(s.close)
        t0 = time.monotonic()
        gs.suchen(30.0, schnittstellen=["127.0.0.1"], mdns_ziele=[s.getsockname()], wsd_ziele=[s.getsockname()], abbruch=lambda: True)
        self.assertLess(time.monotonic() - t0, 3.0)

    def test_doppelte_antworten_zaehlen_einmal(self) -> None:
        s1, t1 = self._antworter(_smb_antwort() + b"")
        self.addCleanup(s1.close)
        gefunden = gs.suchen(0.6, schnittstellen=["127.0.0.1", "127.0.0.1"], mdns_ziele=[s1.getsockname()], wsd_ziele=[s1.getsockname()])
        self.assertEqual(1, len(gefunden))

    def test_lokale_adressen_sind_keine_loopback_adressen(self) -> None:
        for adresse in gs.lokale_adressen():
            self.assertFalse(adresse.startswith("127."))


if __name__ == "__main__":
    unittest.main()
