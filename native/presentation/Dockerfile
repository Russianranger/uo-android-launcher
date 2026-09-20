FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libx11-dev libxext-dev libxfixes-dev libxdamage-dev libxtst-dev && rm -rf /var/lib/apt/lists/*
COPY frame.h transfer.h x11-frame-bridge.c input.h /src/
RUN mkdir /out && cc -std=c11 -O2 -Wall -Wextra -Werror /src/x11-frame-bridge.c -Wl,-Bstatic -lXdamage -lXtst -Wl,-Bdynamic -lX11 -lXext -lXfixes -o /out/x11-frame-bridge

RUN cat /usr/share/doc/libxdamage-dev/copyright /usr/share/doc/libxtst-dev/copyright > /out/presentation-notices.txt
