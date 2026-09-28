# Reuse the recorded userspace builder; pass its exact image ID when building.
ARG BUILDER_IMAGE=e200-userspace:ubuntu26.04-20260923
FROM ${BUILDER_IMAGE}
USER root
RUN apt-get -o Acquire::Check-Valid-Until=false -o APT::Update::Error-Mode=any update \
    && apt-get install -y --no-install-recommends \
      u-boot-tools device-tree-compiler genimage dosfstools mtools \
    && dpkg-query -W > /opt/build-manifest/packages.tsv \
    && rm -rf /var/lib/apt/lists/*
USER 1000:1000
WORKDIR /work
