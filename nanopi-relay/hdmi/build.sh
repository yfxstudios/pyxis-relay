#!/bin/sh
# Builds pyxis-hdmi as a static aarch64 (musl) binary for the NanoPi R5C, on macOS or Linux.
#
# Needs: zig (cross compiler), cmake, meson, ninja, curl, and these sources, which the script
# downloads and checks:
#   Rockchip MPP 1.1.0      (Apache-2.0 / MIT)  hardware video decoder library
#   libdrm 2.4.123          (MIT)               display (KMS) library
#
# usage: ./build.sh [work-dir]     (default: ./build)   -> ./pyxis-hdmi
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
W=${1:-$HERE/build}
mkdir -p "$W/src" "$W/tc" "$W/sysroot"
cd "$W/src"

MPP_URL=https://codeload.github.com/rockchip-linux/mpp/tar.gz/refs/tags/1.1.0
MPP_SHA256=7bb0040f364468ad9abbb71a04553ebc6a5814584e083c2fc9a553783e9656df
DRM_URL=https://dri.freedesktop.org/libdrm/libdrm-2.4.123.tar.xz
DRM_SHA256=a2b98567a149a74b0f50e91e825f9c0315d86e7be9b74394dae8b298caadb79e

fetch() { [ -f "$2" ] || curl -fsSL -o "$2.part" "$1" && { [ -f "$2" ] || mv "$2.part" "$2"; }
          echo "$3  $2" | shasum -a 256 -c - >/dev/null || { echo "checksum mismatch: $2" >&2; rm -f "$2"; exit 1; }; }
fetch "$MPP_URL" mpp-1.1.0.tar.gz "$MPP_SHA256"
fetch "$DRM_URL" libdrm-2.4.123.tar.xz "$DRM_SHA256"
[ -d mpp-1.1.0 ] || tar xzf mpp-1.1.0.tar.gz
[ -d libdrm-2.4.123 ] || tar xJf libdrm-2.4.123.tar.xz

# zig as a cross toolchain
cd "$W/tc"
printf '#!/bin/sh\nexec zig cc -target aarch64-linux-musl "$@"\n' > zcc
printf '#!/bin/sh\nexec zig c++ -target aarch64-linux-musl "$@"\n' > zcxx
printf '#!/bin/sh\nexec zig ar "$@"\n' > zar
printf '#!/bin/sh\nexec zig ranlib "$@"\n' > zranlib
printf '#!/bin/sh\nexec zig ld.lld "$@"\n' > zld
printf '#!/bin/sh\nexit 0\n' > nostrip
chmod +x zcc zcxx zar zranlib zld nostrip
cat > cross.meson <<M
[binaries]
c = '$W/tc/zcc'
cpp = '$W/tc/zcxx'
ar = '$W/tc/zar'
ranlib = '$W/tc/zranlib'
strip = 'true'
pkg-config = 'false'
[host_machine]
system = 'linux'
cpu_family = 'aarch64'
cpu = 'cortex-a55'
endian = 'little'
M
cat > zig.cmake <<M
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER $W/tc/zcc)
set(CMAKE_CXX_COMPILER $W/tc/zcxx)
set(CMAKE_AR $W/tc/zar)
set(CMAKE_RANLIB $W/tc/zranlib)
set(CMAKE_LINKER $W/tc/zld)
set(CMAKE_STRIP $W/tc/nostrip)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_FIND_ROOT_PATH $W/sysroot)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
M

if [ ! -f "$W/sysroot/lib/libdrm.a" ]; then
	(cd "$W/src/libdrm-2.4.123" && meson setup "$W/build-libdrm" --cross-file "$W/tc/cross.meson" --prefix "$W/sysroot" \
		--buildtype=release -Ddefault_library=static -Dintel=disabled -Dradeon=disabled -Damdgpu=disabled \
		-Dnouveau=disabled -Dvmwgfx=disabled -Domap=disabled -Dexynos=disabled -Dfreedreno=disabled -Dtegra=disabled \
		-Dvc4=disabled -Detnaviv=disabled -Dcairo-tests=disabled -Dman-pages=disabled -Dvalgrind=disabled \
		-Dtests=false -Dinstall-test-programs=false -Dudev=false >/dev/null)
	ninja -C "$W/build-libdrm" install >/dev/null
fi
if [ ! -f "$W/sysroot/lib/librockchip_mpp.a" ]; then
	cmake -S "$W/src/mpp-1.1.0" -B "$W/build-mpp" -G Ninja -DCMAKE_TOOLCHAIN_FILE="$W/tc/zig.cmake" \
		-DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$W/sysroot" -DRKPLATFORM=ON -DHAVE_DRM=ON -DBUILD_TEST=OFF >/dev/null
	ninja -C "$W/build-mpp" install >/dev/null
fi

"$W/tc/zcxx" -O2 -std=gnu11 -x c -Wall -Wextra -Wno-unused-parameter \
	-I"$W/sysroot/include" -I"$W/sysroot/include/libdrm" \
	-c "$HERE/pyxis-hdmi.c" -o "$W/pyxis-hdmi.o"
"$W/tc/zcxx" -static -s -o "$HERE/pyxis-hdmi" "$W/pyxis-hdmi.o" \
	"$W/sysroot/lib/librockchip_mpp.a" "$W/sysroot/lib/libdrm.a" -lpthread -lm
echo "Built $HERE/pyxis-hdmi"
