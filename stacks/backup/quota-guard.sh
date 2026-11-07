#!/bin/sh
# Required preflight for this job. Never print its credential-bearing remote URL.
set -eu
export LC_ALL=C
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
umask 077
fail() { echo "Storage budget guard: $1" >&2; exit 2; }
case "${DUPLICATI__OPERATIONNAME:-}" in
  Restore|List|Test|ListRemote) exit 0 ;; # Recovery/verification must remain possible.
  '') fail 'operation identity missing' ;;
esac
case "${DUPLICATI__REMOTEURL:-}" in
  onedrivev2://QuarkBackups/app-recovery\?*) ;;
  *) fail 'unexpected destination; budget allocation required' ;;
esac
# This fixed source envelope is enforced by Quark's local archive producer too.
# Reserve twice the entire envelope, regardless of the current smaller source.
source=/source/quark-apps
count=0
for file in "$source"/apps-????????T??????Z.tar.gz; do
  [ -e "$file" ] || continue
  [ -f "$file" ] && [ ! -L "$file" ] || fail 'unsafe source artifact'
  size=$(stat -c %s "$file") || fail 'source size unavailable'
  [ "$size" -gt 0 ] && [ "$size" -le 4294967296 ] || fail 'source exceeds 4 GiB generation envelope'
  count=$((count + 1))
done
[ "$count" -gt 0 ] && [ "$count" -le 3 ] || fail 'expected one to three bounded completed archives'
listing=$(mktemp)
trap 'rm -f "$listing"' EXIT HUP INT TERM
# Capture errors privately: backend errors can contain the authenticated URL.
if ! duplicati-backend-tool list "$DUPLICATI__REMOTEURL" >"$listing" 2>&1; then
  fail 'remote inventory failed; refusing writes'
fi
# BackendTool lists human-readable rounded sizes. Overestimate each object by
# one full displayed unit, rather than trusting rounded-down values.
remote=$(awk -F '\t' '
BEGIN { total=0; bad=0; header=0 }
NR==1 { if ($1!="Name" || $2!="Dir/File" || $4!="Size") bad=1; else header=1; next }
{
 if (NF!=4 || $2!="File" || $1!~/^duplicati-/) { bad=1; next }
 n=split($4,p," "); unit=p[2]; factor=0
 if (unit=="B" || unit=="bytes" || unit=="byte") factor=1
 if (unit=="KiB") factor=1024
 if (unit=="MiB") factor=1048576
 if (unit=="GiB") factor=1073741824
 if (unit=="TiB") factor=1099511627776
 if (n!=2 || p[1]!~/^[0-9]+([.][0-9]+)?$/ || factor==0) {bad=1; next}
 total+=(p[1]+1)*factor
}
END { if (bad || !header) exit 1; printf "%.0f\n",total }
' "$listing") || fail 'remote inventory could not be bounded'
# Compaction can temporarily duplicate old remote blocks. Also reserve twice
# the maximum new source and 1 GiB for encrypted volume/index/manifest overhead.
# This intentionally stops well before the nominal allocation becomes full.
projected=$((2 * remote + 2 * 3 * 4294967296 + 1073741824))
[ "$projected" -le 100000000000 ] || fail '100 GB Quark allocation would be exceeded including headroom; existing backups preserved'
echo "Storage budget guard passed: conservative remote bytes=$remote; peak bound=$projected; allocation=100000000000"
