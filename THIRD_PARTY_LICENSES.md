# Lizenzen mitgelieferter Fremdkomponenten

Diese Datei führt die Komponenten auf, die zusammen mit dem PS5 Dump & Image
Converter ausgeliefert und in die Windows-EXE eingebettet werden. Sie ist
Bestandteil jeder Weitergabe des Programms.

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

| Datei | Projekt | Autor / Herkunft | Beleg |
| --- | --- | --- | --- |
| `ftpsrv-ps5_v0.21.elf` | ftpsrv | ps5-payload-dev | Projektadresse im ELF |
| `ftpsrv-ps5_v1.15-ng.elf` | ftpsrv-ng | John Törnblom & drakmor | Copyright- und Bannerzeile |
| `ftpsrv-ps5_v1.16-ng.elf` | ftpsrv-ng | John Törnblom & drakmor | Copyright- und Bannerzeile |
| `klogsrv-ps5_v0.9.elf` | klogsrv | John Törnblom | Copyright-Zeile im ELF |
| `websrv-ps5_v0.34.elf` | websrv | ps5-payload-dev | SDK-Adresse im ELF |
| `OffAct_v0.34.elf` | OffAct | ps5-payload-dev | Projektadresse im ELF |
| `ps5-app-dumper_v1.11_Beta.elf` | ps5-app-dumper | ps5-payload-dev | Projektreihe |
| `np-fake-signin-v1.3.elf` | NP Fake Signin | earthonion | „NP Fake Signin (by earthonion)" |
| `garlic-savemgr_v1.12.elf` | GarlicSaves Save-Manager | earthonion | Sponsorenlink im ELF |
| `shadowmountplus_v1.7_Beta6.elf` | ShadowMount+ | drakmor; Dank an VoidWhisper, Gezine, earthonion, EchoStretch | Bannerzeile im ELF |
| `nanodns_v0.4.elf` | nanodns | drakmor | „(c) Drakmor" |
| `game-compressor_v1.0.3.elf` | PS5 Game Compressor | Juma Sayeh | „Built by Juma Sayeh" |
| `pldmgr_v0.5.1.elf` | PS5 Payload Manager | itsPLK | Projektadresse im ELF |
| `ps5debug-NG_1.3.0.elf` | ps5debug-NG | OpenSourcereR; Dank an golden, Ctn, SiSTRo, EchoStretch | „Coded by OpenSourcereR" |
| `CheatRunner_v0.17.elf` | CheatRunner | maj0r | „CheatRunner v0.17 by maj0r" |
| `zftpd-ps5-v1.5.0.elf` | zftpd | seregonwar | Projektadresse, MIT-Lizenz (unten) |
| `zftpd-ps5-zhttp-v1.5.0.elf` | zftpd (zhttp-Variante) | seregonwar | Projektadresse, MIT-Lizenz (unten) |
| `bdj_unpatch_1340.elf` | Y2JB-P2JB-bdj_unpatch | owendswang | im Fenster CREDITS verlinkt |
| `PIZZA-HEN-v0.1.elf` | PIZZA-HEN | – | kein Beleg in der Datei |
| `bfpilot_v0.4.4.elf` | bfpilot | – | kein Beleg in der Datei |
| `dump_installer_v1.07.elf` | Dump Installer | – | kein Beleg in der Datei |
| `kstuff_lite_v1.10_Beta.elf` | kstuff lite | – | kein Beleg in der Datei |
| `kstuff_lite_v1.2-dr_Beta2.elf` | kstuff lite | – | kein Beleg in der Datei |
| `ps5upload_v5.2.1.elf` | PS5Upload | – | kein Beleg in der Datei |
| `OnionHEN_v0.1.0.elf` | OnionHEN | – | kein Beleg in der Datei |

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
| **MkPFS 1.0.0** | Phoenixx1202 / PSBrew | PFS-Verarbeitung – die Kern-Engine für `.ffpfs`/`.ffpfsc` |
| **UFS2Tool** | SvenGDK und Mitwirkende | Erzeugen und Prüfen der UFS2-Struktur in `.ffpkg` – trägt die .NET-Laufzeit in sich, siehe eigenen Abschnitt unten |
| **AMPR EMU** | PS5-Homebrew-Community | Aufgabe 7: Ersatzmodul für den APR-Dateiresolver |
| **libScePlayGo-Stub (pgo_stub) 0.5** | PS5-Homebrew-Community | Aufgabe 7: meldet PlayGo-Inhalte als vollständig installiert |
| **Ersatzbibliotheken für BACKPORT** | PS5 BackPork Kitchen | Firmware-Profile 4.00 bis 7.00 im Ordner `Backport_Fakelibs/` |
| **Hintergrundbilder** | für dieses Programm erstellt | Haupt- und Sidebar-Hintergründe |

---

---

## Die .NET-Laufzeit von Microsoft in `UFS2Tool`

UFS2Tool selbst steht unter BSD-2-Clause. Es ist hier aber **eigenständig**
gebaut – `dotnet publish --self-contained true -p:PublishSingleFile=true`,
siehe `UFS2Tool-4.1/pruefsummen.json` – und trägt Microsofts **.NET-8-**
**Laufzeit damit in der Programmdatei**. Am 03.09.2026 an den Binärdateien
nachgemessen:

| Bau | Größe | `System.Private.CoreLib` | `coreclr` |
| --- | --- | --- | --- |
| `win-x64` | 12,5 MB | 43× | 15× |
| `linux-x64` | 13,6 MB | 28× | 16× |
| `osx-x64` | 13,5 MB | 28× | 77× |
| `osx-arm64` | 12,8 MB | 28× | 77× |

Eingebettet ist die Fassung **8.0.30**.

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
03.09.2026 im Windows-Bau nachgesehen: **keine davon ist enthalten.** Das
Bündel gibt Namen unverschleiert preis – `System.Private.CoreLib` steht 43×
darin –, die Abwesenheit ist also ein Befund und kein Messfehler. UFS2Tool
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

**Pillow**, **cryptography**, **zstandard**, **zlib-ng**, **tkinterdnd2**, **psutil**
sowie **PyInstaller** für den Bau der Windows-EXE.

---

## Genutzte Onlinequelle

**prosperopatches.com** – dorthin wird auf ausdrückliche Rückfrage die Title-ID
gesendet, um bei fehlender oder defekter `param.json` Titel und Content-ID
nachzuschlagen. Die Frage ist auf **Nein** voreingestellt; ohne Zustimmung
verlässt keine Angabe den Rechner.
