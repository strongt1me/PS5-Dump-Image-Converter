# Release Notes – v1.8.72

**Datum:** 21.08.2026
**Vorgänger:** v1.8.71

`.ffpkg` läuft jetzt auf allen drei Systemen, und die dafür nötige Voraussetzung ist verschwunden statt nur dokumentiert.

---

## Der stille Fehler, den niemand sehen konnte

Das Programm bringt UFS2Tool 4.1 mit. Bis jetzt lag nur ein Windows-Bau bei, als Base64 in `ps5_ufs2tool_data.py`. Ich habe ihn ausgepackt und seine `runtimeconfig.json` gelesen:

```json
"framework": { "name": "Microsoft.NETCore.App", "version": "8.0.0" }
```

**Er war framework-abhängig.** Auf einem Rechner ohne installiertes .NET 8 scheiterte jeder `.ffpkg`-Vorgang – und nichts im Programm nannte den Grund. Auf einem Entwicklungsrechner fällt so etwas nie auf, weil .NET dort ohnehin liegt.

Mitgeliefert wird jetzt für jede Plattform ein **eigenständiger** Bau: getrimmt, als eine einzige Datei, ohne Globalisierung. Kein .NET mehr nötig, nirgends.

| Plattform | Größe |
| --- | --- |
| win-x64 | 11,9 MB |
| linux-x64 | 12,9 MB |
| osx-x64 | 12,9 MB |
| osx-arm64 | 12,2 MB |

Jede Fassung des Programms nimmt nur ihre eigene Plattform mit; das macOS-Bündel beide Apple-Architekturen. Gebaut aus dem Quelltext (BSD-2-Clause), die Bauweise steht in `UFS2Tool-4.1/pruefsummen.json`, und jede Datei wird beim Start gegen ihre SHA-256 geprüft.

---

## `.ffpkg` unter macOS und Linux

Bisher stand in der Liste der Windows-Werkzeuge: *„UFS2Tool – Lesen und Bauen von .ffpkg-Abbildern"*. Das war **unsere Packentscheidung, keine Grenze des Werkzeugs**. Sein README nennt Windows, macOS und Linux, und alle Abbild-Operationen arbeiten auf Dateien.

Von den Unterbefehlen, die das Programm verwendet, braucht genau einer Windows:

| Unterbefehl | Stellen im Programm | plattformgebunden? |
| --- | --- | --- |
| `extract` | 22 | nein |
| `info` | 19 | nein |
| `newfs` | 8 | nein |
| `fsck_ufs` | 5 | nein |
| `makefs` | 2 | nein |
| `mount_udf` | 3 | **ja** – braucht den Dokan-Treiber |

Also:

- **Bauen** läuft überall. `newfs` und `makefs` schreiben eine Datei und hängen nichts ein. Die Rechteprüfung bleibt Windows vorbehalten – nur dort verlangt das Programmmanifest von UFS2Tool die Erhöhung.
- **Lesen** läuft außerhalb von Windows über `UFS2Tool extract`, das ohne Einhängen auskommt. Unter Windows bleibt der Weg über ein Dokan-Laufwerk, weil sich dort der Fortschritt Datei für Datei mitzählen lässt.

---

## Nachgemessen, nicht angenommen

Unter Linux mit **unserem eigenen Befehlsbauer**, beide Profile:

```
Referenz (64 KiB)      newfs -O 2 -b 65536 -f 65536 -S 512 -m 0 -i 262144 -D …
                       → 13,6 MB, Magic 0x19540119 (gültiges UFS2)
                       → zurückgeholt: alle Dateien Byte für Byte identisch

Kompatibel (32/4 KiB)  newfs -O 2 -b 32768 -f 4096 -S 512 -D …
                       → 13,3 MB, Magic 0x19540119
                       → zurückgeholt: alle Dateien Byte für Byte identisch
```

Zwei Fallen sind dabei aufgefallen und ausgeräumt, die sonst erst beim Nutzer aufgeschlagen wären:

- **Ohne `InvariantGlobalization=true`** verlangt der Start unter Linux `libicu` und bricht mit „Couldn't find a valid ICU package" ab.
- **`extract` nimmt die Argumente als `<abbild> <ausgabeordner>`** – andersherum meldet es „Path component 'tmp' not found in inode 2", also einen Pfadfehler, wo keiner ist.

---

## Der Diagnosebericht kennt UFS2Tool jetzt als mitgeliefert

Im Abschnitt „Mitgelieferte Werkzeuge" steht es mit Fassung, Plattform und Quelle:

```
UFS2Tool (win-x64): 4.1.0  [SvenGDK/UFS2Tool]
```

Damit fragt die Aktualisierungsprüfung auch dieses Projekt mit ab. Aus der Liste der Fremdwerkzeuge, die der Nutzer selbst installieren muss, ist es verschwunden – dort stehen nur noch FileZilla und OSFMount.

---

## Prüfung

- **1090 Tests grün** (3 übersprungen), 14/14 Quality-Tests.
- `test_ufs2tool_runtime_bundle.py` neu geschrieben: 15 Fälle – Vollständigkeit je Plattform, Prüfsummen gegen die Dateien, die festgehaltene Bauweise, die Plattformwahl, das Ablehnen einer verfälschten Datei und die gefallenen Sperren.
- Die alte Base64-Einbettung ist entfernt (714 KB), samt ihrer Verweise in drei Bau-Spezifikationen und zwei Tests.

---

## Was nicht übernommen wurde

Aus derselben Quelle lagen noch zwei Dinge vor, die nichts beitragen:

- **PSFFPKG** (Skript und 7,8-MB-EXE) ist eine Hülle um einen einzigen Aufruf: `newfs -O 2 -b 32768 -f 4096 -D`. Genau den erzeugt `build_newfs_directory_command` seit jeher, plus `-S` und optional `-m`/`-i`.
- Die **Avalonia-Oberfläche** von UFS2Tool, rund 480 MB der mitgelieferten Bauten. Das Programm bringt sein eigenes Fenster mit.
