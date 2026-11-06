#!/usr/bin/env python3
"""Upload a GNOME Shell extension zip to extensions.gnome.org.

Uses the site's API the same way GNOME's own ``gnome-extensions upload``
does: log in with the account's username and password to get a token,
POST the zip to ``/api/v1/extensions``, then log out. extensions.gnome.org
reviews every upload before users get it.

Reads the login from the ``EGO_USERNAME`` and ``EGO_PASSWORD`` environment
variables and never prints the password or the token.

Usage: ego-upload.py ZIP [--base URL]
Exit status: 0 when uploaded, 1 on any failure.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

BASE = "https://extensions.gnome.org/api/v1"
UA = "clipman-ego-upload/1.0 (+https://github.com/MohammedEl-sayedAhmed/clipman)"
TIMEOUT = 60


class UploadError(Exception):
    """Something stopped the upload; the message says what."""


def check_zip(path):
    """The zip's metadata.json, after checking the layout e.g.o. expects."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if not {"metadata.json", "extension.js"} <= names:
                raise UploadError(f"{path}: metadata.json and extension.js "
                                  "must be at the root of the zip")
            meta = json.loads(archive.read("metadata.json"))
    except (OSError, zipfile.BadZipFile, ValueError) as error:
        raise UploadError(f"{path}: not a usable extension zip ({error})") from None
    if not isinstance(meta, dict) or not meta.get("uuid"):
        raise UploadError(f"{path}: metadata.json has no uuid")
    return meta


def _json(raw):
    try:
        return json.loads(raw.decode("utf-8") or "null")
    except ValueError:
        return None


def _post(url, data, headers):
    """(status, decoded JSON body) of a POST; UploadError when unreachable."""
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": UA, "Accept": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, _json(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _json(error.read())
    except (urllib.error.URLError, TimeoutError) as error:
        host = urllib.parse.urlsplit(url).netloc
        raise UploadError(f"cannot reach {host}: {error}") from None


def _detail(body, status):
    """The server's reason for a failure, without echoing a token."""
    if isinstance(body, dict):
        for key in ("detail", "non_field_errors", "source", "error"):
            if body.get(key):
                return f"{body[key]} (HTTP {status})"
        safe = {k: v for k, v in body.items() if k != "token"}
        return f"{json.dumps(safe)[:300]} (HTTP {status})"
    return f"HTTP {status}"


def login(base, user, password):
    """A login token for the account."""
    data = urllib.parse.urlencode({"login": user, "password": password}).encode()
    status, body = _post(f"{base}/accounts/login/", data,
                         {"Content-Type": "application/x-www-form-urlencoded"})
    token = body.get("token") if isinstance(body, dict) else None
    if status != 200 or not isinstance(token, str) or not token:
        raise UploadError(f"login failed: {_detail(body, status)}")
    return token


def _multipart(fields, file_field, path):
    """(body, content type) for a multipart/form-data POST with one file."""
    boundary = uuid.uuid4().hex
    parts = [
        (f"--{boundary}\r\n"
         f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
         f"{value}\r\n").encode()
        for name, value in fields.items()
    ]
    with open(path, "rb") as f:
        content = f.read()
    parts.append(
        (f"--{boundary}\r\n"
         f'Content-Disposition: form-data; name="{file_field}"; '
         f'filename="{os.path.basename(path)}"\r\n'
         "Content-Type: application/zip\r\n\r\n").encode()
        + content + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload(base, token, path):
    """Upload the zip; the server's JSON reply."""
    body, content_type = _multipart(
        {"shell_license_compliant": "true", "tos_compliant": "true"},
        "source", path,
    )
    status, reply = _post(f"{base}/extensions", body, {
        "Content-Type": content_type,
        "Authorization": f"Token {token}",
    })
    if status != 201:
        raise UploadError(f"upload failed: {_detail(reply, status)}")
    return reply


def logout(base, token):
    """End the session; a failure here only gets a note in the log."""
    try:
        _post(f"{base}/accounts/logout/", b"", {"Authorization": f"Token {token}"})
    except UploadError as error:
        print(f"note: logout failed ({error}); the token expires by itself",
              file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Upload a GNOME Shell extension zip to extensions.gnome.org.")
    parser.add_argument("zip", help="the extension zip")
    parser.add_argument("--base", default=BASE, help="API base URL (for tests)")
    args = parser.parse_args(argv)

    user = os.environ.get("EGO_USERNAME", "")
    password = os.environ.get("EGO_PASSWORD", "")
    try:
        if not user or not password:
            raise UploadError("EGO_USERNAME and EGO_PASSWORD must be set")
        meta = check_zip(args.zip)
        print(f"Uploading {meta['uuid']} (metadata version "
              f"{meta.get('version', '?')}) to extensions.gnome.org")
        token = login(args.base, user, password)
        try:
            reply = upload(args.base, token, args.zip)
        finally:
            logout(args.base, token)
    except UploadError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    shown = {k: reply[k] for k in ("uuid", "version", "status")
             if isinstance(reply, dict) and k in reply}
    print(f"Uploaded {json.dumps(shown) if shown else ''}".rstrip())
    print("extensions.gnome.org reviews each version before users get it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
