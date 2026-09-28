#!/bin/sh
set -eu
# UART provisions /root/.ssh/authorized_keys for RAM development. Production
# provisioning/persistent SSH identity is a separate release gate.
target=$1
[ "$target" != / ] || exit 1
# The base image has no scheduled jobs; do not start an unused cron daemon.
rm -f "$target/etc/init.d/S50crond"
install -d -m 0700 "$target/root/.ssh"
printf '%s\n' 'independent E200 development build' >"$target/etc/e200-build-status"
# Never add vendor flash-updater, JFFS2 automount or SD autorun hooks.
