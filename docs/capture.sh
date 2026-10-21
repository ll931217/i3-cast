#!/bin/bash
# Regenerate docs/screenshots/*.png from the running desktop. Runs a throwaway
# host with its own config dir, so your config.yaml and theme.yaml stay untouched.
# It types into the launcher, so it checks the launcher has focus first.
set -euo pipefail

cd "$(dirname "$0")/.."
out=docs/screenshots
work=$(mktemp -d)
sock="${XDG_RUNTIME_DIR:?}/x-cast.sock"
cli=bin/x-cast
trap 'kill "$host_pid" 2>/dev/null || true; rm -rf "$work"' EXIT

command -v import >/dev/null && command -v montage >/dev/null || { echo "needs ImageMagick (import, montage)" >&2; exit 1; }
[[ -S $sock ]] && { echo "an x-cast host is already running; stop it first (it owns $sock)" >&2; exit 1; }

# XDG_* stay as they are: fontconfig finds your Nerd Font through them.
export X_CAST_CONFIG_DIR=$work/config
export X_CAST_DATA_DIR=$work/data
mkdir -p "$X_CAST_DATA_DIR"
printf '%s' '[{"expression": "12*12", "answer": "144"}, {"expression": "2^16", "answer": "65536"}, {"expression": "20% of 50", "answer": "10"}]' >"$X_CAST_DATA_DIR/calculator-history.json"
.venv/bin/python host/main.py >/dev/null 2>&1 &
host_pid=$!
for _ in {1..50}; do [[ -S $sock ]] && break; sleep 0.1; done

theme() { # theme <bg> <text> <accent> <selected> <border> <error>
  cat >"$X_CAST_CONFIG_DIR/theme.yaml" <<YAML
colors: {background: "$1", text: "$2", selected_text: "$3", selected_background: "$4", border: "$5", error: "$6"}
YAML
  sleep 0.6
}

focus_ok() { # wait up to 2 s for the launcher to take focus
  local i
  for i in {1..40}; do
    [[ $(xdotool getactivewindow 2>/dev/null) == $(xdotool search --onlyvisible --class '^x-cast$' | head -1) ]] && return 0
    sleep 0.05
  done
  return 1
}

shot() { # shot <file> [query] [keys]
  $cli show; sleep 0.6
  focus_ok || { echo "launcher is not focused; refusing to type" >&2; exit 1; }
  xdotool key ctrl+u
  [[ -n ${2:-} ]] && xdotool type --delay 60 "$2"
  [[ -n ${3:-} ]] && xdotool key "$3"
  sleep 0.6
  local w; w=$(xdotool search --onlyvisible --class '^x-cast$' | head -1)
  import -window "$w" "$1"
  xdotool key ctrl+u; $cli hide; sleep 0.3
}

settings_shot() { # settings_shot <file> <tabs to press>: the settings window, on its nth page
  $cli settings; sleep 1
  local w i; w=$(xdotool search --onlyvisible --name '^x-cast Settings$' | head -1)
  xdotool windowfocus "$w"; sleep 0.4
  [[ $(xdotool getactivewindow) == "$w" ]] || { echo "settings window is not focused; refusing to type" >&2; exit 1; }
  for ((i = 0; i < $2; i++)); do xdotool key Tab; done
  sleep 0.5
  import -window "$w" "$1"
  xdotool key Escape; sleep 0.3
}

theme "#1a1b26" "#c0caf5" "#7aa2f7" "#2a2e45" "#3b4261" "#e06c75"
shot $out/hero.png
shot $out/search.png term
shot $out/actions.png alac ctrl+k
shot $out/fallbacks.png wez
shot $out/calculator.png "sqrt(144) * 3"
settings_shot $out/settings.png 0
settings_shot $out/plugins.png 2

mkdir -p "$work/themes"
i=0
for t in "#1a1b26 #c0caf5 #7aa2f7 #2a2e45 #3b4261 #e06c75" \
         "#282828 #ebdbb2 #fabd2f #3c3836 #504945 #fb4934" \
         "#191724 #e0def4 #c4a7e7 #26233a #403d52 #eb6f92" \
         "#fffcf0 #100f0f #205ea6 #e6e4d9 #cecdc3 #af3029" \
         "#2d353b #d3c6aa #a7c080 #3d484d #475258 #e67e80" \
         "#0d1117 #e6edf3 #58a6ff #1f2937 #30363d #f85149"; do
  theme $t
  shot "$work/themes/$((i++)).png" app
done
montage "$work"/themes/*.png -tile 3x2 -geometry 520x+8+8 -background none "$out/themes.png"
echo "wrote $out"
