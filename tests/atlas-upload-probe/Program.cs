using System.Buffers;
using Memento;
using Microsoft.Xna.Framework;

static class Probe
{
    sealed class Image
    {
        internal readonly int width, height;
        internal readonly uint[] actual, expected;
        internal readonly List<Rectangle> rectangles = new();
        internal Image(int width, int height)
        {
            this.width = width; this.height = height;
            actual = new uint[width * height]; expected = new uint[width * height];
            for (int i = 0; i < actual.Length; i++) actual[i] = expected[i] = 0xAB000000U | (uint)i;
        }
        internal void Check() => Require(actual.AsSpan().SequenceEqual(expected), "Pixel difference, including preexisting texels or unwritten holes");
    }
    sealed class TrackingPool : ArrayPool<uint>
    {
        internal readonly HashSet<uint[]> rented = new();
        internal int rents, returns;
        public override uint[] Rent(int minimumLength)
        {
            uint[] array = new uint[minimumLength];
            Array.Fill(array, 0xDEADC0DEU); // Prove every uploaded pixel is initialized, including owned padding.
            Require(rented.Add(array), "Duplicate rented buffer"); rents++; return array;
        }
        public override void Return(uint[] array, bool clearArray = false)
        {
            Require(rented.Remove(array), "Double return or foreign buffer"); returns++;
        }
        internal void Check() => Require(rented.Count == 0 && rents == returns, "Pooled buffer retained after flush, failure or teardown");
    }
    static void Require(bool okay, string message) { if (!okay) throw new Exception(message); }
    static unsafe void Apply(object texture, int level, Rectangle? rectangle, IntPtr pointer, int byteCount)
    {
        var image = (Image)texture; Rectangle r = rectangle!.Value;
        Require(level == 0 && byteCount == r.Width * r.Height * 4, "Native upload arguments changed");
        var source = new ReadOnlySpan<uint>((void*)pointer, byteCount / 4);
        for (int y = 0; y < r.Height; y++) source.Slice(y * r.Width, r.Width).CopyTo(image.actual.AsSpan((y + r.Y) * image.width + r.X));
        image.rectangles.Add(r);
    }
    static unsafe void Write(Image image, Rectangle r, uint[] source, bool color = true, int level = 0, bool padding = false)
    {
        Require(source.Length >= r.Width * r.Height, "Probe source too short");
        for (int y = 0; y < r.Height; y++) source.AsSpan(y * r.Width, r.Width).CopyTo(image.expected.AsSpan((y + r.Y) * image.width + r.X));
        fixed (uint* pointer = source)
            AtlasUploads.UploadCore(image, image.width, image.height, color, level, r, (IntPtr)pointer, r.Width * r.Height * 4, padding);
    }
    static void WriteOwned(Image image, Rectangle sprite, uint[] source)
    {
        // Independent pixel oracle: a fresh private reservation starts with
        // transparent pixels, then receives exactly the original sprite data.
        for (int y = sprite.Y - 1; y <= sprite.Y + sprite.Height; y++)
            image.expected.AsSpan(y * image.width + sprite.X - 1, sprite.Width + 2).Clear();
        Write(image, sprite, source, padding: true);
    }
    static uint[] Pixels(int count, uint value) { var result = new uint[count]; Array.Fill(result, value); return result; }
    static void Begin(AtlasUploads.UploadAction? upload = null, TrackingPool? pool = null)
    {
        AtlasUploads.ConfigureProbe(upload ?? Apply, pool); AtlasUploads.BeginProbeDraw();
    }
    static void Finish(TrackingPool? pool = null)
    {
        AtlasUploads.EndProbeDraw(); AtlasUploads.Flush();
        Require(AtlasUploads.ProbePendingBytes == 0 && AtlasUploads.ProbePendingWrites == 0, "Pending state did not clear");
        pool?.Check(); AtlasUploads.ResetProbe();
    }
    static void RowsAndDirections()
    {
        var pool = new TrackingPool(); var image = new Image(4 * 44, 4 * 44); Begin(pool: pool);
        for (int y = 0; y < 4; y++) for (int x = 0; x < 4; x++)
            Write(image, new Rectangle(x * 44, y * 44, 44, 44), Pixels(44 * 44, (uint)(x + y * 4 + 1)));
        Require(image.rectangles.Count == 0 && AtlasUploads.ProbePendingWrites == 1, "Completed 44x44 rows did not coalesce");
        Finish(pool); image.Check(); Require(image.rectangles.Count == 1 && image.rectangles[0] == new Rectangle(0, 0, 176, 176), "Merged rectangle changed coordinates");
        // All adjacency directions, including reuse of a larger pool bucket.
        foreach (var second in new[] { new Rectangle(0, 16, 16, 16), new Rectangle(32, 16, 16, 16), new Rectangle(16, 0, 16, 16), new Rectangle(16, 32, 16, 16) })
        {
            image = new Image(48, 48); Begin();
            Write(image, new Rectangle(16, 16, 16, 16), Pixels(256, 1)); Write(image, second, Pixels(256, 2));
            Finish(); image.Check(); Require(image.rectangles.Count == 1, "An exact adjacency direction did not merge");
        }
    }
    static void HolesOverlapAndIdentity()
    {
        var a = new Image(64, 64); var b = new Image(64, 64); Begin();
        Write(a, new Rectangle(0, 0, 16, 16), Pixels(256, 1));
        Write(a, new Rectangle(16, 0, 16, 16), Pixels(256, 2));
        Write(a, new Rectangle(0, 16, 16, 16), Pixels(256, 3)); // L shape: must not fill the hole.
        Write(b, new Rectangle(0, 16, 16, 16), Pixels(256, 4));
        Write(a, new Rectangle(0, 32, 16, 16), Pixels(256, 5)); // Do not move across another texture's write.
        Finish(); a.Check(); b.Check(); Require(a.rectangles.Count == 3 && b.rectangles.Count == 1, "Hole or mixed texture writes merged");
        a = new Image(64, 64); Begin();
        Write(a, new Rectangle(0, 0, 16, 16), Pixels(256, 1));
        Write(a, new Rectangle(8, 0, 16, 16), Pixels(256, 2));
        Write(a, new Rectangle(24, 0, 16, 16), Pixels(256, 3));
        Finish(); a.Check(); Require(a.rectangles.Count == 2, "Overlap was collapsed or reordered");
    }
    static void PaddedReservations()
    {
        var pool = new TrackingPool(); var image = new Image(48, 48); var source = new uint[64]; Begin(pool: pool);
        for (int y = 0; y < 4; y++) for (int x = 0; x < 4; x++)
        {
            for (int i = 0; i < source.Length; i++) source[i] = 0xFF000000U | (uint)((y * 4 + x) * 256 + i + 1);
            WriteOwned(image, new Rectangle(1 + x * 10, 1 + y * 10, 8, 8), source);
            Array.Fill(source, 0xDEADBEEFU); // Caller immediately reuses its sprite buffer.
        }
        Require(image.rectangles.Count == 0 && AtlasUploads.ProbePendingWrites == 1 && AtlasUploads.ProbePendingBytes == 40 * 40 * 4,
            "Packer's adjacent private reservations did not merge or accounting excluded padding");
        Finish(pool); image.Check(); Require(image.rectangles.Count == 1 && image.rectangles[0] == new Rectangle(0, 0, 40, 40),
            "Padded sprite reservation coordinates changed");
        // The missing fourth reservation and all surrounding historical texels
        // must remain untouched even though three reservations form an L.
        image = new Image(32, 32); Begin();
        WriteOwned(image, new Rectangle(1, 1, 8, 8), Pixels(64, 1));
        WriteOwned(image, new Rectangle(11, 1, 8, 8), Pixels(64, 2));
        WriteOwned(image, new Rectangle(1, 11, 8, 8), Pixels(64, 3));
        Finish(); image.Check(); Require(image.rectangles.Count == 2, "Padded L-shape filled an unowned hole");
        // Unequal sprite widths still merge when their complete owned margins
        // have an exact edge. Every interior pixel keeps its original value.
        image = new Image(64, 32); Begin();
        WriteOwned(image, new Rectangle(1, 1, 9, 16), Pixels(9 * 16, 4));
        WriteOwned(image, new Rectangle(12, 1, 13, 16), Pixels(13 * 16, 5));
        Finish(); image.Check(); Require(image.rectangles.Count == 1, "Unequal padded sprite reservations did not merge");
        // Atlas-edge sprites have no guaranteed margin: preserve the original
        // upload arguments, pixels and immediate behavior instead.
        image = new Image(32, 32); Begin();
        Write(image, new Rectangle(0, 1, 8, 8), Pixels(64, 6), padding: true);
        Write(image, new Rectangle(1, 0, 8, 8), Pixels(64, 7), padding: true);
        Write(image, new Rectangle(24, 1, 8, 8), Pixels(64, 8), padding: true);
        Write(image, new Rectangle(1, 24, 8, 8), Pixels(64, 9), padding: true);
        Require(image.rectangles.Count == 4 && AtlasUploads.ProbePendingWrites == 0, "Invalid owned border was deferred");
        Finish(); image.Check();
        // Size thresholds and budgets apply to the expanded reservation.
        image = new Image(512, 512); var large = Pixels(510 * 510, 10); Begin();
        for (int i = 0; i < 5; i++) WriteOwned(image, new Rectangle(1, 1, 510, 510), large);
        Require(image.rectangles.Count == 4 && AtlasUploads.ProbePendingBytes == 1024 * 1024, "Padding exceeded the pending byte budget");
        Finish(); image.Check();
        image = new Image(514, 514); Begin();
        Write(image, new Rectangle(1, 1, 512, 512), Pixels(512 * 512, 11), padding: true);
        Require(image.rectangles.Count == 1 && image.rectangles[0] == new Rectangle(1, 1, 512, 512), "Oversized expanded reservation changed original fallback");
        Finish(); image.Check();
    }
    static void AdjacencyFuzz()
    {
        var random = new Random(144903);
        for (int i = 0; i < 1000; i++)
        {
            int width = random.Next(8, 33), height = random.Next(8, 33), other = random.Next(8, 33);
            var a = new Rectangle(40, 40, width, height);
            var b = (i % 4) switch {
                0 => new Rectangle(40 - other, 40, other, height),
                1 => new Rectangle(40 + width, 40, other, height),
                2 => new Rectangle(40, 40 - other, width, other),
                _ => new Rectangle(40, 40 + height, width, other)
            };
            var image = new Image(128, 128); var pixelsA = new uint[a.Width * a.Height]; var pixelsB = new uint[b.Width * b.Height];
            for (int p = 0; p < pixelsA.Length; p++) pixelsA[p] = 0xAA000000U | (uint)p;
            for (int p = 0; p < pixelsB.Length; p++) pixelsB[p] = 0xBB000000U | (uint)p;
            Begin(); Write(image, a, pixelsA); Write(image, b, pixelsB); Finish(); image.Check();
            Require(image.rectangles.Count == 1, "Varied exact adjacency failed to merge");
        }
    }
    static void RandomizedEquivalenceAndReuse()
    {
        var random = new Random(247390); var pool = new TrackingPool();
        var images = new[] { new Image(128, 128), new Image(128, 128) }; var source = new uint[32 * 32];
        Begin(pool: pool);
        for (int i = 0; i < 4000; i++)
        {
            var image = images[random.Next(images.Length)]; int width = random.Next(8, 33), height = random.Next(8, 33);
            var r = new Rectangle(random.Next(129 - width), random.Next(129 - height), width, height);
            for (int p = 0; p < width * height; p++) source[p] = unchecked((uint)(i * 65537 + p));
            Write(image, r, source); Array.Fill(source, 0xDEADBEEFU);
            if (random.Next(7) == 0) { AtlasUploads.Flush(); foreach (var current in images) current.Check(); }
        }
        Finish(pool); foreach (var current in images) current.Check();
    }
    static void Budgets()
    {
        var pool = new TrackingPool(); var image = new Image(16, 16); var source = Pixels(256, 1); Begin(pool: pool);
        for (int i = 0; i < AtlasUploads.MaxPendingWrites + 1; i++) Write(image, new Rectangle(0, 0, 16, 16), source);
        Require(image.rectangles.Count == AtlasUploads.MaxPendingWrites && AtlasUploads.ProbePendingWrites == 1, "Write-count budget did not flush before overflow");
        Finish(pool); image.Check();
        pool = new TrackingPool(); image = new Image(512, 512); source = Pixels(512 * 512, 2); Begin(pool: pool);
        for (int i = 0; i < 5; i++) Write(image, new Rectangle(0, 0, 512, 512), source);
        Require(image.rectangles.Count == 4 && AtlasUploads.ProbePendingBytes == 1024 * 1024, "Byte budget did not flush before overflow");
        Finish(pool); image.Check();
    }
    static unsafe void FallbackAndOutsideOrder()
    {
        int native = 0; var texture = new object(); var source = Pixels(1024 * 512, 3); Begin((_, _, _, _, _) => native++);
        fixed (uint* pointer = source)
        {
            var cases = new[] {
                (0, (Rectangle?)new Rectangle(0, 0, 4, 4), 64, true), // Too small.
                (0, (Rectangle?)new Rectangle(0, 0, 1024, 512), 2 * 1024 * 1024, true), // Too large.
                (1, (Rectangle?)new Rectangle(0, 0, 16, 16), 1024, true),
                (0, (Rectangle?)null, 1024, true),
                (0, (Rectangle?)new Rectangle(-1, 0, 16, 16), 1024, true),
                (0, (Rectangle?)new Rectangle(1010, 0, 16, 16), 1024, true),
                (0, (Rectangle?)new Rectangle(0, 0, 16, 16), 1020, true),
                (0, (Rectangle?)new Rectangle(0, 0, 16, 16), 1024, false)
            };
            foreach (var item in cases)
            {
                int before = native;
                AtlasUploads.UploadCore(texture, 1024, 512, item.Item4, item.Item1, item.Item2, (IntPtr)pointer, item.Item3);
                Require(native == before + 1 && AtlasUploads.ProbePendingWrites == 0, "Fallback did not call original upload immediately");
            }
            AtlasUploads.UploadCore(texture, 1024, 512, true, 0, new Rectangle(0, 0, 16, 16), IntPtr.Zero, 1024);
            Require(native == cases.Length + 1, "Null pointer did not reach original upload unchanged");
        }
        Finish();
        var image = new Image(16, 16); Begin();
        Write(image, new Rectangle(0, 0, 16, 16), Pixels(256, 1)); AtlasUploads.EndProbeDraw();
        Require(image.rectangles.Count == 0, "EndDraw performed GPU work");
        Write(image, new Rectangle(0, 0, 16, 16), Pixels(256, 2));
        Require(image.rectangles.Count == 2 && AtlasUploads.ProbePendingWrites == 0, "Outside Draw did not preserve upload order");
        image.Check(); AtlasUploads.ResetProbe();
    }
    static void ReadbackAndExceptionCleanup()
    {
        var image = new Image(32, 16); Begin();
        Write(image, new Rectangle(0, 0, 16, 16), Pixels(256, 1));
        AtlasUploads.Flush(); image.Check(); // Same barrier required before native readback.
        Write(image, new Rectangle(16, 0, 16, 16), Pixels(256, 2)); Finish(); image.Check();
        var pool = new TrackingPool(); var failure = new InvalidOperationException("Original native upload failure"); int calls = 0;
        Begin((_, _, _, _, _) => { calls++; AtlasUploads.Flush(); throw failure; }, pool);
        image = new Image(32, 16); Write(image, new Rectangle(0, 0, 16, 16), Pixels(256, 1));
        Write(image, new Rectangle(0, 0, 16, 16), Pixels(256, 2));
        try { AtlasUploads.Flush(); throw new Exception("Native upload exception swallowed"); }
        catch (InvalidOperationException actual) { Require(ReferenceEquals(actual, failure), "Native exception identity changed"); }
        Require(calls == 1 && AtlasUploads.ProbePendingWrites == 0 && AtlasUploads.ProbePendingBytes == 0, "Failed flush reentered or retained state");
        pool.Check(); AtlasUploads.Flush(); Require(calls == 1, "Failed flush repeated stale writes"); AtlasUploads.ResetProbe();
        // Draw cleanup cannot mask its original failure or invoke an upload.
        calls = 0; Begin((_, _, _, _, _) => calls++);
        Write(image, new Rectangle(0, 0, 16, 16), Pixels(256, 3));
        try { try { throw failure; } finally { AtlasUploads.EndProbeDraw(); } }
        catch (InvalidOperationException actual) { Require(ReferenceEquals(actual, failure), "Draw cleanup changed the original exception"); }
        Require(calls == 0 && AtlasUploads.ProbePendingWrites == 1, "Draw failure cleanup uploaded or dropped valid writes");
        AtlasUploads.Flush(); Require(calls == 1, "Next native boundary did not flush retained writes"); AtlasUploads.ResetProbe();
        pool = new TrackingPool(); Begin(pool: pool); Write(image, new Rectangle(0, 0, 16, 16), Pixels(256, 4));
        AtlasUploads.ResetProbe(); pool.Check(); // Explicit probe teardown returns buffers without GPU work.
    }
    static void ThreadIsolationAndReentrancy()
    {
        int mainCalls = 0, otherCalls = 0; var image = new Image(16, 16); Begin((_, _, _, _, _) => { mainCalls++; AtlasUploads.Flush(); });
        Write(image, new Rectangle(0, 0, 16, 16), Pixels(256, 1)); Exception? backgroundFailure = null;
        var thread = new Thread(() => {
            try {
                AtlasUploads.ConfigureProbe((_, _, _, _, _) => otherCalls++);
                Write(new Image(16, 16), new Rectangle(0, 0, 16, 16), Pixels(256, 2));
                Require(otherCalls == 1 && AtlasUploads.ProbePendingWrites == 0, "Draw scope leaked to another thread");
                AtlasUploads.BeginProbeDraw(); Write(new Image(16, 16), new Rectangle(0, 0, 16, 16), Pixels(256, 3));
                Require(otherCalls == 1 && AtlasUploads.ProbePendingWrites == 1, "Thread-local draw staging failed"); Finish();
            } catch (Exception ex) { backgroundFailure = ex; }
        });
        thread.Start(); thread.Join(); if (backgroundFailure is not null) throw backgroundFailure;
        Require(mainCalls == 0 && AtlasUploads.ProbePendingWrites == 1 && otherCalls == 2, "Another thread changed main-thread staging");
        Finish(); Require(mainCalls == 1, "Native flush recursed through its own boundary");
    }
    static unsafe void WarmAllocations()
    {
        int native = 0; var image = new object(); var source = Pixels(256, 1);
        Begin((_, _, _, _, _) => native++);
        fixed (uint* pointer = source)
        {
            IntPtr address = (IntPtr)pointer;
            void Frame()
            {
                AtlasUploads.UploadCore(image, 32, 16, true, 0, new Rectangle(0, 0, 16, 16), address, 1024);
                AtlasUploads.UploadCore(image, 32, 16, true, 0, new Rectangle(16, 0, 16, 16), address, 1024);
                AtlasUploads.Flush();
            }
            for (int i = 0; i < 500; i++) Frame();
            long before = GC.GetAllocatedBytesForCurrentThread();
            for (int i = 0; i < 10000; i++) Frame();
            long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
            Require(allocated == 0, "Warm atlas uploads allocated " + allocated + " bytes");
            Require(native == 10500, "Warm merged upload count changed");
        }
        Finish();
        native = 0; Begin((_, _, _, _, _) => native++);
        fixed (uint* pointer = source)
        {
            IntPtr address = (IntPtr)pointer;
            void Frame()
            {
                AtlasUploads.UploadCore(image, 20, 10, true, 0, new Rectangle(1, 1, 8, 8), address, 256, padding: true);
                AtlasUploads.UploadCore(image, 20, 10, true, 0, new Rectangle(11, 1, 8, 8), address, 256, padding: true);
                AtlasUploads.Flush();
            }
            for (int i = 0; i < 500; i++) Frame();
            long before = GC.GetAllocatedBytesForCurrentThread();
            for (int i = 0; i < 10000; i++) Frame();
            long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
            Require(allocated == 0, "Warm padded atlas uploads allocated " + allocated + " bytes");
            Require(native == 10500, "Warm padded native upload reduction changed");
        }
        Finish();
    }
    public static int Main()
    {
        try {
            RowsAndDirections(); HolesOverlapAndIdentity(); PaddedReservations(); AdjacencyFuzz(); RandomizedEquivalenceAndReuse(); Budgets();
            FallbackAndOutsideOrder(); ReadbackAndExceptionCleanup(); ThreadIsolationAndReentrancy(); WarmAllocations();
            Console.WriteLine("ATLAS_UPLOAD_PROBE_PASS randomized_writes=4000 padded_grid_sprites=16 padded_grid_native_uploads=1 warm_frames=20000 warm_allocations=0"); return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        finally { AtlasUploads.ResetProbe(); }
    }
}
