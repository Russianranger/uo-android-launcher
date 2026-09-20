# Exact-build render-list instrumentation

This tool instruments `FillGameObjectList` entry and wraps the existing
`DrawRenderList` IL with a diagnostic catch/finally. The original enumeration,
object draws, enumerator disposal and exception propagation remain in place.
Only `InvalidOperationException` is observed; the exception is rethrown.

The production input is restricted to SHA-256
`b04066be1b1b475ca00e6982a980e2dd11b93abede00c79c68bde566bdcf947e`.
It is TazUO 5.2.0 at commit `0fc274bf83c6ba84f37ec69a6bec7570743c1777`.
`--fixture` is solely for the automated probe, never the Android installer.

Build Memento.RenderTrace, then run the patcher with the original DLL, the trace
DLL and an output DLL. Keep FNA.dll alongside the input. For unavailable optional-parameter enum
dependencies, the resolver uses the original Constant rows' encoded integer
type; the verifier checks all constants remain unchanged. Original portable symbols
are not emitted because injected IL invalidates their offsets. The original
DLL and PDB are retained by the installer; the instrumented assembly provides
method names in stacks without claiming original source offsets.

Complete client assemblies are not committed. The APK carries a checksum-constrained delta
and the diagnostic helper. No Cecil runtime or online patch generation is used
on the device. The helper is preloaded by a minimal .NET startup hook; it adds
no event handlers, timers, graphics calls or worker threads. Existing detailed
managed diagnostics remain independently controlled.
