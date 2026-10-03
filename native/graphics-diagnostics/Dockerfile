FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libvulkan-dev && rm -rf /var/lib/apt/lists/*
COPY layer.c commands.h /src/
RUN mkdir /out && cc -std=c11 -shared -fPIC -O2 -Wall -Wextra -Werror -Wl,-Bsymbolic /src/layer.c -pthread -o /out/libmemento-vulkan-trace.so
RUN cp /usr/share/doc/libvulkan-dev/copyright /out/vulkan-trace-notices.txt
