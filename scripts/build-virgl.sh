#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
target="${1:-android}"
native="$repo_root/runtime-work/native"
mkdir -p "$native"
download() {
    local url="$1" file="$2" sha="$3"
    if [ ! -f "$file" ]; then curl --fail --location --retry 3 --connect-timeout 20 --max-time 180 "$url" -o "$file"; fi
    echo "$sha  $file" | sha256sum --check
}
download https://gitlab.freedesktop.org/virgl/virglrenderer/-/archive/virglrenderer-1.3.0/virglrenderer-virglrenderer-1.3.0.tar.gz "$native/virglrenderer-1.3.0.tar.gz" 56170f8caa1bb642a2624b649e3bcca095ec2834814e5c308efc8a85a709e4ce
download https://github.com/anholt/libepoxy/archive/refs/tags/1.5.10.tar.gz "$native/libepoxy-1.5.10.tar.gz" a7ced37f4102b745ac86d6a70a9da399cc139ff168ba6b8002b4d8d43c900c15
build="$native/virgl-$target"
mkdir -p "$build/source" "$build/epoxy"
tar --no-same-owner -xzf "$native/virglrenderer-1.3.0.tar.gz" --strip-components=1 -C "$build/source"
tar --no-same-owner -xzf "$native/libepoxy-1.5.10.tar.gz" --strip-components=1 -C "$build/epoxy"
for patch in "$repo_root"/native/virgl-patches/*.patch; do
    # Linux has timespec_get; this compatibility patch is only for older Android.
    if [ "$target" != android ] && [[ "$patch" == *0010-* ]]; then continue; fi
    patch -d "$build/source" -p1 --forward < "$patch"
done
cp "$repo_root/native/trasc_dxt.h" "$build/source/src/vrend/trasc_dxt.h"
cp "$repo_root/native/virgl_main.c" "$build/source/vtest/vtest_main.c"
python3 - "$build/source/vtest/meson.build" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]);s=p.read_text()
s=s.replace('dependencies : [libvirglrenderer_dep, gallium_dep],','dependencies : [libvirglrenderer_dep, gallium_dep, epoxy_dep],')
p.write_text(s)
PY
common=(-Dplatforms=egl -Dvenus=false -Dvideo=false -Dtests=false -Ddefault_library=static -Dbuildtype=release)
if [ "$target" = android ]; then
    llvm="${ANDROID_HOME:?Set ANDROID_HOME}/ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin"
    cat > "$build/cross.ini" <<EOF
[binaries]
c = '$llvm/aarch64-linux-android26-clang'
cpp = '$llvm/aarch64-linux-android26-clang++'
ar = '$llvm/llvm-ar'
strip = '$llvm/llvm-strip'
pkg-config = 'pkg-config'
[host_machine]
system = 'android'
cpu_family = 'aarch64'
cpu = 'armv8-a'
endian = 'little'
[built-in options]
c_args = ['-O2', '-fPIC']
c_link_args = ['-Wl,-z,max-page-size=16384']
EOF
    meson setup "$build/epoxy-build" "$build/epoxy" --cross-file "$build/cross.ini" --prefix "$build/install" --libdir lib -Ddefault_library=static -Dbuildtype=release -Degl=yes -Dglx=no -Dx11=false -Dtests=false
    ninja -C "$build/epoxy-build" install
    export PKG_CONFIG_LIBDIR="$build/install/lib/pkgconfig"
    meson setup "$build/out" "$build/source" --cross-file "$build/cross.ini" "${common[@]}"
else
    meson setup "$build/out" "$build/source" "${common[@]}"
fi
ninja -C "$build/out" -j2
if [ "$target" = android ]; then
    output="$repo_root/app/src/main/jniLibs/arm64-v8a/libvirgl-server.so"
    mkdir -p "$(dirname "$output")"
    cp "$build/out/vtest/virgl_test_server" "$output"
    "$llvm/llvm-strip" "$output"
    "$llvm/llvm-readelf" -h -l -d "$output"
fi
