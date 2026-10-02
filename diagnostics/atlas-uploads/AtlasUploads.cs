using System.Buffers;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.CompilerServices;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

[assembly: InternalsVisibleTo("AtlasUploadProbe")]

// The imported client's deps.json remains untouched. The runtime selects this
// hook only after checking the exact renderer/FNA fixture and patch hashes.
internal static class StartupHook
{
    public static void Initialize() => Memento.AtlasUploads.Initialize();
}

namespace Memento
{

// Only atlas writes produced inside GameController.Draw are deferred. Native
// graphics boundaries flush them before any operation can observe the texture.
// The public entry point replaces only the hash-checked TextureAtlas.AddSprite
// call. Its hash-checked Packer reserves one exclusive pixel around each new
// sprite. We initialize only that owned margin to transparent, allowing exact
// reservation adjacency to merge without touching holes or existing sprites.
// No shadow atlas, historical texels, or background uploads are used.
public static class AtlasUploads
{
    internal const int MaxPendingBytes = 4 * 1024 * 1024;
    internal const int MaxPendingWrites = 256;
    internal const int MinBatchBytes = 256;
    internal const int MaxBatchBytes = 1024 * 1024;
    static int initialized;
    static bool enabled;
    [ThreadStatic] static State? state;

    internal delegate void UploadAction(object texture, int level, Rectangle? rectangle, IntPtr data, int byteCount);
    struct Write
    {
        internal object? texture;
        internal Rectangle rectangle;
        internal uint[]? pixels;
        internal int bytes;
    }
    sealed class State
    {
        internal readonly Write[] writes = new Write[MaxPendingWrites];
        internal UploadAction upload = NativeUpload;
        internal ArrayPool<uint> pool = ArrayPool<uint>.Shared;
        internal int count, bytes, drawDepth;
        internal bool flushing;
        internal long logical, native, merged, batchBytes, paddingBytes, maxPending, flushes, flushTicks, maxFlushTicks, stageTicks, fallback, nextReport;
    }
    static State Current => state ??= new State();

    internal static void Initialize()
    {
        if (Environment.GetEnvironmentVariable("MEMENTO_ATLAS_UPLOADS") != "1" ||
            Interlocked.CompareExchange(ref initialized, 1, 0) != 0) return;
        FrameBudget.RegisterDrawBoundaries(BeginDraw, EndDraw);
        enabled = true;
        Report("ATLAS_UPLOADS_ACTIVE revision=1 owned_padding=1 max_pending_bytes=" + MaxPendingBytes + " max_pending_writes=" + MaxPendingWrites);
    }

    static void BeginDraw() => Current.drawDepth++;
    // No uploads here: a failing original Draw must retain
    // its original exception. Unobserved writes stay bounded until the next
    // native graphics boundary (including disposal or the normal presentation).
    static void EndDraw()
    {
        if (state is not { drawDepth: > 0 } s) return;
        s.drawDepth--;
        // Once per frame, rather than checking the clock at every native draw
        // with an empty queue. Optional logging cannot mask original Draw.
        if (s.drawDepth == 0) { try { MaybeReport(s); } catch { } }
    }

    public static void Upload(Texture2D texture, int level, Rectangle? rectangle, IntPtr data, int byteCount)
    {
        if (!enabled) { texture.SetDataPointerEXT(level, rectangle, data, byteCount); return; }
        var s = Current;
        bool candidate = s.drawDepth > 0 && !s.flushing && texture is not null && !texture.IsDisposed &&
            texture.Format == SurfaceFormat.Color;
        UploadCore(texture!, candidate ? texture!.Width : 0, candidate ? texture!.Height : 0,
            candidate, level, rectangle, data, byteCount, padding: true);
    }

    // CPU probe seam exercises the same copying, ordering, bounds, merging and
    // flushing code without creating a native graphics device.
    internal static unsafe void UploadCore(object texture, int width, int height, bool color,
        int level, Rectangle? rectangle, IntPtr data, int byteCount, bool padding = false)
    {
        var s = Current; s.logical++;
        bool candidate = s.drawDepth > 0 && !s.flushing && color && level == 0 && rectangle.HasValue && data != IntPtr.Zero &&
            byteCount > 0 && byteCount <= MaxBatchBytes && Valid(rectangle.GetValueOrDefault(), width, height, byteCount);
        Rectangle sprite = rectangle.GetValueOrDefault(), staged = sprite; int stagedBytes = byteCount;
        if (candidate && padding)
        {
            // A valid sprite against an atlas edge cannot have the guaranteed
            // private margin, so forward the original arguments immediately.
            candidate = sprite.X >= 1 && sprite.Y >= 1 &&
                (long)sprite.X + sprite.Width < width && (long)sprite.Y + sprite.Height < height;
            if (candidate)
            {
                long expanded = ((long)sprite.Width + 2) * ((long)sprite.Height + 2) * sizeof(uint);
                candidate = expanded <= MaxBatchBytes;
                if (candidate)
                {
                    staged = new Rectangle(sprite.X - 1, sprite.Y - 1, sprite.Width + 2, sprite.Height + 2);
                    stagedBytes = (int)expanded;
                }
            }
        }
        if (!candidate || stagedBytes < MinBatchBytes || stagedBytes > MaxBatchBytes)
        {
            Flush(); s.fallback++; CallUpload(s, texture, level, rectangle, data, byteCount); MaybeReport(s); return;
        }
        if (s.count == MaxPendingWrites || s.bytes > MaxPendingBytes - stagedBytes) Flush();
        long began = Stopwatch.GetTimestamp(); uint[]? owned = null;
        try
        {
            owned = s.pool.Rent(stagedBytes / sizeof(uint));
            var source = new ReadOnlySpan<uint>((void*)data, byteCount / sizeof(uint));
            if (padding)
            {
                // Write every owned pixel once. Pool bucket contents outside
                // the packed reservation are neither read nor uploaded.
                owned.AsSpan(0, staged.Width).Clear();
                owned.AsSpan((staged.Height - 1) * staged.Width, staged.Width).Clear();
                for (int y = 0; y < sprite.Height; y++)
                {
                    var row = owned.AsSpan((y + 1) * staged.Width, staged.Width);
                    row[0] = row[^1] = 0;
                    source.Slice(y * sprite.Width, sprite.Width).CopyTo(row.Slice(1, sprite.Width));
                }
                s.paddingBytes += stagedBytes - byteCount;
            }
            else source.CopyTo(owned);
            s.writes[s.count++] = new Write { texture = texture, rectangle = staged, pixels = owned, bytes = stagedBytes };
            owned = null; s.bytes += stagedBytes;
            s.maxPending = Math.Max(s.maxPending, s.bytes);
            // Only the final two writes may merge. This preserves exact order
            // for overlap and mixed textures, while completed rows can merge
            // vertically after their horizontal components have joined.
            while (s.count >= 2 && TryMerge(s)) { }
        }
        catch
        {
            if (owned is not null) s.pool.Return(owned);
            DiscardPending(s); throw;
        }
        finally { s.stageTicks += Math.Max(0, Stopwatch.GetTimestamp() - began); }
    }

    static bool Valid(Rectangle r, int width, int height, int byteCount) => r.X >= 0 && r.Y >= 0 &&
        r.Width > 0 && r.Height > 0 && (long)r.X + r.Width <= width && (long)r.Y + r.Height <= height &&
        (long)r.Width * r.Height * sizeof(uint) == byteCount;

    static bool TryMerge(State s)
    {
        ref Write a = ref s.writes[s.count - 2]; ref Write b = ref s.writes[s.count - 1];
        if (!ReferenceEquals(a.texture, b.texture)) return false;
        var ar = a.rectangle; var br = b.rectangle;
        bool horizontal = ar.Y == br.Y && ar.Height == br.Height &&
            ((long)ar.X + ar.Width == br.X || (long)br.X + br.Width == ar.X);
        bool vertical = ar.X == br.X && ar.Width == br.Width &&
            ((long)ar.Y + ar.Height == br.Y || (long)br.Y + br.Height == ar.Y);
        if (!horizontal && !vertical) return false;
        var merged = new Rectangle(Math.Min(ar.X, br.X), Math.Min(ar.Y, br.Y),
            horizontal ? ar.Width + br.Width : ar.Width, vertical ? ar.Height + br.Height : ar.Height);
        int needed = (a.bytes + b.bytes) / sizeof(uint);
        var original = a.pixels!;
        uint[] output = original.Length >= needed ? original : s.pool.Rent(needed);
        // Repacking bottom-up permits reuse of the existing pooled buffer when
        // horizontal growth changes the packed row stride.
        if (horizontal)
        {
            int ax = ar.X - merged.X, bx = br.X - merged.X;
            for (int y = ar.Height - 1; y >= 0; y--)
            {
                original.AsSpan(y * ar.Width, ar.Width).CopyTo(output.AsSpan(y * merged.Width + ax, ar.Width));
                b.pixels!.AsSpan(y * br.Width, br.Width).CopyTo(output.AsSpan(y * merged.Width + bx, br.Width));
            }
        }
        else
        {
            int aOffset = (ar.Y - merged.Y) * merged.Width, bOffset = (br.Y - merged.Y) * merged.Width;
            original.AsSpan(0, a.bytes / sizeof(uint)).CopyTo(output.AsSpan(aOffset));
            b.pixels!.AsSpan(0, b.bytes / sizeof(uint)).CopyTo(output.AsSpan(bOffset));
        }
        if (!ReferenceEquals(original, output)) s.pool.Return(original);
        s.pool.Return(b.pixels!);
        a.pixels = output; a.rectangle = merged; a.bytes += b.bytes;
        b = default; s.count--; s.merged++; return true;
    }

    public static unsafe void Flush()
    {
        var s = state;
        if (s is null || s.flushing) return;
        if (s.count == 0) return;
        long began = Stopwatch.GetTimestamp(); s.flushing = true; s.flushes++;
        try
        {
            for (int i = 0; i < s.count; i++)
            {
                ref Write write = ref s.writes[i];
                // GraphicsDevice disposal marks the device before disposing
                // children. Those writes have no remaining observer and must
                // not be sent through a destroyed native handle.
                if (write.texture is Texture2D texture &&
                    (texture.IsDisposed || texture.GraphicsDevice.IsDisposed)) continue;
                fixed (uint* data = write.pixels)
                {
                    CallUpload(s, write.texture!, 0, write.rectangle, (IntPtr)data, write.bytes);
                }
                s.batchBytes += write.bytes;
            }
        }
        finally
        {
            DiscardPending(s); s.flushing = false;
            long elapsed = Math.Max(0, Stopwatch.GetTimestamp() - began);
            s.flushTicks += elapsed; s.maxFlushTicks = Math.Max(s.maxFlushTicks, elapsed); MaybeReport(s);
        }
    }

    static void CallUpload(State s, object texture, int level, Rectangle? rectangle, IntPtr data, int byteCount)
    {
        s.native++; s.upload(texture, level, rectangle, data, byteCount);
    }
    static void NativeUpload(object texture, int level, Rectangle? rectangle, IntPtr data, int byteCount)
        => ((Texture2D)texture).SetDataPointerEXT(level, rectangle, data, byteCount);
    static void DiscardPending(State s)
    {
        for (int i = 0; i < s.count; i++)
        {
            if (s.writes[i].pixels is { } pixels) s.pool.Return(pixels);
            s.writes[i] = default;
        }
        s.count = s.bytes = 0;
    }
    static void MaybeReport(State s)
    {
        long now = Stopwatch.GetTimestamp();
        if (s.nextReport == 0) { s.nextReport = now + 5 * Stopwatch.Frequency; return; }
        if (now < s.nextReport) return;
        s.nextReport = now + 5 * Stopwatch.Frequency;
        try
        {
            Report("ATLAS_UPLOADS utc=" + DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture) +
                " thread=" + Environment.CurrentManagedThreadId + " logical_sprites=" + s.logical + " native_uploads=" + s.native +
                " merged=" + s.merged + " fallback_uploads=" + s.fallback + " batch_bytes=" + s.batchBytes + " owned_padding_bytes=" + s.paddingBytes +
                " max_pending_bytes=" + s.maxPending + " flush_calls=" + s.flushes + " flush_total_ms=" + Ms(s.flushTicks) +
                " flush_max_ms=" + Ms(s.maxFlushTicks) + " stage_total_ms=" + Ms(s.stageTicks));
        }
        catch { } // Optional summaries cannot alter graphics behavior.
        s.logical = s.native = s.merged = s.fallback = s.batchBytes = s.paddingBytes = s.maxPending = s.flushes = s.flushTicks = s.maxFlushTicks = s.stageTicks = 0;
    }
    static string Ms(long ticks) => (ticks * 1000.0 / Stopwatch.Frequency).ToString("F3", CultureInfo.InvariantCulture);
    static void Report(string line) { try { Console.Error.WriteLine(line); } catch { } }

    internal static void ConfigureProbe(UploadAction upload, ArrayPool<uint>? pool = null)
    {
        if (state is { } old) DiscardPending(old);
        state = new State { upload = upload, pool = pool ?? ArrayPool<uint>.Shared };
    }
    internal static void BeginProbeDraw() => BeginDraw();
    internal static void EndProbeDraw() => EndDraw();
    internal static int ProbePendingBytes => state?.bytes ?? 0;
    internal static int ProbePendingWrites => state?.count ?? 0;
    internal static void ResetProbe() { if (state is { } s) DiscardPending(s); state = null; }
}
}
