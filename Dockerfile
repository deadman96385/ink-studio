FROM ghcr.io/linuxserver/baseimage-selkies:debiantrixie@sha256:df4a9259e7535526005785202bd08b3b066250a64c65877802b2354fd6a975dd

ARG INKSTITCH_VERSION=3.3.0
ARG INKSTITCH_SHA256=45eea55bf56d9ece417a1d9a40ab859118f43ff772caaf31b42806523dffca9b
ENV TITLE="Ink & Stitch" NO_GAMEPAD=true NO_WEBCAM=true START_DOCKER=false GDK_BACKEND=x11
RUN curl -fL --retry 3 -o /tmp/inkstitch.deb \
      "https://github.com/inkstitch/inkstitch/releases/download/v${INKSTITCH_VERSION}/inkstitch_${INKSTITCH_VERSION}_amd64.deb" \
    && echo "${INKSTITCH_SHA256}  /tmp/inkstitch.deb" | sha256sum -c - \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       inkscape /tmp/inkstitch.deb python3-lxml python3-requests python3-numpy \
    && rm -f /tmp/inkstitch.deb \
    && rm -rf /var/lib/apt/lists/*
COPY root/ /
RUN chmod +x /defaults/autostart /custom-cont-init.d/10-ink-settings \
    && chown -R abc:abc /config \
    && python3 /defaults/install-studio.py \
    && python3 /defaults/touch-patch.py
