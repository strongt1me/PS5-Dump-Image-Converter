"""Gezielte Regressionstests für die UFS2-basierten FFPKG-Buildhilfen."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

#: Der Projektstamm - von hier aus liegt der Referenzordner mit den
#: Fremdwerkzeugen, deren Quelltext einzelne Aussagen belegt.
PROJEKT_WURZEL = Path(__file__).resolve().parent

from ps5_validator.utils.ffpkg_support import (
    FfpkgBuildProfile,
    FfpkgNewfsProfile,
    build_makefs_command,
    build_newfs_directory_command,
    build_readonly_validation_commands,
    calculate_makefs_image_size,
    calculate_makefs_inode_density,
    compatibility_newfs_profile,
    default_build_profile,
    normalize_output_path,
    primary_newfs_profile,
    validate_source_folder,
)


class FfpkgBuildSupportTests(unittest.TestCase):
    def test_default_profile_is_valid_and_conservative(self) -> None:
        profile = default_build_profile()
        self.assertEqual(profile.block_size, 65536)
        self.assertEqual(profile.fragment_size, 65536)
        self.assertEqual(profile.sector_size, 4096)
        self.assertEqual(profile.min_free_percent, 0)
        self.assertEqual(profile.inode_density, 65536)

    def test_beide_profile_fuehren_dieselbe_sektorgroesse(self) -> None:
        """4096 gilt fuer jeden Weg, der ein einhaengbares Abbild ausliefert.

        Bis v1.9.5 stand im makefs-Profil 512 und im newfs-Profil 4096. Wer
        die beiden Wege vergleicht, sucht den Grund fuer den Unterschied -
        und es gibt keinen: ShadowMount+ haengt UFS mit
        ``lvd_ufs_sector_size=4096`` ein, gleich womit gebaut wurde.
        """
        self.assertEqual(default_build_profile().sector_size,
                         primary_newfs_profile().sector_size)

    def test_invalid_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            FfpkgBuildProfile(block_size=12345).normalized()
        with self.assertRaises(ValueError):
            FfpkgBuildProfile(fragment_size=1024, block_size=4096, sector_size=777).normalized()
        with self.assertRaises(ValueError):
            FfpkgNewfsProfile("invalid", 65536, 4096).normalized()

    def test_primary_newfs_command_matches_64k_reference_profile(self) -> None:
        """``-S 4096``, nicht 512.

        ShadowMount+ haengt UFS-Abbilder ueber sein Standard-Backend LVD mit
        4096-Byte-Sektoren ein und empfiehlt genau diesen Befehl. Bis v1.9.5
        baute dieses Projekt mit 512; ein so gebautes .ffpkg hing an echter
        Hardware sauber ein - fsck fehlerfrei, Dateizahl bestaetigt - und der
        Titel stuerzte eine Sekunde nach dem Start ab (04.09.2026 gemessen).
        Dasselbe Spiel als exFAT-in-.ffpfsc lief.

        **Nachtrag 05.09.2026 - der Absturz lag nicht am Abbild.** Die
        Anleitung von 1.7alpha13 erklaert das Konsolenprotokoll woertlich:
        "When crash monitoring detects an app crash before kstuff was paused,
        ShadowMountPlus only notifies that the app crashed." Es ist ein
        Startzeitproblem; dafuer gibt es kstuff_pause_delay_image_seconds
        (Vorgabe 25 s), kstuff_delay je Titel, autopause.txt und autotune.ini.
        Die Sektorgroesse 4096 bleibt trotzdem richtig - mkufs2.sh benutzt
        genau diesen Befehl.

        **Zweiter Nachtrag desselben Tages:** Das Abbild war nach der
        Umstellung sogar byteweise dasselbe. UFS2Tool rechnet jedes ``-S``
        ungleich 512 vor dem Schreiben zurueck; die Aenderung von 512 auf
        4096 konnte den Absturz also gar nicht beeinflussen. Belegt in
        ``SektorgroesseIstFolgenlosTests`` am Quelltext des Werkzeugs.
        """
        profile = primary_newfs_profile()
        self.assertEqual(profile.identifier, "newfs-64k-reference")
        command = build_newfs_directory_command(
            "C:/Tools/UFS2Tool.exe",
            "C:/Source/Game",
            "C:/Out/Game",
            profile=profile,
        )
        self.assertEqual(
            command,
            [
                "C:/Tools/UFS2Tool.exe",
                "newfs",
                "-O",
                "2",
                "-b",
                "65536",
                "-f",
                "65536",
                "-S",
                "4096",
                "-m",
                "0",
                "-i",
                "262144",
                "-D",
                "C:/Source/Game",
                "C:/Out/Game.ffpkg",
            ],
        )

    def test_die_inode_dichte_bleibt_fest_bei_262144(self) -> None:
        """Sie an die Dateizahl anzupassen waere die naheliegende Verbesserung.

        Sie ist es nicht. Am 05.09.2026 durchgerechnet und am echten
        UFS2Tool-4.1 (linux-x64, WSL) nachgemessen:

        ``Ufs2ImageCreator.cs`` Z. 694-702 klemmt die **letzte** Cylinder Group
        nicht. Faellt sie kuerzer aus als ``dblkno`` (= 4 + ipg/256), wird
        ``dataFragsInCg`` negativ, wandert ungeprueft in ``cs_nbfree`` und
        ``superblock.FreeBlocks`` - und die Inodetabelle der letzten Gruppe
        landet jenseits des deklarierten Abbildendes. Ein **kleineres** ``-i``
        erhoeht ``ipg`` und damit ``dblkno`` (262144 -> ipg 512, dblkno 6;
        65536 -> ipg 1792, dblkno 11) und macht genau das wahrscheinlicher.

        Gemessen, zweimal dieselbe Quelle (2000 Dateien in 501 Ordnern):
        mit ``-i 262144`` ein 160-MiB-Abbild, 5 Gruppen a 512 Inoden; mit
        ``-i 65536`` ein 256-MiB-Abbild - 60 Prozent groesser. Bei 1000
        Dateien a 1 KiB *sinkt* die Inode-Kapazitaet von 1536 auf 1280.

        Ueber 30 Kombinationen (50 bis 6002 Dateien, 200 MB bis 8 GB) ist mit
        262144 **keine** betroffen; das gemessene Abbild PPSA19015 (191
        Dateien, 648 MB) hat in der letzten Gruppe 161 Fragmente bei dblkno 6.

        Wer die Dichte doch anpassen will, braucht vorher eine Absicherung
        gegen die letzte Cylinder Group - eine Rechnung aus Dateizahl und
        *geschaetzter* Groesse genuegt nicht: Ein einziges Fragment Abweichung
        (65536 Byte, 0,02 Prozent) kippt die Gruppenzahl.
        """
        self.assertEqual(262144, primary_newfs_profile().inode_density)
        # Und die Begruendung muss am Profil stehen, nicht nur hier.
        import inspect

        from ps5_validator.utils import ffpkg_support

        text = inspect.getdoc(ffpkg_support.primary_newfs_profile) or ""
        self.assertIn("Cylinder Group", text,
                      "Die Begruendung fehlt am Profil - dann senkt sie der "
                      "naechste Leser wieder.")

    def test_compatibility_newfs_command_matches_32k_4k_reference_profile(self) -> None:
        """Kleinerer Block und kleineres Fragment - aber dieselbe Sektorgroesse.

        Das Kompatibilitaetsprofil weicht bewusst bei Block (32 KiB) und
        Fragment (4 KiB) ab; die Sektorgroesse gehoert nicht dazu. Sie stand
        hier bis v1.9.5 auf 512, waehrend das Hauptprofil daneben 4096 fuehrte
        - ohne dass ein Grund fuer den Unterschied genannt war.
        """
        profile = compatibility_newfs_profile()
        self.assertEqual(profile.identifier, "newfs-32k-4k-compatibility")
        command = build_newfs_directory_command(
            "C:/Tools/UFS2Tool.exe",
            "C:/Source/Game",
            "C:/Out/Game",
            profile=profile,
        )
        self.assertEqual(
            command,
            [
                "C:/Tools/UFS2Tool.exe",
                "newfs",
                "-O",
                "2",
                "-b",
                "32768",
                "-f",
                "4096",
                "-S",
                "4096",
                "-D",
                "C:/Source/Game",
                "C:/Out/Game.ffpkg",
            ],
        )
        self.assertNotIn("-m", command)
        self.assertNotIn("-i", command)

    def test_makefs_size_uses_headroom_metadata_reserve_and_block_alignment(self) -> None:
        profile = default_build_profile()
        source_bytes = 648_398_581
        file_count = 15_001
        image_size = calculate_makefs_image_size(source_bytes, file_count, profile)
        self.assertGreaterEqual(
            image_size,
            source_bytes
            + file_count * (profile.fragment_size - 1)
            + 128 * 1024 * 1024
            + file_count * 16 * 1024,
        )
        self.assertEqual(image_size % profile.block_size, 0)

    def test_makefs_size_accounts_for_many_tiny_files(self) -> None:
        profile = default_build_profile()
        source_bytes = 5000 * 64
        file_count = 5000
        image_size = calculate_makefs_image_size(source_bytes, file_count, profile)
        previous_underestimate = source_bytes + 128 * 1024 * 1024 + file_count * 16 * 1024
        self.assertGreater(image_size, previous_underestimate + 300 * 1024 * 1024)
        self.assertGreaterEqual(
            image_size,
            source_bytes + file_count * (profile.fragment_size - 1),
        )

    def test_makefs_inode_density_reserves_entries(self) -> None:
        image_size = calculate_makefs_image_size(648_398_581, 15_000)
        density = calculate_makefs_inode_density(image_size, 15_000)
        self.assertGreaterEqual(density, 4096)
        self.assertLessEqual(density, default_build_profile().inode_density)
        self.assertGreaterEqual(image_size // density, 15_000 * 2 + 2048)

    def test_makefs_command_uses_explicit_ufs2_geometry(self) -> None:
        command = build_makefs_command(
            "C:/Tools/UFS2Tool.exe",
            "C:/Source/Game",
            "C:/Out/Game",
            source_size_bytes=648_398_581,
            file_count=200,
        )
        self.assertEqual(command[0:4], ["C:/Tools/UFS2Tool.exe", "makefs", "-t", "ffs"])
        self.assertIn("-s", command)
        self.assertIn("-o", command)
        options = command[command.index("-o") + 1]
        self.assertIn("version=2", options)
        self.assertIn("bsize=65536", options)
        self.assertIn("fsize=65536", options)
        self.assertIn("density=", options)
        self.assertIn("optimization=time", options)
        self.assertEqual(command[-2], "C:/Out/Game.ffpkg")
        self.assertEqual(command[-1], "C:/Source/Game")
        self.assertNotIn("newfs", command)
        self.assertNotIn("-D", command)
        self.assertNotIn("fsck_ufs", command)

    def test_output_path_requires_ffpkg_extension(self) -> None:
        self.assertEqual(normalize_output_path("out/game").name, "game.ffpkg")
        self.assertEqual(normalize_output_path("out/GAME.FFPKG").suffix, ".FFPKG")
        with self.assertRaises(ValueError):
            normalize_output_path(".ffpkg")

    def test_source_validation_counts_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "dump"
            nested = root / "nested"
            nested.mkdir(parents=True)
            (root / "a.bin").write_bytes(b"abc")
            (nested / "b.bin").write_bytes(b"12345")
            self.assertEqual(validate_source_folder(root), (2, 8))

    def test_empty_source_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "dump"
            root.mkdir()
            with self.assertRaises(ValueError):
                validate_source_folder(root)

            target = Path(temp_dir) / "payload.bin"
            target.write_bytes(b"payload")
            (root / "linked.bin").symlink_to(target)
            with self.assertRaises(ValueError):
                validate_source_folder(root)

    def test_validation_commands_are_read_only(self) -> None:
        info, fsck = build_readonly_validation_commands("UFS2Tool.exe", "game.ffpkg")
        self.assertEqual(info, ["UFS2Tool.exe", "info", "game.ffpkg"])
        self.assertEqual(fsck, ["UFS2Tool.exe", "fsck_ufs", "-fn", "game.ffpkg"])
        self.assertNotIn("-y", fsck)
        self.assertNotIn("--repair", fsck)


class SektorgroesseIstFolgenlosTests(unittest.TestCase):
    """``-S 4096`` ist richtig, aber beim Bau mit UFS2Tool ohne Wirkung.

    Am 04.09.2026 wurde die Sektorgroesse von 512 auf 4096 gestellt, in der
    Annahme, das behebe den Konsolenfehler CE-108-255-1. Das war nicht belegt
    und ist falsch: UFS2Tool rechnet jedes ``-S`` ungleich 512 vor dem
    Schreiben zurueck. Ein mit 4096 gebautes Abbild ist byteweise dasselbe
    wie eines mit 512 - die Aenderung kann den Fehler weder ausgeloest noch
    behoben haben.

    Geprueft wird das am mitgelieferten Quelltext des Werkzeugs, nicht an
    einem eigenen Bau: UFS2Tool verlangt erhoehte Rechte, ein Lauf aus der
    Pruefreihe heraus endet mit "Der angeforderte Vorgang erfordert erhoehte
    Rechte".

    **Der Wert bleibt trotzdem auf 4096.** Er entspricht der Anleitung von
    ShadowMount+ und wirkt, sobald jemand mit dem echten ``newfs`` oder
    ``makefs`` baut - so macht es ShadowMount+ in seinem eigenen
    ``mkufs2.sh``.
    """

    QUELLE = (PROJEKT_WURZEL / "PS5 SDK usw" / "UFS2TOOL" / "UFS2Tool-4.1"
              / "UFS2Tool-4.1")

    def setUp(self) -> None:
        if not self.QUELLE.is_dir():
            self.skipTest("UFS2Tool-Quelltext liegt nicht im Referenzordner")

    def test_ufs2tool_rechnet_die_sektorgroesse_zurueck(self) -> None:
        datei = self.QUELLE / "Ufs2ImageCreator.cs"
        if not datei.is_file():
            self.skipTest("Ufs2ImageCreator.cs fehlt")
        text = datei.read_text(encoding="utf-8", errors="replace")
        self.assertIn("NormalizeSectorSizeForLayout", text,
                      "Die Normalisierung gibt es nicht mehr - dann ist die "
                      "Aussage im Docstring von primary_newfs_profile neu zu "
                      "pruefen.")
        self.assertIn("SectorSize = Ufs2Constants.DefaultSectorSize", text,
                      "Der Ruecksetzer auf 512 ist weg - die Sektorgroesse "
                      "koennte jetzt doch wirken.")

    def test_das_werkzeug_bewacht_die_bytegleichheit_selbst(self) -> None:
        datei = self.QUELLE / "UFS2Tool.Tests" / "SectorSizeNormalizationTests.cs"
        if not datei.is_file():
            self.skipTest("SectorSizeNormalizationTests.cs fehlt")
        text = datei.read_text(encoding="utf-8", errors="replace")
        self.assertIn("DifferentSectorSizesProduceIdenticalLayout", text)
        # Der Waechter vergleicht ausdruecklich 4096 gegen 512.
        self.assertIn("sectorSize: 4096", text)
        self.assertIn("sectorSize: 512", text)

    def test_der_newfs_weg_uebergibt_keine_groesse(self) -> None:
        """Nur mit ``-s`` haette die Sektorgroesse ueberhaupt eine Wirkung.

        ``NormalizeSectorSizeForLayout`` multipliziert ``SizeOverride`` mit
        ``SectorSize / 512``. Dieser Weg uebergibt kein ``-s``, also bleibt
        der Wert 0 und die Multiplikation folgenlos.
        """
        command = build_newfs_directory_command(
            "UFS2Tool.exe", "C:/Quelle", "C:/Ziel",
            profile=primary_newfs_profile())
        self.assertNotIn("-s", command,
                         "Mit einer Groesse waere die Sektorgroesse nicht "
                         "mehr folgenlos - der Docstring muesste nachgezogen "
                         "werden.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
