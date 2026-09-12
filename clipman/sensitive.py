"""Detect clips that contain a known secret shape.

A flagged clip is masked and then deleted after the sensitive timeout.
So a false positive means data loss, while a false negative only leaves
a secret in the local history, which 0700 file permissions already
protect. For that reason the detector only matches known shapes and
never guesses from randomness or character classes. It knows vendor
tokens with a unique prefix, private and SSH keys, JSON Web Tokens, URLs
with a password inside, labelled values such as ``PASSWORD=...``,
``Authorization`` headers, card numbers that pass Luhn, TOTP seeds, and
a few command lines that take a password inline.

A bare password with no label is not detected on purpose. Nothing tells
``Tr0ub4dor&3`` apart from a Wi-Fi name or a licence key, and the old
rule that tried to guess deleted URLs, file names and timestamps.
"""

import base64
import re

__all__ = ["is_sensitive"]

_A = re.ASCII

# Only the first 64 KB is scanned; the cost is about 0.5 ms per KB.
_SCAN_LIMIT = 64 * 1024

# Tokens never sit inside a longer identifier.
_LB = r"(?<![A-Za-z0-9_])"
_RB = r"(?![A-Za-z0-9])"

# Vendor tokens: a namespaced prefix plus the documented alphabet.
# Length floors sit below the documented lengths; vendors lengthen them.
_VENDOR_PATTERNS = [
    # GitHub classic and fine-grained tokens.
    r"gh[pousr]_[A-Za-z0-9]{12,}",
    r"github_pat_[A-Za-z0-9_]{16,}",
    # AWS access key ids: type prefix, then 16 chars with a digit.
    r"(?:AKIA|ASIA|ABIA|ACCA)(?=[A-Z]*\d)[A-Z0-9]{16}",
    # Stripe secret, restricted, publishable and webhook keys.
    r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}",
    r"whsec_[A-Za-z0-9]{24,}",
    # Slack tokens, app tokens and incoming webhooks.
    r"xox[abopers]-[A-Za-z0-9-]{10,}",
    r"xapp-\d-[A-Z0-9]+-\d+-[a-z0-9]{20,}",
    r"hooks\.slack\.com/services/T[A-Z0-9]{6,}/B[A-Z0-9]{6,}/" +
    r"[A-Za-z0-9]{16,}",
    # Google API keys, OAuth access and refresh tokens, client secrets.
    r"AIza[0-9A-Za-z_-]{15,}",
    r"ya29\.[0-9A-Za-z_-]{20,}",
    r"1//0[0-9A-Za-z_-]{30,}",
    r"GOCSPX-[0-9A-Za-z_-]{20,}",
    # npm, PyPI (fixed macaroon location prefix) and Hugging Face.
    r"npm_[A-Za-z0-9]{16,}",
    r"pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{30,}",
    r"hf_[A-Za-z0-9]{30,}",
    # Twilio API key SID; account SID only when paired with its token.
    r"SK[0-9a-f]{32}",
    r"AC[0-9a-f]{32}:[0-9a-f]{32}",
    # SendGrid.
    r"SG\.[A-Za-z0-9_-]{16,32}\.[A-Za-z0-9_-]{32,64}",
    # Azure AD client secrets carry a fixed "7Q~" or "8Q~" marker.
    r"[A-Za-z0-9_.~-]{3}[78]Q~[A-Za-z0-9_.~-]{31,34}",
    # DigitalOcean, GitLab, Shopify, Square, Linear, Figma, Docker Hub.
    r"do[opr]_v1_[a-f0-9]{64}",
    r"glpat-[A-Za-z0-9_-]{20,}",
    r"shp(?:at|ss|ca|pa)_[a-fA-F0-9]{32}",
    r"sq0(?:atp|csp)-[A-Za-z0-9_-]{22,}",
    r"lin_api_[A-Za-z0-9]{32,}",
    r"figd_[A-Za-z0-9_-]{32,}",
    r"dckr_pat_[A-Za-z0-9_-]{20,}",
    # Facebook, Telegram bot, Discord bot, Mailchimp.
    r"EAACEdEose0cBA[A-Za-z0-9]{20,}",
    r"\d{8,10}:AA[A-Za-z0-9_-]{33}",
    r"[MN][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,40}",
    r"[a-f0-9]{32}-us\d{1,2}",
    # age identities.
    r"AGE-SECRET-KEY-1[A-Z0-9]{58}",
]
_VENDOR = [re.compile(_LB + p + _RB, _A) for p in _VENDOR_PATTERNS]

# "sk-" is shared by OpenAI-style keys and CSS class names such as
# "sk-fading-circle", so the body must contain a letter and a digit.
_SK_KEY = re.compile(
    _LB + r"sk-(?:[A-Za-z0-9]{1,12}-){0,3}"
    r"(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{12,}",
    _A)

# Private key material; certificates and public keys are not secrets.
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|PuTTY-User-Key-File-\d",
    _A)

# SSH public keys stay sensitive, as the app has always treated them.
_SSH_KEY = re.compile(
    _LB + r"(?:ssh-(?:rsa|dss|ed25519)|ecdsa-sha2-nistp(?:256|384|521)|"
    r"sk-(?:ssh-ed25519|ecdsa-sha2-nistp256)@openssh\.com)"
    r"[ \t]+AAAA[A-Za-z0-9+/]{16,}",
    _A)

# URL with credentials in the authority: scheme://user:pass@host.
_CRED_URL = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9+.-]{1,31}://"
    r"[^\s/:@]{0,128}:[^\s/@]{1,256}@[^\s/@]+",
    _A)

# The same authority without a scheme, as a whole single-line clip.
# Only numeric or localhost hosts qualify; a DNS name looks like mailto.
_BARE_CRED = re.compile(
    r"\A[A-Za-z0-9._-]{1,64}:[^\s@/]{6,}@"
    r"(?:(?:\d{1,3}\.){3}\d{1,3}|localhost)"
    r"(?::\d{1,5})?(?:/\S*)?\Z",
    _A)

# JSON Web Tokens: the first segment must decode to a JOSE header.
_JWT = re.compile(_LB + r"eyJ[A-Za-z0-9_-]{8,}", _A)

# Labelled secrets: the keyword ends the key and "=" or ":" follows.
_KEYWORDS = (
    r"(?:password|passwd|passphrase|passcode|pwd|secret|token|apikey|"
    r"(?:api|private|access|account|secret|app|signing|encryption|"
    r"master|auth)[_-]?key)")
_LABEL = re.compile(
    _KEYWORDS + r"""["']?[ \t]*([=:])[ \t]*["']?([^\s"';,]{8,})""",
    re.I | _A)
_IDENT_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
_LINE_LEAD_CHARS = frozenset(" \t\"'{,[-")

# HTTP Authorization headers and bare Bearer tokens.
_AUTH_HEADER = re.compile(
    r"""(?<![A-Za-z0-9])(?:proxy-)?authorization["']?[ \t]*:[ \t]*["']?"""
    r"(?:(?:bearer|basic|digest|token|negotiate|hmac|oauth|apikey|api-key)"
    r"""[ \t]+)?([^\s"',]{8,})""",
    re.I | _A)
_BEARER = re.compile(_LB + r"""Bearer[ \t]+([^\s"',]{8,})""", _A)

# TOTP seeds: an otpauth URI or a labelled base32 seed, maybe in groups.
_OTPAUTH = re.compile(r"otpauth://[ht]otp/", re.I | _A)
_TOTP_LABEL = re.compile(
    r"""(?<![A-Za-z0-9])(?i:(?:totp|otp|mfa|2fa)?[_-]?secret)["']?[ \t]*"""
    r"""[:=][ \t]*["']?((?:[A-Z2-7]{4}[ -]){3,}[A-Z2-7]{4,}|[A-Z2-7]{16,})"""
    r"(?![A-Za-z0-9])",
    _A)

# Command lines that take a password inline.
_CLI_DASH_P = re.compile(
    r"(?<![A-Za-z0-9])(?:mysql|mysqldump|mysqladmin|mariadb|sshpass)\b"
    r"""[^\n]*?[ \t]-p([^\s"']{6,})""",
    _A)
_CLI_USER_PASS = re.compile(
    r"(?<![A-Za-z0-9])(?:curl|wget|http|https)\b[^\n]*?[ \t]"
    r"""(?:-u|--user|-a|--auth)[ \t=]+["']?([^\s:"']{1,64}:[^\s"']{4,})""",
    _A)
_NETRC = re.compile(
    r"^[ \t]*machine\s+\S+\s+(?:login\s+\S+\s+)?password[ \t]+(\S{6,})",
    re.M | _A)

# Card numbers: 13-19 digits, single spaces or dashes allowed, not part
# of a longer digit run.
_CARD = re.compile(
    r"(?<![A-Za-z0-9])(?<!\d[ -])(\d(?:[ -]?\d){12,18})(?![ -]?\d)(?![A-Za-z])",
    _A)
_CARD_SEPARATORS = str.maketrans("", "", " -")

# Values that are placeholders rather than literal secrets.
_PLACEHOLDER_WORDS = (
    "your", "example", "changeme", "change_me", "change-me", "replace",
    "placeholder", "redacted", "dummy", "sample", "insert", "xxxx",
    "****", "todo", "here",
)
_VALUE_BAD_LEAD = frozenset("$<{[%(~/=*.")


def _plausible_value(value):
    """Return True when ``value`` reads as a literal secret.

    Rejects short values, shell or template expansions, paths, URLs,
    placeholder words and single-character-class values such as a bare
    word, a bare number or an ALL_CAPS variable name.
    """
    value = value.rstrip(".)]}>")
    if len(value) < 8 or value[0] in _VALUE_BAD_LEAD:
        return False
    if "://" in value or "{{" in value or "${" in value:
        return False
    lowered = value.lower()
    if any(word in lowered for word in _PLACEHOLDER_WORDS):
        return False
    core = value.replace("_", "").replace("-", "")
    has_lower = has_upper = has_digit = has_other = False
    for ch in core:
        if "a" <= ch <= "z":
            has_lower = True
        elif "A" <= ch <= "Z":
            has_upper = True
        elif "0" <= ch <= "9":
            has_digit = True
        else:
            has_other = True
    return has_lower + has_upper + has_digit + has_other >= 2


def _is_jose_header(segment):
    """Return True when ``segment`` decodes to a JOSE header."""
    try:
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except ValueError:
        return False
    return raw.lstrip().startswith(b"{") and (
        b'"alg"' in raw or b'"enc"' in raw)


def _has_jwt(text):
    for match in _JWT.finditer(text):
        if _is_jose_header(match.group(0)):
            return True
    return False


def _has_labelled_secret(text):
    """Match ``KEY=VALUE`` or ``key: value`` with a secret-bearing key.

    The "=" form is accepted anywhere except as a URL query parameter,
    where the clip is a URL the user wants to keep. The ":" form needs a
    quoted key (JSON) or a key that starts its line (YAML, headers), so
    prose such as "the secret: consistency" is left alone.
    """
    for match in _LABEL.finditer(text):
        key_start = match.start()
        floor = max(0, key_start - 64)
        while key_start > floor and text[key_start - 1] in _IDENT_CHARS:
            key_start -= 1
        before = text[key_start - 1] if key_start > 0 else "\n"
        if match.group(1) == "=":
            if before in "?&":
                continue
        elif before not in "\"'":
            line_start = text.rfind("\n", 0, key_start) + 1
            lead = text[line_start:key_start]
            if any(ch not in _LINE_LEAD_CHARS for ch in lead):
                continue
        if _plausible_value(match.group(2)):
            return True
    return False


def _has_auth_header(text):
    for regex in (_AUTH_HEADER, _BEARER):
        for match in regex.finditer(text):
            if _plausible_value(match.group(1)):
                return True
    return False


def _has_cli_password(text):
    for match in _CLI_DASH_P.finditer(text):
        if _plausible_value(match.group(1)):
            return True
    if _CLI_USER_PASS.search(text):
        return True
    for match in _NETRC.finditer(text):
        if _plausible_value(match.group(1)):
            return True
    return False


def _has_totp_seed(text):
    if _OTPAUTH.search(text):
        return True
    for match in _TOTP_LABEL.finditer(text):
        if any("2" <= ch <= "7" for ch in match.group(1)):
            return True
    return False


def _luhn_ok(digits):
    total = 0
    for index, ch in enumerate(reversed(digits)):
        value = ord(ch) - 48
        if index & 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _issuer_ok(digits):
    """Check issuer prefix and length for the major card networks.

    Thirteen-digit Visa and Maestro ranges are excluded: both are rare
    today and both widen the false-positive surface.
    """
    n = len(digits)
    p2 = int(digits[:2])
    p3 = int(digits[:3])
    p4 = int(digits[:4])
    if digits[0] == "4":
        return n in (16, 19)
    if 51 <= p2 <= 55 or 2221 <= p4 <= 2720:
        return n == 16
    if p2 in (34, 37):
        return n == 15
    if p4 == 6011 or p2 == 65 or 644 <= p3 <= 649:
        return n in (16, 19)
    if 3528 <= p4 <= 3589 or p2 == 62:
        return 16 <= n <= 19
    if p2 in (36, 38, 39) or 300 <= p3 <= 305:
        return n == 14
    return False


def _has_card_number(text):
    for match in _CARD.finditer(text):
        raw = match.group(1)
        if " " in raw and "-" in raw:
            continue
        digits = raw.translate(_CARD_SEPARATORS)
        if 13 <= len(digits) <= 19 and _luhn_ok(digits) and _issuer_ok(digits):
            return True
    return False


def is_sensitive(text):
    """Return True when ``text`` contains a concrete secret shape."""
    if not text:
        return False
    text = text[:_SCAN_LIMIT].strip()
    if len(text) < 8:
        return False
    for regex in _VENDOR:
        if regex.search(text):
            return True
    if _SK_KEY.search(text) or _PRIVATE_KEY.search(text):
        return True
    if _SSH_KEY.search(text) or _CRED_URL.search(text):
        return True
    if _BARE_CRED.match(text):
        return True
    if _has_jwt(text) or _has_labelled_secret(text):
        return True
    if _has_auth_header(text) or _has_cli_password(text):
        return True
    if _has_totp_seed(text) or _has_card_number(text):
        return True
    return False
