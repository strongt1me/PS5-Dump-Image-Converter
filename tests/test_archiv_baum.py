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
import zlib
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

    def test_nur_ganze_pfadteile(self) -> None:
        """R5-4: ``alt_sce_sys/param.json`` endet zwar auf ``sce_sys/param.json``, ist aber kein Spiel."""
        self.assertIsNone(ab.spielwurzel_aus_namen(["alt_sce_sys/param.json"]))
        self.assertIsNone(ab.spielwurzel_aus_namen(["Spiel/Kopie_sce_sys/param.json"]))
        self.assertEqual("B", ab.spielwurzel_aus_namen(["A/alt_sce_sys/param.json", "B/sce_sys/param.json"]))
        self.assertEqual("", ab.spielwurzel_aus_namen(["/sce_sys/param.json"]), "Gegenprobe: am Stamm mit fuehrendem Strich")

    def test_ein_dlc_ordner_ist_nicht_das_spiel(self) -> None:
        """R2-P5: ``EP9000-...-ac`` sortiert vor ``PPSA01234-app`` - mit eigener param.json wurde er "das Spiel"."""
        dlc = "EP9000-PPSA01234_00-ABCDEFGHIJKLMNOP-ac"
        namen = [dlc + "/sce_sys/param.json", "PPSA01234-app/sce_sys/param.json", "PPSA01234-app/eboot.bin"]
        self.assertEqual("PPSA01234-app", ab.spielwurzel_aus_namen(namen))
        self.assertEqual(dlc, ab.spielwurzel_aus_namen([dlc + "/sce_sys/param.json"]), "Gegenprobe: allein ist er der Treffer")

    def test_ein_dlc_ordner_ist_nicht_das_spiel_auch_entpackt(self) -> None:
        import tempfile as tf
        with tf.TemporaryDirectory() as t:
            for name in ("EP9000-PPSA01234_00-ABCDEFGHIJKLMNOP-ac", "PPSA01234-app"):
                Path(t, name, "sce_sys").mkdir(parents=True)
                Path(t, name, "sce_sys", "param.json").write_bytes(PARAM)
            Path(t, "liesmich.txt").write_bytes(b"x")
            self.assertEqual(os.path.join(t, "PPSA01234-app"), aq.spielwurzel(t))

    def test_ein_dlc_ordner_in_einem_geschwisterordner_ist_nicht_das_spiel(self) -> None:
        """R3-A2: Die Tiefensuche nahm den ersten Treffer - ``A_DLC/EP...-ac`` vor ``Z_Spiel/PPSA...-app``. Wie beim ZIP: das Spiel."""
        import tempfile as tf
        dlc = "EP9000-PPSA01234_00-ABCDEFGHIJKLMNOP-ac"
        with tf.TemporaryDirectory() as t:
            for rel in ("A_DLC/" + dlc, "Z_Spiel/PPSA01234-app"):
                Path(t, *rel.split("/"), "sce_sys").mkdir(parents=True)
                Path(t, *rel.split("/"), "sce_sys", "param.json").write_bytes(PARAM)
            Path(t, "liesmich.txt").write_bytes(b"x")
            self.assertEqual(os.path.join(t, "Z_Spiel", "PPSA01234-app"), aq.spielwurzel(t))
            self.assertEqual("Z_Spiel/PPSA01234-app", ab.spielwurzel_aus_namen(
                ["A_DLC/%s/sce_sys/param.json" % dlc, "Z_Spiel/PPSA01234-app/sce_sys/param.json"]), "beide Wege gleich")

    def test_entpackt_und_zip_waehlen_gleich_bei_aehnlichen_namen(self) -> None:
        """R4-1: Mit "\\" sortiert "Games\\..." nach "Games2\\..." - mit "/" davor. Beide Wege muessen dasselbe Spiel nehmen."""
        import tempfile as tf
        with tf.TemporaryDirectory() as t:
            for rel in ("Games/PPSA01234", "Games2/PPSA05678"):
                Path(t, *rel.split("/"), "sce_sys").mkdir(parents=True)
                Path(t, *rel.split("/"), "sce_sys", "param.json").write_bytes(PARAM)
            Path(t, "liesmich.txt").write_bytes(b"x")
            zip_wahl = ab.spielwurzel_aus_namen(["Games/PPSA01234/sce_sys/param.json", "Games2/PPSA05678/sce_sys/param.json"])
            self.assertEqual("Games/PPSA01234", zip_wahl)
            self.assertEqual(os.path.join(t, "Games", "PPSA01234"), aq.spielwurzel(t))

    def test_der_flachste_gewinnt_auch_entpackt(self) -> None:
        """Gegenprobe: Ein Spiel eine Ebene tiefer schlaegt eines zwei Ebenen tiefer; ein Spiel in einem Spiel zaehlt nicht."""
        import tempfile as tf
        with tf.TemporaryDirectory() as t:
            for rel in ("A/B/Tief", "Z_Flach", "Z_Flach/Sicherung/Kopie"):
                Path(t, *rel.split("/"), "sce_sys").mkdir(parents=True)
                Path(t, *rel.split("/"), "sce_sys", "param.json").write_bytes(PARAM)
            Path(t, "liesmich.txt").write_bytes(b"x")
            self.assertEqual(os.path.join(t, "Z_Flach"), aq.spielwurzel(t))


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

    def test_aes_zip_entpackt_7zip(self) -> None:
        """Gesamtpruefung 14.11.2026, A6: ``zipfile`` kann AES nicht - bis dahin war ein solches ZIP nie entpackbar."""
        pfad = self._verschluesselt("geheim", methode="AES256")
        self.assertTrue(aq.zip_ist_aes(pfad))
        ziel = self.dir / "aus_aes"
        wurzel = aq.entpacken(pfad, str(ziel), passwort="geheim")
        self.assertEqual(_inhalt("a", 40000), Path(wurzel, "data", "a.pak").read_bytes())

    def test_zipcrypto_mit_deflate64_und_ppmd_entpackt_7zip(self) -> None:
        """Gesamtpruefung 14.11.2026, R2-P1: ``zipfile`` kann diese Verfahren nicht - das richtige Passwort galt als falsch."""
        for verfahren in ("Deflate64", "PPMd"):
            with self.subTest(verfahren=verfahren):
                quelle = self.dir / ("q_" + verfahren) / "Spiel"
                (quelle / "sce_sys").mkdir(parents=True)
                (quelle / "sce_sys" / "param.json").write_bytes(PARAM)
                (quelle / "eboot.bin").write_bytes(_inhalt("eboot.bin", 20000))
                archiv = self.dir / ("spiel_%s.zip" % verfahren)
                erg = subprocess.run([_siebenzip(), "a", "-tzip", "-pgeheim123", "-mem=ZipCrypto", "-mm=" + verfahren, str(archiv), "Spiel"],
                                     cwd=str(quelle.parent), capture_output=True, text=True)
                if erg.returncode != 0:
                    self.skipTest("7-Zip legt %s nicht an" % verfahren)
                self.assertTrue(aq.zip_braucht_7zip(str(archiv)))
                wurzel = aq.entpacken(str(archiv), str(self.dir / ("aus_" + verfahren)), passwort="geheim123")
                self.assertEqual(_inhalt("eboot.bin", 20000), Path(wurzel, "eboot.bin").read_bytes())

    def test_gegenprobe_deflate_bleibt_bei_zipfile(self) -> None:
        self.assertFalse(aq.zip_braucht_7zip(self._verschluesselt("x")))

    def _eine_datei_verschluesselt(self, passwort: str) -> str:
        """Spiel unverschluesselt, nur ``data/a.pak`` mit ZipCrypto (7-Zip fuegt sie mit -p hinzu): Jede Passwortprobe trifft diese Datei."""
        klar, geheim = self.dir / "klar", self.dir / "geheim"
        (klar / "sce_sys").mkdir(parents=True)
        (klar / "eboot.bin").write_bytes(_inhalt("eboot.bin", 5000))
        (klar / "sce_sys" / "param.json").write_bytes(PARAM)
        (geheim / "data").mkdir(parents=True)
        (geheim / "data" / "a.pak").write_bytes(_inhalt("a", 40000))
        ziel = self.dir / "teilweise.zip"
        for ordner, extra in ((klar, []), (geheim, ["-p" + passwort, "-mem=ZipCrypto"])):
            erg = subprocess.run([_siebenzip(), "a", "-tzip", *extra, "-y", str(ziel), "."], cwd=str(ordner),
                                 capture_output=True, text=True)
            if erg.returncode != 0:
                self.skipTest("7-Zip legt das Archiv nicht an: %s" % (erg.stdout or erg.stderr)[-200:])
        return str(ziel)

    def _falsch_mit_pruefbyte(self, pfad: str) -> str:
        """Ein falsches Passwort, das das Pruefbyte von ZipCrypto trifft (1 von 256) und beim Lesen ``zlib.error`` ausloest."""
        with zipfile.ZipFile(pfad) as z:
            info = next(i for i in z.infolist() if i.flag_bits & 0x1 and i.file_size)
            for n in range(20000):
                kandidat = "falsch%05d" % n
                try:
                    with z.open(info, pwd=kandidat.encode()) as q:
                        q.read()
                except RuntimeError:                                    # "Bad password": am Pruefbyte erkannt
                    continue
                except zlib.error:                                      # genau der gesuchte Fall
                    return kandidat
                except Exception:  # noqa: BLE001 - etwa eine falsche Pruefsumme: weiter suchen
                    continue
        self.skipTest("kein falsches Passwort mit passendem Pruefbyte gefunden")
        return ""

    def test_falsches_passwort_mit_passendem_pruefbyte_bricht_die_liste_nicht_ab(self) -> None:
        """Gesamtpruefung 14.11.2026, A2: Bis dahin entkam zlib.error, und das richtige Passwort dahinter kam nie dran."""
        pfad = self._eine_datei_verschluesselt("mein-geheimnis")
        falsch = self._falsch_mit_pruefbyte(pfad)
        with ab.ZipBaum(pfad, weitere_passwoerter=[falsch, "mein-geheimnis"]) as baum:
            baum.dateien()
            self.assertEqual("mein-geheimnis", baum.passwort)
        wurzel = aq.entpacken(pfad, str(self.dir / "aus"), weitere_passwoerter=[falsch, "mein-geheimnis"])
        self.assertEqual(_inhalt("a", 40000), Path(wurzel, "data", "a.pak").read_bytes())
        with self.assertRaises(aq.PasswortFehler):                     # allein ist es einfach falsch, kein anderer Fehler
            aq.entpacken(pfad, str(self.dir / "aus2"), passwort=falsch)


class UnzulaessigeNamenTests(_Ablage):
    """Gesamtpruefung 14.11.2026, A1: Ein Laufwerk mitten im Pfad ("Game/sce_sys/D:/PS5/x") fuehrte unter Windows heraus."""

    @unittest.skipUnless(os.name == "nt", "nur unter Windows macht os.path.join aus 'D:' ein Laufwerk")
    def test_doppelpunkt_in_jedem_teil(self) -> None:
        for name in ("Game/sce_sys/D:/PS5/x", "Game/D:", "data/datei.bin:strom", "C:x"):
            with self.subTest(name=name):
                self.assertTrue(ab._ist_unzulaessig(name))
        pfad = self.zip(extra={"sce_sys/D:/PS5/x": b"x"})
        with ab.ZipBaum(pfad) as baum:
            with self.assertRaises(BaumFehler):
                baum.dateien()

    def test_gewoehnliche_namen_bleiben_erlaubt(self) -> None:
        for name in ("Game/sce_sys/param.json", "a/b c/d.e", "eboot.bin"):
            with self.subTest(name=name):
                self.assertFalse(ab._ist_unzulaessig(name))
        for name in ("../x", "a/../../x", "/abs/x", "\\abs\\x"):
            with self.subTest(name=name):
                self.assertTrue(ab._ist_unzulaessig(name))

    def test_pfad_im_ordner(self) -> None:
        wurzel = str(self.dir / "schatten")
        self.assertEqual(os.path.join(wurzel, "sce_sys", "param.json"), ab.pfad_im_ordner(wurzel, "sce_sys/param.json"))
        for name in ("../aussen.bin", "a/../../aussen.bin") + (("sce_sys/D:/PS5/x",) if os.name == "nt" else ()):
            with self.subTest(name=name):
                with self.assertRaises(BaumFehler):
                    ab.pfad_im_ordner(wurzel, name)


if __name__ == "__main__":
    unittest.main()
