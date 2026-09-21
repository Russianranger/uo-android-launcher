using System;
using System.Diagnostics;
using System.Numerics;
using System.Reflection.Emit;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Exercises translated .NET JIT code, ARM64 Wine calls, code disposal, thread
// handoffs and compacting GC. This does not claim to reproduce TazUO gameplay.
if (RuntimeInformation.ProcessArchitecture != Architecture.X64) return 1;
Console.WriteLine("FEX_DOTNET_BEGIN " + RuntimeInformation.FrameworkDescription);
long batches = 0;
var clock = Stopwatch.StartNew();
Parallel.For(0, 4, worker => {
    while (clock.Elapsed < TimeSpan.FromSeconds(90)) {
        for (int i = 1; i <= 64; i++) {
            var method = new DynamicMethod("FexJit", typeof(int), new[] {typeof(int)});
            var il = method.GetILGenerator();
            il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldc_I4, i);
            il.Emit(OpCodes.Add); il.Emit(OpCodes.Ret);
            var add = method.CreateDelegate<Func<int,int>>();
            if (add(worker) != worker+i) throw new Exception("Translated JIT result mismatch");
            var data = new int[16384]; Array.Fill(data, i);
            var sum = Vector<int>.Zero;
            for (int n=0; n<data.Length; n+=Vector<int>.Count) sum += new Vector<int>(data,n);
            if (Vector.Sum(sum) != i*data.Length) throw new Exception("Vector result mismatch");
            Thread.Yield();
        }
        GC.Collect(2, GCCollectionMode.Forced, true, true);
        Interlocked.Increment(ref batches);
    }
});
Console.WriteLine("FEX_DOTNET_STRESS_OK batches=" + batches);
return batches >= 4 ? 0 : 2;
