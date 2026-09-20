FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libasound2-dev python3
COPY pcm_trasc.c /src/pcm_trasc.c
RUN mkdir /out && cc -O2 -shared -fPIC -DPIC -Wall -Wextra -Werror /src/pcm_trasc.c -lasound -o /out/libasound_module_pcm_trasc.so \
 && strip /out/libasound_module_pcm_trasc.so
