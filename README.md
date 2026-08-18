# PS5 Dump & Image Converter

![Plattform](https://img.shields.io/badge/Plattform-Windows%20%7C%20Linux%20%7C%20macOS-0078D6)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![Version](https://img.shields.io/badge/Version-v1.8.51-blue)
![Status](https://img.shields.io/badge/Status-release--bereit-brightgreen)

Der **PS5 Dump & Image Converter** ist eine Anwendung zum Konvertieren, Entpacken, Packen, Bearbeiten und Prüfen unterstützter PS5-Dump-Formate. Sie läuft unter **Windows**, **Linux** und **macOS**; einzelne Abläufe, die auf Windows-Werkzeuge angewiesen sind, bleiben Windows vorbehalten (siehe [Was außerhalb von Windows anders ist](#was-außerhalb-von-windows-anders-ist)). Die grafische Oberfläche führt durch acht klar getrennte Aufgaben und unterstützt Dump-Ordner, `.ffpfsc`, `.exfat` und echte UFS2-basierte `.ffpkg`-Dateien.

> **Neu bei der Bedienung?** Das **[Benutzerhandbuch](BENUTZERHANDBUCH.html)** (Version v1.8.51) erklärt Aufgabenwahl, Quelle und Ziel, Fortschrittsanzeige, alle Werkzeugleisten-Buttons sowie typische Fehler in einfacher Sprache – mit Inhaltsverzeichnis und allen acht Aufgaben. Es liegt zweifach bei: als **[BENUTZERHANDBUCH.html](BENUTZERHANDBUCH.html)** zum Lesen im Browser und als **[BENUTZERHANDBUCH.pdf](BENUTZERHANDBUCH.pdf)** (25 Seiten) zum Ausdrucken und Weitergeben.

## Inhalt

- [Aktuelle Version](#aktuelle-version)
- [Was die Anwendung kann](#was-die-anwendung-kann)
- [Die acht Aufgaben](#die-acht-aufgaben)
- [Voraussetzungen](#voraussetzungen)
- [Schnellstart](#schnellstart)
- [Empfohlener Ablauf](#empfohlener-ablauf)
- [Wichtige Hinweise](#wichtige-hinweise)
- [Fortschritt und Abschlussprüfung](#fortschritt-und-abschlussprüfung)
- [Entwicklung und Build](#entwicklung-und-build)
- [Projektstruktur](#projektstruktur)
- [Credits und Danksagung](#credits-und-danksagung)
- [Lizenz und Verantwortung](#lizenz-und-verantwortung)

## Aktuelle Version

**v1.8.51** prüft die `sce_sys/param.json` jetzt inhaltlich – und repariert sie auf Wunsch. Bisher genügte es, dass die Datei sich als JSON lesen ließ; alles Weitere fiel erst auf der Konsole auf. Eine Versionsnummer als Zahl statt als Zeichenkette, eine `contentId`, die eine andere Title-ID nennt als das Feld daneben, ein fehlender Sprachblock oder ein BOM am Dateianfang führen dort zu „Missing/invalid param.json" – der Dump sieht dabei einwandfrei aus. Diese Fälle erkennt das Programm jetzt beim Bau **und im Validator**, und es bietet an, sie zu berichtigen. Repariert heißt dabei wirklich repariert: Vorhandene Angaben bleiben stehen, die alte Fassung wird als `param.json.alt` danebengelegt. Details siehe [Release Notes v1.8.51](RELEASE_NOTES_v1.8.51.md).

**v1.8.50** bringt die Anwendung auf den Mac. Neben der Windows-EXE und der Linux-Programmdatei entsteht mit `./Build_macOS.sh` ein Programmbündel `PS5 Dump & Image Converter.app` – mit Symbol im Dock, eigenem Namen in der Menüleiste, scharfer Darstellung auf Retina-Bildschirmen und dunklem Erscheinungsbild. `./Install_macOS.sh` legt es in den Programme-Ordner. Es gelten dieselben Einschränkungen wie unter Linux: `.ffpkg` lesen und bauen sowie die OSFMount-Ersatzwege bleiben Windows vorbehalten, alles Übrige steht vollständig zur Verfügung. Details siehe [Release Notes v1.8.50](RELEASE_NOTES_v1.8.50.md).

**v1.8.49** räumt den Bibliothekssatz auf. Beim Backport wurde bisher der komplette mitgelieferte Ordner in das Spiel kopiert – im FW7-Satz also auch eine `ps5-backpork.elf`, der 116 KB große Payload des Referenzwerkzeugs. ShadowMount+ hängt den Ordner nach `common/lib`, wo Bibliotheken nach Namen geladen werden; nach dieser Datei fragt kein Spiel. Übernommen werden jetzt nur `.sprx` und `.prx` sowie die leere Markierung `FW<n>`, und was übersprungen wurde, steht im Protokoll. Dass die Datei verzichtbar ist, zeigt der Satz selbst: In FW4, FW5 und FW6 fehlt sie. Details siehe [Release Notes v1.8.49](RELEASE_NOTES_v1.8.49.md).

**v1.8.44** räumt das Protokollfeld wirklich auf. Text und Fortschrittsbalken klebten dort in einer Zeile (`Writing PFS image to …[####] 72% write`), und weil eine solche Zeile nicht als Balken erkannt wurde, stapelten sich die folgenden Balken statt sich zu ersetzen. Ursache war der Zeilentrenner der Engine-Ausgabe: Er suchte erst nach dem Zeilenumbruch und erst danach nach dem Wagenrücklauf. Jetzt wird am zuerst auftretenden getrennt – je Phase steht eine Zeile, die sich fortschreibt. Details siehe [Release Notes v1.8.44](RELEASE_NOTES_v1.8.44.md).

**v1.8.43** fasst die Verbindungsdaten der PS5 an einer Stelle zusammen: In den **EINSTELLUNGEN** stehen jetzt IP-Adresse, FTP-Port und KLOG-Port, dazu ein Knopf zum Testen. Alle Fenster, die eine Verbindung brauchen, schlagen diese Werte vor; stimmt ein Port nicht, probieren sie die bekannten Alternativen selbst durch. Der Knopf **KLOG** prüft vor dem Öffnen, ob klogsrv überhaupt läuft, und bietet sonst an, den Payload zu senden – über den Loader oder per FTP auf einen USB-Datenträger der Konsole, samt Eintrag in `autoload.txt`. Dazu übersichtlichere **BIBLIOTHEK** mit Rollbalken und sortierbaren Spalten, ein aufgeräumtes Protokollfeld und eine Fortschrittsanzeige ohne langen Stillstand. Details siehe [Release Notes v1.8.43](RELEASE_NOTES_v1.8.43.md).

**v1.8.42** bringt den Knopf **BENUTZERHANDBUCH** in die Titelleiste, links neben EN: Ein Druck öffnet das mitgelieferte Handbuch im Browser. Im Fenster EINSTELLUNGEN stand der Hinweis über den Knöpfen halb unter ihnen und war abgeschnitten – er hat jetzt eine eigene Zeile. Außerdem erscheinen Fehlermeldungen wieder, die bisher stumm blieben: Schlug ein Backport fehl oder ließ sich eine Remote-INI nicht laden, schreiben oder ihr Debug-Log nicht holen, blieb die Statuszeile einfach stehen, statt den Grund zu nennen. Details siehe [Release Notes v1.8.42](RELEASE_NOTES_v1.8.42.md).

**v1.8.41** verdoppelt die Auswahl der Hintergrundbilder für den Hauptbereich von zehn auf zwanzig. Die zehn neuen Bilder tragen dieselben Motive wie die hohen Bilder der Seitenleiste – Polarlicht, Lichtstrahlen, Bokeh, Sternenfeld, Höhenlinien, Wellenringe, Fluchtpunktraster, Punktraster und warme Bänder –, sodass sich beide Bereiche zueinander passend einstellen lassen. Wie die bisherigen sind sie bewusst dunkel gehalten, damit Karten und Beschriftungen davor lesbar bleiben. Details siehe [Release Notes v1.8.41](RELEASE_NOTES_v1.8.41.md).

**v1.8.40** räumt beim FILEZILLA-Knopf auf: Der eingebaute FTP-Client entfällt, der Knopf startet ausschliesslich Ihre eigene FileZilla-Installation. Gefunden wird sie jetzt auch dann, wenn der Installationsordner beliebig heißt oder direkt auf einem Laufwerk liegt – und der gefundene Pfad wird gemerkt, sodass der nächste Start ohne Suche auskommt. Dasselbe gilt für OSFMount. Details siehe [Release Notes v1.8.40](RELEASE_NOTES_v1.8.40.md).

**v1.8.39** machte den Programmstart ruhig. Das Fenster blitzte kurz **weiß** auf und baute sich danach sichtbar auf; in der Seitenleiste stand der Spielname zeitweise **über** dem Cover, das Bild verschwand für einen Moment und wanderte anschließend mehrfach. Beides ist behoben: Das Fenster erscheint erst fertig, Cover und Name sitzen von Anfang an fest. Dazu ein etwas größerer Spielname, runde Ecken am Startbildschirm und ein nachgezogener Dokan-2-Dialog. Details siehe [Release Notes v1.8.39](RELEASE_NOTES_v1.8.39.md).

**v1.8.38** behob einen Fehler, der **jeden Upload auf die Konsole** betraf: Seit dem 15.08. starteten dort hochgeladene Spiele nicht mehr (**CE-107750-0**). Ursache war der auf Tempo optimierte Payload **zftpd**, der Dateien ohne Ausführungsrecht ablegt – die PS5 startet solche Dateien nicht. Das Programm nutzt jetzt wieder **ftpsrv auf Port 2121** und prüft nach jedem Upload die Rechte, damit so etwas nicht noch einmal stumm bleibt. Details siehe [Release Notes v1.8.38](RELEASE_NOTES_v1.8.38.md).

**v1.8.37** behob beschnittene Bedienelemente in fünf Fenstern. Im **BACKPORT**-Fenster blieben die drei Knöpfe unbeschriftet und die Firmware-Auswahl leer, beim **PKG-Merger** fehlte die Knopfleiste ganz; dieselbe Ursache traf **DOWNLOADS**, **ShadowMount+/MicroMount** und den **JS Loader**. Ein neuer Test misst die Fenster jetzt aus. Siehe [Release Notes v1.8.37](RELEASE_NOTES_v1.8.37.md).

**v1.8.36** schloss die letzte Lücke der `param.json`-Reparatur: Fehlt oder zerbricht die Datei, konnte die Ersatzdatei bisher nur die Title-ID tragen – Titel und Content-ID stehen in **keiner** lokalen Datei eines Dumps. Beide lassen sich jetzt auf Wunsch zur Title-ID online nachschlagen. Die Frage danach ist eine eigene, auf **Nein** voreingestellte Rückfrage, die nennt, wohin die Title-ID geht; ohne Netz oder bei Ablehnung entsteht die Ersatzdatei wie bisher. Nebenbei behoben: Das Fenster *Spiel-Info* zeigte den Titel mit vorangestellter Title-ID (`PPSA19015: Arcade Game Zone`). Siehe [Release Notes v1.8.36](RELEASE_NOTES_v1.8.36.md).

**v1.8.35** brachte **BACKPORT** in das Menü **WEITERE TOOLS**: Ein Spiel, das ein zu neues SDK verlangt, lässt sich damit auf eine ältere Firmware (4.00 bis 7.00) herabsetzen. Das Programm entpackt jede ausführbare Datei, setzt die SDK-Angabe im Modulkopf herab, signiert sie neu und legt die passenden Ersatzbibliotheken dazu. Auf Wunsch entsteht vorher eine vollständige Sicherung; ersetzt wird eine Datei erst, wenn Patchen *und* Signieren gelungen sind. Alles läuft ohne Fremdwerkzeug und ohne .NET-Laufzeit. Siehe [Release Notes v1.8.35](RELEASE_NOTES_v1.8.35.md).

**v1.8.34** machte aus dem Knopf **Download** im Fenster *Spiel-Info* einen vollständigen Vorgang: Updates und Patches werden wirklich heruntergeladen, nach Art getrennt abgelegt (**PS5 Spiele Updates** bzw. **Patches**) und im Fenster **DOWNLOADS** unter WEITERE TOOLS mit Fortschritt und Status geführt. Abgebrochene Downloads setzen dort fort, wo sie stehen geblieben sind; eine halb geladene Datei kann nie für fertig gehalten werden. Der Speicherort wird beim ersten Mal abgefragt und ist in den Einstellungen änderbar. Ein Schritt bleibt bewusst von Hand: Die Adresse entsteht erst hinter einer Sicherheitsabfrage auf der Patch-Seite, die dieses Programm nicht umgeht.

**v1.8.33** war die Nacharbeit zum zweiten Praxistest – sechs weitere Backups, 22 Konvertierungen, und die dabei gefundenen Fehler sind behoben: Die `.ffpkg`-Extraktion verlor stillschweigend eine Datei und prüft ihr Ergebnis jetzt gegen das Abbild, Quelldateien mit Sonderzeichen im Namen brechen den Packlauf nicht mehr ab, die Sammelkonvertierung scheitert nicht mehr an einer Quelle, die schon im Zielformat vorliegt, und `.ffpfs` lässt sich nachträglich zu `.ffpfsc` komprimieren. Dazu drei wiederbelebte Werkzeuge im Menü **WEITERE TOOLS** – **SELF-Inspektor**, **Dump umbenennen** und **Debug-PKG bauen** –, ein gewähltes Hintergrundbild überlebt den Neustart der EXE, und liegengebliebene Temp-Ordner werden abgeräumt.

Seit **v1.8.32** bricht der Kommandozeilenmodus nicht mehr an Sonderzeichen im Protokoll ab, Aufgabe 4 kann eine `.ffpkg` wie angeboten neu aufbauen, der Validator stuft `pfs-version.dat` als Empfehlung statt als Pflicht ein und erkennt alle drei regulären Bauformen eines Containers.

Seit **v1.8.31** erkennt Aufgabe 8 unvollständige Dumps auch am fertigen Container und meldet falsch verschachtelte Container, ohne sie zu entpacken; vor dem Start warnt das Programm, wenn im Quellordner Pflichtdateien fehlen.

Seit **v1.8.30** kann der Rechner nach einem erfolgreichen Lauf selbst herunterfahren: Ein Ankreuzfeld unter TEMP-ORDNER schaltet es ein, danach löst das Programm gemountete Abbilder, räumt die Temp-Ziele und fährt ohne Rückfragen herunter – abbrechbar über ein Countdown-Fenster. Nach einem Fehler oder Abbruch bleibt der Rechner an. Im Kommandozeilenmodus übernimmt das `--shutdown-on-success`.

Seit **v1.8.29** stehen keine farbigen Restflächen mehr auf dem Hintergrundbild (Telemetrie, Größenanzeige, Startphase, Fenstergrößenänderung), ein Design-Wechsel im laufenden Betrieb zieht alle Schriftfarben mit, die FTP-Automatik findet den mitgelieferten **zftpd**-Payload auf Port 2120, und die Lizenzen der mitgelieferten Payloads liegen in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) bei.

Seit **v1.8.28** stehen die Beschriftungen im Hauptfenster randlos auf dem Hintergrundbild: QUELLE, ZIELFORMAT, KOMPRESSION, ZIELORDNER, TEMP-ORDNER, der Formathinweis darunter sowie Überschrift, Untertitel, Statuszeile und die Sidebar-Texte zeigen nur noch die Schrift, ohne Kasten dahinter.

Seit **v1.8.27** liegen die AMPR-EMU- und PlayGo-Versionen sowie eine Auswahl an Hintergrundbildern dem Programm bei: Der Versionsordner für Aufgabe 7 muss nicht von Hand gewählt werden, und im Design-Dialog stehen die mitgelieferten Bilder sofort zur Auswahl (eigene Bilder bleiben möglich). Beides ist in der Windows-EXE eingebettet.

Die seit **v1.7.90** abgesicherte FFPKG-Kernlogik: Jede `.ffpkg` entsteht zunächst im konfigurierten Temp-Staging statt direkt auf dem Zielvolume. Ein Kandidat muss dort `info`, das schreibgeschützte `fsck_ufs -fn` und seit **v1.8.9** zusätzlich die Dateizahl-Prüfung bestehen, bevor er übertragen wird. Nach der Übertragung erzwingen ein SHA-256-Vergleich und eine zweite native UFS2-Prüfung auf dem Zielvolume die Abnahme; erst dann übernimmt eine atomare Umbenennung die finale Datei. Dadurch kann ein Zielvolume keine unvollständige UFS2-Struktur unbemerkt als Erfolg hinterlassen. Die Profile bleiben: 64-KiB-`newfs -D`, 32-KiB/4-KiB-`newfs -D`, danach `makefs` als letzter Fallback. Die eingebettete UFS2Tool-v4.1-Runtime bleibt SHA-256-gesichert.[1] [2] [7] [8]

Seit **v1.8.10** gilt dieselbe Abnahmelogik auch für `.exfat`: Nach dem Bau wird die enthaltene Dateizahl über die vendorte PFS-Bibliothek rein lesend gezählt und mit dem Quellordner verglichen, ohne Mount oder Adminrechte.

| Bereich | Stand |
| --- | --- |
| `.ffpkg`-Primärpfad | UFS2Tool `newfs -D`, 64-KiB-Block/Fragment, 512-Byte-Sektoren, Inode-Reserve |
| `.ffpkg`-Kompatibilität | Bei verworfenem Primärkandidaten: unabhängiges 32-KiB/4-KiB-`newfs`-Profil, danach erst `makefs` |
| `.ffpkg`-Abnahme | `info`, schreibgeschütztes `fsck_ufs -fn` und Dateizahl-Prüfung per UFS2Tool/Dokan2-Mount vor atomarer Übernahme; verworfene Zwischenstände werden gelöscht |
| `.ffpfsc`/`.ffpfs`-Aufbau | Zweistufig: rohes, unkomprimiertes inneres PFS direkt aus den Spieldateien, danach der äußere (komprimierte oder unkomprimierte) Container |
| `.exfat`-Abnahme | Dateizahl-Prüfung über die vendorte PFS-Bibliothek nach dem Bau |
| UFS2Tool-Runtime | Offizielles v4.1-Bundle mit SHA-256-Prüfung vor Extraktion |
| GUI-Synchronisation | Balken, Prozent, Datei- und Bytezähler aus derselben UFS2Tool-Quelle |
| Abschlussbericht | Kein automatischer JSON-Bericht mehr (seit v1.8.11 entfernt) |
| Sprache | Vollständig Deutsch/Englisch umschaltbar (seit v1.8.12) – Oberfläche, Dialoge, Protokoll |
| Windows-EXE-Ziel | `dist\PS5_Dump_Image_Converter_v1.8.51.exe` |

Die vollständigen Änderungen stehen im [Changelog](CHANGELOG.md).

## Was die Anwendung kann

Die Anwendung verbindet eine übersichtliche Windows-Oberfläche mit den benötigten Konvertierungs- und Prüfwerkzeugen. Nutzer wählen eine Aufgabe, eine Quelle, ein unterstütztes Zielformat und einen Zielordner. Der eigentliche Ablauf wird anschließend automatisch ausgeführt.

| Funktionsgruppe | Möglichkeiten |
| --- | --- |
| Konvertieren | Dump-Ordner, `.ffpfsc`, `.exfat` und `.ffpkg` in passende Zielformate umwandeln |
| Entpacken | Unterstützte Container als normalen Dump-Ordner ausgeben |
| Mehrfachverarbeitung | Mehrere Container nacheinander in ein gemeinsames Zielformat konvertieren |
| Universal-Export | Eine unterstützte Quelle gezielt in einen Zielordner exportieren |
| AMPR EMU Manager | AMPR-/PlayGo-Versionen verwalten, Index erzeugen, Dateien per FTP auf der PS5 austauschen |
| Validierung | Dump-Ordner und unterstützte Container auf grundlegende Integrität prüfen; bei `.ffpfsc`/`.ffpfs` zusätzlich die innere Verschachtelung, ohne die Datei zu entpacken |
| Bedienkomfort | Quelle/Ziel/Temp per Drag & Drop setzen, alternativ per Auswahldialog |
| Automatisierung | Jede Aufgabe auch per `--cli`-Kommandozeilenmodus ohne sichtbares Fenster starten |
| AMPR Picker | Spielordner auf der PS5 per FTP durchsuchen, prüfen, Bibliotheken austauschen und den Index dort neu bauen |
| PKG-Merger | Aus Distributionsgründen geteilte `.pkg`-Dateisätze wieder zu einer Datei zusammenführen |
| Param-/Manifest-Editor | `sce_sys/param.json` und `manifest.json` komfortabel bearbeiten, unbekannte Schlüssel bleiben erhalten |
| Bibliothek | Mehrere Ordner nach Dump-Ordnern/Containern durchsuchen, mit Cover, Suche und Detailansicht |
| Diagnosebericht | Version, Systeminfo, letzte Logzeilen und geschwärzte Einstellungen als Textdatei bündeln |
| Sprache | Vollständig Deutsch/Englisch umschaltbar – Oberfläche, alle Dialoge und Protokollmeldungen |
| Klog | Live-Kernel-Log einer PS5 per Rohsocket streamen, filtern, einfärben und exportieren |
| ShadowMount+ | `config.ini` per FTP laden, bearbeiten, schreiben und `debug.log` abrufen |
| .ffpfs (unkomprimiert) | Zusätzliches Zielformat bei Aufgabe 1/3: identisches inneres PFS, aber ohne äußere Kompression |
| Cross-Drive-Staging | Schreibt die Kompressions-Ausgabe bei konfiguriertem Temp-Laufwerk auf einem anderen Laufwerk zwischen, um Lese-/Schreib-Kontention zu vermeiden |
| Live-Systemtelemetrie | Zeigt CPU-/RAM-/Temp-Speicher-Nutzung live an, solange eine Aufgabe läuft |
| Herunterfahren nach Abschluss | Fährt den Rechner nach einem erfolgreichen Lauf herunter – erst nach Lösen der Abbilder und Aufräumen der Temp-Ziele, mit Countdown zum Abbrechen; bei Fehler oder Abbruch bleibt er an |
| SELF-Inspektor | Nur-Lese-Strukturanzeige einer PS4/PS5-SELF-Datei (Header, Segmente, ELF-Kopf, Authority-ID) – ohne Entschlüsselung |
| Windows-Build | Eine eigenständige EXE über das mitgelieferte Buildskript erstellen |

## Die acht Aufgaben

Die Aufgabenbezeichnungen entsprechen der aktuellen Oberfläche von v1.8.51.

| Nr. | Aufgabe | Geeignete Quelle | Mögliche Ausgabe oder Zweck |
| ---: | --- | --- | --- |
| **1** | Dump-Ordner flexibel konvertieren | Spiel-Dump-Ordner | `.ffpfsc`, `.exfat` oder `.ffpkg` |
| **2** | FFPFSC flexibel konvertieren | `.ffpfsc` | Dump-Ordner, `.exfat` oder `.ffpkg` |
| **3** | exFAT flexibel konvertieren | `.exfat` | Dump-Ordner, `.ffpfsc` oder `.ffpkg` |
| **4** | FFPKG flexibel konvertieren | `.ffpkg` | Dump-Ordner, `.ffpfsc` oder `.exfat` |
| **5** | Mehrere Dateien konvertieren | Mehrere `.ffpfsc`, `.exfat` oder `.ffpkg` | Gemeinsames, für alle Quellen unterstütztes Zielformat |
| **6** | Universal-Export in Zielordner | Dump-Ordner oder unterstützter Container | Gewähltes, zur Quelle passendes Zielformat |
| **7** | AMPR EMU Manager | Dump-Ordner, `.ffpfsc`, `.exfat` oder `.ffpkg` | AMPR-EMU-Versionen verwalten, `ampr_emu.index` bauen und per FTP direkt auf der PS5 arbeiten |
| **8** | Dump Validator | Dump-Ordner, `.ffpfsc`, `.exfat` oder `.ffpkg` | Integrität prüfen und einen verständlichen Bericht anzeigen |

Die Oberfläche bietet nur Zielformate an, die zur erkannten Quelle passen. Ein identisches, nicht sinnvolles Selbstziel wird bei normalen Konvertierungen nicht angeboten.

## Voraussetzungen

### Für die fertige Windows-EXE

| Voraussetzung | Hinweis |
| --- | --- |
| Betriebssystem | Windows 10 oder Windows 11 |
| Freier Speicherplatz | Genug Platz für Quelle, temporäre Dateien und fertige Ausgabe |
| Administratorrechte | Für einzelne erhöhte, Mount- oder UFS2-bezogene Abläufe erforderlich |
| OSFMount | Für exFAT-bezogene Mount-Abläufe erforderlich[4] |

### Für die fertige Linux-Version

| Voraussetzung | Hinweis |
| --- | --- |
| Betriebssystem | 64-Bit-Linux mit grafischer Oberfläche (X11 oder Wayland) |
| Tcl/Tk | `python3-tk` (Debian/Ubuntu), `python3-tkinter` (Fedora), `tk` (Arch) – nur zum Bauen nötig, die fertige Datei bringt Tk mit |
| fontconfig | Bestimmt die Schriftwahl. Fehlt es, wird die Tk-Grundschrift verwendet |
| Freier Speicherplatz | Genug Platz für Quelle, temporäre Dateien und fertige Ausgabe |
| Root-Rechte | Für den normalen Betrieb **nicht** erforderlich |

Die Linux-Fassung ist eine einzelne, eigenständige Programmdatei ohne Installation. Sie wird pro Architektur gebaut; der Dateiname nennt sie (`…_linux_x86_64`).

### Für die fertige macOS-Version

| Voraussetzung | Hinweis |
| --- | --- |
| Betriebssystem | macOS 11 (Big Sur) oder neuer, Apple Silicon oder Intel |
| Python zum Bauen | Von [python.org](https://www.python.org/downloads/macos/) oder `brew install python-tk`. Apples mitgeliefertes `/usr/bin/python3` reicht **nicht**: Es bringt kein brauchbares Tcl/Tk mit |
| Tcl/Tk | Version 8.6 oder neuer. Das systemeigene Tk 8.5 zeichnet Rahmen falsch und stürzt bei mehreren Fenstern ab; das Buildskript bricht deshalb ab, wenn es nur 8.5 findet |
| Freier Speicherplatz | Genug Platz für Quelle, temporäre Dateien und fertige Ausgabe |
| Root-Rechte | Für den normalen Betrieb **nicht** erforderlich |

Die macOS-Fassung ist ein Programmbündel (`PS5 Dump & Image Converter.app`). Es wird pro Architektur gebaut – ein auf Apple Silicon erzeugtes Bündel läuft nicht auf einem Intel-Mac und umgekehrt.

Ohne eigenen Mac lässt sich beides auch auf fremder Hardware bauen: Der Workflow [macos-buendel.yml](.github/workflows/macos-buendel.yml) erzeugt die Abbilder für beide Architekturen und legt sie als Artefakt ab (siehe [macOS-Bündel auf fremder Hardware bauen lassen](#macos-bündel-auf-fremder-hardware-bauen-lassen)).

### Für den Python-Start

Zusätzlich werden **Python 3.10 oder neuer** und `pip` benötigt. Die für Anwendung und Build benötigten Pakete werden vom vorhandenen `Build_EXE.ps1` installiert. Für einen normalen Endnutzer ist die fertig gebaute EXE der einfachere Weg.

## Schnellstart

### Fertige EXE verwenden

1. Das vollständige Release in einen eigenen Ordner entpacken.
2. `PS5_Dump_Image_Converter_v1.8.51.exe` starten.
3. Falls Windows nach Administratorrechten fragt, nur fortfahren, wenn die gewählte Aufgabe diese benötigt.
4. Eine der acht Aufgaben auswählen.
5. Quelle, Zielformat und Zielordner festlegen.
6. Den Lauf starten und bis zur Abschlussmeldung warten.

### Python-Version starten

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py
```

### Windows-EXE selbst bauen

Für den einfachsten Weg `Start_Build.bat` per Doppelklick starten. Die Batchdatei ruft das vorhandene Buildskript mit der erforderlichen PowerShell-Ausführungsrichtlinie auf.

Alternativ kann das Skript direkt gestartet werden:

```powershell
.\Build_EXE.ps1
```

Die fertige Datei wird unter folgendem Namen erzeugt:

```text
dist\PS5_Dump_Image_Converter_v1.8.51.exe
```

### Linux-Version selbst bauen

Es gibt keine Fertigdatei zum Herunterladen: Ein Linux-Programm ist an Architektur und C-Bibliothek gebunden, deshalb wird es auf dem Zielsystem gebaut. Der Vorgang dauert wenige Minuten.

```bash
chmod +x Build_Linux.sh
./Build_Linux.sh
```

Das Skript prüft Python und Tcl/Tk, legt bei Bedarf die Umgebung `.venv-linux` an, installiert die benötigten Pakete und erzeugt:

```text
dist/PS5_Dump_Image_Converter_v1.8.51_linux_x86_64
```

**Nicht mit `sudo` bauen.** Das Programm braucht dafür keine Root-Rechte, und ein als root erzeugtes `dist/` lässt sich beim nächsten Lauf als normaler Benutzer nicht mehr aufräumen.

Fehlt Tcl/Tk, bricht das Skript mit dem passenden Installationsbefehl für die erkannte Distribution ab.

### Linux-Version starten und ins Menü legen

```bash
./dist/PS5_Dump_Image_Converter_v1.8.51_linux_x86_64
```

Für einen Eintrag im Anwendungsmenü – samt Symbol und Terminalbefehl `ps5-dump-image-converter`:

```bash
chmod +x Install_Linux.sh
./Install_Linux.sh
```

Alles landet unterhalb von `~/.local`, also ohne `sudo` und ohne Eingriff ins System. Rückgängig machen: `./Install_Linux.sh --entfernen`.

### macOS-Version selbst bauen

Wie unter Linux gibt es keine Fertigdatei zum Herunterladen: Das Bündel ist an die Architektur des Macs gebunden und wird deshalb auf dem Zielsystem gebaut. Der Vorgang dauert wenige Minuten.

```bash
chmod +x Build_macOS.sh
./Build_macOS.sh
```

Das Skript prüft Python und die Tcl/Tk-Version, legt bei Bedarf die Umgebung `.venv-macos` an, installiert die benötigten Pakete, erzeugt `app_icon.icns` und baut:

```text
dist/PS5 Dump & Image Converter.app
```

Zum Schluss wird das Bündel **ad hoc signiert** (`codesign --sign -`). Auf Apple Silicon ist das keine Kür: Dort verweigert das System jede unsignierte Programmdatei den Start. Schlägt `codesign` fehl, fehlen meist die Xcode-Befehlszeilenwerkzeuge (`xcode-select --install`).

Zum Weitergeben zusätzlich ein komprimiertes Abbild erzeugen:

```bash
./Build_macOS.sh --dmg
```

**Nicht mit `sudo` bauen.** Das Programm braucht dafür keine Root-Rechte, und ein als root erzeugtes `dist/` lässt sich beim nächsten Lauf als normaler Benutzer nicht mehr aufräumen.

### macOS-Version starten und ablegen

```bash
open "dist/PS5 Dump & Image Converter.app"
```

Für einen dauerhaften Platz im Programme-Ordner samt Launchpad-Eintrag:

```bash
chmod +x Install_macOS.sh
./Install_macOS.sh
```

Ist `/Applications` nicht beschreibbar, landet das Bündel in `~/Applications` – das braucht kein `sudo` und erscheint genauso im Launchpad. Rückgängig machen: `./Install_macOS.sh --entfernen`.

Wurde das Bündel über Browser, Mail oder AirDrop weitergegeben, meldet macOS beim ersten Start, der Entwickler lasse sich nicht überprüfen. Das Installationsskript räumt diese Markierung selbst ab; von Hand geht es mit:

```bash
xattr -dr com.apple.quarantine "/Applications/PS5 Dump & Image Converter.app"
```

### Quelle/Ziel/Temp per Drag & Drop setzen

Ordner oder Dateien können statt über den Dialog auch direkt aus dem Datei-Explorer in die Felder **QUELLE**, **ZIELORDNER** und **TEMP-ORDNER** gezogen werden. Es gelten dieselben Regeln wie bei der Dialogauswahl (passender Dateityp je Aufgabe); eine ungültige Quelle wird mit derselben Fehlermeldung abgelehnt. Für Aufgabe 5 (Sammelkonvertierung) können mehrere Dateien gleichzeitig auf das Quellfeld gezogen werden. Steht die optionale Bibliothek `tkinterdnd2` nicht zur Verfügung, funktioniert die Anwendung unverändert über die Auswahldialoge weiter.

### Kommandozeilenmodus (CLI) für Automatisierung/Skripte

Für Skripte, geplante Aufgaben oder Batch-Verarbeitung lässt sich jede Aufgabe auch ohne sichtbares Fenster starten. Der CLI-Modus treibt dieselbe geprüfte Ablauflogik wie die GUI an; es gibt keine separate, unabhängige Konvertierungsroutine.

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py --cli --task 1 --source "D:\Dumps\Spiel" --dest "D:\Ausgabe" --format ffpkg --yes
```

| Option | Bedeutung |
| --- | --- |
| `--cli` | Aktiviert den Kommandozeilenmodus (erforderlich). |
| `--task N` | Aufgabennummer 1–8 (alternativ `--mode SCHLÜSSEL`). |
| `--source PFAD [PFAD ...]` | Quellpfad; mehrere Pfade nur bei Aufgabe 5. |
| `--dest PFAD` | Zielordner (nicht nötig bei Aufgabe 8). |
| `--format {folder,ffpfsc,ffpfs,exfat,ffpkg}` | Zielformat, falls die Aufgabe mehrere anbietet. |
| `--temp PFAD` | Temp-Arbeitsordner überschreiben. |
| `--yes` | Überschreib-/Wiederaufnahme-Rückfragen automatisch bestätigen. |
| `--quiet` | Log nicht zusätzlich auf stdout spiegeln. |
| `--shutdown-on-success` | Rechner nach erfolgreichem Abschluss herunterfahren – erst nach Lösen der Abbilder und Aufräumen der Temp-Ziele. Bei Fehler oder Abbruch bleibt er an; der Exit-Code bleibt unverändert. |

Der Prozess beendet sich mit Exit-Code `0` bei Erfolg, `1` bei einem fehlgeschlagenen oder abgebrochenen Lauf und `2` bei ungültigen Argumenten. Administratorrechte werden wie im GUI-Modus automatisch angefordert.

#### Aufgabe 7 (AMPR EMU Manager) im CLI-Modus

Aufgabe 7 fragt ihre Aktion in der Oberfläche über einen Dialog ab. Im CLI-Modus wird dieselbe Auswahl über Argumente übergeben; ohne `--ampr-action` bricht der Aufruf mit Exit-Code `2` ab.

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py --cli --task 7 --source "D:\Dumps\Spiel.ffpfsc" --dest "D:\Ausgabe" --ampr-action ampr_apply --ampr-store "D:\AMPR_EMU" --yes
```

| Option | Bedeutung |
| --- | --- |
| `--ampr-action {ampr_apply,ampr_restore,ampr_remove,ampr_index,ampr_ftp_index}` | Auszuführende Aktion (erforderlich für Aufgabe 7). |
| `--ampr-store PFAD` | Ordner mit den AMPR-/PlayGo-Versionen, z. B. `.../AMPR_EMU`. |
| `--ampr-version WERT` | Gewünschte Version, z. B. `0.2.7.6` (Standard: neueste). |
| `--ampr-variant WERT` | Variante, z. B. `no debug` oder `debug` (Standard: erste passende). |
| `--ampr-lib NAME [NAME ...]` | Zu behandelnde Bibliotheken (Standard: `libSceAmpr.sprx` **und** `libScePlayGo.sprx`). |
| `--ampr-source DATEI` | Eigene `.sprx`/`.prx` statt einer Version aus dem Speicher. |
| `--ampr-no-backup` | Die vom Spiel mitgelieferte Datei nicht als `.orig` sichern. |
| `--ampr-no-index` | `ampr_emu.index` nach der Änderung nicht neu bauen. |
| `--ampr-host IP` | IP-Adresse der PS5 (für `ampr_ftp_index`). |
| `--ampr-port N` | FTP-Port (Standard: automatisch 2121, 2120, 1337, 21 probieren). |
| `--ampr-remote-path PFAD` | Spielordner auf der PS5, der als `/app0` indiziert wird. |
| `--ampr-no-upload` | Index nur lokal erzeugen, nicht auf die PS5 übertragen. |

Bei einem Dump-Ordner als Quelle arbeitet Aufgabe 7 direkt im Ordner; `--dest` entfällt dann. `ampr_ftp_index` arbeitet ausschließlich auf der Konsole und benötigt kein `--source`:

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py --cli --task 7 --ampr-action ampr_ftp_index --ampr-host 192.168.1.94 --ampr-remote-path "/data/homebrew/Mein Spiel" --yes
```

### Kompressionsstufe und Worker-Anzahl einstellen

Unter TEMP-ORDNER bietet die Oberfläche zwei zusätzliche Regler (analog zu ps5-exfat-builder [7]):

| Regler | Wirkung |
| --- | --- |
| Kompression (PFS) | Vier Stufen – 1 Am schnellsten, 3 Schnell, 6 Ausgewogen (Standard), 9 Maximal – steuern den Zstandard-Kompressionsgrad für `.ffpfsc`. Niedrigere Stufen sind bei den meist wenig komprimierbaren PS5-Spieldaten oft die bessere Geschwindigkeits-/Größen-Abwägung. |
| Worker-Threads | Überschreibt die automatische Worker-/Thread-Anzahl für Kopier- und Kompressionsphasen (Standard: die Hälfte der verfügbaren CPU-Kerne). Bestehende Sicherheits-Obergrenzen für sehr große Images bleiben zusätzlich aktiv. |

Beide Werte werden pro Windows-Benutzer gespeichert und beim nächsten Start wiederhergestellt.

### Tastenkürzel

| Kürzel | Wirkung |
| --- | --- |
| `Strg+B` | Startet die aktuelle Aufgabe, sofern STARTEN aktiv ist. |
| `Esc` | Bricht den laufenden Vorgang ab (wird in Eingabefeldern ignoriert). |
| `F5` | Aktualisiert die Quellvorschau/Infobox für den aktuellen Quellpfad. |
| `Strg+Umschalt+T` | Öffnet den FTP-Client. |
| `Strg+Q` | Beendet die Anwendung regulär. |

## Empfohlener Ablauf

Für Einsteiger ist dieser Ablauf am sichersten:

| Schritt | Was zu tun ist |
| ---: | --- |
| **1** | Vorher eine Sicherung der Originalquelle anlegen. |
| **2** | Prüfen, ob ausreichend freier Speicher vorhanden ist. |
| **3** | Die Aufgabe passend zum Quelltyp auswählen. |
| **4** | Quelle und Zielordner sorgfältig kontrollieren. |
| **5** | Nur ein Zielformat wählen, das für den späteren Zweck benötigt wird. |
| **6** | Den Lauf nicht unterbrechen und das Programm nicht schließen. |
| **7** | Auf die grüne Abschlussmeldung beziehungsweise den erfolgreichen Prüfbericht warten. |
| **8** | Erst danach mit der erzeugten Datei weiterarbeiten. |

> **Wichtig:** Eine Dateiendung umzubenennen ist keine Konvertierung. Eine echte `.ffpkg` wird als UFS2-Abbild neu erstellt und geprüft.

## Wichtige Hinweise

### Administratorrechte

Die Aufgaben 1, 2, 4 und 5 sowie UFS2-, Dokan- oder Mount-Abläufe können erhöhte Rechte benötigen. Aufgabe 7 mit einer `.ffpkg`-Quelle benötigt in der Regel ebenfalls Administratorrechte.[5]

### Was außerhalb von Windows anders ist

Die Oberfläche, alle acht Aufgaben in ihren nativen Wegen, der Kommandozeilenmodus, die Übertragung zur PS5 und die Werkzeugfenster arbeiten unter Linux und macOS wie unter Windows. Unterschiede gibt es an diesen Stellen:

| Bereich | Verhalten unter Linux und macOS |
| --- | --- |
| `.ffpkg` lesen und bauen (Aufgabe 4, `.ffpkg`-Ziele) | **Nicht verfügbar.** Beides läuft über UFS2Tool und den Dokan-Treiber – reine Windows-Software. Das Programm sagt das beim Start einer solchen Aufgabe ausdrücklich und nennt dabei das laufende System, statt fehlende Rechte zu melden. |
| OSFMount-Ersatzwege | **Nicht verfügbar.** Sie greifen ohnehin nur, wenn der native Weg an einem untypischen Abbild scheitert. Die nativen MkPFS-/exFAT-Wege sind auf beiden Systemen vollständig vorhanden. |
| Erhöhte Rechte | Werden für den normalen Betrieb **nicht** benötigt. Unter Windows fragt das Programm beim Start nach Administratorrechten, sonst startet es als normaler Benutzer. |
| Einstellungen | Liegen unter `~/.config/PS5ImageConverterPro/` (Linux) bzw. `~/Library/Application Support/PS5ImageConverterPro/` (macOS) statt in `%APPDATA%`. Eine Registrierung in der Registry entfällt; die MIT-Lizenz liegt als Datei bei. |
| Schriftart | Die Oberfläche ist auf *Segoe UI* ausgelegt. Fehlt sie, wählt Linux über fontconfig die erste vorhandene aus *Ubuntu*, *Cantarell*, *Noto Sans*, *DejaVu Sans*, *Liberation Sans*; macOS sieht in seinen Schriftordnern nach und nimmt *SF Pro Text*, *Helvetica Neue* oder *Lucida Grande* (Festbreite: *SF Mono*, *Menlo*, *Monaco*). Wer Microsoft Office installiert hat, bekommt auf beiden Systemen das Windows-Schriftbild. |
| Dateien öffnen | Handbuch, Lizenzen und Zielordner öffnen über `xdg-open` (Linux) bzw. `open` (macOS). „Im Dateimanager zeigen“ läuft unter Linux über die D-Bus-Schnittstelle, die Nautilus, Dolphin, Nemo und Thunar beherrschen, unter macOS über `open -R` – der Finder markiert die Datei dann direkt. |
| Rechner herunterfahren | `--shutdown-on-success` und das Ankreuzfeld nutzen unter Linux `systemctl poweroff`, ersatzweise `shutdown -h now`. macOS geht über die Systemereignisse; beim ersten Mal fragt es dafür die Erlaubnis zur Steuerung anderer Programme ab. |
| Automatische Installation von FileZilla, OSFMount und Dokan | Nur unter Windows. FileZilla wird sonst im `PATH` gefunden, wenn es über die Paketverwaltung bzw. Homebrew installiert ist. |
| Virenscanner-Ausnahmen, Zertifikatsinstallation | Entfallen ersatzlos. |
| Programmsymbol und Signatur (nur macOS) | Das Bündel wird beim Bauen ad hoc signiert. Auf Apple Silicon startet eine unsignierte Programmdatei gar nicht erst; nach jeder Änderung am Bündelinhalt muss neu signiert werden. |

### Freier Speicherplatz

Während einer Konvertierung können temporäre Dateien entstehen. Der freie Speicher sollte deutlich größer als die Quelle sein. Besonders `.ffpkg`-Ausgaben benötigen zusätzliche Reserve für Dateisystemstrukturen und viele kleine Dateien.

### `.ffpkg`-Ausgaben

Eine `.ffpkg` wird als echtes UFS2-Dateisystemabbild erstellt. Der Builder versucht zuerst den dokumentierten `newfs -D`-UFS2-Pfad mit 64-KiB-Block/Fragment. Besteht ein Kandidat die schreibgeschützte Prüfung nicht, löscht die Anwendung ihn und versucht ein unabhängiges 32-KiB/4-KiB-`newfs`-Profil; der ältere explizite `makefs`-Weg bleibt nur als letzter Fallback verfügbar. Nur ein Kandidat, der sowohl `info` als auch `fsck_ufs -fn` besteht, wird atomar als Zieldatei übernommen. OSFMount bleibt auf exFAT-bezogene Mount-Abläufe beschränkt und ist kein Bestandteil der UFS2-/FFPKG-Erstellung.[2] [7] [8]

### `.ffpfsc`-Ausgaben

Der bewährte MkPFS-basierte `.ffpfsc`-Erstellungsweg bleibt unverändert.[3] Dump-Ordner werden zunächst korrekt vorbereitet und anschließend als Container ausgegeben.

### PKG-Merger (Split-Package-Wiederzusammenführung)

Der Button **PKG-MERGER** setzt einen aus Distributionsgründen **geteilten** PS5-`.pkg`-Dateisatz (`<base>_0.pkg`, `<base>_1.pkg`, …, optional `<base>_sc.pkg` als Metadaten-Teil) wieder zu einer vollständigen Datei zusammen. **Wichtig:** Das ist nicht dasselbe wie das Zusammenführen von Basisspiel, Update und DLC – auf der PS5 bleiben das grundsätzlich getrennt installierbare Pakete. Vor dem eigentlichen Zusammenfügen wird der FIH-Header des ersten Teils geprüft (Formatversion, PFS-Offset/-Größe, eingebetteter Metadaten-Offset) und mit der tatsächlichen Größe der nummerierten Teile abgeglichen; nur strukturell konsistente Sätze werden zusammengefügt, optional mit SHA-256-Prüfsumme der Ausgabedatei.

### Param-/Manifest-Editor

Der Button **PARAM/MANIFEST** öffnet eine vorhandene `sce_sys/param.json` oder `manifest.json` oder erstellt ein neues, minimales Dokument. Bekannte Schlüssel (Content-/Title-/Concept-ID, DRM-Typ, Content-Version, Application-Name/-Version u. v. m.) lassen sich über Schnellfelder bearbeiten; alle übrigen Schlüssel – bekannt oder eigen – stehen in einer allgemeinen Tabelle zum Hinzufügen, Bearbeiten und Entfernen bereit (Werte werden als JSON geparst, sonst als Text übernommen). Beim Speichern bleiben nicht erkannte Schlüssel vollständig erhalten; `param.json` wird mit 2, `manifest.json` mit 4 Leerzeichen Einrückung und ohne BOM geschrieben. Es findet keine Signierung oder Verschlüsselung statt.

### Bibliothek

Der Button **BIBLIOTHEK** durchsucht beliebig viele gespeicherte Ordner (nicht rekursiv) nach Dump-Ordnern und `.exfat`/`.ffpkg`/`.ffpfsc`/`.ffpfs`-Containern. Metadaten und Cover werden ausschließlich aus schnell erreichbaren Sidecar-Positionen gelesen (param.json/icon0.png im Dump-Ordner bzw. im selben Ordner wie der Container) – Container werden dabei nicht gemountet oder entpackt, damit ein Scan auch bei vielen Einträgen schnell bleibt. Eine Live-Suche filtert nach Titel, Title-ID oder Pfad; ein ausgewählter Eintrag lässt sich direkt als Quelle für die nächste Aufgabe übernehmen oder im Explorer anzeigen.

### Diagnosebericht

Der Button **DIAGNOSE** schreibt eine zeitgestempelte Textdatei mit App-Version, Betriebssystem/Python-Version, aktueller Aufgabe/Quelle/Ziel, den gespeicherten Einstellungen (Schlüssel mit `password`/`passwort`/`token`/`secret`/`pass` im Namen werden geschwärzt) sowie den letzten Logzeilen. Das Ergebnisfenster bietet **In Zwischenablage kopieren** und **Ordner öffnen**, um den Bericht direkt in eine Fehlermeldung einzufügen oder anzuhängen. Feste Links zu GitHub/Discord/Telegram gibt es bewusst nicht, da für dieses Projekt keine offiziellen Kanäle hinterlegt sind.

### Sprache (Deutsch/Englisch)

Der Button **DE/EN** rechts in der Titelleiste schaltet die komplette Oberfläche zwischen Deutsch und Englisch um – Hauptfenster, alle Dialoge und Nebenfenster sowie sämtliche Protokollmeldungen. Die Sprachwahl wird pro Benutzer gespeichert.

### Klog (Kernel-Log-Monitor)

Der Button **KLOG** verbindet sich per einfachem TCP-Rohsocket mit einer IP/Port-Kombination auf der PS5 (Standardport `3232`, wie bei goldHEN-/etaHEN-Klog-Diensten) und zeigt den zeilenbasierten Kernel-Log live an – farblich nach Error/Warning/Debug/Info eingefärbt, mit Live-Filter, optionalen Zeitstempeln, Pause/Fortsetzen, Leeren und Export in eine Textdatei. IP und Port werden pro Benutzer gespeichert. Es handelt sich um reines Mitlesen über eine bereits offene Log-Verbindung; die Anwendung sendet keine Befehle an die Konsole.

### ShadowMount+ Konfigurationseditor

Der Button **SHADOWMOUNT+** bearbeitet die flache `config.ini` (Schlüssel=Wert je Zeile) des ShadowMount+-Payloads per FTP: **Von PS5 laden**, in einer Tabelle bearbeiten (Hinzufügen/Bearbeiten/Entfernen/Auf Standardwerte zurücksetzen) und **Auf PS5 schreiben** – inklusive Sicherheitsabfrage vor dem Überschreiben. Zusätzlich lässt sich das `debug.log` abrufen. Nutzt einen generischen, getesteten INI-Parser (`ps5_validator/utils/ini_config.py`).

### .ffpfs (unkomprimiertes Zielformat)

Aufgabe 1 ("Dump-Ordner konvertieren") und Aufgabe 3 ("exFAT konvertieren") bieten im Zielformat-Dropdown jetzt zusätzlich **`.ffpfs` (unkomprimiert)** neben `.ffpfsc`. Strukturell identisch zum inneren PFS-Image – lediglich der äußere Kompressions-Schritt (`--compress`/`--no-compress` bei MkPFS) wird uebersprungen. Ergebnis: größere Datei, aber schnellerer Schreib-/Lesevorgang ohne Dekompression. Auch in Aufgabe 5 (Sammelkonvertierung) und Aufgabe 6 (AIO) als Zielformat wählbar. Als reine Eingabe wurde `.ffpfs` bereits zuvor vom Validator/der Bibliothek erkannt – diese Änderung ergänzt die fehlende Ausgabeseite.

### Cross-Drive-Staging-Optimierung

Bei Aufgabe 1 (äußerer FFPFSC-Kompressionsschritt) und Aufgabe 3 (direkte .exFAT→.ffpfsc-Konvertierung) wird die Kompressions-Ausgabe jetzt automatisch auf ein konfiguriertes Temp-Laufwerk umgeleitet, **sofern** dieses auf einem ANDEREN physischen Laufwerk liegt als das Zielverzeichnis und genug freien Speicher bietet (Recherche-Grundlage: `exfat_builder.py`-Kommentar „Output-drive redirection“, liest Quelle und schreibt Ausgabe sonst gleichzeitig auf dieselbe Platte). Nach Abschluss wird die Datei größengeprüft ins Zielverzeichnis verschoben (kein Datenverlust bei Fehlschlag – die Datei bleibt dann auf dem Temp-Laufwerk liegen). Ohne konfiguriertes, abweichendes Temp-Laufwerk bleibt das Verhalten unverändert (direktes Schreiben ins Ziel).

### Live-Systemtelemetrie (CPU/RAM/Temp-Speicher)

Während eine Aufgabe läuft, zeigt eine kleine Statuszeile unterhalb des Fortschrittsbalkens live **CPU-Auslastung**, **RAM-Nutzung** (belegt/gesamt) und **Temp-Speicher-Nutzung** (aktuell/Spitzenwert/frei) an – aktualisiert im Sekundentakt. Nutzt optional `psutil` für CPU/RAM (Recherche-Grundlage: `exfat_builder.py`-Telemetrie-Callback `_emit_build_telemetry`); ist `psutil` nicht installiert, wird nur die Temp-Speicher-Zeile angezeigt (Fallback ohne Fehler). Die eigentliche Phasenanzeige (Scan/Erstellen/Komprimieren/Abschluss) existierte bereits zuvor als Statustext ("Phase X/4 – ...") in den Aufgaben 1 und 3 – diese Änderung ergänzt die fehlenden Systemmetriken.

### SELF-Inspektor

Der Button **SELF-INSPEKTOR** zeigt die Struktur einer PS4/PS5-`SELF`-Datei (Signed ELF: `.self`/`.bin`/`.elf`/`.sprx`/`.prx`) an – Container-Header, Segment-Tabelle (mit Flags: verschlüsselt/komprimiert/signiert/blockweise), eingebetteter ELF-Kopf (Typ/Maschine/Entry-Point) und Extended-Info (Authority-ID mit Kategorie Fake-Debug/Genuine/Privilegiert, Digest). Neues Modul `ps5_validator/utils/self_reader.py` (Byte-Layout aus dem quelloffenen LibProsperoPKG-SDK-Parser `ProsperoFself.cs` recherchiert), 7 Unit-Tests in `test_self_reader.py` (grün) mit synthetischen SELF-Containern.

**Bewusste Grenze:** Es wird **keine echte Entschlüsselung** geschützter Segmente und **keine Signaturprüfung** durchgeführt – dafür wären echte Konsolen-Schlüssel aus einem Exploit-Dump nötig, die dieses Projekt bewusst nicht beschafft. Reine, informative Strukturanzeige.

### Aufgabe 7 und APR-/AMPR-Titel

Aufgabe 7 erkennt geeignete Titel über die vorhandenen PlayGo-Daten. Falls die Erkennung nicht eindeutig ist, fragt die Anwendung nach. Für APR-Titel wird der Ordner mit den benötigten AMPR-Dateien einmal ausgewählt und gespeichert. Anschließend kann die Anwendung `fakelib` vorbereiten und `ampr_emu.index` erzeugen.

### Temporäre Dateien

Nach einer erfolgreichen Abschlussprüfung räumt die Anwendung ihre neu erzeugten temporären Dateien und Ordner auf. Bei einem noch von Windows belegten Pfad wird die Löschung beim Beenden erneut versucht.

## Fortschritt und Abschlussprüfung

Der große Fortschrittsbalken zeigt den Gesamtstand der gewählten Aufgabe. Statuszeile und Detailtext erklären den aktuellen Arbeitsschritt.

| Anzeige | Bedeutung |
| --- | --- |
| Fortschrittsbalken | Gesamtstand der aktiven Aufgabe |
| Prozentwert | Aktueller, sichtbarer Fortschritt |
| `Rest` und `ETA` | Geschätzte verbleibende Datenmenge beziehungsweise Zeit, sobald eine stabile Schätzung möglich ist |
| `Kompr.` | Aktueller MkPFS-Kompressionsschritt; der Hauptbalken bleibt der Gesamtfortschritt |
| `FFPKG: …` | Echter UFS2Tool-Fortschritt einschließlich Datei- und Bytezähler |

Bei der `.ffpkg`-Erstellung bleiben Prozentanzeige, Balken und Detailtext synchron. **100 %** bedeutet erst dann Erfolg, wenn der vorgesehene Abschluss- und Prüfpfad beendet ist.

## Entwicklung und Build

Dieser Abschnitt richtet sich an Entwickler und Tester. Normale Nutzer können direkt zum Beginner-Handbuch wechseln.

### Abhängigkeiten für den direkten Python-Start installieren

```powershell
python -m pip install pillow cryptography zstandard zlib-ng tkinterdnd2 psutil
```

Beim Windows-Build übernimmt `Build_EXE.ps1` diese Installation und richtet zusätzlich PyInstaller ein.

### Quality Suite ausführen

```powershell
python test_all_quality_new.py
```

### Build-Bereitschaft prüfen

```powershell
python test_build_ready.py
```

### EXE bauen

```powershell
.\Build_EXE.ps1
```

Die PyInstaller-Spezifikation erzeugt den synchronisierten v1.8.51-Zielnamen. PyInstaller bündelt die Python-Anwendung für Windows.[6]

### Linux-Programmdatei bauen

```bash
./Build_Linux.sh
```

`PS5ImageConverter_Pro_linux.spec` ist das Gegenstück zur Windows-Spezifikation. Die Unterschiede sind bewusst gesetzt und dort kommentiert:

- kein `icon=`, `version=`, `uac_admin=` – reine Windows-Angaben; das Fenstersymbol setzt die Anwendung zur Laufzeit über `iconphoto()`
- `ps5_ufs2tool_data` ist ausgeschlossen – das Modul enthält ausschließlich Windows-Binärdateien (UFS2Tool, Dokan)
- `PIL._tkinter_finder` steht als versteckter Import darin; ohne ihn baut das Programm anstandslos und stürzt beim ersten Bild im Fenster ab
- der Zielname trägt die Architektur und wird aus `APP_VERSION` gelesen, nicht wiederholt

### macOS-Bündel bauen

```bash
./Build_macOS.sh
```

`PS5ImageConverter_Pro_macos.spec` erzeugt als einzige der drei Spezifikationen kein Einzelstück, sondern ein Programmbündel. Die Unterschiede sind bewusst gesetzt und dort kommentiert:

- `COLLECT` + `BUNDLE` statt einer Onefile-Datei – nur ein Bündel bekommt Symbol im Dock, Namen in der Menüleiste und eine `Info.plist`
- `NSHighResolutionCapable` und `NSRequiresAquaSystemAppearance: false` in der `Info.plist` – ohne das erste ist das Fenster auf jedem Retina-Bildschirm unscharf, ohne das zweite zwingt macOS es ins helle Aqua-Aussehen
- `icon=app_icon.icns` – `.ico` und `.png` zeigt der Finder als leeres Blatt; `extract_icon_icns.py` erzeugt die Datei ohne Apples `iconutil`, also auch auf dem Windows-Rechner
- `argv_emulation=False` – die Emulation fängt Apple-Events mit einer eigenen Ereignisschleife ab, bevor Tk seine eigene startet; das Fenster bleibt danach bis zum ersten Klick taub
- `ps5_ufs2tool_data` ist ausgeschlossen, `PIL._tkinter_finder` steht als versteckter Import darin – beides wie in der Linux-Fassung

### macOS-Bündel auf fremder Hardware bauen lassen

Auf dem Entwicklungsrechner steht kein Mac zur Verfügung. Der Workflow
`.github/workflows/macos-buendel.yml` holt nach, was nur echte Apple-Hardware
beantworten kann – auf **beiden** Architekturen (`macos-14` ist Apple Silicon,
`macos-13` Intel):

1. findet PyInstaller alle Räder in der passenden Architektur,
2. läuft `codesign --deep` über das vollständige Bündel durch,
3. startet das gebaute Programm überhaupt – geprüft über
   `--cli --help`, das denselben Interpreter, dieselben Bibliotheken und
   dieselben eingebetteten Daten lädt wie der Fensterbetrieb, aber ohne
   Bildschirm auskommt.

Der Lauf ruft `./Build_macOS.sh --dmg` auf und legt das Abbild als Artefakt ab.
Bewusst das `.dmg` und nicht das `.app`: Die Artefaktablage zippt ihren Inhalt
und verliert dabei Rechte und Symlinks – die Signatur des Bündels wäre danach
wertlos.

Ausgelöst wird er von Hand („Run workflow") oder von einer Änderung an den
Dateien, die in das Bündel eingehen. Ein Lauf auf macOS zählt zehnfach gegen
das Minutenkontingent; für eine Änderung am Changelog lohnt er nicht.

Ergebnis des ersten Laufs:

| | Apple Silicon | Intel |
| --- | --- | --- |
| Läufer | `macos-14`, macOS 14.8.7 | `macos-15-intel`, macOS 15.7.7 |
| Bauzeit | 0:56 | 2:41 |
| Tcl/Tk | 8.6 | 8.6 |
| Bündel / Abbild | 158 MB / 102 MB | 155 MB / 102 MB |
| Signatur | `valid on disk` | `valid on disk` |
| 39 Tests | grün | grün |

`macos-13` steht bewusst **nicht** in der Matrix: Dieser Läufer sitzt auf der
Hardware, die GitHub abbaut, und ein Job wartete dort 51 Minuten, ohne
überhaupt zu starten. `macos-15-intel` ist der benannte Nachfolger und lief
sofort an.

### Tests unter Linux und macOS

Dieselbe Testsuite läuft auf allen drei Systemen:

```bash
.venv-linux/bin/python test_all_quality_new.py    # Linux
.venv-macos/bin/python test_all_quality_new.py    # macOS
```

Drei Tests prüfen bewusst plattformabhängiges Verhalten und überspringen sich auf dem jeweils anderen System – etwa der Vergleich zweier Pfade, die sich nur in der Groß-/Kleinschreibung unterscheiden: Windows sieht darin denselben Ordner, Linux zwei verschiedene.

`test_macos_fassung.py` prüft die macOS-Fassung von jedem System aus: Es lädt die Plattformschicht ein zweites Mal mit `sys.platform = "darwin"`, liest die `.spec` als Python ein und hält ihre versteckten Importe gegen die der Linux-Fassung. Damit fällt eine auseinandergelaufene Bauvorschrift schon auf dem Entwicklungsrechner auf, nicht erst auf dem Mac.

## Projektstruktur

| Datei oder Ordner | Zweck |
| --- | --- |
| `PS5ImageConverter_Pro_FINAL_revised.py` | Hauptanwendung und grafische Oberfläche |
| `ps5_validator/` | Validatoren und gemeinsame Prüfwerkzeuge |
| `Start_Build.bat` | Windows-Doppelklickstarter für den EXE-Build |
| `Build_EXE.ps1` | Windows-Buildskript |
| `PS5ImageConverter_Pro.spec` | PyInstaller-Konfiguration (Windows) |
| `Build_Linux.sh` | Linux-Buildskript |
| `Install_Linux.sh` | Legt unter Linux Menüeintrag, Symbol und Terminalbefehl an (`--entfernen` macht es rückgängig) |
| `PS5ImageConverter_Pro_linux.spec` | PyInstaller-Konfiguration (Linux) |
| `extract_icon_png.py` | Erzeugt `app_icon.png` für den Linux-Menüeintrag |
| `Build_macOS.sh` | macOS-Buildskript (`--dmg` erzeugt zusätzlich ein Abbild zum Weitergeben) |
| `Install_macOS.sh` | Legt das Bündel im Programme-Ordner ab (`--entfernen` macht es rückgängig) |
| `PS5ImageConverter_Pro_macos.spec` | PyInstaller-Konfiguration (macOS, erzeugt das `.app`-Bündel) |
| `extract_icon_icns.py` | Erzeugt `app_icon.icns` als Symbol des Bündels |
| `ps5_validator/utils/plattform.py` | Betriebssystem-Abstraktion: Schriftwahl, Rechte, Dateien öffnen, Herunterfahren |
| `test_all_quality_new.py` | Aktuelle Quality Suite |
| `test_build_ready.py` | Build-Readiness-Prüfung |
| `test_macos_fassung.py` | Prüft Plattformschicht, `.spec` und Skripte der macOS-Fassung – von jedem System aus |
| `ps5_validator/utils/param_check.py` | Prüft `sce_sys/param.json` inhaltlich und repariert sie |
| `test_param_check.py` | 46 Prüfungen zu Prüfung, Reparatur und CLI-Schaltern |
| `.github/workflows/macos-buendel.yml` | Baut und prüft das macOS-Bündel auf echter Apple-Hardware (beide Architekturen) |
| `.gitattributes` | Schaltet jede Zeilenenden-Umwandlung ab – Python CRLF, Shell-Skripte LF, beides gewollt |
| `CHANGELOG.md` | Vollständige, absteigend sortierte Versionshistorie |
| `BENUTZERHANDBUCH.html` | Bedienanleitung zum Lesen im Browser (v1.8.51, mit Inhaltsverzeichnis, alle Aufgaben und Werkzeugleisten-Buttons) |
| `BENUTZERHANDBUCH.pdf` | Dieselbe Anleitung als 25-seitiges PDF zum Ausdrucken und Weitergeben |

## Credits und Danksagung

### Kernwerkzeuge und technische Grundlagen

- **Phoenixx1202 / PSBrew** für MkPFS[3]
- **SvenGDK und Mitwirkende** für UFS2Tool[2]
- **PassMark Software** für OSFMount[4]
- **Dokan-Projekt** für den Windows-Dateisystemtreiber[5]
- **PyInstaller-Projekt** für den Windows-Build[6]

### Grundlagen des Backports

Die Funktion **BACKPORT** setzt auf Verfahren auf, die in der Szene entwickelt und veröffentlicht wurden:

- **BestPig** für **BackPork**, das Verfahren und den Starter `ps5-backpork.elf`
- **idlesauce** für das ursprüngliche Downgrade-Skript
- **john-tornblom** für `make_fself.py` (Signieren von ELF zu SELF)
- **CyB1K** für **SelfUtil**, dessen Entpackverfahren hier nachgebaut ist
- **PS5 BackPork Kitchen** als Vorlage für Firmware-Profile und Ersatzbibliotheken

### Mitgelieferte Payloads

Ohne die Arbeit dieser Entwickler bliebe die Konsolenseite des Programms leer. Die Zuordnung stammt aus den Dateien selbst – Copyright-Zeilen, Credit-Banner und Projektadressen im jeweiligen Payload –, die vollständige Liste aller 24 Dateien steht in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

- **John Törnblom** und **ps5-payload-dev** für ftpsrv, klogsrv, websrv, OffAct und den App-Dumper
- **drakmor** für ShadowMount+, nanodns und die `-ng`-Fassung von ftpsrv
- **earthonion** für den GarlicSaves-Save-Manager und NP Fake Signin
- **itsPLK** für den PS5 Payload Manager
- **seregonwar** für zftpd (MIT-Lizenz, im Wortlaut beigelegt)
- **OpenSourcereR** für ps5debug-NG
- **maj0r** für CheatRunner
- **Juma Sayeh** für den PS5 Game Compressor
- **aldostools**, **owendswang** und **soniciso** für Payload-Sammlungen und Autoloader
- **Gezine**, **EchoStretch**, **VoidWhisper**, **SiSTRo**, **golden** und **Ctn**, die in den Credits dieser Payloads selbst als Mitwirkende genannt sind

Für Aufgabe 7 liegen der **AMPR-EMU-Resolver** und der **libScePlayGo-Stub** bei, die das Verhalten der Originalmodule nachbilden.

### Weitere Beiträge und Quellen

Weitere Grundlagen und Community-Beiträge stammen unter anderem von KryoMod, Renan Barreto, Y2JB / PS5 Scene Community sowie kerrdec97 für PS5 exFAT Image Builder / ps5-exfat-builder. Ebenso wichtig sind die verwendeten Open-Source-Bibliotheken Pillow, cryptography, zstandard, zlib-ng, tkinterdnd2 und psutil.

Der Online-Nachschlag für Titel und Content-ID bei defekter `param.json` greift auf **prosperopatches.com** zurück – nur auf ausdrückliche Rückfrage und mit nichts als der Title-ID.

Ein Dank geht ebenso an **psxtools.de** – Forum und Community – für Austausch, Rückmeldungen und die Geduld, mit der dort geholfen wird.

Ein besonderer Dank gilt allen Mitgliedern der PS5-Homebrew-Community, die Forschung, Werkzeuge, Code und praktisches Wissen öffentlich teilen.

> Wo eine Nennung fehlt oder falsch zugeordnet ist, ist das ein Versehen und keine Absicht – Hinweise sind ausdrücklich willkommen.

## Vergleich mit anderen PS5-Tools

Dieser Abschnitt ordnet den **PS5 Dump & Image Converter** gegenüber weiteren, in der Szene gepflegten PC- und Konsolen-Werkzeugen ein. Die Einordnung bezieht sich auf den Stand zum Zeitpunkt der Recherche und ersetzt keine eigene Prüfung der jeweiligen Projektseite.

### Direkter Funktionsvergleich (Dump-Ordner → exFAT/ffpkg/ffpfs/ffpfsc)

| Tool | Plattform | Schwerpunkt | Verhältnis zu diesem Programm |
| --- | --- | --- | --- |
| **ps5-exfat-builder** (kerrdec97) [7] | Windows-GUI | All-in-one: Dump → `.exfat`/`.ffpkg`/`.ffpfsc`, Formatkonvertierung, Extraktion, Cover/Bibliothek, FTP-Browser | Funktional großteils deckungsgleich; dieses Programm bietet zusätzlich Aufgabe 7 (`fakelib`/APR-Manager), Aufgabe 8 (Validator), CLI-Modus und Drag & Drop. |
| **PS5-FFPFSC-PRO** (KINGDKAK) [9] | Windows-GUI | Spezialisiert auf `.ffpfsc`-Kompression mit Drag & Drop und Speicherplatz-Warnung | Beide Punkte (Drag & Drop, Speicherplatz-Warnung) sind seit diesem Stand auch hier vorhanden; die `.ffpfsc`-Erstellung nutzt bei uns dieselbe MkPFS-Basis. [3] |
| **PSFFPKG** (sinajet) [8] | Windows-Wrapper | Erstellt `.ffpkg` (UFS2) über UFS2Tool, automatische Größenberechnung | Vergleichbarer Ansatz; dieses Programm ergänzt Temp-Staging, SHA-256-Transferprüfung und doppelte native UFS2-Abnahme vor der atomaren Übernahme. |
| **ps5-ffpfs-cli** (bizkut) [10] | CLI (plattformübergreifend) | Kommandozeilenwerkzeug rund um `.ffpfs`, für Skripte/Automatisierung | Deckt dieselbe Automatisierungs-Nische ab, die der neue `--cli`-Modus dieses Programms für alle acht Aufgaben abdeckt. |
| **Shadowbatch** [11] | Windows-GUI | Stapelkonvertierung mehrerer PS5-Backups nach FFPKG/exFAT inkl. Patch-Verwaltung | Entspricht im Kern Aufgabe 5 (Sammelkonvertierung) sowie der integrierten Update-/Patch-Anzeige dieses Programms. |

### Konsolen-seitige Payloads (Mounten/Installieren auf der PS5)

| Tool | Läuft auf | Zweck |
| --- | --- | --- |
| **ShadowMountPlus** (drakmor) [12] | PS5 (Payload) | Automatischer Auto-Mounter für UFS, exFAT, PFS und verschachtelte komprimierte PFS-Container |
| **PS5-Game-Compressor** (juma-sayeh) [13] | PS5 (Payload) | Komprimiert, entpackt, validiert und repariert ShadowMountPlus-Spiele direkt auf der Konsole |
| **ps5-payload-manager** (itsPLK) [15] | PS5 (Web-Dashboard) | Verwaltet, importiert und lädt Payloads automatisch; eigenes Homescreen-Icon |

Diese drei Werkzeuge laufen auf der Konsole selbst und sind kein Ersatz für die PC-seitige Konvertierung dieses Programms, sondern der folgende Schritt nach dem Erzeugen von `.exfat`/`.ffpkg`/`.ffpfsc`.

### Angrenzendes Ökosystem (kein direkter Funktionsvergleich)

Die folgenden Projekte lösen verwandte, aber andere Aufgaben als die Dump-→-Container-Konvertierung dieses Programms:

| Tool | Zweck |
| --- | --- |
| **ps5upload** (phantomptr) [14] | Sehr umfangreicher, plattformübergreifender PC↔PS5-Transfer über ein eigenes Protokoll (FTX2): schnelle Übertragung, natives Mounten von `.exfat`/`.ffpkg`/`.ffpfs` auf der Konsole, Dateibrowser, Paketinstallation, Payload-Versand, Web-UI. Überschneidet sich mit dem integrierten FTP-Client dieses Programms, ist dabei aber deutlich mächtiger. |
| **fetchpkg** (ps5-payload-dev) [17] | CLI-Werkzeug zum Herunterladen offizieller PS4-/PS5-Updates über ein JSON-Manifest. |
| **LibProsperoPKG** (SvenGDK) [18] | .NET-Bibliothek zum Erstellen/Inspizieren von PS5-`.pkg`-Installationspaketen (GP5/PFS/Fake-Signing). Andere Zieldatei-Domäne als die hier erzeugten Dump-Container. |
| **PS5 Payload SDK** [16] und **SharpProspero** (SvenGDK) [19] | Entwickler-Toolchains (C bzw. C#) zum Programmieren eigener PS5-Homebrew-Anwendungen/Payloads, kein Konvertierungswerkzeug. |

`web.archive.org` diente in dieser Recherche als Fallback, falls einzelne Projektseiten nicht erreichbar waren, und ist selbst kein PS5-spezifisches Werkzeug.

## Lizenz und Verantwortung

Die Lizenzen der **mitgelieferten** Fremdkomponenten stehen in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md); die Datei ist in die Windows-EXE eingebettet und im Fenster **CREDITS** direkt aufrufbar. Sie enthält unter anderem den MIT-Lizenztext von **zftpd** (seregonwar), dessen PS5-Payloads in `helloworld/` liegen und mit ausgeliefert werden.

Vor einer Weiterverteilung müssen die Repository-Dateien und die Lizenzen der gebündelten Werkzeuge geprüft werden. Einzelne integrierte Komponenten können eigene Lizenzbedingungen besitzen.

Die Anwendung sollte ausschließlich für rechtmäßige Inhalte und eigene Sicherungen verwendet werden. Originaldateien sollten vor jeder Bearbeitung separat gesichert bleiben.

## Referenzen

[1]: CHANGELOG.md "Changelog des PS5 Dump & Image Converter"
[2]: https://github.com/SvenGDK/UFS2Tool "UFS2Tool"
[3]: https://github.com/PSBrew/MkPFS "MkPFS"
[4]: https://www.osforensics.com/tools/mount-disk-images.html "OSFMount"
[5]: https://dokan-dev.github.io/ "Dokan"
[6]: https://pyinstaller.org/ "PyInstaller"
[7]: https://github.com/kerrdec97/ps5-exfat-builder "ps5-exfat-builder"
[8]: https://github.com/sinajet/PSFFPKG "PSFFPKG"
[9]: https://github.com/KINGDKAK/PS5-FFPFSC-PRO "PS5-FFPFSC-PRO"
[10]: https://github.com/bizkut/ps5-ffpfs-cli "ps5-ffpfs-cli"
[11]: https://gbatemp.net/threads/shadowbatch-v1-0-convert-single-or-bulk-ps5-backups-to-ffpkg-exfat-patch-management.680097/ "Shadowbatch"
[12]: https://github.com/drakmor/shadowMountPlus "ShadowMountPlus"
[13]: https://github.com/juma-sayeh/PS5-Game-Compressor "PS5-Game-Compressor"
[14]: https://github.com/phantomptr/ps5upload "ps5upload"
[15]: https://github.com/itsPLK/ps5-payload-manager "PS5 Payload Manager"
[16]: https://github.com/ps5-payload-dev/sdk "PS5 Payload SDK"
[17]: https://github.com/ps5-payload-dev/fetchpkg "fetchpkg"
[18]: https://github.com/SvenGDK/LibProsperoPKG "LibProsperoPKG"
[19]: https://github.com/SvenGDK/SharpProspero "SharpProspero"
