package io.github.russianranger.trasc;

/** One deployment list shared by Android startup and the packaged-APK check. */
final class ClientRuntimeAssets {
    private ClientRuntimeAssets() {}
    static final String[] FILES={
        "Memento.Diagnostics.dll",
        "uo_client_runner.py", "uo_content.py", "client_presentation.py",
        "client_audio.py", "client_health.py", "client_graphics.py", "log_retention.py",
        "graphics_probe.py", "runtime_probe.py",
        "x11-frame-bridge", "presentation-bundle.json",
        "libasound_module_pcm_trasc.so", "audio-bundle.json",
        "turnip-26.0.0.so", "libXcomposite.so.1", "SDL3-3.4.16-x64.dll",
        "dxvk-d3d11-x64.dll", "dxvk-dxgi-x64.dll",
        "dxvk-d3d11-x86.dll", "dxvk-dxgi-x86.dll"
    };
}
