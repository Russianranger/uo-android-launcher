# Match the installed runtime's glibc; the server retains Wine 10's protocol.
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential bison flex pkg-config patch xz-utils \
    && rm -rf /var/lib/apt/lists/*
COPY wine-10.0.tar.xz /src/wine-10.0.tar.xz
COPY 0002-translated-exit-grace.patch /src/exit-grace.patch
RUN cd /src && tar -xJf wine-10.0.tar.xz \
    && patch -d wine-10.0 -p1 < exit-grace.patch \
    && mkdir build && cd build \
    && ../wine-10.0/configure --enable-win64 --without-mingw --disable-tests \
       --without-x --without-wayland --without-freetype --without-vulkan \
    && make -j2 server/wineserver && strip server/wineserver
