"""Build the benchmark corpus for the sensitive-clip detector.

``benign`` holds text that people copy every day and that must never be
flagged: URLs, paths, timestamps, commit hashes, UUIDs, hex colours, MAC
addresses, public ids and so on. ``secret`` holds synthetic secrets with
real shapes: vendor tokens, keys, credential URLs, labelled values, card
numbers that pass Luhn, and bare passwords (the hard case).

Every token body comes from a seeded random generator, so the corpus is
the same on every run and no real secret ever appears here. Secret
headers are built by string concatenation so secret scanners do not
match them.

Run as a script to write ``corpus.json`` next to this file.
"""
import base64
import json
from collections import Counter
import os
import random
import string

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "corpus.json")

rng = random.Random(20260911)


def rand(alphabet, n):
    return "".join(rng.choice(alphabet) for _ in range(n))


ALNUM = string.ascii_letters + string.digits
UPDIG = string.ascii_uppercase + string.digits
LOWDIG = string.ascii_lowercase + string.digits
B64 = ALNUM + "+/"
B64URL = ALNUM + "-_"
B32 = string.ascii_uppercase + "234567"
HEX = "0123456789abcdef"


# Luhn
def luhn_ok(digits: str) -> bool:
    ds = [int(c) for c in digits if c.isdigit()]
    if len(ds) < 2:
        return False
    total = 0
    for i, d in enumerate(reversed(ds)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def luhn_complete(body: str) -> str:
    """Append the check digit that makes ``body`` Luhn-valid."""
    for c in "0123456789":
        if luhn_ok(body + c):
            return body + c
    raise AssertionError("unreachable")


def card(prefix: str, length: int) -> str:
    body = prefix + rand(string.digits, length - len(prefix) - 1)
    num = luhn_complete(body)
    assert len(num) == length and luhn_ok(num)
    return num


def group(num: str, sizes, sep):
    out, i = [], 0
    for s in sizes:
        out.append(num[i:i + s])
        i += s
    assert i == len(num)
    return sep.join(out)


visa = card("4", 16)
visa2 = card("4", 16)
mc = card("5" + rng.choice("12345"), 16)
mc2 = card("2221", 16)
amex = card("37", 15)
amex2 = card("34", 15)
disc = card("6011", 16)
disc2 = card("65", 16)

card_items = [
    (visa, "card_visa_plain"),
    (group(visa2, (4, 4, 4, 4), " "), "card_visa_spaces"),
    (group(visa, (4, 4, 4, 4), "-"), "card_visa_dashes"),
    (mc, "card_mastercard_plain"),
    (group(mc, (4, 4, 4, 4), " "), "card_mastercard_spaces"),
    (group(mc2, (4, 4, 4, 4), "-"), "card_mastercard_dashes"),
    (amex, "card_amex_plain"),
    (group(amex, (4, 6, 5), " "), "card_amex_spaces"),
    (group(amex2, (4, 6, 5), "-"), "card_amex_dashes"),
    (disc, "card_discover_plain"),
    (group(disc2, (4, 4, 4, 4), " "), "card_discover_spaces"),
    (group(disc, (4, 4, 4, 4), "-"), "card_discover_dashes"),
    ("4111111111111111", "card_visa_test_number"),
    ("5555555555554444", "card_mastercard_test_number"),
    ("378282246310005", "card_amex_test_number"),
]
for text, _ in card_items:
    assert luhn_ok(text), text

# Long digit strings that must NOT be Luhn-valid (benign).
long_digits = [
    "1234567890123456",
    "4111111111111112",
    "9999999999999999",
    "1111222233334445",
    "0000000000000001",
    "20240115103000123",
    "4532015112830367",   # visa-shaped but checksum broken
]
for d in long_digits:
    assert not luhn_ok(d), f"{d} is Luhn-valid; pick another"


def b64(s):
    return base64.b64encode(s.encode()).decode()


# Benign
benign = []


def B(cat, *texts):
    for t in texts:
        benign.append({"text": t, "category": cat})


B("url",
  "https://github.com/MohammedEl-sayedAhmed/clipman",
  "https://github.com/MohammedEl-sayedAhmed/clipman/pull/268",
  "https://github.com/MohammedEl-sayedAhmed/clipman/issues/42#issuecomment-2841003911",
  "https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/clipman/window.py#L120-L145",
  "https://github.com/MohammedEl-sayedAhmed/clipman/commit/9249ede",
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "https://youtu.be/dQw4w9WgXcQ?t=43",
  "https://www.youtube.com/watch?v=oHg5SJYRHA0&list=PL590L5WQmH8dpP0RyH5pCfIaDEdt9nk7r&index=3",
  "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
  "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0",
  "https://drive.google.com/file/d/1a2B3c4D5e6F7g8H9i0J/view?usp=sharing",
  "https://en.wikipedia.org/wiki/Wayland_(protocol)",
  "https://en.wikipedia.org/wiki/GNOME_Shell#Extensions",
  "https://ar.wikipedia.org/wiki/%D9%88%D8%A7%D9%8A%D9%84%D8%A7%D9%86%D8%AF",
  "http://localhost:8080/",
  "http://localhost:3000/api/v1/users?page=2&limit=50",
  "http://127.0.0.1:5173/#/settings",
  "http://192.168.1.1/",
  "http://192.168.0.254:8443/admin/login",
  "https://[2001:db8::1]:8080/status",
  "https://pypi.org/project/clipman/1.4.2/",
  "https://extensions.gnome.org/extension/9407/clipman/",
  "https://snapcraft.io/clipman",
  "https://flathub.org/apps/io.github.MohammedEl-sayedAhmed.clipman",
  "https://aur.archlinux.org/packages/clipman-git",
  "https://stackoverflow.com/questions/1234567/how-do-i-set-the-wayland-clipboard-from-a-daemon",
  "https://www.amazon.com/dp/B0BSHF7WHW?ref_=cm_sw_r_cp_ud_dp_ABC123XYZ",
  "https://www.google.com/search?q=gtk4+css+define-color&oq=gtk4+css&sourceid=chrome&ie=UTF-8",
  "https://maps.app.goo.gl/Xy7Zq9Kp2RvB3mNt8",
  "https://t.co/AbC123xYz9",
  "https://example.com/path/to/Report_2024-Q3_Final.pdf",
  "https://cdn.example.com/assets/img/hero@2x.png?v=20240115",
  "https://api.example.com/v2/items/8f14e45f-ceea-467a-9575-62d9e2b4f3a1",
  "https://docs.gtk.org/gtk4/class.Window.html",
  "https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API",
  "https://discourse.gnome.org/t/how-to-hide-window-from-alt-tab/12345/7",
  "https://github.com/MohammedEl-sayedAhmed/clipman/releases/download/v1.4.2/clipman-1.4.2.tar.gz",
  "https://user-images.githubusercontent.com/12345678/281234567-9f8e7d6c-5b4a-3c2d-1e0f-abcdef123456.png",
  "https://www.reddit.com/r/gnome/comments/1abc2de/clipboard_manager_for_wayland/",
  "https://news.ycombinator.com/item?id=39876543",
  "https://zoom.us/j/98765432109?pwd=abc123",
  "https://meet.google.com/abc-defg-hij",
  "ftp://ftp.gnu.org/gnu/gcc/gcc-13.2.0/gcc-13.2.0.tar.xz",
  "file:///home/mohammed/Downloads/Invoice_2024-03.pdf",
  "postgresql://localhost:5432/clipman_dev",
  "www.example.com",
  "example.com/about",
  "https://example.com",
  )

B("path",
  "/home/mohammed/Desktop/playground/clipman",
  "/home/mohammed/Desktop/playground/clipman/clipman/window.py",
  "~/.config/clipman/config.json",
  "~/.local/share/clipman/history.db",
  "/usr/lib/python3.12/site-packages/gi/__init__.py",
  "/var/log/syslog.1",
  "/etc/systemd/system/clipman.service",
  "src/main.py:42",
  "clipman/window.py:1187",
  "tests/test_clipboard_monitor.py::TestIsSensitiveFunction::test_url_not_sensitive",
  "report_2024_final.pdf",
  "Report_2024-Q3_Final_v2.docx",
  "IMG_20240115_103000.jpg",
  "Screenshot from 2024-01-15 10-30-00.png",
  "Screenshot_2024-01-15_10-30-00.png",
  "DSC_0042.NEF",
  "clipman-1.4.2.tar.gz",
  "clipman_1.4.2_amd64.deb",
  "clipman-1.4.2-1-any.pkg.tar.zst",
  "ubuntu-24.04.1-desktop-amd64.iso",
  "Fedora-Workstation-Live-x86_64-40-1.14.iso",
  "node_modules/.bin/eslint",
  "./build/Release/app.AppImage",
  "../docs/design/main-window.html",
  "docs/design/tokens.css",
  ".github/workflows/refresh-numbers.yml",
  "Cargo.lock",
  "CHANGELOG.md",
  "requirements-dev.txt",
  "meeting-notes_2024-01-15.md",
  "backup-2024-01-15T10-30-00Z.sql.gz",
  "/dev/nvme0n1p2",
  "/sys/class/backlight/intel_backlight/brightness",
  "/proc/sys/net/ipv4/ip_forward",
  "/run/user/1000/wayland-0",
  "/mnt/data/Photos/2023/12_December/IMG_4521.HEIC",
  )

B("windows_path",
  r"C:\Users\Mohammed\Documents\Report_2024.docx",
  r"C:\Program Files\Mozilla Firefox\firefox.exe",
  r"D:\Backups\2024-01-15\system.img",
  r"\\fileserver01\share\Projects\Q3\budget_v3.xlsx",
  r"C:\Windows\System32\drivers\etc\hosts",
  r"%APPDATA%\Code\User\settings.json",
  )

B("timestamp",
  "2024-01-15T10:30:00Z",
  "2024-01-15T10:30:00.123456+03:00",
  "2024-01-15 10:30:00",
  "2024-01-15",
  "20240115T103000Z",
  "Mon, 15 Jan 2024 10:30:00 GMT",
  "Mon Jan 15 10:30:00 UTC 2024",
  "15/01/2024 10:30",
  "1705314600",
  "1705314600123",
  "2024-W03-1",
  "10:30:00.123",
  "2024-01-15T10:30:00Z/2024-01-16T10:30:00Z",
  "PT1H30M",
  "Q3-2024",
  )

B("version",
  "v1.4.2",
  "1.4.2",
  "1.4.2-rc.1",
  "v2.0.0-beta.3+build.2024.01.15",
  "3.12.1",
  "Python 3.12.1",
  "GNOME Shell 46.2",
  "6.8.0-45-generic",
  "0.15.13",
  "2024.1.2",
  "ruff 0.15.13",
  "libgtk-4-1 4.14.2+ds-1ubuntu1",
  "v0.0.1-alpha",
  "1.0.0+20240115.git9249ede",
  )

B("git_sha",
  "9249ede",
  "0a4b6e9",
  "9249ede3f1a7c2b8d4e5f60718293a4b5c6d7e8f",
  "cbcb70e4d2a1b9c8e7f6a5b4c3d2e1f0a9b8c7d6",
  "a56e668",
  "HEAD~3",
  "origin/main",
  "feature/sensitive-detector-v2",
  "fix/window-focus-restore-49",
  "9249ede..0a4b6e9",
  )

B("uuid",
  "8f14e45f-ceea-467a-9575-62d9e2b4f3a1",
  "550e8400-e29b-41d4-a716-446655440000",
  "123e4567-e89b-12d3-a456-426614174000",
  "01HZX3Q9K7M2N8P4R6T0V1W5Y3",   # ULID
  "F47AC10B-58CC-4372-A567-0E02B2C3D479",
  "{8f14e45f-ceea-467a-9575-62d9e2b4f3a1}",
  )

B("ip",
  "192.168.1.1",
  "10.0.0.1",
  "172.16.254.3",
  "8.8.8.8",
  "192.168.1.0/24",
  "10.0.0.5:8080",
  "2001:db8::1",
  "fe80::1ff:fe23:4567:890a",
  "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
  "::1",
  "[fe80::1%wlp3s0]",
  "192.168.1.1:22",
  )

B("mac",
  "00:1A:2B:3C:4D:5E",
  "a4:c3:f0:12:34:56",
  "00-1A-2B-3C-4D-5E",
  "001a.2b3c.4d5e",
  )

B("hex_color",
  "#1e1e2e",
  "#CDD6F4",
  "#89b4fa",
  "#F5E0DC80",
  "rgba(30,30,46,0.8)",
  "hsl(240,21%,15%)",
  "0xFF1E1E2E",
  )

B("email",
  "mohammed@example.com",
  "Mohammed.Ahmed+github@example.co.uk",
  "noreply@github.com",
  "support-team_2024@sub.example.org",
  "first.last@Example.COM",
  "user123@mail.example.io",
  "\"Mohammed Ahmed\" <mohammed@example.com>",
  )

B("phone",
  "+966501234567",
  "+1 (415) 555-2671",
  "+44 20 7946 0958",
  "0501234567",
  "(011) 4567-8901",
  "+1-415-555-2671",
  "555-0123",
  "*100#",
  )

B("shell",
  "./configure",
  "./configure --prefix=/usr --enable-wayland",
  "make -j8",
  "sudo apt install wl-clipboard",
  "git fetch origin --prune",
  "git rebase -i HEAD~3",
  "xvfb-run -a /usr/bin/python3 -m pytest -q",
  "CLIPMAN_REQUIRE_GTK4=1 xvfb-run -a /usr/bin/python3 -m pytest -q",
  "ruff check clipman tests",
  "systemctl --user restart clipman.service",
  "journalctl -u clipman -f --since=-1h",
  "ls -la",
  "docker compose up -d --build",
  "pip install -e .[dev]",
  "--enable-feature=wayland",
  "-Dbuildtype=release",
  "gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'",
  "chmod 0700 ~/.local/share/clipman",
  "curl -fsSL https://get.docker.com | sh",
  "npx --yes create-vite@5.2.0 my-app",
  "kill -9 12345",
  "ssh mohammed@db-01.prod.internal",
  "scp ./dist/clipman-1.4.2.tar.gz mohammed@10.0.0.5:/tmp/",
  "rsync -avz --delete ~/Photos/ /mnt/backup/Photos/",
  )

B("identifier",
  "handleNewText",
  "ClipboardMonitor",
  "_is_sensitive",
  "MAX_TEXT_SIZE",
  "MIN_EVENT_INTERVAL",
  "clipboard_monitor.py",
  "Gdk.Clipboard.set()",
  "Adw.PreferencesWindow",
  "Meta.Window.hide_from_window_list",
  "org.gnome.Shell.Extensions",
  "io.github.MohammedEl-sayedAhmed.clipman",
  "clipman@clipman.com",
  "Optional[Dict[str, Any]]",
  "List[Tuple[int, str]]",
  "Callable[[str], bool]",
  "std::vector<uint8_t>",
  "GLib.timeout_add_seconds",
  "XDG_RUNTIME_DIR",
  "WAYLAND_DISPLAY",
  "PyGObject",
  "Wl_Paste_Watcher",
  "test_url_not_sensitive",
  "__init__.py",
  "useState<boolean>(false)",
  "self._restart_count",
  "getElementById",
  "kDefaultTimeoutMs",
  "HTTP_401_UNAUTHORIZED",
  "ENOENT",
  "SIGTERM",
  )

B("package_spec",
  "ruff==0.15.13",
  "PyGObject>=3.46,<4",
  "pytest~=8.2",
  "@types/node@20.11.5",
  "react@18.3.1",
  "org.apache.commons:commons-lang3:3.14.0",
  "serde = \"1.0.197\"",
  "python3-gi (>= 3.46)",
  "clipman[dev]==1.4.2",
  "numpy==1.26.4; python_version < \"3.13\"",
  )

B("docker_tag",
  "python:3.12-slim-bookworm",
  "ghcr.io/mohammedel-sayedahmed/clipman:1.4.2",
  "postgres:16.2-alpine",
  "nginx:1.25.4",
  "registry.example.com:5000/team/app:2024.01.15-abc1234",
  "ubuntu@sha256:1b8d8ff4777f36f19bfe73ee4df61e3a0b789caeff29caa019539ec7c9a57f95",
  "node:20.11.1-bookworm-slim",
  )

B("social",
  "#WaylandClipboard",
  "@MohammedEl-sayedAhmed",
  "@gnome",
  "#GNOME46",
  "u/clipman_dev",
  "#100DaysOfCode",
  "@clipman:matrix.org",
  "r/gnome",
  )

B("shortcut",
  "Ctrl+Shift+V",
  "Super+V",
  "Ctrl+Alt+T",
  "<Super><Shift>v",
  "Ctrl+Shift+Alt+F12",
  "Alt+F2",
  "Shift+Insert",
  "<Primary><Alt>Delete",
  "Meta+Space",
  "F11",
  )

B("license",
  "Apache-2.0",
  "GPL-3.0-or-later",
  "MIT",
  "LGPL-2.1-only",
  "BSD-3-Clause",
  "CC-BY-SA-4.0",
  "SPDX-License-Identifier: Apache-2.0",
  "MPL-2.0",
  )

B("tracking",
  "1Z999AA10123456784",
  "9400111899223456789012",
  "RB123456789SA",
  "JD014600003456789012",
  "ORD-2024-000123",
  "INV-2024-01-0042",
  "TKT-98765",
  "PO#20240115-7",
  "SA-2024-8891",
  "AWB 176-12345675",
  "RMA20240115A",
  )

B("isbn",
  "978-0-306-40615-7",
  "9780306406157",
  "ISBN 0-306-40615-2",
  "978-1-59327-950-3",
  )

B("flight",
  "SV1234",
  "BA0117",
  "EK203",
  "LH 1234",
  "6E2341",
  "RUH-LHR",
  "PNR: X7K9QZ",
  "Seat 23A",
  )

B("plate",
  "ABC-1234",
  "KA 01 AB 1234",
  "B 1234 ABC",
  "7XYZ123",
  "RKD 2345",
  )

B("coordinates",
  "24.7136,46.6753",
  "24.7136° N, 46.6753° E",
  "51.5074,-0.1278",
  "geo:24.7136,46.6753",
  "24°42'49\"N 46°40'31\"E",
  "-33.8688, 151.2093",
  )

B("currency",
  "$1,234.56",
  "SAR 4,999.00",
  "€19.99",
  "£3,450",
  "1.234,56 €",
  "USD 250,000.00",
  "¥12,800",
  "$0.99/mo",
  "1,000,000",
  "3.14159",
  "-12.5%",
  "1e-9",
  "0xDEADBEEF",
  "0b10110011",
  "0o755",
  )

B("model_number",
  "RTX4090",
  "RTX 4090",
  "GeForce RTX 4070 Ti Super",
  "i7-13700K",
  "Ryzen 9 7950X3D",
  "ThinkPad X1 Carbon Gen 11",
  "WD_BLACK SN850X 2TB",
  "SM-S928B",
  "iPhone 15 Pro Max",
  "A2849",
  "TL-WR841N",
  "LG 27GP850-B",
  "B550M-PLUS",
  "USB-C",
  "Wi-Fi 6E",
  )

B("ssid",
  "Mohammed_5G",
  "HomeNet-2.4GHz",
  "STC-Fiber_A1B2",
  "TP-LINK_5C3D",
  "Cafe Free WiFi",
  "eduroam",
  "AndroidAP-7f3e",
  )

B("hostname",
  "db-01.prod.internal",
  "web-03.eu-west-1.example.net",
  "localhost",
  "mohammed-thinkpad",
  "ip-10-0-0-5.ec2.internal",
  "k8s-node-pool-a1b2c3-xyz9",
  "smtp.gmail.com:587",
  "gitlab.example.com:2222",
  "printer-HP-LaserJet-M404n.local",
  "router.asus.com",
  )

B("link_scheme",
  "mailto:mohammed@example.com",
  "mailto:mohammed@example.com?subject=Clipman%20v1.4.2%20release",
  "tel:+966501234567",
  "tel:+1-415-555-2671",
  "sms:+966501234567?body=Hi",
  "vscode://file/home/mohammed/clipman/window.py:1187:5",
  "slack://channel?team=T01ABCDE&id=C02FGHIJ",
  "spotify:track:4uLU6hMCjMI75M1A2tKUQC",
  "magnet:?xt=urn:btih:c12fe1c06bba254a9dc9f519b335aa7c1367a88a",
  "geo:0,0?q=Riyadh",
  "obsidian://open?vault=Notes&file=2024-01-15",
  "data:text/plain;base64,aGVsbG8gd29ybGQ=",
  )

B("base64_short",
  b64("hello world"),                  # aGVsbG8gd29ybGQ=
  b64("clipman rocks"),
  b64("Mohammed"),
  b64("2024-01-15 meeting notes"),
  b64("The quick brown fox"),
  "SGVsbG8sIFdvcmxkIQ==",              # Hello, World!
  )

B("word",
  "don't",
  "we'll",
  "O'Brien",
  "Antidisestablishmentarianism",
  "Pneumonoultramicroscopicsilicovolcanoconiosis",
  "Donaudampfschifffahrtsgesellschaft",
  "supercalifragilisticexpialidocious",
  "Al-Riyadh",
  "Saint-Étienne",
  "naïve",
  "Zürich",
  "مرحبا",
  "مدير_الحافظة",
  "こんにちは世界",
  "Mohammed",
  "GNOME",
  "e.g.",
  "etc.",
  "COVID-19",
  "3D-printed",
  "24/7",
  "9-to-5",
  "W-2",
  "B2B",
  "Wi-Fi",
  "T-Mobile",
  "Ph.D.",
  "AC/DC",
  "Ctrl",
  )

B("non_latin",
  "مدير الحافظة لسطح مكتب جنوم",
  "剪贴板管理器",
  "クリップボード履歴を消去する",
  "클립보드 관리자 설정",
  "Менеджер буфера обмена для Wayland",
  "Διαχειριστής προχείρου",
  "東京都渋谷区神南1-19-11",
  "١٢٣٤٥٦٧٨٩٠",
  )

B("mixed_script",
  "Clipman — مدير الحافظة لـ GNOME 46",
  "Wayland (ويلاند) protocol",
  "GNOME 46 での動作を確認済み",
  "版本 v1.4.2 已发布",
  "Riyadh الرياض 2024-01-15",
  "Ctrl+Shift+V で履歴を開く",
  "تحديث clipman-1.4.2 على Ubuntu 24.04",
  "Zürich–München ICE 2024",
  )

B("checksum",
  "d41d8cd98f00b204e9800998ecf8427e",
  "da39a3ee5e6b4b0d3255bfef95601890afd80709",
  "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  ubuntu-24.04.1-desktop-amd64.iso",
  "sha256:" + rand(HEX, 64),
  "sha512-" + rand(B64, 86) + "==",
  "SHA256:" + rand(B64URL, 43),
  "SHA256:" + rand(B64URL, 43) + " mohammed@thinkpad (ED25519)",
  "4AEE 18F8 3AFD EB23 D3F5 0F8B 2E5A 8C03 1B2C 6D7E",
  "0x2E5A8C031B2C6D7E",
  "3f4e2a1b9c8d",
  "crc32: 0x1A2B3C4D",
  )

B("public_id",
  "dQw4w9WgXcQ",
  "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "B0BSHF7WHW",
  "https://discord.gg/gnome",
  "https://discord.gg/Ab3xY9zQ",
  "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
  "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
  "1HGCM82633A004352",
  "SA0380000000608010167519",
  "GB82 WEST 1234 5698 7654 32",
  "RJHISARI",
  "G-ABC123XYZ4",
  "UA-12345678-1",
  "clipman-web-7d9f8b6c5d-x2k9q",
  "i-0abcd1234efgh5678",
  "arn:aws:s3:::clipman-backups/2024/01/15/history.db",
  "vpc-0a1b2c3d4e5f67890",
  "projects/clipman-prod/topics/clips",
  "ami-0c55b159cbfafe1f0",
  )

B("imei",
  "356938035643809",
  "IMEI: 490154203237518",
  )

B("env_placeholder",
  "PASSWORD=",
  "SECRET_KEY=",
  "DB_PASSWORD=${DB_PASSWORD}",
  "API_KEY=<your-api-key>",
  "OPENAI_API_KEY=$OPENAI_API_KEY",
  "npm_config_prefix=~/.npm-global",
  "npm_config_registry=https://registry.npmjs.org/",
  "WAYLAND_DISPLAY=wayland-0",
  "CLIPMAN_REQUIRE_GTK4=1",
  "GTK_DEBUG=interactive",
  "PYTHONPATH=/home/mohammed/Desktop/playground/clipman",
  "DATABASE_URL=postgresql://localhost/clipman_dev",
  )

B("code",
  "^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$",
  "f\"{self.host}:{self.port}\"",
  "[clipman](https://github.com/MohammedEl-sayedAhmed/clipman)",
  "Hello%20World%21",
  "0 6 * * *",
  "%Y-%m-%dT%H:%M:%SZ",
  "sk-fading-circle",
  "@define-color clip_dim #6c7086;",
  "SELECT COUNT(*) FROM entries;",
  "git@github.com:MohammedEl-sayedAhmed/clipman.git",
  "ssh://git@github.com/MohammedEl-sayedAhmed/clipman.git",
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "\\u{1F600}",
  "rgba(var(--accent-rgb), .32)",
  "const {data} = await res.json();",
  "x86_64-linux-gnu",
  "aarch64-unknown-linux-musl",
  "application/vnd.api+json; charset=utf-8",
  "text/x-python3",
  )

B("sentence_keyword",
  "Forgot your password? Click here to reset it.",
  "Your one-time passcode expires in 10 minutes.",
  "Please rotate the API key before the release.",
  "The token was revoked yesterday, ask IT for a new one.",
  "Signed-off-by: Mohammed Ahmed <mohammed@example.com>",
  "Password must be at least 12 characters long.",
  "Set SECRET_KEY in the environment, never in the repo.",
  "Get:1 http://archive.ubuntu.com/ubuntu noble InRelease [256 kB]",
  )

B("multiline_config",
  "[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n[remote \"origin\"]\n\turl = git@github.com:MohammedEl-sayedAhmed/clipman.git\n\tfetch = +refs/heads/*:refs/remotes/origin/*",
  "Host db-01\n    HostName 10.0.0.5\n    User mohammed\n    IdentityFile ~/.ssh/id_ed25519\n    Port 22",
  "version: \"3.9\"\nservices:\n  db:\n    image: postgres:16.2-alpine\n    ports:\n      - \"5432:5432\"",
  "[Desktop Entry]\nName=Clipman\nExec=clipman --daemon\nIcon=io.github.MohammedEl-sayedAhmed.clipman\nType=Application",
  "# .env.example\nDATABASE_URL=\nSECRET_KEY=\nDEBUG=true\n",
  )

B("long_digits_non_luhn", *long_digits)

B("sentence",
  "hello world",
  "hello clipboard",
  "Can you send me the report by Friday?",
  "Meeting moved to 3pm, same room.",
  "Thanks, I'll take a look this afternoon.",
  "The quick brown fox jumps over the lazy dog.",
  "Please review PR #268 when you get a chance.",
  "Ordered the RTX 4090 for $1,599.99 — arrives Tuesday.",
  "Version 1.4.2 fixes the focus-restore bug on GNOME 49.",
  "My flight lands at 10:30 on 2024-01-15, terminal 3.",
  "See https://github.com/MohammedEl-sayedAhmed/clipman for details.",
  "Run `ruff check clipman tests` before pushing.",
  "Error: ENOENT: no such file or directory, open '/etc/clipman.conf'",
  "TypeError: Cannot read properties of undefined (reading 'length')",
  "warning: unused variable `count` (line 42)",
  "Traceback (most recent call last):",
  "FAILED tests/test_window.py::test_focus - AssertionError",
  "Copied 3 files to /mnt/backup in 0.42s",
  "Total: 12 passed, 1 skipped in 3.21s",
  "Wi-Fi password is on the fridge.",
  "Call me at +966 50 123 4567 after 6.",
  "Ubuntu 24.04 LTS (Noble Numbat) — released April 25, 2024",
  "Il fait beau aujourd'hui à Paris.",
  "الاجتماع غداً في الساعة العاشرة صباحاً",
  "Der schnelle braune Fuchs springt über den faulen Hund.",
  "1. Open Settings 2. Go to Keyboard 3. Add Ctrl+Shift+V",
  "SELECT id, created_at FROM entries WHERE sensitive = 1 ORDER BY created_at DESC LIMIT 20;",
  "def handle_new_text(self, text: str) -> None:",
  "const items = await db.query('SELECT * FROM clips');",
  "if err != nil { return fmt.Errorf(\"read: %w\", err) }",
  "Fixes #42. Also tightens the CSS selector for the search bar.",
  "feat(monitor): replace character-class heuristic with shape-based rules",
  "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
  "OK",
  "Yes, sounds good!",
  )

B("multiline",
  "def _is_sensitive(text: str) -> bool:\n    t = text.strip()\n    if not t:\n        return False\n    return any(t.startswith(p) for p in _TOKEN_PREFIXES)\n",
  "{\n  \"name\": \"clipman\",\n  \"version\": \"1.4.2\",\n  \"history_limit\": 500,\n  \"auto_clear_seconds\": 30\n}",
  "DEBUG=true\nLOG_LEVEL=info\nPORT=8080\nNODE_ENV=production\n",
  "# TODO\n- [ ] rebase onto main\n- [x] fix CSS selector\n- [ ] screenshot-verify\n",
  "name: CI\non:\n  push:\n    branches: [main]\njobs:\n  test:\n    runs-on: ubuntu-24.04\n",
  "Hi Sara,\n\nAttached is the Q3 report (Report_2024-Q3_Final_v2.docx).\nLet me know if anything is missing.\n\nBest,\nMohammed",
  "$ git log --oneline -3\n9249ede chore(numbers): refresh marketing counters (#268)\n0a4b6e9 chore(numbers): refresh marketing counters (#267)\n9f3b1a6 chore(numbers): refresh marketing counters (#266)",
  "Traceback (most recent call last):\n  File \"clipman/window.py\", line 1187, in _cleanup_sensitive\n    self.db.purge_sensitive(older_than=30)\nAttributeError: 'NoneType' object has no attribute 'purge_sensitive'",
  "id,created_at,type\n1,2024-01-15T10:30:00Z,text\n2,2024-01-15T10:31:12Z,image\n3,2024-01-15T10:35:44Z,text",
  "<div class=\"clip-row\" data-id=\"42\">\n  <span class=\"clip-dim\">2024-01-15 10:30</span>\n</div>",
  "[Unit]\nDescription=Clipman clipboard daemon\nAfter=graphical-session.target\n\n[Service]\nExecStart=/usr/bin/clipman --daemon\nRestart=on-failure",
  "line1\nline2",
  "Shopping:\n- milk\n- eggs\n- 2x AA batteries\n- HDMI 2.1 cable",
  "SELECT id, content_text\nFROM entries\nWHERE created_at > '2024-01-15'\nORDER BY id DESC;",
  "@import url('tokens.css');\n\n.clip-dim { color: @clip_dim; }\n.type-text { color: @type_text; }",
  "import os\nimport sys\n\nsys.path.insert(0, os.path.dirname(__file__))\n",
  "Steps to reproduce:\n1. Copy a URL with digits, e.g. https://youtu.be/dQw4w9WgXcQ\n2. Wait 30 s\n3. The clip is gone",
  "\"Screenshot from 2024-01-15 10-30-00.png\"\n\"Screenshot from 2024-01-15 10-31-07.png\"",
  "export PATH=\"$HOME/.local/bin:$PATH\"\nexport EDITOR=vim\nexport WAYLAND_DISPLAY=wayland-0",
  )


# Secret
secret = []


def S(cat, *texts):
    for t in texts:
        secret.append({"text": t, "category": cat})


ghp = "ghp_" + rand(ALNUM, 36)
gho = "gho_" + rand(ALNUM, 36)
ghs = "ghs_" + rand(ALNUM, 36)
ghr = "ghr_" + rand(ALNUM, 36)
ghu = "ghu_" + rand(ALNUM, 36)
gh_pat = "github_pat_" + rand(ALNUM, 22) + "_" + rand(ALNUM, 59)
assert len(ghp) == 40 and len(gh_pat) == 93
S("github_token", ghp, gho, ghs, ghr, ghu, gh_pat)

akia = ["AKIA" + rand(UPDIG, 16) for _ in range(3)]
asia = "ASIA" + rand(UPDIG, 16)
for k in akia:
    assert len(k) == 20
S("aws_access_key_id", *akia, asia)

aws_secret = [rand(B64, 40) for _ in range(3)]
S("aws_secret_access_key", *aws_secret,
  "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")

S("stripe",
  "sk_live_" + rand(ALNUM, 24),
  "sk_live_51" + rand(ALNUM, 97),
  "pk_live_" + rand(ALNUM, 24),
  "sk_test_" + rand(ALNUM, 24),
  "rk_live_" + rand(ALNUM, 24),
  "whsec_" + rand(ALNUM, 32),
  )

S("slack",
  "xoxb-" + rand(string.digits, 13) + "-" + rand(string.digits, 13) + "-" + rand(ALNUM, 24),
  "xoxp-" + rand(string.digits, 12) + "-" + rand(string.digits, 12) + "-" + rand(string.digits, 13) + "-" + rand(HEX, 32),
  "xoxa-2-" + rand(string.digits, 12) + "-" + rand(string.digits, 12) + "-" + rand(ALNUM, 24),
  "https://hooks.slack.com/services/T" + rand(UPDIG, 8) + "/B" + rand(UPDIG, 10) + "/" + rand(ALNUM, 24),
  )

goog = ["AIza" + rand(B64URL, 35) for _ in range(2)]
for g in goog:
    assert len(g) == 39
S("google_api_key", *goog)

S("openai",
  "sk-proj-" + rand(ALNUM + "-_", 74) + "T3BlbkFJ" + rand(ALNUM + "-_", 74),
  "sk-" + rand(ALNUM, 48),
  "sk-ant-api03-" + rand(B64URL, 93) + "AA",
  )

S("npm_token",
  "npm_" + rand(ALNUM, 36),
  "//registry.npmjs.org/:_authToken=npm_" + rand(ALNUM, 36),
  )

S("pypi_token",
  "pypi-" + "AgEIcHlwaS5vcmc" + rand(B64URL, 150),
  )

S("huggingface_token",
  "hf_" + rand(ALNUM, 34),
  )


def jwt(payload):
    h = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    p = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    s = rand(B64URL, 43)
    return f"{h}.{p}.{s}"


S("jwt",
  jwt('{"sub":"1234567890","name":"Mohammed","iat":1705314600}'),
  jwt('{"iss":"https://auth.example.com","exp":1705318200,"scope":"read write"}'),
  "eyJhbGciOiJSUzI1NiIsImtpZCI6ImFiYzEyMyJ9." + rand(B64URL, 120) + "." + rand(B64URL, 342),
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
  )

S("pem_private_key",
  "-----BEGIN RSA " + "PRIVATE KEY-----\n" + "\n".join(rand(B64, 64) for _ in range(6)) + "\n" + rand(B64, 40) + "=\n-----END RSA PRIVATE KEY-----",
  "-----BEGIN " + "PRIVATE KEY-----\n" + "\n".join(rand(B64, 64) for _ in range(4)) + "\n-----END PRIVATE KEY-----",
  "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n" + rand(B64, 70) + "\n-----END OPENSSH PRIVATE KEY-----",
  "-----BEGIN EC " + "PRIVATE KEY-----\nMHcCAQEEI" + rand(B64, 55) + "\n" + rand(B64, 64) + "\n-----END EC PRIVATE KEY-----",
  "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----\n\n" + "\n".join(rand(B64, 64) for _ in range(3)) + "\n-----END PGP PRIVATE KEY BLOCK-----",
  "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg...",
  )

S("ssh_public_key",
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" + rand(B64, 43) + " mohammed@thinkpad",
  "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQ" + rand(B64, 370) + "= mohammed@thinkpad",
  "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC...",
  )

S("connection_string",
  "postgresql://clipman:" + rand(ALNUM, 16) + "@db-01.prod.internal:5432/clipman",
  "postgres://admin:s3cr3tP%40ss@10.0.0.5/app",
  "mysql://root:" + rand(ALNUM, 12) + "@127.0.0.1:3306/wordpress",
  "mongodb+srv://appuser:" + rand(ALNUM, 20) + "@cluster0.abc12.mongodb.net/prod?retryWrites=true&w=majority",
  "mongodb://admin:secret@cluster.example.com",
  "redis://:" + rand(ALNUM, 24) + "@redis.example.com:6379/0",
  "rediss://default:" + rand(ALNUM, 32) + "@eu1-clip-12345.upstash.io:6379",
  "amqp://guest:" + rand(ALNUM, 14) + "@rabbit.internal:5672/",
  "mssql://sa:" + rand(ALNUM + "!#", 14) + "@sqlserver.internal:1433/master",
  "Server=db.example.com;Database=app;User Id=sa;Password=" + rand(ALNUM, 16) + ";",
  )

for text, cat in card_items:
    S(cat, text)

S("env_secret",
  "API_KEY=" + rand(ALNUM, 32),
  "PASSWORD=" + rand(ALNUM + "!@#", 16),
  "DB_PASSWORD=" + rand(ALNUM, 20),
  "SECRET_KEY=" + rand(ALNUM + "-_", 50),
  "AWS_SECRET_ACCESS_KEY=" + aws_secret[0],
  "STRIPE_SECRET_KEY=sk_live_" + rand(ALNUM, 24),
  "GITHUB_TOKEN=" + ghp,
  "OPENAI_API_KEY=sk-" + rand(ALNUM, 48),
  "export DATABASE_URL=postgresql://app:" + rand(ALNUM, 18) + "@localhost/app",
  "JWT_SECRET=\"" + rand(ALNUM, 40) + "\"",
  "HEROKU_API_KEY=" + "-".join((rand(HEX, 8), rand(HEX, 4), rand(HEX, 4), rand(HEX, 4), rand(HEX, 12))),
  "DEBUG=false\nSECRET_KEY=" + rand(ALNUM, 40) + "\nALLOWED_HOSTS=*",
  "password: " + rand(ALNUM + "!@#$", 16),
  "passwd=" + rand(ALNUM, 14),
  )

S("bearer",
  "Bearer " + rand(B64URL, 64),
  "Authorization: Bearer " + jwt('{"sub":"42","exp":1705318200}'),
  "Authorization: Bearer " + rand(ALNUM, 40),
  "Authorization: Basic " + b64("mohammed:" + rand(ALNUM, 14)),
  "Bearer eyJhbGciOiJIUzI1NiJ9.token",
  "-H 'Authorization: Bearer " + rand(ALNUM, 40) + "'",
  "X-Api-Key: " + rand(ALNUM, 32),
  )

S("basic_auth_url",
  "https://mohammed:" + rand(ALNUM, 16) + "@git.example.com/team/repo.git",
  "http://admin:" + rand(ALNUM + "!", 12) + "@192.168.1.1/",
  "https://user:" + rand(ALNUM, 20) + "@registry.example.com:5000/v2/",
  "ftp://mohammed:" + rand(ALNUM, 12) + "@ftp.example.com/upload",
  )

S("password",
  "Tr0ub4dor&3xQ!",
  "8f3Kd$2mPq9#vL",
  "MyP@ssw0rd!",
  "Xk9#mP2$vL5nQ8wR",
  "gH7!kL9@pQ2#sT4$vW6",
  "N7v!eR2#qP9xL4mZ8w",
  "Qz9$Wx3!Er7&Ty2*",
  "aB3$dE5^gH7*jK9(",
  "pW7#kD2!mX9$zQ4&vB6%nH8",
  "Uj4!Lp9#Rt2$Wq7^Yx5&Zc8*",
  "9mK#2pQ$7vL!4xR&8zT",
  "L4!w9Kd#Pq2$Vm7&Xz",
  "correcthorsebatterystaple1!X",
  "kX3vT9mQ2pL7nR4wY8zB5cD1",
  "Password123!",
  "Summer2024!!",
  "Admin@12345",
  "P@ssw0rd2024#",
  )

S("passphrase",
  "correct-Horse7-battery!Staple",
  "Blue$Whale-Dances_42",
  "coffee&Donuts#0730",
  "Correct-Horse-Battery-Staple-2024!",
  "Purple.Elephant.Runs.Fast.99",
  "Winter_Is_C0ming!2024",
  )

S("totp_secret",
  "otpauth://totp/Example:mohammed@example.com?secret=" + rand(B32, 32) + "&issuer=Example",
  "otpauth://totp/GitHub:mohammed?secret=" + rand(B32, 16) + "&issuer=GitHub&algorithm=SHA1&digits=6&period=30",
  "TOTP_SECRET=" + rand(B32, 32),
  "secret: " + " ".join(rand(B32, 4) for _ in range(8)),
  )

S("twilio",
  "SK" + rand(HEX, 32),
  "AC" + rand(HEX, 32) + ":" + rand(HEX, 32),
  )

S("sendgrid",
  "SG." + rand(B64URL, 22) + "." + rand(B64URL, 43),
  "SG." + rand(B64URL, 22) + "." + rand(B64URL, 43),
  )

S("azure",
  "DefaultEndpointsProtocol=https;AccountName=clipmanstore;AccountKey=" + rand(B64, 86) + "==;EndpointSuffix=core.windows.net",
  "Endpoint=sb://clipman.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=" + rand(B64, 43) + "=",
  rand(ALNUM, 3) + "8Q~" + rand(ALNUM + "_-.~", 34),   # Entra client secret
  )

S("gcp",
  "{\n  \"type\": \"service_account\",\n  \"project_id\": \"clipman-prod\",\n  \"private_key_id\": \"" + rand(HEX, 40) + "\",\n  \"private_key\": \"-----BEGIN PRIVATE KEY-----\\n" + rand(B64, 64) + "\\n-----END PRIVATE KEY-----\\n\",\n  \"client_email\": \"svc@clipman-prod.iam.gserviceaccount.com\"\n}",
  "ya29." + rand(B64URL, 120),
  "1//0" + rand(B64URL, 100),
  )

S("heroku",
  "HEROKU_API_KEY=" + "-".join((rand(HEX, 8), rand(HEX, 4), rand(HEX, 4), rand(HEX, 4), rand(HEX, 12))),
  "heroku_api_key: " + "-".join((rand(HEX, 8), rand(HEX, 4), rand(HEX, 4), rand(HEX, 4), rand(HEX, 12))),
  )

S("private_ip_credentials",
  "admin:" + rand(ALNUM + "!", 12) + "@192.168.1.1",
  "ssh://root:" + rand(ALNUM, 14) + "@10.0.0.5:22",
  "smb://mohammed:" + rand(ALNUM, 12) + "@fileserver01/share",
  "vnc://:" + rand(ALNUM, 10) + "@192.168.1.50:5900",
  "mysql -h 10.0.0.5 -u root -p" + rand(ALNUM, 14),
  )

S("other_vendor",
  "dop_v1_" + rand(HEX, 64),
  "glpat-" + rand(ALNUM + "-_", 20),
  "shpat_" + rand(HEX, 32),
  "sq0atp-" + rand(B64URL, 22),
  "lin_api_" + rand(ALNUM, 40),
  "figd_" + rand(B64URL, 40),
  "dckr_pat_" + rand(B64URL, 27),
  "EAACEdEose0cBA" + rand(ALNUM, 150),
  "sk-or-v1-" + rand(HEX, 64),
  "M" + rand(B64URL, 23) + "." + rand(B64URL, 6) + "." + rand(B64URL, 27),
  rand(string.digits, 10) + ":AA" + rand(B64URL, 33),
  )


def strong(alphabet, n):
    """Random password that uses every class its alphabet offers."""
    classes = [c for c in (string.ascii_lowercase, string.ascii_uppercase,
                           string.digits, string.punctuation)
               if any(ch in alphabet for ch in c)]
    while True:
        pw = rand(alphabet, n)
        if all(any(ch in c for ch in pw) for c in classes):
            return pw


# The two bare alphanumeric entries are the acknowledged hard case: by
# shape they equal a Google Docs id.  A detector that misses them pays
# only recall, which is the intended trade-off.
S("password_generated",
  strong(ALNUM + "!@#$%^&*", 12),
  strong(ALNUM + "!@#$%^&*", 16),
  strong(ALNUM + "!@#$%^&*()-_=+", 20),
  strong(ALNUM + "!@#$%^&*", 24),
  strong(ALNUM + "!@#$%^&*()-_=+[]{}", 32),
  strong(ALNUM + "!@#$%^&*", 40),
  strong(ALNUM, 20),
  strong(ALNUM, 32),
  )

S("multiline_secret",
  "[default]\naws_access_key_id = " + akia[0] + "\naws_secret_access_key = " + aws_secret[1],
  "{\n  \"api_key\": \"" + rand(ALNUM, 32) + "\",\n  \"endpoint\": \"https://api.example.com\"\n}",
  "database:\n  host: db-01.prod.internal\n  user: clipman\n  password: " + rand(ALNUM + "!#", 18),
  "machine api.github.com\n  login MohammedEl-sayedAhmed\n  password " + ghp,
  "export STRIPE_SECRET_KEY=sk_live_" + rand(ALNUM, 24) + "\nexport STRIPE_WEBHOOK_SECRET=whsec_" + rand(ALNUM, 32),
  )


# Sanity checks
def luhn_runs(text, lo=13, hi=19):
    """Delimited digit runs of card length that pass Luhn.

    Single spaces or dashes between digits are allowed.  The run must
    not touch another digit on either side, which is how a card rule
    scans real text: a 22-digit IBAN body is not a card candidate.
    """
    import re
    pattern = r"(?<!\d)\d(?:[ -]?\d){%d,%d}(?!\d)" % (lo - 1, hi - 1)
    hits = []
    for m in re.finditer(pattern, text):
        ds = re.sub(r"[ -]", "", m.group())
        if lo <= len(ds) <= hi and luhn_ok(ds):
            hits.append(m.group())
    return hits


for item in benign:
    hits = luhn_runs(item["text"])
    if item["category"] == "imei":
        # IMEIs carry a Luhn check digit by design.
        assert hits, f"IMEI item is not Luhn-valid: {item['text']!r}"
        continue
    assert not hits, f"benign item contains Luhn-valid card-length run: {item['text']!r} -> {hits}"

seen = set()
for bucket in (benign, secret):
    for item in bucket:
        assert item["text"] not in seen, f"duplicate: {item['text']!r}"
        seen.add(item["text"])

assert len(benign) >= 200, len(benign)
assert len(secret) >= 80, len(secret)

if __name__ == "__main__":
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"benign": benign, "secret": secret}, fh, ensure_ascii=False, indent=1)

    print(f"benign={len(benign)} secret={len(secret)} -> {OUT}")
    print("benign categories:", dict(sorted(Counter(i['category'] for i in benign).items())))
    print("secret categories:", dict(sorted(Counter(i['category'] for i in secret).items())))
