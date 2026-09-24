#!/usr/bin/env python3
"""Test scripts/check-footprints.sh, the pull-request footprint check.

Every commit-message case in the corpus becomes a real commit in a
throwaway repo, and the CI check must reach the same verdict as the local
commit-msg hook, so the two never drift apart. A few more cases cover what
only the pull-request check sees: added lines, the title, the description
(a bot's description is skipped), and merge commits.

Prints one line per mismatch, then "ci-scan <passed> <failed>" last; the
harness (_test.sh) reads that line.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile


def _run(args, cwd, env, check=True):
    return subprocess.run(args, cwd=cwd, env=env, check=check,
                          capture_output=True, text=True)


class Repo:
    """A throwaway clone holding the check script and a base commit."""

    def __init__(self, root, tmp):
        self.path = os.path.join(tmp, "repo")
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("GIT_", "PR_"))
        }
        self.env.update(
            HOME=home, GIT_CONFIG_GLOBAL=os.path.join(home, ".gitconfig"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="Jane Doe", GIT_AUTHOR_EMAIL="jane@example.org",
            GIT_COMMITTER_NAME="Jane Doe", GIT_COMMITTER_EMAIL="jane@example.org",
        )
        _run(["git", "init", "-q", "-b", "main", self.path], tmp, self.env)
        for rel in ("scripts/check-footprints.sh", ".githooks/_lib.sh"):
            os.makedirs(os.path.join(self.path, os.path.dirname(rel)), exist_ok=True)
            shutil.copy2(os.path.join(root, rel), os.path.join(self.path, rel))
        self.write("README.md", "base\n")
        self.base = self.commit("base")

    def git(self, *args):
        return _run(["git", *args], self.path, self.env).stdout.strip()

    def write(self, rel, text):
        full = os.path.join(self.path, rel)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "a") as f:
            f.write(text)

    def commit(self, message):
        self.git("add", "-A")
        # verbatim: keep the message exactly as the hooks saw it.
        self.git("commit", "-q", "--allow-empty", "--no-verify",
                 "--cleanup=verbatim", "-m", message)
        return self.git("rev-parse", "HEAD")

    def reset(self):
        self.git("reset", "-q", "--hard", self.base)

    def check(self, head, **pr):
        env = dict(self.env, **pr)
        result = _run([os.path.join(self.path, "scripts/check-footprints.sh"),
                       self.base, head], self.path, env, check=False)
        return "PASS" if result.returncode == 0 else "BLOCK"


def main(root):
    with open(os.path.join(root, ".githooks/_test_corpus.json")) as f:
        corpus = json.load(f)
    messages = [c for c in corpus if not c["input"].lstrip().startswith("{")]
    # A known footprint line, taken from the corpus rather than retyped.
    footprint = corpus[0]["input"].splitlines()[-1]

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(root, tmp)

        for index, case in enumerate(messages):
            repo.reset()
            repo.write("change.txt", f"change {index}\n")
            head = repo.commit(case["input"])
            results.append((f"message case {index}: {case['reason'][:60]}",
                            case["expected_outcome"], repo.check(head)))

        def extra(name, expected, files=(), message="docs: tweak", **pr):
            repo.reset()
            for rel, text in files:
                repo.write(rel, text)
            head = repo.commit(message)
            results.append((name, expected, repo.check(head, **pr)))

        extra("clean change", "PASS", [("notes.txt", "hello\n")])
        extra("footprint added to a file", "BLOCK", [("notes.txt", footprint + "\n")])
        extra("footprint added to an allowlisted doc", "PASS",
              [("docs/hooks.md", footprint + "\n")])
        extra("footprint in the title", "BLOCK", PR_TITLE="fix: x " + footprint)
        extra("footprint in a person's description", "BLOCK",
              PR_BODY="Summary\n\n" + footprint, PR_AUTHOR_TYPE="User")
        extra("footprint in a bot's description", "PASS",
              PR_BODY="Release notes\n\n" + footprint, PR_AUTHOR_TYPE="Bot")
        extra("clean title and description", "PASS",
              PR_TITLE="fix: tidy", PR_BODY="Summary\n\nPlain words.",
              PR_AUTHOR_TYPE="User")

        # A merge commit brings in no content of its own to check.
        repo.reset()
        repo.git("checkout", "-q", "-b", "side")
        repo.write("side.txt", "side\n")
        repo.commit("docs: side")
        repo.git("checkout", "-q", "main")
        repo.git("reset", "-q", "--hard", repo.base)
        repo.write("main.txt", "main\n")
        repo.commit("docs: main")
        repo.git("merge", "-q", "--no-ff", "--no-edit", "side")
        results.append(("clean merge commit", "PASS", repo.check(repo.git("rev-parse", "HEAD"))))

    failed = 0
    for name, expected, actual in results:
        if expected != actual:
            failed += 1
            print(f"ci-scan [{name}] expected={expected} got={actual}")
    print(f"ci-scan {len(results) - failed} {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "..")))
