"""Execute exact patched renderer/FNA native boundaries under Windows .NET/Wine."""
from pathlib import Path
import os
import subprocess
import sys

work = Path(sys.argv[1]).resolve()
wine = Path(sys.argv[2]).resolve()

def windows(path):
    return "Z:" + str(path).replace("/", "\\")

try:
    for folder, mode in [("original", "disabled"), ("patched", "enabled"), ("patched", "disabled"), ("patched", "failure")]:
        env = os.environ.copy()
        env["MEMENTO_ATLAS_UPLOADS"] = "0" if mode == "disabled" else "1"
        env["DOTNET_STARTUP_HOOKS"] = ";".join(windows(work / "assets" / name) for name in ["Memento.FrameBudget.dll", "Memento.AtlasUploads.dll"])
        shim = work / ("atlas-shim-fail.dll" if mode == "failure" else "atlas-shim.dll")
        result = subprocess.run([str(wine), windows(work / "probe" / "AtlasBoundaryProbe.exe"), windows(work / folder), windows(shim), mode],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", timeout=90)
        print(result.stdout, flush=True)
        assert result.returncode == 0 and f"ATLAS_BOUNDARY_OK actual_fna=true" in result.stdout, (folder, mode, result.returncode)
        assert f"mode={mode}" in result.stdout
        if mode != "failure":
            assert "actual_renderer=true" in result.stdout and "native_overloads=26" in result.stdout
            assert "args_preserved=true refs_preserved=true" in result.stdout and "disposal=true" in result.stdout
        else:
            assert "native_exception=true draw_cleanup=true" in result.stdout
        if mode != "disabled":
            assert "ATLAS_UPLOADS_ACTIVE revision=1" in result.stdout
        else:
            assert "ATLAS_UPLOADS_ACTIVE" not in result.stdout
finally:
    subprocess.run([str(wine.with_name("wineserver")), "-k"], timeout=15, check=False)
    subprocess.run([str(wine.with_name("wineserver")), "-w"], timeout=15, check=False)
