# Separate compiler experiment; preserve the proven GCC 7.3 kernel builder.
ARG BASE_IMAGE=sha256:1a03eacee44006912ed09b19729e2a9cdd9c2923c1ced0d72e491d00a311570a
FROM ${BASE_IMAGE}
USER root
# Reuse the base's immutable 20260923T000000Z Ubuntu package snapshot.
RUN apt-get -o Acquire::Check-Valid-Until=false -o APT::Update::Error-Mode=any update \
    && apt-get install -y --no-install-recommends gcc-15-arm-linux-gnueabihf binutils-arm-linux-gnueabihf \
    && mkdir -p /opt/gcc15/bin \
    && ln -s /usr/bin/arm-linux-gnueabihf-gcc-15 /opt/gcc15/bin/arm-linux-gnueabihf-gcc \
    && for tool in ar as ld nm objcopy objdump ranlib readelf size strings strip; do \
         ln -s /usr/bin/arm-linux-gnueabihf-$tool /opt/gcc15/bin/arm-linux-gnueabihf-$tool; done \
    && arm-linux-gnueabihf-gcc-15 --version > /opt/build-manifest/compiler-gcc15.txt \
    && dpkg-query -W > /opt/build-manifest/packages-gcc15.tsv \
    && rm -rf /var/lib/apt/lists/*
ENV E200_CROSS_COMPILE=/opt/gcc15/bin/arm-linux-gnueabihf-
USER 1000:1000
WORKDIR /work
