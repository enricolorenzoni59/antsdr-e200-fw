################################################################################
# libad9361 ported upstream to the libiio v1 API on 2026-10-23.
################################################################################

LIBAD9361_IIO_VERSION = 7d8e7cadd07636cafb7a87d6bcdcc4dd4fcca9b3
LIBAD9361_IIO_SITE = $(call github,analogdevicesinc,libad9361-iio,$(LIBAD9361_IIO_VERSION))
LIBAD9361_IIO_INSTALL_STAGING = YES
LIBAD9361_IIO_LICENSE = LGPL-2.1+
LIBAD9361_IIO_LICENSE_FILES = LICENSE
LIBAD9361_IIO_DEPENDENCIES = libiio
LIBAD9361_IIO_CONF_OPTS = -DBUILD_TESTS=OFF -DWITH_DOC=OFF \
	-DPYTHON_BINDINGS=OFF -DMATLAB_BINDINGS=OFF

$(eval $(cmake-package))
