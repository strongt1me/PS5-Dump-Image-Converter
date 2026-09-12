# -*- coding: utf-8 -*-
"""Anleitungen, die ein Werkzeug sich selbst erklären lässt.

**Warum es das gibt:** Das Fenster *App direkt installieren* trug drei
Absätze Erklärung über den Feldern - vollständig, belegt, und trotzdem
unverständlich. Der Anwender hat es am 12.09.2026 so gesagt: „Bei diesem
Tool steht zwar viel, aber verstehen tut man trotzdem nichts."

Das Problem war nicht die Menge, sondern die Reihenfolge: Der Text begann
mit dem, was das Werkzeug *technisch tut* (``sceAppInstUtilAppInstallAll``),
und beantwortete nie, was der Anwender zuerst wissen will - *wofür brauche
ich das, und was mache ich jetzt?*

Deshalb zwei getrennte Dinge:

* Im Fenster steht nur noch, **was das Werkzeug ist** - zwei Sätze.
* Die ganze Erklärung liegt hinter einem Knopf, als Seite im Browser:
  Was ist das, wofür, was brauche ich, Schritt für Schritt, was geht schief.

Die Seite entsteht zur Laufzeit aus den Texten hier. Das hält sie
zweisprachig, ohne dass eine zweite Datei mitgeliefert und ins Manifest
eingetragen werden muss.
"""
from __future__ import annotations

import html
import io
import os
import tempfile
from typing import Any

#: Die Farben des Benutzerhandbuchs - damit beides gleich aussieht.
_STIL = """
:root{
  --bg:#070b14; --bg2:#0c1322; --karte:#111a2c; --karte2:#16223a;
  --rand:#1f3050; --rand-hell:#2c4470; --text:#dce6f5; --text-leise:#8ea3c4;
  --blau:#2f8fff; --blau-hell:#6fb4ff; --gruen:#3ddc84; --gelb:#ffcc4d;
  --rot:#ff5f6d;
  --schrift:"Segoe UI",-apple-system,BlinkMacSystemFont,Roboto,Helvetica,Arial,sans-serif;
  --mono:"Cascadia Mono",Consolas,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
     font-family:var(--schrift);font-size:16px;line-height:1.7;
     -webkit-font-smoothing:antialiased}
.kopf{padding:52px 40px 44px;
  background:radial-gradient(1100px 380px at 15% -10%,rgba(47,143,255,.28),transparent 60%),
             radial-gradient(800px 340px at 85% 0%,rgba(15,76,156,.35),transparent 65%),
             linear-gradient(180deg,#0a1224 0%,var(--bg2) 100%);
  border-bottom:1px solid var(--rand)}
.kopf-inhalt{max-width:940px;margin:0 auto}
.kopf h1{margin:0 0 10px;font-size:38px;line-height:1.18;font-weight:700;
         letter-spacing:-.5px}
.kopf h1 .akzent{background:linear-gradient(92deg,var(--blau-hell),var(--blau));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.kopf .unter{color:var(--text-leise);font-size:18px;margin:0;max-width:68ch}
main{max-width:940px;margin:0 auto;padding:36px 40px 90px}
section{margin:0 0 34px}
h2{font-size:24px;margin:0 0 14px;font-weight:650;letter-spacing:-.2px}
h2 .nr{display:inline-grid;place-items:center;width:30px;height:30px;
  margin-right:12px;border-radius:9px;background:rgba(47,143,255,.14);
  border:1px solid var(--rand-hell);color:var(--blau-hell);
  font-size:15px;font-weight:700;vertical-align:2px}
p{margin:0 0 14px;max-width:74ch}
.karte{background:var(--karte);border:1px solid var(--rand);border-radius:14px;
       padding:20px 24px;margin:0 0 16px}
.karte h3{margin:0 0 10px;font-size:17px;font-weight:650;color:var(--blau-hell)}
.karte p:last-child{margin-bottom:0}
ol.schritte{counter-reset:s;list-style:none;padding:0;margin:0 0 16px}
ol.schritte>li{counter-increment:s;position:relative;padding:0 0 4px 46px;
  margin:0 0 18px}
ol.schritte>li::before{content:counter(s);position:absolute;left:0;top:0;
  width:30px;height:30px;display:grid;place-items:center;border-radius:50%;
  background:var(--blau);color:#04101f;font-weight:700;font-size:15px}
ul.haken{list-style:none;padding:0;margin:0 0 16px}
ul.haken li{position:relative;padding-left:28px;margin:0 0 9px}
ul.haken li::before{content:"\\2713";position:absolute;left:0;top:0;
  color:var(--gruen);font-weight:700}
code,kbd{font-family:var(--mono);font-size:14px;background:var(--karte2);
  border:1px solid var(--rand);border-radius:6px;padding:2px 7px;
  color:var(--blau-hell)}
table{width:100%;border-collapse:collapse;margin:0 0 6px;font-size:15px}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--rand);
  vertical-align:top}
th{color:var(--text-leise);font-weight:600;font-size:13px;
   text-transform:uppercase;letter-spacing:.6px}
td.code{font-family:var(--mono);color:var(--rot);white-space:nowrap}
.warn{border-left:3px solid var(--gelb);background:rgba(255,204,77,.07)}
.warn h3{color:var(--gelb)}
.gut{border-left:3px solid var(--gruen);background:rgba(61,220,132,.06)}
.gut h3{color:var(--gruen)}
.fuss{color:var(--text-leise);font-size:14px;border-top:1px solid var(--rand);
  padding-top:20px;margin-top:40px}
@media(max-width:700px){.kopf,main{padding-left:22px;padding-right:22px}
  .kopf h1{font-size:30px}}
"""

#: Das Zeichen, das im Text Code einrahmt. Als Name, weil es sonst in
#: jedem zweiten Docstring als Markup gelesen wird.
_CODEZEICHEN = "`"


def _p(text: str) -> str:
    """Wandelt eine Textzeile in HTML.

    Zwei Auszeichnungen, mehr braucht es nicht: ``**fett**`` und das
    Rückwärts-Hochkomma für Code. Alles andere wird maskiert - die Texte
    unten sollen sich lesen lassen, ohne dass jemand HTML darin schreibt.
    """
    teile = html.escape(text)
    for zeichen, marke in (("**", "b"), (_CODEZEICHEN, "code")):
        stueck = teile.split(zeichen)
        teile = ""
        for n, s in enumerate(stueck):
            teile += s if n % 2 == 0 else "<%s>%s</%s>" % (marke, s, marke)
    return teile


#: Die Anleitung zum Werkzeug *App direkt installieren*, in beiden Sprachen.
#:
#: Die Reihenfolge ist der eigentliche Inhalt: erst wofür, dann was man
#: braucht, dann was man tut, und erst ganz am Ende, was schiefgehen kann.
APPINSTALL: dict[str, dict[str, Any]] = {
    "de": {
        "titel": "App direkt installieren",
        "akzent": "Anleitung",
        "unter": "Eine Anwendung auf der PS5 als Kachel anlegen – ohne "
                 "eine Paketdatei zu bauen.",
        "abschnitte": [
            {"h": "Was ist das?", "bloecke": [
                ("p", "Dieses Werkzeug legt die Dateien einer Anwendung "
                      "**direkt** auf die Konsole und sagt ihr dann: „Das "
                      "hier ist ab jetzt eine App.“ Danach steht eine "
                      "Kachel im Menü der PS5, genau wie bei einem "
                      "gekauften Spiel."),
                ("p", "Der Umweg über eine `.pkg`-Datei "
                      "entfällt – und das ist der Punkt: Ein selbst "
                      "gebautes `.pkg` lässt sich zwar "
                      "installieren, **startet aber nicht**. Die Konsole kann "
                      "die Schlüssel dafür nicht ableiten und bricht "
                      "mit `CE-100096-6` ab. Der Weg hier "
                      "funktioniert."),
            ]},
            {"h": "Wofür brauche ich das?", "bloecke": [
                ("karte", "Fall 1 – eine Weboberfläche als Kachel",
                 "Sie haben ein Werkzeug, das im Browser der PS5 läuft "
                 "– etwa einen Payload-Sender oder eine Dateiverwaltung. "
                 "Statt jedesmal den Browser zu öffnen und eine Adresse "
                 "zu tippen, legen Sie eine Kachel an. Ein Druck darauf, und "
                 "die Seite ist offen. **Das ist der erprobte Weg** – er "
                 "braucht kein eigenes Programm und geht immer."),
                ("karte", "Fall 2 – ein eigenes Programm als Kachel",
                 "Sie haben ein selbst gebautes Homebrew mit eigener "
                 "`eboot.bin`. Das lässt sich hier genauso "
                 "anlegen. **Achtung:** Es startet nur, wenn die "
                 "`eboot.bin` mit der Autorität `0x31"
                 "` signiert ist. Der Knopf **Prüfen** sagt Ihnen "
                 "das vorher – drücken Sie ihn zuerst."),
            ]},
            {"h": "Was brauche ich vorher?", "bloecke": [
                ("p", "Auf der **Konsole** müssen zwei Dienste laufen. "
                      "Beide gehören zu jedem gängigen "
                      "Jailbreak-Payload:"),
                ("haken", [
                    "`ftpsrv` auf Port **2121** – darüber "
                    "kommen die Dateien auf die Konsole.",
                    "`elfldr` auf Port **9021** – darüber "
                    "wird die App angemeldet.",
                ]),
                ("p", "Für **Fall 2** brauchen Sie außerdem einen "
                      "Ordner auf dem Rechner mit:"),
                ("haken", [
                    "`eboot.bin` – das Programm selbst. Ein "
                    "**SELF** mit Fake-Autorität, kein rohes ELF.",
                    "`sce_sys/param.json` – darin muss eine "
                    "`titleId` stehen.",
                    "`sce_sys/icon0.png` – das Bild der Kachel. "
                    "Fehlt es, bleibt die Kachel leer.",
                ]),
            ]},
            {"h": "Schritt für Schritt", "bloecke": [
                ("p", "**Fall 1 – Kachel für eine "
                      "Weboberfläche:**"),
                ("schritte", [
                    "Oben **Kachel für eine Weboberfläche** "
                    "wählen.",
                    "**Title-ID** eintragen. Eine frei erfundene reicht, sie "
                    "darf nur keinem echten Spiel gehören – etwa "
                    "`PPSA99001`. Neun Zeichen: vier Buchstaben, "
                    "fünf Ziffern.",
                    "**Angezeigter Name** – was unter der Kachel steht.",
                    "**Adresse** – wohin die Kachel führt, zum "
                    "Beispiel `http://192.168.1.94:8080`.",
                    "**Symbolbild** wählen: eine PNG-Datei, am besten "
                    "512×512.",
                    "**PS5-Adresse** prüfen – die IP Ihrer Konsole.",
                    "**Prüfen** drücken. Im Feld darunter steht, ob "
                    "etwas fehlt.",
                    "**Installieren** drücken und bestätigen. Danach "
                    "steht die Kachel im Menü.",
                ]),
                ("p", "**Fall 2 – eigenes Programm:**"),
                ("schritte", [
                    "Oben **Anwendung mit eigenem Programm** wählen.",
                    "**Ordner wählen** – der Ordner mit "
                    "`eboot.bin` und `sce_sys`.",
                    "**Prüfen** drücken. Steht dort eine "
                    "Autorität von `0x38`, hören Sie hier "
                    "auf: Die App würde mit `CE-108262-9` "
                    "abstürzen. Sie muss mit `0x31` neu "
                    "signiert werden.",
                    "Steht alles auf grün: **Installieren** drücken "
                    "und bestätigen.",
                ]),
            ]},
            {"h": "Was passiert dabei auf der Konsole?", "bloecke": [
                ("p", "Damit Sie wissen, worauf Sie klicken:"),
                ("schritte", [
                    "Die Systempartition wird **kurz beschreibbar** "
                    "geschaltet.",
                    "Die Dateien werden nach `/user/app/<Title-ID>/` "
                    "und `/system_ex/app/<Title-ID>/` gelegt.",
                    "Die Konsole wird aufgefordert, die App anzumelden.",
                    "Erst danach wird `param.json.system` geschrieben "
                    "– die Reihenfolge ist nicht beliebig.",
                ]),
                ("warn", "Eine vorhandene App wird überschrieben",
                 "Liegt unter derselben **Title-ID** schon etwas auf der "
                 "Konsole, wird es ersetzt. Wählen Sie deshalb eine ID, "
                 "die keinem Ihrer Spiele gehört."),
            ]},
            {"h": "Wenn etwas schiefgeht", "bloecke": [
                ("tabelle", ["Meldung", "Was dahintersteckt", "Was hilft"], [
                    ("CE-100096-6",
                     "Die Konsole kann die Schlüssel eines selbst "
                     "gebauten Pakets nicht ableiten.",
                     "Betrifft den .pkg-Weg, nicht diesen hier. Nutzen Sie "
                     "dieses Werkzeug."),
                    ("CE-108262-9",
                     "Die <code>eboot.bin</code> ist mit Autorität "
                     "<code>0x38</code> signiert – der Vorgabe des "
                     "Payload-SDK.",
                     "Mit Autorität <code>0x31</code> neu signieren. Der "
                     "Knopf <b>Prüfen</b> sagt es vorher."),
                    ("Keine Verbindung",
                     "<code>ftpsrv</code> oder <code>elfldr</code> läuft "
                     "nicht.",
                     "Den Jailbreak-Payload erneut ausführen, dann die "
                     "PS5-Adresse prüfen."),
                    ("Kachel bleibt leer",
                     "Es wurde kein <code>icon0.png</code> mitgeliefert.",
                     "Ein PNG wählen und noch einmal installieren."),
                    ("Kachel erscheint nicht",
                     "Das Menü der Konsole hat die Liste noch nicht neu "
                     "gelesen.",
                     "In ein anderes Menü wechseln und zurück, sonst "
                     "die Konsole neu starten."),
                ]),
            ]},
            {"h": "Woher das bekannt ist", "bloecke": [
                ("gut", "Alles hier ist gemessen, nicht vermutet",
                 "Beide Bauformen wurden am 29.08.2026 auf einer echten "
                 "Konsole ausprobiert. Die Kachel für eine "
                 "Weboberfläche startet zuverlässig; die Anwendung "
                 "mit eigenem Programm startet, sobald die Autorität "
                 "stimmt. Die Reihenfolge der Schritte stammt aus "
                 "`samples/install_app` des Payload-SDK."),
            ]},
        ],
        "fuss": "PS5 Dump &amp; Image Converter – Anleitung zum Werkzeug "
                "„App direkt installieren“",
    },
    "en": {
        "titel": "Install app directly",
        "akzent": "Guide",
        "unter": "Put an application on the PS5 as a tile – without "
                 "building a package file.",
        "abschnitte": [
            {"h": "What is this?", "bloecke": [
                ("p", "This tool places an application's files **directly** on "
                      "the console and then tells it: “this is an app "
                      "now.” Afterwards a tile sits in the PS5 menu, just "
                      "like a purchased game."),
                ("p", "It skips the `.pkg` file – and that is "
                      "the point: a self-built `.pkg` does install, "
                      "but **does not start**. The console cannot derive the "
                      "keys for it and fails with `CE-100096-6`. The "
                      "route taken here works."),
            ]},
            {"h": "What do I need this for?", "bloecke": [
                ("karte", "Case 1 – a web interface as a tile",
                 "You have a tool that runs in the PS5 browser – a "
                 "payload sender or a file manager, say. Instead of opening "
                 "the browser and typing an address every time, you create a "
                 "tile. One press and the page is open. **This is the proven "
                 "route** – it needs no program of its own and always "
                 "works."),
                ("karte", "Case 2 – your own program as a tile",
                 "You have self-built homebrew with its own "
                 "`eboot.bin`. That can be installed here just as "
                 "well. **Careful:** it only starts if the "
                 "`eboot.bin` is signed with authority "
                 "`0x31`. The **Check** button tells you beforehand "
                 "– press it first."),
            ]},
            {"h": "What do I need first?", "bloecke": [
                ("p", "Two services must be running on the **console**. Both "
                      "come with every common jailbreak payload:"),
                ("haken", [
                    "`ftpsrv` on port **2121** – the files "
                    "travel through it.",
                    "`elfldr` on port **9021** – the app is "
                    "registered through it.",
                ]),
                ("p", "For **case 2** you also need a folder on the computer "
                      "holding:"),
                ("haken", [
                    "`eboot.bin` – the program itself. A "
                    "**SELF** with a fake authority, not a raw ELF.",
                    "`sce_sys/param.json` – it must carry a "
                    "`titleId`.",
                    "`sce_sys/icon0.png` – the tile's picture. "
                    "Without it the tile stays blank.",
                ]),
            ]},
            {"h": "Step by step", "bloecke": [
                ("p", "**Case 1 – tile for a web interface:**"),
                ("schritte", [
                    "Select **Tile for a web interface** at the top.",
                    "Enter a **Title ID**. A made-up one is fine, it must only "
                    "not belong to a real game – `PPSA99001`, "
                    "say. Nine characters: four letters, five digits.",
                    "**Displayed name** – what appears under the tile.",
                    "**Address** – where the tile leads, for example "
                    "`http://192.168.1.94:8080`.",
                    "Choose an **icon image**: a PNG file, ideally "
                    "512×512.",
                    "Check the **PS5 address** – your console's IP.",
                    "Press **Check**. The field below says what is missing.",
                    "Press **Install** and confirm. The tile is then in the "
                    "menu.",
                ]),
                ("p", "**Case 2 – your own program:**"),
                ("schritte", [
                    "Select **Application with its own program** at the top.",
                    "**Choose folder** – the one holding "
                    "`eboot.bin` and `sce_sys`.",
                    "Press **Check**. If it reports an authority of "
                    "`0x38`, stop here: the app would crash with "
                    "`CE-108262-9`. It has to be re-signed with "
                    "`0x31`.",
                    "If everything is green: press **Install** and confirm.",
                ]),
            ]},
            {"h": "What happens on the console?", "bloecke": [
                ("p", "So you know what you are clicking:"),
                ("schritte", [
                    "The system partition is made **writable for a moment**.",
                    "The files are placed into "
                    "`/user/app/<Title ID>/` and "
                    "`/system_ex/app/<Title ID>/`.",
                    "The console is asked to register the app.",
                    "Only afterwards is `param.json.system` written "
                    "– the order is not arbitrary.",
                ]),
                ("warn", "An existing app is overwritten",
                 "If something already sits under the same **Title ID** on the "
                 "console, it is replaced. So pick an ID that belongs to none "
                 "of your games."),
            ]},
            {"h": "When something goes wrong", "bloecke": [
                ("tabelle", ["Message", "What is behind it", "What helps"], [
                    ("CE-100096-6",
                     "The console cannot derive the keys of a self-built "
                     "package.",
                     "That concerns the .pkg route, not this one. Use this "
                     "tool."),
                    ("CE-108262-9",
                     "The <code>eboot.bin</code> is signed with authority "
                     "<code>0x38</code> – the payload SDK default.",
                     "Re-sign with authority <code>0x31</code>. The "
                     "<b>Check</b> button says so beforehand."),
                    ("No connection",
                     "<code>ftpsrv</code> or <code>elfldr</code> is not "
                     "running.",
                     "Run the jailbreak payload again, then check the PS5 "
                     "address."),
                    ("Tile stays blank",
                     "No <code>icon0.png</code> was supplied.",
                     "Choose a PNG and install once more."),
                    ("Tile does not appear",
                     "The console menu has not re-read its list yet.",
                     "Switch to another menu and back, otherwise restart the "
                     "console."),
                ]),
            ]},
            {"h": "Where this is known from", "bloecke": [
                ("gut", "Everything here was measured, not guessed",
                 "Both shapes were tried on a real console on 29 Aug 2026. The "
                 "tile for a web interface starts reliably; the application "
                 "with its own program starts as soon as the authority is "
                 "right. The order of the steps comes from "
                 "`samples/install_app` of the payload SDK."),
            ]},
        ],
        "fuss": "PS5 Dump &amp; Image Converter – guide to the "
                "“Install app directly” tool",
    },
}


def _block(art: str, *teile: Any) -> str:
    """Setzt einen Inhaltsblock. Eine Sorte je Aufruf."""
    if art == "p":
        return "<p>%s</p>" % _p(teile[0])
    if art in ("karte", "warn", "gut"):
        klasse = "karte" if art == "karte" else "karte " + art
        return '<div class="%s"><h3>%s</h3><p>%s</p></div>' % (
            klasse, html.escape(teile[0]), _p(teile[1]))
    if art == "haken":
        return '<ul class="haken">%s</ul>' % "".join(
            "<li>%s</li>" % _p(t) for t in teile[0])
    if art == "schritte":
        return '<ol class="schritte">%s</ol>' % "".join(
            "<li>%s</li>" % _p(t) for t in teile[0])
    if art == "tabelle":
        kopf = "".join("<th>%s</th>" % html.escape(t) for t in teile[0])
        leib = "".join(
            '<tr><td class="code">%s</td><td>%s</td><td>%s</td></tr>'
            % (html.escape(z[0]), z[1], z[2]) for z in teile[1])
        return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
            kopf, leib)
    raise ValueError("unbekannte Blockart: %s" % art)


def als_html(anleitung: dict[str, Any], sprache: str = "de") -> str:
    """Setzt eine Anleitung zu einer fertigen Seite zusammen.

    Args:
        anleitung: Ein Eintrag wie :data:`APPINSTALL`.
        sprache: ``"de"`` oder ``"en"``. Unbekanntes fällt auf Deutsch
            zurück - eine leere Seite wäre die schlechtere Antwort.
    """
    daten = anleitung.get(sprache) or anleitung["de"]
    teile = []
    for nummer, abschnitt in enumerate(daten["abschnitte"], 1):
        inhalt = "".join(_block(*b) for b in abschnitt["bloecke"])
        teile.append(
            '<section><h2><span class="nr">%d</span>%s</h2>%s</section>'
            % (nummer, html.escape(abschnitt["h"]), inhalt))
    return (
        '<!DOCTYPE html>\n<html lang="%s">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s – %s</title>\n<style>%s</style>\n</head>\n<body>\n"
        '<header class="kopf"><div class="kopf-inhalt">'
        '<h1>%s <span class="akzent">%s</span></h1>'
        '<p class="unter">%s</p></div></header>\n'
        '<main>%s<p class="fuss">%s</p></main>\n</body>\n</html>\n'
        % (sprache, html.escape(daten["titel"]), html.escape(daten["akzent"]),
           _STIL, html.escape(daten["titel"]), html.escape(daten["akzent"]),
           html.escape(daten["unter"]), "".join(teile), daten["fuss"]))


def schreiben(anleitung: dict[str, Any], sprache: str, name: str) -> str:
    """Legt die Seite als Datei ab und gibt ihren Pfad zurück.

    In den Temp-Ordner, unter einem festen Namen je Sprache: Wer den Knopf
    zweimal drückt, soll nicht zwei Dateien hinterlassen. Ein Fehlschlag
    wirft - der Aufrufer soll ihn melden, nicht stillschweigend nichts tun.
    """
    ziel = os.path.join(tempfile.gettempdir(), "%s_%s.html" % (name, sprache))
    with io.open(ziel, "w", encoding="utf-8") as fh:
        fh.write(als_html(anleitung, sprache))
    return ziel
