#!/bin/sh
# Compile affected objects only. Dependencies are unpacked locally, not installed.
set -eu
audit_source=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
audit_workspace=$(dirname -- "$audit_source")
audit_validation="$audit_workspace/lpi4a-audit-validation"
audit_deps="$audit_validation/deps/root/usr"
export PATH="$audit_deps/bin:/tmp/lpi4a-package-deps/root/usr/bin:$PATH"
export LD_LIBRARY_PATH="$audit_deps/lib/riscv64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CPATH="/tmp/lpi4a-package-deps/root/usr/include${CPATH:+:$CPATH}"
export LIBRARY_PATH="/tmp/lpi4a-package-deps/root/usr/lib/riscv64-linux-gnu${LIBRARY_PATH:+:$LIBRARY_PATH}"
export M4="$audit_deps/bin/m4"
export BISON_PKGDATADIR="$audit_deps/share/bison"
make -C "$audit_source" O="$audit_workspace/lpi4a-audit-kbuild" ARCH=riscv -j4 \
    drivers/tty/serial/8250/8250_dma.o \
    drivers/tty/serial/8250/8250_port.o \
    drivers/dma/dw-axi-dmac/dw-axi-dmac-platform.o \
    drivers/i2c/busses/i2c-designware-platdrv.o
