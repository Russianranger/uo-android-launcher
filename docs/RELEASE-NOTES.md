# UO Memento Mobile 0.2.14

This update batches adjacent first-use terrain and animation atlas uploads on the supported Turnip client. It reduces separate GPU upload commands while preserving sprite pixels and upload order. Install over your working app after logging out and saving/stopping the session; keep app data and the installed runtime/client.

The 0.2.13 device logs show repeated 100–540 ms FNA presentation waits while Android copy/post remain below one millisecond and warm visits are smooth. Individual sprite uploads are a concrete graphics cost to reduce; these logs do not prove they explain every pause. CPU decoding, expensive item handlers and other driver waits remain possible.

Queued sprite pixels are copied unchanged. Only their newly reserved one-pixel borders are initialized to transparent, allowing padded reservations to merge with no holes or changes to old sprites. Queued data is limited to 4 MiB. Uploads commit before native drawing, readback, texture changes, presentation and disposal, including the managed disposal entry before its texture handle is cleared. There is no background graphics thread or full atlas shadow. Exact FNA/Renderer patches preserve identities, original native entry points and unrelated methods/resources. Verified originals support restoration; unknown upstream files remain untouched.

The existing Surface fix, changed-region delivery, packet budget, music cache, controller and launcher features remain. Keep 60 FPS, Turnip, Smooth world loading ON, and Render trace / Managed diagnostics OFF. Prior timings remain; new atlas summaries measure upload reduction.

Follow the [device checklist](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.14/UO-Memento-Mobile-0.2.14-Instructions.txt): visit the same area/interior, repeat without restarting, note pauses or visual defects, then export Journal logs. Automated checks establish pixels, ordering, migration and upload reduction. Actual Thor performance still requires this comparison.
