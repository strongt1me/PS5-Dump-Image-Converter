# PS5 Dump & Image Converter v1.8.1 – Release Notes

## Zweck dieses Releases

Version **v1.8.1** ist ein reines Oberflächen-Release auf Basis von v1.8.0: Es behebt Farb- und Kontrastfehler in allen drei Designs (Dunkel/Mittel/Hell) und räumt die Titelleiste auf. Die Konvertierungslogik (Aufgaben 1–8) sowie die abgesicherte FFPKG-Kernlogik aus v1.7.90 sind **unverändert**.

## Anlass

Nutzer-Rückmeldung: Das Hell-Design wirkte "ziemlich rudimentär" und nicht sauber geordnet/farblich abgestimmt. Nach Behebung bat der Nutzer um dieselbe Überarbeitung für Dunkel und Mittel sowie um mehrere Anpassungen an der Titelleiste (Buttons entfernen, Reihenfolge ändern).

## Bugfixes: Farbdesign

| Fehler | Betroffene Designs | Fix |
| --- | --- | --- |
| Hover-Text der 16 Titelleisten-Buttons und der 8 Sidebar-Buttons unsichtbar (weißer Text auf weißem/hellem Hover-Hintergrund) | Alle drei, am schwersten in Hell | Hover-Textfarbe nutzt jetzt `fg_primary`/`bg_main` der aktiven Palette statt hart codiertem `"white"` |
| `bg_main`/`bg_card` fast identisch hell/dunkel (Karten verschmelzen mit Hintergrund) | Alle drei (Hell: 1,10:1, Dunkel: 1,17:1, Mittel: 1,26:1 Kontrastverhältnis vor dem Fix) | Paletten angehoben: Hell `bg_main #E4EAF3`/`border #AEBBCE`; Dunkel `bg_card #1C2E48`/`border #425775`; Mittel `bg_card #516489` |
| Fünf Aktions-Buttons: helle Akzentfarbe als Füllung + weißer Text kaum lesbar | Dunkel, Mittel | Textfarbe folgt jetzt `bg_main` der aktiven Palette (invertiert sich passend je Design) |
| Zu blasses Rot bei Löschen-/Fehler-Buttons | Mittel | `error_btn`/`error_btn_hover` von `#F87171`/`#EF4444` auf `#EF4444`/`#DC2626` angepasst |
| Dropdown-Popup von `ttk.Combobox` nie eingefärbt (Windows-Standard weiß/schwarz) | Alle drei, am störendsten in Dunkel | Popup-Farben jetzt über `option_add("*TCombobox*Listbox...")` gesetzt |
| `ttk.Treeview` (Profile, Patch-/Spiele-/Warteschlangenlisten, 12+ Stellen) nie gestylt | Alle drei | Neue globale `Treeview`-/`Treeview.Heading`-Styles |
| `TCheckbutton`/`TNotebook` nie gestylt | Alle drei | Neue globale Styles ergänzt |
| Ordner-Liste im Bibliotheks-Fenster ohne jede Farbgebung | Alle drei | Listbox erhält Farben aus aktiver Palette |
| Theme-Wechsel zur Laufzeit unvollständig (`Toplevel`, `Listbox`, `Text`, `Checkbutton`/`Radiobutton`, `Canvas` blieben unverändert) | Alle drei | `_recolor_widget` um diese Widget-Typen erweitert |
| Sidebar-Buttons ohne sichtbaren Rand | Alle drei | `RoundedButton` erhielt eine `outline`-Option, gefüllt mit der Theme-Rahmenfarbe |

Alle Fixes greifen ausschließlich über die bestehende `self._COLORS`-Palette und wirken damit automatisch in allen drei (und künftigen) Designs.

## Änderungen an der Titelleiste (Nutzerwunsch)

- **Entfernt** (Button, Hover-Handler und Sprachumschalt-Referenz): PS5-GAME-MANAGER, MICROMOUNT, FPKG-BUILDER, DPI-INSTALLER.
- **Entfernt inklusive Funktion**: SELF-INSPEKTOR – Button und die beiden Methoden `_show_self_inspector`/`_render_self_inspector_window` wurden vollständig aus dem Quellcode entfernt. Das unabhängige Parser-Modul `ps5_validator/utils/self_reader.py` und dessen Tests bleiben bestehen.
- **Neue Reihenfolge** (links nach rechts): EN · DIAGNOSE · KLOG · BIBLIOTHEK · SHADOWMOUNT+ · PARAM/MANIFEST · PKG-MERGER · FILEZILLA · JS LOADER · CREDITS · DESIGN · BEENDEN.

Die dahinterliegenden Module der entfernten Buttons (außer SELF-INSPEKTOR) bleiben unverändert im Quellcode erhalten – nur der Einstiegspunkt über die Titelleiste entfällt. `_apply_language()` verwendet für alle Titelleisten-Buttons bereits `getattr(self, attr, None)` mit Null-Check, daher kein Folgefehler bei Sprachumschaltung.

## Dokumentation

- **Neu**: [`BENUTZERHANDBUCH.md`](BENUTZERHANDBUCH.md) – vollständig auf v1.8.1 aktualisierte, nicht technische Bedienanleitung (alle acht Aufgaben plus alle aktuellen Werkzeugleisten-Buttons und die Design-Auswahl). Ersetzt inhaltlich das ältere, bebilderte `Benutzerhandbuch für Beginner.pdf` (Stand v1.7.87), das weiterhin im Repository bleibt.
- **Aufgeräumt**: `CHANGELOG.md` – die Einträge zu v1.8.0 und v1.8.1 waren deutlich ausführlicher als der Rest der Versionshistorie (lange Fließtext-Absätze, wiederholte Test-Bestätigungssätze). Auf Nutzerwunsch auf das etablierte, knappere Format der übrigen Versionen gebracht; keine inhaltlichen Fakten entfernt, nur gekürzt/umformuliert. Ungenutzte Quellenverweise am Dateiende entfernt.

## Abnahmenachweis

Das projekteigene Release-Test-Gate (`.github/skills/release-test/scripts/run_all_tests.py`) bestand vollständig:

- Syntax-Check: bestanden
- Build-Readiness-Tests: 22 Tests bestanden
- Code-Quality-Suite: 39 Tests bestanden

Zusätzlich bestanden alle 77 über `unittest discover` gefundenen Modultests unverändert (keine neuen Testmodule in diesem Release, da rein UI-bezogen). Die Anwendung wurde nach jeder Änderung syntaktisch geprüft und nacheinander in allen drei Designs (Dunkel/Mittel/Hell) live gestartet – jeweils ohne Exceptions.

Die EXE wurde erfolgreich gebaut: `dist\PS5_Dump_Image_Converter_v1.8.1.exe` (29,3 MB).

## Vollständigkeit des Release

Quellcode, Changelog und diese Release Notes sind aktuell. Versionsnummern wurden konsistent in `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`), `README.md`, `Start_Build.bat`, `Build_EXE.ps1`, `PS5ImageConverter_Pro.spec`, `file_version_info.txt` und `test_build_ready.py` auf v1.8.1 angehoben. `SOURCE_FILE_MANIFEST_v1.8.1.sha256` wurde nach dem Build neu erzeugt.
