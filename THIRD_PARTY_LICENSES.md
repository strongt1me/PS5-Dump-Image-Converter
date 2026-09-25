# Lizenzen mitgelieferter Fremdkomponenten

Diese Datei führt die Komponenten auf, die zusammen mit dem PS5 Dump & Image
Converter ausgeliefert und in die Windows-EXE eingebettet werden. Sie ist
Bestandteil jeder Weitergabe des Programms.

Das Programm selbst steht unter der MIT-Lizenz; ihr Text steht in der Datei
[LICENSE](LICENSE), die ebenfalls jeder Weitergabe beiliegt. Für die hier
aufgeführten Komponenten gilt sie nicht – für sie gelten ihre eigenen Lizenzen.

Weitere im Programm verwendete oder verlinkte Projekte sind im Fenster **CREDITS**
sowie im Abschnitt „Referenzen" der [README.md](README.md) aufgeführt. Für Werkzeuge,
die nicht mitgeliefert, sondern nur heruntergeladen oder verlinkt werden, gelten die
Bedingungen der jeweiligen Anbieter.

> **Zur Herkunft der Namen:** Die unten genannten Autorinnen und Autoren stammen aus
> den Dateien selbst – aus Copyright-Zeilen, Credit-Bannern und Projektadressen, die
> im jeweiligen Payload hinterlegt sind – oder aus der Dokumentation des Projekts.
> Wo sich kein Beleg finden ließ, steht das Projekt ohne Zuordnung. Lieber eine
> Lücke als eine falsche Zuschreibung; Hinweise auf fehlende Nennungen sind
> ausdrücklich willkommen.

---

## Payloads im Ordner `helloworld/`

Alle Dateien werden unverändert in der Form weitergegeben, in der ihre Autoren sie
veröffentlicht haben. Es gelten deren jeweilige Lizenzbedingungen. Wer einzelne
Payloads weiterverteilt, sollte die Bedingungen des jeweiligen Projekts prüfen.

Den Wortlaut der GNU General Public License 3.0 enthält
`helloworld/LICENSE-GPL-3.0.txt` – der unveränderte Text der Free Software
Foundation. Er gilt für die Zeilen unten, die GPL-3.0 oder GPL-3.0-or-later
nennen: PS5 PKG Manager, ActRemoteLink (Agent und PIN-Anzeige), OnionHEN und
unjail-ps5app-payload. Wo der Quelltext des jeweiligen Projekts zu finden ist,
steht in seiner Zeile.

| Datei | Projekt | Autor / Herkunft | Beleg |
| --- | --- | --- | --- |
| `ftpsrv-ps5_v0.21.1.elf` | ftpsrv | ps5-payload-dev | Projektadresse im ELF |
| `ftpsrv-ps5_v1.15-ng.elf` | ftpsrv-ng | John Törnblom & drakmor | Copyright- und Bannerzeile |
| `ftpsrv-ps5_v1.16-ng-stable.elf` | ftpsrv-ng | John Törnblom & drakmor | Copyright- und Bannerzeile; geladen aus dem Release 1.16-ng-stable |
| `klogsrv-ps5_v0.9.elf` | klogsrv | John Törnblom | Copyright-Zeile im ELF |
| `websrv-ps5_v0.34.elf` | websrv | ps5-payload-dev | SDK-Adresse im ELF |
| `OffAct_v0.34.elf` | OffAct | ps5-payload-dev | Projektadresse im ELF |
| `ps5-app-dumper_v1.11_Beta.elf` | ps5-app-dumper | ps5-payload-dev | Projektreihe |
| `np-fake-signin-v1.3.elf` | NP Fake Signin | earthonion | „NP Fake Signin (by earthonion)" |
| `garlic-savemgr_v1.13.1.elf` | GarlicSaves Save-Manager | earthonion | Sponsorenlink im ELF |
| `shadowmountplus_v1.7beta1.elf` | ShadowMount+ | drakmor; Dank an VoidWhisper, Gezine, earthonion, EchoStretch | Bannerzeile im ELF; aus dem Release 1.7beta1 |
| `nanodns_v0.4.elf` | nanodns | drakmor | „(c) Drakmor" |
| `game-compressor_v1.0.4.elf` | PS5 Game Compressor | Juma Sayeh | „Built by Juma Sayeh" |
| `pldmgr_v0.5.1.elf` | PS5 Payload Manager | itsPLK | Projektadresse im ELF |
| `pkgmgr_v1.2.4.elf` | PS5 PKG Manager | itsPLK | `github.com/itsPLK/ps5-pkg-manager` im ELF; GPL-3.0 (LICENSE im Quellarchiv des Projekts); beim Autor heißt die Datei „pkg-manager_v1.2.4.elf“ |
| `actremotelink_agent_v2.0.elf` | ActRemoteLink (Agent) | francoataffarel; Dank an earthonion (np-fake-signin) | `github.com/francoataffarel/ActRemoteLink`, GPL-3.0-or-later (README des Projekts); Fassung aus `VERSION`; Bauten: `https://github.com/francoataffarel/ActRemoteLink/releases/download/v2.0/ActRemoteLink.zip`, Quelltext: Tag `v2.0` des Projekts |
| `actremotelink_pin_notify_v2.0.elf` | ActRemoteLink (PIN-Anzeige) | francoataffarel | dasselbe Projekt, dieselbe Lizenz und derselbe Download wie die Zeile darüber |
| `ps5debug-NG_v1.3.2.elf` | ps5debug-NG | OpenSourcereR; Dank an golden, Ctn, SiSTRo, EchoStretch | „Coded by OpenSourcereR"; geladen aus dem Release 1.3.2 (Pharaoh2k/ps5debug-NG) |
| `elfldr-ps5_v0.26.elf` | elfldr | ps5-payload-dev (John Törnblom) | Quelldateiname `elfldr.c` im ELF; geladen aus dem Release v0.26 |
| `web-file-mgr-v1.9.elf` | PS5 Web File Manager | owendswang | „Web File Manager / Version: … / Port: …" im ELF |
| `webkit-autoloader-installer_v0.4.0.elf` | PS5 WebKit Autoloader (Installer) | itsPLK | „Autoloader Installer v… by PLK" im ELF |
| `ProsperoMgr.elf` | Prospero Manager | – | „Prospero Manager" im ELF, kein Autorenname |
| `CheatRunner_v0.17.elf` | CheatRunner | maj0r | „CheatRunner v0.17 by maj0r" |
| `zftpd-ps5-v1.5.0.elf` | zftpd | seregonwar | Projektadresse, MIT-Lizenz (unten) |
| `zftpd-ps5-zhttp-v1.5.0.elf` | zftpd (zhttp-Variante) | seregonwar | Projektadresse, MIT-Lizenz (unten) |
| `bdj_unpatch_1340.elf` | Y2JB-P2JB-bdj_unpatch | owendswang | im Fenster CREDITS verlinkt |
| `PIZZA-HEN-v2.00.elf` | PIZZA-HEN | – | kein Beleg in der Datei |
| `bfpilot_v0.4.4.elf` | bfpilot | – | kein Beleg in der Datei |
| `dump_installer_v1.07.elf` | Dump Installer | – | kein Beleg in der Datei |
| `kstuff_lite_v1.11_Beta.elf` | kstuff lite | EchoStretch | Release v1.11 von `github.com/EchoStretch/kstuff-lite` (Prüfsumme gleich); im ELF der Quellpfad `drakmor/kstuff-lite` |
| `kstuff_lite_v1.2-dr_Beta2.elf` | kstuff lite | – | kein Beleg in der Datei |
| `ps5upload-5.33.2.elf` | PS5Upload | phantomptr | Eigenname `ps5upload` im ELF; geladen aus dem Release v5.33.2 |
| `OnionHEN_v0.0.13.elf` | OnionHEN | – | GPL-3.0 (LICENSE im Projekt-ZIP) |
| `unjail-ps5app-payload.elf` | unjail-ps5app-payload | SvenGDK | GPL-3.0 (Lizenztext + Quellcode in `helloworld/unjail-ps5app-payload-1.0/`) |

Weitere Payload-Sammlungen und Werkzeuge, die im Fenster **CREDITS** verlinkt sind:
**aldostools** (PS5-Payloads), **owendswang** (Autoloader, bdj_unpatch),
**soniciso** (ELF Arsenal), **Gezine**, **EchoStretch**, **drakmor**, **itsPLK**,
**seregonwar** und **ps5-payload-dev**.

---

## zftpd (seregonwar)

Projektseite: https://github.com/seregonwar/zftpd

Zero-Copy-FTP/HTTP-Daemon in C11. Auf Konsolen lauscht er standardmäßig auf
Port 2120; die Variante `zhttp` stellt zusätzlich einen HTTP-Dateiexplorer auf
demselben Port bereit. Startoptionen: `-p <PORT>`, `-d <VERZEICHNIS>`.

> **Hinweis zum Einsatz in diesem Programm:** Für Übertragungen zur Konsole wird
> seit v1.8.38 **ftpsrv auf Port 2121** verwendet. zftpd legt Dateien ohne
> Ausführungsrecht ab (`0666`); hochgeladene Spiele starten damit nicht. Der
> Payload bleibt beigelegt, wird aber nicht mehr vorgeschlagen.

```
MIT License

Copyright (c) 2026 Seregon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Weitere eingebettete Bestandteile

| Bestandteil | Herkunft | Verwendung im Programm |
| --- | --- | --- |
| **MkPFS 1.0.0** | PSBrew / Renan Barreto (@RenanGBarreto) | PFS-Verarbeitung – die Kern-Engine für `.ffpfs`/`.ffpfsc` |
| **LibProsperoPkg 2.6.0** | SvenGDK | Das Werkzeug hinter „PKG bauen“; liegt als `prosperopkg` für vier Plattformen bei (GPL-3.0). Der Ordner heißt noch `ProsperoPkg-2.5` – maßgeblich ist `ProsperoPkg-2.5/fassung.json` |
| **PS4 FFPFSC 0.2.9** | siehe `PS4FFPFSC-0.2.9/UPSTREAM.md` | PS4-Pakete nach `.ffpfsc` (GPL-3.0-or-later); bringt eigene Fremdbestandteile mit, deren Lizenzen in `PS4FFPFSC-0.2.9/LICENSES/` liegen |
| **PS5 Wee Tools 0.1.8** | andy-man ([ps5-wee-tools](https://github.com/andy-man/ps5-wee-tools)) | Werkzeug für den NOR-Flash der Konsole (GPL-3.0); unverändert mitgeliefert und als eigenständiges Programm gestartet (WEITERE TOOLS). Quelltext, Lizenz und Herkunft in `PS5-Wee-Tools-0.1.8/` (`LICENSE`, `UPSTREAM.md`, `herkunft.json`) |
| **UFS2Tool** | SvenGDK und Mitwirkende | Erzeugen und Prüfen der UFS2-Struktur in `.ffpkg` – **hier für Dateien >2 GB gepatcht** (`UFS2Tool-4.1/patch/`); trägt die .NET-Laufzeit in sich, siehe eigenen Abschnitt unten |
| **AMPR EMU** | drakmor / Roman Tarasov (`drakmor/ampr_emu`, GPL-3.0-or-later – Copyright-Zeile im Quellprojekt) | Aufgabe 7: Ersatzmodul für den APR-Dateiresolver. Mitgeliefert sind gebaute `libSceAmpr.sprx` mehrerer Fassungen; der Quellcode liegt öffentlich unter https://github.com/drakmor/ampr_emu |
| **AMPR PackTools 4.0** | drakmor / Roman Tarasov – aus der AMPR-EMU-Ausgabe `ampr-emu-0.4.2.1-fix` (Ordner `ampr-pack-tools-windows-x64`) | Baut, prüft und entpackt die Asset-Packs (`.pak`) für den AMPR EMU; liegt als Python-Werkzeug in `AMPR_PackTools-4.0/` bei, mit `USER_GUIDE_EN.md` und `BUILD_INFO.txt`. Das Packformat nutzt LZ4 – dessen Lizenztext liegt daneben (`LICENSE-LZ4.txt`: `lib/` BSD-2-Clause, sonst GPL-2.0-or-later) |
| **libScePlayGo-Stub (pgo_stub) 0.5** | PS5-Homebrew-Community (GPL-3.0) | Aufgabe 7: meldet PlayGo-Inhalte als vollständig installiert; Quellcode und Lizenztext liegen unter `PlayGo & AMPR_EMU/PlayGo_v0.5/Quellcode/` bei |
| **PS5-AppInstall (`appinst.elf`)** | abgeleitet vom Beispiel `samples/install_app` des **PS5 Payload SDK** von **John Törnblom** | Das Werkzeug „App direkt installieren“ schickt es an die Konsole und registriert die Anwendung. GPL-3.0-or-later; Quelltext `appinst.c`, Herkunft und die Abweichungen vom Vorbild in `PS5-AppInstall/NOTICE.md` |
| **Ersatzbibliotheken für BACKPORT** | PS5 BackPork Kitchen | Firmware-Profile 4.00 bis 7.00 im Ordner `Backport_Fakelibs/` |
| **PS5 WebKit Autoloader 0.4.0** | itsPLK ([ps5-webkit-autoloader](https://github.com/itsPLK/ps5-webkit-autoloader)) | Legt eine Kachel auf den Startbildschirm der Konsole; liegt als Host, Skript und Installer bei |
| **Hintergrundbilder** | für dieses Programm erstellt | Haupt- und Sidebar-Hintergründe |

---

---

## Die .NET-Laufzeit von Microsoft in `UFS2Tool`

UFS2Tool selbst steht unter BSD-2-Clause. Die hier gebündelte Fassung ist
zusätzlich **gepatcht** – streamendes Entpacken für Dateien über 2 GB
(`Ufs2Image.ReadFileToStream`, behebt die int32-Grenze beim `.ffpkg`-Auspacken);
geänderte Quelle und Beschreibung liegen in `UFS2Tool-4.1/patch/`. Es ist hier
aber **eigenständig** gebaut – `dotnet publish --self-contained true -p:PublishSingleFile=true`,
siehe `UFS2Tool-4.1/pruefsummen.json` – und trägt Microsofts **.NET-10-**
**Laufzeit damit in der Programmdatei**. Am 17.09.2026 an den neuen
Binärdateien nachgemessen:

| Bau | Größe | `System.Private.CoreLib` | `coreclr` |
| --- | --- | --- | --- |
| `win-x64` | 12,7 MB | 62× | 17× |
| `linux-x64` | 14,3 MB | 56× | 13× |
| `osx-x64` | 13,8 MB | 56× | 75× |
| `osx-arm64` | 13,0 MB | 56× | 78× |

Eingebettet ist die Fassung **10.0.11**.

**Warum .NET 10.** Bis zum 17.09.2026 steckte hier **8.0.30**. Microsofts
Unterstützung für .NET 8 endet am **10.11.2026**; danach gäbe es für die
mitgelieferte Laufzeit keine Sicherheitskorrekturen mehr. .NET 10 ist LTS und
wird bis zum **14.11.2028** gepflegt. Neu gebaut wurde aus derselben Quelle
(UFS2Tool 4.1.0) mit demselben Patch, nur mit `TargetFramework net10.0`;
Einzelheiten in `UFS2Tool-4.1/patch/PATCH.md`. Das mitgelieferte ProsperoPkg
verlangt ohnehin bereits .NET 10.

**Nicht überall MIT.** Der Quellcode von .NET steht unter der MIT-Lizenz, die
**Windows-Binärdateien** aber unter einem eigenen Vertrag. Microsoft sagt das
selbst in `dotnet/core/license-information.md`: „On Linux and macOS: MIT
license" – „On Windows: .NET Library License". Für die drei Nicht-Windows-
Bauten oben gilt also MIT, für `win-x64` die **.NET Library License**. Wer
sich auf die MIT-Angabe der NuGet-Pakete stützt, liegt für Windows falsch;
dieser Widerspruch ist bei Microsoft als `dotnet/runtime` Issue #108905
gemeldet und war beim Nachsehen am 03.09.2026 offen.

Die Weitergabe ist **ausdrücklich erlaubt** (.NET Library License §3.a,
„Distributable Code"), solange das eigene Programm dem etwas Eigenes
hinzufügt – was hier der Fall ist. Die Laufzeit wird unverändert
weitergegeben.

**Keine weiteren Sonderbedingungen.** Issue #108905 nennt vier Dateien mit
eigenen Verträgen – `D3DCompiler_47_cor3.dll` (Windows SDK License) und
`vcruntime140_cor3.dll` (Visual C++ Runtime License) unter ihnen. Am
03.09.2026 im .NET-8-Bau und am 17.09.2026 erneut in allen vier .NET-10-Bauten
nachgesehen: **keine davon ist enthalten.** Das Bündel gibt Namen
unverschleiert preis – `System.Private.CoreLib` steht 62× darin –, die
Abwesenheit ist also ein Befund und kein Messfehler. UFS2Tool
ist ein Konsolenprogramm ohne Oberfläche; die betroffenen Dateien gehören
zur Desktop-Beilage, die hier nicht mitkommt.

**Nicht betroffen:** `ProsperoPkg-2.5` ist bewusst framework-abhängig gebaut
(`--self-contained false`) und enthält keine Laufzeit – nachgemessen: 1,3 MB
je Plattform, keine einzige `coreclr`-Marke. Es verlangt ein installiertes
.NET 10 und sagt das beim Fehlen auch. Ebenso wenig betroffen sind `MkPFS`
und `PS4FFPFSC`; beide bringen ihre eigenen Lizenztexte mit.

Quellen, am 03.09.2026 geprüft:
[license-information.md](https://github.com/dotnet/core/blob/main/license-information.md) ·
[license-information-windows.md](https://github.com/dotnet/core/blob/main/license-information-windows.md) ·
[Issue #108905](https://github.com/dotnet/runtime/issues/108905) ·
[.NET Library License](https://dotnet.microsoft.com/en-us/dotnet_library_license.htm)

## Verfahren, die nachgebaut wurden

Kein Fremdcode, aber fremde Vorarbeit – ohne die es die Funktion **BACKPORT**
nicht gäbe:

| Person / Projekt | Beitrag |
| --- | --- |
| **BestPig** | BackPork – Verfahren und Starter `ps5-backpork.elf` |
| **idlesauce** | ursprüngliches Downgrade-Skript |
| **John Törnblom** | `make_fself.py` – Signieren von ELF zu SELF |
| **CyB1K** | SelfUtil, dessen Entpackverfahren hier nachgebaut ist |
| **PS5 BackPork Kitchen** | Vorlage für Firmware-Profile und Ersatzbibliotheken |

---

## Verwendete Python-Bibliotheken

Diese Bibliotheken werden in die EXE eingebettet; es gelten ihre jeweiligen Lizenzen:

**Pillow**, **cryptography**, **zstandard**, **zlib-ng**, **tkinterdnd2**, **psutil**,
**lz4** (für die Asset-Packs des AMPR EMU) und **pyserial** (BSD-3-Clause, für PS5 Wee Tools)
sowie **PyInstaller** für den Bau der Windows-EXE.

---

## Genutzte Onlinequelle

**prosperopatches.com** – dorthin wird auf ausdrückliche Rückfrage die Title-ID
gesendet, um bei fehlender oder defekter `param.json` Titel und Content-ID
nachzuschlagen. Die Frage ist auf **Nein** voreingestellt; ohne Zustimmung
verlässt keine Angabe den Rechner.
