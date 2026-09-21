# FEX's documented Wine ARM64EC architecture. No x86 Linux runtime or Box64.
# Build on real ARM64; Debian 12 keeps compatibility with our Android bridges.
FROM debian:bookworm-slim AS builder
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git xz-utils cmake ninja-build build-essential python3 \
    bison flex pkg-config libfreetype-dev libfontconfig-dev libx11-dev libxext-dev \
    libxrender-dev libxrandr-dev libxi-dev libxcursor-dev libxfixes-dev libxinerama-dev \
    libxxf86vm-dev libxcomposite-dev libxdamage-dev libvulkan-dev libgl-dev \
    libgnutls28-dev libasound2-dev libpulse-dev libdbus-1-dev libudev-dev libunwind-dev
ARG WINE_COMMIT=a6844d10622fc1a973ec1f22fc4f78a0fcd6cb29
ARG FEX_COMMIT=320c5f18475b0c8a7e99c51a5fdc5b5e35b147ab
RUN curl -fL --retry 3 https://github.com/bylaws/llvm-mingw/releases/download/20250920/llvm-mingw-20250920-ucrt-ubuntu-22.04-aarch64.tar.xz -o /tmp/toolchain.tar.xz \
 && echo 'bce5cc755c613515fd44e1ee9523123d854103abae147571adb645450036274d  /tmp/toolchain.tar.xz' | sha256sum -c - \
 && mkdir /toolchain && tar -xJf /tmp/toolchain.tar.xz --strip-components=1 -C /toolchain
ENV PATH=/toolchain/bin:$PATH
RUN git init /src/wine && cd /src/wine \
 && git remote add origin https://github.com/bylaws/wine.git \
 && git fetch --depth 1 origin "$WINE_COMMIT" && git checkout --detach FETCH_HEAD \
 && mkdir /wine-build && cd /wine-build \
 && /src/wine/configure --prefix=/opt/wine --enable-archs=arm64ec,aarch64,i386 --with-mingw=clang --disable-tests \
      --without-wayland --without-gstreamer --without-cups --without-sane --without-gphoto \
 && make -j4 && make install DESTDIR=/out \
 && cp /wine-build/config.log /out/wine-build-config.log
RUN git init /src/fex && cd /src/fex \
 && git remote add origin https://github.com/FEX-Emu/FEX.git \
 && git fetch --depth 1 origin "$FEX_COMMIT" && git checkout --detach FETCH_HEAD \
 && git submodule update --init --recursive --depth 1 \
 && for arch in arm64ec aarch64; do \
      cmake -S . -B /fex-$arch -GNinja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_TOOLCHAIN_FILE=/src/fex/Data/CMake/toolchain_mingw.cmake \
        -DMINGW_TRIPLE=$arch-w64-mingw32 -DENABLE_LTO=False -DBUILD_TESTING=False \
        -DENABLE_JEMALLOC_GLIBC_ALLOC=False -DTUNE_CPU=none -DTUNE_ARCH=generic \
        -DCMAKE_INSTALL_PREFIX=/opt/wine -DCMAKE_INSTALL_LIBDIR=lib/wine/aarch64-windows \
        -DOVERRIDE_VERSION=FEX-2510; \
      cmake --build /fex-$arch --parallel 4; \
      cp /fex-$arch/Bin/lib*fex.dll /out/opt/wine/lib/wine/aarch64-windows/; \
    done \
 && mkdir -p /sources \
 && tar --exclude=.git -czf /sources/wine-arm64ec-source.tar.gz -C /src wine \
 && tar --exclude=.git -czf /sources/fex-2510-source-with-submodules.tar.gz -C /src fex

FROM debian:bookworm-slim AS runtime
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates python3 tigervnc-standalone-server xauth xfonts-base \
    libgl1-mesa-dri libglx-mesa0 libgl1 libvulkan1 mesa-vulkan-drivers \
    libx11-6 libxext6 libxrender1 libxrandr2 libxi6 libxfixes3 libxcursor1 libxinerama1 libxxf86vm1 libxcomposite1 libxdamage1 \
    libfontconfig1 libfreetype6 fonts-liberation libasound2 libpulse0 libdbus-1-3 libudev1 \
    libgnutls30 libunwind8 procps \
 && apt-get clean && rm -rf /var/lib/apt/lists/* /var/log/* \
 && mkdir -p /client /dotnet /prefix /session /logs /opt/uo-client /tmp
COPY --from=builder /out/opt/wine /opt/wine
RUN printf '{"format":2,"architecture":"arm64","runtime":"fex-arm64ec-1","wine":"10.13-arm64ec","wine_commit":"a6844d10622fc1a973ec1f22fc4f78a0fcd6cb29","fex":"FEX-2510","fex_commit":"320c5f18475b0c8a7e99c51a5fdc5b5e35b147ab"}\n' > /etc/memento-client-runtime.json \
 && dpkg-query -W > /etc/memento-client-packages.txt
CMD ["/bin/bash"]

FROM scratch AS sources
COPY --from=builder /sources/ /
COPY --from=builder /out/wine-build-config.log /
