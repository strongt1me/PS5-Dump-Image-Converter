# Release Notes – v1.8.67

**Datum:** 20.08.2026
**Vorgänger:** v1.8.66

Diese Ausgabe hat zwei Schwerpunkte: Container werden vollständig ausgepackt, egal wie sie gebaut wurden – und PS4-Spiele lassen sich jetzt direkt im Programm zu einem ShadowMountPlus-Abbild zusammenführen.

---

## 1. Jede Bauart einer .ffpfsc wird vollständig entpackt

### Der Befund

Eine `.ffpfsc` sieht von außen immer gleich aus. `mkpfs tree` und `inspect` zeigen bei jeder Bauart genau einen Eintrag. Tatsächlich gibt es vier:

| Wie gebaut | Aufbau |
| --- | --- |
| `mkpfs pack folder … --raw` | Container → rohes PFS → Spieldateien |
| `mkpfs pack folder …` | Container → exFAT-Abbild → Spieldateien |
| `mkpfs pack file …` | Container → eingebettetes Abbild |
| beides hintereinander | Container → PFS → exFAT → Spieldateien |

Dabei ist wichtig: **`mkpfs pack folder` nimmt ohne `--raw` immer den Wrapper-Weg.** Der Ordner wird selbst in ein exFAT gewickelt und komprimiert; `--no-compress` wirkt auf diesem Weg gar nicht.

Aufgabe 2, 4 und 7 entschieden bisher nach der Frage „liegt im Container ein Ordner oder eine Datei?" und packten höchstens **eine** Ebene tiefer aus. Bei einem Container mit einer Ebene mehr kam deshalb eine einzelne `.exfat`-Datei heraus – und Aufgabe 4 meldete trotzdem Erfolg.

### Was geändert wurde

- Alle drei Aufgaben teilen sich jetzt dieselbe Auspack-Schleife (`_entpacke_container_ebenen`). Entschieden wird an der Kennung des Abbilds – exFAT-Signatur, PFS-Magic, UFS2-Superblock –, nicht an Name oder Endung.
- Nach dem Auspacken wird gegen die Sollwerte des innersten Abbilds gezählt. Fehlen Dateien oder Bytes, bricht die Aufgabe mit dem genauen Fehlbetrag ab.
- Das Verschieben ins Ziel führt gleichnamige Ordner zusammen und lässt die Aufgabe bei einem Fehlschlag scheitern. Vorher wurde er nur protokolliert – und der Ordner mit den betroffenen Dateien direkt danach gelöscht.
- Jedes ausgepackte Abbild wird nach seiner Ebene gelöscht. Das halbiert den Spitzenplatzbedarf; bei einem 159-GB-Container sind das rund 246 GB weniger.
- Der Validator prüft die Pflichtdateien jetzt auch **innerhalb** eines exFAT-Innenabbilds.

### Nachgemessen

An vier echten Containern (bis 159 GB) wurde geprüft, dass der exFAT-Leser jede belegte Cluster-Zelle erfasst – die Leseseite verliert nichts. Der Fehler lag ausschließlich in der Ablaufsteuerung.

**Die Erstellung von Containern ist unverändert.** Der Umbau betrifft nur Lesen, Anzeigen und Prüfen.

---

## 2. Bauart-Anzeige neben QUELLE

Sobald eine `.ffpfsc`/`.ffpfs` als Quelle anliegt, steht rechts neben „QUELLE", was darin steckt: exFAT-Innenabbild, PFS-Innenabbild, ohne Innenabbild, UFS2-Innenabbild – oder in Orange „eine Ebene zu viel". Ein Tooltip erklärt jede Bauart und nennt im Warnfall den Weg zum richtigen Bau.

Die Prüfung läuft im Hintergrund und liest nur Kopf, Inode-Tabelle und Verzeichnisblöcke: gemessen 0,01 s bei kleinen Dateien, 5 s bei einem 117-GB-Container.

---

## 3. .ffpfsc ↔ .ffpfs

Beide Richtungen waren mit dem Hinweis „lässt sich nicht nachträglich entpacken" gesperrt. Seit dem vollständigen Auspacken stimmt das nicht mehr: Der Weg ist derselbe wie zu `.ffpkg` – erst in den Dump-Ordner, dann neu bauen. Aufgabe 2 bietet beide Formate an; das Selbst-Ziel bleibt gesperrt.

---

## 4. Neu: PS4 PKG zu ffpfsc

Neuer Eintrag unter **WEITERE TOOLS**. Er führt PS4-PKG (Basis, Patches, wahlweise DLC) oder ein bereits entpacktes PS4-Spiel zu einem ShadowMountPlus-Abbild zusammen – als `.ffpfsc` oder als unkomprimiertes `.exfat`.

**Umsetzung:** Eingebettet ist der Arbeitsteil von PS4 FFPFSC 0.2.8 (GPL-3.0) samt PKG-Entpacker, DLC-Helfer und der von ihm geprüften MkPFS-Fassung 1.0.0 – zusammen 4,9 MB. Die Qt-Oberfläche der Vorlage bleibt außen vor; die Oberfläche stellt dieses Programm, auf Deutsch und Englisch. Einzelheiten in `PS4FFPFSC-0.2.8/UPSTREAM.md`.

### Behobene Fehler des Werkzeugs

1. **`doctor` verlangte Compiler und CMake**, obwohl der fertige Entpacker daneben liegt. Die Prüfung hing an „ist die Anwendung eingefroren?" statt an „ist ein Entpacker da?" – das Gesamturteil lautete deshalb immer „nicht bereit".
2. **Ein Absturz des Entpackers galt als „PKG nicht unterstützt".** Beim Prüfen mit Prüfsumme bricht er mit einem Stapelüberlauf ab (Rückgabewert `0xC00000FD`, an mehreren PKG nachgemessen). Der Rückgabewert wurde nicht ausgewertet. Jetzt wird ohne Prüfsummenlauf wiederholt und diese in Python nachgerechnet.
3. **Zu lange Arbeitspfade ließen das Entpacken scheitern** („Failed to write extracted PKG entry"). Ab etwa 150 Zeichen Arbeitsordner sprengen die inneren Pfade die 260-Zeichen-Grenze von Windows. Das Programm weicht jetzt auf einen kurzen Pfad aus und schreibt es ins Protokoll.

### Nachgewiesen

Ein vollständiger Durchlauf mit einer echten PS4-PKG (`CUSA00775`, 130 MB) erzeugte ein `.ffpfsc` von 80,75 MB. Die Prüfung von MkPFS meldet 0 Fehler; der eigene Validator bestätigt „in Ordnung (exFAT-Abbild im Container)", 113 innere Dateien, Pflichtdateien vollständig.

### Bekannte Grenzen

Beides stammt aus der Vorlage und besteht weiter:

- Manche Spiele scheitern auf der Konsole an der Trophäenregistrierung (`errcode=0x80551618`). Die Trophäendatei liegt im erzeugten Abbild – der Fehler entsteht auf der Konsole, nicht beim Bauen.
- Die DLC-Einbettung ist ausdrücklich experimentell: nicht mit allen Spielen und DLC-Arten verträglich. Sie ist standardmäßig aus und fragt vor dem Start nach.

---

## Prüfung

- Gesamte Testreihe grün, davon neu: `test_ffpfsc_entpacken.py` (Auspacken aller Bauarten, Vollständigkeit, Verschieben, Bauart-Anzeige, Aufgabe 2 und 7) und `test_ps4_pkg_converter.py` (Einbettung, interne Modi, die beiden behobenen Werkzeugfehler, Pfadgrenze).
- Die Quality-Prüfungen sichern jetzt ab, dass Aufgabe 2 **und** 7 dieselbe Auspack-Schleife benutzen – vorher wurde je Aufgabe nach einem Protokolltext gesucht, sodass eine Korrektur nur die Hälfte erreichen konnte.
