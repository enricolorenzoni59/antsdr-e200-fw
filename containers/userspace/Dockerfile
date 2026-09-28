# Buildroot host tools: immutable Ubuntu base and dated package archive.
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
      bc bison build-essential bzip2 ca-certificates cpio curl debianutils file flex \
      gawk git libncurses-dev libssl-dev patch perl python3 python3-pytest \
      rsync unzip wget xz-utils e2fsprogs qemu-user \
    && mkdir -p /opt/build-manifest \
    && dpkg-query -W > /opt/build-manifest/packages.tsv \
    && cp /etc/apt/sources.list /opt/build-manifest/sources.list \
    && rm -rf /var/lib/apt/lists/*
# Buildroot selects and verifies its own Arm GNU 14.2.rel1 toolchain.
RUN if ! getent passwd 1000 >/dev/null; then useradd --create-home --uid 1000 builder; fi
USER 1000:1000
WORKDIR /work
CMD ["bash"]
