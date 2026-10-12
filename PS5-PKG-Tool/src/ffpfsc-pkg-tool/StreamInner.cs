using System;
using System.Buffers.Binary;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using LibProsperoPkg.PFS;

namespace PkgTool;

// stream-inner: the files of a package's /app0 tree as one byte stream on stdout - for a program that sends them
// on (FTP to a console) without ever writing an unpacked copy to disk.
//
//   stream-inner <pkg> --plan <file> [--passcode P]
//
//   <file> is UTF-8, one line per file to send:  <start> TAB <path>   (path relative to /app0, "/"-separated)
//   <start> is the offset to carry on from (the part the receiver already has); 0 = the whole file.
//
//   stdout is binary and nothing else (every message goes to stderr), little-endian:
//     file     "PKF1"  u32 pathLen  path(UTF-8)  i64 size  i64 start   then exactly (size - start) data bytes
//     end      "PKE1"  u32 fileCount
//   The frame carries the offset the file really starts at: only a plain, contiguous file can start in the middle
//   (InnerImage.IsContiguous); any other file, and a start outside 1..size-1, is sent whole and says start = 0.
//   Stream ends without the end frame, or exit code != 0: the run failed (see stderr).
//
// The idea - read a package and push the files straight to the console, resuming a half-sent file - is
// fpkg2ftp's (kvaps, GPL-3.0-or-later); the code is written here.
internal static partial class Program
{
    const string FileFrame = "PKF1";
    const string EndFrame = "PKE1";

    static int CmdStreamInner(string[] args)
    {
        // Stdout is the data channel: from here on the console writer is stderr, so a stray message - or the usage
        // text of a bad call - can never end up inside a frame.
        var stdout = Console.OpenStandardOutput();
        Console.SetOut(Console.Error);

        if (args.Length < 2) return Bad("stream-inner needs <pkg>");
        var pkg = args[1];
        string passcode = new string('0', 32);
        string? planFile = null;
        for (int i = 2; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--passcode": passcode = Need(args, ref i, "--passcode"); break;
                case "--plan": planFile = Need(args, ref i, "--plan"); break;
                default: return Bad("unknown stream-inner flag: " + args[i]);
            }
        }
        if (planFile == null) return Bad("stream-inner needs --plan <file>");
        if (!File.Exists(pkg)) throw new FileNotFoundException("package not found", pkg);
        if (!File.Exists(planFile)) throw new FileNotFoundException("plan file not found", planFile);

        var plan = new List<(string path, long start)>();
        foreach (var raw in File.ReadAllLines(planFile, Encoding.UTF8))
        {
            if (raw.Length == 0) continue;
            int tab = raw.IndexOf('\t');
            if (tab <= 0 || !long.TryParse(raw.AsSpan(0, tab), out var start) || start < 0)
                return Bad("bad plan line (want <start> TAB <path>): " + raw);
            var rel = raw.Substring(tab + 1).Replace('\\', '/').Trim('/');
            if (rel.Length > 0) plan.Add((rel, start));
        }
        if (plan.Count == 0) return Bad("--plan lists no files");

        var errors = new List<string>();
        var tmpCnt = Path.Combine(RealPath(Path.GetTempPath()), "fpkg-stream-cnt-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var img = new InnerImage(pkg, passcode, cacheBlockSize: 4 << 20, cacheBlocks: 8);
            var cnt = LiftCntSceSys(pkg, passcode, tmpCnt, errors);
            foreach (var e in errors) Console.Error.WriteLine("[warn] " + e);
            var tree = BuildInnerTree(img, cnt);

            // Everything is checked before the first byte goes out: a bad plan must fail cleanly, not halfway.
            foreach (var (path, _) in plan)
                if (!tree.TryGetValue(path, out var te) || te.type != "file")
                {
                    Console.Error.WriteLine("[error] not a file in the image: " + path);
                    return 1;
                }
            Console.Error.WriteLine($"[info] stream-inner  {pkg}  ({plan.Count} file(s))");

            int sent = 0;
            foreach (var (path, wanted) in plan)
            {
                var te = tree[path];
                long size = te.size ?? 0;
                bool fromCnt = te.source == "cnt";
                PfsReader.File? node = null;
                if (!fromCnt)
                    node = img.Pfs.GetFile(path) ?? throw new InvalidDataException("inner file vanished: " + path);
                bool canStartInside = fromCnt || InnerImage.IsContiguous(node!);
                long start = canStartInside && wanted > 0 && wanted < size ? wanted : 0;

                WriteFileFrame(stdout, path, size, start);
                var counted = new CountingStream(stdout);
                if (fromCnt)
                {
                    using var fs = File.OpenRead(cnt[path]);
                    if (start > 0) fs.Seek(start, SeekOrigin.Begin);
                    fs.CopyTo(counted, 1 << 20);
                }
                else
                {
                    long actual = img.CopyFileFrom(node!, counted, start);
                    if (actual != start) throw new InvalidOperationException($"internal: {path} started at {actual}, announced {start}");
                }
                // A file that gives out another amount than its frame announced would shift every later frame.
                if (counted.Written != size - start)
                    throw new InvalidDataException($"{path}: wrote {counted.Written:N0} B, frame announced {size - start:N0} B");
                stdout.Flush();
                sent++;
            }

            var end = new byte[8];
            Encoding.ASCII.GetBytes(EndFrame).CopyTo(end, 0);
            BinaryPrimitives.WriteUInt32LittleEndian(end.AsSpan(4), (uint)sent);
            stdout.Write(end, 0, end.Length);
            stdout.Flush();
            Console.Error.WriteLine($"[info] stream-inner done: {sent} file(s)");
            return 0;
        }
        finally
        {
            try { if (Directory.Exists(tmpCnt)) Directory.Delete(tmpCnt, recursive: true); } catch { }
        }
    }

    static void WriteFileFrame(Stream o, string path, long size, long start)
    {
        var name = Encoding.UTF8.GetBytes(path);
        var buf = new byte[4 + 4 + name.Length + 8 + 8];
        Encoding.ASCII.GetBytes(FileFrame).CopyTo(buf, 0);
        BinaryPrimitives.WriteUInt32LittleEndian(buf.AsSpan(4), (uint)name.Length);
        name.CopyTo(buf, 8);
        BinaryPrimitives.WriteInt64LittleEndian(buf.AsSpan(8 + name.Length), size);
        BinaryPrimitives.WriteInt64LittleEndian(buf.AsSpan(16 + name.Length), start);
        o.Write(buf, 0, buf.Length);
    }

    /// <summary>Write-only pass-through that counts what went through it.</summary>
    sealed class CountingStream : Stream
    {
        readonly Stream _inner;
        public long Written { get; private set; }
        public CountingStream(Stream inner) { _inner = inner; }
        public override void Write(byte[] buffer, int offset, int count) { _inner.Write(buffer, offset, count); Written += count; }
        public override void Write(ReadOnlySpan<byte> buffer) { _inner.Write(buffer); Written += buffer.Length; }
        public override void Flush() => _inner.Flush();
        public override bool CanRead => false;
        public override bool CanSeek => false;
        public override bool CanWrite => true;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
    }
}
