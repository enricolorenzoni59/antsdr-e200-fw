# Kernel-only builder: immutable base, dated package archive and verified compiler.
FROM ubuntu@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78
# Bootstrap HTTPS trust from a versioned package authenticated by Ubuntu APT metadata.
ADD https://archive.ubuntu.com/ubuntu/pool/main/c/ca-certificates/ca-certificates_20260601~22.04.1_all.deb /tmp/ca-certificates.deb
RUN echo '6e8cdcc8c86103acd4fc14649eac62ff2037108389074a7b167567af33c32245  /tmp/ca-certificates.deb' | sha256sum -c - \
    && dpkg-deb -x /tmp/ca-certificates.deb /tmp/ca-bootstrap \
    && mkdir -p /etc/ssl/certs \
    && cat /tmp/ca-bootstrap/usr/share/ca-certificates/mozilla/*.crt > /etc/ssl/certs/ca-certificates.crt \
    && printf 'Acquire::https::CaInfo "/etc/ssl/certs/ca-certificates.crt";\n' > /etc/apt/apt.conf.d/99e200-ca-bootstrap \
    && rm -rf /tmp/ca-bootstrap /tmp/ca-certificates.deb
ARG UBUNTU_SNAPSHOT=20260923T000000Z
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC
RUN rm -f /etc/apt/sources.list.d/ubuntu.sources \
    && printf 'deb https://snapshot.ubuntu.com/ubuntu/%s resolute main universe\ndeb https://snapshot.ubuntu.com/ubuntu/%s resolute-updates main universe\ndeb https://snapshot.ubuntu.com/ubuntu/%s resolute-security main universe\n' \
      "$UBUNTU_SNAPSHOT" "$UBUNTU_SNAPSHOT" "$UBUNTU_SNAPSHOT" > /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false -o APT::Update::Error-Mode=any update \
    && apt-get install -y --no-install-recommends \
      bc bison build-essential ca-certificates curl flex git libssl-dev libmpc-dev zlib1g \
      python3 python3-pytest u-boot-tools xz-utils \
    && mkdir -p /opt/build-manifest \
    && dpkg-query -W > /opt/build-manifest/packages.tsv \
    && cp /etc/apt/sources.list /opt/build-manifest/sources.list \
    && rm -rf /var/lib/apt/lists/*
# Hash from the pinned vendor Buildroot toolchain-external-linaro-arm.hash.
RUN curl --fail --location --retry 3 \
      https://sources.buildroot.net/toolchain-external-linaro-arm/gcc-linaro-7.3.1-2018.05-x86_64_arm-linux-gnueabihf.tar.xz \
      -o /tmp/compiler.tar.xz \
    && echo '7248bf105d0d468887a9b8a7120bb281ac8ad0223d9cb3d00dc7c2d498485d91  /tmp/compiler.tar.xz' | sha256sum -c - \
    && mkdir /opt/toolchain \
    && tar -xJf /tmp/compiler.tar.xz --strip-components=1 -C /opt/toolchain \
    && rm /tmp/compiler.tar.xz \
    && /opt/toolchain/bin/arm-linux-gnueabihf-gcc --version > /opt/build-manifest/compiler.txt
# Official Ubuntu images may already provide UID 1000.
RUN if ! getent passwd 1000 >/dev/null; then useradd --create-home --uid 1000 builder; fi
ENV E200_CROSS_COMPILE=/opt/toolchain/bin/arm-linux-gnueabihf-
USER 1000:1000
WORKDIR /work
CMD ["bash"]
