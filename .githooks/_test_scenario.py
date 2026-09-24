#!/usr/bin/env python3
"""Run one git-state case from the hooks corpus through the real hooks.

A case describes a clone: its git identity, environment overrides, the gh
CLI's active login, and whether it is the maintainer's clone or a
contributor's. This builds that clone in a temp directory, stages a change,
runs the real pre-commit hook, makes the commit, then runs the real
pre-push hook. It prints PASS when both hooks accept the case and BLOCK
when one refuses it. Given the hook the case targets (the corpus's
expected_check), a refusal by the other hook prints BLOCK(<hook>), which
the harness counts as a mismatch.

Everything is hermetic: a temp HOME and global git config, no system
config, and a stub gh on PATH, so the developer's own settings never leak
into a result.

Case keys (all optional):
  context               "maintainer" (origin is the maintainer's repo, the
                        default) or "contributor" (origin is a fork)
  user.email, user.name, git_user_email, git_user_name
                        the clone's git config identity
  env                   environment variables for the hooks
  git_var_GIT_AUTHOR_IDENT
                        the effective author ident ("Name <email> ts tz")
  gh_active_login       login the gh stub reports; empty means logged out
  gh_installed          false means gh reports no login
  maintainer_flag       value for git config clipman.hooks.maintainer
  global_config         {"key": "value"} pairs for the global git config
  commit_author         "Name <email>" for the commit only, made after
                        pre-commit ran: a commit from outside the hook chain
"""

import json
import os
import shlex
import subprocess
import sys
import tempfile

MAINTAINER = "MohammedEl-sayedAhmed"
ZERO = "0" * 40

# Variables from the developer's shell that would change what the hooks see.
_DROP_PREFIXES = ("GIT_", "CLIPMAN_HOOKS_")
_DROP_NAMES = ("EMAIL", "GH_TOKEN", "GITHUB_TOKEN")


def _clean_env(home, stub_dir):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(_DROP_PREFIXES) and key not in _DROP_NAMES
    }
    env.update(
        HOME=home,
        XDG_CONFIG_HOME=os.path.join(home, ".config"),
        GIT_CONFIG_GLOBAL=os.path.join(home, ".gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        PATH=stub_dir + os.pathsep + os.environ.get("PATH", ""),
    )
    return env


def _write_gh_stub(stub_dir, login):
    path = os.path.join(stub_dir, "gh")
    with open(path, "w") as f:
        f.write("#!/bin/sh\n")
        f.write(f"echo {shlex.quote(login)}\n" if login else "exit 1\n")
    os.chmod(path, 0o700)


def _split_ident(ident):
    """Return (name, email) from "Name <email> timestamp tz"."""
    name, _, rest = ident.partition(" <")
    return name.strip(), rest.split(">", 1)[0]


def run_case(hooks_dir, case, expected_check=""):
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        stub_dir = os.path.join(tmp, "bin")
        repo = os.path.join(tmp, "repo")
        os.mkdir(home)
        os.mkdir(stub_dir)
        env = _clean_env(home, stub_dir)

        login = case.get("gh_active_login", "")
        if case.get("gh_installed") is False:
            login = ""
        _write_gh_stub(stub_dir, login)

        def git(*args):
            return subprocess.run(
                ["git", *args], cwd=repo, env=env, check=True,
                capture_output=True, text=True,
            ).stdout.strip()

        subprocess.run(["git", "init", "-q", repo], env=env, check=True)
        for key, value in (case.get("global_config") or {}).items():
            git("config", "--global", key, value)

        email = case.get("user.email", case.get("git_user_email"))
        name = case.get("user.name", case.get("git_user_name"))
        if email:
            git("config", "user.email", email)
        if name:
            git("config", "user.name", name)
        if "maintainer_flag" in case:
            git("config", "clipman.hooks.maintainer", case["maintainer_flag"])

        owner = MAINTAINER if case.get("context", "maintainer") == "maintainer" else "contributor-fork"
        git("remote", "add", "origin", f"https://github.com/{owner}/clipman.git")

        env.update(case.get("env") or {})
        ident = case.get("git_var_GIT_AUTHOR_IDENT")
        if ident:
            ident_name, ident_email = _split_ident(ident)
            env.setdefault("GIT_AUTHOR_NAME", ident_name)
            env.setdefault("GIT_AUTHOR_EMAIL", ident_email)
        # git needs a committer to make the commit; fall back to the author
        # so a case that sets only one side still commits.
        for side in ("NAME", "EMAIL"):
            if f"GIT_AUTHOR_{side}" in env:
                env.setdefault(f"GIT_COMMITTER_{side}", env[f"GIT_AUTHOR_{side}"])

        with open(os.path.join(repo, "change.txt"), "w") as f:
            f.write("a small change\n")
        git("add", "change.txt")

        refused_by = None
        pre_commit = subprocess.run(
            [os.path.join(hooks_dir, "pre-commit")], cwd=repo, env=env,
            capture_output=True, text=True,
        )
        if pre_commit.returncode != 0:
            refused_by = "pre-commit"
        else:
            commit_author = case.get("commit_author")
            if commit_author:
                author_name, author_email = _split_ident(commit_author)
                env.update(GIT_AUTHOR_NAME=author_name, GIT_AUTHOR_EMAIL=author_email)
            sha = git("commit-tree", git("write-tree"), "-m", "test: a small change")
            url = git("remote", "get-url", "--push", "origin")
            pre_push = subprocess.run(
                [os.path.join(hooks_dir, "pre-push"), "origin", url],
                cwd=repo, env=env, capture_output=True, text=True,
                input=f"refs/heads/main {sha} refs/heads/main {ZERO}\n",
            )
            if pre_push.returncode != 0:
                refused_by = "pre-push"

    if refused_by is None:
        return "PASS"
    if expected_check in ("pre-commit", "pre-push") and expected_check != refused_by:
        return f"BLOCK({refused_by})"
    return "BLOCK"


def main(argv):
    if len(argv) not in (3, 4):
        print(f"usage: {argv[0]} <hooks-dir> <case-json> [expected-check]", file=sys.stderr)
        return 2
    expected_check = argv[3] if len(argv) == 4 else ""
    print(run_case(os.path.abspath(argv[1]), json.loads(argv[2]), expected_check))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
