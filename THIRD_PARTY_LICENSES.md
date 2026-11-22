# Lizenzen mitgelieferter Fremdkomponenten

Diese Datei führt die Komponenten auf, die zusammen mit dem PS5 Dump & Image
Converter ausgeliefert und in die Windows-EXE eingebettet werden. Sie ist
Bestandteil jeder Weitergabe des Programms.

Das Programm selbst steht seit dem 07.10.2026 unter der GNU General Public
License, Version 3 oder (nach Wahl) jeder späteren Fassung (GPL-3.0-or-later);
der unveränderte Lizenztext steht in der Datei [LICENSE](LICENSE), die
ebenfalls jeder Weitergabe beiliegt. Fassungen bis einschließlich v1.9.64 wurden
unter der MIT-Lizenz veröffentlicht. Für die hier aufgeführten Komponenten gelten
ihre eigenen Lizenzen.

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
nennen: PS5 PKG Manager, ActRemoteLink (Agent und PIN-Anzeige), OnionHEN, DPI v2 (OnionHEN-Plugin),
unjail-ps5app-payload, Prospero Manager, WebKit Autoloader (Installer), CheatRunner,
BackPork, shsrv, gdbsrv, MemDBG, ps5-hwinfo, ps5-syslang, ps5-unified-autoloader, PoorDS4,
garlic-worker, PS5 Cooling & System Center – Pro und Home Hider (mit der eingebauten LiveShell Engine). Wo der Quelltext des jeweiligen Projekts zu finden ist, steht in seiner Zeile.

Für aria2 gilt die GNU General Public License 2.0; ihren Wortlaut – der Text aus dem Projekt,
unverändert – enthält `helloworld/LICENSE-GPL-2.0.txt`. Für SMPlusGui und den Lapy JB Daemon gilt
die MIT-Lizenz; ihre Texte stehen unten, wie bei zftpd. ps5-self-pager steht unter der Unlicense
(gemeinfrei) und knüpft nichts an die Weitergabe.

| Datei | Projekt | Autor / Herkunft | Beleg |
| --- | --- | --- | --- |
| `ftpsrv-ps5_v0.22.elf` | ftpsrv | ps5-payload-dev | Projektadresse im ELF; Release v0.22 vom 08.11.2026 (SHA-256 gegen den Release-Anhang geprüft; beim Autor heißt die Datei „ftpsrv-ps5.elf“) |
| `ftpsrv-ps5_v1.15-ng.elf` | ftpsrv-ng | John Törnblom & drakmor | Copyright- und Bannerzeile |
| `ftpsrv-ps5_v1.16-ng-stable.elf` | ftpsrv-ng | John Törnblom & drakmor | Copyright- und Bannerzeile; geladen aus dem Release 1.16-ng-stable |
| `klogsrv-ps5_v0.9.elf` | klogsrv | John Törnblom | Copyright-Zeile im ELF |
| `websrv-ps5_v0.34.elf` | websrv | ps5-payload-dev | SDK-Adresse im ELF |
| `OffAct_v0.4.2.elf` | OffAct | ps5-payload-dev | Projektadresse im ELF; geladen aus dem Release v0.4.2 (die alte Datei hieß „v0.34" - dieses Tag gab es beim Autor nie, vermutlich ein Zahlendreher) |
| `ps5-app-dumper_v2.10.elf` | ps5-app-dumper | EchoStretch | `github.com/EchoStretch/ps5-app-dumper`, Release v2.10 (SHA-256 gegen den Release-Anhang geprüft); im ELF die Fußzeile der Weboberfläche „PS5 APP DUMPER · EchoStretch · GPL-3.0“ und `"version": "2.10"`; kein LICENSE im Repo |
| `np-fake-signin-v1.3.elf` | NP Fake Signin | earthonion | „NP Fake Signin (by earthonion)" |
| `garlic-savemgr_v1.15-beta23.elf` | GarlicSaves Save-Manager | earthonion | Sponsorenlink im ELF; Release v1.15-beta23 vom 11.11.2026 (Freigabe-Notizen leer; laut Quelltext-Vergleich mit beta22: PFS-Metadaten bleiben erhalten, die Verschlüsselung des Arbeitsdienstes wird angeglichen; zuvor beta22 mit der Korrektur für Spielstände bei Copy-on-Write und Dateibesitzer) von `github.com/earthonion/garlic-savemgr` (dort heißt die Datei „garlic-savemgr.elf“), SHA-256 gegen den GitHub-Digest geprüft; Vorabfassung der Reihe 1.15, die der Autor als Release führt. Die Datei auf `git.etawen.dev/earthonion/garlic-savemgr` (Quelle der 1.14.0) war bei v1.15-beta14 anders gebaut als der GitHub-Anhang (clang 18.1.8 statt 22.1.2); mitgeliefert wird der GitHub-Bau |
| `shadowmountplus_v1.7beta12.elf` | ShadowMount+ | drakmor; Dank an VoidWhisper, Gezine, earthonion, EchoStretch, owendswang (libsmb2) und John Törnblom | Bannerzeile im ELF; aus der Vorabfassung 1.7beta12 (SHA-256 gegen den Release-Anhang geprüft); enthält für SMB-Netzfreigaben **libsmb2** (LGPL-2.1; Lizenztext und Hinweise liegen dem Release-Zip unter `licenses/` bei); beim Autor heißt die Datei „shadowmountplus.elf” |
| `nanodns_v0.4.elf` | nanodns | drakmor | „(c) Drakmor" |
| `game-compressor_v1.1.1.elf` | PS5 Game Compressor | Juma Sayeh | „Built by Juma Sayeh“ im ELF (dazu „Tested by Osama Abualia“); `github.com/juma-sayeh/PS5-Game-Compressor`, dort kein LICENSE; „v1.1.1“ im ELF; die Fassung steht auf der Release-Seite des Projekts noch nicht (Stand 03.10.2026, dort zuletzt 1.0.4), die SHA-256 stimmt mit der SHA256SUMS der Fassung überein |
| `pldmgr_v0.6.3.elf` | PS5 Payload Manager | itsPLK | Projektadresse im ELF; `github.com/itsPLK/ps5-payload-manager`, Release v0.6.3 (Hotfix gegen fehlende Emojis auf der PS5); SHA-256 gegen den Release-Anhang geprüft |
| `pkgmgr_v1.5.1.elf` | PS5 PKG Manager | itsPLK | `github.com/itsPLK/ps5-pkg-manager` im ELF (Titelzeile „PKG Manager v1.5.1 (914311f …)“); GPL-3.0 (LICENSE im Quellarchiv des Projekts); SHA-256 gegen den Release-Anhang geprüft; beim Autor heißt die Datei „pkg-manager_v1.5.1.elf“ |
| `actremotelink_agent_v2.0.elf` | ActRemoteLink (Agent) | francoataffarel; Dank an earthonion (np-fake-signin) | `github.com/francoataffarel/ActRemoteLink`, GPL-3.0-or-later (README des Projekts); Fassung aus `VERSION`; Bauten: `https://github.com/francoataffarel/ActRemoteLink/releases/download/v2.0/ActRemoteLink.zip`, Quelltext: Tag `v2.0` des Projekts |
| `actremotelink_pin_notify_v2.0.elf` | ActRemoteLink (PIN-Anzeige) | francoataffarel | dasselbe Projekt, dieselbe Lizenz und derselbe Download wie die Zeile darüber |
| `ps5debug-NG_v1.3.2.elf` | ps5debug-NG | OpenSourcereR; Dank an golden, Ctn, SiSTRo, EchoStretch | „Coded by OpenSourcereR"; geladen aus dem Release 1.3.2 (Pharaoh2k/ps5debug-NG) |
| `elfldr-ps5_v0.28.elf` | elfldr | ps5-payload-dev (John Törnblom) | Quelldateiname `elfldr.c` im ELF; geladen aus dem Release v0.28 (19.11.2026), SHA-256 gleich dem Digest des Release-Anhangs „elfldr-ps5.elf“ |
| `web-file-mgr-v1.14.elf` | PS5 Web File Manager | owendswang | „v1.14“ und die eigene Seite `http://127.0.0.1:8888/` im ELF; `github.com/owendswang/ps5-web-file-manager`, Release v1.14 vom 10.11.2026 (neu: FTP und WebDAV über „Manage Paths“, die Datei ist dadurch deutlich größer; Vollbild-Schalter nur PS5, beim Autor weiter als experimentell bezeichnet – auf Firmware 11.60 stürzt dabei laut Autor die ShellUI beim Zurückstellen ab; SHA-256 gegen den GitHub-Digest des Release-Anhangs geprüft; den dort zusätzlich angebotenen `wfm-7zip-helper` liefert das Programm nicht mit) |
| `webkit-autoloader-installer_v0.8.3.elf` | PS5 WebKit Autoloader (Installer) | itsPLK | „WebKit Autoloader v0.8.3“ im ELF; Original-Release v0.8.3 von itsPLK (GPL-3.0); SHA-256 gegen den Release-Anhang geprüft; die Datei heißt beim Autor genauso |
| `ProsperoMgr_v1.2.1.elf` | Prospero Manager | notmaj0r | `github.com/notmaj0r/ProsperoMgr`, Release v1.2.1 vom 15.11.2026, GPL-3.0 (LICENSE im Quellarchiv); SHA-256 gegen den Release-Anhang geprüft; Neuerungen laut Notizen seit v1.2: Logos für Payloads und Repositories, klarere PKG-Installation (mehrere Pakete auf einmal wählen, Prüfschritt, Grundspiel zuerst), Spiele werden am Inhalt ihres Ordners erkannt, besseres Verhalten bei Netzwechsel; Port 7070 unverändert (README des Autors nachgesehen). Vorherige Datei (unversioniert, ohne Autorenzuordnung) war dieselbe Software in einer älteren Bauart - ersetzt. Achtung: `Phoenixx1202/ProsperoMgr` ist nur ein Fork von notmaj0r, nicht die Quelle. |
| `CheatRunner_v0.18.1.elf` | CheatRunner | maj0r | „CheatRunner v0.18.1 by maj0r“ im ELF; `github.com/notmaj0r/CheatRunner`, Release v0.18.1, GPL-3.0; SHA-256 gegen den Release-Anhang geprüft |
| `ps4mount_v0.8.0.elf` | PS4Mount | gasb07 | „PS4Mount 0.8.0” und die eigene Seite `http://127.0.0.1:8770/` im ELF; `github.com/gasb07/ps4mount`, Release v0.8.0 vom 13.11.2026, GPL-3.0-or-later (README und LICENSE im Quellarchiv des Projekts; Quelltext: Tag `v0.8.0`); das ELF verwendet das PS5 Payload SDK von John Törnblom (GPL-3.0-or-later), Schlüsseldaten aus LibOrbisPkg von maxton (LGPL-3.0) und SQLite (gemeinfrei); SHA-256 gegen den Release-Anhang geprüft (Neuerungen laut Notizen seit 0.7.3: PS4Mount verschiebt keine Pakete mehr, Spiele, Updates und Add-ons laufen aus dem Ordner, in dem sie liegen, früher geordnete Bibliotheken laufen weiter; Korrekturen bei Add-ons mit großer Kopie, beim Protokoll und bei einem Spiel auf zwei Laufwerken; Port 8770 unverändert, im ELF nachgesehen); beim Autor heißt die Datei „ps4mount.elf” |
| `neo-manager_v0.7.0.elf` | NeoEnabler | gasb07 | „NeoEnabler 0.7.0” und die eigene Seite `http://127.0.0.1:8765/` im ELF; `github.com/gasb07/NeoEnabler`, Release 0.7.0, GPL-3.0 (LICENSE im Quellarchiv des Projekts); das ELF enthält die Laufzeit des PS5 Payload SDK von John Törnblom (GPL-3.0-or-later) und Teile von ps-patch-system (illusion, Apache-2.0); SHA-256 gegen den Release-Anhang geprüft; beim Autor heißt die Datei „neo-manager.elf”; braucht ps-patch-system, das vorher geladen sein muss; lädt beim Start die Spielpatches aus dem Projekt des Autors (`api.github.com`, `raw.githubusercontent.com`) und trägt sie in die Dateien von ps-patch-system ein (Sicherung unter `/data/neo-enabler/xml-backup/`) |
| `exfat2ampr.elf` | exFAT2AMPR | V-10 | `SPDX-License-Identifier: GPL-3.0-or-later` mit Zusatzbedingungen (NOTICE im Quelltext, eingebettet im ELF); `github.com/exFAT2AMPR/exfat2ampr`, Fassung 1.104 (keine Versionsnummer im Dateinamen; Fassung nur zur Laufzeit per `GET /api/state -> “version”` abrufbar); SHA-256 `ffc0956937077c29d7afdf60c9a01b62fa23034d2b50013608139b57f8b90d16`; enthält AMPR EMU 0.4.2.1 (Drakmor, GPL-3.0-or-later) eingebettet |
| `HomeHider_v2.0.0.elf` | Home Hider | Euphoric-Dev | „Home Hider“ und die eigene Seite `http://127.0.0.1:8090/` im ELF (`HOMEHIDER-ELF-VERSION=2.0.0`); `github.com/Euphoric-Dev/HomeHider`, Freigabe „HomeHider V2.0“ (Tag `RELEASE-V2`, 24.10.2026), GPL-3.0 (LICENSE und Quelltext im Quellarchiv der Freigabe, `HomeHider-v2-source.zip`); SHA-256 `d6c687dd53d54435a6710209cb0dddd00035d86edc567d494d776428d3494b82`, gleich dem Digest des Release-Anhangs; beim Autor heißt die Datei „HomeHider.elf“. Enthält unverändert die **LiveShell Engine 1.5.2** von ZiZc3 (`github.com/ZiZc3/LiveShell`, GPL-3.0; aufgebaut auf OnionHEN und dem PS5 Payload SDK von John Törnblom), die Home Hider für den Live-Hintergrund an den ELF-Loader übergibt (eigener Port 9050), sowie SQLite und stb (gemeinfrei). Schreibt in die Startbildschirm-Datenbank der Konsole (Sicherung vor jeder Änderung, laut Autor alles rückgängig zu machen); an der Konsole nicht nachgemessen |
| `kraken-mount_v0.3.1.elf` | Kraken Mount | quer3q | „kraken-mount/0.3.1“ und „web UI on port“ im ELF; `github.com/quer3q/kraken-mount`, Release v0.3.1 (20.11.2026), GPL-3.0-or-later (README und LICENSE im Projekt; laut GitHub-Schnittstelle kein Fork); SHA-256 `3ec636a6b42ceff61ac7aa47e0ed01a41be851da94cfcf3158811995ea868b27`, gleich dem Digest des Release-Anhangs und der `SHA256SUMS` des Autors; beim Autor heißt die Datei „kraken-mount.elf“. Bindet Spielordner (unverpackt, zstd, LZ4) und Debug-FPKG-Dateien ohne Installation ein und bringt laut Release-Notizen ampr-emu-ng (quer3q, GPL-3.0-or-later; in 0.3.1 die Fassung v0.5.0, im ELF byte-gleich der Freigabe des NG-Projekts nachgewiesen) mit, seit 0.3.0 außerdem dlc_emu 0.3 und pgo_stub 0.6 von drakmor (laut Release-Notizen und README; beide werden einem Spiel nur in die fakelib gelegt, wenn es keinen eigenen mitbringt); Registrierung, fakelib-Überlagerung und Backports sind laut README aus ShadowMount+ von drakmor (GPL-3.0) übernommen; gebaut mit dem PS5 Payload SDK von John Törnblom (GPL-3.0-or-later). Braucht geladenes kstuff und ein beendetes ShadowMount+ |
| `ps5-dump-forge_v0.5.7.elf` | Dump Forge | quer3q | „Dump Forge v0.5.7“ (eingebettete Seite) und `github.com/quer3q/ps5-dump-forge` im ELF; Release v0.5.7 (22.11.2026), GPL-3.0-or-later (README und LICENSE im Projekt; laut GitHub-Schnittstelle kein Fork); SHA-256 `83a7e82a9070a671953d96e4acfc909697505281e4a023a2c6411316c2c1ce6c`, gleich dem Digest des Release-Anhangs und der `SHA256SUMS` des Autors; beim Autor heißt die Datei „ps5-dump-forge-0.5.7-ps5.elf“ (hier auf das Namensschema des Ordners umbenannt). Wandelt PS5-Spielabbilder und -ordner um und bearbeitet sie (Abbild-Formate, Debug-FPKG, zstd- und LZ4-Packs); die Weboberfläche liegt auf Port 8095 und teilt ihn mit AnyPad PS5. Enthält laut README die Paket-Bausteine von ps5upload (phantomptr, GPL-3.0, `vendor/`, v7.0.22) und die Laufzeit ampr_emu 0.4.2.1 von drakmor (GPL-3.0-or-later) unverändert, seit 0.5.6 zudem die Laufzeit ampr-emu-ng (quer3q, GPL-3.0-or-later; vorher v0.3.4; in 0.5.6 die v0.4.1, dort Datei und Prüfsumme gleich der 0.4.1 im Programm, für 0.5.7 nicht erneut verglichen); ab 0.5.6 liegt jeder Freigabe ein `payloads.json` für den Payload Manager bei; weitere Hinweise (LZ4 unter BSD-2-Clause, HDE64) stehen in `THIRD-PARTY-NOTICES.md` des Projekts (die der 0.5.7 ist byte-gleich der von 0.5.6) |
| `patchdl_0.3.13.elf` | PatchDL | Knutwurst | `SPDX-License-Identifier: GPL-3.0-or-later`; Copyright 2026 Knutwurst; `github.com/knutwurst/ps5-patchdl`, Fassung 0.3.13 (Release v0.3.13); SHA-256 `257cce632b9ad701094dad3f8c0206ff87ab6b417415a57ebfd558c5ee3b0c50`, gleich dem Digest des Release-Anhangs; seit 0.3.13 mit Zusatzbedingungen nach Abschnitt 7 der GPL (Datei NOTICE im Quelltext: Urheberhinweis in der Info-Box der Einstellungsseite, Kennzeichnung veränderter Fassungen); die Datei wird unverändert weitergegeben |
| `zftpd-ps5-v1.7.0.elf` | zftpd | seregonwar | Projektadresse, MIT-Lizenz (unten); „Version 1.7.0“ im ELF; SHA-256 gegen den Release-Anhang geprüft |
| `zftpd-ps5-zhttp-v1.7.0.elf` | zftpd (zhttp-Variante) | seregonwar | Projektadresse, MIT-Lizenz (unten); „Version 1.7.0“ im ELF; SHA-256 gegen den Release-Anhang geprüft |
| `bdj_unpatch_1340.elf` | Y2JB-P2JB-bdj_unpatch | owendswang | im Fenster CREDITS verlinkt |
| `PIZZA-HEN-v2.00.elf` | PIZZA-HEN | – | kein Beleg in der Datei |
| `bfpilot_v0.4.4-multilang.elf` | bfpilot (mehrsprachige Fassung) | – | kein Beleg in der Datei |
| `dump_installer_v1.07.elf` | Dump Installer | – | kein Beleg in der Datei |
| `kstuff_lite_v1.11_Beta_EchoStretch.elf` | kstuff lite (EchoStretch-Build) | EchoStretch | Release v1.11 von `github.com/EchoStretch/kstuff-lite` |
| `kstuff_v1.13-fpkg-dr-test5.elf` | kstuff (dr) | drakmor | „Welcome To Kstuff Lite 1.13-fpkg-dr-test5“ und „By sleirsgoevy“ im ELF; „dr“ = drakmor; Fassung vom Nutzer geliefert (07.10.2026, ersetzt die frühere „Beta4“, die innen „1.13-fpkg-dr-test4“ trug); öffentlich nicht nachprüfbar – die Freigaben von `github.com/drakmor/kstuff-lite` (Fork) enden bei 1.2-dr-test2, und `drakmor/kstuff` gibt es nicht |
| `ps5upload-12.6.11.elf` | PS5Upload | phantomptr | Eigenname `ps5upload`; Release v12.6.11 vom 19.11.2026 (SHA-256 gegen den Release-Anhang geprüft; Neuerungen laut Notizen seit 12.5.1: 12.6.0 Sicherungsabgleich zwischen zwei PS5, Paket als Datei kopieren statt installieren (für Kraken Mount), Payloads kommen vom Nutzer (die App lädt sie nicht mehr selbst), 12.6.1 alle Laufwerke im Dateibrowser und ein Hinweis, wenn Kraken Mount älter als 0.2.1 ist, 12.6.2 (Vorabfassung) übersichtlichere Payload-Seite und der Hinweis, PS5-Fake-Pakete auf Firmware über 11.60 mit Kraken Mount einzuhängen, 12.6.3 vorhandenes Spiel auf der PS5 ersetzen, 12.6.4 Trophäen nach der Offline-Aktivierung und Korrekturen aus einer Prüfrunde, 12.6.5 Sicherungen auf einem PS5-Laufwerk und höhere Remote-Play-Bitrate, 12.6.7 (12.6.6 wurde nicht veröffentlicht) Paket als Datei an die PS5 senden, 12.6.8 Korrektur am Remote Play unter Linux, 12.6.9 (Vorabfassung) Gesamtprüfung von App, Engine und PS5-Hilfsdienst mit Korrekturen (Mausrad ändert keine Zahlenfelder mehr, Sicherungen, Remote Play, Cheats, Namen in älteren Kodierungen, Hochladen und Installieren), 12.6.10 (Vorabfassung) Bildrate auf Firmware 4.x und Korrekturen am Telefon, 12.6.11 Entpacken einer RAR, die nicht auf das Laufwerk passt, wird am Anfang abgelehnt (laut Autor an keiner Konsole erprobt); zuvor seit 12.4.12: 12.4.13 bis 12.4.23 (darunter Korrekturen an den Cheats, Play Together auch über IPv6, Payload-Quellen als Liste, PS5Upload von einer Konsole entfernen, zstd-Laufzeit ab 0.4.0 in neuen Packs), 12.5.1 großes Convert-Update (zstd-Packs mit ampr-emu-ng 0.4.1 für jedes PS5-Spiel, Packs in jedem Abbildformat, Umwandeln direkt aus Archiven, Abbild an Ort und Stelle ändern, Umwandeln auf der PS5 in Minion, Debug-Paket mit Kraken Mount einhängen statt installieren); davor seit 12.4.9: 12.4.10 sammelt Korrekturen aus einer Gesamtprüfung von App, Engine und PS5-Hilfsdienst (Dateiaktionen im geöffneten Ordner, Einhängen von Abbildern, Sicherungsdaten, beschädigte Pakete), 12.4.11 Remote Play und Hinweis zum Backport, 12.4.12 Sicherung auf einen anderen Benutzer wiederherstellen und Rückfrage beim Einhängen eines gepackten Spiels ohne ShadowMount+; zuvor 12.4.9, 12.4.8, 12.4.4 und die Reihe 12.4.5 bis 12.4.7 vom 10. und 11.11.2026, die der Autor jeweils am selben Tag abgelöst hat); wie 6.x bis 12.x mit dem Verbindungsprotokoll AVA1 (Port 9120 unverändert, Minion weiter auf 9180, README der Freigabe v12.6.11 nachgesehen), passt also zur PC-App ab 6.0; die PC-App 11.x meldet bei einem älteren Hilfsdienst auf der Konsole „Update the helper to play together“ (Notizen von 11.0.0) |
| `OnionHEN_v0.0.13.elf` | OnionHEN | aydencharles | Projektadresse im ELF (`github.com/aydencharles/onionHEN`); GPL-3.0 (LICENSE im Projekt); aus dem Release v0.0.13, SHA-256 gegen den Release-Anhang geprüft; beim Autor heißt die Datei „OnionHEN.elf“ |
| `OnionHEN_v0.9.0.elf` | OnionHEN | aydencharles | Projektadresse im ELF (`github.com/aydencharles/onionHEN`); GPL-3.0 (LICENSE im Projekt); aus dem Release v0.9.0 (stabile Fassung nach v0.9.0-beta1 und -beta2), SHA-256 gegen den Release-Anhang geprüft; beim Autor heißt die Datei „OnionHEN.elf“ |
| `dpiv2-13.60-1.00.elf` | DPI v2 (OnionHEN-Plugin) | OnionBuddies | „DPI v2“, „DPIV00001“ und Pfade unter `/data/OnionHEN/` im ELF; Quelltext `github.com/OnionBuddies/onionHEN-dpiv2-plugin`, GPL-3.0 (LICENSE im Projekt); beim Autor gibt es dazu keine Freigabe (keine Release-Anhänge) – die Datei hat der Nutzer geliefert, ihre SHA-256 lässt sich gegen nichts prüfen; ein Plugin für OnionHEN, das auf der Konsole im Ordner „/data/OnionHEN/plugins“ als „DPIV00001.elf“ liegt und von OnionHEN gestartet wird |
| `unjail-ps5app-payload.elf` | unjail-ps5app-payload | SvenGDK | GPL-3.0 (Lizenztext + Quellcode in `helloworld/unjail-ps5app-payload-1.2/`); aus dem Release v1.2 |
| `SMPlusGui_v1.0.1.elf` | SMPlusGui | KarnerF | „SMPlusGui by Karner“ im ELF; `github.com/KarnerF/SMPlusGui`, Release v1.0.1, MIT-Lizenz (unten); SHA-256 gegen den Release-Anhang geprüft |
| `ps5-backpork_v0.1.elf` | BackPork | BestPig; Dank an idlesauce | „Welcome To BackPork 0.1 By BestPig“ im ELF; `github.com/BestPig/BackPork`, Release 0.1, GPL-3.0; beim Autor heißt die Datei „ps5-backpork.elf“; SHA-256 gegen den Release-Anhang geprüft |
| `aria2-v1.37.0-3.elf` | aria2 für PS5 | Tatsuhiro Tsujikawa (aria2); PS5-Bau: owendswang | „Copyright (C) 2006, 2019 Tatsuhiro Tsujikawa“ im ELF; `github.com/owendswang/ps5-aria2` (GitHub-Fork von `aria2/aria2`), Release v1.37.0-3, GPL-2.0 (Wortlaut: `helloworld/LICENSE-GPL-2.0.txt`); SHA-256 gegen den Release-Anhang geprüft |
| `shsrv-ps5_v0.20.elf` | shsrv | ps5-payload-dev | `github.com/ps5-payload-dev/shsrv`, Release v0.20, GPL-3.0; kein Beleg im ELF selbst; beim Autor heißt die Datei „shsrv-ps5.elf“; SHA-256 gegen den Release-Anhang geprüft |
| `gdbsrv-ps5_v0.9.elf` | gdbsrv | John Törnblom (ps5-payload-dev) | „Copyright (C) 2025 John Törnblom“ im ELF; `github.com/ps5-payload-dev/gdbsrv`, Release v0.9, GPL-3.0; beim Autor heißt die Datei „gdbsrv-ps5.elf“; SHA-256 gegen den Release-Anhang geprüft |
| `MemDBG-ps5_nightly-20261112.elf` | MemDBG | seregonwar | „MemDBG by seregonwar“ im ELF; `github.com/seregonwar/MemDBG`, Freigabe nightly-20261112-g6e31144, GPL-3.0; beim Autor heißt die Datei „MemDBG-ps5.elf“; SHA-256 gegen den Release-Anhang geprüft |
| `ps5-self-pager-full-system_v1.2.elf` | ps5-self-pager (ganzes System) | idlesauce | `github.com/idlesauce/ps5-self-pager`, Release v1.2, Unlicense (gemeinfrei, ohne Bedingungen); kein Beleg im ELF selbst; beim Autor heißt die Datei „ps5-self-pager-full-system.elf“; SHA-256 gegen den Release-Anhang geprüft |
| `ps5-self-pager-game_v1.2.elf` | ps5-self-pager (Spiel) | idlesauce | dasselbe Projekt und dieselbe Lizenz wie die Zeile darüber; beim Autor heißt die Datei „ps5-self-pager-game.elf“ |
| `ps5-self-pager-shellcore_v1.2.elf` | ps5-self-pager (ShellCore) | idlesauce | dasselbe Projekt und dieselbe Lizenz wie oben; beim Autor heißt die Datei „ps5-self-pager-shellcore.elf“ |
| `ps5-self-pager-system-common-lib_v1.2.elf` | ps5-self-pager (Systembibliotheken) | idlesauce | dasselbe Projekt und dieselbe Lizenz wie oben; beim Autor heißt die Datei „ps5-self-pager-system-common-lib.elf“ |
| `ps5-hwinfo-sysinfo_v0.1.elf` | ps5-hwinfo (Systemdaten) | drakmor | `github.com/drakmor/ps5-hwinfo`, Release 0.1, GPL-3.0; kein Beleg im ELF selbst; beim Autor heißt die Datei „hwinfo_sysinfo.elf“; SHA-256 gegen den Release-Anhang geprüft |
| `ps5-hwinfo-bench_v0.1.elf` | ps5-hwinfo (Benchmark) | drakmor | dasselbe Projekt und dieselbe Lizenz wie die Zeile darüber; beim Autor heißt die Datei „hwinfo_bench.elf” |
| `byepervisor_reborn.elf` | Byepervisor Reborn | drakmor (Fork von PS5Dev) | Hypervisor-Exploit für FW 6.xx–13.60; `github.com/drakmor/Byepervisor-Reborn` (Fork von `PS5Dev/Byepervisor-Reborn`), GPL-3.0 (LICENSE im Projekt); kein Release vorhanden – Datei vom Nutzer eingebracht (15.10.2026); SHA-256 lässt sich gegen keinen Anhang prüfen |
| `lapy_jb_daemon-v1.2.elf` | PS5 Lapy JB Daemon | Arksama (Team PHU); Freigabe von itsPLK | `github.com/itsPLK/PS5-Lapy-JB-Daemon` (GitHub-Fork von `ArkSama/PS5-Lapy-JB-Daemon`, das selbst keine Freigabe hat), Release v1.2; MIT-Lizenz mit Bitte um Namensnennung (unten); kein Beleg im ELF selbst; SHA-256 gegen den Release-Anhang geprüft |
| `ps5-syslang-de-v0.3.elf` | ps5-syslang (Systemsprache Deutsch) | owendswang | `github.com/owendswang/ps5-syslang`, Release v0.3, GPL-3.0; kein Beleg im ELF selbst; SHA-256 gegen den Release-Anhang geprüft |
| `ps5-unified-autoloader-v0.1.7-abc3b82.elf` | ps5-unified-autoloader | itsPLK | `github.com/itsPLK/ps5-unified-autoloader`, Release v0.1.7-abc3b82, GPL-3.0; Adressen von itsPLK (Payload Manager) im ELF; SHA-256 gegen den Release-Anhang geprüft |
| `PoorDS4_rc51.elf` | PoorDS4 | ItsBlurf; baut auf Ghostcontrol von StonedModder auf | `github.com/ItsBlurf/PoorDS4` (laut NOTICE.md des Projekts ein GitHub-Fork von Ghostcontrol), Release v0.1.0-rc51, GPL-3.0 oder neuer; kein Beleg im ELF selbst; beim Autor heißt die Datei „PoorDS4rc51.elf“; SHA-256 gegen den Release-Anhang geprüft |
| `PoorDS4-status_rc51.elf` | PoorDS4 (Statusanzeige) | ItsBlurf | dasselbe Projekt und dieselbe Lizenz wie die Zeile darüber; beim Autor heißt die Datei „PoorDS4-status.elf“ |
| `PoorDS4-stop_rc51.elf` | PoorDS4 (Beenden) | ItsBlurf | dasselbe Projekt und dieselbe Lizenz wie oben; beim Autor heißt die Datei „PoorDS4-stop.elf“ |
| `garlic-worker-ps5_2026-11-18.elf` | garlic-worker | earthonion | `github.com/earthonion/garlic-worker`, Freigabe v1.6.6 vom 18.11.2026 (SHA-256 gegen den Release-Anhang geprüft; laut Notizen seit v1.5.9: v1.6.0 Copy-on-Write-Abbilder nach dem Füllen des flachen PFS mit genauer Geometrie und korrigierter Mount-Fertigstellung, v1.6.1 bis v1.6.6 chives.json und geschützte Metadaten in jedem Spielstand-Verzeichnis, Auswahl des passenden Spielstands bei Archiven mit mehreren Spielständen und kein doppeltes PS5IMAGE, PS5PARAM, PS5PARAM_SIZE und PS5KEY mehr beim Entschlüsseln (ältere Ausgaben bleiben lesbar); davor laut Quelltext-Vergleich v1.5.5 bis v1.5.9: Verschlüsselung der Spielstände angeglichen und PFS-Metadaten erhalten, Konto-ID in beiden Bytefolgen erhalten, PS5IMAGE und PS5KEY für Copy-on-Write-Spielstände beim Entschlüsseln ausgegeben; zuvor v1.5.5 vom 11.11.2026 (Korrektur bei Copy-on-Write-Verschlüsselung und PFS-Dateibesitzer), v1.5.4 vom 10.11.2026, v1.5.2 vom 09.11.2026 und „latest“ vom 30.10.2026, Build e0cbe2d), GPL-3.0; im ELF steht nur die Fassung („garlic-worker/v1.6.6“), kein Beleg für den Autor; beim Autor heißt die Datei „garlic-worker-ps5.elf“; SHA-256 gegen den Release-Anhang geprüft |
| `AnyPad-PS5-0.9.5-beta.elf` | AnyPad PS5 | elmonomalvad0 (früher als sinfiltros auf GitHub) | „0.9.5-beta“ und die eigene Seite `http://127.0.0.1:8095/` im ELF; seit Oktober 2026 auf Codeberg: `codeberg.org/elmonomalva0/Any-Pad-ps5`, Release v0.9.5-beta vom 14.10.2026 (das GitHub-Konto `sinfiltros` gibt es nicht mehr; die README nennt elmonomalvad0 als denselben Autor, und die dort erneut veröffentlichte v0.5.5-beta ist byte-gleich mit der früheren GitHub-Freigabe); GPL-3.0-or-later (README, LICENSE im Projekt); SHA-256 gegen die `.sha256`-Datei der Freigabe geprüft |
| `PS5_Cooling_System_Center_v1.88.0.elf` | PS5 Cooling & System Center – Pro | Projektinhaber (eigene Entwicklung, keine Fremdsoftware) | „PS5 Cooling & System Center - Pro 1.88.0“ und die eigene Seite `http://127.0.0.1:8086` im ELF; Release v1.88.0 vom 19.11.2026 (neu laut Notizen seit 1.86.6: 1.86.7 „Original danach“ auch bei einem von ShadowMountPlus eingehängten Spiel und Verschieben auf demselben Laufwerk ohne Kopie, 1.87.0 Spielstände auf eine andere Konsole übertragen (Knopf „Als ZIP“, PS5 und PS4), 1.88.0 Spielstände auch in der Vollbild-App über ein USB-Laufwerk, alle Spielstände eines Spiels in einem Zug und eine Prüfrunde zum sicheren Einspielen; vorher 1.86.6 „Original danach“ beim Konvertieren, Kopieren und Entpacken, eingebettetes Kraken Mount v0.3.0, `payload-manager.json` als Release-Datei) aus `github.com/strongt1me/ps5-cooling-system-center-pro` (dort Quelltext und LICENSE: GPL-3.0); SHA-256 gegen den Release-Anhang geprüft |
| `YT-Blocker_v1.4r6.elf` | YT-Blocker | Fassung 1.4: MasterPS0 (Sammlung „PS5 Host Payloads“); Methode von SvenGDK; Fassungen 1.4r3 bis 1.4r6: Nachbau, im Quelltext ohne Namen (vom Nutzer geliefert) | Am 22.11.2026 vom Nutzer als aktuellste Fassung geliefert (beim Nutzer heißt die Datei „YT-Blocker_v1.4r6_(1.00-14.22).elf“, also Firmware 1.00 bis 14.22; hier ohne Klammern abgelegt, Inhalt und SHA-256 unverändert); ersetzt die Fassung 1.4 (seit 10.10.2026 als „_13.60“ abgelegt). Zu dieser Datei gibt es keine öffentliche Freigabe. Der Quelltext v1.4r6 (`main.c`, `Makefile`, CHANGELOG bis r6) liegt beim Projektinhaber, nicht im Projekt: Kopf GPL-3.0-or-later, „Copyright (C) 2025“ ohne Namen, laut Kopf aus der kompilierten „ytblocker14.elf“ nachgebaut; die ELF neben dem Quelltext ist byte-gleich mit dieser Datei. Gegenprobe vom 22.11.2026: Die Meldungstexte des Quelltexts (samt „v1.4r6“) stehen in der ELF, und ein Neubau mit clang 21.1.8 und ps5-payload-sdk ergibt dieselben 1799 Funktionen, alle aus `main.c` und SQLite gleich groß, `.data` und `.dynstr` byte-gleich. Byte-gleich ist der Neubau nicht: Der Code ist 832 Bytes größer, nur im Startcode des SDK und in dessen `timegm`/`__secs_to_tm` (das Makefile nennt SDK v0.50; welche SDK-Fassung beim Neubau vorlag, wurde nicht abgelesen). Wie v1.4 setzt sie die Fassung der YouTube-App (PPSA01650 bis PPSA01652) in `appinfo.db` und `param.json` auf 99.999.999, nach der Anleitung „How to fully block YouTube from being updated on the PS5 when using YT2JB“ von SvenGDK (`gist.github.com/SvenGDK/6525ec4af64e45a847e35af45da46ab4`, ohne Lizenzangabe; im ELF in der Meldung „Full-Y2JB-YouTube-Block“ verlinkt). Nach dem CHANGELOG ab r3 zusätzlich `app.db` (`AppInfoJson`) und eine Sicherung nach `/data/y2jb_blocker_backup`; r6 meldet sich als Daemon („Daemon: aktiv (Patches bleiben erhalten)“), schreibt `/data/y2jb_blocker_backup/daemon.log` und patcht erneut, wenn der Wert zurückgesetzt wurde (im Quelltext ein Wächter über kqueue mit 30-Sekunden-Rückfall; Lauf auf der Konsole nicht gemessen). Gebaut mit clang 21.1.8 (1,2 MB statt 2,1 MB bei v1.4), enthält SQLite 3.50.0 (gemeinfrei), keine Pfade des Bauenden im ELF; SHA-256 `acbc4b10c2de38978fee5c901b51f542181b5b8a422064841a4633618a2a83ff` |

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
> Payload bleibt beigelegt, wird aber nicht mehr vorgeschlagen. Unter „Konsole & Payloads“
> lässt er sich weiterhin starten und zeigt dort seinen Dateibrowser (Port 2120).

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

## SMPlusGui (KarnerF)

Projektseite: https://github.com/KarnerF/SMPlusGui

Weboberfläche zum Einstellen von ShadowMount+; läuft als Payload auf der PS5 und zeigt ihre Seite dort
im Browser.

```
MIT License

Copyright (c) 2026 KarnerF

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

## PS5 Lapy JB Daemon (Arksama / Team PHU)

Projektseite: https://github.com/itsPLK/PS5-Lapy-JB-Daemon (GitHub-Fork von
https://github.com/ArkSama/PS5-Lapy-JB-Daemon)

Daemon, der die Jailbreak-auf-Abruf-Schnittstelle von etaHEN nachbildet. Der Lizenztext enthält neben der
MIT-Lizenz die Bitte um Namensnennung des ursprünglichen Autors und einen Haftungshinweis; beides ist
hier unverändert wiedergegeben.

```
MIT License

Copyright (c) 2026 Arksama (Team PHU)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

Credits to original author when re-used in derivative works appreciated.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

DISCLAIMER

This software is provided for educational and interoperability purposes only.
It is intended to be used on PS5 consoles owned by the user, on firmware
versions that have been publicly jailbroken via third-party tools.

The daemon mimics etaHEN's jailbreak-on-demand API for homebrew apps that
expect that environment. It does not bypass any DRM or grant access to
copyrighted material. Use it only with software you have the right to run.

Use of this software in ways that violate Sony's Terms of Service is at
your own risk. The authors take no responsibility for misuse.
```

---

## Weitere eingebettete Bestandteile

| Bestandteil | Herkunft | Verwendung im Programm |
| --- | --- | --- |
| **MkPFS 1.1.0** | PSBrew / Renan Barreto (@RenanGBarreto) | PFS-Verarbeitung – die Kern-Engine für `.ffpfs`/`.ffpfsc` |
| **LibProsperoPkg 2.6.0** | SvenGDK | Das Werkzeug hinter „PS4 & PS5 PKG lesen“ (bis 02.10.2026 auch hinter „PKG bauen“, das seitdem ausgebaut ist); liegt als `prosperopkg` für vier Plattformen bei (GPL-3.0). Der Ordner heißt noch `ProsperoPkg-2.5` – maßgeblich ist `ProsperoPkg-2.5/fassung.json`. **Seit 29.09.2026 mit einem eigenen Patch** (behebt einen Abbruch beim Bauen von Titeln mit vielen kleinen Dateien), geänderte Quelle und Begründung in `ProsperoPkg-2.5/patch/` |
| **OrbisPkgTool 1.0.0** | pearlxcore ([OrbisPkgTool](https://github.com/pearlxcore/OrbisPkgTool), Commit `5cd42a5`) | Die Befehlszeile hinter „PS4 PKG → OTA“: PS4-Pakete lesen, entpacken, prüfen, zusammenführen, neu packen und bauen. **MIT-Lizenz**, Text in `OrbisPkgTool-1.0.0/LICENSE`. Eigenständig gebaut und deshalb mit .NET-10-Laufzeit (siehe den Abschnitt unten), nur für Windows; **eine Änderung am Quelltext** (die Ausgabe wird als UTF-8 geschrieben), Herkunft, Bauparameter und Prüfsummen in `OrbisPkgTool-1.0.0/` (`UPSTREAM.md`, `pruefsummen.json`, `patch/`). Das **PS4 PKG Tool** von pearlxcore (GPL-3.0), das dieselbe Bibliothek benutzt, diente nur als Anregung für das Fenster – aus ihm ist kein Code übernommen |
| **PS4 FFPFSC 0.2.9** | siehe `PS4FFPFSC-0.2.9/UPSTREAM.md` | PS4-Pakete nach `.ffpfsc` (GPL-3.0-or-later); bringt eigene Fremdbestandteile mit, deren Lizenzen in `PS4FFPFSC-0.2.9/LICENSES/` liegen |
| **PS5 Wee Tools 0.1.8** | andy-man ([ps5-wee-tools](https://github.com/andy-man/ps5-wee-tools)) | Werkzeug für den NOR-Flash der Konsole (GPL-3.0); unverändert mitgeliefert und als eigenständiges Programm gestartet (WEITERE TOOLS). Quelltext, Lizenz und Herkunft in `PS5-Wee-Tools-0.1.8/` (`LICENSE`, `UPSTREAM.md`, `herkunft.json`) |
| **UFS2Tool** | SvenGDK und Mitwirkende | Erzeugen und Prüfen der UFS2-Struktur in `.ffpkg` – **hier für Dateien >2 GB gepatcht** (`UFS2Tool-4.1/patch/`); trägt die .NET-Laufzeit in sich, siehe eigenen Abschnitt unten |
| **AMPR EMU** | drakmor / Roman Tarasov (`drakmor/ampr_emu`, GPL-3.0-or-later – Copyright-Zeile im Quellprojekt) | Aufgabe 7: Ersatzmodul für den APR-Dateiresolver. Mitgeliefert sind gebaute `libSceAmpr.sprx` mehrerer Fassungen; der Quellcode liegt öffentlich unter https://github.com/drakmor/ampr_emu |
| **ampr-emu-ng 0.5.0, 0.4.1, 0.4.0-beta und 0.3.5** | quer3q (`quer3q/ampr-emu-ng`, GPL-3.0-or-later wie das Ursprungsprojekt) | Aufgabe 1 und 7: eigenständige Weiterentwicklung des AMPR EMU, in den Listen als „NG 0.5.0“, „NG 0.4.1“, „NG 0.4.0-beta“, „NG 0.3.5“, „NG 0.3.4“, „NG 0.3.3“, „NG 0.3.2“, „NG 0.3.1“, „NG 0.3.0“ und „NG 0.2.0“ geführt (je Fassung eine stille und eine Debug-Datei, unter der neuesten Fassung von drakmor einsortiert). Mitgeliefert sind die Freigabe v0.5.0 vom 20.11.2026 (Marke auf Commit d20210e) als `0.5.0 ng/libSceAmpr.sprx` (Release-Anhang `libSceAmpr.sprx`) und `0.5.0 ng-debug/libSceAmpr.sprx` (Release-Anhang `libSceAmpr-debug.sprx`), die Freigabe v0.4.1 vom 15.11.2026 (Marke auf Commit 8b61a06) als `0.4.1 ng/libSceAmpr.sprx` (Release-Anhang `libSceAmpr.sprx`) und `0.4.1 ng-debug/libSceAmpr.sprx` (Release-Anhang `libSceAmpr-debug.sprx`), die Vorabfassung „beta“ vom 14.11.2026 (Commit 54d6ac2, Anhänge von 17:36 UTC) als `0.4.0-beta ng/libSceAmpr.sprx` und `0.4.0-beta ng-debug/libSceAmpr.sprx` sowie `PlayGo & AMPR_EMU/AMPR_EMU/0.3.5 ng/libSceAmpr.sprx` (Release-Anhang `libSceAmpr.sprx`) und `0.3.5 ng-debug/libSceAmpr.sprx` (Release-Anhang `libSceAmpr-debug.sprx`) aus der Freigabe v0.3.5 vom 11.11.2026 sowie die der Freigaben v0.3.4 vom 09.11.2026 (`0.3.4 ng`, `0.3.4 ng-debug`), v0.3.3 vom 07.11.2026 (`0.3.3 ng`, `0.3.3 ng-debug`), v0.3.2 vom 06.11.2026 (`0.3.2 ng`, `0.3.2 ng-debug`), v0.3.1 vom 05.11.2026 (`0.3.1 ng`, `0.3.1 ng-debug`), v0.3.0 vom 04.11.2026 (`0.3.0 ng`, `0.3.0 ng-debug`) und v0.2.0 vom 02.11.2026 (`0.2.0 ng`, `0.2.0 ng-debug`); SHA-256 jeweils gegen den GitHub-Digest geprüft; der Quellcode liegt öffentlich unter https://github.com/quer3q/ampr-emu-ng |
| **AMPR PackTools 4.0** | drakmor / Roman Tarasov – aus der AMPR-EMU-Ausgabe `ampr-emu-0.4.2.1-fix` (Ordner `ampr-pack-tools-windows-x64`) | Baut, prüft und entpackt die Asset-Packs (`.pak`) für den AMPR EMU; liegt als Python-Werkzeug in `AMPR_PackTools-4.0/` bei, mit `USER_GUIDE_EN.md` und `BUILD_INFO.txt`. Das Packformat nutzt LZ4 – dessen Lizenztext liegt daneben (`LICENSE-LZ4.txt`: `lib/` BSD-2-Clause, sonst GPL-2.0-or-later). Seit 29.09.2026 wird daraus auch `ampr_pack_profile.py` aktiv aus dem Programm heraus aufgerufen (Mitschnitt-Assistent, eigener Selbstaufruf `--ampr-pack-profil`), nicht mehr nur mitgeliefert |
| **AMPR-Pack-Profile** (ASTRO BOT, Insomniac, Unity, EA Sports UFC 6) | danthespal ([MkPFS.CSharp](https://github.com/danthespal/MkPFS.CSharp), GPL-3.0-or-later) | Vier getestete Packprofile in `AMPR_PackTools-4.0/profiles/` (`astrobot.toml`, `insomniac.toml`, `unity.toml`, `ufc6-PPSA23566.toml`); auf echten PS5-Dumps gemessene Dateilisten und Engine-Regeln, die das Programm ab v1.9.78 automatisch einsetzt, wenn Spieltitel oder Engine erkannt werden. Die TOML-Dateien sind inhaltlich von MkPFS.CSharp abgeleitet; GPL-3.0-or-later gilt entsprechend. |
| **libScePlayGo-Stub (pgo_stub) 0.6 und 0.5** | drakmor und PS5-Homebrew-Community (GPL-3.0) | Aufgabe 7: meldet PlayGo-Inhalte als vollständig installiert; beide Fassungen liegen nebeneinander; Quellcode und Lizenztext liegen unter `PlayGo & AMPR_EMU/PlayGo_v0.6/Quellcode/` und `PlayGo_v0.5/Quellcode/` bei; 0.6 aus der Freigabe „PlayGo emu 0.6“ vom 10.10.2026 (`github.com/drakmor/pgo_stub`, SHA-256 der beiden Anhänge gegen den GitHub-Digest geprüft; die README im Quelltext nennt noch „0.5“) |
| **DLC EMU 0.3 (`dlc_emu`)** | drakmor (`drakmor/dlc_emu`, GPL-3.0; Dank an idlesauce für `ps4-eboot-dlc-patcher`) | Kästchen „DLC EMU“ beim Erstellen: drei Ersatzbibliotheken (`libSceAppContent`, `libSceNpEntitlementAccess`, `libSceGameUpdate`) in den fakelib-Ordner, dazu eine `dlc_emu.ini`; je Fassung als `log` und `nolog` unter `PlayGo & AMPR_EMU/DLC_EMU/0.3/`, mit Lizenztext und README; SHA-256 der Release-Datei `dlc_emu_0.3.zip` gegen den Digest geprüft, die Anhänge stammen unverändert daraus |
| **PS5-AppInstall (`appinst.elf`)** | abgeleitet vom Beispiel `samples/install_app` des **PS5 Payload SDK** von **John Törnblom** | Das Werkzeug „App direkt installieren“ schickt es an die Konsole und registriert die Anwendung. GPL-3.0-or-later; Quelltext `appinst.c`, Herkunft und die Abweichungen vom Vorbild in `PS5-AppInstall/NOTICE.md` |
| **Ersatzbibliotheken für BACKPORT** | PS5 BackPork Kitchen | Firmware-Profile 4.00 bis 7.00 im Ordner `Backport_Fakelibs/`. Die darin enthaltenen `libSceAmpr.sprx`/`libScePlayGo.sprx` sind davon ausgenommen – das sind seit 28.10.2026 die eigenen, oben gelisteten AMPR-EMU- und PlayGo-Stub-Dateien (drakmor), nicht Bestandteile von PS5 BackPork Kitchen |
| **PS5 WebKit Autoloader 0.4.0, 0.5.1, 0.5.2, 0.6.0, 0.6.1, 0.6.2, 0.7.1, 0.8.2 und 0.8.3** | itsPLK ([ps5-webkit-autoloader](https://github.com/itsPLK/ps5-webkit-autoloader)) | Legt eine Kachel auf den Startbildschirm der Konsole; liegt je Fassung als Installer im Ordner `PS5 WebKit Autoloader/` bei; Host (Windows-Programm) und Skript liefert das Programm seit v1.9.90 nicht mehr mit, sondern lädt sie beim ersten Klick auf den jeweiligen Knopf aus dem Release des Autors (`github.com/itsPLK/ps5-webkit-autoloader`, SHA-256 gegen den Release-Anhang geprüft) in den Einstellungsordner; die Fassung wählt man auf der Seite „WebKit Autoloader“. Unveränderte Original-Releases v0.4.0, v0.5.1, v0.5.2, v0.6.1, v0.6.2, v0.7.1, v0.8.2 und v0.8.3 (v0.5.0 entfernt: Dateien defekt) sowie die Vorabfassung v0.6.0-pre-4488577 (im Ordner als v0.6.0 abgelegt); GPL-3.0 (LICENSE im Projekt, an jedem dieser Tags vorhanden); SHA-256 aller siebenundzwanzig Dateien gegen den Release-Anhang geprüft |
| **QR-Kodierer (`ps5_validator/utils/qr_klein.py`)** | EchoStretch, slopmaster33 (webhb 0.4.1, GPL-3.0-or-later) | Zeigt die Adresse einer Weboberfläche als QR-Code (Byte-Modus, Stufe M, Versionen 1 bis 6). Eine Übertragung von `qr.c` aus dem webhb-Archiv nach Python; für 14 Eingaben gegen das übersetzte C-Original auf gleiche Module geprüft. |
| **7-Zip 26.06** | Igor Pavlov ([7-zip.org](https://www.7-zip.org/)) | Entpackt `.7z`- und `.rar`-Archive, die als Quelle von Aufgabe 1 dienen (`7-Zip-26.06/`: `7z.exe` und `7z.dll` für Windows, `7zz` für Linux und je ein `7zz` für macOS auf Apple Silicon und auf Intel (seit 26.06 getrennte Pakete); unverändert, aus den Paketen `7z2606-x64.exe`, `7z2606-linux-x64.tar.xz`, `7z2606-mac.tar.xz` und `7z2606-mac-x64.tar.xz` der Freigabe 26.06 vom 07.11.2026 auf `github.com/ip7z/7zip`, SHA-256 gegen den GitHub-Digest geprüft). Lizenz: GNU LGPL, für einen Teil des Codes mit der „unRAR license restriction“ (verbietet nur, damit einen RAR-Packer nachzubauen) und BSD – Text in `7-Zip-26.06/License.txt`. |
| **PS5-PKG-Tool 2.5.1 (`ffpfsc-pkg-tool`)** | Quelltext aus **ps5-fpkg-converter 0.0.3** (Autor laut `pyproject.toml`: „Sub“; GPL-3.0-or-later), mit der Engine von **ps5-ultrapack** (Knutwurst; bis einschließlich 2.4.1 MIT, seit 2.4.2 GPL-3.0-or-later mit Zusatzbedingungen nach Abschnitt 7 – der Quelltext hier stammt aus der MIT-Zeit, von der neueren Fassung wird nur die Versionsnummer geführt, Näheres in `PS5-PKG-Tool/README.md`) | Das Werkzeug hinter „PS5 PKG Dump & Image Converter“: PS5-Pakete lesen, prüfen und entpacken (auch direkt auf die PS5); gebaut werden Pakete seit dem 17.11.2026 von Dump Forge. Gebaut aus `PS5-PKG-Tool/src/` (net10.0, abhängig von der .NET-Laufzeit), je Plattform ein Ordner. Enthält die Bibliothek **LibProsperoPkg** in der Fassung 1.2.0 (GPL-3.0-or-later, Build d7090eb6; als fertige Datei – die Quelle liegt nicht bei, die Herkunft steht in `PS5-PKG-Tool/src/ffpfsc-pkg-tool/lib/README.md`), **LibOrbisPkg** (LGPL-3.0, Quelle in `src/LibOrbisPkg`), **Magick.NET** (Apache-2.0, Hinweise in `PS5-PKG-Tool/NOTICE_Magick.NET.txt`), **BCnEncoder.Net** (MIT oder Unlicense) und **CommunityToolkit.HighPerformance** (MIT). Lizenztext: `PS5-PKG-Tool/LICENSE`. |
| **Dump Forge 0.5.7 – Befehlszeile (`Dump-Forge-CLI/`)** | quer3q ([ps5-dump-forge](https://github.com/quer3q/ps5-dump-forge), GPL-3.0-or-later; Freigabe v0.5.7 vom 22.11.2026) | Der **Paketersteller** (seit 17.11.2026 der einzige) im Bereich „PKG / FPKG“ (Fenster „PS5 PKG Dump & Image Converter“): Das Programm führt die Befehlszeile `ps5-dump-forge` aus (`convert <Quelle> --to pkg`, `inspect --json`), um aus Spielordnern und Abbildern (.ffpkg, .ffpfsc, .ffpfs, .exFAT) ein Debug-Paket (FPKG) zu bauen und zu prüfen - Forge selbst, nichts davon ist nachgebaut. Je Plattform eine Datei, unverändert aus der Freigabe: Windows x64 (`Dump-Forge-CLI/win-x64/`), Windows arm64 (`win-arm64/`), macOS universal (`macos-universal/`), Linux x64 statisch (`linux-x64/`), Linux arm64 dynamisch gegen glibc (`linux-arm64/`); SHA-256 der Archive gegen `SHA256SUMS` und den Digest der Freigabe geprüft (alle fünf, 22.11.2026), alle Prüfsummen in `Dump-Forge-CLI/README.md`; die arm64-Dateien wurden nicht ausgeführt. Lizenztext (`LICENSE`) und `THIRD-PARTY-NOTICES.md` (die in Forge enthaltenen Fremdteile: ps5upload-Engine von phantomptr, ampr_emu von drakmor, ampr-emu-ng von quer3q, LZ4 u. a.) liegen im Ordner bei. Quelltext: <https://github.com/quer3q/ps5-dump-forge/tree/v0.5.7>. **Aus dem Quelltext übertragen** (nach Python, auf den Weg zur `eboot.bin` beschnitten; dieselbe Lizenz): das Lesen des SDK einer `eboot.bin` (`programm_sdk.py`, nach `crates/ps5-dump-forge-core/src/sdk.rs`) und das Lesen einer Datei aus einem `.pkg` – Kopf und Behälter, äußeres PFS mit AES-128-XTS, Beschreibung und Kraken-Decoder des inneren Abbilds, inneres Dateisystem (`pkg_eboot.py`, nach `crates/ps5-dump-forge-fpkg` und `vendor/ps5upload-fpkg`; der Kraken-Teil dort wiederum nach der Beschreibung von powzix/ooz, GPL-3.0) |
| **Hintergrundbilder** | für dieses Programm erstellt | Haupt- und Sidebar-Hintergründe |
| **Microsoft WebView2 SDK 1.0.3856.49** (nur Windows) | Microsoft Corporation – `Microsoft.Web.WebView2.Core.dll` und `WebView2Loader.dll` (x64), von Microsoft signiert; entnommen dem Paket **pywebview 6.2.1** (BSD-3-Clause), von dem sonst nichts eingebettet wird | Zeigt die Weboberflächen der Konsole rechts im Programm, über die in Windows enthaltene WebView2-Laufzeit. BSD-artige Lizenz von Microsoft – Wortlaut im eigenen Abschnitt unten |

---

---

## Eigener UFS2-Schreiber nach UFS2Tool (`ps5_validator/utils/ufs2_schreiber.py`)

Das Programm schreibt eine `.ffpkg` selbst, ohne UFS2Tool aufzurufen
(Datei `ps5_validator/utils/ufs2_schreiber.py`). Das ist ein **Nachbau des Erzeugers von
UFS2Tool 4.1** (`Ufs2ImageCreator.cs`, `Ufs2Superblock.cs`, `Ufs2Inode.cs`, `Ufs2DirectoryEntry.cs`
von SvenGDK) in Python: Größenschätzung, Aufbau von Superblock und Zylindergruppen, Blockvergabe und
Verzeichnisblöcke folgen seinem Quelltext, damit dasselbe Abbild entsteht (die Tests vergleichen
byteweise gegen `UFS2Tool newfs -D`). Es gilt deshalb dessen Lizenz, BSD 2-Clause, die hier mit
dem Hinweis auf den Urheber wiedergegeben wird:

```
BSD 2-Clause License

Copyright (c) 2026, SvenGDK
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

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

**Dasselbe gilt für `OrbisPkgTool`** (seit 05.10.2026, nur `win-x64`): Auch diese
Befehlszeile ist eigenständig gebaut (`PublishSingleFile`, getrimmt, 12,8 MB) und
trägt die .NET-**10.0.12**-Laufzeit in sich – es gilt für sie also die .NET Library
License wie für den Windows-Bau von `UFS2Tool`, und die Weitergabe ist aus demselben
Grund erlaubt. Auf die vier Dateien mit eigenen Verträgen aus Issue #108905 am
05.10.2026 in der fertigen Datei nachgesehen: keine davon ist enthalten (weder
`D3DCompiler_47_cor3.dll` noch `vcruntime140_cor3.dll` noch ein anderer `*_cor3.dll`-Name);
`System.Private.CoreLib` und `coreclr` stehen darin, die Abwesenheit ist also ein
Befund und kein Messfehler. Gebaut ist `net10.0-windows` ohne Windows Forms und ohne WPF.

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

## Microsoft WebView2 SDK (nur Windows)

Die beiden Dateien `Microsoft.Web.WebView2.Core.dll` und `WebView2Loader.dll`
stammen aus dem NuGet-Paket **Microsoft.Web.WebView2 1.0.3856.49** (über
pywebview 6.2.1) und werden unverändert weitergegeben. Die Browser-Engine
selbst (WebView2-Laufzeit) liegt nicht bei – sie gehört zu Windows. Lizenz
laut nuget.org, am 26.09.2026 nachgelesen:

```
Copyright (C) Microsoft Corporation. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.
* The name of Microsoft Corporation, or the names of its contributors may not
  be used to endorse or promote products derived from this software without
  specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

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

Ebenfalls nur Ideen, kein Code (der Code dazu ist hier neu geschrieben):

| Person / Projekt | Idee |
| --- | --- |
| **kvaps – fpkg2ftp** (GPL-3.0-or-later) | Ein PS5-Paket lesen und die Dateien gleich per FTP an die Konsole schicken, eine angefangene Datei dort fortsetzen, wo die Konsole sie hat, und nach einem Abriss neu verbinden (`pkg_direkt`, `konsole_ftp`, Befehl `stream-inner` des PKG-Werkzeugs) |
| **KINGDKAK – PS5-FFPFSC-PRO** | Idee der Voreinstellungen Schnell, Ausgewogen, Maximal und Wenig RAM für Kompressionsstufe und Kernzahl (die Werte waren hier eigene; die Blockgröße gehörte nicht dazu). Die Knöpfe gibt es seit dem 11.10.2026 nicht mehr; die Namensnennung bleibt, weil frühere Fassungen die Idee enthielten |

---

## Profilbilder im Fenster CREDITS

Der Ordner `credits/` enthält die öffentlichen GitHub-Profilbilder der Entwicklerinnen
und Entwickler, denen das Fenster **Credits & Community** dankt (Liste:
`ps5_validator/utils/credits_daten.py`). Sie dienen allein der Namensnennung, wurden
einmal von GitHub geladen und auf 160 × 160 px verkleinert; Herkunft und Prüfsumme
jedes Bildes stehen in `credits/herkunft.json`. Die Rechte an den Bildern liegen bei
den jeweiligen Kontoinhabern. Zur Laufzeit lädt das Programm nichts aus dem Netz.

---

## Verwendete Python-Bibliotheken

Diese Bibliotheken werden in die EXE eingebettet; es gelten ihre jeweiligen Lizenzen:

**Pillow**, **cryptography**, **zstandard**, **zlib-ng**, **tkinterdnd2**, **psutil**,
**lz4** (für die Asset-Packs des AMPR EMU) und **pyserial** (BSD-3-Clause, für PS5 Wee Tools)
sowie **PyInstaller** für den Bau der Windows-EXE. Nur in der Windows-EXE, für die
Weboberflächen im Programm: **pythonnet** (MIT) mit **clr_loader** (MIT, Benedikt
Reinartz), **cffi** (MIT-0) und **pycparser** (BSD-3-Clause) – die Brücke zu .NET.

---

## Genutzte Onlinequelle

**prosperopatches.com** – dorthin wird auf ausdrückliche Rückfrage die Title-ID
gesendet, um bei fehlender oder defekter `param.json` Titel und Content-ID
nachzuschlagen. Die Frage ist auf **Nein** voreingestellt; ohne Zustimmung
verlässt keine Angabe den Rechner.
