"""GP5-Projektdatei (*.gp5): Lesen/Schreiben des PS5-"Prospero"-Projektformats.

GP5 ist das XML-Projektdeskriptor-Format, mit dem externe PKG-Builder (z.B. GP5Creator/
GP5PKGBuilder in PS-Multi-Tools, oder eigene orbis-pub-cmd-artige Werkzeuge) beschrieben
bekommen, welcher Quellordner mit welcher Content-ID/Passcode/Volume-Typ zu einem PS5-Paket
verarbeitet werden soll. Dieses Modul erzeugt/liest ausschliesslich die Projektdatei selbst;
es baut kein PKG und enthaelt keine Kryptografie.

Schema (Element-/Attributnamen) durch Gegenlesen des quelloffenen LibProsperoPKG-Modells
(GPL-3.0-or-later, https://github.com/SvenGDK/LibProsperoPKG) ermittelt; eigenstaendige
Python-Neuentwicklung auf Basis der (nicht schutzfaehigen) Format-Fakten, kein Uebersetzen
des dortigen C#-Quellcodes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from xml.dom import minidom
from xml.etree import ElementTree as ET

DEFAULT_PASSCODE = "00000000000000000000000000000000"


class Gp5VolumeType(str, Enum):
    """Die von einem GP5-Projekt beschriebenen PS5-Paket-Volumentypen."""

    APP = "prospero_app"
    PATCH = "prospero_patch"
    AC = "prospero_ac"
    AC_NODATA = "prospero_ac_nodata"


@dataclass
class Gp5Chunk:
    id: int
    label: str = ""


@dataclass
class Gp5Scenario:
    id: int
    label: str = ""
    type: str = "playmode"
    initial_chunk_count: int = 1
    chunks: str = "0"  # Kommagetrennte Chunk-IDs als Elementtext, z.B. "0" oder "0,1,2"


@dataclass
class Gp5ChunkInfo:
    chunk_count: int = 1
    scenario_count: int = 1
    chunks: list[Gp5Chunk] = field(default_factory=lambda: [Gp5Chunk(id=0, label="Chunk #0")])
    scenarios_default_id: int = 0
    scenarios: list[Gp5Scenario] = field(
        default_factory=lambda: [Gp5Scenario(id=0, label="Scenario #0")]
    )


@dataclass
class Gp5Package:
    passcode: str = DEFAULT_PASSCODE
    content_id: str = ""
    storage_type: str = ""
    app_path: str = ""


@dataclass
class Gp5Volume:
    volume_type: Gp5VolumeType = Gp5VolumeType.APP
    volume_id: str = ""
    volume_ts: str = ""
    package: Gp5Package = field(default_factory=Gp5Package)
    chunk_info: Gp5ChunkInfo | None = None


@dataclass
class Gp5File:
    src_path: str
    dst_path: str


@dataclass
class Gp5Dir:
    src_path: str
    dst_path: str


@dataclass
class Gp5RootDir:
    src_path: str = ""
    dir_exclude: str = ""
    file_exclude: str = ""


@dataclass
class Gp5Project:
    """In-Memory-Modell eines *.gp5-Projekts.

    Zwei gleichwertige Layouts:
      - Normal: ein einzelnes rekursiv durchlaufenes `rootdir` (+ optionales global_exclude).
      - Flat: eine explizite `files`-/`folders`-Liste (Quell- auf Zielpfade), kein rootdir.
    """

    fmt: str = "gp5"
    version: int = 1000
    volume: Gp5Volume = field(default_factory=Gp5Volume)
    global_exclude: str = ""
    rootdir: Gp5RootDir = field(default_factory=Gp5RootDir)
    files: list[Gp5File] = field(default_factory=list)
    folders: list[Gp5Dir] = field(default_factory=list)

    @property
    def is_flat_layout(self) -> bool:
        return bool(self.files or self.folders)


def create_project(
    volume_type: Gp5VolumeType,
    src_path: str,
    passcode: str = DEFAULT_PASSCODE,
    content_id: str = "",
) -> Gp5Project:
    """Erstellt ein neues GP5-Projekt (Normal-Layout) mit sinnvollen Vorgaben.

    PlayGo-Chunk-/Szenario-Informationen werden nur für App- und Patch-Pakete angelegt
    (Additional Content trägt keine PlayGo-Daten), analog zum Referenzverhalten.
    """
    volume = Gp5Volume(
        volume_type=volume_type,
        package=Gp5Package(passcode=passcode, content_id=content_id),
    )
    if volume_type in (Gp5VolumeType.APP, Gp5VolumeType.PATCH):
        volume.chunk_info = Gp5ChunkInfo()
    return Gp5Project(volume=volume, rootdir=Gp5RootDir(src_path=src_path))


def _add_text_element(parent: ET.Element, tag: str, text: str) -> None:
    if not text:
        return
    el = ET.SubElement(parent, tag)
    el.text = text


def to_xml_element(project: Gp5Project) -> ET.Element:
    """Baut den `<psproject>`-Wurzelknoten für das gegebene Projekt auf."""
    root = ET.Element("psproject", {"fmt": project.fmt, "version": str(project.version)})

    volume_el = ET.SubElement(root, "volume")
    _add_text_element(volume_el, "volume_type", project.volume.volume_type.value)
    _add_text_element(volume_el, "volume_id", project.volume.volume_id)
    _add_text_element(volume_el, "volume_ts", project.volume.volume_ts)

    pkg = project.volume.package
    pkg_attrs: dict[str, str] = {"passcode": pkg.passcode}
    if pkg.content_id:
        pkg_attrs["content_id"] = pkg.content_id
    if pkg.storage_type:
        pkg_attrs["storage_type"] = pkg.storage_type
    if pkg.app_path:
        pkg_attrs["app_path"] = pkg.app_path
    ET.SubElement(volume_el, "package", pkg_attrs)

    if project.volume.chunk_info is not None:
        ci = project.volume.chunk_info
        ci_el = ET.SubElement(volume_el, "chunk_info", {
            "chunk_count": str(ci.chunk_count),
            "scenario_count": str(ci.scenario_count),
        })
        chunks_el = ET.SubElement(ci_el, "chunks")
        for chunk in ci.chunks:
            ET.SubElement(chunks_el, "chunk", {"id": str(chunk.id), "label": chunk.label})
        scenarios_el = ET.SubElement(ci_el, "scenarios", {"default_id": str(ci.scenarios_default_id)})
        for sc in ci.scenarios:
            sc_el = ET.SubElement(scenarios_el, "scenario", {
                "id": str(sc.id),
                "type": sc.type,
                "initial_chunk_count": str(sc.initial_chunk_count),
                "label": sc.label,
            })
            sc_el.text = sc.chunks

    if project.is_flat_layout:
        if project.files:
            files_el = ET.SubElement(root, "files")
            for f in project.files:
                ET.SubElement(files_el, "file", {"dst_path": f.dst_path, "src_path": f.src_path})
        if project.folders:
            folders_el = ET.SubElement(root, "folders")
            for d in project.folders:
                ET.SubElement(folders_el, "dir", {"dst_path": d.dst_path, "src_path": d.src_path})
    else:
        _add_text_element(root, "global_exclude", project.global_exclude)
        rootdir_attrs: dict[str, str] = {}
        if project.rootdir.dir_exclude:
            rootdir_attrs["dir_exclude"] = project.rootdir.dir_exclude
        if project.rootdir.file_exclude:
            rootdir_attrs["file_exclude"] = project.rootdir.file_exclude
        if project.rootdir.src_path:
            rootdir_attrs["src_path"] = project.rootdir.src_path
        ET.SubElement(root, "rootdir", rootdir_attrs)

    return root


def write_to(project: Gp5Project, path: str) -> None:
    """Schreibt das Projekt als eingerücktes, UTF-8-kodiertes *.gp5-XML ohne BOM."""
    root = to_xml_element(project)
    rough = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding=None)
    # minidom fügt eine eigene XML-Deklaration ein und oft eine zusätzliche Leerzeile
    # nach den Deklarationen; auf ein sauberes, einzeiliges Deklarationsformat normalisieren.
    lines = [ln for ln in pretty.splitlines() if ln.strip()]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def read_from(path: str) -> Gp5Project:
    """Liest ein *.gp5-Projekt von der Festplatte."""
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "psproject":
        raise ValueError(f"Keine gültige GP5-Projektdatei (Wurzelelement ist <{root.tag}>): {path}")

    project = Gp5Project(
        fmt=root.get("fmt", "gp5"),
        version=int(root.get("version", "1000")),
    )

    volume_el = root.find("volume")
    if volume_el is not None:
        volume_type_text = _find_text(volume_el, "volume_type", Gp5VolumeType.APP.value)
        try:
            volume_type = Gp5VolumeType(volume_type_text)
        except ValueError:
            volume_type = Gp5VolumeType.APP
        pkg_el = volume_el.find("package")
        package = Gp5Package(
            passcode=(pkg_el.get("passcode", DEFAULT_PASSCODE) if pkg_el is not None else DEFAULT_PASSCODE),
            content_id=(pkg_el.get("content_id", "") if pkg_el is not None else ""),
            storage_type=(pkg_el.get("storage_type", "") if pkg_el is not None else ""),
            app_path=(pkg_el.get("app_path", "") if pkg_el is not None else ""),
        )
        project.volume = Gp5Volume(
            volume_type=volume_type,
            volume_id=_find_text(volume_el, "volume_id", ""),
            volume_ts=_find_text(volume_el, "volume_ts", ""),
            package=package,
        )

        ci_el = volume_el.find("chunk_info")
        if ci_el is not None:
            chunks = [
                Gp5Chunk(id=int(c.get("id", "0")), label=c.get("label", ""))
                for c in ci_el.findall("chunks/chunk")
            ]
            scenarios_el = ci_el.find("scenarios")
            scenarios: list[Gp5Scenario] = []
            default_id = 0
            if scenarios_el is not None:
                default_id = int(scenarios_el.get("default_id", "0"))
                for sc in scenarios_el.findall("scenario"):
                    scenarios.append(Gp5Scenario(
                        id=int(sc.get("id", "0")),
                        label=sc.get("label", ""),
                        type=sc.get("type", "playmode"),
                        initial_chunk_count=int(sc.get("initial_chunk_count", "1")),
                        chunks=(sc.text or "0").strip(),
                    ))
            project.volume.chunk_info = Gp5ChunkInfo(
                chunk_count=int(ci_el.get("chunk_count", str(len(chunks) or 1))),
                scenario_count=int(ci_el.get("scenario_count", str(len(scenarios) or 1))),
                chunks=chunks or [Gp5Chunk(id=0, label="Chunk #0")],
                scenarios_default_id=default_id,
                scenarios=scenarios or [Gp5Scenario(id=0, label="Scenario #0")],
            )

    project.global_exclude = _find_text(root, "global_exclude", "")

    rootdir_el = root.find("rootdir")
    if rootdir_el is not None:
        project.rootdir = Gp5RootDir(
            src_path=rootdir_el.get("src_path", ""),
            dir_exclude=rootdir_el.get("dir_exclude", ""),
            file_exclude=rootdir_el.get("file_exclude", ""),
        )

    files_el = root.find("files")
    if files_el is not None:
        project.files = [
            Gp5File(src_path=f.get("src_path", ""), dst_path=f.get("dst_path", ""))
            for f in files_el.findall("file")
        ]

    folders_el = root.find("folders")
    if folders_el is not None:
        project.folders = [
            Gp5Dir(src_path=d.get("src_path", ""), dst_path=d.get("dst_path", ""))
            for d in folders_el.findall("dir")
        ]

    return project


def _find_text(parent: ET.Element, tag: str, default: str) -> str:
    el = parent.find(tag)
    if el is None or el.text is None:
        return default
    return el.text.strip()
