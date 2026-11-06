"""scripts/ego-upload.py against a fake extensions.gnome.org API.

The fake server answers the three calls the script makes (login, upload,
logout) with the replies of the real site's code: django-rest-registration
for login and logout, with knox tokens, and the extension upload view.
Nothing leaves this machine.
"""
import contextlib
import email.parser
import email.policy
import http.server
import importlib.util
import io
import json
import os
import shutil
import socket
import tempfile
import threading
import unittest
import unittest.mock
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "ego_upload", ROOT / "scripts" / "ego-upload.py"
)
ego = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ego)

USER, PASSWORD, TOKEN = "maintainer", "s3cret-pass", "tok-123456"


class FakeEgo(http.server.BaseHTTPRequestHandler):
    """Records every request; ``state`` sets how it answers."""

    def log_message(self, *_args):
        pass

    def _reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _form(raw):
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}

    def do_POST(self):
        state = self.server.state
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        call = {"path": self.path, "auth": self.headers.get("Authorization")}
        state["calls"].append(call)
        if self.path == "/api/v1/accounts/login/":
            call["form"] = self._form(raw)
            if call["form"] != {"login": USER, "password": PASSWORD}:
                self._reply(400, {"detail": "Login or password invalid."})
            elif state.get("login_without_token"):
                self._reply(200, {"detail": "Login successful"})
            else:
                self._reply(200, {"detail": "Login successful", "token": {
                    "expiry": "2026-11-13T00:00:00Z", "token": TOKEN}})
        elif self.path == "/api/v1/extensions":
            message = email.parser.BytesParser(policy=email.policy.default).parsebytes(
                b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + raw)
            fields = {}
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                fields[name] = (part.get_filename(), part.get_payload(decode=True))
            call["fields"] = fields
            if call["auth"] != f"Token {TOKEN}":
                self._reply(401, {"detail": "Invalid token."})
            elif state.get("reject"):
                self._reply(400, state["reject"])
            else:
                self._reply(201, {"extension": "clipman@clipman.com", "version": 8,
                                  "status": 0, "link": "/extension/9407/"})
        elif self.path == "/api/v1/accounts/logout/":
            call["form"] = self._form(raw)
            if call["auth"] != f"Token {TOKEN}":
                self._reply(401, {"detail": "Invalid token."})
            elif state.get("logout_status"):
                self._reply(state["logout_status"], {"detail": "Server error."})
            else:
                self._reply(200, {"detail": "Logout successful"})
        else:
            self._reply(404, {"detail": "Not found."})


class TestEgoUpload(unittest.TestCase):
    def setUp(self):
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeEgo)
        self.server.state = {"calls": []}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}/api/v1"
        self.dir = tempfile.mkdtemp(prefix="clipman-ego-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.zip = self._zip({"metadata.json": json.dumps(
            {"uuid": "clipman@clipman.com", "version": 9,
             "url": "https://github.com/MohammedEl-sayedAhmed/clipman"}),
            "extension.js": "export default class {}\n"})

    def _zip(self, files, name="clipman-extension-v1.3.0.zip"):
        path = os.path.join(self.dir, name)
        with zipfile.ZipFile(path, "w") as archive:
            for member, text in files.items():
                archive.writestr(member, text)
        return path

    def _run(self, zip_path=None, env=None, base=None):
        env = {"EGO_USERNAME": USER, "EGO_PASSWORD": PASSWORD} if env is None else env
        out, err = io.StringIO(), io.StringIO()
        with unittest.mock.patch.dict(os.environ, env, clear=False), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if "EGO_USERNAME" not in env:
                os.environ.pop("EGO_USERNAME", None)
                os.environ.pop("EGO_PASSWORD", None)
            code = ego.main([zip_path or self.zip, "--base", base or self.base])
        text = out.getvalue() + err.getvalue()
        # The password and the token never reach the log.
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn(TOKEN, text)
        return code, text

    def _paths(self):
        return [call["path"] for call in self.server.state["calls"]]

    def test_logs_in_uploads_and_logs_out(self):
        code, text = self._run()
        self.assertEqual(code, 0, text)
        self.assertEqual(self._paths(), ["/api/v1/accounts/login/",
                                         "/api/v1/extensions",
                                         "/api/v1/accounts/logout/"])
        login, upload, logout = self.server.state["calls"]
        self.assertEqual(login["form"], {"login": USER, "password": PASSWORD})
        self.assertEqual(upload["auth"], f"Token {TOKEN}")
        self.assertEqual(logout["auth"], f"Token {TOKEN}")
        self.assertEqual(logout["form"], {"revoke_token": "true"})
        fields = upload["fields"]
        self.assertEqual(fields["shell_license_compliant"][1], b"true")
        self.assertEqual(fields["tos_compliant"][1], b"true")
        filename, content = fields["source"]
        self.assertEqual(filename, "clipman-extension-v1.3.0.zip")
        with open(self.zip, "rb") as f:
            self.assertEqual(content, f.read())
        self.assertIn('"version": 8', text)
        self.assertIn("reviews each version", text)
        self.assertNotIn("note:", text)

    def test_a_refused_login_stops_before_the_upload(self):
        code, text = self._run(env={"EGO_USERNAME": USER, "EGO_PASSWORD": "wrong"})
        self.assertEqual(code, 1)
        self.assertIn("login failed: Login or password invalid. (HTTP 400)", text)
        self.assertEqual(self._paths(), ["/api/v1/accounts/login/"])

    def test_a_login_reply_without_a_token_stops_before_the_upload(self):
        self.server.state["login_without_token"] = True
        code, text = self._run()
        self.assertEqual(code, 1)
        self.assertIn("login failed: the reply has no token", text)
        self.assertEqual(self._paths(), ["/api/v1/accounts/login/"])

    def test_a_rejected_upload_still_logs_out(self):
        self.server.state["reject"] = {"source": ["The `url` field is missing"]}
        code, text = self._run()
        self.assertEqual(code, 1)
        self.assertIn("upload failed: ['The `url` field is missing'] (HTTP 400)", text)
        self.assertEqual(self._paths()[-1], "/api/v1/accounts/logout/")
        # The site also answers some rejections with a bare list.
        self.server.state["reject"] = ["An extension with that UUID has already been added"]
        code, text = self._run()
        self.assertEqual(code, 1)
        self.assertIn("upload failed: An extension with that UUID has already been "
                      "added (HTTP 400)", text)

    def test_a_failed_logout_does_not_fail_the_upload(self):
        real_post = ego._post

        def post(url, data, headers):
            if url.endswith("/accounts/logout/"):
                raise ego.UploadError("cannot reach 127.0.0.1: timed out")
            return real_post(url, data, headers)

        with unittest.mock.patch.object(ego, "_post", post):
            code, text = self._run()
        self.assertEqual(code, 0, text)
        self.assertIn("note: logout failed (cannot reach", text)
        self.assertIn("Uploaded", text)

    def test_a_refused_logout_does_not_fail_the_upload(self):
        self.server.state["logout_status"] = 500
        code, text = self._run()
        self.assertEqual(code, 0, text)
        self.assertIn("note: logout failed (Server error. (HTTP 500))", text)

    def test_a_bad_zip_stops_before_any_request(self):
        bad = self._zip({"metadata.json": "{}"}, name="bad.zip")
        code, text = self._run(zip_path=bad)
        self.assertEqual(code, 1)
        self.assertIn("must be at the root of the zip", text)
        nested = self._zip({"ext/metadata.json": "{}", "ext/extension.js": ""},
                           name="nested.zip")
        self.assertEqual(self._run(zip_path=nested)[0], 1)
        no_uuid = self._zip({"metadata.json": "{}", "extension.js": ""},
                            name="no-uuid.zip")
        self.assertIn("no uuid", self._run(zip_path=no_uuid)[1])
        no_url = self._zip({"metadata.json": json.dumps({"uuid": "a@b"}),
                            "extension.js": ""}, name="no-url.zip")
        self.assertIn("no url", self._run(zip_path=no_url)[1])
        self.assertEqual(self._paths(), [])

    def test_a_missing_login_stops_before_any_request(self):
        code, text = self._run(env={})
        self.assertEqual(code, 1)
        self.assertIn("EGO_USERNAME and EGO_PASSWORD must be set", text)
        self.assertEqual(self._paths(), [])

    def test_an_unreachable_server_is_an_error(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        code, text = self._run(base=f"http://127.0.0.1:{port}/api/v1")
        self.assertEqual(code, 1)
        self.assertIn("cannot reach 127.0.0.1", text)


if __name__ == "__main__":
    unittest.main()
