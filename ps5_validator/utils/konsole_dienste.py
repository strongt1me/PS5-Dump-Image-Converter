# -*- coding: utf-8 -*-
"""Welche Dienste laufen gerade auf der Konsole?

Die haeufigste Ursache, wenn etwas mit der PS5 nicht klappt, ist banal: Das
Payload laeuft nicht. Statt das an jeder Stelle einzeln zu merken, fragt
dieses Modul alle bekannten Ports auf einmal ab und liefert eine Ampel.

Geprueft wird mit einem TCP-Verbindungsversuch. Das ist absichtlich stumpf -
wer die Verbindung annimmt, laeuft; was er danach spricht, interessiert hier
nicht. Ein Dienst kann also "laeuft" melden und trotzdem streiken; die
Gegenprobe ist immer der eigentliche Aufruf.

**Zum Port des ELF-Loaders:** Die Quellen sind sich nicht einig - das README
von elfldr 0.26 nennt 9020, ps5upload und ActRemoteLink senden an 9021, und
an der Konsole des Nutzers ist 9021 der arbeitende Port (payload_versand).
Beide stehen im Katalog; welcher antwortet, sagt die Abfrage.

Das Modul bindet ``i18n`` nicht ein: Es traegt nur Schluessel, die
Oberflaeche uebersetzt sie (wie ``prosperopkg.MELDUNGEN``).

Vorlage: ``konsole/dienste.py`` aus den vorbereiteten Dateien des Nutzers
(nur Standardbibliothek). Hier angepasst: Textschluessel statt fester
Beschriftungen, der Payload-Manager (8084) dazu - ueber ihn laeuft der
zweite Sendeweg -, und die Muster der mitgelieferten ELF-Dateien.
"""
from __future__ import annotations

import os
import re
import socket
import threading
import time
from dataclasses import dataclass, field

#: Wie lange auf eine Verbindung gewartet wird. Im LAN antwortet ein
#: laufender Dienst weit darunter; ist nichts da, kommt die Ablehnung
#: sofort. Der Wert greift nur bei stillen Paketverlusten.
ZEITSCHRANKE = 0.6

#: Wie lange nach dem Senden eines Dienst-Payloads dessen Ausgabe mitgelesen
#: wird (Sekunden Stille). Ein Dienst laeuft dauerhaft und schliesst die
#: Verbindung zu elfldr nie; mit der allgemeinen Vorgabe von 30 s wartete
#: deshalb jeder Start im Fenster "Konsole & Payloads" die vollen 30 s ab,
#: die Grundausstattung (drei Payloads) ueber anderthalb Minuten (bis zum
#: 26.09.2026). Seine Startmeldung schreibt ein Dienst sofort; ob er laeuft,
#: sagt danach :func:`warten_bis_bereit`.
LESEZEIT = 3.0

#: So viel wird von einer Versionsabfrage hoechstens gelesen. Gelesen wird
#: sonst bis zum Ende der Antwort: Ein Abbruch mitten in der Uebertragung soll
#: keinen Dienst der Konsole aus dem Tritt bringen (den ftpsrv legt ein
#: abgebrochener Download lahm). Die Antwort von "/version" hat 157 Bytes.
SEITE_HOECHSTENS = 64 * 1024


@dataclass(frozen=True)
class Dienst:
    """Ein Dienst auf der Konsole - Port, Textschluessel, Startdatei."""

    schluessel: str
    port: int
    #: Muster der mitgelieferten ELF-Datei (helloworld/), "" = keine.
    payload_muster: str = ""
    #: Muster einer mitgelieferten Datei, aus der **nur die Version** der Spalte
    #: "Version" kommt - ohne dass der Eintrag daraus gestartet wird
    #: (``payload_muster`` bleibt leer). Fuer Dienste, die das Programm bewusst
    #: nicht selbst schickt: ShadowMount+ (laeuft ueblicherweise aus dem Autoload),
    #: der zweite Port des ELF-Loaders (derselbe Dienst wie 9021) und DPI v2 (ein
    #: OnionHEN-Plugin, das OnionHEN selbst startet). Seit dem 05.10.2026 -
    #: vorher stand dort immer ein Strich.
    datei_muster: str = ""
    #: Pfad der Weboberflaeche, oder "" fuer keine.
    web: str = ""
    #: Nur einer aus dieser Gruppe muss laufen (die beiden Loader-Ports).
    gruppe: str = ""
    #: Sekunden, die dieser Dienst nach dem Start zum Hochkommen braucht.
    anlaufzeit: float = 1.5
    #: Dieser Dienst begruesst von sich aus (FTP: "220 ..."). Dann wird der
    #: Gruss mitgelesen - ein offener Port allein taeuscht hier.
    begruessung: bool = False
    #: Woran der laufende Dienst seine Version verraet: ein Muster mit einer
    #: Gruppe, gesucht im Gruss (``begruessung``) oder in der Antwort auf
    #: ``version_pfad``. "" = er nennt keine.
    version_muster: str = ""
    #: HTTP-Pfad, unter dem der Dienst seine Version nennt, "" = keiner.
    version_pfad: str = ""
    #: Wie ``version_pfad``, aber als ``POST`` mit leerem JSON-Objekt - so fragt die
    #: Schnittstelle von ShadowMount+ (jede Anfrage dort ist ein POST).
    version_post: str = ""
    #: Ein **Plugin**, keine eigenstaendige ELF: Pfad auf der Konsole, unter dem es
    #: liegen muss, damit sein Wirt (``plugin_wirt``) es beim Start laedt. Solche
    #: Eintraege schickt "Ausgewaehltes starten" nie an den ELF-Loader; die Seite
    #: legt sie stattdessen per FTP dorthin (Nutzer 06.10.2026, DPI v2 fuer OnionHEN).
    plugin_pfad: str = ""
    #: Das Programm auf der Konsole, das das Plugin laedt - es muss installiert sein.
    plugin_wirt: str = ""

    @property
    def ist_plugin(self) -> bool:
        return bool(self.plugin_pfad)

    @property
    def name_schluessel(self) -> str:
        return "dienst.%s" % self.schluessel

    @property
    def zweck_schluessel(self) -> str:
        return "dienst.%s_zweck" % self.schluessel


#: Reihenfolge = Anzeigereihenfolge. Oben steht, was ohne alles andere nicht
#: geht: ohne ELF-Loader laesst sich nichts nachladen.
#:
#: Die Versionsquellen sind an der Konsole gemessen (26.09.2026): der ftpsrv
#: gruesst mit "220-Version: 1.16-ng-stable (built ...)", der Payload-Manager
#: antwortet auf "/version" mit "0.5.1" (seine eigene Weboberflaeche fragt
#: dort; die Startseite waere 725.540 Bytes, und Teilanfragen kennt er nicht).
#: ELF-Loader und Kernel-Protokoll haben keinen Weg dafuer; Webserver
#: ("Homebrew Launcher") und BFpilot nennen auf ihrer Startseite keine.
KATALOG: tuple[Dienst, ...] = (
    Dienst("elfldr9021", 9021, "elfldr*.elf", gruppe="elfldr", anlaufzeit=2.5),
    # Derselbe Dienst auf dem zweiten bekannten Port: gestartet wird er ueber die
    # Zeile 9021, hier steht nur die Version der beiliegenden Datei (seit 05.10.2026).
    Dienst("elfldr9020", 9020, "", gruppe="elfldr", datei_muster="elfldr*.elf"),
    Dienst("pldmgr", 8084, "pldmgr*.elf", web="/", anlaufzeit=2.0,
           version_muster=r"^\s*v?(\d[\w.-]*)", version_pfad="/version"),
    Dienst("ftpsrv", 2121, "ftpsrv-ps5*.elf", begruessung=True,
           version_muster=r"Version:\s*([^\s(]+)"),
    Dienst("klogsrv", 3232, "klogsrv*.elf", anlaufzeit=1.0),
    # Der PKG Manager haelt zwei weitere Ports offen: 18841 (Paketstrom) und
    # 18842 (Direct Install). Beide gehoeren zum selben Payload und kommen mit
    # ihm hoch - geprueft wird deshalb nur die Weboberflaeche auf 8844.
    Dienst("pkgmgr", 8844, "pkgmgr*.elf", web="/", anlaufzeit=2.0),
    Dienst("webfm", 8888, "web-file-mgr*.elf", web="/", anlaufzeit=2.0),
    Dienst("garlic", 8082, "garlic-savemgr*.elf", web="/", anlaufzeit=2.0),
    Dienst("bfpilot", 5905, "bfpilot*.elf", web="/"),
    Dienst("websrv", 8080, "websrv-ps5*.elf", web="/"),
    # Kein payload_muster (bewusst): ShadowMount+ laeuft ueblicherweise
    # dauerhaft aus dem Autoload, nicht auf Knopfdruck. Ein blosser TCP-Check
    # kann "aus, weil api_bind_address=127.0.0.1" nicht von "laeuft wirklich
    # nicht" unterscheiden - "Ausgewaehltes starten" haette sonst leicht eine
    # zweite Instanz riskiert. Die API/Weboberflaeche lauscht ab Werk nur auf
    # 127.0.0.1; von diesem PC aus ist sie erst erreichbar, wenn
    # api_bind_address in der config.ini auf die PS5-Adresse oder 0.0.0.0
    # zeigt (ShadowMount+-Editor in "WEITERE TOOLS").
    #
    # Version seit dem 05.10.2026 (der Nutzer: "bei ShadowMount+ steht nie die Version"):
    # Ist die Schnittstelle von diesem PC aus erreichbar, nennt ShadowMount+ sie selbst -
    # ``POST /api/v1/version`` liefert ``"shadowmount_version"`` (docs/api.md). Sonst
    # (Normalfall: nur 127.0.0.1) steht die Version der beiliegenden Datei da.
    Dienst("shadowmount", 10101, web="/", datei_muster="shadowmountplus_v*.elf",
           version_muster=r'"shadowmount_version"\s*:\s*"([^"]+)"',
           version_post="/api/v1/version"),
    # Alles-in-einem-Weboberflaeche (Dateimanager, PKG-Installer, Spielstaende,
    # Payloads, Autoloader ...) - ein einzelnes ELF, startet ueblicherweise auf
    # Knopfdruck wie webfm/pkgmgr, deshalb MIT payload_muster (anders als
    # ShadowMount+ oben).
    Dienst("prosperomgr", 7070, "ProsperoMgr*.elf", web="/", anlaufzeit=2.0),
    Dienst("upload", 9113, "ps5upload*.elf"),
    # --- Weitere Payloads mit Port (seit 02.10.2026) ---------------------------
    # Ports und Weboberflaechen stammen aus den Beschreibungen der Autoren und,
    # wo vorhanden, aus einer Zeichenkette im ELF selbst (CheatRunner 9999,
    # Game Compressor 5910, gdbsrv 2159); an der Konsole noch NICHT nachgemessen.
    # Bewusst nicht aufgenommen:
    # * shsrv (Telnet-Shell, 2323): startet je Verbindung einen Shell-Prozess
    #   (``elfldr_spawn`` in der Annahmeschleife) - der Statuscheck wuerde bei
    #   jeder Abfrage einen Prozess auf der Konsole erzeugen.
    # * MemDBG: sein TCP-Port ist 9020, hier der zweite Port des ELF-Loaders.
    # * garlic-worker: der Port ist nur ein Startparameter, kein Standardwert.
    # * nanoDNS: horcht auf 53, die Abfrage prueft aber nur TCP.
    # * OnionHEN (eigene Ladekette auf 9020), PIZZA-HEN (kein Port belegt) und
    #   ActRemoteLink (Remote Play ist aus dem Programm genommen).
    Dienst("cheatrunner", 9999, "CheatRunner_v*.elf", web="/", anlaufzeit=2.0),
    Dienst("appdumper", 8081, "ps5-app-dumper_v*.elf", web="/", anlaufzeit=2.0),
    Dienst("gamecompressor", 5910, "game-compressor_v*.elf", web="/", anlaufzeit=2.0),
    Dienst("smplusgui", 7777, "SMPlusGui_v*.elf", web="/", anlaufzeit=2.0),
    # AriaNg steckt im ELF und liegt auf demselben Port wie die RPC-Schnittstelle.
    Dienst("aria2", 6800, "aria2-v*.elf", web="/", anlaufzeit=3.0),
    # Nur die zhttp-Fassung traegt die Weboberflaeche; der HTTP-Port spiegelt
    # den FTP-Port (auf Konsolen 2120). Ohne Gruss geprueft: Die Fassung
    # entscheidet bei einer Verbindung, ob FTP oder HTTP gesprochen wird.
    Dienst("zftpd", 2120, "zftpd-ps5-zhttp-v*.elf", web="/", anlaufzeit=2.5),
    Dienst("gdbsrv", 2159, "gdbsrv-ps5_v*.elf"),
    Dienst("ps5debug", 744, "ps5debug-NG_v*.elf", anlaufzeit=2.0),
    # --- AnyPad PS5 (seit 04.10.2026) -----------------------------------------
    # Bluetooth-Controller (DualShock 4, Xbox, Switch Pro, 8BitDo ...) an der
    # PS5. Port und Weboberflaeche (koppeln, vergessen, Protokoll, beenden) aus
    # dem README des Autors (v0.5.5-beta, unveraendert in v0.6.0-beta vom
    # 06.10.2026 - das Projekt liegt seitdem auf Codeberg) und aus dem ELF
    # selbst ("deeplinkUri": "http://127.0.0.1:8095/"); an der Konsole noch
    # NICHT nachgemessen. Die
    # Seite fragt keine PIN ab. Eine zweite Instanz verhindert das Payload
    # selbst (Sperrdatei); gestartet wird hier ohnehin nur, wenn der Port zu
    # ist. Anlaufzeit geschaetzt (Bluetooth kommt mit hoch), nicht gemessen.
    Dienst("anypad", 8095, "AnyPad-PS5-*.elf", web="/", anlaufzeit=3.0),
    # --- DPI v2 (seit 05.10.2026) ----------------------------------------------
    # Paketinstaller im Browser, ein Plugin fuer OnionHEN. Auftrag des Nutzers: Was von
    # den ELFs in helloworld/ eine Weboberflaeche hat, steht in dieser Tabelle. Port
    # 12800 (WebUI) laut README des Autors (OnionBuddies/onionHEN-dpiv2-plugin), dort
    # einstellbar; der Uebertragungsport 9090 gehoert zum selben Plugin. An der Konsole
    # noch NICHT nachgemessen. Kein payload_muster (bewusst): Das Plugin liegt unter
    # /data/OnionHEN/plugins/DPIV00001.elf und wird von OnionHEN gestartet - sein
    # main() verbindet sich beim Start mit dem OnionHEN-Daemon (Quelltext main.c) -,
    # "Ausgewaehltes starten" soll es nicht ueber den ELF-Loader schicken. Aus der
    # Datei kommt nur die Version der Spalte.
    Dienst("dpiv2", 12800, web="/", datei_muster="dpiv2-*.elf",
           plugin_pfad="/data/OnionHEN/plugins/DPIV00001.elf", plugin_wirt="OnionHEN"),
    # --- WK Autoloader (seit 07.10.2026 mit Zeile) -----------------------------
    # Jailbreak-Host von X-F1REBALL-X (umtx2 bis 5.50, Relapse 7.00-13.60), bisher ohne Zeile
    # mitgeliefert; seit v1.0.16 mit eigener Seite. Port 1022 laut README des Autors ("Send the WK
    # Autoloader ELF; wait for install/cache. Open http://PS5_IP:1022") und aus dem ELF selbst
    # ("deeplinkUri": "http://127.0.0.1:1022/app/index.html" - die Medien-App der Konsole). Gestartet
    # wird er wie beschrieben ueber den ELF-Loader (payload_muster); danach waehlt man auf der Seite
    # Payload Manager (8084) oder Elf Launcher (1000). An der Konsole noch NICHT nachgemessen;
    # Anlaufzeit geschaetzt (er richtet beim ersten Start seinen Zwischenspeicher ein).
    Dienst("wkautoloader", 1022, "WK-AutoLoader_v*.elf", web="/", anlaufzeit=4.0),
    # --- PS5 Cooling & System Center - Pro (seit 05.10.2026) -------------------
    # Die eigene App des Projektinhabers (helloworld/PS5_Cooling_System_Center_v1.48.0.elf):
    # Luefter- und Temperatursteuerung, Systeminfo, Spielebibliothek, Pakete installieren ... im
    # Browser. Port und Weboberflaeche aus dem ELF selbst: ``"deeplinkUri": "http://127.0.0.1:8086"``,
    # der Port ist die Einstellung ``http_port`` (Vorgabe 8086), ``bind_address`` steht ab Werk auf
    # 0.0.0.0 (im LAN erreichbar). Die Weboberflaeche lehnt Anfragen ab, die nicht ueber die IP-Adresse
    # der Konsole kommen (``forbidden_origin``) - hier geht alles ueber die IP. Die laufende Version
    # nennt ``GET /api/v1/system`` als ``"app_version"``. Mit payload_muster: startet auf Knopfdruck
    # (Knopf 5 der Ansicht KONSOLE) und ueber "Ausgewaehltes starten". Ist ein anderer Port eingestellt,
    # gilt die Zeile nicht - Anlaufzeit geschaetzt (Sensoren und Kachel-Dienst kommen mit hoch). An der
    # Konsole noch NICHT nachgemessen.
    Dienst("coolsyscent", 8086, "PS5_Cooling_System_Center_v*.elf", web="/", anlaufzeit=3.0,
           version_muster=r'"app_version"\s*:\s*"([^"]+)"', version_pfad="/api/v1/system"),
)

#: Die Grundausstattung, in dieser Reihenfolge: Ohne Loader geht nichts,
#: danach die beiden Dienste, die fast jeder Weg braucht.
GRUNDAUSSTATTUNG: tuple[str, ...] = ("elfldr9021", "ftpsrv", "klogsrv")

_NACH_SCHLUESSEL = {d.schluessel: d for d in KATALOG}


@dataclass
class Stand:
    dienst: Dienst
    laeuft: bool = False
    #: Port offen, aber kein Gruss - der Dienst haengt. Am 17.08.2026 an der
    #: Konsole erlebt: ftpsrv nahm Verbindungen weiter an und antwortete
    #: nicht mehr; ein neu geladenes Payload half nicht, nur ein Neustart der
    #: Konsole. Ein reiner Portscan meldet hier faelschlich "laeuft".
    stumm: bool = False
    #: Die Version, die der laufende Dienst selbst nennt (siehe
    #: :func:`laufende_version`), "" = unbekannt.
    version: str = ""


@dataclass
class Uebersicht:
    adresse: str
    staende: list[Stand] = field(default_factory=list)

    def __iter__(self):
        return iter(self.staende)

    def __len__(self) -> int:
        return len(self.staende)

    def laeuft(self, schluessel: str) -> bool:
        return any(s.laeuft for s in self.staende
                   if s.dienst.schluessel == schluessel)

    def gruppe_laeuft(self, gruppe: str) -> bool:
        """Laeuft mindestens einer aus dieser Gruppe?"""
        return any(s.laeuft for s in self.staende if s.dienst.gruppe == gruppe)

    @property
    def loader_port(self) -> "int | None":
        """Der Port, auf dem der ELF-Loader tatsaechlich antwortet."""
        for stand in self.staende:
            if stand.dienst.gruppe == "elfldr" and stand.laeuft:
                return stand.dienst.port
        return None

    @property
    def anzahl_laufend(self) -> int:
        return sum(1 for s in self.staende if s.laeuft)

    @property
    def bereit(self) -> bool:
        """Ist die Konsole ansprechbar?

        Das entscheidet der ELF-Loader oder der Payload-Manager: Ueber einen
        von beiden laesst sich alles Weitere nachladen (siehe
        ``payload_versand``).
        """
        return self.gruppe_laeuft("elfldr") or self.laeuft("pldmgr")


def dienst(schluessel: str) -> "Dienst | None":
    return _NACH_SCHLUESSEL.get(schluessel)


def port_offen(adresse: str, port: int, zeit: float = ZEITSCHRANKE) -> bool:
    """Nimmt an diesem Port jemand Verbindungen an?"""
    try:
        with socket.create_connection((adresse, int(port)), timeout=zeit):
            return True
    except OSError:
        return False


def dienst_pruefen(adresse: str, eintrag: Dienst,
                   zeit: float = ZEITSCHRANKE) -> "tuple[bool, bool]":
    """Prueft einen Dienst.

    Returns:
        ``(laeuft, stumm)``. ``stumm`` ist True, wenn der Port zwar offen
        ist, ein erwarteter Gruss aber ausbleibt - dann haengt der Dienst
        (siehe :class:`Stand`), und ``laeuft`` ist False.
    """
    try:
        with socket.create_connection((adresse, int(eintrag.port)),
                                      timeout=zeit) as verbindung:
            if not eintrag.begruessung:
                return (True, False)
            verbindung.settimeout(zeit)
            try:
                gruss = verbindung.recv(64)
            except OSError:
                gruss = b""
            if gruss:
                return (True, False)
            return (False, True)
    except OSError:
        return (False, False)


def version_aus_dateiname(name: str) -> str:
    """Die Version im Namen einer mitgelieferten ELF-Datei, oder "".

    ``elfldr-ps5_v0.26.elf`` -> ``0.26``, ``ftpsrv-ps5_v1.16-ng-stable.elf`` ->
    ``1.16-ng-stable``, ``ps5upload-5.33.2.elf`` -> ``5.33.2``,
    ``shadowmountplus_v1.7beta4.elf`` -> ``1.7beta4`` (Stufe ohne Trenner direkt
    hinter der Zahl, seit 05.10.2026). Eine Zahl ohne Punkt
    (``bdj_unpatch_1340.elf``) gilt nicht als Version.
    """
    stamm = os.path.basename(str(name or ""))
    if stamm.lower().endswith(".elf"):
        stamm = stamm[:-4]
    treffer = re.search(
        r"[_-]v?(\d+(?:\.\d+)+(?:[A-Za-z][A-Za-z0-9]*)?(?:[-_][A-Za-z0-9]+)*)$", stamm)
    return treffer.group(1) if treffer else ""


def laufende_version(adresse: str, eintrag: Dienst, zeit: float = ZEITSCHRANKE) -> str:
    """Die Version, die der laufende Dienst selbst nennt - oder "".

    Nur Dienste mit ``version_muster`` verraten sie (siehe :data:`KATALOG`).
    Ein Fehler oder ein fehlender Treffer ergibt "" - die Version ist eine
    Zugabe, sie entscheidet nie ueber "laeuft".
    """
    if not eintrag.version_muster or not str(adresse or "").strip():
        return ""
    muster = re.compile(eintrag.version_muster)
    try:
        if eintrag.begruessung:
            text = _gruss_lesen(adresse, eintrag.port, muster, zeit)
        elif eintrag.version_pfad:
            text = _seite_lesen(adresse, eintrag.port, eintrag.version_pfad, zeit)
        elif eintrag.version_post:
            text = _seite_lesen(adresse, eintrag.port, eintrag.version_post, zeit,
                                post=b"{}")
        else:
            return ""
    except OSError:
        return ""
    treffer = muster.search(text)
    return treffer.group(1).strip() if treffer else ""


def _gruss_lesen(adresse: str, port: int, muster: "re.Pattern[str]",
                 zeit: float) -> str:
    """Liest den Gruss eines Dienstes, bis die Version darin steht.

    Der ftpsrv gruesst mehrzeilig ("220-..." bis "220 Service is ready"), und
    die Zeilen koennen in mehreren Stuecken kommen. Schluss ist beim Treffer,
    bei der letzten Zeile des Grusses (drei Ziffern und ein Leerzeichen) oder
    nach 4 KB.
    """
    gelesen = b""
    with socket.create_connection((adresse, int(port)), timeout=zeit) as verbindung:
        verbindung.settimeout(zeit)
        while len(gelesen) < 4096:
            try:
                stueck = verbindung.recv(1024)
            except OSError:
                break
            if not stueck:
                break
            gelesen += stueck
            text = gelesen.decode("utf-8", "replace")
            if muster.search(text) or re.search(r"(?:^|\n)\d{3} ", text):
                break
    return gelesen.decode("utf-8", "replace")


def _seite_lesen(adresse: str, port: int, pfad: str, zeit: float,
                 post: "bytes | None" = None) -> str:
    """Der Rumpf einer HTTP-Antwort - gelesen, bis die Konsole schliesst.

    HTTP/1.0 mit ``Connection: close``: Das Ende der Verbindung ist das Ende
    der Antwort. Abgebrochen wird nur bei :data:`SEITE_HOECHSTENS` oder wenn
    die Konsole mitten in der Antwort verstummt. Antwortet sie nicht mit 200
    (etwa 404 bei einer aelteren Fassung ohne diesen Pfad), ergibt das "".

    ``post``: ein JSON-Koerper - dann geht die Anfrage als ``POST`` mit
    ``Content-Type: application/json`` und ``Content-Length`` hinaus (so
    verlangt es die Schnittstelle von ShadowMount+: jede Anfrage dort ist ein
    POST mit einem Objekt, hoechstens 4096 Bytes).
    """
    if post is None:
        anfrage = ("GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n"
                   % (pfad or "/", adresse)).encode("ascii")
    else:
        kopf = ("POST %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n"
                "Content-Type: application/json\r\nContent-Length: %d\r\n\r\n"
                % (pfad or "/", adresse, len(post))).encode("ascii")
        anfrage = kopf + post
    teile: list[bytes] = []
    menge = 0
    with socket.create_connection((adresse, int(port)), timeout=zeit) as verbindung:
        verbindung.settimeout(max(zeit, 2.0))
        verbindung.sendall(anfrage)
        while menge < SEITE_HOECHSTENS:
            try:
                stueck = verbindung.recv(65536)
            except OSError:
                break
            if not stueck:
                break
            teile.append(stueck)
            menge += len(stueck)
    kopf, _trenner, rumpf = b"".join(teile).partition(b"\r\n\r\n")
    status = kopf.split(b"\r\n", 1)[0].split()
    if len(status) < 2 or status[1] != b"200":
        return ""
    return rumpf.decode("utf-8", "replace")


def warten_bis_bereit(adresse: str, eintrag: Dienst, grenze: "float | None" = None,
                      takt: float = 0.3, zeit: float = ZEITSCHRANKE) -> bool:
    """Wartet, bis der Dienst antwortet - hoechstens ``grenze`` Sekunden.

    Ersetzt seit dem 26.09.2026 das feste Abwarten der ``anlaufzeit``: Wer
    schon nach einer halben Sekunde antwortet, haelt nicht mehr die ganze
    Anlaufzeit auf; wer laenger braucht, bekommt bis zum Vierfachen davon
    (mindestens 6 s). Geprueft wird wie in der Ampel, mit Gruss wo einer
    erwartet wird (:func:`dienst_pruefen`).
    """
    frist = grenze if grenze is not None else max(6.0, 4.0 * eintrag.anlaufzeit)
    ende = time.monotonic() + frist
    while True:
        laeuft, _stumm = dienst_pruefen(adresse, eintrag, zeit)
        if laeuft:
            return True
        if time.monotonic() >= ende:
            return False
        time.sleep(takt)


def pruefen(adresse: str, zeit: float = ZEITSCHRANKE,
            dienste: "tuple[Dienst, ...]" = KATALOG) -> Uebersicht:
    """Fragt alle Dienste gleichzeitig ab.

    Nacheinander gefragt kostete das bei zehn Diensten und einer stillen
    Konsole das Zehnfache der Zeitschranke - nebenlaeufig kostet es einmal
    die Zeitschranke.

    Laufende Dienste, die ihre Version nennen, werden danach noch nach ihr
    gefragt (:func:`laufende_version`). Der Zustand steht vorher fest: Kommt
    die Version zu spaet, fehlt nur sie.
    """
    ziel = (adresse or "").strip()
    if not ziel:
        return Uebersicht(adresse="", staende=[Stand(d) for d in dienste])

    ergebnisse: "dict[str, tuple[bool, bool, str]]" = {}
    sperre = threading.Lock()

    def fragen(eintrag: Dienst) -> None:
        laeuft, stumm = dienst_pruefen(ziel, eintrag, zeit)
        with sperre:
            ergebnisse[eintrag.schluessel] = (laeuft, stumm, "")
        if laeuft and eintrag.version_muster:
            version = laufende_version(ziel, eintrag, zeit)
            with sperre:
                ergebnisse[eintrag.schluessel] = (laeuft, stumm, version)

    faeden = [threading.Thread(target=fragen, args=(d,), daemon=True)
              for d in dienste]
    for faden in faeden:
        faden.start()
    # Etwas Luft ueber der Zeitschranke, damit ein knapp verspaeteter Faden
    # noch zaehlt statt als "aus" zu gelten.
    for faden in faeden:
        faden.join(timeout=zeit + 1.0)

    with sperre:
        staende = [Stand(d, *ergebnisse.get(d.schluessel, (False, False, "")))
                   for d in dienste]
    return Uebersicht(adresse=ziel, staende=staende)


def web_adresse(eintrag: Dienst, adresse: str) -> str:
    """Die Adresse der Weboberflaeche - leer, wenn der Dienst keine hat."""
    if not eintrag.web or not str(adresse or "").strip():
        return ""
    return "http://%s:%d%s" % (str(adresse).strip(), eintrag.port, eintrag.web)
