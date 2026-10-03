# UO Memento Mobile 0.2.16

Adds an opt-in **Cold-load timing (Thor test)** option to investigate the remaining first-visit outdoor and interior stutters. It records bounded individual long frames with packet, atlas, allocation/GC and CPU evidence, plus passive FNA and native Vulkan resource/shader/pipeline/submission/presentation/wait timing. The touch menu gains **Mark test phase** for a cold route, first interior entry, exit/re-entry and outdoor retrace. Android presentation tails and available external I/O/scheduling counters are included in the support ZIP.

The option defaults off. Keep the existing Turnip / Native Surface, 60 FPS and other settings; leave Smooth world loading on. Turn the option off and relaunch after the test to restore the existing atlas FNA build. The 0.2.13 summaries and 0.2.14 batching are retained. This is a diagnostic release with no new performance optimization and no claim that the cold stutters are solved.

Install over the working app after logging out and saving/stopping the session. Application ID, signing certificate, installed Wine/FEX runtime, changed-region delivery, Surface geometry caching, audio, server, controls and viewport behavior are retained. **Back to Launcher Menu** remains the quick-menu return label.

See the [Thor test procedure](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.16/UO-Memento-Mobile-0.2.16-Instructions.txt) and [diagnostic record guide](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/DIAGNOSTICS-0.2.16.md). Analyze the resulting logs before choosing the next measured optimization.
