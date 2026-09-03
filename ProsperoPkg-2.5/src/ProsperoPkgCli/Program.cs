// Kommandozeilen-Huelle um LibProsperoPkg.
//
// Das Programm ruft PKG-Werkzeuge als eigene Prozesse auf - so wie mkpfs
// und UFS2Tool. Das haelt die Grenze sauber: LibProsperoPkg steht unter
// GPL-3, das aufrufende Programm nicht.
//
// Zwei Befehle:
//
//   inspect --source <Ordner>
//       Sagt, ob ein Backup als Debug-Paket starten wuerde. Liest nur.
//
//   build --source <Ordner> --out <Ordner> [Optionen]
//       Baut ein finalisiertes Debug-Abbild (\x7FFIH). Nur dieses Format
//       ist ein vollstaendiges Paket; ein nacktes \x7FCNT traegt bloss
//       Metadaten.
//
// Die Ausgabe ist zeilenweise und schlicht, damit das aufrufende Programm
// sie unveraendert in sein Protokollfenster stellen kann. Die letzte
// Zeile eines geglueckten Baus lautet "RESULT: <Pfad>".

using System.Globalization;
using System.Text.Json;
using LibProsperoPkg;
using LibProsperoPkg.Content;

namespace ProsperoPkgCli;

internal static class Program
{
    private const int ExitOk = 0;
    private const int ExitUsage = 2;
    private const int ExitFailed = 3;

    internal static int Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        if (args.Length == 0)
        {
            Usage();
            return ExitUsage;
        }

        try
        {
            return args[0].ToLowerInvariant() switch
            {
                "inspect" => Inspect(Parse(args)),
                "build" => Build(Parse(args)),
                "homebrew" => Homebrew(Parse(args)),
                "--help" or "-h" or "help" => Usage(),
                _ => Unknown(args[0]),
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[FEHLER] {ex.GetType().Name}: {ex.Message}");
            return ExitFailed;
        }
    }

    private static int Unknown(string was)
    {
        Console.Error.WriteLine($"[FEHLER] Unbekannter Befehl: {was}");
        Usage();
        return ExitUsage;
    }

    private static int Usage()
    {
        Console.WriteLine("ProsperoPkgCli - Huelle um LibProsperoPkg 2.5");
        Console.WriteLine();
        Console.WriteLine("  inspect --source <Ordner>");
        Console.WriteLine("  build   --source <Ordner> --out <Ordner>");
        Console.WriteLine("  homebrew --source <Ordner> --out <Ordner> [--module <Datei>]");
        Console.WriteLine("          [--content-id <36 Zeichen>] [--title-id <9 Zeichen>]");
        Console.WriteLine("          [--title <Text>] [--version <NN.NN>]");
        Console.WriteLine("          [--passcode <32 Zeichen>] [--mode Application|Homebrew|");
        Console.WriteLine("           AdditionalContentData|AdditionalContentNoData]");
        Console.WriteLine("          [--license-free] [--fake-sign] [--metadata-only]");
        Console.WriteLine("          [--schnell]  (Kraken ohne Optimal-Parse, Messwerkzeug)");
        Console.WriteLine();
        Console.WriteLine("Ohne --content-id/--title-id/--title/--version werden die Werte aus");
        Console.WriteLine("sce_sys/param.json des Quellordners genommen.");
        return ExitUsage;
    }

    private static Dictionary<string, string> Parse(string[] args)
    {
        var werte = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (int i = 1; i < args.Length; i++)
        {
            string a = args[i];
            if (!a.StartsWith("--", StringComparison.Ordinal))
            {
                continue;
            }

            string name = a[2..];
            // Schalter ohne Wert: das naechste Argument ist eine Option
            // oder es gibt keines mehr.
            if (i + 1 >= args.Length || args[i + 1].StartsWith("--", StringComparison.Ordinal))
            {
                werte[name] = "1";
            }
            else
            {
                werte[name] = args[++i];
            }
        }

        return werte;
    }

    private static string Pflicht(Dictionary<string, string> w, string name)
    {
        if (!w.TryGetValue(name, out string? wert) || string.IsNullOrWhiteSpace(wert))
        {
            throw new ArgumentException($"--{name} fehlt.");
        }

        return wert;
    }

    private static int Inspect(Dictionary<string, string> w)
    {
        string quelle = Pflicht(w, "source");
        if (!Directory.Exists(quelle))
        {
            Console.Error.WriteLine($"[FEHLER] Kein Ordner: {quelle}");
            return ExitFailed;
        }

        ProsperoLaunchReadinessReport bericht = ProsperoLaunchReadiness.InspectAppRoot(quelle);
        Console.WriteLine($"AppRoot              : {bericht.AppRoot}");
        Console.WriteLine($"IsLaunchReady        : {bericht.IsLaunchReady}");
        Console.WriteLine($"HasEboot             : {bericht.HasEboot}");
        Console.WriteLine($"HasParamJson         : {bericht.HasParamJson}");
        Console.WriteLine($"RequiresDebugConsole : {bericht.RequiresDebugConsole}");
        Console.WriteLine($"Modules              : {bericht.Modules.Count}");
        foreach (ModuleLaunchReadiness m in bericht.Modules)
        {
            if (!m.WillRunOnDebugConsole)
            {
                Console.WriteLine($"BLOCKER: {m.Kind}\t{m.Path}");
            }
        }

        foreach (string i in bericht.Issues)
        {
            Console.WriteLine($"ISSUE: {i}");
        }

        Console.WriteLine($"RESULT: {(bericht.IsLaunchReady ? "READY" : "NOT_READY")}");
        return ExitOk;
    }

    /// <summary>Liest fehlende Angaben aus sce_sys/param.json des Quellordners.</summary>
    private static void AusParamJson(string quelle, ProsperoBuildOptions o)
    {
        string pfad = Path.Combine(quelle, "sce_sys", "param.json");
        if (!File.Exists(pfad))
        {
            return;
        }

        using JsonDocument doc = JsonDocument.Parse(File.ReadAllBytes(pfad));
        JsonElement wurzel = doc.RootElement;

        string? Lies(string name) =>
            wurzel.TryGetProperty(name, out JsonElement e) && e.ValueKind == JsonValueKind.String
                ? e.GetString()
                : null;

        if (string.IsNullOrWhiteSpace(o.ContentId))
        {
            o.ContentId = Lies("contentId") ?? "";
        }

        if (string.IsNullOrWhiteSpace(o.TitleId))
        {
            o.TitleId = Lies("titleId") ?? "";
        }

        if (string.IsNullOrWhiteSpace(o.Title) &&
            wurzel.TryGetProperty("localizedParameters", out JsonElement lp) &&
            lp.ValueKind == JsonValueKind.Object)
        {
            foreach (string sprache in new[] { "de-DE", "en-US" })
            {
                if (lp.TryGetProperty(sprache, out JsonElement eintrag) &&
                    eintrag.TryGetProperty("titleName", out JsonElement tn) &&
                    tn.ValueKind == JsonValueKind.String)
                {
                    o.Title = tn.GetString() ?? "";
                    break;
                }
            }
        }

        if (string.IsNullOrWhiteSpace(o.Title))
        {
            o.Title = o.TitleId;
        }

        // masterVersion hat das Format NN.NN, contentVersion NN.NNN.NNN.
        // Die Bauoptionen wollen NN.NN.
        string? master = Lies("masterVersion");
        if (!string.IsNullOrWhiteSpace(master))
        {
            o.Version = master;
        }
    }

    /// <summary>Die Encoder-Schalter, die den teuren Optimal-Parse steuern.</summary>
    private static readonly string[] OptimalSchalter =
    {
        "ProductionOptimalSingleChunk",
        "ProductionWindowedOptimal",
    };

    /// <summary>
    /// Schaltet den Optimal-Parse des Kraken-Encoders ab.
    /// </summary>
    /// <remarks>
    /// Die Felder sind <c>internal static</c> und ohne
    /// <c>InternalsVisibleTo</c> nur ueber Reflexion erreichbar. Das ist
    /// bewusst so gewaehlt: Die Bibliothek bleibt unveraendert, und der
    /// Eingriff steht an einer Stelle, statt sich im Fremdcode zu
    /// verstecken.
    ///
    /// Findet sich ein Feld nicht, wird das gesagt und weitergemacht -
    /// eine andere Fassung der Bibliothek darf die Namen aendern.
    /// </remarks>
    private static void GreedyErzwingen()
    {
        Type? typ = typeof(ProsperoBuildOptions).Assembly
            .GetType("LibProsperoPkg.PFS.Compression.Oodle.OodleKrakenEncoder");
        if (typ is null)
        {
            Console.WriteLine("HINWEIS: OodleKrakenEncoder nicht gefunden - --schnell wirkt nicht.");
            return;
        }

        foreach (string name in OptimalSchalter)
        {
            System.Reflection.FieldInfo? feld = typ.GetField(
                name,
                System.Reflection.BindingFlags.NonPublic
                | System.Reflection.BindingFlags.Static);
            if (feld is null || feld.FieldType != typeof(bool))
            {
                Console.WriteLine($"HINWEIS: {name} nicht setzbar - uebersprungen.");
                continue;
            }

            object? vorher = feld.GetValue(null);
            feld.SetValue(null, false);
            Console.WriteLine($"schnell: {name} {vorher} -> {feld.GetValue(null)}");
        }
    }

    private static int Homebrew(Dictionary<string, string> w)
    {
        string quelle = Pflicht(w, "source");
        string ziel = Pflicht(w, "out");
        if (!Directory.Exists(quelle))
        {
            Console.Error.WriteLine($"[FEHLER] Kein Ordner: {quelle}");
            return ExitFailed;
        }

        Directory.CreateDirectory(ziel);

        var o = new ProsperoHomebrewPackageOptions
        {
            HomebrewFolder = quelle,
            OutputFolder = ziel,
        };

        if (w.TryGetValue("module", out string? modul))
        {
            o.ModuleName = modul;
        }

        if (w.TryGetValue("content-id", out string? cid))
        {
            o.ContentId = cid;
        }

        if (w.TryGetValue("title", out string? titel))
        {
            o.Title = titel;
        }

        if (w.TryGetValue("version", out string? ver))
        {
            o.Version = ver;
        }

        if (w.TryGetValue("passcode", out string? pc))
        {
            o.Passcode = pc;
        }

        if (w.ContainsKey("schnell"))
        {
            GreedyErzwingen();
        }

        Console.WriteLine($"Homebrew  : {o.HomebrewFolder}");
        Console.WriteLine($"Modul     : {o.ModuleName}");
        Console.WriteLine($"Ziel      : {o.OutputFolder}");
        Console.WriteLine("---");
        Console.Out.Flush();

        var begonnen = DateTime.UtcNow;
        ProsperoHomebrewPackageResult ergebnis =
            ProsperoHomebrewPackager.Package(o, zeile =>
            {
                Console.WriteLine(zeile);
                Console.Out.Flush();
            });

        Console.WriteLine("---");
        foreach (string warnung in ergebnis.Warnings)
        {
            Console.WriteLine($"WARN: {warnung}");
        }

        ProsperoLaunchReadinessReport bericht = ergebnis.LaunchReadiness;
        Console.WriteLine($"IsLaunchReady : {bericht.IsLaunchReady}");
        foreach (ModuleLaunchReadiness m in bericht.Modules)
        {
            if (!m.WillRunOnDebugConsole)
            {
                Console.WriteLine($"BLOCKER: {m.Kind}\t{m.Path}");
            }
        }

        double sekunden = (DateTime.UtcNow - begonnen).TotalSeconds;
        long groesse = File.Exists(ergebnis.OutputPath)
            ? new FileInfo(ergebnis.OutputPath).Length
            : 0;
        Console.WriteLine(string.Format(
            CultureInfo.InvariantCulture,
            "Dauer: {0:F0} s, Groesse: {1} Byte", sekunden, groesse));
        if (ergebnis.DebugLicense is not null)
        {
            Console.WriteLine(
                "DebugLicense: ContentId=" + ergebnis.DebugLicense.ContentId
                + ", RequiresRif=" + ergebnis.DebugLicense.RequiresRif);
        }

        Console.WriteLine($"RESULT: {ergebnis.OutputPath}");
        return ExitOk;
    }

    private static int Build(Dictionary<string, string> w)
    {
        string quelle = Pflicht(w, "source");
        string ziel = Pflicht(w, "out");
        if (!Directory.Exists(quelle))
        {
            Console.Error.WriteLine($"[FEHLER] Kein Ordner: {quelle}");
            return ExitFailed;
        }

        Directory.CreateDirectory(ziel);

        var o = new ProsperoBuildOptions
        {
            SourceFolder = quelle,
            OutputFolder = ziel,
        };

        if (w.TryGetValue("content-id", out string? cid))
        {
            o.ContentId = cid;
        }

        if (w.TryGetValue("title-id", out string? tid))
        {
            o.TitleId = tid;
        }

        if (w.TryGetValue("title", out string? titel))
        {
            o.Title = titel;
        }

        if (w.TryGetValue("version", out string? ver))
        {
            o.Version = ver;
        }

        if (w.TryGetValue("passcode", out string? pc))
        {
            o.Passcode = pc;
        }

        AusParamJson(quelle, o);

        if (w.ContainsKey("metadata-only"))
        {
            o.OutputFormat = ProsperoOutputFormat.MetadataContainer;
        }

        if (w.TryGetValue("mode", out string? modus) &&
            Enum.TryParse(modus, ignoreCase: true, out ProsperoPackageMode m))
        {
            o.Mode = m;
        }

        o.LicenseFree = w.ContainsKey("license-free");
        o.FakeSignSelfModules = w.ContainsKey("fake-sign");

        if (w.ContainsKey("schnell"))
        {
            GreedyErzwingen();
        }

        Console.WriteLine($"Quelle    : {o.SourceFolder}");
        Console.WriteLine($"Ziel      : {o.OutputFolder}");
        Console.WriteLine($"ContentId : {o.ContentId}");
        Console.WriteLine($"TitleId   : {o.TitleId}");
        Console.WriteLine($"Titel     : {o.Title}");
        Console.WriteLine($"Version   : {o.Version}");
        Console.WriteLine($"Modus     : {o.Mode}");
        Console.WriteLine($"Format    : {o.OutputFormat}");
        Console.WriteLine($"LicenseFree/FakeSign: {o.LicenseFree}/{o.FakeSignSelfModules}");
        Console.WriteLine("---");
        Console.Out.Flush();

        var begonnen = DateTime.UtcNow;
        ProsperoBuildResult ergebnis = ProsperoPackageBuilder.Build(o, zeile =>
        {
            Console.WriteLine(zeile);
            Console.Out.Flush();
        });

        Console.WriteLine("---");
        foreach (string warnung in ergebnis.Warnings)
        {
            Console.WriteLine($"WARN: {warnung}");
        }

        double sekunden = (DateTime.UtcNow - begonnen).TotalSeconds;
        long groesse = File.Exists(ergebnis.OutputPath)
            ? new FileInfo(ergebnis.OutputPath).Length
            : 0;
        Console.WriteLine(string.Format(
            CultureInfo.InvariantCulture,
            "Dauer: {0:F0} s, Groesse: {1} Byte", sekunden, groesse));
        if (ergebnis.DebugLicense is not null)
        {
            Console.WriteLine($"DebugLicense: ContentId={ergebnis.DebugLicense.ContentId}");
        }

        Console.WriteLine($"RESULT: {ergebnis.OutputPath}");
        return ExitOk;
    }
}
