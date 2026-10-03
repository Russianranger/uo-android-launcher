# Passive Vulkan cold-load observer, revision 2

This explicit Linux Vulkan layer sits below Wine. It forwards each intercepted
call exactly once with the caller's arguments and return value. It never queries
fence status, submits work, inserts synchronization, polls, or changes GPU data.
The retained loader's instance destroy callback remains cached at creation.

Revision 2 adds bounded correlation to the existing 50 ms slow-call records
(eight per thread per five-second window). Successful fast submissions are kept
in fence metadata rather than logged individually, so a slow wait can describe
the submission it was waiting on. Device IDs are process-wide monotonic; queue,
fence, image and command-buffer IDs are monotonic within a device and change
when a destroyed object's handle is reused. Destruction/free metadata is retired
before forwarding, so a concurrent new allocation cannot be removed by the old
object's bookkeeping after the downstream destroy returns. Fence generations advance after a
successful reset. A reset set too large to examine makes generations
conservatively `unknown`; later observations do not invent a numeric generation
until the fence is recreated. Failed operations do not publish success metadata.

`VULKAN_CALL` preserves `op`, `wall_ms`, `thread_cpu_ms`, and `result`. A void
operation has a synthetic result of zero, identified by its operation name;
there is no driver return value for that operation. Driver wall/CPU durations
are captured on either side of the direct forwarding call, before metadata is
updated. `metadata_ms` measures device lookup and correlation preparation/update,
including waits for the metadata mutex. The mutex is never held during a driver
call. It excludes the cost of formatting and writing logs; client frame timing
still includes all diagnostic overhead.

Slow submission records contain queue identity/family/index, attempt ID, prior
successful queue submission ID, batch
counts, semaphore counts from examined batch headers, observed command counts,
and the first observed image-copy target's ID/dimensions. These are observations
of selected commands, not proof of an upload-only or render-only submission.
`incomplete_command_coverage=true` is declared in the activation record because
not every Vulkan command or extension is intercepted. Queue wait-idle and
present records also retain the prior successful queue submission ID; this is
the last known submit on that queue, not proof of which GPU command stalled. Secondary command
execution is explicitly uncertain and is not expanded recursively.

Slow wait records contain `fence_count`, `wait_all`, `timeout_ns`, and two bounded
lists. Each fence is represented as:

```
fences=id:generation:origin:origin_id:queue_id:age_ms,...
```

The age is host time since the prior successful submit/acquire returned, measured
at the start of the wait. It is not GPU execution duration. Origins are `submit`,
`acquire`, `created_signaled`, `unattributed`, `reset_unattributed`, or
`truncated_reset_unknown`. A successful/suboptimal acquire has its own attempt
ID. A wait snapshot does not infer which fence caused a wait, particularly for
wait-any or multi-fence calls, and does not infer GPU completion.

Each fence's source submission summary is represented as:

```
fence_submit_evidence=fence_id:batches:commands:transfer_calls:draw_calls:dispatch_calls:render_pass_calls:secondary_calls:first_copy_image_id:width:height:uncertain:missing:submit_wall_ms,...
```

For acquire origins the command evidence is zero. `submit_wall_ms` describes the
prior host API call, not GPU execution. The first image is one observed copy
resource; other images may be used by the batch. Resource creation slow records
also retain image extent/format/usage/mips/layers or memory-allocation bytes/type.
Five-second `VULKAN_COUNTS` records additionally count successful image creations,
2048-square image creations and allocated bytes, with metadata total/maximum. Timing/resource window totals span all devices used
by the reporting thread (`scope=thread_all_devices`); cumulative tracker limits
are for the separately labeled `tracker_device_id`.

Per device capacities are 16 queues, 256 fences, 512 command buffers and 512
images. There are no per-call allocations. Each slow wait describes at most eight
fences. Submission inspection examines at most 64 batch headers and 64 command
references. Omitted/missing records are exposed as `refs_omitted`, `missing_refs`,
`evidence_uncertain`, and cumulative `tracking_overflow_total`,
`tracking_missing_total`, `tracking_truncated_total`. Broad truncated reset/free
operations conservatively invalidate affected tracking rather than retain stale
attribution. Tracking is neither a complete resource census nor a memory-leak
measurement; allocated-byte totals do not subtract frees.

`../../scripts/check-vulkan-trace.sh` verifies retained loader dispatch/lifetime,
actual wrapper results/arguments/failures, fence reuse/reset/acquire, bounded
capacity behavior, multithreaded correlation, and live Vulkan pixel parity plus
2048-square image copying and fence reuse. Twelve real timeout waits verify
unchanged results, wait versus CPU timing, and eight records/four suppressions.
