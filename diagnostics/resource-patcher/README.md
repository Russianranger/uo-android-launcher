# Exact-client resource timing

This opt-in diagnostic layer adds 24 typed scopes and five `Monitor.Enter`
observations to the checksum-pinned TazUO 5.2 assemblies, on top of the published
frame budget, music cache, atlas batching and 0.2.16 FNA observations. Seven
deltas cover both frame-budget/render-trace client variants and both original
and music-cached Assets variants. Complete vendor assemblies are never shipped.

The selected boundaries are actual art/terrain/static/gump/texmap/light and
MUL/UOP animation decoding, external PNG loading, bulk and mapped reads, chunk
loading, world rendering, animation cache locking, item/mobile creation, FNA
image loading, and graphics resource registration/removal. Generic mapped
`ReadAt<T>` and primitive byte/pixel getters remain untouched; terrain page
faults through the generic method remain inside the enclosing chunk scope.

The original IL, arguments, results, custom modifiers, constants, annotations,
resources, native imports, and original exception regions remain intact. Typed
return locals support the imported byref-like `ArtInfo`, `GumpInfo`, and
`Span<FrameInfo>` results without boxing. A final diagnostic `finally` runs on
every original return or exception. The five original monitor calls forward
their original object/ref-bool exactly once; lock-wait records are buffered until
the enclosing observed method has completed its original cleanup. Constructors
and managed-pointer-returning sprite getters are not wrapped.

`RESOURCE_CALL` reports originating managed thread, begin-stage/frame, wall,
self, nested FNA wall, allocation, and parent/depth. Self excludes only observed
resource children; unobserved decoding, JIT, locks, scheduling, and disk/page
fault work can remain in self. FNA wall is nested inside resource wall and must
not be added to it. Allocations are inclusive of child calls. CPU is sampled only
for outermost resource scopes; network processing supplies an outer scope so
object creation bursts do not add CPU syscalls per object. Background threads
without a frame have `frame=0`, `stage=none`, and unavailable start offset.

Slow records require 50 ms and are capped at eight per originating thread/window.
Count/total/max windows retain all calls; their measured `window_ms` is provided
because reporting is deferred until the next outermost resource activity.
`resource_trace_overhead_ms` records observer bookkeeping/output cost in the
frame; it overlaps some parent/stage wall and is not an additive attribution or
an amount that can safely be subtracted from every nested scope.

The backend preflights every output checksum and every required backup before
changing any assembly. Atomic per-file replacements are individually
recoverable after interrupted preparation. The next launch first restores all
recognized diagnostic outputs to their verified ordinary frame/music/atlas
bases; it also recognizes the 0.2.16 diagnostic FNA for upgrades. Unknown
assemblies are preserved. The observer requires original SDL and manifest
revision 2. Disabling cold-load timing restores all five managed libraries while
retaining the ordinary performance improvements.

Run `scripts/check-resource-trace.sh --host-only` after the atlas suite. The
normal command also publishes/runs `ResourceTraceProbe.exe` under x64 Wine.
The same probe is staged for retained ARM64 Wine/FEX and both PRoot modes. It
JIT-prepares all 24 exact wrapped bodies, including their byref-like returns and
nested exception handlers; executes real file/mapped reads and the new disposal
exception cleanup; executes a contended graphics resource lock plus original
null-lock failure; and verifies attribution, nesting, bounded records, thread
isolation, network exception cleanup, stage overflow recovery, and allocation
free warm calls. Structural verification checks all other methods and metadata.
Separate native GPU tests verify the observer and original atlas pixel behavior.
