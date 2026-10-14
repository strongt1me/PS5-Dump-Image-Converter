# -*- coding: utf-8 -*-
"""Tests fuer ``ps5_validator.utils.werkzeug_updates`` - den Knopf „Updates“ auf der Seite „Konsole & Payloads“.

Ohne Netz: Das Urteil steckt in reinen Funktionen, das Holen laeuft ueber eine Nachbildung von ``Netz``
(``FakeNetz``). Die Freigaben (``RELEASES``) sind die gekuerzten Antworten von GitHub und Codeberg vom
10.10.2026; die Dateinamen (``HELLOWORLD``, ``WEBKIT``) der Stand des Ordners am selben Tag. Beides ist **fest**:
Die Tests pruefen die Regeln, nicht den Stand des Ordners - tauscht jemand eine ELF aus, bleibt der Test gruen.
Was am echten Ordner gemessen wird, ist unabhaengig von Fassungen: dass **jede** Datei einen Eintrag hat, jeder
Eintrag eine Datei und jede mitgelieferte Fassung lesbar ist (``AbdeckungTests``).

Drei Dinge, an denen das Verfahren haengt, sind hier eigens belegt:

* die **Zielnamen** (``ziel``) ergeben fuer die heutige Freigabe genau die heutigen Dateinamen - sonst gaelte
  jede Datei als „neu“ oder liesse sich nach dem Holen nicht mehr finden;
* **nichts wird ohne Pruefung abgelegt** (Groesse, SHA-256, Adresse, Zielname) und ein mehrteiliges Werkzeug kommt
  ganz oder gar nicht;
* die **Anfragegrenze** von GitHub (60 je Stunde) wird mit ETag und Zwischenspeicher eingehalten.
"""
from __future__ import annotations

import email.message
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import werkzeug_updates as wu   # noqa: E402

# ---------------------------------------------------------------------------
# Die festen Daten
# ---------------------------------------------------------------------------
#: Quelle -> Freigaben, neueste zuerst: (Marke, Vorabfassung, Datum, Anhangsnamen).
#: Gekuerzt aus den Antworten vom 10.10.2026 (die obersten drei Freigaben, bei sehr vielen Anhaengen nur die
#: passenden und ein paar, die nicht passen duerfen).
RELEASES = {
    'ps5-payload-dev/ftpsrv': [
        ('v0.21.1', False, '2026-08-20', ['ftpsrv-ps4.elf', 'ftpsrv-ps5-install.elf', 'ftpsrv-ps5.elf']),
        ('v0.21', False, '2026-08-02', ['ftpsrv-ps4.elf', 'ftpsrv-ps5-install.elf', 'ftpsrv-ps5.elf']),
        ('v0.20', False, '2026-05-12', ['ftpsrv-ps4.elf', 'ftpsrv-ps5-install.elf', 'ftpsrv-ps5.elf']),
    ],
    'ps5-payload-dev/klogsrv': [
        ('v0.9', False, '2026-08-02', ['klogsrv-ps4.elf', 'klogsrv-ps5.elf']),
        ('v0.8', False, '2026-05-12', ['klogsrv-ps4.elf', 'klogsrv-ps5.elf']),
    ],
    'ps5-payload-dev/websrv': [
        ('v0.34', False, '2026-08-02', ['OffAct.zip', 'PKGInstall.zip', 'websrv-ps5.elf']),
        ('v0.33', False, '2026-06-28', ['OffAct.zip', 'PKGInstall.zip', 'websrv-ps5.elf']),
    ],
    'ps5-payload-dev/elfldr': [
        ('v0.26', False, '2026-08-29', ['elfldr-ps5.elf']),
        ('v0.25', False, '2026-08-22', ['elfldr-ps5.elf']),
    ],
    'ps5-payload-dev/offact': [
        ('v0.4.2', False, '2025-06-28', ['OffAct.zip']),
        ('v0.4.1', False, '2025-06-23', ['OffAct.zip']),
    ],
    'ps5-payload-dev/shsrv': [
        ('v0.20', False, '2026-08-02', ['shsrv-ps5.elf']),
        ('v0.19', False, '2026-06-28', ['shsrv-ps5.elf']),
    ],
    'ps5-payload-dev/gdbsrv': [
        ('v0.9', False, '2026-08-02', ['gdbsrv-ps4.elf', 'gdbsrv-ps5.elf']),
        ('v0.8', False, '2026-05-12', ['gdbsrv-ps4.elf', 'gdbsrv-ps5.elf']),
    ],
    'owendswang/ps5-web-file-manager': [
        ('v1.10', False, '2026-10-05', ['web-file-mgr-v1.10.elf', 'wfm-7zip-helper.elf']),
        ('v1.9', False, '2026-09-16', ['web-file-mgr-v1.9.elf', 'wfm-7zip-helper.elf']),
    ],
    'itsPLK/ps5-pkg-manager': [
        ('v1.5.0', False, '2026-10-08', ['pkg-manager_v1.5.0.elf']),
        ('v1.4.1', False, '2026-09-27', ['pkg-manager_v1.4.1.elf']),
    ],
    'itsPLK/ps5-payload-manager': [
        ('v0.6.0', False, '2026-10-13', ['pldmgr_v0.6.0.elf']),
        ('v0.5.2', False, '2026-09-29', ['pldmgr_v0.5.2.elf']),
        ('v0.5.1', False, '2026-08-02', ['pldmgr_v0.5.1.elf']),
    ],
    'phantomptr/ps5upload': [
        ('v6.7.3', False, '2026-10-09', ['latest.json', 'PS5Upload-6.7.3-win-x64.zip', 'ps5upload-6.7.3.elf',
                                         'ps5upload-engine-6.7.3-windows-x64.exe']),
        ('v6.7.2', True, '2026-10-09', ['latest.json', 'PS5Upload-6.7.2-win-x64.zip', 'ps5upload-6.7.2.elf',
                                        'ps5upload-engine-6.7.2-windows-x64.exe']),
        ('v6.7.1', False, '2026-10-09', ['latest.json', 'PS5Upload-6.7.1-win-x64.zip', 'ps5upload-6.7.1.elf',
                                         'ps5upload-engine-6.7.1-windows-x64.exe']),
    ],
    'EchoStretch/ps5-app-dumper': [
        ('v2.10', False, '2026-10-03', ['ps5-app-dumper_v2.10.elf', 'webhb-0.4.1.tar.gz',
                                        'webhb-0.4.1.tar.gz.sha256']),
        ('v2.00', False, '2026-09-29', ['ps5-app-dumper_v2.00.elf', 'webhb-0.4.1.tar.gz']),
        ('v1.11', False, '2026-07-28', ['ps5-app-dumper.elf']),
    ],
    'EchoStretch/dump_installer': [
        ('1.07', False, '2026-07-12', ['dump_installer.zip']),
        ('1.06', False, '2026-06-08', ['dump_installer.zip']),
    ],
    'drakmor/ShadowMountPlus': [
        ('1.7beta4', True, '2026-10-03', ['shadowmountplus.elf', 'ShadowMountPlus_1.7beta4.zip']),
        ('1.7beta3', False, '2026-10-01', ['shadowmountplus.elf', 'ShadowMountPlus_1.7beta3.zip']),
        ('1.7beta2', False, '2026-09-21', ['shadowmountplus.elf', 'ShadowMountPlus_1.7beta2.zip']),
    ],
    'drakmor/pgo_stub': [
        ('0.6', False, '2026-10-10', ['libScePlayGo.sprx', 'libScePlayGo_log.sprx']),
        ('0.5', True, '2026-07-02', ['pgo_stub_0.5.zip']),
    ],
    'drakmor/nanoDNS': [
        ('0.4', False, '2026-08-04', ['nanodns-ps4.elf', 'nanodns.elf']),
        ('0.3', False, '2026-06-03', ['nanodns-ps4.elf', 'nanodns.elf']),
    ],
    'seregonwar/zftpd': [
        ('v1.6.0', False, '2026-09-30', ['SHA256SUMS.txt', 'zftpd-ps4-v1.6.0.elf', 'zftpd-ps5-v1.6.0.bin',
                                         'zftpd-ps5-v1.6.0.elf', 'zftpd-ps5-zhttp-v1.6.0.bin',
                                         'zftpd-ps5-zhttp-v1.6.0.elf']),
        ('v1.5.0', False, '2026-06-14', ['zftpd-ps4-v1.5.0.elf', 'zftpd-ps5-v1.5.0.bin', 'zftpd-ps5-v1.5.0.elf',
                                         'zftpd-ps5-zhttp-v1.5.0.bin', 'zftpd-ps5-zhttp-v1.5.0.elf']),
    ],
    'Pharaoh2k/ps5debug-NG': [
        ('1.3.2', False, '2026-09-23', ['ps5debug-NG_v1.3.2.elf']),
        ('1.3.0', False, '2026-06-21', ['ps5debug-NG_v1.3.0.elf']),
    ],
    'EchoStretch/kstuff-lite': [
        ('v1.11', False, '2026-09-20', ['kstuff.elf']),
        ('v1.10', False, '2026-08-12', ['kstuff.elf']),
    ],
    'notmaj0r/ProsperoMgr': [
        ('v1.1', False, '2026-09-28', ['ProsperoMgr.elf']),
        ('beta', True, '2026-08-25', ['ProsperoMgr.elf']),
    ],
    'strongt1me/ps5-cooling-system-center-pro': [
        ('v1.56.0', False, '2026-10-10', ['cooling-center-launcher-installer_v1.56.0.elf',
                                          'IV9999-PSCC69690_00-PS5COOLINGCNTR01-A0100-V0100.pkg', 'LIESMICH.txt',
                                          'PS5_Cooling_System_Center_v1.56.0.elf']),
        ('v1.55.0', False, '2026-10-09', ['cooling-center-launcher-installer_v1.55.0.elf', 'LIESMICH.txt',
                                          'PS5_Cooling_System_Center_v1.55.0.elf']),
    ],
    'itsPLK/ps5-webkit-autoloader': [
        ('v0.6.1', False, '2026-10-08', ['webkit-autoloader-host_v0.6.1.exe', 'webkit-autoloader-host_v0.6.1.py',
                                         'webkit-autoloader-installer_v0.6.1.elf']),
        ('v0.6.0', False, '2026-10-08', ['webkit-autoloader-host_v0.6.0.exe', 'webkit-autoloader-host_v0.6.0.py',
                                         'webkit-autoloader-installer_v0.6.0.elf']),
        ('v0.6.0-pre-4488577', True, '2026-10-07', ['webkit-autoloader-host_v0.6.0-pre-4488577.exe',
                                                     'webkit-autoloader-host_v0.6.0-pre-4488577.py',
                                                     'webkit-autoloader-installer_v0.6.0-pre-4488577.elf']),
    ],
    'notmaj0r/CheatRunner': [
        ('v0.17.2', False, '2026-10-01', ['CheatRunner.elf']),
        ('v0.17.1', False, '2026-09-30', ['CheatRunner.elf']),
    ],
    'KarnerF/SMPlusGui': [
        ('v1.0.1', False, '2026-09-21', ['SMPlusGui_v1.0.1.elf']),
        ('v1.0.0', False, '2026-08-09', ['SMPlusGui_v1.0.0.elf']),
    ],
    'BestPig/BackPork': [
        ('0.1', False, '2026-04-30', ['ps5-backpork.elf']),
    ],
    'owendswang/ps5-aria2': [
        ('v1.37.0-3', False, '2026-10-05', ['aria2-v1.37.0-3.elf']),
        ('v1.37.0-2', False, '2026-10-03', ['aria2-v1.37.0-2.elf']),
    ],
    'idlesauce/ps5-self-pager': [
        ('v1.2', False, '2026-06-09', ['ps5-self-pager-full-system.elf', 'ps5-self-pager-game.elf',
                                       'ps5-self-pager-shellcore.elf', 'ps5-self-pager-system-common-lib.elf']),
        ('v1.1', False, '2025-11-16', ['ps5-self-pager-full-system.elf', 'ps5-self-pager-game.elf',
                                       'ps5-self-pager-shellcore.elf', 'ps5-self-pager-system-common-lib.elf']),
    ],
    'drakmor/ps5-hwinfo': [
        ('0.1', False, '2026-06-01', ['hwinfo_bench.elf', 'hwinfo_sysinfo.elf']),
    ],
    'itsPLK/PS5-Lapy-JB-Daemon': [
        ('v1.2', False, '2026-06-01', ['lapy_jb_daemon-v1.2.elf']),
    ],
    'owendswang/ps5-syslang': [
        ('v0.2.1', False, '2026-10-01', ['ps5-syslang-de-v0.2.1.elf', 'ps5-syslang-en-US-v0.2.1.elf',
                                         'ps5-syslang-fr-FR-v0.2.1.elf']),
        ('v0.2', False, '2026-06-28', ['ps5-syslang-de-v0.2.elf', 'ps5-syslang-en-US-v0.2.elf']),
        ('v0.1', False, '2026-06-27', ['ps5-syslang-v0.1.elf', 'syslang.ini']),
    ],
    'itsPLK/ps5-unified-autoloader': [
        ('v0.1.5-915a65e', False, '2026-09-29', ['ps5-unified-autoloader-v0.1.5-915a65e.elf']),
        ('v0.1.4-955249d', False, '2026-08-16', ['ps5-unified-autoloader-v0.1.4-955249d.elf']),
    ],
    'juma-sayeh/PS5-Game-Compressor': [
        ('v1.0.4', False, '2026-08-21', ['game-compressor.elf']),
        ('v1.0.3', False, '2026-06-20', ['game-compressor.elf']),
    ],
    'X-F1REBALL-X/wk-autoloader': [
        ('v1.0.16', False, '2026-10-06', ['installer.elf', 'wk-dual-payload.elf']),
        ('v1.0.14', False, '2026-10-06', ['installer.elf', 'wk-dual-payload.elf']),
    ],
    'gasb07/ps4mount': [
        ('v0.4.4', False, '2026-10-14', ['ps4mount.elf', 'ps4mount.elf.sha256']),
        ('v0.4.1', False, '2026-10-12', ['ps4mount.elf', 'ps4mount.elf.sha256']),
        ('v0.4.0', False, '2026-10-11', ['ps4mount.elf', 'ps4mount.elf.sha256']),
    ],
    'aydencharles/onionHEN': [
        ('v0.9.0-beta2', True, '2026-10-07', ['OnionHEN.elf']),
        ('v0.9.0-beta1', True, '2026-10-03', ['OnionHEN.elf']),
        ('v0.0.13', False, '2026-09-11', ['OnionHEN.elf']),
    ],
    'francoataffarel/ActRemoteLink': [
        ('v2.0', False, '2026-06-21', ['ActRemoteLink.zip']),
    ],
    'earthonion/garlic-savemgr': [
        ('v1.7', False, '2026-03-16', ['garlic-savemgr.elf']),
        ('v1.6', False, '2026-03-15', ['garlic-savemgr.elf']),
    ],
    'earthonion/garlic-worker': [
        ('latest', True, '2026-04-09', ['garlic-worker-ps4.elf', 'garlic-worker-ps5.elf']),
    ],
    'earthonion/np-fake-signin': [
        ('1.1', False, '2026-02-02', ['np-fake-signin-ps4.elf', 'np-fake-signin-ps5.elf']),
        ('1.0', False, '2026-02-01', ['np-fake-signin-ps4.elf', 'np-fake-signin-ps5.elf']),
        ('0.2_beta', True, '2026-01-31', ['np-fake-signin-ps4.elf', 'np-fake-signin-ps5.elf']),
    ],
    'ItsBlurf/PoorDS4': [
        ('v0.1.0-rc51', False, '2026-09-30', ['PoorDS4-status.elf', 'PoorDS4-stop.elf', 'PoorDS4rc51.elf',
                                              'SHA256SUMS.txt']),
        ('v0.1.0-rc44', False, '2026-09-18', ['PoorDS4-status.elf', 'PoorDS4-stop.elf', 'PoorDS4rc44.elf',
                                              'SHA256SUMS.txt']),
    ],
    'seregonwar/MemDBG': [
        ('nightly-20260930-g6e493c9', False, '2026-09-30', ['MemDBG-host-linux.tar.gz', 'MemDBG-ps4.elf',
                                                            'MemDBG-ps5.elf', 'SHA256SUMS.txt']),
        ('nightly-20260922-g6e493c9', False, '2026-09-22', ['MemDBG-host-linux.tar.gz', 'MemDBG-ps4.elf',
                                                            'MemDBG-ps5.elf', 'SHA256SUMS.txt']),
    ],
    'OnionBuddies/onionHEN-dpiv2-plugin': [],
    'SvenGDK/unjail-ps5app-payload': [
        ('v1.2', False, '2026-09-26', ['unjail.elf']),
        ('v1.1', False, '2026-09-25', ['unjail.elf']),
    ],
    'PSBrew/MkPFS': [
        ('1.1.0', False, '2026-10-03', ['mkpfs-1.1.0-windows-x64.exe', 'mkpfs-1.1.0.tar.gz']),
        ('1.0.0', False, '2026-08-31', ['mkpfs-1.0.0-windows-x64.exe', 'mkpfs-1.0.0.tar.gz']),
    ],
    'SvenGDK/UFS2Tool': [
        ('v4.1', False, '2026-05-08', ['linux-x64.zip', 'win-x64-selfcontained.zip', 'win-x64.zip']),
        ('v4.0', False, '2026-02-15', ['linux-x64.zip', 'win-x64-selfcontained.zip', 'win-x64.zip']),
    ],
    'SvenGDK/LibProsperoPkg': [
        ('v2.5', False, '2026-07-13', ['libprosperopkg-win-x64.zip', 'linux-x64.zip', 'win-x64.zip']),
        ('v2.0', False, '2026-07-10', ['libprosperopkg-win-x64.zip']),
    ],
    'pearlxcore/OrbisPkgTool': [
        ('v1.0.0', False, '2026-08-30', ['OrbisPkgTool-v1.0.0-win-x64.zip']),
    ],
    'andy-man/ps5-wee-tools': [
        ('v0.1.8', False, '2026-09-17', []),
        ('v0.2.x', False, '2024-09-17', []),
        ('v0.1.5', False, '2023-11-14', ['ps5-wee-tools-v0.1.5.zip']),
    ],
    'drakmor/ampr_emu': [
        ('0.4.2.1', False, '2026-09-06', ['ampr-emu-0.4.2.1-fix.zip', 'libSceAmpr.sprx',
                                          'libSceAmpr.sprx-0.4.2.1-test-debug-pack',
                                          'libSceAmpr.sprx-0.4.2.1-test-nopack',
                                          'libSceAmpr.sprx-0.4.2.1-test-pack']),
        ('0.3.6.6', False, '2026-08-23', ['libSceAmpr.sprx-0.3.6.6-test', 'libSceAmpr.sprx-0.3.6.6-test-debug']),
    ],
    'ip7z/7zip': [
        ('26.04', False, '2026-10-06', ['7z2604-src.7z', '7z2604-x64.exe', '7zr.exe']),
        ('26.03', False, '2026-09-04', ['7z2603-src.7z', '7z2603-x64.exe', '7zr.exe']),
    ],
    'codeberg:elmonomalva0/Any-Pad-ps5': [
        ('v0.8.1-beta', False, '2026-10-09', ['AnyPad-PS5-0.8.1-beta.elf', 'AnyPad-PS5-0.8.1-beta.elf.sha256']),
        ('v0.7.0-beta', False, '2026-10-08', ['AnyPad-PS5-0.7.0-beta.elf', 'AnyPad-PS5-0.7.0-beta.elf.sha256']),
    ],
    'knutwurst/ps5-ultrapack': [
        ('v2.2.2', False, '2026-10-08', ['PS5-UltraPack-2.2.2-macos-arm64.zip',
                                         'PS5-UltraPack-2.2.2-macos-arm64.zip.sha256']),
        ('v2.2.1', False, '2026-10-07', ['PS5-UltraPack-2.2.1-macos-arm64.zip',
                                         'PS5-UltraPack-2.2.1-macos-arm64.zip.sha256']),
    ],
    'sub0x00001/ps5-fpkg-converter': [
        ('v0.0.2', False, '2026-10-07', ['PS5-FPKG-Converter-v0.0.2-portable-win64.zip']),
    ],
}

#: Die ELF-Dateien in helloworld/ am 10.10.2026.
HELLOWORLD = [
    "AnyPad-PS5-0.8.1-beta.elf", "CheatRunner_v0.17.2.elf", "MemDBG-ps5_nightly-20260930.elf", "OffAct_v0.4.2.elf",
    "OnionHEN_v0.0.13.elf", "OnionHEN_v0.9.0-beta2.elf", "PIZZA-HEN-v2.00.elf",
    "PS5_Cooling_System_Center_v1.56.0.elf", "PoorDS4-status_rc51.elf", "PoorDS4-stop_rc51.elf", "PoorDS4_rc51.elf",
    "ProsperoMgr_v1.1.elf", "SMPlusGui_v1.0.1.elf", "WK-AutoLoader_v1.0.16.elf", "actremotelink_agent_v2.0.elf",
    "actremotelink_pin_notify_v2.0.elf", "aria2-v1.37.0-3.elf", "bdj_unpatch_1340.elf",
    "bfpilot_v0.4.4-multilang.elf", "dpiv2-13.60-1.00.elf", "dump_installer_v1.07.elf", "elfldr-ps5_v0.26.elf",
    "ftpsrv-ps5_v0.21.1.elf", "ftpsrv-ps5_v1.15-ng.elf", "ftpsrv-ps5_v1.16-ng-stable.elf",
    "game-compressor_v1.1.1.elf", "garlic-savemgr_v1.13.1.elf", "garlic-worker-ps5_2026-04-09.elf",
    "gdbsrv-ps5_v0.9.elf", "klogsrv-ps5_v0.9.elf", "kstuff_lite_v1.11_Beta_EchoStretch.elf",
    "kstuff_v1.13-fpkg-dr-test5.elf", "lapy_jb_daemon-v1.2.elf", "nanodns_v0.4.elf", "np-fake-signin-v1.3.elf",
    "pkgmgr_v1.5.0.elf", "pldmgr_v0.6.0.elf", "ps4mount_v0.4.4.elf", "ps5-app-dumper_v2.10.elf", "ps5-backpork_v0.1.elf",
    "ps5-hwinfo-bench_v0.1.elf", "ps5-hwinfo-sysinfo_v0.1.elf", "ps5-self-pager-full-system_v1.2.elf",
    "ps5-self-pager-game_v1.2.elf", "ps5-self-pager-shellcore_v1.2.elf", "ps5-self-pager-system-common-lib_v1.2.elf",
    "ps5-syslang-de-v0.2.1.elf", "ps5-unified-autoloader-v0.1.5-915a65e.elf", "ps5debug-NG_v1.3.2.elf",
    "ps5upload-6.7.3.elf", "shadowmountplus_v1.7beta4.elf", "shsrv-ps5_v0.20.elf", "unjail-ps5app-payload.elf",
    "web-file-mgr-v1.10.elf", "webkit-autoloader-installer_v0.6.1.elf", "websrv-ps5_v0.34.elf",
    "zftpd-ps5-v1.6.0.elf", "zftpd-ps5-zhttp-v1.6.0.elf",
]
#: Der Ordner „PS5 WebKit Autoloader“ am 10.10.2026: fuenf Fassungen, je drei Dateien.
WEBKIT = sorted("webkit-autoloader-%s_v%s.%s" % (art, fassung, endung)
                for fassung in ("0.4.0", "0.5.1", "0.5.2", "0.6.0", "0.6.1")
                for art, endung in (("host", "exe"), ("host", "py"), ("installer", "elf")))
#: AMPR EMU im Bestand: (Fassung, Variante).
AMPR = [("0.4.2.1", "test-pack"), ("0.4.2.1", "test-nopack"), ("0.4.2.1", "test-debug-pack"),
        ("0.3.6.6", "debug"), ("0.3.6.6", "no debug")]

#: Was die Tabelle fuer diese festen Daten urteilen muss (alles andere: ``aktuell``; Eintraege ohne Vergleich
#: - ``ART_KEINE`` - sind ``ohne_quelle``). Die drei ersten haben eine mitgelieferte Fassung, die auf der
#: Freigaben-Seite ihres Autors (noch) nicht steht.
ERWARTET_ABWEICHUNG = {
    "game-compressor": wu.STATUS_NEUER, "np-fake-signin": wu.STATUS_NEUER, "garlic-savemgr": wu.STATUS_NEUER,
    "dpiv2": wu.STATUS_UNKLAR,
}


def inhalt(name: str) -> bytes:
    """Der erfundene Inhalt eines Anhangs - ihn kennen die Freigabe (Groesse, Pruefsumme) und das Laden."""
    return b"\x7fELF" + (name.encode("utf-8") + b"|") * 3


def summe(name: str) -> str:
    return hashlib.sha256(inhalt(name)).hexdigest()


def github_roh(quelle: str, freigaben=None) -> list[dict]:
    """Die Antwort der Schnittstelle fuer ``quelle`` - mit Groessen und Pruefsummen, die zu ``inhalt`` passen."""
    art, repo = wu.quelle_zerlegen(quelle)
    seite = wu.seite_der_quelle(quelle)
    erg = []
    for marke, vorab, datum, namen in (RELEASES[quelle] if freigaben is None else freigaben):
        erg.append({
            "tag_name": marke, "name": marke, "prerelease": vorab, "draft": False,
            "published_at": datum + "T12:00:00Z", "html_url": "%s/tag/%s" % (seite, marke),
            "assets": [{"name": n, "size": len(inhalt(n)),
                        "digest": "" if art == "codeberg" or n.endswith(".sha256") else "sha256:" + summe(n),
                        "browser_download_url": "%s/download/%s/%s" % (seite, marke, n)} for n in namen]})
    return erg


class FakeNetz:
    """Antwortet aus ``RELEASES``; nichts geht ins Netz. Fuehrt Buch, was gefragt und geladen wurde."""

    def __init__(self, releases=None, ausfaelle=None) -> None:
        self.releases = RELEASES if releases is None else releases
        self.ausfaelle = dict(ausfaelle or {})
        self.gefragt: list[tuple[str, str]] = []
        self.geladen: list[str] = []
        self.verfaelscht: set[str] = set()
        self.sperre = threading.Lock()

    def abfragen(self, quelle: str, etag: str = "") -> "wu.Antwort":
        with self.sperre:
            self.gefragt.append((quelle, etag))
        if quelle in self.ausfaelle:
            antwort = self.ausfaelle[quelle]
            if isinstance(antwort, BaseException):
                raise antwort
            return antwort
        if quelle not in self.releases:
            return wu.Antwort(404)
        text = json.dumps(github_roh(quelle, self.releases[quelle]))
        marke = 'W/"%s"' % hashlib.md5(text.encode("utf-8")).hexdigest()[:10]
        if etag and etag == marke:
            return wu.Antwort(304, "", etag)
        return wu.Antwort(200, text, marke)

    def laden(self, adresse, pfad, fortschritt=None, abbruch=None):
        self.geladen.append(adresse)
        if abbruch is not None and abbruch.is_set():
            raise wu.Abgebrochen()
        daten = inhalt(adresse.rsplit("/", 1)[-1])
        if adresse in self.verfaelscht:
            daten = daten[:-1] + b"X"
        Path(pfad).write_bytes(daten)
        if fortschritt is not None:
            fortschritt(len(daten), len(daten))
        return len(daten), hashlib.sha256(daten).hexdigest()

    def bytes(self, adresse, grenze=64 * 1024 * 1024):
        name = adresse.rsplit("/", 1)[-1]
        if name.endswith(".sha256"):
            ziel = name[:-len(".sha256")]
            return ("%s  %s\n" % (summe(ziel), ziel)).encode("utf-8")
        return inhalt(name)


def bestand_aus(helloworld=HELLOWORLD, webkit=WEBKIT, geholt=None, wurzeln=()) -> "wu.Bestand":
    return wu.Bestand(mitgeliefert={wu.ORT_PAYLOADS: list(helloworld), wu.ORT_WEBKIT: list(webkit)},
                      geholt=dict(geholt or {}), wurzeln=list(wurzeln))


def freigaben_von(quelle: str) -> list["wu.Freigabe"]:
    return wu.freigaben_lesen(github_roh(quelle))


# ---------------------------------------------------------------------------
# Fassungen
# ---------------------------------------------------------------------------
class FassungsTests(unittest.TestCase):

    def test_die_reihenfolge_der_fassungen(self) -> None:
        # Jede Kette ist aufsteigend gemeint.
        ketten = [
            ["0.4", "0.4.1", "0.5", "0.10"],
            ["6.9.0", "6.10.0"],
            ["1.7beta3", "1.7beta4", "1.7"],
            ["0.9.0-beta2", "0.9.0", "0.9.1"],
            ["1.0.0-alpha1", "1.0.0-beta1", "1.0.0-rc1", "1.0.0"],
            ["1.37.0-1", "1.37.0-2", "1.37.0-3", "1.37.1"],
            ["1.05", "1.06", "1.07", "1.08", "1.10"],        # Dump Installer: zweistellige Unterfassung
        ]
        for kette in ketten:
            schluessel = [wu.fassungsschluessel(f) for f in kette]
            self.assertEqual(sorted(schluessel), schluessel, kette)
            self.assertEqual(len(set(schluessel)), len(schluessel), kette)

    def test_ohne_zahl_gibt_es_keinen_schluessel(self) -> None:
        for text in ("", "latest", "beta", "nightly"):
            self.assertEqual((), wu.fassungsschluessel(text), text)

    def test_v_vorn_und_abschlussnullen_zaehlen_nicht(self) -> None:
        self.assertEqual(wu.fassungsschluessel("v1.2"), wu.fassungsschluessel("1.2.0"))
        self.assertEqual(wu.fassungsschluessel("V3"), wu.fassungsschluessel("3.0.0.0"))

    def test_fassung_aus_dem_dateinamen(self) -> None:
        erwartet = {
            "elfldr-ps5_v0.26.elf": "0.26",
            "ps5upload-6.7.3.elf": "6.7.3",
            "ftpsrv-ps5_v1.16-ng-stable.elf": "1.16",
            "shadowmountplus_v1.7beta4.elf": "1.7beta4",
            "OnionHEN_v0.9.0-beta2.elf": "0.9.0-beta2",
            "aria2-v1.37.0-3.elf": "1.37.0-3",
            "AnyPad-PS5-0.8.1-beta.elf": "0.8.1-beta",
            "kstuff_lite_v1.11_Beta_EchoStretch.elf": "1.11_Beta",
            "zftpd-ps5-zhttp-v1.6.0.elf": "1.6.0",
            "ps5-syslang-de-v0.2.1.elf": "0.2.1",
            "PS5_Cooling_System_Center_v1.56.0.elf": "1.56.0",
            "webkit-autoloader-host_v0.6.1.exe": "0.6.1",
            "dump_installer_v1.07.elf": "1.07",
            "bdj_unpatch_1340.elf": "",
            "unjail-ps5app-payload.elf": "",
        }
        for name, soll in erwartet.items():
            self.assertEqual(soll, wu.fassung_aus_datei(name), name)

    def test_fassung_aus_dem_dateinamen_in_den_besonderen_modi(self) -> None:
        self.assertEqual("rc51", wu.fassung_aus_datei("PoorDS4-status_rc51.elf", "rc"))
        self.assertEqual("20260930", wu.fassung_aus_datei("MemDBG-ps5_nightly-20260930.elf", "datum8"))
        self.assertEqual("2026-04-09", wu.fassung_aus_datei("garlic-worker-ps5_2026-04-09.elf", "datum"))
        self.assertEqual("0.1.5-915a65e", wu.fassung_aus_datei(
            "ps5-unified-autoloader-v0.1.5-915a65e.elf", "tag", "ps5-unified-autoloader-v{f}.elf"))
        self.assertEqual("", wu.fassung_aus_datei("anderes.elf", "tag", "ps5-unified-autoloader-v{f}.elf"))
        self.assertEqual("", wu.fassung_aus_datei("ohne_marke.elf", "rc"))

    def test_fassung_aus_der_marke(self) -> None:
        self.assertEqual("0.26", wu.fassung_aus_tag("v0.26"))
        self.assertEqual("1.7beta4", wu.fassung_aus_tag("1.7beta4"))
        self.assertEqual("1.37.0-3", wu.fassung_aus_tag("v1.37.0-3"))
        self.assertEqual("0.1.5", wu.fassung_aus_tag("v0.1.5-915a65e"))
        self.assertEqual("0.1.5-915a65e", wu.fassung_aus_tag("v0.1.5-915a65e", "tag"))
        self.assertEqual("rc51", wu.fassung_aus_tag("v0.1.0-rc51", "rc"))
        self.assertEqual("20260930", wu.fassung_aus_tag("nightly-20260930-g6e493c9", "datum8"))
        self.assertEqual("2026-04-09", wu.fassung_aus_tag("latest", "datum", "2026-04-09"))
        self.assertEqual("", wu.fassung_aus_tag("beta"))

    def test_vergleichen(self) -> None:
        tabelle = [
            ("0.26", "0.27", "zahl", "neu"), ("0.26", "0.26", "zahl", "aktuell"), ("0.27", "0.26", "zahl", "neuer"),
            ("1.7beta4", "1.7", "zahl", "neu"), ("1.7", "1.7beta4", "zahl", "neuer"),
            ("1.0", "1.0.0", "zahl", "aktuell"),
            ("0.1.5", "0.1.5-915a65e", "zahl", "unklar"),     # gleiche Zahl, verschiedener Rest: nicht entscheidbar
            ("", "1.0", "zahl", "unklar"), ("1.0", "", "zahl", "unklar"),
            ("1.11_Beta", "1.11", "nur_zahl", "aktuell"), ("1.11_Beta", "1.12", "nur_zahl", "neu"),
            ("rc44", "rc51", "rc", "neu"), ("rc51", "rc51", "rc", "aktuell"),
            ("20260922", "20260930", "datum8", "neu"),
            ("2026-04-09", "2026-04-10", "datum", "neu"), ("2026-04-09", "2026-04-09", "datum", "aktuell"),
            ("0.1.5-915a65e", "0.1.5-abcdef0", "tag", "aktuell"),
        ]
        for lokal, neu, modus, soll in tabelle:
            self.assertEqual(soll, wu.vergleichen(lokal, neu, modus), (lokal, neu, modus))

    def test_der_ordnername(self) -> None:
        self.assertEqual("1.1.0", wu.fassung_aus_ordnername("MkPFS-1.1.0"))
        self.assertEqual("26.00", wu.fassung_aus_ordnername("C:\\x\\7-Zip-26.00\\"))
        self.assertEqual("0.1.8", wu.fassung_aus_ordnername("/a/PS5-Wee-Tools-0.1.8"))
        self.assertEqual("", wu.fassung_aus_ordnername("helloworld"))

    def test_dateien_ordnen_sich_nach_der_fassung(self) -> None:
        namen = ["a_v6.9.0.elf", "a_v6.10.0.elf", "a_v6.2.elf"]
        self.assertEqual(["a_v6.2.elf", "a_v6.9.0.elf", "a_v6.10.0.elf"],
                         sorted(namen, key=wu.datei_schluessel))
        # Vorabfassung unter der fertigen, auch ohne "_v".
        self.assertEqual("OnionHEN_v0.9.0.elf", max(["OnionHEN_v0.9.0-beta2.elf", "OnionHEN_v0.9.0.elf",
                                                     "OnionHEN_v0.0.13.elf"], key=wu.datei_schluessel))
        self.assertEqual("ps5upload-6.10.0.elf", max(["ps5upload-6.9.0.elf", "ps5upload-6.10.0.elf"],
                                                     key=wu.datei_schluessel))
        # Ohne lesbare Fassung entscheidet der Name - und eine mit Fassung gewinnt.
        self.assertEqual("b_v1.0.elf", max(["z_ohne.elf", "b_v1.0.elf"], key=wu.datei_schluessel))
        self.assertEqual("z_ohne.elf", max(["a_ohne.elf", "z_ohne.elf"], key=wu.datei_schluessel))


# ---------------------------------------------------------------------------
# Freigaben deuten
# ---------------------------------------------------------------------------
class FreigabenTests(unittest.TestCase):

    def test_beide_schnittstellen_werden_gelesen(self) -> None:
        for quelle in ("ps5-payload-dev/elfldr", "codeberg:elmonomalva0/Any-Pad-ps5"):
            freigaben = freigaben_von(quelle)
            self.assertEqual(len(RELEASES[quelle]), len(freigaben), quelle)
            erste = freigaben[0]
            self.assertEqual(RELEASES[quelle][0][0], erste.tag)
            self.assertEqual(RELEASES[quelle][0][2], erste.datum)
            self.assertEqual(RELEASES[quelle][0][3], [a.name for a in erste.anhaenge])
            self.assertTrue(all(a.adresse.startswith(("https://github.com/", "https://codeberg.org/"))
                                for a in erste.anhaenge))

    def test_unbrauchbares_wird_uebersprungen_nie_geworfen(self) -> None:
        self.assertEqual([], wu.freigaben_lesen("kein json"))
        self.assertEqual([], wu.freigaben_lesen('{"message": "API rate limit exceeded"}'))
        self.assertEqual([], wu.freigaben_lesen(b"\xff\xfe"))
        self.assertEqual([], wu.freigaben_lesen(None))
        roh = [{"name": "ohne Marke"}, 5, {"tag_name": "v1", "assets": [{"size": 3}, {"name": "a.elf", "size": "x"}]}]
        freigaben = wu.freigaben_lesen(roh)
        self.assertEqual(["v1"], [f.tag for f in freigaben])
        self.assertEqual(["a.elf"], [a.name for a in freigaben[0].anhaenge])
        self.assertEqual(0, freigaben[0].anhaenge[0].groesse)

    def test_der_zwischenspeicher_gibt_dasselbe_zurueck(self) -> None:
        for quelle in RELEASES:
            freigaben = freigaben_von(quelle)
            wieder = wu.freigaben_lesen(json.loads(json.dumps(wu.freigaben_als_daten(freigaben))))
            self.assertEqual(freigaben, wieder, quelle)

    def test_die_form_fuer_ampr_updates(self) -> None:
        freigaben = freigaben_von("drakmor/ampr_emu")
        roh = wu.freigaben_als_roh(freigaben)
        self.assertEqual(freigaben, wu.freigaben_lesen(roh))

    def test_quellen_und_adressen(self) -> None:
        self.assertEqual(("github", "a/b"), wu.quelle_zerlegen("a/b"))
        self.assertEqual(("codeberg", "a/b"), wu.quelle_zerlegen("codeberg:a/b"))
        self.assertEqual(("", ""), wu.quelle_zerlegen(""))
        self.assertEqual("https://github.com/a/b/releases", wu.seite_der_quelle("a/b"))
        self.assertEqual("https://codeberg.org/a/b/releases", wu.seite_der_quelle("codeberg:a/b"))
        self.assertTrue(wu.adresse_der_quelle("a/b").startswith("https://api.github.com/repos/a/b/releases"))
        self.assertTrue(wu.adresse_der_quelle("codeberg:a/b").startswith("https://codeberg.org/api/v1/repos/a/b/"))
        self.assertEqual("", wu.adresse_der_quelle(""))
        self.assertEqual("", wu.seite_der_quelle(""))


# ---------------------------------------------------------------------------
# Die Tabelle
# ---------------------------------------------------------------------------
class TabelleTests(unittest.TestCase):

    def test_schluessel_sind_eindeutig_und_auffindbar(self) -> None:
        schluessel = [w.schluessel for w in wu.WERKZEUGE]
        self.assertEqual(len(schluessel), len(set(schluessel)))
        for w in wu.WERKZEUGE:
            self.assertIs(w, wu.werkzeug(w.schluessel))
        self.assertIsNone(wu.werkzeug("gibt-es-nicht"))

    def test_jeder_eintrag_ist_wohlgeformt(self) -> None:
        modi = {"zahl", "nur_zahl", "tag", "rc", "datum8", "datum"}
        quellform = re.compile(r"^(codeberg:)?[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
        for w in wu.WERKZEUGE:
            with self.subTest(w.schluessel):
                self.assertIn(w.gruppe, wu.GRUPPEN)
                self.assertIn(w.art, (wu.ART_DATEI, wu.ART_HINWEIS, wu.ART_EMU, wu.ART_KEINE))
                self.assertIn(w.modus, modi)
                self.assertTrue(w.name.strip())
                if w.quelle:
                    self.assertRegex(w.quelle, quellform)
                else:
                    self.assertEqual(wu.ART_KEINE, w.art, "ohne Quelle gibt es nichts zu pruefen")
                if w.art == wu.ART_DATEI:
                    self.assertTrue(w.dateien, "ladbar heisst: Dateien angegeben")
                    self.assertTrue(w.muster)
                else:
                    self.assertEqual((), w.dateien, "nur ladbare Eintraege legen Dateien ab")
                for d in w.dateien:
                    self.assertIn("{f}", d.ziel, "ohne {f} wuerden sich die Fassungen ueberschreiben")
                    self.assertTrue(set(d.orte) <= set(wu.ORTE))
                    self.assertTrue(wu.ziel_erlaubt(d.ziel.replace("{f}", "1.0")), d.ziel)
                if w.hinweis:
                    self.assertTrue(w.hinweis.startswith("updates.hinweis_"))

    def test_die_orte_sind_alle_die_die_tabelle_benutzt(self) -> None:
        benutzt = {w.ordner for w in wu.WERKZEUGE if w.muster}
        benutzt |= {o for w in wu.WERKZEUGE for d in w.dateien for o in d.orte}
        self.assertEqual(set(wu.ORTE), benutzt)

    def test_alle_gruppen_kommen_vor_und_stehen_zusammen(self) -> None:
        reihenfolge = [w.gruppe for w in wu.WERKZEUGE]
        gruppen_in_reihe = [g for i, g in enumerate(reihenfolge) if i == 0 or reihenfolge[i - 1] != g]
        self.assertEqual(len(gruppen_in_reihe), len(set(gruppen_in_reihe)),
                         "Jede Gruppe steht an einem Stueck - sonst erschiene ihre Kopfzeile zweimal")
        self.assertEqual(set(wu.GRUPPEN), set(reihenfolge))

    def test_die_quellen_sind_je_einmal_zu_fragen(self) -> None:
        zu_fragen = wu.quellen(wu.WERKZEUGE)
        self.assertEqual(len(zu_fragen), len(set(zu_fragen)))
        self.assertNotIn("", zu_fragen)
        # Ein Eintrag ohne Vergleich kostet keine Anfrage - auch wenn er einen Link zur Freigaben-Seite traegt.
        ohne_vergleich = {w.seite for w in wu.WERKZEUGE if w.art == wu.ART_KEINE and w.seite}
        self.assertTrue(ohne_vergleich, "Es gibt Eintraege mit Link und ohne Vergleich")
        for seite in ohne_vergleich:
            repo = seite.split("github.com/", 1)[1].rsplit("/releases", 1)[0]
            self.assertNotIn(repo, zu_fragen)
        # Eine vollstaendige Pruefung braucht rund 50 Anfragen; GitHub erlaubt ohne Anmeldung 60 je Stunde.
        self.assertLessEqual(len(zu_fragen), 55, "Die Anfragegrenze von GitHub liegt bei 60 je Stunde")

    def test_jede_quelle_der_tabelle_steht_in_den_festen_freigaben(self) -> None:
        # Sonst belegt der Rest dieser Datei nichts fuer sie.
        fehlen = [q for q in wu.quellen(wu.WERKZEUGE) if q not in RELEASES]
        self.assertEqual([], fehlen)

    def test_hinweise_der_tabelle_sind_ubersetzt(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for w in wu.WERKZEUGE:
            if w.hinweis:
                self.assertIn(w.hinweis, STRINGS, w.schluessel)
                self.assertTrue(STRINGS[w.hinweis].get("de") and STRINGS[w.hinweis].get("en"), w.hinweis)


class FestTests(unittest.TestCase):
    """Wo das Programm bei der mitgelieferten Datei bleibt: elfldr, ftpsrv und klogsrv."""

    def test_welche_eintraege_fest_sind(self) -> None:
        self.assertEqual({"elfldr", "ftpsrv", "klogsrv"}, {w.schluessel for w in wu.WERKZEUGE if w.fest})
        for w in wu.WERKZEUGE:
            if w.fest:
                self.assertEqual("updates.hinweis_fest", w.hinweis, "Der Hinweis erklaert, warum")
                self.assertEqual(wu.ART_DATEI, w.art, "Nur Geladenes kann 'fest' sein")

    def test_ist_fest_trifft_die_muster_des_katalogs(self) -> None:
        for muster in ("elfldr*.elf", "elfldr-ps5_v*.elf", "ftpsrv-ps5*.elf", "klogsrv*.elf", "KLOGSRV*.ELF"):
            self.assertTrue(wu.ist_fest(muster), muster)
        for muster in ("", "pldmgr*.elf", "pkgmgr*.elf", "websrv-ps5*.elf", "ps5upload*.elf", "gdbsrv-ps5_v*.elf",
                       "PS5_Cooling_System_Center_v*.elf", "garlic-savemgr*.elf", "zftpd-ps5-zhttp-v*.elf", "*.elf"):
            self.assertFalse(wu.ist_fest(muster), muster)

    def test_jedes_fest_gehoert_zu_einem_katalogmuster(self) -> None:
        from ps5_validator.utils import konsole_dienste as kd
        muster = {d.payload_muster for d in kd.KATALOG if d.payload_muster}
        for w in wu.WERKZEUGE:
            if w.fest:
                self.assertTrue(any(wu.ist_fest(m) and fnmatch_trifft(m, w) for m in muster),
                                "%s: Kein Katalogmuster trifft den Eintrag" % w.schluessel)


def fnmatch_trifft(muster: str, w: "wu.Werkzeug") -> bool:
    import fnmatch
    return any(fnmatch.fnmatchcase(d.ziel.replace("{f}", "0").lower(), muster.lower()) for d in w.dateien)


class AbdeckungTests(unittest.TestCase):
    """Am echten Ordner gemessen - unabhaengig von Fassungen."""

    #: Was in diesen Ordnern liegt, ohne ein Werkzeug zu sein.
    KEIN_WERKZEUG = (".txt", ".png", ".md")

    def _dateien(self, ort: str) -> list[str]:
        ordner = PROJEKT / ort
        return sorted(n.name for n in ordner.iterdir() if n.is_file() and n.suffix.lower() not in self.KEIN_WERKZEUG)

    def test_jede_datei_hat_einen_eintrag(self) -> None:
        for ort in wu.ORTE:
            karte = wu.abgedeckte_dateien(self._dateien(ort), ort)
            self.assertEqual([], karte.get("", []),
                             "Diese Dateien in %s hat die Tabelle von werkzeug_updates nicht: Wer eine neue Datei "
                             "einspielt, traegt sie dort ein (und im Skill werkzeug-updates.md)." % ort)

    def test_jeder_eintrag_hat_eine_datei(self) -> None:
        # Das ``muster`` muss selbst treffen (nicht erst eine Vorlage aus ``dateien``): Nach ihm liest ``lokale_fassung``.
        for ort in wu.ORTE:
            namen = self._dateien(ort)
            tot = [w.schluessel for w in wu.WERKZEUGE
                   if w.muster and w.ordner == ort and not any(wu._passt(w, n) for n in namen)]
            self.assertEqual([], tot, "Eintraege ohne Datei in %s" % ort)

    def test_jede_mitgelieferte_fassung_ist_lesbar(self) -> None:
        bestand = wu.bestand_lesen(lambda ort: str(PROJEKT / ort), str(PROJEKT / "gibt-es-nicht"))
        for w in wu.WERKZEUGE:
            if w.art in (wu.ART_DATEI, wu.ART_HINWEIS) and w.muster and not w.lokal:
                self.assertTrue(wu.lokale_fassung(w, bestand).fassung,
                                "%s: aus den Dateinamen ist keine Fassung zu lesen" % w.schluessel)

    def test_der_webkit_ordner_hat_je_fassung_drei_dateien(self) -> None:
        namen = self._dateien(wu.ORT_WEBKIT)
        fassungen = {wu.fassung_aus_datei(n) for n in namen}
        self.assertNotIn("", fassungen)
        for fassung in fassungen:
            for art, endung in (("host", "exe"), ("host", "py"), ("installer", "elf")):
                self.assertIn("webkit-autoloader-%s_v%s.%s" % (art, fassung, endung), namen)

    def test_ps5_pkg_tool_stimmt_mit_der_tabelle(self) -> None:
        # Die Fassungen stehen in der Tabelle fest (das gebaute Programm hat von den Quellen nur win-x64 dabei).
        # Wer das Werkzeug neu baut, muss sie dort nachziehen - sonst urteilte "Updates" auf altem Stand.
        readme = (PROJEKT / "PS5-PKG-Tool" / "README.md").read_text(encoding="utf-8")
        programm = (PROJEKT / "PS5-PKG-Tool" / "src" / "ffpfsc-pkg-tool" / "Program.cs").read_text(encoding="utf-8")
        konverter = re.search(r"ps5-fpkg-converter\s+(\d+(?:\.\d+)+)", readme).group(1)
        ultrapack = re.search(r'ToolVersion\s*=\s*"(\d+(?:\.\d+)+)"', programm).group(1)
        self.assertEqual("fest:" + konverter, wu.werkzeug("ps5-pkg-tool").lokal)
        self.assertEqual("fest:" + ultrapack, wu.werkzeug("ps5-ultrapack").lokal)

    def test_playgo_stimmt_mit_dem_ordner(self) -> None:
        # Die Ordner heissen PlayGo_v0.6 (mit Unterstrich) und liefern keine Fassung ueber "ordnername" - deshalb steht
        # sie fest in der Tabelle und wird hier gegen den hoechsten Ordner gehalten.
        ordner = [p.name for p in (PROJEKT / "PlayGo & AMPR_EMU").glob("PlayGo_v*") if p.is_dir()]
        fassungen = [n.split("_v", 1)[1] for n in ordner]
        self.assertTrue(fassungen)
        hoechste = max(fassungen, key=wu.fassungsschluessel)
        self.assertEqual("fest:" + hoechste, wu.werkzeug("playgo").lokal)

    def test_die_ordner_fassungen_sind_lesbar(self) -> None:
        bestand = wu.Bestand(wurzeln=[str(PROJEKT)])
        for schluessel in ("mkpfs", "ufs2tool", "prosperopkg", "orbispkgtool", "wee-tools", "7zip",
                           "ampr-packtools", "ps4ffpfsc", "unjail"):
            lokal = wu.lokale_fassung(wu.werkzeug(schluessel), bestand)
            self.assertTrue(lokal.fassung, "%s: Fassung nicht lesbar" % schluessel)


# ---------------------------------------------------------------------------
# Das Urteil
# ---------------------------------------------------------------------------
class UrteilTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp(prefix="wu_wurzel_")
        for ordner in ("MkPFS-1.1.0", "UFS2Tool-4.1", "OrbisPkgTool-1.0.0", "PS5-Wee-Tools-0.1.8", "7-Zip-26.00",
                       "AMPR_PackTools-4.0", "PS4FFPFSC-0.2.9", "ProsperoPkg-2.5", "PS5-PKG-Tool",
                       "helloworld/unjail-ps5app-payload-1.2"):
            os.makedirs(os.path.join(cls.tmp, *ordner.split("/")))
        Path(cls.tmp, "ProsperoPkg-2.5", "fassung.json").write_text(
            json.dumps({"fassung": "2.6.0", "quelle": "SvenGDK/LibProsperoPKG"}), encoding="utf-8-sig")
        cls.bestand = bestand_aus(wurzeln=[cls.tmp])
        cls.befunde, _speicher = wu.pruefen(wu.WERKZEUGE, cls.bestand, FakeNetz(), {}, heute="2026-10-10",
                                            ampr_vorhanden=lambda: AMPR, ampr_ordner=os.path.join(cls.tmp, "ampr"))
        cls.nach = {b.werkzeug.schluessel: b for b in cls.befunde}

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_jedes_werkzeug_bekommt_ein_urteil_in_tabellenreihenfolge(self) -> None:
        self.assertEqual([w.schluessel for w in wu.WERKZEUGE], [b.werkzeug.schluessel for b in self.befunde])

    def test_der_heutige_stand(self) -> None:
        for befund in self.befunde:
            w = befund.werkzeug
            if w.art == wu.ART_KEINE:
                self.assertEqual(wu.STATUS_OHNE_QUELLE, befund.status, w.schluessel)
                continue
            if w.lokal:
                continue                        # Ordner-Werkzeuge: ``EngineTests``
            soll = ERWARTET_ABWEICHUNG.get(w.schluessel, wu.STATUS_AKTUELL)
            self.assertEqual(soll, befund.status, "%s: %s %s -> %s %s" % (
                w.schluessel, befund.status, befund.lokal, befund.neu, befund.meldung))

    def test_die_zielnamen_ergeben_die_heutigen_dateinamen(self) -> None:
        # Der Beleg fuer die Umbenennungsvorlagen: Fuer die heutige Freigabe entstehen genau die Namen, die schon im
        # Ordner liegen. Ausgenommen die, deren mitgelieferte Fassung nicht die der Freigabe ist.
        pruefte = 0
        for w in wu.WERKZEUGE:
            if w.art != wu.ART_DATEI or ERWARTET_ABWEICHUNG.get(w.schluessel):
                continue
            treffer = wu._kandidat(w, freigaben_von(w.quelle))
            self.assertIsNotNone(treffer, w.schluessel)
            _freigabe, _fassung, teile = treffer
            for teil in teile:
                for ort in teil.orte:
                    vorhanden = self.bestand.mitgeliefert[ort]
                    self.assertIn(teil.ziel, vorhanden, "%s legte %s in %s ab - dort liegt es nicht" % (
                        w.schluessel, teil.ziel, ort))
                    pruefte += 1
        self.assertGreater(pruefte, 40, "Die Pruefung hat kaum etwas gemessen")

    def test_die_abweichungen_haben_den_erwarteten_grund(self) -> None:
        self.assertEqual(wu.MELDUNG_KEINE_FREIGABE, self.nach["dpiv2"].meldung)
        for schluessel in ("game-compressor", "np-fake-signin", "garlic-savemgr"):
            self.assertGreater(wu.fassungsschluessel(self.nach[schluessel].lokal),
                               wu.fassungsschluessel(self.nach[schluessel].neu))

    def test_ladbar_ist_nur_was_neu_ist_und_dateien_hat(self) -> None:
        for befund in self.befunde:
            self.assertEqual(befund.status == wu.STATUS_NEU and bool(befund.teile or befund.ampr), befund.ladbar)
        self.assertFalse(any(b.ladbar for b in self.befunde), "Heute ist nichts ladbar")

    def test_eine_neue_fassung_wird_mit_dateien_angeboten(self) -> None:
        neu = dict(RELEASES)
        neu['ps5-payload-dev/elfldr'] = [('v0.27', False, '2026-10-12', ['elfldr-ps5.elf'])] + RELEASES[
            'ps5-payload-dev/elfldr']
        w = wu.werkzeug("elfldr")
        befund = wu.beurteilen(w, wu.lokale_fassung(w, self.bestand), wu.freigaben_lesen(
            github_roh("ps5-payload-dev/elfldr", neu["ps5-payload-dev/elfldr"])))
        self.assertEqual(wu.STATUS_NEU, befund.status)
        self.assertEqual(("0.26", "0.27"), (befund.lokal, befund.neu))
        self.assertEqual("2026-10-12", befund.datum)
        self.assertTrue(befund.ladbar)
        (teil,) = befund.teile
        self.assertEqual("elfldr-ps5_v0.27.elf", teil.ziel)
        self.assertEqual("elfldr-ps5.elf", teil.anhang)
        self.assertEqual((wu.ORT_PAYLOADS,), teil.orte)
        self.assertEqual("sha256:" + summe("elfldr-ps5.elf"), teil.digest)
        self.assertEqual(len(inhalt("elfldr-ps5.elf")), teil.groesse)
        self.assertEqual(teil.groesse, befund.groesse)
        self.assertTrue(teil.adresse.startswith("https://github.com/ps5-payload-dev/elfldr/"))

    def test_mehrere_dateien_einer_freigabe_kommen_zusammen(self) -> None:
        w = wu.werkzeug("webkit")
        freigaben = wu.freigaben_lesen(github_roh("itsPLK/ps5-webkit-autoloader", [
            ('v0.6.2', False, '2026-10-12', ['webkit-autoloader-host_v0.6.2.exe', 'webkit-autoloader-host_v0.6.2.py',
                                             'webkit-autoloader-installer_v0.6.2.elf'])]))
        befund = wu.beurteilen(w, wu.lokale_fassung(w, self.bestand), freigaben)
        self.assertEqual(wu.STATUS_NEU, befund.status)
        self.assertEqual(["webkit-autoloader-host_v0.6.2.exe", "webkit-autoloader-host_v0.6.2.py",
                          "webkit-autoloader-installer_v0.6.2.elf"], [t.ziel for t in befund.teile])
        # Der Installer kommt zusaetzlich nach helloworld - dort liegt nur eine WebKit-ELF.
        self.assertEqual((wu.ORT_WEBKIT, wu.ORT_PAYLOADS), befund.teile[2].orte)
        self.assertEqual((wu.ORT_WEBKIT,), befund.teile[0].orte)

    def test_fehlt_der_freigabe_ein_anhang_wird_eine_aeltere_genommen(self) -> None:
        w = wu.werkzeug("webkit")
        freigaben = wu.freigaben_lesen(github_roh("itsPLK/ps5-webkit-autoloader", [
            ('v0.7.0', False, '2026-10-12', ['webkit-autoloader-host_v0.7.0.exe']),       # unvollstaendig
            ('v0.6.1', False, '2026-10-08', RELEASES["itsPLK/ps5-webkit-autoloader"][0][3])]))
        befund = wu.beurteilen(w, wu.lokale_fassung(w, self.bestand), freigaben)
        self.assertEqual(wu.STATUS_AKTUELL, befund.status)
        self.assertEqual("0.6.1", befund.neu)
        leer = wu.beurteilen(w, wu.lokale_fassung(w, self.bestand), wu.freigaben_lesen(github_roh(
            "itsPLK/ps5-webkit-autoloader", [('v0.7.0', False, '2026-10-12', ['nichts.txt'])])))
        self.assertEqual((wu.STATUS_UNKLAR, wu.MELDUNG_KEINE_DATEI), (leer.status, leer.meldung))

    def test_vorabfassungen_gelten_nur_wenn_die_tabelle_es_sagt(self) -> None:
        # ps5upload: v6.7.2 ist als Vorabfassung gekennzeichnet; neueste fertige ist v6.7.3.
        w = wu.werkzeug("ps5upload")
        self.assertFalse(w.vorab)
        freigaben = freigaben_von("phantomptr/ps5upload")
        self.assertEqual("v6.7.3", wu._kandidat(w, freigaben)[0].tag)
        # Gibt es nur Vorabfassungen (garlic-worker "latest"), gilt die oberste.
        w2 = wu.werkzeug("garlic-worker")
        self.assertEqual("latest", wu._kandidat(w2, freigaben_von("earthonion/garlic-worker"))[0].tag)
        # ShadowMount+ nimmt die Vorabfassung 1.7beta4 (die neueste), obwohl 1.7beta3 "fertig" heisst.
        w3 = wu.werkzeug("shadowmountplus")
        self.assertTrue(w3.vorab)
        self.assertEqual("1.7beta4", wu._kandidat(w3, freigaben_von("drakmor/ShadowMountPlus"))[1])
        # Ohne die Erlaubnis kaeme die aeltere heraus.
        ohne = wu.Werkzeug(**{**w3.__dict__, "vorab": False})
        self.assertEqual("1.7beta3", wu._kandidat(ohne, freigaben_von("drakmor/ShadowMountPlus"))[1])

    def test_entwuerfe_zaehlen_nie(self) -> None:
        roh = github_roh("ps5-payload-dev/elfldr", [('v9.9', False, '2026-10-12', ['elfldr-ps5.elf'])]
                         + RELEASES['ps5-payload-dev/elfldr'])
        roh[0]["draft"] = True
        w = wu.werkzeug("elfldr")
        befund = wu.beurteilen(w, wu.lokale_fassung(w, self.bestand), wu.freigaben_lesen(roh))
        self.assertEqual(("0.26", wu.STATUS_AKTUELL), (befund.neu, befund.status))

    def test_eine_unlesbare_marke_wird_uebergangen(self) -> None:
        roh = github_roh("ps5-payload-dev/elfldr", [('nightly', False, '2026-10-12', ['elfldr-ps5.elf'])]
                         + RELEASES['ps5-payload-dev/elfldr'])
        w = wu.werkzeug("elfldr")
        befund = wu.beurteilen(w, wu.lokale_fassung(w, self.bestand), wu.freigaben_lesen(roh))
        self.assertEqual("0.26", befund.neu)

    def test_eine_boese_fassung_kommt_in_keinen_dateinamen(self) -> None:
        # Im Modus "tag" ist die ganze Marke die Fassung - sie darf nie ein Pfad werden.
        w = wu.werkzeug("unified-autoloader")
        for boese in ("v1.0/../../x", "v1.0\\evil", "v1.0 evil", "v" + "1" * 80, "v1.0;rm"):
            roh = github_roh("itsPLK/ps5-unified-autoloader", [(boese, False, '2026-10-12', ['x.elf'])])
            befund = wu.beurteilen(w, wu.lokale_fassung(w, self.bestand), wu.freigaben_lesen(roh))
            self.assertEqual((), befund.teile, boese)
            self.assertNotEqual(wu.STATUS_NEU, befund.status, boese)

    def test_ohne_lesbare_lokale_fassung_ist_es_unklar(self) -> None:
        w = wu.werkzeug("elfldr")
        befund = wu.beurteilen(w, wu.Lokal(), freigaben_von("ps5-payload-dev/elfldr"))
        self.assertEqual((wu.STATUS_UNKLAR, wu.MELDUNG_LOKAL_UNLESBAR, "0.26"),
                         (befund.status, befund.meldung, befund.neu))

    def test_eine_geholte_fassung_zaehlt_als_geholt(self) -> None:
        w = wu.werkzeug("elfldr")
        bestand = bestand_aus(geholt={wu.ORT_PAYLOADS: ["elfldr-ps5_v0.27.elf"]})
        lokal = wu.lokale_fassung(w, bestand)
        self.assertEqual(("0.27", True), (lokal.fassung, lokal.geholt))
        befund = wu.beurteilen(w, lokal, freigaben_von("ps5-payload-dev/elfldr"))
        self.assertEqual((wu.STATUS_NEUER, True), (befund.status, befund.geholt))
        # Gleiche Fassung an beiden Orten: Es gilt die mitgelieferte, nichts ist "geholt".
        gleich = bestand_aus(geholt={wu.ORT_PAYLOADS: ["elfldr-ps5_v0.26.elf"]})
        self.assertFalse(wu.lokale_fassung(w, gleich).geholt)

    def test_ordner_ohne_fassung_in_der_marke_und_ohne_quelle(self) -> None:
        for schluessel in ("kstuff-drakmor", "bdj-unpatch"):
            befund = self.nach[schluessel]
            self.assertTrue(befund.seite.startswith("https://github.com/"), schluessel)
        self.assertEqual("", self.nach["appinst"].seite)

    def test_zusammenfassung_zaehlt_je_status(self) -> None:
        zaehler = wu.zusammenfassung(self.befunde)
        self.assertEqual(len(self.befunde), sum(zaehler.values()))
        # Drei Fassungen, die ihr Autor (noch) nicht so veroeffentlicht hat, dazu LibProsperoPkg 2.6.0 (Eigenbau).
        self.assertEqual(4, zaehler.get(wu.STATUS_NEUER))
        self.assertEqual(1, zaehler.get(wu.STATUS_UNKLAR))                 # DPI v2: keine Freigabe
        self.assertEqual(10, zaehler.get(wu.STATUS_OHNE_QUELLE))           # davon YT-Blocker (Sammlung, kein Einzel-ELF)
        self.assertGreaterEqual(zaehler.get(wu.STATUS_NEU_HINWEIS, 0), 1)  # 7-Zip 26.04
        self.assertNotIn(wu.STATUS_FEHLER, zaehler)
        self.assertNotIn(wu.STATUS_NEU, zaehler)


class EngineTests(unittest.TestCase):
    """Die Werkzeuge, bei denen nur gemeldet wird - mit selbst gebauten Ordnern."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="wu_engines_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _bestand(self) -> "wu.Bestand":
        return wu.Bestand(wurzeln=[self.tmp])

    def test_ordnername_nimmt_die_hoechste(self) -> None:
        for name in ("7-Zip-26.00", "7-Zip-9.20", "7-Zip-26.10"):
            os.makedirs(os.path.join(self.tmp, name))
        self.assertEqual("26.10", wu.lokale_fassung(wu.werkzeug("7zip"), self._bestand()).fassung)

    def test_neuere_freigabe_eines_ordner_werkzeugs_wird_gemeldet_nicht_geladen(self) -> None:
        os.makedirs(os.path.join(self.tmp, "7-Zip-26.00"))
        w = wu.werkzeug("7zip")
        befund = wu.beurteilen(w, wu.lokale_fassung(w, self._bestand()), freigaben_von("ip7z/7zip"))
        self.assertEqual((wu.STATUS_NEU_HINWEIS, "26.00", "26.04"), (befund.status, befund.lokal, befund.neu))
        self.assertFalse(befund.ladbar)
        self.assertEqual((), befund.teile)
        self.assertTrue(befund.seite.startswith("https://github.com/"))

    def test_json_fassung(self) -> None:
        os.makedirs(os.path.join(self.tmp, "ProsperoPkg-2.5"))
        pfad = os.path.join(self.tmp, "ProsperoPkg-2.5", "fassung.json")
        Path(pfad).write_bytes(b"\xef\xbb\xbf" + json.dumps({"fassung": "2.6.0"}).encode("utf-8"))   # mit BOM
        w = wu.werkzeug("prosperopkg")
        lokal = wu.lokale_fassung(w, self._bestand())
        self.assertEqual("2.6.0", lokal.fassung)
        befund = wu.beurteilen(w, lokal, freigaben_von("SvenGDK/LibProsperoPkg"))
        self.assertEqual(wu.STATUS_NEUER, befund.status)         # eigener Bau aus neuerem Quelltext
        Path(pfad).write_text("kein json", encoding="utf-8")
        self.assertEqual("", wu.lokale_fassung(w, self._bestand()).fassung)

    def test_text_und_fest(self) -> None:
        os.makedirs(os.path.join(self.tmp, "Eins"))
        Path(self.tmp, "Eins", "info.txt").write_text("Fassung: 3.4.5 vom Montag", encoding="utf-8")
        text = wu.Werkzeug("t", "T", wu.GRUPPE_WERKZEUG, "a/b", ordner="Eins", art=wu.ART_HINWEIS,
                           lokal=r"text:info.txt:Fassung:\s*(\d+(?:\.\d+)+)")
        self.assertEqual("3.4.5", wu.lokale_fassung(text, self._bestand()).fassung)
        fest = wu.Werkzeug("f", "F", wu.GRUPPE_WERKZEUG, "a/b", art=wu.ART_HINWEIS, lokal="fest:7.1")
        self.assertEqual("7.1", wu.lokale_fassung(fest, self._bestand()).fassung)
        leer = wu.Werkzeug("l", "L", wu.GRUPPE_WERKZEUG, "a/b", art=wu.ART_HINWEIS, lokal="fest:")
        self.assertEqual("", wu.lokale_fassung(leer, self._bestand()).fassung)

    def test_ordner_mit_eckigen_klammern_im_namen(self) -> None:
        # glob.glob haette "[test]" als Zeichenvorrat gelesen und nichts gefunden.
        wurzel = os.path.join(self.tmp, "[test] Programm")
        os.makedirs(os.path.join(wurzel, "MkPFS-1.1.0"))
        bestand = wu.Bestand(wurzeln=[wurzel])
        self.assertEqual("1.1.0", wu.lokale_fassung(wu.werkzeug("mkpfs"), bestand).fassung)

    def test_ordner_in_unterordner(self) -> None:
        os.makedirs(os.path.join(self.tmp, "helloworld", "unjail-ps5app-payload-1.2"))
        self.assertEqual("1.2", wu.lokale_fassung(wu.werkzeug("unjail"), self._bestand()).fassung)
        self.assertEqual("", wu.lokale_fassung(wu.werkzeug("unjail"), wu.Bestand(wurzeln=[self.tmp + "x"])).fassung)


# ---------------------------------------------------------------------------
# Pruefen: Zwischenspeicher, ETag, Anfragegrenze
# ---------------------------------------------------------------------------
class PruefenTests(unittest.TestCase):

    def setUp(self) -> None:
        self.bestand = bestand_aus()
        self.werkzeuge = [wu.werkzeug(s) for s in ("elfldr", "ftpsrv", "ps5upload", "dpiv2", "cooling")]

    def _pruefen(self, netz, speicher=None, **opt):
        return wu.pruefen(self.werkzeuge, self.bestand, netz, speicher, heute="2026-10-10", **opt)

    def test_jede_quelle_wird_einmal_gefragt(self) -> None:
        netz = FakeNetz()
        gesamt = []
        befunde, speicher = self._pruefen(netz, melden=lambda art, **w: gesamt.append((art, w["fertig"], w["gesamt"])))
        self.assertEqual(sorted(wu.quellen(self.werkzeuge)), sorted(q for q, _ in netz.gefragt))
        self.assertEqual(5, len(netz.gefragt))
        self.assertEqual([("pruefe", n, 5) for n in range(1, 6)], sorted(gesamt))
        self.assertEqual(sorted(wu.quellen(self.werkzeuge)), sorted(speicher))
        self.assertEqual(len(befunde), len(self.werkzeuge))

    def test_die_zweite_pruefung_fragt_mit_etag_und_bekommt_304(self) -> None:
        erste = FakeNetz()
        _b, speicher = self._pruefen(erste)
        for quelle, eintrag in speicher.items():
            self.assertTrue(eintrag["etag"].startswith('W/"'), quelle)
            self.assertEqual("2026-10-10", eintrag["stand"])
        zweite = FakeNetz()
        befunde2, speicher2 = self._pruefen(zweite, speicher)
        self.assertTrue(all(etag for _q, etag in zweite.gefragt), "Alle Anfragen tragen den ETag")
        # Das Urteil ist dasselbe, der Zwischenspeicher bleibt, nur der Stand wird erneuert.
        self.assertEqual([b.status for b in self._pruefen(FakeNetz())[0]], [b.status for b in befunde2])
        for quelle in speicher:
            self.assertEqual(speicher[quelle]["etag"], speicher2[quelle]["etag"])
            self.assertEqual(speicher[quelle]["freigaben"], speicher2[quelle]["freigaben"])
        # Frisch bestaetigt: kein Stand, keine Meldung - ausser dem Grund eines "unklar" (DPI v2 hat keine Freigabe).
        self.assertTrue(all(b.stand == "" for b in befunde2))
        self.assertTrue(all(b.meldung == "" for b in befunde2 if b.status != wu.STATUS_UNKLAR))

    def test_der_zwischenspeicher_des_aufrufers_bleibt_unveraendert(self) -> None:
        speicher: dict = {}
        self._pruefen(FakeNetz(), speicher)
        self.assertEqual({}, speicher)

    def test_die_anfragegrenze_wird_gemeldet_und_der_gespeicherte_stand_gilt(self) -> None:
        _b, speicher = self._pruefen(FakeNetz())
        gesperrt = FakeNetz(ausfaelle={q: wu.Antwort(429, "", "", 1760000000) for q in wu.quellen(self.werkzeuge)})
        befunde, _neu = self._pruefen(gesperrt, {q: {**e, "stand": "2026-10-09"} for q, e in speicher.items()})
        for b in befunde:
            if b.werkzeug.schluessel == "dpiv2":
                continue
            self.assertEqual(wu.MELDUNG_LIMIT, b.meldung, b.werkzeug.schluessel)
            self.assertEqual("1760000000", b.detail)
            self.assertEqual("2026-10-09", b.stand)
            self.assertIn(b.status, (wu.STATUS_AKTUELL, wu.STATUS_NEUER), "Urteil aus dem Stand von gestern")

    def test_ohne_gespeicherten_stand_ist_eine_gesperrte_quelle_ein_fehler(self) -> None:
        gesperrt = FakeNetz(ausfaelle={"ps5-payload-dev/elfldr": wu.Antwort(429, "", "", 0)})
        befunde, speicher = self._pruefen(gesperrt)
        elfldr = befunde[0]
        self.assertEqual((wu.STATUS_FEHLER, wu.MELDUNG_LIMIT, ""), (elfldr.status, elfldr.meldung, elfldr.stand))
        self.assertNotIn("ps5-payload-dev/elfldr", speicher, "Eine gescheiterte Abfrage wird nicht gespeichert")
        self.assertEqual(wu.STATUS_AKTUELL, befunde[1].status, "Die uebrigen Quellen sind davon nicht betroffen")

    def test_die_anfragegrenze_nennt_den_zeitpunkt_der_freigabe(self) -> None:
        gesperrt = FakeNetz(ausfaelle={"ps5-payload-dev/elfldr": wu.Antwort(429, "", "", 1760000000)})
        elfldr = self._pruefen(gesperrt)[0][0]
        self.assertEqual((wu.MELDUNG_LIMIT, "1760000000"), (elfldr.meldung, elfldr.detail))

    def test_ein_403_ohne_anfragegrenze_ist_ein_netzfehler_mit_code(self) -> None:
        # Ein gesperrtes Projekt oder eine Firewall ist keine Anfragegrenze: "Warte bis ..." waere die falsche Auskunft.
        netz = FakeNetz(ausfaelle={"ps5-payload-dev/elfldr": wu.Antwort(403, "", "", 0)})
        elfldr = self._pruefen(netz)[0][0]
        self.assertEqual((wu.STATUS_FEHLER, wu.MELDUNG_NETZ, "403"), (elfldr.status, elfldr.meldung, elfldr.detail))

    def test_der_zwischenspeicher_wird_auf_die_gefragten_quellen_beschnitten(self) -> None:
        _b, speicher = self._pruefen(FakeNetz())
        mit_altlast = {**speicher, "frueher/gefragt": {"etag": 'W/"x"', "stand": "2026-01-01", "freigaben": []}}
        _b2, neu = self._pruefen(FakeNetz(), mit_altlast)
        self.assertEqual(sorted(speicher), sorted(neu), "Was nicht mehr gefragt wird, bleibt nicht liegen")
        self.assertIn("frueher/gefragt", mit_altlast, "Der Speicher des Aufrufers bleibt unveraendert")

    def test_eine_gesperrte_quelle_behaelt_ihren_eintrag_im_zwischenspeicher(self) -> None:
        _b, speicher = self._pruefen(FakeNetz())
        gesperrt = FakeNetz(ausfaelle={q: wu.Antwort(429, "", "", 0) for q in wu.quellen(self.werkzeuge)})
        _b2, neu = self._pruefen(gesperrt, speicher)
        self.assertEqual(speicher, neu, "Eine Sperre loescht den gemerkten Stand nicht")

    def test_netzfehler_und_andere_antworten(self) -> None:
        netz = FakeNetz(ausfaelle={"ps5-payload-dev/elfldr": OSError("Name or service not known"),
                                   "ps5-payload-dev/ftpsrv": wu.Antwort(500),
                                   "phantomptr/ps5upload": wu.Antwort(200, "<html>Wartung</html>", "x"),
                                   "OnionBuddies/onionHEN-dpiv2-plugin": wu.Antwort(404)})
        befunde, speicher = self._pruefen(netz)
        elfldr, ftpsrv, upload, dpiv2, _cooling = befunde
        self.assertEqual((wu.STATUS_FEHLER, wu.MELDUNG_NETZ), (elfldr.status, elfldr.meldung))
        self.assertIn("Name or service", elfldr.detail)
        self.assertEqual((wu.STATUS_FEHLER, wu.MELDUNG_NETZ, "500"), (ftpsrv.status, ftpsrv.meldung, ftpsrv.detail))
        self.assertEqual((wu.STATUS_FEHLER, wu.MELDUNG_ANTWORT), (upload.status, upload.meldung))
        self.assertEqual((wu.STATUS_FEHLER, wu.MELDUNG_NICHT_GEFUNDEN), (dpiv2.status, dpiv2.meldung))
        self.assertEqual(["strongt1me/ps5-cooling-system-center-pro"], sorted(speicher))

    def test_abbrechen_fragt_nichts_mehr(self) -> None:
        abbruch = threading.Event()
        abbruch.set()
        netz = FakeNetz()
        befunde, _s = self._pruefen(netz, abbruch=abbruch)
        self.assertEqual([], netz.gefragt)
        self.assertTrue(all(b.status == wu.STATUS_FEHLER and b.meldung == wu.MELDUNG_ABGEBROCHEN for b in befunde))

    def test_eine_leere_freigabenliste_ist_kein_fehler(self) -> None:
        befunde, speicher = self._pruefen(FakeNetz())
        dpiv2 = befunde[3]
        self.assertEqual((wu.STATUS_UNKLAR, wu.MELDUNG_KEINE_FREIGABE), (dpiv2.status, dpiv2.meldung))
        self.assertIn("OnionBuddies/onionHEN-dpiv2-plugin", speicher, "Auch 'nichts da' wird gemerkt")

    def test_eintraege_ohne_quelle_kosten_keine_anfrage(self) -> None:
        netz = FakeNetz()
        wu.pruefen([wu.werkzeug("appinst"), wu.werkzeug("bdj-unpatch"), wu.werkzeug("pizza-hen")], self.bestand, netz,
                   heute="2026-10-10")
        self.assertEqual([], netz.gefragt)

    def test_der_zwischenspeicher_ueberlebt_die_platte(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            self.assertEqual({}, wu.speicher_lesen(basis))
            _b, speicher = self._pruefen(FakeNetz())
            self.assertTrue(wu.speicher_schreiben(basis, speicher))
            self.assertEqual(speicher, wu.speicher_lesen(basis))
            self.assertEqual([wu.SPEICHER_DATEI], os.listdir(wu.update_ordner(basis)))
            Path(wu.update_ordner(basis), wu.SPEICHER_DATEI).write_text("{kaputt", encoding="utf-8")
            self.assertEqual({}, wu.speicher_lesen(basis))
            Path(wu.update_ordner(basis), wu.SPEICHER_DATEI).write_text('{"quellen": [1, 2]}', encoding="utf-8")
            self.assertEqual({}, wu.speicher_lesen(basis))

    def test_der_zwischenspeicher_ist_nicht_schreibbar(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            sperre = os.path.join(basis, wu.UNTERORDNER)
            Path(sperre).write_text("ich bin eine Datei, kein Ordner", encoding="utf-8")
            self.assertFalse(wu.speicher_schreiben(basis, {"a/b": {}}))

    def test_neu_beurteilen_braucht_kein_netz_und_behaelt_die_meldung(self) -> None:
        befunde, speicher = self._pruefen(FakeNetz())
        elfldr = befunde[0]
        bestand = bestand_aus(geholt={wu.ORT_PAYLOADS: ["elfldr-ps5_v0.27.elf"]})
        neu = wu.neu_beurteilen(elfldr, bestand, speicher)
        self.assertEqual((wu.STATUS_NEUER, "0.27", True), (neu.status, neu.lokal, neu.geholt))
        mit_meldung = wu.neu_beurteilen(wu.Befund(werkzeug=elfldr.werkzeug, status=wu.STATUS_AKTUELL,
                                                  meldung=wu.MELDUNG_LIMIT, detail="123", stand="2026-10-09"),
                                        self.bestand, speicher)
        self.assertEqual((wu.MELDUNG_LIMIT, "123", "2026-10-09"), (mit_meldung.meldung, mit_meldung.detail,
                                                                   mit_meldung.stand))


class AmprTests(unittest.TestCase):

    def test_der_bestand_ist_aktuell(self) -> None:
        w = wu.werkzeug("ampr-emu")
        befund = wu.beurteilen_emu(w, freigaben_von("drakmor/ampr_emu"), "", "", AMPR, "")
        self.assertEqual((wu.STATUS_AKTUELL, "0.4.2.1", "0.4.2.1"), (befund.status, befund.lokal, befund.neu))
        self.assertEqual((), befund.ampr)

    def test_fehlende_varianten_werden_angeboten(self) -> None:
        w = wu.werkzeug("ampr-emu")
        befund = wu.beurteilen_emu(w, freigaben_von("drakmor/ampr_emu"), "", "", [("0.3.6.2", "no debug")], "")
        self.assertEqual(wu.STATUS_NEU, befund.status)
        self.assertTrue(befund.ladbar)
        self.assertEqual("0.4.2.1", befund.neu, "Angezeigt wird die neueste Freigabe")
        self.assertIn("0.4.2.1", {a.fassung for a in befund.ampr})
        self.assertGreater(befund.groesse, 0)

    def test_was_schon_im_ordner_liegt_wird_nicht_nochmal_angeboten(self) -> None:
        w = wu.werkzeug("ampr-emu")
        with tempfile.TemporaryDirectory() as ordner:
            erst = wu.beurteilen_emu(w, freigaben_von("drakmor/ampr_emu"), "", "", [("0.3.6.2", "no debug")], ordner)
            netz = FakeNetz()
            abgelegt, fehler = wu.holen_emu(erst, ordner, netz)
            self.assertEqual([], fehler)
            self.assertEqual(len(erst.ampr), len(abgelegt))
            self.assertTrue(all(os.path.isfile(p) for p in abgelegt))
            nochmal = wu.beurteilen_emu(w, freigaben_von("drakmor/ampr_emu"), "", "", [("0.3.6.2", "no debug")], ordner)
            self.assertEqual(wu.STATUS_AKTUELL, nochmal.status)

    def test_fehler_und_leere_antwort(self) -> None:
        w = wu.werkzeug("ampr-emu")
        self.assertEqual(wu.STATUS_FEHLER, wu.beurteilen_emu(w, None, wu.MELDUNG_NETZ).status)
        leer = wu.beurteilen_emu(w, [], "", "", AMPR, "")
        self.assertEqual((wu.STATUS_UNKLAR, wu.MELDUNG_KEINE_DATEI), (leer.status, leer.meldung))

    def test_fremde_adressen_werden_nicht_geholt(self) -> None:
        w = wu.werkzeug("ampr-emu")
        roh = github_roh("drakmor/ampr_emu")
        for freigabe in roh:
            for anhang in freigabe["assets"]:
                anhang["browser_download_url"] = "https://boese.example/" + anhang["name"]
        befund = wu.beurteilen_emu(w, wu.freigaben_lesen(roh), "", "", [("0.3.6.2", "no debug")], "")
        netz = FakeNetz()
        with tempfile.TemporaryDirectory() as ordner:
            abgelegt, fehler = wu.holen_emu(befund, ordner, netz)
            self.assertEqual([], os.listdir(ordner))
        self.assertEqual([], abgelegt)
        self.assertEqual(1, len(fehler))
        self.assertEqual([], netz.geladen)


# ---------------------------------------------------------------------------
# Holen
# ---------------------------------------------------------------------------
def befund_fuer(schluessel: str, neu_roh: list, bestand=None) -> "wu.Befund":
    """Ein ladbarer Befund: das Werkzeug mit einer erfundenen neueren Freigabe."""
    w = wu.werkzeug(schluessel)
    freigaben = wu.freigaben_lesen(github_roh(w.quelle, neu_roh))
    befund = wu.beurteilen(w, wu.lokale_fassung(w, bestand or bestand_aus()), freigaben)
    assert befund.ladbar, (schluessel, befund)
    return befund


class HolenTests(unittest.TestCase):

    def setUp(self) -> None:
        self.basis = tempfile.mkdtemp(prefix="wu_basis_")
        self.addCleanup(shutil.rmtree, self.basis, ignore_errors=True)
        self.elfldr = befund_fuer("elfldr", [('v0.27', False, '2026-10-12', ['elfldr-ps5.elf'])])
        self.webkit = befund_fuer("webkit", [('v0.6.2', False, '2026-10-12', [
            'webkit-autoloader-host_v0.6.2.exe', 'webkit-autoloader-host_v0.6.2.py',
            'webkit-autoloader-installer_v0.6.2.elf'])])

    def _alle_dateien(self) -> list[str]:
        erg = []
        for wurzel, _ordner, dateien in os.walk(self.basis):
            erg.extend(os.path.relpath(os.path.join(wurzel, d), self.basis).replace("\\", "/") for d in dateien)
        return sorted(erg)

    def test_eine_datei_kommt_an_ihren_platz(self) -> None:
        netz = FakeNetz()
        meldungen = []
        ergebnis = wu.holen([self.elfldr], self.basis, netz, lambda art, **w: meldungen.append((art, w)))
        ziel = os.path.join(self.basis, wu.UNTERORDNER, "helloworld", "elfldr-ps5_v0.27.elf")
        self.assertEqual([ziel], ergebnis.abgelegt)
        self.assertEqual(["elfldr"], ergebnis.fertig)
        self.assertEqual(inhalt("elfldr-ps5.elf"), Path(ziel).read_bytes())
        self.assertEqual(([], []), (ergebnis.fehler, ergebnis.ohne_summe))
        self.assertEqual(["Werkzeug-Updates/helloworld/elfldr-ps5_v0.27.elf"], self._alle_dateien(),
                         "Nichts Zusaetzliches: keine Zwischendatei bleibt liegen")
        self.assertIn("hole", [a for a, _w in meldungen])
        self.assertIn(("abgelegt", {"name": "elfldr", "text": ziel}), meldungen)

    def test_nach_dem_holen_gilt_die_geholte_als_vorhanden(self) -> None:
        wu.holen([self.elfldr], self.basis, FakeNetz())
        bestand = bestand_aus(geholt={wu.ORT_PAYLOADS: wu.geholte_dateien(self.basis, wu.ORT_PAYLOADS)})
        self.assertEqual(["elfldr-ps5_v0.27.elf"], bestand.geholt[wu.ORT_PAYLOADS])
        lokal = wu.lokale_fassung(wu.werkzeug("elfldr"), bestand)
        self.assertEqual(("0.27", True), (lokal.fassung, lokal.geholt))
        self.assertEqual([], wu.geholte_dateien(self.basis, wu.ORT_WEBKIT))
        self.assertEqual([], wu.geholte_dateien("", wu.ORT_PAYLOADS))

    def test_mehrteilig_alles_an_alle_orte(self) -> None:
        ergebnis = wu.holen([self.webkit], self.basis, FakeNetz())
        self.assertEqual([], ergebnis.fehler)
        self.assertEqual(sorted([
            "Werkzeug-Updates/PS5 WebKit Autoloader/webkit-autoloader-host_v0.6.2.exe",
            "Werkzeug-Updates/PS5 WebKit Autoloader/webkit-autoloader-host_v0.6.2.py",
            "Werkzeug-Updates/PS5 WebKit Autoloader/webkit-autoloader-installer_v0.6.2.elf",
            "Werkzeug-Updates/helloworld/webkit-autoloader-installer_v0.6.2.elf"]), self._alle_dateien())
        self.assertEqual(4, len(ergebnis.abgelegt))

    def test_mehrteilig_ganz_oder_gar_nicht(self) -> None:
        netz = FakeNetz()
        netz.verfaelscht.add(self.webkit.teile[2].adresse)           # der dritte Teil ist beschaedigt
        ergebnis = wu.holen([self.webkit], self.basis, netz)
        self.assertEqual([], ergebnis.abgelegt)
        self.assertEqual(1, len(ergebnis.fehler))
        self.assertIn("SHA-256", ergebnis.fehler[0])
        self.assertEqual([], self._alle_dateien(), "Auch die zwei guten Teile bleiben draussen, und nichts liegt herum")

    def test_ein_fehler_haelt_die_uebrigen_nicht_auf(self) -> None:
        netz = FakeNetz()
        netz.verfaelscht.add(self.elfldr.teile[0].adresse)
        ergebnis = wu.holen([self.elfldr, self.webkit], self.basis, netz)
        self.assertEqual(["WebKit Autoloader"], ergebnis.fertig)
        self.assertEqual(1, len(ergebnis.fehler))
        self.assertTrue(ergebnis.fehler[0].startswith("elfldr:"))

    def test_die_groesse_wird_geprueft(self) -> None:
        w = wu.werkzeug("elfldr")
        roh = github_roh(w.quelle, [('v0.27', False, '2026-10-12', ['elfldr-ps5.elf'])])
        roh[0]["assets"][0]["size"] += 5
        befund = wu.beurteilen(w, wu.lokale_fassung(w, bestand_aus()), wu.freigaben_lesen(roh))
        ergebnis = wu.holen([befund], self.basis, FakeNetz())
        self.assertEqual([], ergebnis.abgelegt)
        self.assertIn("Bytes", ergebnis.fehler[0])

    def test_ohne_digest_zaehlt_die_danebenliegende_pruefsumme(self) -> None:
        w = wu.werkzeug("anypad")
        neu = [('v0.9.0-beta', False, '2026-10-12', ['AnyPad-PS5-0.9.0-beta.elf', 'AnyPad-PS5-0.9.0-beta.elf.sha256'])]
        befund = wu.beurteilen(w, wu.lokale_fassung(w, bestand_aus()),
                               wu.freigaben_lesen(github_roh(w.quelle, neu)))
        (teil,) = befund.teile
        self.assertEqual("", teil.digest)
        self.assertTrue(teil.pruefsumme_adresse.endswith("AnyPad-PS5-0.9.0-beta.elf.sha256"))
        ergebnis = wu.holen([befund], self.basis, FakeNetz())
        self.assertEqual(([], []), (ergebnis.fehler, ergebnis.ohne_summe))
        self.assertEqual(1, len(ergebnis.abgelegt))

    def test_eine_falsche_danebenliegende_pruefsumme_haelt_die_datei_zurueck(self) -> None:
        w = wu.werkzeug("anypad")
        neu = [('v0.9.0-beta', False, '2026-10-12', ['AnyPad-PS5-0.9.0-beta.elf', 'AnyPad-PS5-0.9.0-beta.elf.sha256'])]
        befund = wu.beurteilen(w, wu.lokale_fassung(w, bestand_aus()),
                               wu.freigaben_lesen(github_roh(w.quelle, neu)))
        netz = FakeNetz()
        netz.verfaelscht.add(befund.teile[0].adresse)
        ergebnis = wu.holen([befund], self.basis, netz)
        self.assertEqual([], ergebnis.abgelegt)
        self.assertEqual([], self._alle_dateien())

    def test_ganz_ohne_pruefsumme_wird_es_gesagt(self) -> None:
        w = wu.werkzeug("elfldr")
        roh = github_roh(w.quelle, [('v0.27', False, '2026-10-12', ['elfldr-ps5.elf'])])
        roh[0]["assets"][0]["digest"] = ""
        befund = wu.beurteilen(w, wu.lokale_fassung(w, bestand_aus()), wu.freigaben_lesen(roh))
        meldungen = []
        ergebnis = wu.holen([befund], self.basis, FakeNetz(), lambda art, **wert: meldungen.append((art, wert)))
        self.assertEqual(["elfldr-ps5_v0.27.elf"], ergebnis.ohne_summe)
        self.assertEqual(1, len(ergebnis.abgelegt), "Die Groesse stimmt - geholt wird trotzdem, aber nicht stumm")
        self.assertIn(("ohne_summe", {"name": "elfldr", "text": "elfldr-ps5_v0.27.elf"}), meldungen)

    def test_fremde_adressen_werden_nie_geholt(self) -> None:
        for adresse in ("http://github.com/x/y.elf", "https://github.com.boese.example/x.elf",
                        "https://example.com/elfldr.elf", "ftp://github.com/x.elf", "file:///C:/Windows/x.elf", ""):
            teil = self.elfldr.teile[0]
            gefaelscht = wu.Befund(werkzeug=self.elfldr.werkzeug, status=wu.STATUS_NEU,
                                   teile=(wu.Teil(teil.anhang, teil.ziel, teil.orte, adresse, teil.groesse,
                                                  teil.digest),))
            netz = FakeNetz()
            ergebnis = wu.holen([gefaelscht], self.basis, netz)
            self.assertEqual([], netz.geladen, adresse)
            self.assertEqual(1, len(ergebnis.fehler), adresse)
            self.assertEqual([], self._alle_dateien(), adresse)

    def test_boese_zielnamen_werden_nie_geschrieben(self) -> None:
        for ziel in ("..\\..\\evil.elf", "../evil.elf", "unter/ordner.elf", ".versteckt.elf", "evil.dll", "evil.bat",
                     "", "C:\\evil.elf", "evil.elf\\"):
            teil = self.elfldr.teile[0]
            gefaelscht = wu.Befund(werkzeug=self.elfldr.werkzeug, status=wu.STATUS_NEU,
                                   teile=(wu.Teil(teil.anhang, ziel, teil.orte, teil.adresse, teil.groesse,
                                                  teil.digest),))
            netz = FakeNetz()
            ergebnis = wu.holen([gefaelscht], self.basis, netz)
            self.assertEqual([], netz.geladen, repr(ziel))
            self.assertEqual(1, len(ergebnis.fehler), repr(ziel))
            self.assertEqual([], self._alle_dateien(), repr(ziel))

    def test_ein_ort_ausserhalb_der_tabelle_wird_nie_beschrieben(self) -> None:
        teil = self.elfldr.teile[0]
        gefaelscht = wu.Befund(werkzeug=self.elfldr.werkzeug, status=wu.STATUS_NEU,
                               teile=(wu.Teil(teil.anhang, teil.ziel, ("..", "helloworld"), teil.adresse,
                                              teil.groesse, teil.digest),))
        ergebnis = wu.holen([gefaelscht], self.basis, FakeNetz())
        self.assertEqual(1, len(ergebnis.fehler))
        self.assertEqual([], self._alle_dateien())

    def test_abbrechen_mitten_im_holen_hinterlaesst_nichts(self) -> None:
        abbruch = threading.Event()
        netz = FakeNetz()
        original = netz.laden

        def laden_und_abbrechen(adresse, pfad, fortschritt=None, abbruch_=None):
            ergebnis = original(adresse, pfad, fortschritt, abbruch_)
            abbruch.set()                                   # nach dem ersten Teil
            return ergebnis

        netz.laden = laden_und_abbrechen
        ergebnis = wu.holen([self.webkit, self.elfldr], self.basis, netz, abbruch=abbruch)
        self.assertTrue(ergebnis.abgebrochen)
        self.assertEqual([], ergebnis.abgelegt)
        self.assertEqual([], self._alle_dateien())
        self.assertEqual(1, len(netz.geladen), "Nach dem Abbruch wird nichts mehr geladen")

    def test_nicht_ladbare_befunde_werden_uebergangen(self) -> None:
        netz = FakeNetz()
        aktuell = wu.Befund(werkzeug=wu.werkzeug("elfldr"), status=wu.STATUS_AKTUELL)
        hinweis = wu.Befund(werkzeug=wu.werkzeug("7zip"), status=wu.STATUS_NEU_HINWEIS)
        ergebnis = wu.holen([aktuell, hinweis], self.basis, netz)
        self.assertEqual(([], [], []), (ergebnis.abgelegt, ergebnis.fehler, netz.geladen))
        self.assertFalse(os.path.exists(wu.update_ordner(self.basis)), "Ohne Arbeit wird nichts angelegt")

    def test_zu_grosse_dateien_werden_abgewiesen(self) -> None:
        with mock.patch.object(wu, "GRENZE_BYTES", 64):
            antwort = mock.MagicMock()
            antwort.headers = {"Content-Length": "5000"}
            antwort.__enter__.return_value = antwort
            with mock.patch.object(wu.urllib.request, "urlopen", return_value=antwort):
                with tempfile.TemporaryDirectory() as ordner, self.assertRaises(ValueError):
                    wu.Netz().laden("https://github.com/a/b", os.path.join(ordner, "x.teil"))

    def test_eine_geholte_datei_ersetzt_nur_ihre_fruehere_gleichen_namens(self) -> None:
        wu.holen([self.elfldr], self.basis, FakeNetz())
        ziel = os.path.join(self.basis, wu.UNTERORDNER, "helloworld", "elfldr-ps5_v0.27.elf")
        Path(ziel).write_bytes(b"alt")
        wu.holen([self.elfldr], self.basis, FakeNetz())
        self.assertEqual(inhalt("elfldr-ps5.elf"), Path(ziel).read_bytes())

    def test_ziel_und_adresse_pruefungen(self) -> None:
        self.assertTrue(wu.ziel_erlaubt("pkgmgr_v1.5.0.elf"))
        self.assertTrue(wu.ziel_erlaubt("webkit-autoloader-host_v0.6.1.exe"))
        self.assertTrue(wu.ziel_erlaubt("webkit-autoloader-host_v0.6.1.py"))
        for schlecht in ("", "a/b.elf", "a\\b.elf", ".x.elf", "x.zip", "x.sh", "x"):
            self.assertFalse(wu.ziel_erlaubt(schlecht), schlecht)
        self.assertTrue(wu.adresse_erlaubt("https://github.com/a/b/releases/download/v1/x.elf"))
        self.assertTrue(wu.adresse_erlaubt("https://codeberg.org/a/b/releases/download/v1/x.elf"))
        for schlecht in ("http://github.com/a", "https://evil.example/github.com/", "", None, "github.com/a"):
            self.assertFalse(wu.adresse_erlaubt(schlecht), schlecht)


# ---------------------------------------------------------------------------
# Der Update-Ordner im Programm
# ---------------------------------------------------------------------------
class UpdateOrdnerTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="wu_ordner_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.eins = os.path.join(self.tmp, "mitgeliefert")
        self.zwei = os.path.join(self.tmp, "geholt")
        os.makedirs(self.eins)
        os.makedirs(self.zwei)

    def _legen(self, ordner: str, *namen: str) -> None:
        for name in namen:
            Path(ordner, name).write_bytes(b"x")

    def test_die_hoechste_fassung_ueber_beide_ordner(self) -> None:
        self._legen(self.eins, "ftpsrv-ps5_v0.21.1.elf", "ftpsrv-ps5_v1.16-ng-stable.elf")
        self._legen(self.zwei, "ftpsrv-ps5_v1.9.elf")
        self.assertEqual(os.path.join(self.eins, "ftpsrv-ps5_v1.16-ng-stable.elf"),
                         wu.beste_datei("ftpsrv-ps5*.elf", [self.eins, self.zwei]))
        self._legen(self.zwei, "ftpsrv-ps5_v1.17.elf")
        self.assertEqual(os.path.join(self.zwei, "ftpsrv-ps5_v1.17.elf"),
                         wu.beste_datei("ftpsrv-ps5*.elf", [self.eins, self.zwei]))

    def test_zehn_kommt_nach_neun_und_ohne_unterstrich_v(self) -> None:
        self._legen(self.eins, "ps5upload-6.9.0.elf", "ps5upload-6.10.0.elf")
        self.assertEqual(os.path.join(self.eins, "ps5upload-6.10.0.elf"),
                         wu.beste_datei("ps5upload-*.elf", [self.eins, self.zwei]))

    def test_bei_gleichem_namen_gewinnt_der_vordere_ordner(self) -> None:
        self._legen(self.eins, "elfldr-ps5_v0.26.elf")
        self._legen(self.zwei, "elfldr-ps5_v0.26.elf")
        self.assertEqual(os.path.join(self.eins, "elfldr-ps5_v0.26.elf"),
                         wu.beste_datei("elfldr-ps5_v*.elf", [self.eins, self.zwei]))

    def test_fehlende_ordner_und_leere_muster(self) -> None:
        self.assertEqual("", wu.beste_datei("*.elf", [os.path.join(self.tmp, "gibt-es-nicht"), ""]))
        self.assertEqual("", wu.beste_datei("", [self.eins]))
        self._legen(self.zwei, "x_v1.elf")
        self.assertEqual(os.path.join(self.zwei, "x_v1.elf"),
                         wu.beste_datei("x_v*.elf", [os.path.join(self.tmp, "gibt-es-nicht"), self.zwei]))

    def test_gross_und_kleinschreibung_wie_unter_windows(self) -> None:
        self._legen(self.eins, "OnionHEN_v0.0.13.elf")
        self.assertEqual(os.path.join(self.eins, "OnionHEN_v0.0.13.elf"),
                         wu.beste_datei("onionhen_v*.elf", [self.eins]))

    def test_zwischendateien_zaehlen_nie(self) -> None:
        self._legen(self.zwei, "elfldr-ps5_v0.27.elf.teil", ".abc.teil")
        self.assertEqual("", wu.beste_datei("elfldr*", [self.zwei]))
        self.assertEqual([], wu._dateien_in(self.zwei))

    def test_bestand_lesen(self) -> None:
        hello = os.path.join(self.tmp, "helloworld")
        os.makedirs(hello)
        self._legen(hello, "a_v1.elf")
        os.makedirs(os.path.join(self.tmp, wu.UNTERORDNER, "helloworld"))
        self._legen(os.path.join(self.tmp, wu.UNTERORDNER, "helloworld"), "a_v2.elf")
        bestand = wu.bestand_lesen(lambda ort: os.path.join(self.tmp, ort), self.tmp)
        self.assertEqual({"helloworld": ["a_v1.elf"]}, bestand.mitgeliefert)
        self.assertEqual(["a_v2.elf"], bestand.geholt["helloworld"])
        self.assertEqual([], bestand.geholt[wu.ORT_WEBKIT])
        self.assertEqual([os.path.abspath(self.tmp)], bestand.wurzeln)

    def test_bestand_lesen_ueberlebt_einen_fehler_beim_finden(self) -> None:
        def kaputt(_ort):
            raise RuntimeError("kaputt")
        bestand = wu.bestand_lesen(kaputt, self.tmp)
        self.assertEqual(({}, []), (bestand.mitgeliefert, bestand.wurzeln))


# ---------------------------------------------------------------------------
# Das echte Netz - mit nachgebautem urlopen
# ---------------------------------------------------------------------------
class _Antwort(io.BytesIO):
    def __init__(self, daten: bytes, kopf: dict | None = None, status: int = 200) -> None:
        super().__init__(daten)
        self.headers = kopf or {}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _fehler(code: int, kopf: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.github.com/x", code, "x", kopf or {}, io.BytesIO(b""))


class NetzTests(unittest.TestCase):

    def test_abfragen_sendet_agent_etag_und_liest_antwort(self) -> None:
        gesehen = {}

        def urlopen(anfrage, timeout=None):
            gesehen.update(url=anfrage.full_url, kopf={k.lower(): v for k, v in anfrage.header_items()},
                           frist=timeout)
            return _Antwort(b"[]", {"ETag": 'W/"x1"'})

        with mock.patch.object(wu.urllib.request, "urlopen", urlopen):
            antwort = wu.Netz().abfragen("ps5-payload-dev/elfldr", 'W/"alt"')
        self.assertEqual((200, "[]", 'W/"x1"'), (antwort.status, antwort.text, antwort.etag))
        self.assertTrue(gesehen["url"].startswith("https://api.github.com/repos/ps5-payload-dev/elfldr/releases"))
        self.assertEqual("PS5DumpImageConverter", gesehen["kopf"]["user-agent"])
        self.assertEqual('W/"alt"', gesehen["kopf"]["if-none-match"])
        self.assertTrue(gesehen["frist"], "Ohne Zeitgrenze liesse eine haengende Verbindung das Fenster warten")

    def test_codeberg_geht_an_die_forgejo_schnittstelle(self) -> None:
        gesehen = {}

        def urlopen(anfrage, timeout=None):
            gesehen["url"] = anfrage.full_url
            return _Antwort(b"[]")

        with mock.patch.object(wu.urllib.request, "urlopen", urlopen):
            wu.Netz().abfragen("codeberg:elmonomalva0/Any-Pad-ps5")
        self.assertTrue(gesehen["url"].startswith("https://codeberg.org/api/v1/repos/elmonomalva0/Any-Pad-ps5/"))

    def test_304_ist_keine_ausnahme(self) -> None:
        with mock.patch.object(wu.urllib.request, "urlopen", side_effect=_fehler(304)):
            antwort = wu.Netz().abfragen("a/b", 'W/"x"')
        self.assertEqual((304, 'W/"x"'), (antwort.status, antwort.etag))

    def test_403_mit_leerem_kontingent_ist_die_anfragegrenze(self) -> None:
        kopf = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1760000000"}
        with mock.patch.object(wu.urllib.request, "urlopen", side_effect=_fehler(403, kopf)):
            antwort = wu.Netz().abfragen("a/b")
        self.assertEqual((429, 1760000000), (antwort.status, antwort.zuruecksetzen))
        with mock.patch.object(wu.urllib.request, "urlopen", side_effect=_fehler(403, {})):
            self.assertEqual(403, wu.Netz().abfragen("a/b").status, "Ein 403 ohne leeres Kontingent bleibt 403")
        with mock.patch.object(wu.urllib.request, "urlopen", side_effect=_fehler(404)):
            self.assertEqual(404, wu.Netz().abfragen("a/b").status)

    def test_retry_after_ist_die_zweite_anfragegrenze(self) -> None:
        # Zu viele Anfragen kurz hintereinander meldet GitHub als 403 oder 429 mit Retry-After (Sekunden).
        with mock.patch.object(wu.time, "time", return_value=1760000000.0):
            for code in (403, 429):
                with mock.patch.object(wu.urllib.request, "urlopen",
                                       side_effect=_fehler(code, {"Retry-After": "60"})):
                    antwort = wu.Netz().abfragen("a/b")
                self.assertEqual((429, 1760000060), (antwort.status, antwort.zuruecksetzen), code)

    def test_das_ende_des_kontingents_geht_dem_retry_after_vor(self) -> None:
        kopf = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1760003600", "Retry-After": "60"}
        with mock.patch.object(wu.urllib.request, "urlopen", side_effect=_fehler(403, kopf)):
            antwort = wu.Netz().abfragen("a/b")
        self.assertEqual((429, 1760003600), (antwort.status, antwort.zuruecksetzen))

    def test_andere_fehler_bleiben_ihr_code(self) -> None:
        for code, kopf in ((403, {"X-RateLimit-Remaining": "7"}), (500, {"Retry-After": "30"}),
                           (404, {"X-RateLimit-Remaining": "0"}), (429, {}), (503, {})):
            with mock.patch.object(wu.urllib.request, "urlopen", side_effect=_fehler(code, kopf)):
                antwort = wu.Netz().abfragen("a/b")
            self.assertEqual(code, antwort.status, (code, kopf))

    def test_unlesbare_kopfzeilen_sind_kein_absturz(self) -> None:
        kopf = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "bald",
                "Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}
        with mock.patch.object(wu.urllib.request, "urlopen", side_effect=_fehler(403, kopf)):
            antwort = wu.Netz().abfragen("a/b")
        self.assertEqual((429, 0), (antwort.status, antwort.zuruecksetzen))

    def test_die_schreibung_der_kopfzeilen_ist_gleichgueltig(self) -> None:
        # Ueber HTTP/2 kommen die Namen klein geschrieben; urllib reicht sie als Message weiter (ohne Gross/Klein).
        kopf = email.message.Message()
        kopf["x-ratelimit-remaining"] = "0"
        kopf["x-ratelimit-reset"] = "1760000000"
        with mock.patch.object(wu.urllib.request, "urlopen", side_effect=_fehler(403, kopf)):
            antwort = wu.Netz().abfragen("a/b")
        self.assertEqual((429, 1760000000), (antwort.status, antwort.zuruecksetzen))

    def test_netzfehler_werden_nicht_verschluckt(self) -> None:
        with mock.patch.object(wu.urllib.request, "urlopen", side_effect=urllib.error.URLError("weg")):
            with self.assertRaises(urllib.error.URLError):
                wu.Netz().abfragen("a/b")
        with self.assertRaises(ValueError):
            wu.Netz().abfragen("")

    def test_laden_schreibt_blockweise_und_rechnet_die_summe(self) -> None:
        daten = bytes(range(256)) * 2000                  # 512 000 Byte, mehrere Bloecke
        fortschritt = []
        with tempfile.TemporaryDirectory() as ordner, mock.patch.object(
                wu.urllib.request, "urlopen", return_value=_Antwort(daten, {"Content-Length": str(len(daten))})):
            ziel = os.path.join(ordner, "x.teil")
            groesse, hexsumme = wu.Netz().laden("https://github.com/a/b/x.elf", ziel,
                                                lambda f, g: fortschritt.append((f, g)))
            self.assertEqual(daten, Path(ziel).read_bytes())
        self.assertEqual((len(daten), hashlib.sha256(daten).hexdigest()), (groesse, hexsumme))
        self.assertGreater(len(fortschritt), 1)
        self.assertEqual((len(daten), len(daten)), fortschritt[-1])

    def test_laden_bricht_auf_wunsch_ab(self) -> None:
        abbruch = threading.Event()
        abbruch.set()
        with tempfile.TemporaryDirectory() as ordner, mock.patch.object(
                wu.urllib.request, "urlopen", return_value=_Antwort(b"x" * 10)):
            with self.assertRaises(wu.Abgebrochen):
                wu.Netz().laden("https://github.com/a/b/x.elf", os.path.join(ordner, "x.teil"), abbruch=abbruch)

    def test_laden_ohne_laengenangabe_zaehlt_mit(self) -> None:
        with mock.patch.object(wu, "GRENZE_BYTES", 100), mock.patch.object(
                wu.urllib.request, "urlopen", return_value=_Antwort(b"y" * 1000)):
            with tempfile.TemporaryDirectory() as ordner, self.assertRaises(ValueError):
                wu.Netz().laden("https://github.com/a/b/x.elf", os.path.join(ordner, "x.teil"))

    def test_bytes_hat_eine_grenze(self) -> None:
        with mock.patch.object(wu.urllib.request, "urlopen", return_value=_Antwort(b"abc")):
            self.assertEqual(b"abc", wu.Netz().bytes("https://github.com/a/b/x.sha256"))
        with mock.patch.object(wu.urllib.request, "urlopen", return_value=_Antwort(b"a" * 100)):
            with self.assertRaises(ValueError):
                wu.Netz().bytes("https://github.com/a/b/x.sha256", grenze=10)

    def test_nichts_in_diesem_modul_fragt_von_selbst(self) -> None:
        # "Netzzugriff nur auf Knopfdruck": Das Importieren und das Urteilen duerfen nie ins Netz gehen.
        with mock.patch.object(wu.urllib.request, "urlopen") as urlopen, \
                mock.patch("socket.create_connection") as verbindung:
            wu.pruefen([wu.werkzeug("appinst")], bestand_aus(), FakeNetz(), heute="2026-10-10")
            wu.beurteilen(wu.werkzeug("elfldr"), wu.Lokal("0.26"), freigaben_von("ps5-payload-dev/elfldr"))
            wu.lokale_fassung(wu.werkzeug("elfldr"), bestand_aus())
            wu.abgedeckte_dateien(HELLOWORLD)
        urlopen.assert_not_called()
        verbindung.assert_not_called()

    def test_urlopen_steht_nur_in_der_klasse_netz(self) -> None:
        # "Wer wissen will, was das Programm sendet, muss nur hierher sehen."
        import ast
        baum = ast.parse(Path(wu.__file__).read_text(encoding="utf-8"))
        insgesamt = sum(1 for k in ast.walk(baum) if isinstance(k, ast.Attribute) and k.attr == "urlopen")
        in_netz = sum(1 for klasse in baum.body if isinstance(klasse, ast.ClassDef) and klasse.name == "Netz"
                      for k in ast.walk(klasse) if isinstance(k, ast.Attribute) and k.attr == "urlopen")
        self.assertGreaterEqual(insgesamt, 3)
        self.assertEqual(insgesamt, in_netz, "urlopen ausserhalb der Klasse Netz")


if __name__ == "__main__":
    unittest.main()
