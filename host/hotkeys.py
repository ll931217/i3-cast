"""Writes i3 key bindings for commands, from `hotkeys:` in config.yaml.

    hotkeys:
      "app:firefox.desktop": "$mod+Shift+f"
      "script-commands:/home/me/.config/x-cast/script-commands/hello.sh": "$mod+F9"

    hotkeys.py CLI_PATH CONFIG_YAML   prints the i3 config lines
"""
import re
import shlex
import sys

import yaml

KEY = re.compile(r"^[A-Za-z0-9_$+\- ]+$")


def bindings(hotkeys, cli):
    """i3 lines for {commandId: key}. Raises ValueError on a key i3 would misread."""
    lines = []
    for command_id, key in sorted((hotkeys or {}).items()):
        key = str(key).strip()
        if not KEY.match(key) or key.endswith("+"):
            raise ValueError("bad key %r for %s" % (key, command_id))
        lines.append("bindsym %s exec --no-startup-id %s run %s" % (key, shlex.quote(cli), shlex.quote(str(command_id))))
    return lines


if __name__ == "__main__":
    cli, config = sys.argv[1:3]
    try:
        with open(config) as f:
            data = yaml.safe_load(f) or {}
        print("\n".join(["# Written by `x-cast setup hotkeys` from config.yaml. Edit that, not this."] + bindings(data.get("hotkeys"), cli)))
    except (OSError, ValueError, yaml.YAMLError) as e:
        sys.exit("x-cast: %s" % e)
