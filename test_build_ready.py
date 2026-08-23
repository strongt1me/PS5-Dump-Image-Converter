#!/usr/bin/env python3
"""
Build-Validierungstests für PS5ImageConverter
- Prüft ob PyInstaller das EXE bauen kann
- Validiert spec-Datei
- Prüft alle benötigten Daten-Dateien
"""

import os
import sys
import json
import subprocess
import unittest
from pathlib import Path

# UTF-8 Encoding für Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

# Unicode symbols with fallback for Windows
try:
    "[OK]".encode(sys.stdout.encoding)
    CHECK = "[OK]"
    CROSS = "[FAIL]"
except (UnicodeEncodeError, AttributeError):
    CHECK = "[+]"
    CROSS = "[x]"

def print_header(title):
    print(f"\n{BLUE}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{RESET}\n")

def test_pyinstaller_installed():
    print_header("TEST: PyInstaller Installation")
    try:
        result = subprocess.run(['pyinstaller', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  {GREEN}[OK]{RESET}  PyInstaller {version}")
            return True
        else:
            print(f"  {RED}[FAIL]{RESET}  PyInstaller nicht gefunden")
            return False
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET}  Fehler: {e}")
        return False

def _app_version() -> str:
    """Liest APP_VERSION aus der Hauptdatei.

    Frueher stand die Versionsnummer hier fest im Test und musste bei jedem
    Sprung von Hand nachgezogen werden - vergass man es, meldete der Test
    "Output-Dateiname fehlt", obwohl an der .spec nichts falsch war.
    """
    import re
    quelle = open('PS5ImageConverter_Pro_FINAL_revised.py', encoding='utf-8').read(20000)
    treffer = re.search(r'APP_VERSION\s*=\s*"(v[\d.]+)"', quelle)
    return treffer.group(1) if treffer else ''


def test_spec_file():
    print_header("TEST: Spec-Datei Validierung")
    
    spec_file = "PS5ImageConverter_Pro.spec"
    if not os.path.exists(spec_file):
        print(f"  {RED}[FAIL]{RESET}  {spec_file} nicht gefunden")
        return False
    
    try:
        with open(spec_file, 'r') as f:
            spec_content = f.read()
        
        # Prüfe auf kritische Elemente
        checks = [
            ('name=', 'Exe-Name'),
            ('datas=', 'Daten-Dateien'),
            ('hiddenimports=', 'Hidden Imports'),
            ('UFS2Tool-4.1', 'UFS2Tool-v4.1-Laufzeit je Plattform'),
            (f'PS5_Dump_Image_Converter_{_app_version()}', 'Output-Dateiname'),
        ]
        
        all_ok = True
        for pattern, desc in checks:
            if pattern in spec_content:
                print(f"  {GREEN}[OK]{RESET}  {desc}")
            else:
                print(f"  {RED}[FAIL]{RESET}  {desc} fehlt")
                all_ok = False
        
        return all_ok
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET}  Fehler beim Lesen: {e}")
        return False

def test_data_files():
    print_header("TEST: Daten-Dateien für Build")
    
    required_files = {
        'app_icon.ico': 'Anwendungsicon',
        'Build_EXE.ps1': 'Windows-Buildskript',
        'Start_Build.bat': 'Windows-Doppelklickstarter',
    }
    optional_files = {
        'helloworld/': 'Optionale Helloworld-Einbettung',
    }

    all_exist = True
    for file_path, description in required_files.items():
        exists = os.path.exists(file_path)
        status = f"{GREEN}[OK]{RESET}" if exists else f"{RED}[FAIL]{RESET}"
        size_info = ""

        if exists:
            if os.path.isfile(file_path):
                size_info = f" ({os.path.getsize(file_path):,} Bytes)"
            elif os.path.isdir(file_path):
                files = len(list(Path(file_path).rglob('*')))
                size_info = f" ({files} Dateien)"

        print(f"  {status}  {description:30} {file_path}{size_info}")
        all_exist = all_exist and exists

    for file_path, description in optional_files.items():
        exists = os.path.exists(file_path)
        status = f"{GREEN}[OK]{RESET}" if exists else f"{YELLOW}[i]{RESET}"
        print(f"  {status}  {description:30} {file_path}" + ("" if exists else " (nicht eingebettet)"))

    return all_exist

def test_windows_build_starter():
    print_header("TEST: Windows-Buildstarter")

    starter = Path('Start_Build.bat')
    if not starter.is_file():
        print(f"  {RED}[FAIL]{RESET}  Start_Build.bat nicht gefunden")
        return False

    try:
        content = starter.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        content = starter.read_text(encoding='cp1252')
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET}  Starter konnte nicht gelesen werden: {e}")
        return False

    required_tokens = ('powershell.exe', 'Build_EXE.ps1', 'exit /b %RC%')
    missing = [token for token in required_tokens if token.lower() not in content.lower()]
    if missing:
        print(f"  {RED}[FAIL]{RESET}  Starter unvollständig: {', '.join(missing)}")
        return False

    print(f"  {GREEN}[OK]{RESET}  Start_Build.bat ruft Build_EXE.ps1 kontrolliert auf")
    return True


def test_icon_format():
    print_header("TEST: Icon-Format Validierung")
    
    icon_file = 'app_icon.ico'
    try:
        with open(icon_file, 'rb') as f:
            header = f.read(4)
        
        # ICO-Dateien beginnen mit 00 00 01 00 (little-endian)
        if header == b'\x00\x00\x01\x00':
            size = os.path.getsize(icon_file)
            print(f"  {GREEN}[OK]{RESET}  Valides ICO-Format ({size:,} Bytes)")
            return True
        else:
            print(f"  {RED}[FAIL]{RESET}  Ungültiges ICO-Header")
            return False
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET}  Fehler: {e}")
        return False

def test_python_version():
    print_header("TEST: Python-Version Kompatibilität")
    
    py_version = sys.version_info
    version_str = f"{py_version.major}.{py_version.minor}.{py_version.micro}"
    
    # Python 3.8+ erforderlich für moderne Features
    if py_version.major >= 3 and py_version.minor >= 8:
        print(f"  {GREEN}[OK]{RESET}  Python {version_str}")
        return True
    else:
        print(f"  {RED}[FAIL]{RESET}  Python {version_str} zu alt (3.8+ erforderlich)")
        return False

def test_dependencies_frozen():
    print_header("TEST: Abhängigkeits-Versionen für Build")
    
    try:
        import PIL
        import cryptography
        import zstandard
        
        versions = {
            'Pillow': PIL.__version__,
            'cryptography': cryptography.__version__,
            'zstandard': zstandard.__version__,
        }
        
        print(f"  Installierte Versions-Snapshot:")
        for pkg, ver in versions.items():
            print(f"    - {pkg:20} {ver}")
        
        # Prüfe ob sie mit requirements.txt matchen
        with open('requirements.txt', 'r') as f:
            reqs = f.read()
        
        print(f"\n  requirements.txt Versionen:")
        for line in reqs.split('\n'):
            if line.strip() and not line.startswith('#'):
                print(f"    - {line.strip()}")
        
        print(f"\n  {GREEN}[OK]{RESET}  Abhängigkeiten sind installiert")
        return True
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET}  Fehler: {e}")
        return False

def test_output_directory():
    print_header("TEST: Build-Output-Verzeichnis")
    
    dist_dir = 'dist'
    build_dir = 'build'
    
    print(f"  Prüfe ob Output-Verzeichnisse leer sind (für sauberen Build):")
    
    results = []
    for dir_name in [dist_dir, build_dir]:
        if os.path.exists(dir_name):
            files = list(Path(dir_name).rglob('*'))
            file_count = len([f for f in files if f.is_file()])
            print(f"  {YELLOW}⚠{RESET}  {dir_name}/ existiert mit {file_count} Dateien (wird überschrieben)")
            results.append(True)  # Das ist OK, wird überschrieben
        else:
            print(f"  {GREEN}[OK]{RESET}  {dir_name}/ ist leer/neu")
            results.append(True)
    
    return all(results)

def main():
    print(f"\n{BLUE}{'='*60}")
    print("  PS5 IMAGE CONVERTER - BUILD-VALIDIERUNG")
    print(f"{'='*60}{RESET}\n")
    
    results = {}
    
    results['PyInstaller'] = test_pyinstaller_installed()
    results['SpecFile'] = test_spec_file()
    results['DataFiles'] = test_data_files()
    results['BuildStarter'] = test_windows_build_starter()
    results['IconFormat'] = test_icon_format()
    results['PythonVersion'] = test_python_version()
    results['Dependencies'] = test_dependencies_frozen()
    results['OutputDir'] = test_output_directory()
    
    # Zusammenfassung
    print_header("BUILD-READINESS ZUSAMMENFASSUNG")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = f"{GREEN}[OK]{RESET}" if result else f"{RED}[FAIL]{RESET}"
        print(f"  {status}  {test_name}")
    
    print(f"\n  {BLUE}Ergebnis:{RESET} {passed}/{total} Tests bestanden")
    
    if passed == total:
        print(f"\n  {GREEN}🔨 BUILD KANN GESTARTET WERDEN!{RESET}")
        print(f"  {BLUE}Befehl:{RESET} .\\Build_EXE.ps1\n")
        return 0
    else:
        print(f"\n  {RED}⚠  {total - passed} Voraussetzung(en) nicht erfüllt{RESET}\n")
        return 1


class VersionsstandTests(unittest.TestCase):
    """Die Versionsnummer steht an vier Stellen - sie muessen zusammenpassen.

    Am 22.08.2026 aufgefallen: Die fertige EXE meldete in ihren
    Dateieigenschaften **1.8.72.0**, waehrend das Programm v1.8.81 war.
    file_version_info.txt war neun Ausgaben lang nicht mitgezogen worden,
    und niemand hat es gemerkt - die Datei faellt nur auf, wenn man die
    Eigenschaften der EXE im Explorer aufschlaegt.

    Diese Datei war bis dahin ein reines Handskript ohne TestCase und
    lieferte unter "unittest discover" null Tests. Deshalb steht die
    Pruefung jetzt als richtige Testklasse hier.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.version = _app_version()          # z. B. "v1.8.81"
        cls.blank = cls.version.lstrip("v")   # z. B. "1.8.81"

    def test_die_hauptdatei_nennt_ueberhaupt_eine_version(self) -> None:
        self.assertRegex(self.version, r"^v\d+\.\d+\.\d+$")

    def test_die_spec_baut_den_passenden_namen(self) -> None:
        with open("PS5ImageConverter_Pro.spec", encoding="utf-8") as datei:
            inhalt = datei.read()
        self.assertIn("PS5_Dump_Image_Converter_%s" % self.version, inhalt,
                      "Der Zielname der .spec passt nicht zu APP_VERSION.")

    def test_die_versionsressource_haengt_nicht_zurueck(self) -> None:
        """Sonst zeigt Windows in den Dateieigenschaften etwas anderes an."""
        with open("file_version_info.txt", encoding="utf-8") as datei:
            inhalt = datei.read()
        vierstellig = self.blank + ".0"
        klammer = "(%s, 0)" % ", ".join(self.blank.split("."))
        self.assertIn(klammer, inhalt, "filevers/prodvers haengen zurueck.")
        self.assertIn("'FileVersion', '%s'" % vierstellig, inhalt)
        self.assertIn("'ProductVersion', '%s'" % vierstellig, inhalt)
        self.assertIn("PS5_Dump_Image_Converter_%s.exe" % self.version, inhalt)

    def test_das_bauskript_kennt_dieselbe_version(self) -> None:
        with open("Build_EXE.ps1", encoding="utf-8-sig") as datei:
            inhalt = datei.read()
        self.assertIn('$EXE_VERSION = "%s"' % self.version, inhalt)


class SpecDatenTests(unittest.TestCase):
    """Was die drei .spec-Dateien in ``datas`` legen - alle drei nachgesehen.

    Am 23.08.2026 an dist/PS5_Dump_Image_Converter_v1.8.93.exe gemessen: 48
    .pyc-Dateien lagen im Archiv, darunter pipeline.cpython-314.pyc aus
    PS4FFPFSC-0.2.8/ps4ffpsc/__pycache__/ - direkt neben pipeline.py. Bei
    (Ordner, Ziel) nimmt PyInstaller den ganzen Baum mit, __pycache__
    eingeschlossen. In jenem Bau war die .pyc aktuell; waere sie es nicht,
    liefe in der EXE eine aeltere Fassung des Moduls, waehrend der Quelltext
    daneben die neue zeigt - ein Fehler, der sich nur an der EXE zeigt und
    aus der Quelle nie nachstellbar waere.
    """

    SPECS = (
        'PS5ImageConverter_Pro.spec',
        'PS5ImageConverter_Pro_linux.spec',
        'PS5ImageConverter_Pro_macos.spec',
    )

    @staticmethod
    def _datas(spec: str) -> list:
        """Die .spec ausfuehren, mit Attrappen statt PyInstaller."""
        aufrufe: dict = {}

        class Ergebnis:
            def __getattr__(self, name):
                return '<%s>' % name

        class Attrappe:
            def __init__(self, name):
                self.name = name

            def __call__(self, *args, **kwargs):
                aufrufe.setdefault(self.name, []).append((args, kwargs))
                return Ergebnis()

        pfad = Path(spec).resolve()
        namensraum = {'SPEC': str(pfad), '__file__': str(pfad)}
        for name in ('Analysis', 'PYZ', 'EXE', 'COLLECT', 'BUNDLE'):
            namensraum[name] = Attrappe(name)
        quelle = pfad.read_text(encoding='utf-8')
        exec(compile(quelle, str(pfad), 'exec'), namensraum)
        return aufrufe['Analysis'][0][1]['datas']

    def test_kein_pycache_in_datas(self) -> None:
        for spec in self.SPECS:
            datas = self._datas(spec)
            self.assertTrue(datas, '%s: datas ist leer' % spec)
            for quelle, ziel in datas:
                with self.subTest(spec=spec, quelle=quelle):
                    pfad = Path(quelle).as_posix()
                    self.assertNotIn('__pycache__', pfad)
                    self.assertNotIn('__pycache__', Path(ziel).as_posix())
                    self.assertFalse(pfad.endswith(('.pyc', '.pyo')), pfad)

    def test_die_python_quellen_kommen_trotzdem_mit(self) -> None:
        """Der Filter darf nicht die .py-Dateien mit wegwerfen."""
        pflicht = (
            'PS4FFPFSC-0.2.8/ps4ffpsc/pipeline.py',
            'PS4FFPFSC-0.2.8/ps4ffpsc/inventory.py',
            'PS4FFPFSC-0.2.8/mkpfs_1_0_0/mkpfs/pfs.py',
            'MkPFS-0.0.9/mkpfs/pfs.py',
        )
        for spec in self.SPECS:
            quellen = {Path(q).as_posix() for q, _z in self._datas(spec)}
            for teil in pflicht:
                with self.subTest(spec=spec, datei=teil):
                    self.assertTrue(any(p.endswith(teil) for p in quellen),
                                    '%s fehlt in %s' % (teil, spec))

    def test_die_ziele_behalten_ihren_unterbau(self) -> None:
        """Datei fuer Datei einsammeln darf den Baum nicht flachklopfen."""
        for spec in self.SPECS:
            ziele = set()
            for quelle, ziel in self._datas(spec):
                if Path(quelle).as_posix().endswith('/ps4ffpsc/pipeline.py'):
                    ziele.add(Path(ziel).as_posix())
            self.assertIn('PS4FFPFSC-0.2.8/ps4ffpsc', ziele,
                          '%s: pipeline.py landet im falschen Ordner' % spec)


if __name__ == '__main__':
    sys.exit(main())

