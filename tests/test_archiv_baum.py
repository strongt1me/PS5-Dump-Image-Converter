# -*- coding: utf-8 -*-
"""``archiv_baum.ZipBaum``: ZIP-Archive als Lesebaum, ohne Entpacken (14.11.2026)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import archiv_baum as ab          # noqa: E402
from ps5_validator.utils import archiv_quelle as aq        # noqa: E402
from ps5_validator.utils.spielbaum import BaumFehler       # noqa: E402

PARAM = b'{"titleId": "PPSA12345"}'


def _inhalt(rel: str, n: int = 3000) -> bytes:
    return (rel.encode("utf-8") + b"|") * (n // (len(rel) + 1) + 1)


class _Ablage(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def zip(self, name: str = "spiel.zip", *, wurzel: str = "", verfahren: int = zipfile.ZIP_DEFLATED, extra: "dict | None" = None,
            leere_ordner: "tuple[str, ...]" = ()) -> str:
        pfad = self.dir / name
        dateien = {
            "eboot.bin": _inhalt("eboot.bin", 2000),
            "sce_sys/param.json": PARAM,
            "data/a.pak": _inhalt("a", 50000),
            "data/tief/b.pak": _inhalt("b", 7000),
            "leer.bin": b"",
        }
        dateien.update(extra or {})
        with zipfile.ZipFile(pfad, "w", compression=verfahren) as z:
            for rel, daten in dateien.items():
                z.writestr((wurzel + "/" if wurzel else "") + rel, daten)
            for o in leere_ordner:
                z.writestr(zipfile.ZipInfo((wurzel + "/" if wurzel else "") + o.rstrip("/") + "/"), b"")
        self.dateien = dateien
        return str(pfad)


class WurzelTests(unittest.TestCase):
    def test_am_stamm(self) -> None:
        self.assertEqual("", ab.spielwurzel_aus_namen(["eboot.bin", "sce_sys/param.json"]))

    def test_eine_ebene_tiefer_und_mit_backslash(self) -> None:
        self.assertEqual("Spiel", ab.spielwurzel_aus_namen(["Spiel/eboot.bin", "Spiel/sce_sys/param.json"]))
        self.assertEqual("Spiel", ab.spielwurzel_aus_namen(["Spiel\\sce_sys\\param.json"]))

    def test_der_flachste_gewinnt(self) -> None:
        self.assertEqual("A", ab.spielwurzel_aus_namen(["A/sce_sys/param.json", "A/Sicherung/B/sce_sys/param.json"]))

    def test_zu_tief_oder_nichts(self) -> None:
        self.assertIsNone(ab.spielwurzel_aus_namen(["a/b/c/d/sce_sys/param.json"]))
        self.assertIsNone(ab.spielwurzel_aus_namen(["readme.txt", "x/y.bin"]))

    def test_gross_klein_wie_beim_entpackten_ordner(self) -> None:
        self.assertEqual("S", ab.spielwurzel_aus_namen(["S/SCE_SYS/PARAM.JSON"]))


class ListeUndLesenTests(_Ablage):
    def test_dateien_nach_pfad_mit_groesse_und_inhalt(self) -> None:
        pfad = self.zip()
        with ab.ZipBaum(pfad) as baum:
            liste = baum.dateien()
            self.assertEqual(sorted(self.dateien), [d.rel for d in liste])
            for d in liste:
                self.assertEqual(len(self.dateien[d.rel]), d.groesse)
                self.assertEqual(self.dateien[d.rel], b"".join(d.lesen(1000)), d.rel)

    def test_alle_packverfahren(self) -> None:
        for verfahren in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            with self.subTest(verfahren=verfahren):
                pfad = self.zip("v%d.zip" % verfahren, verfahren=verfahren)
                with ab.ZipBaum(pfad) as baum:
                    d = baum.suchen()["data/a.pak"]
                    self.assertEqual(self.dateien["data/a.pak"], b"".join(d.lesen()))

    def test_spielordner_im_archiv_wird_zur_wurzel(self) -> None:
        pfad = self.zip(wurzel="Mein Spiel (1.00)", extra={"../ausserhalb.txt".replace("../", ""): b"egal"})
        with ab.ZipBaum(pfad) as baum:
            self.assertEqual("Mein Spiel (1.00)", baum.dateien() and baum.wurzel)
            self.assertIn("eboot.bin", baum.suchen())
            self.assertNotIn("Mein Spiel (1.00)/eboot.bin", baum.suchen())

    def test_dateien_ausserhalb_des_spielordners_zaehlen_nicht(self) -> None:
        pfad = self.dir / "z.zip"
        with zipfile.ZipFile(pfad, "w") as z:
            z.writestr("Spiel/eboot.bin", b"e")
            z.writestr("Spiel/sce_sys/param.json", PARAM)
            z.writestr("LIESMICH.txt", b"nicht ins Spiel")
        with ab.ZipBaum(str(pfad)) as baum:
            self.assertEqual(["eboot.bin", "sce_sys/param.json"], [d.rel for d in baum.dateien()])

    def test_leere_ordner_werden_gemerkt(self) -> None:
        pfad = self.zip(leere_ordner=("save/leer", "data/auch leer"))
        with ab.ZipBaum(pfad) as baum:
            self.assertIn("save/leer", baum.ordner())
            self.assertIn("data/auch leer", baum.ordner())

    def test_ignorierte_namen_fallen_weg(self) -> None:
        pfad = self.zip(extra={"Thumbs.db": b"x", "data/.DS_Store": b"y"})
        with ab.ZipBaum(pfad, ignoriert=lambda n: n in ("Thumbs.db", ".DS_Store")) as baum:
            rels = [d.rel for d in baum.dateien()]
            self.assertNotIn("Thumbs.db", rels)
            self.assertNotIn("data/.DS_Store", rels)

    def test_mehrere_faeden_lesen_zugleich(self) -> None:
        pfad = self.zip(extra={"gross.bin": os.urandom(400_000)})
        fehler: "list[str]" = []
        with ab.ZipBaum(pfad) as baum:
            alle = baum.dateien()

            def arbeit() -> None:
                for d in alle:
                    if b"".join(d.lesen(4096)) != self.dateien[d.rel]:
                        fehler.append(d.rel)
            faeden = [threading.Thread(target=arbeit) for _ in range(6)]
            for f in faeden:
                f.start()
            for f in faeden:
                f.join()
        self.assertEqual([], fehler)

    def test_stempel_und_unveraendert(self) -> None:
        pfad = self.zip()
        baum = ab.ZipBaum(pfad)
        self.addCleanup(baum.schliessen)
        baum.dateien()
        self.assertTrue(baum.unveraendert())
        self.assertEqual(baum.stempel(), baum.stempel())
        with open(pfad, "ab") as f:
            f.write(b"\0" * 10)
        self.assertFalse(baum.unveraendert())


class FehlerTests(_Ablage):
    def test_kein_spiel_im_archiv(self) -> None:
        pfad = self.dir / "k.zip"
        with zipfile.ZipFile(pfad, "w") as z:
            z.writestr("liesmich.txt", b"x")
        with self.assertRaises(BaumFehler):
            ab.ZipBaum(str(pfad)).dateien()

    def test_unzulaessiger_pfad(self) -> None:
        pfad = self.dir / "u.zip"
        with zipfile.ZipFile(pfad, "w") as z:
            z.writestr("sce_sys/param.json", PARAM)
            z.writestr("../raus.txt", b"x")
        with self.assertRaises(BaumFehler) as ctx:
            ab.ZipBaum(str(pfad)).dateien()
        self.assertIn("Unzulaessiger", str(ctx.exception))

    def test_absoluter_pfad_und_laufwerk(self) -> None:
        for name in ("/etc/x", "C:/x.txt", "\\\\server\\x"):
            with self.subTest(name=name):
                pfad = self.dir / "a.zip"
                with zipfile.ZipFile(pfad, "w") as z:
                    z.writestr("sce_sys/param.json", PARAM)
                    z.writestr(name, b"x")
                with self.assertRaises(BaumFehler):
                    ab.ZipBaum(str(pfad)).dateien()

    def test_kein_zip(self) -> None:
        pfad = self.dir / "kaputt.zip"
        pfad.write_bytes(b"das ist kein zip" * 20)
        with self.assertRaises(BaumFehler):
            ab.ZipBaum(str(pfad)).dateien()

    def test_fehlende_datei(self) -> None:
        with self.assertRaises(BaumFehler):
            ab.ZipBaum(str(self.dir / "gibtsnicht.zip"))

    def test_beschaedigter_inhalt_wird_beim_lesen_gemeldet(self) -> None:
        pfad = self.zip(verfahren=zipfile.ZIP_STORED)
        roh = bytearray(Path(pfad).read_bytes())
        i = roh.find(self.dateien["data/a.pak"][:40])
        self.assertGreater(i, 0)
        roh[i + 10] ^= 0xFF                                  # ein Byte im Inhalt kippen: die Pruefsumme stimmt nicht mehr
        Path(pfad).write_bytes(bytes(roh))
        with ab.ZipBaum(pfad) as baum:
            with self.assertRaises(BaumFehler):
                b"".join(baum.suchen()["data/a.pak"].lesen())

    def test_verweis_im_archiv_wird_uebersprungen(self) -> None:
        pfad = self.dir / "l.zip"
        with zipfile.ZipFile(pfad, "w") as z:
            z.writestr("eboot.bin", b"e")
            z.writestr("sce_sys/param.json", PARAM)
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "eboot.bin")
        with ab.ZipBaum(str(pfad)) as baum:
            self.assertNotIn("link", baum.suchen())
            self.assertEqual(["link"], baum.uebersprungen)


def _siebenzip() -> str:
    try:
        return aq.siebenzip_suchen()
    except Exception:  # noqa: BLE001
        return ""


@unittest.skipUnless(_siebenzip(), "7-Zip nicht gefunden")
class PasswortTests(_Ablage):
    """Verschluesselte ZIPs entstehen mit 7-Zip (``zipfile`` kann nur lesen): ZipCrypto, wie sie die Release-Seiten benutzen."""

    def _verschluesselt(self, passwort: str, methode: str = "ZipCrypto") -> str:
        quelle = self.dir / "quelle"
        (quelle / "sce_sys").mkdir(parents=True)
        (quelle / "eboot.bin").write_bytes(_inhalt("eboot.bin", 5000))
        (quelle / "sce_sys" / "param.json").write_bytes(PARAM)
        (quelle / "data").mkdir()
        (quelle / "data" / "a.pak").write_bytes(_inhalt("a", 40000))
        ziel = self.dir / "pw.zip"
        befehl = [_siebenzip(), "a", "-tzip", "-p" + passwort, "-mem=" + methode, "-y", str(ziel), "."]
        erg = subprocess.run(befehl, cwd=str(quelle), capture_output=True, text=True)
        if erg.returncode != 0 or not ziel.is_file():
            self.skipTest("7-Zip legt das Archiv nicht an: %s" % (erg.stdout or erg.stderr)[-200:])
        return str(ziel)

    def test_bekanntes_passwort_wird_gefunden(self) -> None:
        pfad = self._verschluesselt(aq.BEKANNTE_PASSWOERTER[0])
        with ab.ZipBaum(pfad) as baum:
            baum.dateien()
            self.assertEqual(aq.BEKANNTE_PASSWOERTER[0], baum.passwort)
            self.assertEqual(_inhalt("a", 40000), b"".join(baum.suchen()["data/a.pak"].lesen()))

    def test_weiteres_passwort_aus_der_liste(self) -> None:
        pfad = self._verschluesselt("mein-geheimnis")
        with ab.ZipBaum(pfad, weitere_passwoerter=["falsch", "mein-geheimnis"]) as baum:
            baum.dateien()
            self.assertEqual("mein-geheimnis", baum.passwort)

    def test_angegebenes_passwort_ersetzt_die_liste(self) -> None:
        pfad = self._verschluesselt(aq.BEKANNTE_PASSWOERTER[0])
        with ab.ZipBaum(pfad, passwort="falsch") as baum:
            with self.assertRaises(aq.PasswortFehler):
                baum.dateien()

    def test_kein_passwort_passt(self) -> None:
        pfad = self._verschluesselt("unbekannt-123")
        with ab.ZipBaum(pfad) as baum:
            with self.assertRaises(aq.PasswortFehler):
                baum.dateien()

    def test_aes_wird_abgelehnt_statt_falsch_gelesen(self) -> None:
        pfad = self._verschluesselt("geheim", methode="AES256")
        with ab.ZipBaum(pfad, passwort="geheim") as baum:
            with self.assertRaises(BaumFehler):
                baum.dateien()


if __name__ == "__main__":
    unittest.main()
