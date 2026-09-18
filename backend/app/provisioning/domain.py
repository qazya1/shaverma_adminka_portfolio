"""Builds a new service's frontend/backend URLs from the admin-supplied
third-level domain label.

    label="индия"  ->  url              = https://xn--d1ahbs6g.xn----8sbwack8bga.xn--p1ai
                        backend_base_url = https://xn--api--t4dxb2b6l.xn----8sbwack8bga.xn--p1ai

The "api-" prefix is applied to the *Unicode* label before punycode
encoding (matching the example given: "а.example-service.рф" and
"api-а.example-service.рф" are both encoded whole, not literal string-prefixed
ACE forms) -- see idna.encode, which IDNA2008-encodes each dot-separated
label of a domain.
"""

import idna


class InvalidDomainLabelError(ValueError):
    """Raised when the admin-supplied third-level label isn't a usable
    domain label."""


def validate_label(label: str) -> None:
    """The admin-supplied label only -- a single domain label, not a
    full domain (no dots). Unicode letters/digits/hyphens; must not
    start or end with a hyphen. idna.encode() enforces the remaining
    IDNA structural rules (total encoded length, "--" in positions 3-4,
    disallowed codepoints, ...) and raises idna.IDNAError for anything
    that slips past this coarser check.
    """

    if not label or len(label) > 63:
        raise InvalidDomainLabelError("label must be 1-63 characters")
    if label.startswith("-") or label.endswith("-"):
        raise InvalidDomainLabelError("label must not start or end with a hyphen")
    if "." in label:
        raise InvalidDomainLabelError("label must be a single domain label, not a full domain")
    if not all(ch == "-" or ch.isalnum() for ch in label):
        raise InvalidDomainLabelError("label may only contain letters, digits, and internal hyphens")


def to_punycode_domain(domain: str) -> str:
    """IDNA2008-encode a full dotted domain (every label), returning the
    all-ASCII form. Raises InvalidDomainLabelError on anything IDNA
    itself rejects (bad structure, disallowed codepoints, ...)."""

    try:
        return idna.encode(domain, uts46=True).decode("ascii")
    except idna.IDNAError as exc:
        raise InvalidDomainLabelError(str(exc)) from exc


def build_service_urls(label: str, zone: str) -> tuple[str, str]:
    """Validate `label` and return (frontend_url, backend_url), both full
    `https://` URLs with punycode-encoded, all-ASCII hosts."""

    validate_label(label)

    frontend_domain = to_punycode_domain(f"{label}.{zone}")
    backend_domain = to_punycode_domain(f"api-{label}.{zone}")

    return f"https://{frontend_domain}", f"https://{backend_domain}"


def domain_from_url(url: str) -> str:
    """Strip the scheme (and any trailing slash) off a `https://host` URL
    -- used wherever only the bare host is needed (nginx server_name)."""

    return url.split("://", 1)[-1].rstrip("/")
