# Build tools for the relay factory image: partition table, ext4 editing without mounting,
# and checksums. Runs natively on arm64 (the R5C's architecture).
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends fdisk e2fsprogs gzip xz-utils coreutils openssl python3 qrencode \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /work
