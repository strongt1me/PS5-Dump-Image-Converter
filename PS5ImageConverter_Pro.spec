# -*- mode: python ; coding: utf-8 -*-
# PyInstaller .spec-Datei fuer PS5 Dump & Image Converter v1.8.61
# =========================================================
# Verwendung:
#   pyinstaller PS5ImageConverter_Pro.spec --clean
#
# Voraussetzungen (einmalig installieren):
#   pip install pyinstaller --upgrade
#   pip install pillow cryptography zstandard
#
# Alle Dateien muessen im selben Ordner liegen:
#   PS5ImageConverter_Pro_FINAL_revised.py
#   PS5ImageConverter_Pro.spec
#   app_icon.ico
#   splash_image.png  (optional, Splashscreen-Grafik)
#   helloworld/  (Ordner mit JS/ELF Dateien)
# =========================================================
import os
import glob

# Pfad zum Projektordner (relativ zur .spec-Datei)
_here = os.path.dirname(os.path.abspath(SPEC))
_mkpfs_roots = [
    _path
    for _path in glob.glob(os.path.join(_here, 'MkPFS-*'))
    if os.path.isdir(_path) and os.path.isfile(os.path.join(_path, 'mkpfs', '__init__.py'))
]

# Daten-Dateien die in die EXE eingebettet werden
_datas = [
    # app_icon.ico fuer Fenster-Icon zur Laufzeit
    (os.path.join(_here, 'app_icon.ico'), '.'),
]

# splash_image.png fuer den Splashscreen einbetten falls vorhanden
_splash_image = os.path.join(_here, 'splash_image.png')
if os.path.isfile(_splash_image):
    _datas.append((_splash_image, '.'))

# helloworld-Ordner einbetten (JS Loader Dateien)
_helloworld = os.path.join(_here, 'helloworld')
if os.path.isdir(_helloworld):
    _datas.append((_helloworld, 'helloworld'))

# ip.ini einbetten falls vorhanden
_ip_ini = os.path.join(_here, 'ip.ini')
if os.path.isfile(_ip_ini):
    _datas.append((_ip_ini, '.'))

# Lizenzen der mitgelieferten Fremdkomponenten einbetten. Die EXE enthaelt die
# Payloads aus helloworld/ - darunter zftpd unter MIT-Lizenz, die verlangt, dass
# der Lizenztext jeder Kopie beiliegt. Im Fenster CREDITS ist die Datei aufrufbar.
_third_party = os.path.join(_here, 'THIRD_PARTY_LICENSES.md')
if os.path.isfile(_third_party):
    _datas.append((_third_party, '.'))

# Benutzerhandbuch einbetten - der Knopf BENUTZERHANDBUCH in der Titelleiste
# oeffnet es. README.md und CHANGELOG.md kommen mit, weil das Handbuch auf beide
# verlinkt; ohne sie waeren das in der EXE tote Verweise.
for _doc in ('BENUTZERHANDBUCH.html', 'README.md', 'CHANGELOG.md'):
    _doc_pfad = os.path.join(_here, _doc)
    if os.path.isfile(_doc_pfad):
        _datas.append((_doc_pfad, '.'))

# MkPFS-Engine als Quellordner einbetten (z. B. MkPFS-0.0.9/)
for _mkpfs_src in _mkpfs_roots:
    _datas.append((_mkpfs_src, os.path.basename(_mkpfs_src)))

# Mitgelieferte AMPR-EMU-/PlayGo-Versionen einbetten. Dadurch steht der
# Versionsspeicher in Aufgabe 7 ohne manuelle Ordnerwahl bereit.
_ampr_store = os.path.join(_here, 'PlayGo & AMPR_EMU')
if os.path.isdir(_ampr_store):
    _datas.append((_ampr_store, 'PlayGo & AMPR_EMU'))

# Ersatzbibliotheken fuer den Backport einbetten (je Firmware ein Satz).
# Ohne sie startet ein herabgesetztes Spiel nicht: Es erwartet Bibliotheken,
# die es auf der aelteren Firmware nicht gibt.
_backport_libs = os.path.join(_here, 'Backport_Fakelibs')
if os.path.isdir(_backport_libs):
    _datas.append((_backport_libs, 'Backport_Fakelibs'))

# Mitgelieferte Hintergrundbilder einbetten (Auswahl im Design-Dialog).
_backgrounds = os.path.join(_here, 'Hintergrundbilder')
if os.path.isdir(_backgrounds):
    _datas.append((_backgrounds, 'Hintergrundbilder'))

# tkinterdnd2 (optionales Drag & Drop) bringt eigene, plattformspezifische
# Tcl/Tk-Bibliotheken mit (tkinterdnd2/tkdnd/<plattform>/). Der mitgelieferte
# PyInstaller-Community-Hook (hook-tkinterdnd2.py aus _pyinstaller_hooks_contrib)
# erkennt 'tkinterdnd2' automatisch ueber hiddenimports und sammelt NUR den
# passenden Plattformordner korrekt inklusive der nativen DLL/SO/DYLIB. Ein
# zusaetzlicher manueller collect_data_files('tkinterdnd2')-Aufruf hier wuerde
# ALLE Plattformordner (auch Linux/macOS) als reine "Daten" einsammeln und
# dabei mit dem Hook kollidieren - die fuer Windows tatsaechlich benoetigte
# tkdnd-DLL ging dadurch bei der Binaer-/Daten-Neuklassifizierung verloren,
# sodass 'tkinterdnd2.TkinterDnD.Tk()' beim Start mit "can't find package
# tkdnd" abstuerzte. Daher bewusst KEIN manueller collect_data_files-Aufruf.

a = Analysis(
    ['PS5ImageConverter_Pro_FINAL_revised.py'],
    pathex=[_here, *_mkpfs_roots],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        # Dynamisch importierte FFPKG-/UFS2Tool-v4.1-Ressource
        'ps5_ufs2tool_data',
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
        'ps5_validator.utils.ini_config',
        'ps5_validator.utils.pkg_writer',
        # dpi_upload bewusst NICHT gebuendelt: der etaHEN-"Direct Package
        # Installer V2" liess sich mangels laufendem Dienst nie erproben. Der
        # Quelltext samt Tests bleibt im Projekt, wandert aber nicht in die EXE.
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
        'ctypes.wintypes',
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
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    name='PS5_Dump_Image_Converter_v1.8.61',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[
        'vcruntime140.dll',
        'ucrtbase.dll',
        'python3*.dll',
    ],
    runtime_tmpdir=None,
    console=False,           # Kein Konsolenfenster
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',     # EXE-Symbol und Taskleisten-Symbol
    uac_admin=True,          # Administratorrechte anfordern (fuer OSFMount, Dokan)
    version='file_version_info.txt',
)
