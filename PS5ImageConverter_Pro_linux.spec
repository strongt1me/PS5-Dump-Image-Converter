# -*- mode: python ; coding: utf-8 -*-
# PyInstaller .spec-Datei fuer PS5 Dump & Image Converter - Linux-Fassung
# =========================================================
# Verwendung:
#   ./Build_Linux.sh          (empfohlen - prueft Abhaengigkeiten mit)
#   pyinstaller PS5ImageConverter_Pro_linux.spec --clean
#
# Voraussetzungen:
#   Systempakete: python3-tk (Tcl/Tk), fontconfig
#   pip:          pyinstaller pillow cryptography zstandard
#
# Unterschiede zur Windows-Fassung (PS5ImageConverter_Pro.spec):
#   - kein icon=/version=/uac_admin=: Das sind reine Windows-Angaben. Das
#     Fenstersymbol setzt die Anwendung zur Laufzeit selbst ueber iconphoto().
#   - ohne ps5_ufs2tool_data: Dieses Modul enthaelt ausschliesslich Windows-
#     Binaerdateien (UFS2Tool.exe, Dokan). Unter Linux sind sie nicht
#     ausfuehrbar, wuerden das Ergebnis aber um rund ein Megabyte aufblaehen.
#   - ohne ctypes.wintypes: existiert unter Linux nicht.
#   - Der Dateiname traegt die Architektur, weil ein Linux-Programm im
#     Gegensatz zur .exe nicht ohne Weiteres auf andere Architekturen passt.
# =========================================================
import glob
import os
import platform
import re

# Pfad zum Projektordner (relativ zur .spec-Datei)
_here = os.path.dirname(os.path.abspath(SPEC))


def _app_version() -> str:
    """Liest APP_VERSION aus dem Hauptprogramm.

    Bewusst ausgelesen statt hier wiederholt: Die Windows-.spec traegt die
    Version fest im Namen, was bei jedem Versionssprung an drei Stellen
    nachgezogen werden muss. Fuer die Linux-Fassung genuegt eine Stelle.
    """
    quelle = os.path.join(_here, 'PS5ImageConverter_Pro_FINAL_revised.py')
    try:
        with open(quelle, 'r', encoding='utf-8') as datei:
            for zeile in datei:
                treffer = re.match(r'^APP_VERSION\s*=\s*["\'](.+?)["\']', zeile)
                if treffer:
                    return treffer.group(1)
    except OSError:
        pass
    return 'unbekannt'


_version = _app_version()
_arch = platform.machine() or 'x86_64'

_mkpfs_roots = [
    _path
    for _path in glob.glob(os.path.join(_here, 'MkPFS-*'))
    if os.path.isdir(_path) and os.path.isfile(os.path.join(_path, 'mkpfs', '__init__.py'))
]

# Daten-Dateien die in das Programm eingebettet werden
_datas = [
    # app_icon.ico wird zur Laufzeit ueber Pillow gelesen und per iconphoto()
    # gesetzt - unter Linux gibt es kein iconbitmap() fuer .ico-Dateien.
    (os.path.join(_here, 'app_icon.ico'), '.'),
]

# splash_image.png fuer den Splashscreen einbetten falls vorhanden
_splash_image = os.path.join(_here, 'splash_image.png')
if os.path.isfile(_splash_image):
    _datas.append((_splash_image, '.'))

# helloworld-Ordner einbetten (JS Loader Dateien). Die Nutzlasten laufen auf
# der PS5, nicht auf dem Rechner - sie werden hier also genauso gebraucht.
_helloworld = os.path.join(_here, 'helloworld')
if os.path.isdir(_helloworld):
    _datas.append((_helloworld, 'helloworld'))

# ip.ini einbetten falls vorhanden
_ip_ini = os.path.join(_here, 'ip.ini')
if os.path.isfile(_ip_ini):
    _datas.append((_ip_ini, '.'))

# Lizenzen der mitgelieferten Fremdkomponenten einbetten. Das Programm enthaelt
# die Payloads aus helloworld/ - darunter zftpd unter MIT-Lizenz, die verlangt,
# dass der Lizenztext jeder Kopie beiliegt. Im Fenster CREDITS ist die Datei
# aufrufbar. Unter Linux uebernimmt das die einzige Lizenzablage: Eine
# Registrierung wie in der Windows-Registry gibt es dort nicht.
_third_party = os.path.join(_here, 'THIRD_PARTY_LICENSES.md')
if os.path.isfile(_third_party):
    _datas.append((_third_party, '.'))

# Benutzerhandbuch einbetten - der Knopf BENUTZERHANDBUCH in der Titelleiste
# oeffnet es ueber xdg-open. README.md und CHANGELOG.md kommen mit, weil das
# Handbuch auf beide verlinkt.
for _doc in ('BENUTZERHANDBUCH.html', 'README.md', 'CHANGELOG.md'):
    _doc_pfad = os.path.join(_here, _doc)
    if os.path.isfile(_doc_pfad):
        _datas.append((_doc_pfad, '.'))

# MkPFS-Engine als Quellordner einbetten (z. B. MkPFS-0.0.9/)
for _mkpfs_src in _mkpfs_roots:
    _datas.append((_mkpfs_src, os.path.basename(_mkpfs_src)))

# Eingebettetes PS4-FFPFSC (PS4 PKG -> ffpfsc, siehe dort UPSTREAM.md).
# Der Ordner enthaelt neben dem Python-Teil die beiden nativen Helfer in bin/
# und die von diesem Werkzeug geprueften MkPFS-Quellen; die Qt-Oberflaeche der
# Vorlage ist bewusst nicht dabei.
_ps4ffpsc = os.path.join(_here, 'PS4FFPFSC-0.2.8')
if os.path.isdir(_ps4ffpsc):
    _datas.append((_ps4ffpsc, 'PS4FFPFSC-0.2.8'))

# Mitgelieferte AMPR-EMU-/PlayGo-Versionen einbetten.
_ampr_store = os.path.join(_here, 'PlayGo & AMPR_EMU')
if os.path.isdir(_ampr_store):
    _datas.append((_ampr_store, 'PlayGo & AMPR_EMU'))

# Ersatzbibliotheken fuer den Backport einbetten (je Firmware ein Satz).
_backport_libs = os.path.join(_here, 'Backport_Fakelibs')
if os.path.isdir(_backport_libs):
    _datas.append((_backport_libs, 'Backport_Fakelibs'))

# Mitgelieferte Hintergrundbilder einbetten (Auswahl im Design-Dialog).
_backgrounds = os.path.join(_here, 'Hintergrundbilder')
if os.path.isdir(_backgrounds):
    _datas.append((_backgrounds, 'Hintergrundbilder'))

# tkinterdnd2 (optionales Drag & Drop) bringt eigene, plattformspezifische
# Tcl/Tk-Bibliotheken mit (tkinterdnd2/tkdnd/<plattform>/). Der mitgelieferte
# PyInstaller-Community-Hook sammelt NUR den passenden Plattformordner - unter
# Linux also tkdnd/linux-x64/ samt libtkdnd*.so. Ein zusaetzlicher manueller
# collect_data_files('tkinterdnd2')-Aufruf wuerde damit kollidieren; deshalb
# bewusst keiner (siehe ausfuehrliche Begruendung in der Windows-.spec).

a = Analysis(
    ['PS5ImageConverter_Pro_FINAL_revised.py'],
    pathex=[_here, *_mkpfs_roots],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'tomllib',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers',
        'zlib_ng',
        'zlib_ng.zlib_ng',
        'unicodedata',
        'contextvars',
        'concurrent.futures',
        # Dynamisch importierter FFPKG-Validatorpfad
        'ps5_validator',
        'ps5_validator.core',
        'ps5_validator.core.dispatcher',
        'ps5_validator.core.validator_base',
        'ps5_validator.modules',
        'ps5_validator.modules.ffpkg_validator',
        'ps5_validator.modules.dump_validator',
        'ps5_validator.modules.extfat_validator',
        'ps5_validator.modules.ffpfs_validator',
        'ps5_validator.utils',
        'ps5_validator.utils.ffpkg_support',
        'ps5_validator.utils.file_io',
        'ps5_validator.utils.hashing',
        'ps5_validator.utils.logger',
        'ps5_validator.utils.pkg_reader',
        'ps5_validator.utils.pkg_merger',
        'ps5_validator.utils.gp5_project',
        'ps5_validator.utils.param_manifest',
        'ps5_validator.utils.dump_rename',
        'ps5_validator.utils.i18n',
        'ps5_validator.utils.anzeige_diagnose',
        'ps5_validator.utils.aktualisierungen',
        'ps5_validator.utils.ini_config',
        'ps5_validator.utils.pkg_writer',
        # Betriebssystem-Abstraktion (Schriften, Rechte, Dateien oeffnen)
        'ps5_validator.utils.plattform',
        # dpi_upload bewusst NICHT gebuendelt - wie in der Windows-.spec.
        'ps5_validator.utils.self_reader',
        'ps5_validator.utils.ps5_downloads',
        'ps5_validator.utils.ps5_backport',
        # Tkinter
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.simpledialog',
        # Optionales Drag & Drop (Quelle/Ziel/Temp)
        'tkinterdnd2',
        # Optionale Live-Systemtelemetrie (CPU/RAM) waehrend laufender Aufgaben
        'psutil',
        # Pillow
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        # Bruecke zwischen Pillow und Tcl/Tk. Sie wird nur zur Laufzeit aus
        # ImageTk heraus geladen, taucht also in keiner Importkette auf.
        # Ohne diesen Eintrag baut das Programm anstandslos und stuerzt beim
        # ersten Bild im Fenster ab: "No module named 'PIL._tkinter_finder'",
        # gefolgt von 'invalid command name "PyImagingPhoto"'. Unter Windows
        # loest der mitgelieferte PyInstaller-Hook das von selbst.
        'PIL._tkinter_finder',
        'PIL.ImageDraw',
        'PIL.ImageFilter',
        'PIL.ImageFont',
        'PIL.FpxImagePlugin',
        'PIL.MicImagePlugin',
        # Multiprocessing
        'multiprocessing',
        'multiprocessing.pool',
        # Stdlib
        'threading',
        'queue',
        'io',
        'base64',
        'tempfile',
        'subprocess',
        'pathlib',
        'struct',
        'hashlib',
        'zipfile',
        'shutil',
        'ctypes',
        'argparse',
        'datetime',
        'lzma',
        'pkgutil',
        'uuid',
        'zlib',
        'json',
        'logging',
        're',
        'os',
        'sys',
        'time',
        'urllib',
        'urllib.request',
        'urllib.parse',
        'webbrowser',
        'ftplib',
        'socket',
        'ssl',
        'stat',
        'http.server',
        'http.client',
        'email.utils',
        # Drittanbieter
        'cryptography',
        'cryptography.hazmat',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.primitives.hashes',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.backends.openssl',
        'zstandard',
        # Vendorte MkPFS-Module fuer Analyse/Packaging explizit bekanntmachen
        'mkpfs',
        'mkpfs.ampr',
        'mkpfs.cli',
        'mkpfs.consts',
        'mkpfs.exfat',
        'mkpfs.exfat_writer',
        'mkpfs.logging',
        'mkpfs.pbar',
        'mkpfs.pfs',
        'mkpfs.utils',
        'bcrypt',
        'nacl',
        'nacl.bindings',
        'nacl.public',
        'nacl.signing',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PyQt5',
        'PyQt6',
        'wx',
        'gi',
        # Reine Windows-Nutzlast: UFS2Tool.exe, dessen Laufzeit und der
        # Dokan-Treiber, alle als Base64 hinterlegt. Unter Linux nicht
        # ausfuehrbar; die Aufrufwege dorthin steigen vorher mit einer
        # eindeutigen Meldung aus.
        'ps5_ufs2tool_data',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'PS5_Dump_Image_Converter_{_version}_linux_{_arch}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # False = kein Terminalfenster. Startet man das Programm aus einer Shell,
    # landen Meldungen weiterhin auf stdout/stderr; ueber den Menueeintrag
    # gestartet bleibt es still.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
