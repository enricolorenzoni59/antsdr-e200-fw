################################################################################
# Native libiio for the E200 single-RX profile (no v0 ABI shim).
################################################################################

LIBIIO_VERSION = 1.0.0
LIBIIO_SITE = $(call github,analogdevicesinc,libiio,v$(LIBIIO_VERSION))
LIBIIO_INSTALL_STAGING = YES
LIBIIO_LICENSE = LGPL-2.1+
LIBIIO_LICENSE_FILES = COPYING.txt
LIBIIO_DEPENDENCIES = libxml2 zstd host-flex host-bison

# BR2_PACKAGE_LIBIIO_TESTS historically selected the CLI tools. In v1 these
# live under WITH_UTILS; WITH_TESTS now means upstream unit tests.
LIBIIO_CONF_OPTS = \
	-DWITH_LOCAL_BACKEND=ON -DWITH_NETWORK_BACKEND=ON -DWITH_XML_BACKEND=ON \
	-DWITH_LOCAL_CONFIG=ON -DWITH_LOCAL_DMABUF_API=ON -DWITH_LOCAL_MMAP_API=ON \
	-DWITH_USB_BACKEND=OFF -DWITH_SERIAL_BACKEND=OFF \
	-DWITH_IIOD=ON -DWITH_IIOD_V0_COMPAT=ON -DLIBIIO_COMPAT=OFF \
	-DWITH_AIO=OFF -DWITH_IIOD_USBD=OFF -DWITH_IIOD_SERIAL=OFF \
	-DWITH_ZSTD=ON -DWITH_MODULES=OFF -DHAVE_DNS_SD=OFF \
	-DWITH_UTILS=ON -DWITH_TESTS=OFF -DWITH_EXAMPLES=OFF \
	-DPYTHON_BINDINGS=OFF -DCSHARP_BINDINGS=OFF -DWITH_DOC=OFF \
	-DWITH_MAN=OFF -DINSTALL_UDEV_RULE=OFF

define LIBIIO_INSTALL_INIT_SYSV
	$(INSTALL) -D -m 0755 package/libiio/S60iiod \
		$(TARGET_DIR)/etc/init.d/S60iiod
endef

$(eval $(cmake-package))
