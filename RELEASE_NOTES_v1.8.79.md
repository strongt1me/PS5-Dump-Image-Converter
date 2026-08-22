# Release Notes – v1.8.79

**Datum:** 22.08.2026
**Vorgänger:** v1.8.78

Eine lange Fehlersuche an der echten Konsole – und am Ende lag es an einer Datei, die niemand abholt.

---

## PS5-Pakete werden benannt statt verschwiegen

Legt man einen Ordner mit PS5-Paketen ins PS4-Fenster, stand dort bisher nur **„0 Spiel(e) gefunden"**. Keine Zeile im Protokoll, kein Grund, nichts. Jetzt liest das Programm beim Einlesen die ersten vier Bytes jeder Datei:

```text
In der Quelle liegen 4 Paket(e) für die PS5. Dieses Fenster baut Abbilder aus
PS4-Paketen; PS5-Pakete kann das eingebettete Werkzeug nicht öffnen. Sie
bleiben unberücksichtigt:
    Mafia.The.Old.Country.Gatto.Nero.Pack.DLC.PS5-DUPLEX.pkg
    …
```

`\x7FCNT` ist ein PS4-Paket, `\x7FFIH` ein PS5-Paket. Kein Entpacken, keine Wartezeit. An **31 Paketen** eines Datenträgers nachgemessen — 20 PS4, 11 PS5 — und das Kennzeichen stimmte ausnahmslos mit der Title-ID im Paket überein.

Der Anlass war eine Fehlannahme, die sich messen ließ: Der eingebettete Entpacker weist jedes PS5-Paket ab, an 11 von 11 mit demselben Wortlaut (`Invalid PKG magic`). Ein PS5-Paket in dieses Fenster zu legen kann also nie funktionieren — das darf man dann auch sagen.

## Der Ablageort-Hinweis kommt zweimal statt viermal

Einmal **eine Minute nach dem Start**, einmal **bei der Hälfte**.

Die erste hängt bewusst an der Uhr statt am Fortschritt. Gemessen an einer echten Konvertierung: Der Balken erreicht 50 % schon nach 10 Sekunden und steht bei 60 Sekunden bereits bei 74 % — er läuft nicht gleichmäßig, das Entpacken meldet früh viel Fortschritt und das Packen kriecht danach. „Eine Minute nach dem Start" ist dagegen bei jedem Spiel dieselbe Stelle.

Dauer und Aussehen bleiben: 25 Sekunden, langsam ein- und ausgeblendet, kein Klick nötig. Steht gerade eine Einblendung, fasst der Wecker alle zwei Sekunden nach, statt sich darüberzulegen; beim Ende wird er abgestellt.

## Richtigstellung: eigene Ordner auf dem Stick

In v1.8.77 stand, ein selbst angelegter Ordner wie `/mnt/usb0/ps4ffpsc/` werde „nicht gefunden". Das war zu absolut, und der Nutzer hat zu Recht widersprochen. An der Konsole in drei Schritten nachgemessen:

| Schritt | Ergebnis |
| --- | --- |
| Abbild nach `/mnt/usb0/ps4ffpsc/`, 190 s gewartet | nicht gefunden — die automatische Suche geht nicht hinein |
| Pfad in `/data/shadowmount/manual.lst` eingetragen | sofort eingehängt und registriert |
| Spiel gestartet | `[GAME] started: CUSA00775 pid=121` — es **läuft** von dort |

Der Rat der Vorlage war also nicht falsch, sondern **unvollständig**: Sie nannte den Ordner und darunter dieselbe Zeile für `manual.lst`, ohne zu sagen, dass der Eintrag dafür nötig ist.

Nur ist er nicht neustartfest. Der Eintrag hält einen absoluten Pfad samt Einhängepunkt fest — und beim Nutzer wurde der Spiele-Stick nach einem Neustart von `usb0` zu `usb1`, weil zwei USB-Geräte angeschlossen sind. Der Titel war weg, während ein anderes Spiel aus der Stickwurzel unverändert lief.

**Deshalb weiterhin: Abbild direkt in die Wurzel.** Nicht weil ein Unterordner unmöglich wäre, sondern weil die Anheftung daran zerbricht. Fenstertext, Begleitdatei und Handbuch sagen das jetzt so.

## Neu dokumentiert: warum die Trophäen scheitern

Startet ein PS4-Spiel aus einem Abbild, meldet die Konsole bei **jedem** Start:

```text
[Trophy:Register] ** Trophy registration failed. errcode=0x80551618 **
```

Die Ursache liegt nicht im Abbild. `update_trophy_metadata()` in ShadowMountPlus kopiert nach `/system_data/priv/appmeta/<TITLE>/` nur `sce_sys/trophy2/npbind.dat` und `sce_sys/uds/npbind.dat` — beides **PS5**-Pfade. Ein PS4-Spiel legt die NP-Bindung flach unter `sce_sys/npbind.dat` ab, und eine fehlende Quelle gilt dort ausdrücklich als Erfolg. Die beiden Ordner werden angelegt und bleiben leer.

An der Konsole belegt:

| `/system_data/priv/appmeta/<TITLE>/` | über Package Installer | über ShadowMountPlus |
| --- | --- | --- |
| `npbind.dat` | **532 Bytes vorhanden** | **fehlt** |
| `trophy2/`, `uds/` | — | **leer angelegt** |

Und die Gegenprobe: Datei von Hand nachgelegt, Spiel gestartet — **immer noch aus dem Abbild** —, der Fehler ist weg und der Trophäendienst greift zu. In drei Mitschnitten davor stand er jedes Mal drin.

Das Programm sagt das jetzt nach jedem Bau eines PS4-Abbilds, und im Handbuch steht der ganze Zusammenhang samt der Stelle, an der die Datei fehlt. Ohne diese Erklärung sieht es aus wie ein Fehler der Konvertierung — und ist keiner.

## Kleinigkeiten

Sieben deutsche Texte standen in Ersatzschreibung (`fuer`, `oeffnen`, `nachpruefen`), während der Rest der Oberfläche echte Umlaute setzt. Darunter die Meldung `Das Abbild liess sich nicht nachpruefen`, die in v1.8.78 so ausgeliefert wurde. Alle korrigiert, ein Test hält es fest.

Der Absatz zu **v1.8.78** fehlte im README ganz. Das Skript, das ihn einsetzen sollte, hatte eine Prüfung mit `or` und ging durch, ohne etwas zu tun. Er ist jetzt nachgetragen.

## Nachgeprüft

**1172 Tests grün**, drei übersprungen. Neu sind unter anderem sieben zur Konsolenerkennung am Magic, zwei, die den Wecker der Einblendung wirklich stellen und ablaufen lassen, und einer, der die NP-Lücke in Text und Handbuch festhält.

## Was offen bleibt

Ein PS4-Titel hängt beim Start aus dem Abbild in einem „Bitte warten", während dasselbe Paket über den Package Installer seinen Offline-Dialog zeigt und weiterläuft. Ausgeschlossen sind: der Ablageort, fehlende PlayGo-Inhalte, eine Netzwartezeit (auch ohne Netz derselbe Hänger), und ein unvollständiges Abbild — Datei für Datei verglichen, 113 zu 113, keine Größenabweichung. Dass es an derselben fehlenden NP-Bindung liegt, ist naheliegend, aber nicht gemessen.

Der Patch dieses Titels ließ sich nicht einbauen: Der eingebettete Entpacker stürzt an dieser einen Datei reproduzierbar ab (`0xC0000005` beim Entpacken, `0xC00000FD` bei der Prüfsumme), während ein größeres Update desselben Typs sauber durchläuft. Eine neuere Fassung des Werkzeugs gibt es nicht.
