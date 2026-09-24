#!/usr/bin/env python3
"""Quoting and settings helpers for install.sh and uninstall.sh.

The checkout path goes into a systemd unit, a desktop entry and a GNOME
shortcut command. Each has its own quoting rules, and a path with a space,
& or | broke all three. The quoting lives here so the tests can check it
against the real parsers.

Usage:
    install_helper.py check-path PATH
    install_helper.py fill TEMPLATE LAUNCHER
    install_helper.py shortcut-command LAUNCHER
    install_helper.py strv-add LIST ITEM
    install_helper.py strv-remove LIST ITEM
    install_helper.py supports-shell METADATA SHELL_VERSION

LIST is a string array as `gsettings get` prints it. strv-add and
strv-remove print the new array in the form `gsettings set` reads.
"""

import ast
import json
import shlex
import sys

PLACEHOLDER = "CLIPMAN_PATH_PLACEHOLDER/launcher.sh"

# systemd refuses quotes, backslashes and control characters in a program
# path, even quoted, and expands % and $ in a unit file. A desktop entry
# gives % " ` $ and \ special meanings. No one escaping works for all of
# these, so the installer refuses them.
UNSAFE_CHARS = frozenset("%$\"'`\\")


def _is_control(char):
    return ord(char) < 0x20 or ord(char) == 0x7F


def path_problem(path):
    """Return why the installer cannot write path, or "" if it can."""
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return "it is not valid UTF-8"
    bad = sorted({char for char in path if char in UNSAFE_CHARS})
    if any(_is_control(char) for char in path):
        bad.append("a control character (such as a line break)")
    if bad:
        return "it contains " + " ".join(bad)
    return ""


def fill(template, launcher):
    """Return the template with the launcher path written in.

    Double quotes are all that systemd's ExecStart= and a desktop entry's
    Exec= need for a path without UNSAFE_CHARS.
    """
    lines = []
    for line in template.splitlines(keepends=True):
        # The key only means something in the autostart folder, and the
        # installer no longer writes there.
        if line.startswith("X-GNOME-Autostart-enabled="):
            continue
        lines.append(line.replace(PLACEHOLDER, f'"{launcher}"'))
    return "".join(lines)


def gvariant_string(text):
    """Return text as a GVariant string literal."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def shortcut_command(launcher):
    """Return the shortcut command, as a value for `gsettings set`.

    gnome-settings-daemon splits the command like a shell does, so the
    path is shell-quoted. gsettings then needs a GVariant literal: a bare
    value that starts with a quote is not read as a plain string.
    """
    return gvariant_string(f"{shlex.quote(launcher)} toggle")


def parse_strv(text):
    """Return the items of a string array printed by `gsettings get`."""
    text = text.strip()
    if text.startswith("@as "):
        text = text[len("@as "):]
    return [str(item) for item in ast.literal_eval(text)]


def format_strv(items):
    """Return items as a GVariant string-array literal."""
    if not items:
        return "@as []"
    return "[" + ", ".join(gvariant_string(item) for item in items) + "]"


def supports_shell(metadata, shell_version):
    """Return True if the extension metadata lists this Shell's major version."""
    major = shell_version.strip().split(".")[0]
    return major in json.loads(metadata).get("shell-version", [])


def main(argv):
    command, args = argv[0], argv[1:]
    if command == "check-path":
        problem = path_problem(args[0])
        if problem:
            print(f"Error: the install folder cannot be used because {problem}:",
                  file=sys.stderr)
            print(f"  {args[0]}", file=sys.stderr)
            print("Move the clipman folder to a path without those characters,"
                  " then run ./install.sh again.", file=sys.stderr)
            return 1
    elif command == "fill":
        with open(args[0], encoding="utf-8") as template:
            sys.stdout.write(fill(template.read(), args[1]))
    elif command == "shortcut-command":
        print(shortcut_command(args[0]))
    elif command == "strv-add":
        items = parse_strv(args[0])
        if args[1] not in items:
            items.append(args[1])
        print(format_strv(items))
    elif command == "strv-remove":
        print(format_strv([item for item in parse_strv(args[0]) if item != args[1]]))
    elif command == "supports-shell":
        with open(args[0], encoding="utf-8") as metadata:
            return 0 if supports_shell(metadata.read(), args[1]) else 1
    else:
        print(f"install_helper.py: unknown command {command!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
