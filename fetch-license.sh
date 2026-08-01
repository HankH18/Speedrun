#!/usr/bin/env bash
# Fetch the canonical AGPL-3.0 text into ./LICENSE
#
# The license text is fetched rather than vendored so it is byte-exact.
# A transcribed license is a corrupted legal document.

set -euo pipefail

cd "$(dirname "$0")/.."

URL="https://www.gnu.org/licenses/agpl-3.0.txt"
TMP="$(mktemp)"

echo "Fetching AGPL-3.0 from ${URL} ..."
curl -fsSL "$URL" -o "$TMP"

# Sanity check: the real text is ~34KB and opens with a known line.
BYTES=$(wc -c < "$TMP")
if [ "$BYTES" -lt 30000 ]; then
  echo "ERROR: fetched file is only ${BYTES} bytes — expected ~34000. Not installing." >&2
  rm -f "$TMP"
  exit 1
fi

if ! head -n 5 "$TMP" | grep -q "GNU AFFERO GENERAL PUBLIC LICENSE"; then
  echo "ERROR: fetched file does not look like the AGPL. Not installing." >&2
  rm -f "$TMP"
  exit 1
fi

mv "$TMP" LICENSE
echo "Wrote LICENSE (${BYTES} bytes)."
echo
echo "Note: Anki includes portions under BSD-3-Clause. When reusing those"
echo "components, preserve their original copyright notice and disclaimer."
