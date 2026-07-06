# -*- mode: python ; coding: utf-8 -*-
# PyInstaller .spec-Datei fuer PS5 Dump & Image Converter v1.7.78
# =========================================================
# Verwendung:
#   pyinstaller PS5ImageConverter_Pro.spec --clean
#
# Voraussetzungen (einmalig installieren):
#   pip install pyinstaller --upgrade
#   pip install pillow cryptography zstandard paramiko
#
# Alle Dateien muessen im selben Ordner liegen:
#   PS5ImageConverter_Pro_FINAL_revised.py
#   PS5ImageConverter_Pro.spec
#   app_icon.ico
#   helloworld/  (Ordner mit JS/ELF Dateien)
# =========================================================
import os
import glob

# Pfad zum Projektordner (relativ zur .spec-Datei)
_here = os.path.dirname(os.path.abspath(SPEC))

# Daten-Dateien die in die EXE eingebettet werden
_datas = [
    # app_icon.ico fuer Fenster-Icon zur Laufzeit
    (os.path.join(_here, 'app_icon.ico'), '.'),
]

# helloworld-Ordner einbetten (JS Loader Dateien)
_helloworld = os.path.join(_here, 'helloworld')
if os.path.isdir(_helloworld):
    _datas.append((_helloworld, 'helloworld'))

# ip.ini einbetten falls vorhanden
_ip_ini = os.path.join(_here, 'ip.ini')
if os.path.isfile(_ip_ini):
    _datas.append((_ip_ini, '.'))

# MkPFS-Engine als Quellordner einbetten (z. B. MkPFS-0.0.9/)
for _mkpfs_src in glob.glob(os.path.join(_here, 'MkPFS-*')):
    if os.path.isdir(_mkpfs_src) and os.path.isfile(os.path.join(_mkpfs_src, 'mkpfs', '__init__.py')):
        _datas.append((_mkpfs_src, os.path.basename(_mkpfs_src)))

a = Analysis(
    ['PS5ImageConverter_Pro_FINAL_revised.py'],
    pathex=[_here],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        # Tkinter
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.simpledialog',
        # Pillow
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageDraw',
        'PIL.ImageFilter',
        'PIL.ImageFont',
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
        # paramiko (SFTP-Unterstuetzung im FTP-Client)
        'paramiko',
        'paramiko.transport',
        'paramiko.sftp_client',
        'paramiko.sftp_file',
        'paramiko.rsakey',
        'paramiko.ecdsakey',
        'paramiko.ed25519key',
        'paramiko.hostkeys',
        'paramiko.auth_handler',
        'paramiko.channel',
        'paramiko.client',
        'paramiko.compress',
        'paramiko.config',
        'paramiko.file',
        'paramiko.kex_curve25519',
        'paramiko.kex_ecdh_nist',
        'paramiko.kex_gex',
        'paramiko.kex_group14',
        'paramiko.kex_group16',
        'paramiko.message',
        'paramiko.packet',
        'paramiko.pipe',
        'paramiko.pkey',
        'paramiko.proxy',
        'paramiko.server',
        'paramiko.sftp',
        'paramiko.sftp_attr',
        'paramiko.sftp_handle',
        'paramiko.sftp_server',
        'paramiko.ssh_exception',
        'paramiko.util',
        'paramiko.win_pageant',
        'paramiko.win_openssh',
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
    name='PS5_Dump_Image_Converter_v1.7.78',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    version_file=None,
)
