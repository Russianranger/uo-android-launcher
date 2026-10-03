"""Checksum-pinned client dependencies needed to JIT all resource boundaries.

Test-only downloads from the same public Memento package as the client fixture;
none of these complete vendor assemblies is committed or shipped in the APK.
"""
from pathlib import Path
import importlib.util
import sys

spec = importlib.util.spec_from_file_location('music_fixture', Path(__file__).with_name('fetch-music-fixture.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.FILES = {
    'FontStashSharp.FNA.dll': 'de3b78df807a244398df36ea2425986d8796389ca446de97c6c5131cd20ffb53',
    'FontStashSharp.Base.dll': '10ae9579608962d42f7bbc1030f86c6df66d07ecd87cea7011716a93957e5f13',
    'StbTrueTypeSharp.dll': 'b0b5bce1d3d8664f0c812dac00595504c21ead1ec36878a4c95eb755746f7afa',
    'StbImageSharp.dll': '5cd5e5b038998360d597bd2a5e3c57f932d507c038a186bb5675e9ac9fcdf661',
    'SixLabors.Fonts.dll': 'e661c6ac204861eab86e45eb8736988491170da9a8f5d040d380cf6b9cd395ff',
}
fixture.fetch(Path(sys.argv[1] if len(sys.argv) > 1 else 'runtime-work/resource-fixture/patched'))
