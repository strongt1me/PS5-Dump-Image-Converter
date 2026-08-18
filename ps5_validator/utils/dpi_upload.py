"""Hilfsfunktionen fuer den generischen etaHEN "Direct Package Installer V2" (DPI)-Upload.

DPI V2 ist ein regulaerer etaHEN-Dienst (HTTP-Server, Standardport 12800), der beliebige
`.pkg`-Dateien per multipart/form-data-Upload entgegennimmt und auf der Konsole installiert.
Dieses Modul baut NUR die reinen Multipart-Rahmenbytes (Header/Footer/Content-Type) - die
eigentliche Netzwerk-Uebertragung (http.client-Streaming mit Fortschrittsanzeige) liegt in
der GUI-Methode ``_show_dpi_installer`` der Hauptanwendung.

WICHTIG - Abgrenzung: Dies ist AUSSCHLIESSLICH der generische Upload-Transport, den viele
Homebrew-Werkzeuge fuer bereits laufende etaHEN-Diensste nutzen (vergleichbar mit den
FTP-basierten Werkzeugen ShadowMount+/PS5-Game-Manager dieses Projekts). Es ist NICHT die
Y2JB-spezifische Exploit-Logik (YouTube-Schwachstelle, Update-Blockierung) - diese wurde
bewusst nicht implementiert (siehe scene-comparison-backlog.md).
"""
from __future__ import annotations

DEFAULT_DPI_PORT = 12800
DEFAULT_BOUNDARY = "PS5IMAGECONVERTERBOUNDARY"


def content_type_header(boundary: str = DEFAULT_BOUNDARY) -> str:
    """Liefert den ``Content-Type``-Headerwert fuer den Multipart-Upload."""
    return f"multipart/form-data; boundary={boundary}"


def build_multipart_frame(filename: str, file_size: int, boundary: str = DEFAULT_BOUNDARY) -> tuple[bytes, bytes, int]:
    """Baut Header-/Footer-Bytes und Gesamtgroesse fuer einen multipart/form-data-Upload.

    Args:
        filename: Anzeigename der Datei im Formularfeld (nur Basisname, kein Pfad).
        file_size: Groesse der eigentlichen Dateinutzlast in Bytes.
        boundary: Multipart-Boundary-String (ohne führende/folgende Bindestriche).

    Returns:
        Tupel (header_bytes, footer_bytes, total_size), wobei ``total_size`` die Summe aus
        Header, Dateinutzlast und Footer ist (fuer den ``Content-Length``-Header).
    """
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    total_size = len(header) + file_size + len(footer)
    return header, footer, total_size
