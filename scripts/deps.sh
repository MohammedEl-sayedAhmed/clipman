#!/usr/bin/env bash
#
# System package manifest for clipman: source it for the clipman_deps_*
# functions, or run it as a CLI (see --help).
# shellcheck disable=SC2034  # arrays are read through a nameref

# Package lists: runtime (app), test (Xvfb + build headers), lint (shellcheck)

CLIPMAN_DEPS_RUNTIME_APT=(
    wl-clipboard wtype python3-gi python3-dbus
    gir1.2-gtk-4.0 gir1.2-adw-1 libadwaita-1-0
)
CLIPMAN_DEPS_RUNTIME_DNF=(
    wl-clipboard wtype python3-gobject python3-dbus gtk4 libadwaita
)
CLIPMAN_DEPS_RUNTIME_PACMAN=(
    wl-clipboard wtype python-gobject python-dbus gtk4 libadwaita
)

CLIPMAN_DEPS_TEST_APT=(
    xvfb python3-venv python3-dev pkg-config
    libcairo2-dev libgirepository-2.0-dev libdbus-1-dev libglib2.0-dev
)
CLIPMAN_DEPS_TEST_DNF=(
    xorg-x11-server-Xvfb python3-devel pkgconf-pkg-config
    cairo-devel cairo-gobject-devel gobject-introspection-devel
    dbus-devel glib2-devel
)
CLIPMAN_DEPS_TEST_PACMAN=(
    xorg-server-xvfb python-pip pkgconf cairo gobject-introspection dbus glib2
)

CLIPMAN_DEPS_LINT_APT=(shellcheck)
CLIPMAN_DEPS_LINT_DNF=(ShellCheck)
CLIPMAN_DEPS_LINT_PACMAN=(shellcheck)

# primary=fallback, consulted with `apt-cache policy` for the apt backend.
declare -A CLIPMAN_DEPS_ALTERNATIVES_APT=(
    [libgirepository-2.0-dev]=libgirepository1.0-dev
)

# Helpers

_clipman_deps_log() {
    printf 'deps: %s\n' "$*" >&2
}

_clipman_deps_have_tty() {
    [ -t 0 ]
}

# Whether the assume-yes flag should be passed to the package manager.
_clipman_deps_assume_yes() {
    if [ "${CLIPMAN_DEPS_YES:-0}" = "1" ]; then
        return 0
    fi
    if [ "${CI:-}" = "true" ] && ! _clipman_deps_have_tty; then
        return 0
    fi
    return 1
}

#######################################
# Detect the host's package manager.
# Outputs:
#   Writes apt, dnf or pacman to stdout.
# Returns:
#   1 when none is present.
#######################################
clipman_deps_detect_pm() {
    if command -v apt-get >/dev/null 2>&1; then
        echo apt
    elif command -v dnf >/dev/null 2>&1; then
        echo dnf
    elif command -v pacman >/dev/null 2>&1; then
        echo pacman
    else
        return 1
    fi
}

# Validate/normalize a package-manager name; echo it back.
_clipman_deps_pm() {
    local pm="${1:-}"
    if [ -z "$pm" ]; then
        if ! pm=$(clipman_deps_detect_pm); then
            _clipman_deps_log "no supported package manager found (apt-get, dnf or pacman)"
            return 1
        fi
    fi
    case "$pm" in
        apt|dnf|pacman) echo "$pm" ;;
        *)
            _clipman_deps_log "unknown package manager '$pm' (expected apt, dnf or pacman)"
            return 1
            ;;
    esac
}

# Echo the raw (unresolved) list for one base set and one pm.
_clipman_deps_raw_list() {
    local set="$1" pm="$2" var
    var="CLIPMAN_DEPS_$(printf '%s' "$set" | tr '[:lower:]' '[:upper:]')_$(printf '%s' "$pm" | tr '[:lower:]' '[:upper:]')"
    local -n _ref="$var"
    printf '%s\n' "${_ref[@]}"
}

# Expand set aliases (dev -> runtime test lint); one set name per line.
_clipman_deps_expand_sets() {
    local set
    for set in "$@"; do
        case "$set" in
            runtime|test|lint) echo "$set" ;;
            dev) printf '%s\n' runtime test lint ;;
            *)
                _clipman_deps_log "unknown set '$set' (expected runtime, test, lint or dev)"
                return 1
                ;;
        esac
    done
}

# apt only: does the local index know a candidate? Without apt-cache on the
# host (e.g. `--pm apt --print` elsewhere) we cannot tell, so assume yes.
_clipman_deps_apt_has_candidate() {
    local pkg="$1" candidate
    if ! command -v apt-cache >/dev/null 2>&1; then
        return 0
    fi
    candidate=$(apt-cache policy "$pkg" 2>/dev/null | awk '/^ *Candidate:/ { print $2; exit }')
    [ -n "$candidate" ] && [ "$candidate" != "(none)" ]
}

# Apply the alternatives map to one package name and echo the result.
_clipman_deps_resolve() {
    local pm="$1" pkg="$2"
    if [ "$pm" = "apt" ] && [ -n "${CLIPMAN_DEPS_ALTERNATIVES_APT[$pkg]:-}" ]; then
        if ! _clipman_deps_apt_has_candidate "$pkg"; then
            pkg="${CLIPMAN_DEPS_ALTERNATIVES_APT[$pkg]}"
        fi
    fi
    echo "$pkg"
}

# Union of the resolved lists for several sets, one package per line, in
# first-seen order and de-duplicated.
_clipman_deps_union() {
    local pm="$1"
    shift
    local sets set pkg
    sets=$(_clipman_deps_expand_sets "$@") || return 1
    declare -A seen=()
    for set in $sets; do
        while IFS= read -r pkg; do
            [ -n "$pkg" ] || continue
            pkg=$(_clipman_deps_resolve "$pm" "$pkg")
            if [ -z "${seen[$pkg]:-}" ]; then
                seen[$pkg]=1
                echo "$pkg"
            fi
        done < <(_clipman_deps_raw_list "$set" "$pm")
    done
}

# Is one package installed? Uses the pm's own database.
_clipman_deps_installed() {
    local pm="$1" pkg="$2"
    case "$pm" in
        apt)
            [ "$(dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null)" = "install ok installed" ]
            ;;
        dnf)
            rpm -q "$pkg" >/dev/null 2>&1
            ;;
        pacman)
            pacman -Qi "$pkg" >/dev/null 2>&1
            ;;
    esac
}

# Missing packages across several sets, one per line.
_clipman_deps_missing_lines() {
    local pm="$1"
    shift
    local pkgs pkg
    pkgs=$(_clipman_deps_union "$pm" "$@") || return 1
    for pkg in $pkgs; do
        if ! _clipman_deps_installed "$pm" "$pkg"; then
            echo "$pkg"
        fi
    done
}

# Root, passwordless sudo, or a TTY for sudo's prompt; otherwise return 3 so
# the caller prints the command instead of hanging or hitting "sudo: not found".
_clipman_deps_run_privileged() {
    if [ "$(id -u)" = "0" ]; then
        "$@"
    elif ! command -v sudo >/dev/null 2>&1; then
        return 3
    elif sudo -n true 2>/dev/null || _clipman_deps_have_tty; then
        sudo "$@"
    else
        return 3
    fi
}

# Public API

#######################################
# Resolve one set's package list for a package manager.
# Arguments:
#   set  runtime, test, lint or dev
#   pm   apt, dnf or pacman (default: detected)
# Outputs:
#   Writes the space-separated list to stdout.
# Returns:
#   1 on an unknown set or package manager.
#######################################
clipman_deps_list() {
    local set="${1:-}" pm
    if [ -z "$set" ]; then
        _clipman_deps_log "usage: clipman_deps_list <set> [pm]"
        return 1
    fi
    pm=$(_clipman_deps_pm "${2:-}") || return 1
    local lines
    lines=$(_clipman_deps_union "$pm" "$set") || return 1
    # shellcheck disable=SC2086  # word-splitting the newline list is intended
    echo $lines
}

#######################################
# List the packages of one set that are not installed.
# Arguments:
#   set  runtime, test, lint or dev
#   pm   apt, dnf or pacman (default: detected)
# Outputs:
#   Writes the missing packages, space-separated, to stdout.
# Returns:
#   0 when nothing is missing, 1 otherwise.
#######################################
clipman_deps_missing() {
    local set="${1:-}" pm
    if [ -z "$set" ]; then
        _clipman_deps_log "usage: clipman_deps_missing <set> [pm]"
        return 1
    fi
    pm=$(_clipman_deps_pm "${2:-}") || return 1
    local lines
    lines=$(_clipman_deps_missing_lines "$pm" "$set") || return 1
    if [ -n "$lines" ]; then
        # shellcheck disable=SC2086
        echo $lines
        return 1
    fi
    return 0
}

#######################################
# Install the missing packages of one or more sets on the host.
# Globals:
#   CLIPMAN_DEPS_YES        1 passes the assume-yes flag (implied on CI)
#   CLIPMAN_DEPS_NO_UPDATE  1 skips apt-get update
# Arguments:
#   One or more of runtime, test, lint, dev.
# Outputs:
#   Progress to stderr; on return 3, the sudo command to run.
# Returns:
#   0 when all packages are present, 3 when root cannot be obtained
#   non-interactively, 1 otherwise.
#######################################
clipman_deps_install() {
    if [ "$#" -eq 0 ]; then
        _clipman_deps_log "usage: clipman_deps_install <set...>"
        return 1
    fi
    local pm
    pm=$(_clipman_deps_pm "") || return 1

    local missing_lines
    missing_lines=$(_clipman_deps_missing_lines "$pm" "$@") || return 1
    if [ -z "$missing_lines" ]; then
        _clipman_deps_log "all $pm packages for '$*' are already installed"
        return 0
    fi

    local -a yes=()
    if _clipman_deps_assume_yes; then
        case "$pm" in
            apt|dnf) yes=(-y) ;;
            pacman) yes=(--noconfirm) ;;
        esac
    fi
    # A 30 s fetch timeout lets a stalled mirror fail and retry within CI's
    # 4-minute step cap.
    local -a apt_opts=(-o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o DPkg::Lock::Timeout=60)
    local -a update_cmd=()
    if [ "$pm" = "apt" ] && [ "${CLIPMAN_DEPS_NO_UPDATE:-0}" != "1" ]; then
        update_cmd=(env DEBIAN_FRONTEND=noninteractive apt-get update "${apt_opts[@]}")
    fi

    local rc=0
    if [ "${#update_cmd[@]}" -gt 0 ]; then
        _clipman_deps_run_privileged "${update_cmd[@]}" || rc=$?
        # Re-resolve the alternatives against the refreshed index.
        if [ "$rc" -eq 0 ]; then
            missing_lines=$(_clipman_deps_missing_lines "$pm" "$@") || return 1
        fi
    fi
    local -a missing=()
    local pkg
    for pkg in $missing_lines; do
        missing+=("$pkg")
    done
    if [ "${#missing[@]}" -eq 0 ]; then
        _clipman_deps_log "all $pm packages for '$*' are already installed"
        return 0
    fi

    local -a install_cmd=()
    case "$pm" in
        apt) install_cmd=(env DEBIAN_FRONTEND=noninteractive apt-get install "${apt_opts[@]}" "${yes[@]}" "${missing[@]}") ;;
        dnf) install_cmd=(dnf install "${yes[@]}" "${missing[@]}") ;;
        pacman) install_cmd=(pacman -S --needed "${yes[@]}" "${missing[@]}") ;;
    esac
    _clipman_deps_log "missing $pm packages: ${missing[*]}"

    if [ "$rc" -eq 0 ]; then
        _clipman_deps_run_privileged "${install_cmd[@]}" || rc=$?
    fi

    if [ "$rc" -eq 3 ]; then
        _clipman_deps_log "cannot obtain root privileges non-interactively; run:"
        if [ "${#update_cmd[@]}" -gt 0 ]; then
            printf '  sudo %s\n' "${update_cmd[*]}" >&2
        fi
        printf '  sudo %s\n' "${install_cmd[*]}" >&2
        return 3
    fi
    if [ "$rc" -ne 0 ]; then
        _clipman_deps_log "package installation failed (exit $rc)"
        return 1
    fi

    if missing_lines=$(_clipman_deps_missing_lines "$pm" "$@") && [ -z "$missing_lines" ]; then
        _clipman_deps_log "installed: ${missing[*]}"
        return 0
    fi
    # shellcheck disable=SC2086
    _clipman_deps_log "still missing after install:" $missing_lines
    return 1
}

# CLI (only when executed, never when sourced)

_clipman_deps_usage() {
    cat <<'EOF'
usage: scripts/deps.sh [--runtime|--test|--lint|--dev]... [--pm apt|dnf|pacman]
                       [--print|--check|--install] [--yes] [--no-update]

Sets (repeatable; default --dev = runtime + test + lint):
  --runtime   packages the app needs to run
  --test      Xvfb plus the headers needed to build PyGObject / dbus-python
  --lint      shellcheck
  --dev       all of the above

Actions (default --print):
  --print     print the resolved package list for the target package manager
  --check     print missing packages; exit 1 if any are missing
  --install   install the missing packages (sudo when needed)

Options:
  --pm NAME   target package manager instead of auto-detecting
  --yes       pass the assume-yes flag to the package manager
  --no-update skip `apt-get update` before installing
  -h, --help  show this help

Exit codes: 0 ok · 1 missing/failure · 2 usage · 3 privileges needed
EOF
}

_clipman_deps_main() {
    local -a sets=()
    local action="" pm=""
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --runtime|--test|--lint|--dev) sets+=("${1#--}") ;;
            --print|--check|--install)
                if [ -n "$action" ] && [ "$action" != "${1#--}" ]; then
                    _clipman_deps_log "conflicting actions --$action and $1"
                    _clipman_deps_usage >&2
                    return 2
                fi
                action="${1#--}"
                ;;
            --pm)
                if [ "$#" -lt 2 ]; then
                    _clipman_deps_log "--pm needs an argument"
                    return 2
                fi
                pm="$2"
                shift
                ;;
            --pm=*) pm="${1#--pm=}" ;;
            --yes) CLIPMAN_DEPS_YES=1 ;;
            --no-update) CLIPMAN_DEPS_NO_UPDATE=1 ;;
            -h|--help)
                _clipman_deps_usage
                return 0
                ;;
            *)
                _clipman_deps_log "unknown argument '$1'"
                _clipman_deps_usage >&2
                return 2
                ;;
        esac
        shift
    done
    if [ "${#sets[@]}" -eq 0 ]; then sets=(dev); fi
    [ -n "$action" ] || action=print
    case "$pm" in
        ""|apt|dnf|pacman) ;;
        *)
            _clipman_deps_log "unknown package manager '$pm' (expected apt, dnf or pacman)"
            _clipman_deps_usage >&2
            return 2
            ;;
    esac

    case "$action" in
        print)
            pm=$(_clipman_deps_pm "$pm") || return 1
            local lines
            lines=$(_clipman_deps_union "$pm" "${sets[@]}") || return 1
            # shellcheck disable=SC2086
            echo $lines
            ;;
        check)
            pm=$(_clipman_deps_pm "$pm") || return 1
            local lines
            lines=$(_clipman_deps_missing_lines "$pm" "${sets[@]}") || return 1
            if [ -n "$lines" ]; then
                _clipman_deps_log "missing $pm packages for '${sets[*]}':"
                # shellcheck disable=SC2086
                echo $lines
                return 1
            fi
            _clipman_deps_log "all $pm packages for '${sets[*]}' are installed"
            ;;
        install)
            if [ -n "$pm" ]; then
                local detected
                detected=$(clipman_deps_detect_pm || true)
                if [ "$pm" != "$detected" ]; then
                    _clipman_deps_log "--pm $pm does not match this host (${detected:-none}); --install uses the host's package manager"
                    return 2
                fi
            fi
            clipman_deps_install "${sets[@]}"
            ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    set -euo pipefail
    _clipman_deps_main "$@"
fi
