"""Audit current public archive directories; never infer historical eligibility."""

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from pvb24.data.acquisition import NoRedirect, object_write
from pvb24.ids import canonical, digest

BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/"
ALLOWED_PREFIXES = (
    "data/futures/um/monthly/",
    "data/futures/um/daily/",
    "data/futures/um/monthly/klines/",
)
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
MAX_PAGE = 2 * 1024 * 1024


def page_url(prefix, token=None):
    if prefix not in ALLOWED_PREFIXES:
        raise ValueError("Only reviewed directory roots may be inventoried; no archive/date access")
    params = {"list-type": "2", "delimiter": "/", "prefix": prefix, "max-keys": 1000}
    if token is not None:
        params["continuation-token"] = token
    return BUCKET + "?" + urlencode(params)


def public_page(url):
    if not url.startswith(BUCKET + "?"):
        raise ValueError("Official archive catalog endpoint required")
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=30) as response:
        raw = response.read(MAX_PAGE + 1)
    if len(raw) > MAX_PAGE:
        raise ValueError("Catalog page exceeds resource limit")
    return raw


def decode_page(raw, prefix, token=None):
    page_url(prefix, token)  # same root guard for offline decoding
    if len(raw) > MAX_PAGE:
        raise ValueError("Catalog page exceeds resource limit")
    text = raw.decode("utf-8")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("Catalog XML entities are not supported")
    root = ET.fromstring(text)

    def field(name):
        values = root.findall(NS + name)
        if len(values) != 1:
            raise ValueError("Missing or ambiguous catalog field: " + name)
        return values[0].text or ""

    if (
        root.tag != NS + "ListBucketResult"
        or field("Name") != "data.binance.vision"
        or field("Prefix") != prefix
        or field("Delimiter") != "/"
    ):
        raise ValueError("Catalog response identity differs from request")
    returned_token = root.findtext(NS + "ContinuationToken")
    if returned_token != token:
        raise ValueError("Catalog continuation does not match request")
    if root.findall(NS + "Contents"):
        raise ValueError("Directory inventory refuses leaf objects, including dated archives")
    children = []
    for item in root.findall(NS + "CommonPrefixes"):
        fields = item.findall(NS + "Prefix")
        if len(fields) != 1:
            raise ValueError("Missing or ambiguous child prefix")
        child = fields[0].text or ""
        name = child[len(prefix) : -1]
        if (
            not child.startswith(prefix)
            or not child.endswith("/")
            or not name
            or not all(c.isalnum() or c in "_-" for c in name)
        ):
            raise ValueError("Catalog child escapes its single directory level")
        children.append(child)
    if len(set(children)) != len(children):
        raise ValueError("Duplicate catalog child")
    flag = field("IsTruncated")
    if flag not in ("true", "false"):
        raise ValueError("Explicit catalog completeness flag required")
    next_values = root.findall(NS + "NextContinuationToken")
    next_token = next_values[0].text if len(next_values) == 1 else None
    if (flag == "true" and not next_token) or (flag == "false" and next_values):
        raise ValueError("Catalog pagination token inconsistent with completeness")
    if field("KeyCount") != str(len(children)):
        raise ValueError("Catalog item count differs from decoded directory entries")
    return tuple(children), next_token


def inventory(prefix, output, *, fetch=public_page, max_pages=20):
    page_url(prefix)  # validate before network or writes
    if type(max_pages) is not int or not 1 <= max_pages <= 100:
        raise ValueError("Explicit bounded catalog page budget required")
    root = Path(output)
    report = {
        "schema": "PVB24_ARCHIVE_DIRECTORY_INVENTORY_V1",
        "scope": "CURRENT_ARCHIVE_DIRECTORY_METADATA_ONLY",
        "prefix": prefix,
        "started_at": datetime.now(UTC),
        "status": "INCOMPLETE",
        "historical_eligibility_verified": False,
        "historical_rules_verified": False,
        "final_test_access": "LOCKED",
        "archive_objects_read": 0,
        "pages": [],
        "children": [],
    }
    token, tokens, children = None, set(), set()
    try:
        for _ in range(max_pages):
            url = page_url(prefix, token)
            raw = fetch(url)
            if len(raw) > MAX_PAGE:
                raise ValueError("Catalog page exceeds resource limit")
            name = object_write(root / "objects", raw, ".xml")
            report["pages"].append({"url": url, "object": name, "received_at": datetime.now(UTC)})
            names, next_token = decode_page(raw, prefix, token)
            if children.intersection(names):
                raise ValueError("Repeated directory entry across catalog pages")
            children.update(names)
            report["children"] = sorted(children)
            if next_token is None:
                report["status"] = "COMPLETE"
                break
            if next_token in tokens:
                raise ValueError("Catalog pagination token repeated")
            tokens.add(next_token)
            token = next_token
        else:
            raise ValueError("Catalog page budget exhausted before completeness")
    except (OSError, ValueError, urllib.error.URLError, ET.ParseError) as exc:
        report.update(error_type=type(exc).__name__, error=str(exc))
    report["completed_at"] = datetime.now(UTC)
    report["directory_hash"] = digest(report["children"])
    name = object_write(root / "reports", canonical(report).encode(), ".json")
    return report, root / "reports" / name
