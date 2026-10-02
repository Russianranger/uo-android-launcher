using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using Memento;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

// Resolve the imported exact fixture before JITting any FNA-typed probe body.
if (args.Length != 3) throw new ArgumentException("fixture-folder native-shim enabled|disabled|failure");
var folder = Path.GetFullPath(args[0]);
AssemblyLoadContext.Default.Resolving += (_, name) => {
    var file = Path.Combine(folder, name.Name + ".dll");
    return File.Exists(file) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(file) : null;
};
var fna = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, "FNA.dll"));
var native = NativeLibrary.Load(Path.GetFullPath(args[1]));
NativeLibrary.SetDllImportResolver(fna, (_, _, _) => native);
Probe.Run(folder, native, args[2]);

static class Probe
{
    const BindingFlags Instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
    const BindingFlags Static = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void ResetCall();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int CountCall();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int IdCall(int index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong ArgCall(int index, int argument);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PixelCall(int texture, int x, int y);
    static ResetCall reset = null!;
    static CountCall count = null!;
    static IdCall id = null!;
    static ArgCall arg = null!;
    static PixelCall pixel = null!;
    static void Check(bool ok, string why) { if (!ok) throw new Exception(why); }
    static void Field(object value, Type owner, string name, object field) => owner.GetField(name, Instance)!.SetValue(value, field);
    static T Export<T>(IntPtr native, string name) where T : Delegate => Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(native, name));
    static Texture2D Texture(int number)
    {
        var device = (GraphicsDevice)RuntimeHelpers.GetUninitializedObject(typeof(GraphicsDevice));
        Field(device, typeof(GraphicsDevice), "GLDevice", new IntPtr(0xD00D));
        // Empty real TextureCollections satisfy the original Dispose body.
        var collection = typeof(TextureCollection).GetConstructors(Instance).Single().Invoke(new object[] { 1, new bool[1] });
        Field(device, typeof(GraphicsDevice), "<Textures>k__BackingField", collection);
        Field(device, typeof(GraphicsDevice), "<VertexTextures>k__BackingField", collection);
        var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
        Field(texture, typeof(Texture2D), "<Width>k__BackingField", 64);
        Field(texture, typeof(Texture2D), "<Height>k__BackingField", 64);
        Field(texture, typeof(Texture), "<Format>k__BackingField", SurfaceFormat.Color);
        Field(texture, typeof(Texture), "<LevelCount>k__BackingField", 1);
        Field(texture, typeof(Texture), "texture", new IntPtr(0x5000 + number));
        Field(texture, typeof(GraphicsResource), "graphicsDevice", device);
        GC.SuppressFinalize(texture); GC.SuppressFinalize(device);
        return texture;
    }
    static unsafe void Upload(Texture2D texture, Rectangle r, uint value)
    {
        uint[] data = Enumerable.Repeat(value, r.Width * r.Height).ToArray();
        fixed (uint* p = data) AtlasUploads.Upload(texture, 0, r, (IntPtr)p, data.Length * 4);
        // A producer is free to reuse its scratch memory immediately.
        Array.Clear(data);
    }
    static long Begin() => FrameBudget.Begin(FrameBudget.Draw);
    static void End(long began) => FrameBudget.End(FrameBudget.Draw, began);
    static Type NativeType => typeof(Texture2D).Assembly.GetType("Microsoft.Xna.Framework.Graphics.FNA3D", true)!;
    static readonly Dictionary<string, int> NativeIds = new() {
        ["DrawIndexedPrimitives"] = 1, ["DrawInstancedPrimitives"] = 2, ["DrawPrimitives"] = 3,
        ["SetTextureData2D"] = 4, ["SetTextureData3D"] = 5, ["SetTextureDataCube"] = 6, ["SetTextureDataYUV"] = 7,
        ["GetTextureData2D"] = 8, ["GetTextureData3D"] = 9, ["GetTextureDataCube"] = 10,
        ["ReadBackbuffer"] = 11, ["ResolveTarget"] = 12, ["ResetBackbuffer"] = 13, ["SwapBuffers"] = 14,
        ["AddDisposeTexture"] = 15, ["SetRenderTargets"] = 16, ["Clear"] = 17, ["DestroyDevice"] = 18,
        ["GetVertexBufferData"] = 19, ["GetIndexBufferData"] = 20, ["SetVertexBufferData"] = 21, ["SetIndexBufferData"] = 22,
    };
    static object FirstFieldValue(Type type, int n) => type == typeof(float) ? BitConverter.Int32BitsToSingle(n) : type == typeof(byte) ? unchecked((byte)n) : type.IsEnum ? Enum.ToObject(type, n) : n;
    static uint FirstWord(object value, Type type)
    {
        var memory = Marshal.AllocHGlobal(Marshal.SizeOf(type));
        try { for (int i = 0; i < Marshal.SizeOf(type); i++) Marshal.WriteByte(memory, i, 0); Marshal.StructureToPtr(value, memory, false); return (uint)Marshal.ReadInt32(memory); }
        finally { Marshal.FreeHGlobal(memory); }
    }
    static unsafe (object[], ulong[], List<IntPtr>) Arguments(MethodInfo method)
    {
        var values = new object[method.GetParameters().Length]; var expected = new ulong[values.Length]; var allocated = new List<IntPtr>();
        foreach (var p in method.GetParameters()) {
            int i = p.Position; var t = p.ParameterType;
            if (t.IsByRef) {
                var element = t.GetElementType()!; var value = Activator.CreateInstance(element)!;
                var first = element.GetFields(Instance).OrderBy(f => f.MetadataToken).First();
                first.SetValue(value, FirstFieldValue(first.FieldType, 70 + i)); values[i] = value; expected[i] = FirstWord(value, element);
            } else if (t.IsPointer) {
                var memory = Marshal.AllocHGlobal(128); allocated.Add(memory); values[i] = Pointer.Box((void*)memory, t); expected[i] = (ulong)memory.ToInt64();
            } else if (t == typeof(IntPtr)) { values[i] = new IntPtr(0x10000 + i); expected[i] = (ulong)(0x10000 + i); }
            else if (t == typeof(float)) { values[i] = 1.25f + i; expected[i] = (uint)BitConverter.SingleToInt32Bits((float)values[i]); }
            else if (t == typeof(byte)) { values[i] = (byte)(31 + i); expected[i] = (byte)values[i]; }
            else { values[i] = t.IsEnum ? Enum.ToObject(t, 401 + i) : 401 + i; expected[i] = (ulong)(401 + i); }
        }
        return (values, expected, allocated);
    }
    public static void Run(string folder, IntPtr native, string mode)
    {
        bool enabled = mode != "disabled";
        Environment.SetEnvironmentVariable("MEMENTO_ATLAS_UPLOADS", enabled ? "1" : "0");
        typeof(AtlasUploads).Assembly.GetType("StartupHook", true)!.GetMethod("Initialize", Static)!.Invoke(null, null);
        reset = Export<ResetCall>(native, "TestReset"); count = Export<CountCall>(native, "TestCount"); id = Export<IdCall>(native, "TestId");
        arg = Export<ArgCall>(native, "TestArg"); pixel = Export<PixelCall>(native, "TestPixel");
        Export<ResetCall>(native, "TestClearPixels")();
        var texture = Texture(0);
        if (mode == "failure") {
            reset(); long began = Begin(); Upload(texture, new Rectangle(1, 1, 8, 8), 0xABCD1234);
            var fail = NativeType.GetMethod("FNA3D_GetIndexBufferData", Static)!;
            var (values, _, allocated) = Arguments(fail);
            try { fail.Invoke(null, values); throw new Exception("Missing original native entry point was swallowed"); }
            catch (TargetInvocationException e) when (e.InnerException is EntryPointNotFoundException) { }
            finally { foreach (var p in allocated) Marshal.FreeHGlobal(p); End(began); }
            Check(count() == 1 && id(0) == 4 && pixel(0, 1, 1) == 0xABCD1234, "Flush did not occur once before failing original native call");
            reset(); Upload(texture, new Rectangle(11, 1, 8, 8), 0x87654321);
            Check(count() == 1 && pixel(0, 11, 1) == 0x87654321, "Exception cleanup retained draw scope or lost later upload");
            Console.WriteLine("ATLAS_BOUNDARY_OK actual_fna=true mode=failure native_exception=true draw_cleanup=true"); return;
        }
        // The public production path owns pixel data and coalesces two complete
        // adjacent rectangles before actual FNA invokes its native upload.
        reset(); long draw = Begin();
        Upload(texture, new Rectangle(1, 1, 8, 8), 0x01020304); Upload(texture, new Rectangle(11, 1, 8, 8), 0x11223344);
        Check(count() == (enabled ? 0 : 2), "Draw scope enablement changed immediate/deferred behavior");
        AtlasUploads.Flush(); End(draw);
        Check(count() == (enabled ? 1 : 2), "Actual merged upload or reentrant native Flush duplicated/lost uploads");
        Check(pixel(0, 1, 1) == 0x01020304 && pixel(0, 8, 8) == 0x01020304 && pixel(0, 11, 1) == 0x11223344 && pixel(0, 18, 8) == 0x11223344,
            "Staged pointer memory was lost or merged stride corrupted texels");
        Check(pixel(0, 20, 0) == 0 && pixel(0, 9, 1) == 0 && pixel(0, 10, 1) == 0, "Merged upload touched historical/unwritten texture data");

        // Execute every actual patched native wrapper, including overloads.
        int wrappers = 0;
        foreach (var method in NativeType.GetMethods(Static).Where(m => m.Name.StartsWith("FNA3D_") && NativeIds.ContainsKey(m.Name[6..]))) {
            reset(); draw = Begin(); Upload(texture, new Rectangle(1, 11, 8, 8), 0x55667788);
            var (values, expected, allocated) = Arguments(method);
            try { method.Invoke(null, values); }
            finally { End(draw); foreach (var p in allocated) Marshal.FreeHGlobal(p); }
            Check(count() == 2 && id(0) == 4 && id(1) == NativeIds[method.Name[6..]], "Original native call did not execute exactly once after upload: " + method);
            for (int i = 0; i < expected.Length; i++) Check(arg(1, i) == expected[i], $"Native argument changed: {method.Name}[{i}] expected {expected[i]} got {arg(1, i)}");
            if (method.Name is "FNA3D_ResolveTarget" or "FNA3D_ResetBackbuffer" or "FNA3D_Clear" or "FNA3D_SwapBuffers")
                foreach (var p in method.GetParameters().Where(p => p.ParameterType.IsByRef)) {
                    var t = p.ParameterType.GetElementType()!; var f = t.GetFields(Instance).OrderBy(f => f.MetadataToken).First();
                    var expectedValue = FirstFieldValue(f.FieldType, 24680);
                    Check(Equals(f.GetValue(values[p.Position]), expectedValue), "Native by-ref result was not propagated: " + method);
                }
            wrappers++;
        }
        Check(wrappers == 26, "Actual fixture native overload count changed: " + wrappers);
        // Draw scope cleanup itself must not issue a GPU call while an
        // original managed exception unwinds. The next observing boundary
        // flushes the copied pixels and outside-Draw writes remain immediate.
        reset(); draw = Begin(); var originalError = new InvalidOperationException("fixture Draw");
        try { Upload(texture, new Rectangle(1, 21, 8, 8), 0xABCDEF12); throw originalError; }
        catch (InvalidOperationException e) { Check(ReferenceEquals(e, originalError), "Draw exception identity changed"); }
        finally { End(draw); }
        Check(count() == (enabled ? 0 : 1), "Draw cleanup performed an unsafe GPU upload while unwinding");
        AtlasUploads.Flush(); Check(count() == 1 && pixel(0, 1, 21) == 0xABCDEF12, "Next boundary lost exceptional Draw pixels");
        reset(); draw = Begin(); Upload(texture, new Rectangle(11, 21, 8, 8), 0x1234ABCD);
        try { AtlasUploads.Upload(texture, 0, new Rectangle(21, 21, 8, 8), IntPtr.Zero, 256); throw new Exception("Original validation failure was swallowed"); }
        catch (ArgumentNullException e) { Check(e.ParamName == "data", "Original FNA validation exception changed"); }
        finally { End(draw); }
        Check(count() == 1 && pixel(0, 11, 21) == 0x1234ABCD, "Fallback exception lost preceding queued write");
        // Overlapping writes and mixed textures preserve original ordering.
        var other = Texture(1); reset(); draw = Begin();
        Upload(texture, new Rectangle(1, 31, 8, 8), 0xAAAAAAAA); Upload(other, new Rectangle(1, 31, 8, 8), 0xBBBBBBBB);
        Upload(texture, new Rectangle(1, 31, 8, 8), 0xCCCCCCCC); AtlasUploads.Flush(); End(draw);
        Check(count() == 3 && arg(0, 1) == 0x5000 && arg(1, 1) == 0x5001 && arg(2, 1) == 0x5000 && pixel(0, 1, 31) == 0xCCCCCCCC && pixel(1, 1, 31) == 0xBBBBBBBB,
            "Overlapping/mixed atlas writes reordered");
        // Outside Draw (including unsupported renderer configuration), writes
        // remain immediate; disabled initialization never registers callbacks.
        reset(); Upload(texture, new Rectangle(1, 41, 8, 8), 0xDDDDDDDD); Check(count() == 1, "Outside-Draw write was deferred");
        reset(); draw = Begin(); var disposable = Texture(2); Upload(disposable, new Rectangle(1, 1, 8, 8), 0x12345678); disposable.Dispose(); End(draw);
        Check(count() == 2 && id(0) == 4 && arg(0, 1) == 0x5002 && id(1) == 15 && arg(1, 1) == 0x5002 && disposable.IsDisposed,
            "Pending upload lost native handle before Texture.Dispose");
        if (enabled) {
            reset(); draw = Begin(); var dying = Texture(3); Upload(dying, new Rectangle(1, 1, 8, 8), 0xDEADBEEF);
            Field(dying.GraphicsDevice, typeof(GraphicsDevice), "<IsDisposed>k__BackingField", true); AtlasUploads.Flush(); End(draw);
            Check(count() == 0, "Pending write reached an already-disposed graphics device");
        }
        ActualRenderer(folder, texture, enabled);
        Console.WriteLine($"ATLAS_BOUNDARY_OK actual_fna=true actual_renderer=true mode={mode} native_overloads={wrappers} args_preserved=true refs_preserved=true reentrant_flush=true pixel_copy=true disposal=true");
    }
    delegate Texture2D AddSpriteCall(object atlas, uint[] pixels, int width, int height, out Rectangle rectangle);
    static void ActualRenderer(string folder, Texture2D texture, bool enabled)
    {
        var renderer = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, "ClassicUO.Renderer.dll"));
        var utility = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, "ClassicUO.Utility.dll"));
        var type = renderer.GetType("ClassicUO.Renderer.TextureAtlas", true)!;
        var atlas = Activator.CreateInstance(type, texture.GraphicsDevice, 64, 64, SurfaceFormat.Color)!;
        ((List<Texture2D>)type.GetField("_textureList", Instance)!.GetValue(atlas)!).Add(texture);
        type.GetField("_packer", Instance)!.SetValue(atlas, Activator.CreateInstance(utility.GetType("StbRectPackSharp.Packer", true)!, 64, 64));
        var call = new DynamicMethod("ActualAddSprite", typeof(Texture2D), new[] { typeof(object), typeof(uint[]), typeof(int), typeof(int), typeof(Rectangle).MakeByRefType() }, typeof(Probe).Module, true);
        var il = call.GetILGenerator(); il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Castclass, type); il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Call, typeof(ReadOnlySpan<uint>).GetMethod("op_Implicit", new[] { typeof(uint[]) })!);
        il.Emit(OpCodes.Ldarg_2); il.Emit(OpCodes.Ldarg_3); il.Emit(OpCodes.Ldarg_S, (byte)4); il.Emit(OpCodes.Callvirt, type.GetMethod("AddSprite")!); il.Emit(OpCodes.Ret);
        var add = (AddSpriteCall)call.CreateDelegate(typeof(AddSpriteCall));
        // Twelve real Packer reservations fill two rows. Fresh one-pixel
        // margins are disjoint owned allocations; a texel beyond them is old
        // texture data and must survive the production coalescing path.
        uint[] sentinel = { 0xF00DBAAD }; unsafe { fixed (uint* p = sentinel) texture.SetDataPointerEXT(0, new Rectangle(60, 60, 1, 1), (IntPtr)p, 4); }
        reset(); long draw = Begin(); var rectangles = new Rectangle[12];
        for (int i = 0; i < rectangles.Length; i++) {
            var data = Enumerable.Repeat(0xA1B2C300u + (uint)i, 64).ToArray();
            var result = add(atlas, data, 8, 8, out rectangles[i]);
            Check(ReferenceEquals(result, texture), "Actual TextureAtlas changed sprite texture identity");
            Array.Clear(data);
            Check(rectangles[i] == new Rectangle(1 + i % 6 * 10, 1 + i / 6 * 10, 8, 8), "Pinned packer UV/owned reservation changed");
        }
        Check(count() == (enabled ? 0 : 12), "Actual Renderer.AddSprite did not reach production helper");
        AtlasUploads.Flush(); End(draw);
        Check(count() == (enabled ? 1 : 12), "Actual renderer twelve-sprite upload reduction failed: " + count());
        for (int i = 0; i < rectangles.Length; i++) {
            var r = rectangles[i];
            for (int y = 0; y < 8; y++) for (int x = 0; x < 8; x++)
                Check(pixel(0, r.X + x, r.Y + y) == 0xA1B2C300u + (uint)i, "Actual renderer sprite byte oracle changed");
            if (enabled) Check(pixel(0, r.X - 1, r.Y) == 0 && pixel(0, r.X + r.Width, r.Y) == 0 && pixel(0, r.X, r.Y - 1) == 0 && pixel(0, r.X, r.Y + r.Height) == 0,
                "Fresh reserved atlas margin was not transparent");
        }
        Check(pixel(0, 60, 60) == 0xF00DBAAD, "Merged upload rewrote old texels beyond owned packer reservations");
        if (enabled) Check(arg(0, 2) == 0 && arg(0, 3) == 0 && arg(0, 4) == 60 && arg(0, 5) == 20 && arg(0, 8) == 60 * 20 * 4,
            "Two actual packer rows did not form one exact covered reservation");
        ((IDisposable)type.GetField("_packer", Instance)!.GetValue(atlas)!).Dispose();
    }
}
