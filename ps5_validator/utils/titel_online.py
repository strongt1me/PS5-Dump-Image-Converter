"""Titel und Content-ID zu einer Title-ID von der Patch-Seite lesen.

Reine Auswertung eines bereits geladenen HTML-Dokuments - ohne Netzzugriff,
damit sie fuer sich pruefbar bleibt. Das Laden selbst liegt in der Oberflaeche,
wo auch die Rueckfrage an den Nutzer sitzt.

Wozu: Fehlt ``sce_sys/param.json`` oder ist sie beschaedigt, legt das Programm
eine Ersatzdatei an. Die Title-ID kommt dabei aus ``sce_sys/nptitle.dat``, Titel
und Content-ID stehen aber in keiner lokalen Datei des Dumps - weder in der
``eboot.bin`` (33 MB vollstaendig durchsucht) noch in ``npbind.dat``. Bleibt der
Nachschlag auf der Patch-Seite, die dieselbe Adresse nutzt wie die Update-Liste
im Spiel-Info-Fenster.

Am 16.08.2026 an acht echten Backups nachgemessen: Content-ID **8/8 exakt**,
Titel **7/8**. Die eine Abweichung ist eine Umbenennung zwischen Regionen
(``PPSA04319``: lokal "Instant Sports Plus", online "Instant Sports Paradise") -
die Content-ID stimmte auch dort.

Seit der ersten Messung im August stellt die Seite dem Titel die Title-ID voran
(``PPSA19015: Arcade Game Zone``); dieses Praefix wird hier abgetrennt.
"""
from __future__ import annotations

import html as _html
import re

#: Praefixe der Title-IDs je Plattform und die zugehoerige Seite.
SEITE_PS5 = "https://prosperopatches.com"
SEITE_PS4 = "https://orbispatches.com"

PRAEFIXE_PS5 = ("PPSA", "PPSS", "PPUS", "PPJP", "PCJS", "PCAS", "ECAS")
PRAEFIXE_PS4 = ("CUSA", "PUSA")

_TITLE_ID_RE = re.compile(r"^[A-Z]{4}\d{5}$")

#: UP8016-PPSA19015_00-0489895718491618
_CONTENT_ID_RE = re.compile(
    r"[A-Z]{2}\d{4}-(?:PPSA|PPSS|PPUS|PPJP|PCJS|PCAS|ECAS|CUSA|PUSA)\d{5}_\d{2}-[A-Z0-9]{16}")

_TITEL_MUSTER = (
    r"<meta[^>]+property=['\"]og:title['\"][^>]+content=['\"]([^'\"]+)['\"]",
    r"<meta[^>]+name=['\"]twitter:title['\"][^>]+content=['\"]([^'\"]+)['\"]",
    r"<h1[^>]*>\s*([^<]+?)\s*</h1>",
)

#: Was die Seite an den Titel haengt und was hier nicht hineingehoert.
_ZU_ENTFERNEN = (
    r"\s*[-–|]\s*Prospero\s*Patches\s*$",
    r"\s*[-–|]\s*Orbis\s*Patches\s*$",
)


def ist_title_id(wert: str) -> bool:
    """True fuer eine Zeichenfolge der Form ``PPSA19015``."""
    return bool(_TITLE_ID_RE.match(str(wert or "").strip().upper()))


def seiten_url(title_id: str) -> str:
    """Adresse der Patch-Seite; leer, wenn die Title-ID nicht zuzuordnen ist."""
    tid = str(title_id or "").strip().upper()
    if not ist_title_id(tid):
        return ""
    if tid.startswith(PRAEFIXE_PS5):
        return f"{SEITE_PS5}/{tid}"
    if tid.startswith(PRAEFIXE_PS4):
        return f"{SEITE_PS4}/{tid}"
    return ""


def titel_aus_html(doc: str, title_id: str = "") -> str:
    """Zieht den Spieltitel aus dem Seitenkopf.

    Die Seite schreibt inzwischen ``PPSA19015: Arcade Game Zone``; die Title-ID
    davor wird abgetrennt, ebenso ein angehaengter Seitenname.
    """
    tid = str(title_id or "").strip().upper()
    for muster in _TITEL_MUSTER:
        treffer = re.search(muster, str(doc or ""), flags=re.IGNORECASE)
        if not treffer:
            continue
        titel = _html.unescape(treffer.group(1)).strip()
        if tid:
            titel = re.sub(r"^\s*" + re.escape(tid) + r"\s*[:–-]\s*", "",
                           titel, flags=re.IGNORECASE).strip()
        for weg in _ZU_ENTFERNEN:
            titel = re.sub(weg, "", titel, flags=re.IGNORECASE).strip()
        if titel:
            return titel
    return ""


def content_id_aus_html(doc: str, title_id: str = "") -> str:
    """Zieht die Content-ID aus dem Seitentext.

    Eine Seite kann mehrere Content-IDs nennen (andere Regionen oder Ausgaben).
    Bevorzugt wird darum die, die die gesuchte Title-ID enthaelt; nur wenn keine
    passt, wird die erste genommen.
    """
    tid = str(title_id or "").strip().upper()
    treffer = _CONTENT_ID_RE.findall(str(doc or ""))
    if not treffer:
        return ""
    if tid:
        for kandidat in treffer:
            if tid in kandidat:
                return kandidat
    return treffer[0]


def metadaten_aus_html(doc: str, title_id: str = "") -> dict[str, str]:
    """Beides auf einmal.

    Returns:
        Dict mit ``title`` und/oder ``content_id``; fehlende Werte fehlen ganz.
    """
    ergebnis: dict[str, str] = {}
    titel = titel_aus_html(doc, title_id)
    if titel:
        ergebnis["title"] = titel
    content_id = content_id_aus_html(doc, title_id)
    if content_id:
        ergebnis["content_id"] = content_id
    return ergebnis
