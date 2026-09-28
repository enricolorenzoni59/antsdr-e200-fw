# Preserve the recorded builder; Buildroot 2026.08 rejects this Ubuntu
# snapshot's uutils install implementation. Select its installed GNU binary.
ARG BASE_IMAGE=sha256:6b92a46a2581e2fcab967983ec4160c42607d3c04c4759bf63a45212a5c7b351
FROM ${BASE_IMAGE}
USER root
RUN test -x /usr/bin/gnuinstall \
    && update-alternatives --install /usr/bin/install install /usr/bin/gnuinstall 100 \
    && install --version > /opt/build-manifest/install.txt
USER 1000:1000
WORKDIR /work
