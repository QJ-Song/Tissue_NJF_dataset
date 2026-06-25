#!/usr/bin/env bash
set -u

TARGET="/tmp/fuse"

echo "Checking stale mount at ${TARGET}..."
if ! mount | grep -F " ${TARGET} " >/dev/null 2>&1; then
    echo "No active mount entry found for ${TARGET}."
else
    mount | grep -F " ${TARGET} " || true
fi

echo
echo "Testing df..."
if df -l -x tmpfs -x efivarfs -x vfat --output=target >/tmp/isaacsim-df-check.txt 2>/tmp/isaacsim-df-check.err; then
    echo "df is already healthy."
    cat /tmp/isaacsim-df-check.txt
    exit 0
fi

echo "df failed:"
cat /tmp/isaacsim-df-check.err
echo

if command -v fusermount3 >/dev/null 2>&1; then
    echo "Trying fusermount3 -u ${TARGET}..."
    fusermount3 -u "${TARGET}" || true
elif command -v fusermount >/dev/null 2>&1; then
    echo "Trying fusermount -u ${TARGET}..."
    fusermount -u "${TARGET}" || true
else
    echo "No fusermount command found."
fi

echo
echo "Re-testing df..."
if df -l -x tmpfs -x efivarfs -x vfat --output=target >/tmp/isaacsim-df-check.txt 2>/tmp/isaacsim-df-check.err; then
    echo "df is healthy after unmount."
    cat /tmp/isaacsim-df-check.txt
    exit 0
fi

echo "df still failed:"
cat /tmp/isaacsim-df-check.err
echo
echo "If the error still mentions ${TARGET}, run this command manually in the remote terminal:"
echo "sudo umount -l ${TARGET}"
exit 1
