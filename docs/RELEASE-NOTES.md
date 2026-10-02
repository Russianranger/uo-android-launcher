# UO Memento Mobile 0.2.15

The touch quick menu now says **Back to Launcher Menu**, accurately naming the screen it opens. Display-failure dialog and reconnect guidance use the same wording. The existing return action is unchanged.

Install over the working app after logging out and saving/stopping the session. The application ID and signing certificate remain the same; keep app data, the runtime and imported client.

The 0.2.14 Thor export confirms atlas batching and revision 2 diagnostics are active. After initial world entry, atlas flush maxima stayed below 0.7 ms, while FNA EndDraw still reached 1,365.524 and 1,653.006 ms. Packet handlers contributed separate 163–172 ms pauses. Later gameplay windows were much smoother, but the export contains no action markers to identify individual cold visits or warm repeats.

This is a wording update, not a claimed stutter fix. No client/runtime/presentation performance code or diagnostics are changed. See [the telemetry analysis](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/THOR-0.2.14-ANALYSIS.md) and [short device check](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.15/UO-Memento-Mobile-0.2.15-Instructions.txt).
