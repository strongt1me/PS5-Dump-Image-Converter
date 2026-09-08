# -*- mode: python ; coding: utf-8 -*-
# PyInstaller .spec-Datei fuer PS5 Dump & Image Converter v1.9.8
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

# Quellordner Datei fuer Datei einsammeln, ohne __pycache__.
# Bei (Ordner, Ziel) nimmt PyInstaller den ganzen Baum mit - also auch eine
# dort liegengebliebene .pyc. Im Buendel laege sie neben ihrer .py, und eine
# veraltete .pyc koennte eine aeltere Fassung des Moduls einschleusen,
# waehrend der Quelltext daneben die neue zeigt: ein Fehler, der sich nur an
# der EXE zeigt und aus der Quelle nie nachstellbar waere.
def _dateien_ohne_pycache(_quelle, _ziel, _ohne=()):
    """Sammelt einen Quellordner fuer die Einbettung.

    ``_ohne`` nennt Unterordner, die draussen bleiben - fuer MkPFS ist das
    ``tests``: Der Testbestand des Autors liegt seit dem 06.09.2026 daneben
    (425 KB) und gehoert in den Pruefstand, nicht in die Auslieferung.
    """
    _eintraege = []
    for _wurzel, _ordner, _dateien in os.walk(_quelle):
        _ordner[:] = [_o for _o in _ordner
                      if _o != '__pycache__' and _o not in _ohne]
        _rel = os.path.relpath(_wurzel, _quelle)
        _unterziel = _ziel if _rel == os.curdir else os.path.join(_ziel, _rel)
        for _datei in _dateien:
            if _datei.endswith(('.pyc', '.pyo')):
                continue
            _eintraege.append((os.path.join(_wurzel, _datei), _unterziel))
    return _eintraege

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

# Die Anleitungen zu den beiden ShadowMountPlus-Fassungen. Das Auswahlfenster
# hinter Knopf 7 oeffnet sie; ohne sie waeren die beiden Knoepfe dort leer.
_anleitungen = os.path.join(_here, 'Anleitungen')
if os.path.isdir(_anleitungen):
    _datas.append((_anleitungen, 'Anleitungen'))

# Der WebKit Autoloader: Host als Windows-Programm, derselbe als
# Python-Skript und der Installer-Payload. Der Ordner gehoert dem
# Benutzer - was darin liegt, wird eingebettet. Legt er eine neuere
# Fassung hinein, kommt sie beim naechsten Bau mit; das Programm sucht
# zur Laufzeit nach Muster und nimmt die hoechste Versionsnummer.
_webkit = os.path.join(_here, 'PS5 WebKit Autoloader')
if os.path.isdir(_webkit):
    _datas.append((_webkit, 'PS5 WebKit Autoloader'))

# Payload fuer die Direktinstallation einer Anwendung. Klein genug, um
# es immer mitzunehmen; ohne das ELF kann das Werkzeug die Kachel auf
# der Konsole nicht anmelden. appinst.c und NOTICE.md kommen mit, weil
# das Payload von GPL-3-Quellen abstammt.
_appinstall = os.path.join(_here, 'PS5-AppInstall')
if os.path.isdir(_appinstall):
    _datas.append((_appinstall, 'PS5-AppInstall'))

# MkPFS-Engine als Quellordner einbetten (z. B. MkPFS-1.0.0/)
for _mkpfs_src in _mkpfs_roots:
    _datas.extend(_dateien_ohne_pycache(_mkpfs_src,
                                        os.path.basename(_mkpfs_src),
                                        _ohne=('tests',)))

# ProsperoPkg 2.5 - das Werkzeug hinter "PKG bauen". Alle vier Bauten kommen
# mit: Das Programm waehlt zur Laufzeit nach Betriebssystem und Prozessor
# (prosperopkg.plattformordner()), und wer eine Datei weitergibt, soll sie
# nicht getrennt danebenlegen muessen. Zusammen rund 6 MB.
#
# Bis v1.9.2 stand ProsperoPkg in keiner .spec. Die fertige Datei fand das
# Werkzeug deshalb nur, wenn der Quellordner danebenlag - im Auslieferungs-
# buendel lief "PKG bauen" ins Leere.
_prosperopkg = os.path.join(_here, 'ProsperoPkg-2.5')
if os.path.isdir(_prosperopkg):
    # bin/ und obj/ bleiben draussen: Wer die C#-Quellen daneben einmal
    # uebersetzt, legt unter src/ProsperoPkgCli/ 89 MB .NET-Bauausgabe ab.
    # Der Ordner ist git-ignoriert, deshalb faellt das im Baum nicht auf -
    # in der fertigen Datei aber schon: Die Windows-Fassung wuchs dadurch
    # von 143 auf 182 MB, bemerkt am 06.09.2026 beim Groessenvergleich mit
    # der Vorversion. Gebraucht werden nur die vier fertigen Bauten
    # (linux-x64, osx-arm64, osx-x64, win-x64), zusammen 6 MB.
    _datas.extend(_dateien_ohne_pycache(_prosperopkg, 'ProsperoPkg-2.5',
                                        _ohne=('bin', 'obj')))

# Eingebettetes PS4-FFPFSC (PS4 PKG -> ffpfsc, siehe dort UPSTREAM.md).
# Der Ordner enthaelt neben dem Python-Teil die beiden nativen Helfer in bin/
# und die von diesem Werkzeug geprueften MkPFS-Quellen; die Qt-Oberflaeche der
# Vorlage ist bewusst nicht dabei.
_ps4ffpsc = os.path.join(_here, 'PS4FFPFSC-0.2.8')
if os.path.isdir(_ps4ffpsc):
    _datas.extend(_dateien_ohne_pycache(_ps4ffpsc, 'PS4FFPFSC-0.2.8'))

# UFS2Tool 4.1 fuer diese Plattform. Eigenstaendig gebaut (getrimmt,
# ohne Globalisierung), damit auf dem Zielrechner kein .NET 8
# installiert sein muss - der frueher eingebettete Windows-Bau war
# framework-abhaengig und scheiterte ohne .NET stillschweigend.
_ufs2tool = os.path.join(_here, 'UFS2Tool-4.1')
if os.path.isdir(_ufs2tool):
    for _beilage in ('LICENSE', 'pruefsummen.json'):
        _quelle = os.path.join(_ufs2tool, _beilage)
        if os.path.isfile(_quelle):
            _datas.append((_quelle, 'UFS2Tool-4.1'))
    for _ziel in ['win-x64']:
        _bau = os.path.join(_ufs2tool, _ziel)
        if os.path.isdir(_bau):
            _datas.append((_bau, os.path.join('UFS2Tool-4.1', _ziel)))

# Mitgelieferte AMPR-EMU-/PlayGo-Versionen einbetten. Dadurch steht der
# Versionsspeicher in Aufgabe 7 ohne manuelle Ordnerwahl bereit - und die
# Auslieferung bleibt eine einzige Datei.
#
# In v1.8.94 lag der Ordner daneben, damit sich eine neue AMPR-Fassung
# hineinlegen laesst, ohne neu zu bauen. Das wiegt den Nachteil nicht auf:
# Wer die EXE weitergibt oder verschiebt und den Ordner vergisst, hat in
# Aufgabe 7 keine einzige Version zur Auswahl, ohne dass die Ursache
# erkennbar waere. Ein eigener Ordner bleibt ueber die Ordnerwahl im
# AMPR-EMU-Manager weiterhin moeglich.
_ampr_store = os.path.join(_here, 'PlayGo & AMPR_EMU')
if os.path.isdir(_ampr_store):
    _datas.append((_ampr_store, 'PlayGo & AMPR_EMU'))

# Die Packwerkzeuge des AMPR EMU ("neue Methode"). Ohne sie faellt die
# Auswahl beim Erstellen sichtbar auf "Normal" zurueck - das Programm
# bleibt also benutzbar, aber die gepackten Baender liessen sich nicht
# bauen. Reiner Python-Quelltext, rund 0,4 MB.
_ampr_packtools = os.path.join(_here, 'AMPR_PackTools-4.0')
if os.path.isdir(_ampr_packtools):
    _datas.extend(_dateien_ohne_pycache(_ampr_packtools, 'AMPR_PackTools-4.0'))

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
        # Module, die das eingebettete PS4-Werkzeug (PS4FFPFSC-0.2.8) braucht.
        # Es liegt als Datenordner bei und wird erst zur Laufzeit ueber
        # sys.path geladen - PyInstaller sieht seine Importe deshalb nicht.
        # Ohne diese Liste bricht der interne Modus mit "No module named
        # 'tomllib'" ab (unter Linux nachgemessen; Windows haette denselben
        # Fehler gehabt, nur faellt er dort erst beim Klick auf).
        'tomllib',
        # LZ4 fuer das eingebettete AMPR-Packwerkzeug
        # (AMPR_PackTools-4.0/ampr_pack_format.py:987 importiert
        # lz4.block erst zur Laufzeit). Der Quelltext dieses Programms
        # importiert es nirgends unmittelbar - ohne diese Zeile findet
        # PyInstaller es nicht, und die neue AMPR-Methode faellt beim
        # Anwender auf 'Normal' zurueck, obwohl alles mitgeliefert ist.
        'lz4',
        'lz4.block',
        # Weitere Module, die ampr_pack.py und ampr_pack_format.py
        # brauchen. Sie liegen als Datenordner bei - PyInstaller liest
        # ihre Importe nicht.
        #
        # 'ctypes.util' hat es am 08.09.2026 beim Anwender zerlegt:
        # ctypes selbst ist eingebettet (samt _endian, _layout,
        # wintypes), das Untermodul util aber nicht - das zieht nur
        # herein, wer es ausdruecklich einbindet. Die neue Methode
        # brach damit sofort ab, sobald sie loslief.
        #
        # So wurde die Liste bestimmt: die Importe der beiden Dateien
        # einsammeln und gegen build/*/Analysis-00.toc halten. Von 23
        # gebrauchten Modulen fehlten genau diese vier. Bewacht von
        # test_ampr_assetpakete.EigenstaendigkeitTests.
        # Diese vier fehlten gemessen in der fertigen Datei.
        'array',
        'binascii',
        'ctypes.util',
        'math',
        # Diese beiden lagen nur zufaellig drin - ein anderes Modul
        # zog sie mit. Auf einen solchen Umweg sollte sich nichts
        # verlassen: Genau so war ctypes eingebettet und ctypes.util
        # trotzdem nicht da.
        'dataclasses',
        'fnmatch',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers',
        'zlib_ng',
        'zlib_ng.zlib_ng',
        'unicodedata',
        'contextvars',
        'concurrent.futures',
        # Dynamisch importierte FFPKG-/UFS2Tool-v4.1-Ressource
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
        'mkpfs.batch',
        'mkpfs.cli',
        'mkpfs.compression',
        'mkpfs.consts',
        'mkpfs.exfat',
        'mkpfs.exfat_writer',
        'mkpfs.gather',
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
    name='PS5_Dump_Image_Converter_v1.9.8',
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
