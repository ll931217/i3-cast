#!/bin/bash
# Live check against the running x-cast host on X11. It shows and hides the
# launcher but never types, so nothing lands in other windows.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
cli=bin/x-cast
fail=0
pass() { printf '  ok    %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fail=1; }

echo "doctor"
$cli doctor | sed 's/^/  /' || fail=1

echo "ipc"
[[ $($cli call system.healthPing '{}') == '{"ok":true,"data":null}' ]] && pass "system.healthPing round trip" || bad "system.healthPing round trip"
[[ $($cli call foo.bar) == '{"ok":false,"error":"Unknown method foo.bar"}' ]] && pass "unknown methods are errors" || bad "unknown methods are errors"
$cli call settings.getGeneralSettings | grep -q '"popToRootTimeout"' && pass "settings document loaded" || bad "settings document loaded"

echo "root search"
search() { $cli call rootSearch.search "{\"query\":\"$1\"}"; }
search "" | grep -q '"id":"apps"' && pass "empty root lists applications" || bad "empty root lists applications"
search zzzz-no-match | grep -q '"id":"fallback-commands"' && pass "fallback section for unmatched queries" || bad "fallback section for unmatched queries"
count=$($cli call system.info | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["data"]["candidates"])')
(( count > 0 )) && pass "$count candidates (desktop entries)" || bad "no candidates"

echo "toggle latency (show -> window visible; budget 100 ms, includes xdotool polling)"
visible() { xdotool search --onlyvisible --class '^x-cast$' >/dev/null 2>&1; }
$cli hide; sleep 0.3
worst=0
for i in 1 2 3 4 5; do
  t0=$(date +%s%N); $cli show
  until visible; do :; done
  ms=$(( ($(date +%s%N) - t0) / 1000000 ))
  printf '        run %d: show %3d ms\n' "$i" "$ms"
  (( ms > worst )) && worst=$ms
  $cli hide; sleep 0.3
done
(( worst <= 100 )) && pass "worst show ${worst} ms" || bad "worst show ${worst} ms is over 100 ms"

exit $fail
