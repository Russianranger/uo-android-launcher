using System;
using System.IO;
using System.IO.MemoryMappedFiles;
using System.Runtime.CompilerServices;
using System.Threading;

namespace Memento
{
    // Fixed, per-thread breadcrumbs, observed by Python outside Wine. After
    // initialization this uses only memory writes: no file IO, timers, stack
    // walking, console locks, graphics calls, or new worker threads per probe.
    internal static unsafe class RenderProgress
    {
        const int Header = 32, Slots = 16, Stride = 64;
        internal const int Size = Header + Slots * Stride;
        static object lifetime;
        static byte* data;
        [ThreadStatic] static int slotPlusOne;

        internal static bool Open()
        {
            // Keep mapping-specific types out of this method and the hot path
            // so even a missing optional framework library can be caught here.
            try { return OpenMapping(); }
            catch { return false; }
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        static bool OpenMapping()
        {
            if (data != null) return true;
            MemoryMappedFile mapping = null;
            MemoryMappedViewAccessor view = null;
            byte* pointer = null;
            try
            {
                string path = Environment.GetEnvironmentVariable("MEMENTO_RENDER_PROGRESS");
                if (string.IsNullOrEmpty(path)) return false;
                var file = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite);
                try
                {
                    if (file.Length != Size) return false;
                    mapping = MemoryMappedFile.CreateFromFile(file, null, Size,
                        MemoryMappedFileAccess.ReadWrite, HandleInheritability.None, false);
                }
                finally { if (mapping == null) file.Dispose(); }
                view = mapping.CreateViewAccessor(0, Size, MemoryMappedFileAccess.ReadWrite);
                view.SafeMemoryMappedViewHandle.AcquirePointer(ref pointer);
                pointer += view.PointerOffset;
                *(int*)(pointer + 8) = 2;
                *(int*)(pointer + 12) = Environment.ProcessId; // Wine/Windows pid
                *(int*)(pointer + 16) = Slots;
                *(int*)(pointer + 20) = Stride;
                Thread.MemoryBarrier();
                *(long*)pointer = 0x3230435254524f55; // UORTRC02, little endian
                lifetime = new object[] { mapping, view };
                data = pointer; // Mapping/pointer retained until process exit.
                return true;
            }
            finally
            {
                if (data == null)
                {
                    if (pointer != null) view.SafeMemoryMappedViewHandle.ReleasePointer();
                    view?.Dispose();
                    mapping?.Dispose();
                }
            }
        }

        internal static void Record(int stage, int count = -1, int version = 0,
                                    int readers = 0, long fill = 0, int issue = 0, int hresult = 0)
        {
            byte* start = data;
            if (start == null || slotPlusOne < 0) return;
            if (slotPlusOne == 0)
            {
                int thread = Environment.CurrentManagedThreadId;
                for (int i = 0; i < Slots; i++)
                    if (Interlocked.CompareExchange(ref *(int*)(start + Header + i * Stride + 4), thread, 0) == 0)
                    { slotPlusOne = i + 1; break; }
                if (slotPlusOne == 0) { slotPlusOne = -1; return; }
            }
            byte* row = start + Header + (slotPlusOne - 1) * Stride;
            int sequence = *(int*)row;
            Volatile.Write(ref *(int*)row, unchecked(sequence + 1));
            Thread.MemoryBarrier();
            *(int*)(row + 8) = stage;
            *(int*)(row + 12) = count;
            *(int*)(row + 16) = version;
            *(int*)(row + 20) = readers;
            *(long*)(row + 24) = fill;
            ++*(long*)(row + 32); // Boundary count; no clock call in the hot path.
            if (stage == 5) ++*(long*)(row + 40);
            *(int*)(row + 48) |= issue; // Keep failure evidence after finally/End.
            if (issue != 0) *(int*)(row + 52) = hresult;
            Volatile.Write(ref *(int*)row, unchecked(sequence + 2));
        }
    }
}
