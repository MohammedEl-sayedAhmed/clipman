# Translating clipman

clipman uses GNU gettext for translations. User-visible strings are
wrapped with `_()` and collected into a single template at
`po/clipman.pot`. The files scanned are listed in `po/POTFILES.in`:
`app.py`, `edge_states.py`, `preferences.py`, `snippets_dialog.py` and
`window.py`. The template currently holds 226 strings.

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

   `--check` catches broken `.po` syntax. It does **not** catch a
   mistyped placeholder yet: the template does not mark `{name}`
   placeholders as format strings, so check each one by eye. A wrong
   placeholder makes that dialog fail at runtime.
   [#321](https://github.com/MohammedEl-sayedAhmed/clipman/issues/321)
   tracks fixing this before the first translation lands.
5. Open a PR adding `po/<lang>.po` only. Mention which language and
   how to verify in the PR description.

## Regenerating the translation template

When you add a new `_("...")` call in code, regenerate the template so
translators see the new string:

```bash
scripts/dev.sh i18n
```

That runs `scripts/gen-pot.py`, which reads `po/POTFILES.in` and
extracts with `pygettext`. `pygettext` ships with CPython, so no extra
system package is needed. The header is rewritten afterwards, so the
template is byte-identical between runs when the sources have not
changed, and the diff shows only real string changes. The same command
then compiles any `po/*.po` into `locale/`, which needs `msgfmt` from
the `gettext` package (`scripts/deps.sh --i18n --install`).

Add the file to `po/POTFILES.in` when a module grows its first `_()`
call, and commit the regenerated `clipman.pot` together with the code
change — the template diff is the translator's signal that work is
needed.

## Source-side conventions

- Import the translation function straight from the standard library:
  `from gettext import gettext as _`. Do **not** write
  `from clipman import _`: that points a submodule back at the package
  root, which CodeQL reports as `py/cyclic-import` and the security
  gate fails the pull request. `clipman/__init__.py` has already bound
  the text domain by the time any submodule loads, so the plain import
  picks up the right catalogue.
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

`install.sh` and `scripts/dev.sh i18n` both compile every
`po/<lang>.po` into `locale/<lang>/LC_MESSAGES/clipman.mo`, so a source
checkout picks up translations. Both steps are best effort: with no
`.po` files, or without `msgfmt` installed, they print a line and carry
on, and the app stays in English.

Still open: the packaged builds. `snap/snapcraft.yaml`, `aur/PKGBUILD`
and `pyproject.toml` have no locale install step, so snap, AUR and pip
users would see English even once a language is contributed. That is
worth wiring up with the first `.po` file, not before — there is
nothing to ship yet.

## Where to ask

- Specific phrasing question on a string: open a GitHub Discussion in
  the [project's Discussions](https://github.com/MohammedEl-sayedAhmed/clipman/discussions).
- Tooling problem with `msginit`/`msgfmt`: open an issue with the
  bug template; include your gettext version
  (`msgfmt --version | head -1`).
