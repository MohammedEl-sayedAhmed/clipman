"""scripts/contributors.py writes the README's contributors list.

The list names people only. These tests feed it pull requests shaped
like the GitHub API's, and never reach the network.
"""
import contextlib
import importlib.util
import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "contributors", ROOT / "scripts" / "contributors.py"
)
contributors = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(contributors)


def _pull(number, login, user_id, kind="User", merged=True):
    return {
        "number": number,
        "merged_at": "2026-10-01T00:00:00Z" if merged else None,
        "user": {"login": login, "id": user_id, "type": kind},
    }


def _person(login, user_id, prs, name=None):
    return {"login": login, "id": user_id, "prs": prs, "name": name or login}


class TestWhoIsListed(unittest.TestCase):
    def test_people_with_a_merged_pull_request(self):
        people = contributors.collect([
            _pull(5, "ngtw-j", 1),
            _pull(297, "MrTomRod", 2),
        ])
        self.assertEqual([p["login"] for p in people], ["ngtw-j", "MrTomRod"])

    def test_bots_and_ai_tools_are_never_listed(self):
        """The maintainer's rule: no AI tool and no bot in the credits."""
        pulls = [
            _pull(1, "dependabot[bot]", 10, kind="Bot"),
            _pull(2, "github-actions[bot]", 11, kind="Bot"),
            _pull(3, "Copilot", 12, kind="Bot"),
            _pull(4, "claude[bot]", 13, kind="Bot"),
            # Accounts that GitHub types as users.
            _pull(5, "claude", 14),
            _pull(6, "Claude-Code-Helper", 15),
            _pull(7, "anthropic-agent", 16),
            _pull(8, "copilot-swe-agent", 17),
            _pull(9, "openai-codex", 18),
            _pull(10, "chatgpt-pr", 19),
            _pull(11, "renovate[bot]", 20),
        ]
        self.assertEqual(contributors.collect(pulls), [])

    def test_maintainer_deleted_accounts_and_opt_outs_are_not_listed(self):
        pulls = [
            _pull(1, "MohammedEl-sayedAhmed", 30),
            _pull(2, "ghost", 31),
        ]
        self.assertEqual(contributors.collect(pulls), [])
        with patch.object(contributors, "EXCLUDE", frozenset({"someone"})):
            self.assertEqual(contributors.collect([_pull(3, "Someone", 32)]), [])

    def test_pull_requests_that_were_not_merged_do_not_count(self):
        pulls = [_pull(165, "a-person", 40, merged=False)]
        self.assertEqual(contributors.collect(pulls), [])

    def test_one_entry_per_person_in_order_of_their_first_pull_request(self):
        people = contributors.collect([
            _pull(40, "second", 2),
            _pull(30, "first", 1),
            _pull(10, "first", 1),
        ])
        self.assertEqual(
            [(p["login"], p["prs"]) for p in people],
            [("first", [10, 30]), ("second", [40])],
        )


class TestRendering(unittest.TestCase):
    def test_plain_html_with_absolute_links_and_no_emoji(self):
        block = contributors.render_block([
            _person("ngtw-j", 172234289, [5], "Josie Ng"),
            _person("MrTomRod", 40867365, [297], "Thomas Roder"),
        ])
        self.assertTrue(block.isascii(), block)
        self.assertNotIn("style=", block)
        # PyPI shows the README too, where relative links break.
        for url in re.findall(r'(?:href|src)="([^"]+)"', block):
            self.assertTrue(url.startswith("https://"), url)
        self.assertIn("<b>Josie Ng</b>", block)
        self.assertIn('Pull request <a href="https://github.com/'
                      'MohammedEl-sayedAhmed/clipman/pull/5">#5</a>', block)

    def test_names_are_escaped(self):
        block = contributors.render_block(
            [_person("someone", 1, [7], '<b>Eve</b> & "co"')]
        )
        self.assertIn("&lt;b&gt;Eve&lt;/b&gt; &amp; &quot;co&quot;", block)
        self.assertNotIn("<b>Eve</b>", block)

    def test_avatar_uses_the_account_id_at_twice_the_size(self):
        block = contributors.render_block([_person("someone", 92355621, [354])])
        self.assertIn('src="https://avatars.githubusercontent.com/u/92355621'
                      '?v=4&amp;s=160" width="80" height="80"', block)

    def test_many_pull_requests_get_one_link(self):
        few = contributors.render_block([_person("someone", 1, [1, 2])])
        self.assertIn('Pull requests <a href="https://github.com/'
                      'MohammedEl-sayedAhmed/clipman/pull/1">#1</a>, ', few)
        many = contributors.render_block([_person("someone", 1, [1, 2, 3, 4])])
        self.assertIn("author%3Asomeone\">4 pull requests</a>", many)

    def test_rows_wrap(self):
        people = [_person(f"p{i}", i, [i]) for i in range(1, 8)]
        block = contributors.render_block(people)
        self.assertEqual(block.count("<tr>"), 2)

    def test_empty_list(self):
        self.assertEqual(contributors.render_block([]),
                         "<p>No outside contributions yet.</p>")


class TestReplaceBlock(unittest.TestCase):
    TEXT = ("before\n" + contributors.START + "\nold\n" + contributors.END
            + "\nafter\n")

    def test_replaces_only_the_text_between_the_markers(self):
        new = contributors.replace_block(self.TEXT, "new")
        self.assertEqual(new, "before\n" + contributors.START + "\nnew\n"
                         + contributors.END + "\nafter\n")
        self.assertEqual(contributors.replace_block(new, "new"), new)

    def test_refuses_missing_doubled_or_swapped_markers(self):
        start, end = contributors.START, contributors.END
        for text in ("no markers", start + "\n", start + end + start + end,
                     end + "\n" + start + "\n"):
            with self.subTest(text=text):
                self.assertIsNone(contributors.replace_block(text, "new"))


class TestMain(unittest.TestCase):
    PULLS = [_pull(5, "ngtw-j", 172234289)]
    STALE = ("# Clipman\n" + contributors.START + "\nold\n"
             + contributors.END + "\n")

    def _run(self, argv, responses):
        """Run main() on a scratch README, answering API calls from
        ``responses`` (a URL part mapped to its JSON). Return the exit
        status and the README text after the run."""
        def fake_get(url):
            for part, value in responses.items():
                if part in url:
                    return value
            return None

        with tempfile.TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(self.STALE, encoding="utf-8")
            with patch.object(contributors, "README", readme), \
                 patch.object(contributors, "_get_json", side_effect=fake_get), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                status = contributors.main(argv)
            return status, readme.read_text(encoding="utf-8")

    def test_writes_the_list(self):
        status, text = self._run([], {"/pulls?": self.PULLS,
                                      "/users/ngtw-j": {"name": "Josie Ng"}})
        self.assertEqual(status, 0)
        self.assertIn("<b>Josie Ng</b>", text)
        self.assertNotIn("\nold\n", text)

    def test_check_reports_a_stale_list_and_writes_nothing(self):
        status, text = self._run(["--check"], {
            "/pulls?": self.PULLS, "/users/ngtw-j": {"name": "Josie Ng"},
        })
        self.assertEqual(status, 1)
        self.assertEqual(text, self.STALE)

    def test_nothing_is_written_when_the_api_cannot_be_read(self):
        for responses in ({}, {"/pulls?": self.PULLS}):
            with self.subTest(responses=list(responses)):
                status, text = self._run([], responses)
                self.assertEqual(status, 2)
                self.assertEqual(text, self.STALE)


class TestReadme(unittest.TestCase):
    def test_readme_list_is_plain_and_names_no_ai_tool(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(contributors.START), 1)
        self.assertEqual(text.count(contributors.END), 1)
        block = text.split(contributors.START, 1)[1].split(contributors.END, 1)[0]
        self.assertTrue(block.isascii())
        for word in contributors.AI_WORDS:
            self.assertNotIn(word, block.lower())


if __name__ == "__main__":
    unittest.main()
