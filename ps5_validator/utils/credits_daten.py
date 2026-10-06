# -*- coding: utf-8 -*-
"""Wer im Fenster "Credits & Community" steht - mit Bild, Werken, Links und Dank.

Auftrag des Nutzers vom 06.10.2026: den Entwicklern der Werkzeuge und Arbeiten, die das Programm nutzt, mit
GitHub-Bild, Namen und anklickbaren Links danken - und vielen bekannten Entwicklern der Community dazu. Jede
Zuordnung ist gegen GitHub geprueft (Konto, Repo, bei Bedarf der Commit-Verlauf); was sich nicht belegen liess,
steht hier nicht (siehe ``project_credits_fenster`` im Memory des Projekts).

Die Profilbilder liegen im Ordner :data:`BILDORDNER` (einmal geladen, mitgeliefert; Herkunft in
``herkunft.json`` dort). Das Programm laedt zur Laufzeit nichts aus dem Netz.

Dieses Modul kennt keine Oberflaeche; die Texte stehen zweisprachig direkt hier, weil sie zu den Eintraegen
gehoeren (``i18n`` traegt nur die Ueberschriften des Fensters).
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Der mitgelieferte Ordner mit den Profilbildern (``<login>.png``, 160 x 160).
BILDORDNER = "credits"

#: Gruppen in der Reihenfolge des Fensters.
PROJEKT = "projekt"
WERKZEUGE = "werkzeuge"
COMMUNITY = "community"
GRUPPEN = (PROJEKT, WERKZEUGE, COMMUNITY)


@dataclass(frozen=True)
class Entwickler:
    """Ein Eintrag im Fenster."""

    #: GitHub-Konto (auch Name der Bilddatei); leer, wenn es kein Konto (mehr) gibt.
    login: str
    #: Angezeigter Name.
    name: str
    gruppe: str
    #: Werke als (Titel, Adresse) - die Adresse oeffnet sich im Browser.
    werke: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    #: Dank, ``{"de": ..., "en": ...}`` - gezeigt, wenn die Karte Platz dafuer hat.
    dank: dict = field(default_factory=dict)

    @property
    def profil(self) -> str:
        return "https://github.com/%s" % self.login if self.login else ""

    @property
    def bild(self) -> str:
        """Dateiname des Profilbilds im :data:`BILDORDNER`, leer ohne Konto."""
        return "%s.png" % self.login.lower() if self.login else ""

    def dank_text(self, sprache: str) -> str:
        return self.dank.get("de" if sprache == "de" else "en", "")


def _gh(pfad: str) -> str:
    return "https://github.com/" + pfad


ENTWICKLER: tuple[Entwickler, ...] = (
    # --- Das Programm ---
    Entwickler("strongt1me", "Strongt1me", PROJEKT,
               (("PS5 Dump & Image Converter", _gh("strongt1me")),),
               {"de": "Idee, Tests an der echten Konsole und dieses Programm – gebaut für die Community.",
                "en": "Idea, testing on a real console and this program – built for the community."}),
    # --- Werkzeuge und Arbeiten im Programm ---
    Entwickler("RenanGBarreto", "Renan Barreto (PSBrew)", WERKZEUGE,
               (("MkPFS", _gh("PSBrew/MkPFS")),),
               {"de": "Danke für MkPFS – die PFS-Engine, auf der dieses Programm steht.",
                "en": "Thank you for MkPFS – the PFS engine this program is built on."}),
    Entwickler("SvenGDK", "SvenGDK", WERKZEUGE,
               (("UFS2Tool", _gh("SvenGDK/UFS2Tool")),
                ("unjail-ps5app-payload", _gh("SvenGDK/unjail-ps5app-payload"))),
               {"de": "Danke für UFS2Tool und LibProsperoPkg – ohne sie gäbe es hier kein .ffpkg und kein Paketlesen.",
                "en": "Thank you for UFS2Tool and LibProsperoPkg – without them there would be no .ffpkg and no package reading here."}),
    Entwickler("drakmor", "Drakmor", WERKZEUGE,
               (("AMPR EMU", _gh("drakmor/ampr_emu")),
                ("ShadowMount+", _gh("drakmor/ShadowMountPlus")),
                ("kstuff-lite", _gh("EchoStretch/kstuff-lite")),
                ("nanoDNS", _gh("drakmor/nanoDNS")),
                ("pgo_stub", _gh("drakmor/pgo_stub")),
                ("ps5-hwinfo", _gh("drakmor/ps5-hwinfo"))),
               {"de": "Danke für AMPR EMU, ShadowMount+, die Arbeit an kstuff-lite und so vieles mehr – "
                      "ein großer Teil der PS5-Szene läuft auf deinem Code.",
                "en": "Thank you for AMPR EMU, ShadowMount+, the work on kstuff-lite and so much more – "
                      "a large part of the PS5 scene runs on your code."}),
    Entwickler("Gezine", "Gezine", WERKZEUGE,
               (("BD-JB5", _gh("Gezine/BD-JB5")), ("Y2JB", _gh("Gezine/Y2JB"))),
               {"de": "Danke für BD-JB5 und Y2JB – ohne sie gäbe es den Jailbreak über Blu-ray und YouTube nicht.",
                "en": "Thank you for BD-JB5 and Y2JB – without them there would be no jailbreak via Blu-ray and YouTube."}),
    Entwickler("owendswang", "owendswang", WERKZEUGE,
               (("BD-JB5 Poops Autoloader", _gh("owendswang/BD-JB5-Poops-Autoloader")),
                ("Y2JB-P2JB bdj_unpatch", _gh("owendswang/Y2JB-P2JB-bdj_unpatch")),
                ("PS5 Web File Manager", _gh("owendswang/ps5-web-file-manager")),
                ("ps5-syslang", _gh("owendswang/ps5-syslang")),
                ("ps5-aria2", _gh("owendswang/ps5-aria2"))),
               {"de": "Danke für die BD-JB- und Y2JB-Startketten mit Autoloader, den Web File Manager und "
                      "ps5-syslang – damit wird der Jailbreak für alle einfach.",
                "en": "Thank you for the BD-JB and Y2JB chains with autoloader, the Web File Manager and "
                      "ps5-syslang – they make the jailbreak easy for everyone."}),
    Entwickler("john-tornblom", "John Törnblom", WERKZEUGE,
               (("PS5 Payload SDK", _gh("ps5-payload-dev/sdk")),
                ("elfldr", _gh("ps5-payload-dev/elfldr")),
                ("ftpsrv", _gh("ps5-payload-dev/ftpsrv")),
                ("shsrv", _gh("ps5-payload-dev/shsrv")),
                ("gdbsrv", _gh("ps5-payload-dev/gdbsrv"))),
               {"de": "Danke für das Payload SDK, elfldr, ftpsrv und die vielen Grundbausteine, auf denen fast "
                      "jedes PS5-Homebrew aufbaut.",
                "en": "Thank you for the Payload SDK, elfldr, ftpsrv and the many building blocks nearly every "
                      "PS5 homebrew is built on."}),
    Entwickler("EchoStretch", "EchoStretch", WERKZEUGE,
               (("kstuff-lite", _gh("EchoStretch/kstuff-lite")),
                ("ps5-app-dumper", _gh("EchoStretch/ps5-app-dumper"))),
               {"de": "Danke für kstuff-lite und den App Dumper – ohne Dumps gäbe es hier nichts umzuwandeln.",
                "en": "Thank you for kstuff-lite and the App Dumper – without dumps there would be nothing to convert here."}),
    Entwickler("itsPLK", "itsPLK", WERKZEUGE,
               (("PS5 WebKit Autoloader", _gh("itsPLK/ps5-webkit-autoloader")),
                ("PS5 Payload Manager", _gh("itsPLK/ps5-payload-manager")),
                ("PS5 PKG Manager", _gh("itsPLK/ps5-pkg-manager")),
                ("ps5-unified-autoloader", _gh("itsPLK/ps5-unified-autoloader"))),
               {"de": "Danke für WebKit Autoloader, Payload Manager und PKG Manager – Werkzeuge, die jeden Tag gebraucht werden.",
                "en": "Thank you for the WebKit Autoloader, Payload Manager and PKG Manager – tools used every day."}),
    Entwickler("idlesauce", "idlesauce", WERKZEUGE,
               (("umtx2", _gh("idlesauce/umtx2")),
                ("ps5-self-pager", _gh("idlesauce/ps5-self-pager"))),
               {"de": "Danke für umtx2, ps5-self-pager und das ursprüngliche Downgrade-Skript hinter BACKPORT.",
                "en": "Thank you for umtx2, ps5-self-pager and the original downgrade script behind BACKPORT."}),
    Entwickler("BestPig", "BestPig", WERKZEUGE,
               (("BackPork", _gh("BestPig/BackPork")),),
               {"de": "Danke für BackPork – die Grundlage der Funktion BACKPORT.",
                "en": "Thank you for BackPork – the foundation of the BACKPORT feature."}),
    Entwickler("CyB1K", "CyB1K", WERKZEUGE,
               (("PS4 Fake PKG Tools", _gh("CyB1K/PS4-Fake-PKG-Tools-3.87")),),
               {"de": "Danke für SelfUtil – sein Entpackverfahren ist hier für BACKPORT nachgebaut.",
                "en": "Thank you for SelfUtil – its unpacking method is rebuilt here for BACKPORT."}),
    Entwickler("pearlxcore", "pearlxcore", WERKZEUGE,
               (("OrbisPkgTool", _gh("pearlxcore/OrbisPkgTool")),),
               {"de": "Danke für OrbisPkgTool – die Engine hinter „PS4 PKG → OTA“.",
                "en": "Thank you for OrbisPkgTool – the engine behind “PS4 PKG → OTA”."}),
    Entwickler("andy-man", "andy-man", WERKZEUGE,
               (("PS5 Wee Tools", _gh("andy-man/ps5-wee-tools")),),
               {"de": "Danke für PS5 Wee Tools – das Werkzeug für den NOR-Flash der Konsole.",
                "en": "Thank you for PS5 Wee Tools – the tool for the console's NOR flash."}),
    Entwickler("ChillQuant", "ChillQuant", WERKZEUGE,
               (("Direct Stream for PlayStation 5", _gh("ChillQuant/direct-stream-ps5")),),
               {"de": "Danke für Direct Stream – Dateien direkt in den Speicher der PS5.",
                "en": "Thank you for Direct Stream – files straight into the PS5's storage."}),
    Entwickler("kerrdec97", "kerrdec97", WERKZEUGE,
               (("ps5-exfat-builder", _gh("kerrdec97/ps5-exfat-builder")),),
               {"de": "Danke für ps5-exfat-builder – Vorarbeit und Orientierung für dieses Programm.",
                "en": "Thank you for ps5-exfat-builder – groundwork and guidance for this program."}),
    Entwickler("earthonion", "earthonion", WERKZEUGE,
               (("NP Fake Signin", _gh("earthonion")),
                ("garlic-worker", _gh("earthonion/garlic-worker"))),
               {"de": "Danke für NP Fake Signin, GarlicSaves und garlic-worker.",
                "en": "Thank you for NP Fake Signin, GarlicSaves and garlic-worker."}),
    Entwickler("notmaj0r", "maj0r", WERKZEUGE,
               (("Prospero Manager", _gh("notmaj0r/ProsperoMgr")),
                ("CheatRunner", _gh("notmaj0r/CheatRunner"))),
               {"de": "Danke für Prospero Manager und CheatRunner.",
                "en": "Thank you for Prospero Manager and CheatRunner."}),
    Entwickler("seregonwar", "Seregon", WERKZEUGE,
               (("zftpd", _gh("seregonwar/zftpd")), ("MemDBG", _gh("seregonwar/MemDBG"))),
               {"de": "Danke für zftpd und MemDBG.",
                "en": "Thank you for zftpd and MemDBG."}),
    Entwickler("aydencharles", "Hexwell", WERKZEUGE,
               (("OnionHEN", _gh("aydencharles/onionHEN")),),
               {"de": "Danke für OnionHEN.",
                "en": "Thank you for OnionHEN."}),
    Entwickler("OnionBuddies", "OnionBuddies", WERKZEUGE,
               (("DPI v2 (OnionHEN-Plugin)", _gh("OnionBuddies/onionHEN-dpiv2-plugin")),),
               {"de": "Danke für das DPI-v2-Plugin für OnionHEN.",
                "en": "Thank you for the DPI v2 plugin for OnionHEN."}),
    Entwickler("Pharaoh2k", "Pharaoh2k", WERKZEUGE,
               (("ps5debug-NG", _gh("Pharaoh2k/ps5debug-NG")),),
               {"de": "Danke für ps5debug-NG.",
                "en": "Thank you for ps5debug-NG."}),
    Entwickler("OpenSourcereR-dev", "OpenSourcereR", WERKZEUGE,
               (("ps5debug-NG", _gh("Pharaoh2k/ps5debug-NG")),),
               {"de": "Danke für die Arbeit an ps5debug-NG.",
                "en": "Thank you for the work on ps5debug-NG."}),
    Entwickler("juma-sayeh", "Juma Sayeh", WERKZEUGE,
               (("PS5 Game Compressor", _gh("juma-sayeh/PS5-Game-Compressor")),),
               {"de": "Danke für den PS5 Game Compressor.",
                "en": "Thank you for the PS5 Game Compressor."}),
    Entwickler("francoataffarel", "francoataffarel", WERKZEUGE,
               (("ActRemoteLink", _gh("francoataffarel/ActRemoteLink")),),
               {"de": "Danke für ActRemoteLink.",
                "en": "Thank you for ActRemoteLink."}),
    Entwickler("X-F1REBALL-X", "X-F1REBALL-X", WERKZEUGE,
               (("WK-AutoLoader", _gh("X-F1REBALL-X/WK-AutoLoader")),),
               {"de": "Danke für den WK Autoloader.",
                "en": "Thank you for the WK Autoloader."}),
    Entwickler("phantomptr", "PhantomPtr", WERKZEUGE,
               (("PS5Upload", _gh("phantomptr")),),
               {"de": "Danke für PS5Upload.",
                "en": "Thank you for PS5Upload."}),
    Entwickler("KarnerF", "Karner", WERKZEUGE,
               (("SMPlusGui", _gh("KarnerF/SMPlusGui")),),
               {"de": "Danke für SMPlusGui.",
                "en": "Thank you for SMPlusGui."}),
    Entwickler("ItsBlurf", "ItsBlurf", WERKZEUGE,
               (("PoorDS4", _gh("ItsBlurf/PoorDS4")),),
               {"de": "Danke für PoorDS4.",
                "en": "Thank you for PoorDS4."}),
    Entwickler("StonedModder", "StonedModder", WERKZEUGE,
               (("Ghostcontrol", _gh("StonedModder")),),
               {"de": "Danke für Ghostcontrol, auf dem PoorDS4 aufbaut.",
                "en": "Thank you for Ghostcontrol, which PoorDS4 builds on."}),
    Entwickler("ArkSama", "ArkSama (Team PHU)", WERKZEUGE,
               (("PS5 Lapy JB Daemon", _gh("ArkSama/PS5-Lapy-JB-Daemon")),),
               {"de": "Danke für den Lapy JB Daemon.",
                "en": "Thank you for the Lapy JB Daemon."}),
    Entwickler("", "sinfiltros", WERKZEUGE, (),
               {"de": "Danke für AnyPad PS5.",
                "en": "Thank you for AnyPad PS5."}),
    # --- Community ---
    Entwickler("TheOfficialFloW", "TheFloW (Andy Nguyen)", COMMUNITY,
               (("PPPwn", _gh("TheOfficialFloW/PPPwn")),),
               {"de": "Danke für PPPwn und viele Jahre Forschung, die die Szene geprägt haben.",
                "en": "Thank you for PPPwn and many years of research that shaped the scene."}),
    Entwickler("Cryptogenic", "Specter (Cryptogenic)", COMMUNITY,
               (("PS5 IPV6 Kernel Exploit", _gh("Cryptogenic/PS5-IPV6-Kernel-Exploit")),
                ("PS4 5.05 Kernel Exploit", _gh("Cryptogenic/PS4-5.05-Kernel-Exploit"))),
               {"de": "Danke für die Kernel-Exploits für PS4 und PS5 und das geteilte Wissen.",
                "en": "Thank you for the PS4 and PS5 kernel exploits and the knowledge you shared."}),
    Entwickler("sleirsgoevy", "sleirsgoevy", COMMUNITY,
               (("kstuff", _gh("ps5-payload-dev/kstuff")), ("ps4jb", _gh("sleirsgoevy/ps4jb"))),
               {"de": "Danke für kstuff und ps4jb – Grundlagen, auf denen heute so vieles läuft.",
                "en": "Thank you for kstuff and ps4jb – foundations so much runs on today."}),
    Entwickler("ChendoChap", "ChendoChap", COMMUNITY,
               (("PS5-Webkit-Execution", _gh("ChendoChap/PS5-Webkit-Execution")),),
               {"de": "Danke für die WebKit-Ausführung auf der PS5 und die PS4-Arbeiten.",
                "en": "Thank you for WebKit execution on the PS5 and the PS4 work."}),
    Entwickler("zecoxao", "zecoxao", COMMUNITY,
               (("ps5-pup-decrypt", _gh("zecoxao/ps5-pup-decrypt")),),
               {"de": "Danke für die vielen geteilten Werkzeuge und Erkenntnisse.",
                "en": "Thank you for the many tools and insights you shared."}),
    Entwickler("flatz", "flatz", COMMUNITY,
               (("pkg_pfs_tool", _gh("flatz/pkg_pfs_tool")),
                ("ps4_remote_pkg_installer", _gh("flatz/ps4_remote_pkg_installer"))),
               {"de": "Danke für pkg_pfs_tool, den Remote Package Installer und jahrelange Forschung.",
                "en": "Thank you for pkg_pfs_tool, the Remote Package Installer and years of research."}),
    Entwickler("Al-Azif", "Al Azif", COMMUNITY,
               (("ps4-exploit-host", _gh("Al-Azif/ps4-exploit-host")),),
               {"de": "Danke für ps4-exploit-host und die Werkzeuge rund um die Firmware.",
                "en": "Thank you for ps4-exploit-host and the firmware tools."}),
    Entwickler("LightningMods", "LightningMods", COMMUNITY,
               (("Itemzflow", _gh("LightningMods/Itemzflow")), ("PS4-Store", _gh("LightningMods/PS4-Store"))),
               {"de": "Danke für Itemzflow und den Homebrew Store.",
                "en": "Thank you for Itemzflow and the Homebrew Store."}),
    Entwickler("SiSTR0", "SiSTRo", COMMUNITY,
               (("ps5-versions", _gh("SiSTR0/ps5-versions")), ("ps4ren", _gh("SiSTR0/ps4ren"))),
               {"de": "Danke für ps5-versions, ps4ren und deine Beiträge zur Szene.",
                "en": "Thank you for ps5-versions, ps4ren and your contributions to the scene."}),
)


def gruppe(name: str) -> list[Entwickler]:
    """Die Eintraege einer Gruppe in der Reihenfolge von :data:`ENTWICKLER`."""
    return [e for e in ENTWICKLER if e.gruppe == name]
