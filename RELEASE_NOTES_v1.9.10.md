Diese Fassung bringt keine neuen Funktionen. Sie ist das Ergebnis eines
Durchgangs durch **alle acht Aufgaben, alle Zielformate, alle vier
Kompressionsstufen und alle zweiundzwanzig Werkzeugfenster** — 49
Konvertierungsläufe an drei verschiedenen Sicherungen, dazu jedes Fenster
einmal geöffnet und wieder geschlossen.

Vier Dinge sind dabei aufgefallen. Zwei davon betrafen Aufgabe 7 und waren
so gebaut, dass sie sich gegenseitig verdeckten.

## Aufgabe 7 verlangte ein Zielverzeichnis, das sie nie benutzt

Der AMPR EMU Manager arbeitet im Spielordner selbst — er tauscht dort eine
Bibliothek aus und baut den Index neu. Ein Ziel hat er nicht.

Trotzdem bestand die Vorprüfung auf einer Zielangabe, und ohne sie ließ sich
Aufgabe 7 **überhaupt nicht starten** — weder im Fenster noch über die
Kommandozeile. Dass es ein Versehen war, zeigt die Speicherplatz-Prüfung
unmittelbar darunter: Sie nimmt Aufgabe 7 seit jeher aus. Die Ausnahme fehlte
nur eine Prüfung weiter oben.

Ein Ziel darf man weiterhin angeben; dann landet der Index dort. Nötig ist es
nicht mehr. Ein angegebenes, aber nicht vorhandenes Ziel wird nach wie vor
beanstandet — ein Tippfehler soll nicht stillschweigend im Spielordner landen.

## „Asset-Pack herausnehmen“ baute es sofort wieder auf

Der Knopf aus v1.9.9 entfernte Manifest, Laufzeitdatei und die `.pak`-Bänder —
und legte sie im selben Durchlauf wieder an, sobald die Methode auf
*Asset-Pack* stand. Also genau dann, wenn man ihn braucht.

Die Ursache steckt in der Ablauffolge: Die Aktion meldet „im Ordner wurde
etwas geändert“, und der Schritt dahinter baut bei jeder Änderung ein Pack,
wenn die neue Methode eingestellt ist. Beides zusammen hob sich auf.

Sichtbar war davon nichts. Das Protokoll meldete „Erfolgreich abgeschlossen“,
und im Ordner lagen weiterhin alle sechs Dateien. Wer das Pack loswerden
wollte, hatte es noch, ohne es zu merken.

Nachgemessen an einem echten Spielordner mit 72 Dateien:

| Schritt | Packdateien im Ordner |
| --- | --- |
| vorher | 0 |
| nach dem Packen | 6 |
| nach dem Herausnehmen | **0** |

Vor der Behebung standen nach dem Herausnehmen wieder 6 da.

## Die Fassungsangabe aus der Klappliste taugt jetzt auch für die Kommandozeile

Das Fenster zeigt `0.4.2.1 test-pack` — Fassung und Variante in einem Stück —
und speichert es auch so. Wer das ablas und als `--ampr-version` einsetzte,
bekam:

> Keine passende Datei im Versionsordner für libSceAmpr.sprx
> (Version 0.4.2.1 test-pack, Variante *)

Die Meldung deutete auf eine fehlende Fassung, dabei stimmte nur die
Schreibweise nicht.

Beide Formen gehen jetzt:

```
--ampr-version "0.4.2.1 test-pack"
--ampr-version "0.4.2.1" --ampr-variant "test-pack"
```

Eine Variante mit Leerzeichen (`no debug`) bleibt dabei ganz; getrennt wird
nur am ersten Leerzeichen.

## Der AMPR-Index-Builder hatte keinen SCHLIESSEN-Knopf

Beim Durchgehen aller Werkzeugfenster war er das einzige mit richtigen Knöpfen
(„Durchsuchen“, „Index bauen“) und ohne einen zum Schließen — nur das X der
Fensterleiste half. Nachgeholt, und die Wache, die das für vier andere Fenster
schon prüfte, deckt ihn jetzt mit ab.

---

### Was der Durchgang sonst ergeben hat

Die übrigen 46 Konvertierungsläufe liefen durch, mit Prüfung. Zwei Belege, die
über „kein Fehler“ hinausgehen:

- **Rundweg:** Aus einem Dump-Ordner mit 191 Dateien (648.398.581 Bytes) über
  `.ffpfsc` *und* über `.exFAT` zurück — beide Male exakt dieselbe Zahl an
  Dateien und dieselbe Byte-Summe.
- **Kompressionsstufen:** 184,5 → 161,2 → 160,0 → 157,1 MB für die Stufen
  1/3/6/9. Die Auswahl wirkt also wirklich; das war sie einmal nicht.

### Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.10.exe` | Windows 64-bit |
| `PS5_Dump_Image_Converter_v1.9.10_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.9.10.sha256` | Prüfsummen der Quelldateien |

Beide Programmdateien laufen eigenständig; es muss nichts nachinstalliert
werden.
