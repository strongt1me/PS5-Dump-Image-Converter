# -*- mode: python ; coding: utf-8 -*-
# PyInstaller .spec-Datei fuer PS5 Dump & Image Converter - macOS-Fassung
# =========================================================
# Verwendung:
#   ./Build_macOS.sh          (empfohlen - prueft Abhaengigkeiten mit)
#   pyinstaller PS5ImageConverter_Pro_macos.spec --clean
#
# Voraussetzungen:
#   Python von python.org oder aus Homebrew - das mitgelieferte
#   /usr/bin/python3 bringt kein brauchbares Tcl/Tk mit.
#   pip: pyinstaller pillow cryptography zstandard
#
# Unterschiede zur Linux-Fassung (PS5ImageConverter_Pro_linux.spec):
#   - Ergebnis ist ein Programmbuendel (.app) statt einer einzelnen Datei. Das
#     ist unter macOS keine Geschmacksfrage: Nur ein Buendel bekommt ein Symbol
#     im Dock, einen eigenen Namen in der Menueleiste und eine Info.plist - und
#     nur ueber die Info.plist laesst sich dem System sagen, dass das Fenster in
#     echter Bildschirmaufloesung und im dunklen Erscheinungsbild zu zeichnen
#     ist.
#   - Deshalb COLLECT + BUNDLE statt einer Onefile-Datei. Eine Onefile-Datei
#     liesse sich zwar in ein Buendel legen, entpackt sich aber bei jedem Start
#     neu nach /var/folders; der Start dauert dann Sekunden statt Sekunden-
#     bruchteile, und die Signatur des Buendels sagt nichts mehr ueber das aus,
#     was tatsaechlich laeuft.
#   - icon=app_icon.icns: .ico und .png zeigt der Finder als leeres Blatt.
#
# Unterschiede zur Windows-Fassung (PS5ImageConverter_Pro.spec):
#   - kein version=/uac_admin=: reine Windows-Angaben.
#   - UFS2Tool liegt seit v1.8.72 als eigenstaendiger Bau je Plattform bei
#     Binaerdateien (UFS2Tool.exe, Dokan).
#   - Der Buendelname traegt keine Version, die Ordner unter dist/ dagegen
#     schon: Im Programme-Ordner soll ueber Updates hinweg derselbe Name
#     stehen, damit eine neue Fassung die alte ersetzt statt sich danebenzulegen.
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
    Version fest im Namen, was bei jedem Versionssprung nachgezogen werden
    muss. Fuer die macOS-Fassung genuegt eine Stelle.
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
# CFBundleShortVersionString erlaubt nur Ziffern und Punkte. Das fuehrende "v"
# aus APP_VERSION muss weg, sonst weist der Finder die Angabe still zurueck und
# zeigt im Informationsfenster gar keine Version an.
_plist_version = _version.lstrip('vV') or '0.0.0'
_arch = platform.machine() or 'x86_64'

#: Name der ausfuehrbaren Datei in Contents/MacOS/. Bewusst ohne Version: Der
#: Kommandozeilenaufruf (--cli) zeigt genau dorthin und soll ueber Updates
#: hinweg gleich bleiben.
_programmname = 'PS5_Dump_Image_Converter'
#: Name des Buendels im Finder und im Dock.
_buendelname = 'PS5 Dump & Image Converter'

#: Symbol des Buendels. Fehlt es, baut PyInstaller ohne Symbol weiter -
#: erzeugen laesst es sich jederzeit mit 'python extract_icon_icns.py'.
_icns = os.path.join(_here, 'app_icon.icns')

_mkpfs_roots = [
    _path
    for _path in glob.glob(os.path.join(_here, 'MkPFS-*'))
    if os.path.isdir(_path) and os.path.isfile(os.path.join(_path, 'mkpfs', '__init__.py'))
]

# Daten-Dateien die in das Programm eingebettet werden
_datas = [
    # app_icon.ico wird zur Laufzeit ueber Pillow gelesen und per iconphoto()
    # gesetzt - das ist das Symbol IM Fenster. Das Symbol DES Buendels im
    # Dock und im Finder ist eine andere Sache: Dafuer reicht PyInstaller
    # weiter unten app_icon.icns nach Contents/Resources durch.
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
# oeffnet es ueber open(1). README.md und CHANGELOG.md kommen mit, weil das
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
    for _ziel in ['osx-arm64', 'osx-x64']:
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
# macOS also tkdnd/osx-64/ bzw. osx-arm64/ samt libtkdnd*.dylib. Ein zusaetzlicher
# manueller
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
        # Dokan-Treiber, alle als Base64 hinterlegt. Unter macOS nicht
        # ausfuehrbar; die Aufrufwege dorthin steigen vorher mit einer
        # eindeutigen Meldung aus.
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    # True = die Bibliotheken wandern nicht in die Programmdatei, sondern
    # daneben. Genau das braucht ein Buendel: Contents/MacOS/ fuer das Programm,
    # Contents/Frameworks/ fuer alles Mitgelieferte.
    exclude_binaries=True,
    name=_programmname,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # False = kein Terminalfenster. Aus einer Shell gestartet landen Meldungen
    # weiterhin auf stdout/stderr; ueber den Finder gestartet bleibt es still.
    console=False,
    disable_windowed_traceback=False,
    # False, obwohl ein Buendel Dateien annehmen koennte: argv_emulation faengt
    # das Apple-Event "oeffne Dokument" mit einer eigenen Ereignisschleife ab,
    # bevor Tk seine eigene startet. Bei einem Tk-Programm bleibt das Fenster
    # danach bis zum ersten Klick taub. Dateien nimmt das Programm ohnehin ueber
    # seine eigenen Auswahldialoge und per Drag & Drop entgegen.
    argv_emulation=False,
    # None = fuer die Architektur bauen, auf der gebaut wird. 'universal2' setzt
    # voraus, dass jedes einzelne Rad (Pillow, cryptography, zstandard, zlib-ng)
    # als universal2 vorliegt; ein einziges ohne arm64-Anteil laesst den Bau
    # erst ganz am Ende scheitern.
    target_arch=None,
    # Die Signatur setzt Build_macOS.sh nachtraeglich ueber codesign: Sie muss
    # das fertige Buendel umfassen, PyInstaller signiert hier nur die einzelne
    # Programmdatei.
    codesign_identity=None,
    entitlements_file=None,
    icon=_icns if os.path.isfile(_icns) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    # Dieser Ordner ist das Zwischenergebnis, nicht das Auslieferungsstueck. Er
    # traegt Version und Architektur, damit mehrere Baustaende nebeneinander
    # liegen koennen, ohne sich zu ueberschreiben.
    name=f'{_programmname}_{_version}_macos_{_arch}',
)

app = BUNDLE(
    coll,
    name=f'{_buendelname}.app',
    icon=_icns if os.path.isfile(_icns) else None,
    bundle_identifier='com.jbuserc0re.ps5dumpimageconverter',
    version=_plist_version,
    info_plist={
        # CFBundleName steht in der Menueleiste neben dem Apfel. Apple empfiehlt
        # dort hoechstens 15 Zeichen; der volle Name steht im Finder darunter.
        'CFBundleName': 'PS5 Converter',
        'CFBundleDisplayName': _buendelname,
        'CFBundleShortVersionString': _plist_version,
        'CFBundleVersion': _plist_version,
        'CFBundleExecutable': _programmname,
        'CFBundlePackageType': 'APPL',
        'LSApplicationCategoryType': 'public.app-category.utilities',
        # Ohne diesen Eintrag zeichnet macOS das Fenster aus einem einfach
        # aufgeloesten Puffer in doppelter Groesse - auf jedem Retina-Bildschirm
        # sichtbar unscharf.
        'NSHighResolutionCapable': True,
        # False = das dunkle Erscheinungsbild des Systems gilt auch hier. Fehlt
        # der Eintrag, zwingt macOS aeltere Tk-Fassungen in das helle
        # Aqua-Aussehen; die hellen Systemleisten stossen sich dann mit dem
        # dunklen Design des Programms.
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '11.0',
        'NSHumanReadableCopyright': 'MIT License - PS5 Dump & Image Converter Contributors',
        # Kein CFBundleDocumentTypes: Ohne argv_emulation (siehe oben) bekommt
        # das Programm das Apple-Event zum Oeffnen einer Datei gar nicht zu
        # sehen. Eine Dateizuordnung anzumelden, die dann nichts tut, waere
        # schlechter als keine.
    },
)
