# Translating clipman

clipman uses GNU gettext for translations. All user-visible strings
in the UI (`clipman/window.py`) are wrapped with `_()` and collected
into a single translation template at `po/clipman.pot` (currently 70
translatable strings).

This guide covers two audiences: translators adding a new language,
and contributors who added new translatable strings in code. The
source-side conventions are summarised in `CONTRIBUTING.md` under
*i18n (Translations)* — this document expands on the full workflow.

## Adding a new language

1. Confirm the language isn't already in `po/` (look for an existing
   `po/<lang>.po`). At the time of writing only `po/clipman.pot` and
   `po/POTFILES.in` exist — no languages have been translated yet,
   so the first translator for any locale starts from the template.
2. Generate a `.po` file from the template:

   ```bash
   cd po
   msginit --locale=<lang> --input=clipman.pot --output-file=<lang>.po
   ```

   where `<lang>` is the IETF tag like `de`, `pt_BR`, `zh_CN`.
3. Translate the `msgstr` entries with your editor of choice
   (Poedit, Lokalize, or plain text — `.po` is a plain-text format).
   Keep placeholders like `{count}` and `{n}` exactly as written;
   they are filled in at runtime by Python's `.format()`.
4. Validate:

   ```bash
   msgfmt --check --statistics po/<lang>.po -o /dev/null
   ```

   `--check` enforces format-string parity with the original `msgid`,
   so any stray placeholder mismatch is caught here.
5. Open a PR adding `po/<lang>.po` only. Mention which language and
   how to verify in the PR description.

## Regenerating the translation template

When you add a new `_("...")` call in code, regenerate the POT so
translators see the new string:

```bash
xgettext \
    --from-code=UTF-8 \
    --language=Python \
    --keyword=_ \
    --output=po/clipman.pot \
    --files-from=po/POTFILES.in
```

`po/POTFILES.in` currently lists `clipman/window.py` — the only file
holding translatable strings today. Confirm the keyword (`_`) and the
files-from list match what `po/POTFILES.in` expects before running.
Commit the regenerated `clipman.pot` together with the code change
that introduced the new strings — the POT diff is the translator's
signal that work is needed.

## Source-side conventions

- Import `_` from the `clipman` package: `from clipman import _`.
  The gettext bootstrap lives in `clipman/__init__.py`, which binds
  the `clipman` text domain to a `locale/` directory next to the
  package root.
- Wrap every user-visible string: `label.set_text(_("Search..."))`.
- Use `.format(...)` for strings with variables — keep the
  placeholders inside the translatable string:
  `_("{count} items").format(count=total)`.
- Do not concatenate translated fragments; one full sentence per
  `_()` call so translators get context.
- `po/POTFILES.in` lists every file the extractor scans. Add new
  source files there when they grow `_()` calls.

## Runtime install paths

The gettext bootstrap in `clipman/__init__.py` points at a `locale/`
directory next to the package root:

```python
LOCALE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locale"
)
gettext.bindtextdomain("clipman", LOCALE_DIR)
gettext.textdomain("clipman")
```

At the moment **no part of the build actually compiles `.po` files
into `.mo` files or installs them into that `locale/` directory**.
`install.sh` does not run `msgfmt`; `snap/snapcraft.yaml`,
`flathub/io.github.MohammedEl_sayedAhmed.Clipman.json`, `aur/PKGBUILD`,
and `pyproject.toml` likewise have no locale install step. Until that
gap is closed, `_()` is effectively a passthrough at runtime — the
strings are wrapped and the POT is maintained, but end users will see
English regardless of `LANG`.

Closing the gap will require, at minimum:

- A `msgfmt` step that compiles each `po/<lang>.po` into
  `locale/<lang>/LC_MESSAGES/clipman.mo` during install.
- Mirroring that step in `install.sh` and in each packaging manifest
  (snap, flatpak, AUR) so distributed builds carry the compiled
  catalogues.

Contributions that wire this up are welcome — once it lands, this
section will be updated with the concrete commands.

## Where to ask

- Specific phrasing question on a string: open a GitHub Discussion in
  the [project's Discussions](https://github.com/MohammedEl-sayedAhmed/clipman/discussions).
- Tooling problem with `xgettext`/`msginit`/`msgfmt`: open an issue
  with the `kind:bug` template; include your gettext version
  (`xgettext --version | head -1`).
