import json
import urllib.error
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit

import pytest

from pvb24.data.catalog import ALLOWED_PREFIXES, NS, decode_page, inventory, page_url

PREFIX = ALLOWED_PREFIXES[2]


def page(names=("BTCUSDT",), *, prefix=PREFIX, token=None, next_token=None, change=None):
    root = ET.Element(NS + "ListBucketResult")
    values = {
        "Name": "data.binance.vision",
        "Prefix": prefix,
        "Delimiter": "/",
        "KeyCount": str(len(names)),
        "IsTruncated": "true" if next_token else "false",
    }
    if token is not None:
        values["ContinuationToken"] = token
    if next_token is not None:
        values["NextContinuationToken"] = next_token
    if change:
        values.update(change)
    for key, value in values.items():
        ET.SubElement(root, NS + key).text = value
    for name in names:
        ET.SubElement(ET.SubElement(root, NS + "CommonPrefixes"), NS + "Prefix").text = (
            prefix + name + "/"
        )
    return ET.tostring(root)


def test_catalog_follows_all_pages_and_remains_current_metadata_not_historical_security(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        token = parse_qs(urlsplit(url).query).get("continuation-token", [None])[0]
        return (
            page(("BTCUSDT", "DELISTEDUSDT"), next_token="next+token/=")
            if token is None
            else page(("ETHUSDT",), token=token)
        )

    result, path = inventory(PREFIX, tmp_path, fetch=fetch)
    assert result["status"] == "COMPLETE" and len(calls) == 2 and len(result["children"]) == 3
    assert not result["historical_eligibility_verified"] and not result["historical_rules_verified"]
    assert result["archive_objects_read"] == 0 and result["final_test_access"] == "LOCKED"
    assert all((tmp_path / "objects" / p["object"]).exists() for p in result["pages"])
    assert json.loads(path.read_text())["directory_hash"] == result["directory_hash"]
    assert any("DELISTEDUSDT" in name for name in result["children"])


@pytest.mark.parametrize(
    "case", ["repeated_child", "repeated_token", "wrong_token", "budget", "network"]
)
def test_partial_catalog_is_audited_but_never_labelled_complete(tmp_path, case):
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return page(next_token="next")
        if case == "network":
            raise urllib.error.URLError("fixture interruption")
        if case == "repeated_child":
            return page(token="next")
        if case == "repeated_token":
            return page(("ETHUSDT",), token="next", next_token="next")
        return page(("ETHUSDT",), token="wrong")

    result, path = inventory(PREFIX, tmp_path, fetch=fetch, max_pages=1 if case == "budget" else 3)
    assert result["status"] == "INCOMPLETE" and "error" in result
    assert result["children"] and path.exists()


@pytest.mark.parametrize(
    "change",
    [
        {"Name": "foreign"},
        {"Prefix": "data/spot/"},
        {"Delimiter": ""},
        {"IsTruncated": "maybe"},
        {"IsTruncated": "true"},
        {"KeyCount": "0"},
    ],
)
def test_response_identity_and_completeness_are_validated(change):
    with pytest.raises(ValueError):
        decode_page(page(change=change), PREFIX)


def test_catalog_rejects_nested_paths_leaf_objects_entities_and_arbitrary_request_roots(tmp_path):
    for name in ("../BTCUSDT", "BTCUSDT/1m", ""):
        with pytest.raises(ValueError):
            decode_page(page((name,)), PREFIX)
    with pytest.raises(ValueError):
        decode_page(b"<!DOCTYPE x><x/>", PREFIX)
    leaf = ET.fromstring(page())
    ET.SubElement(leaf, NS + "Contents")
    with pytest.raises(ValueError, match="leaf objects"):
        decode_page(ET.tostring(leaf), PREFIX)
    for prefix in (PREFIX + "BTCUSDT/1m/2025-07/", "data/futures/cm/monthly/", "../"):
        with pytest.raises(ValueError, match="reviewed directory"):
            inventory(prefix, tmp_path, fetch=lambda url: pytest.fail("Must not request network"))
    with pytest.raises(ValueError):
        page_url("https://foreign/")


def test_bad_xml_page_is_retained_for_audit_and_repeat_observation_cannot_overwrite(tmp_path):
    good, _ = inventory(PREFIX, tmp_path, fetch=lambda url: page())
    bad, _ = inventory(PREFIX, tmp_path, fetch=lambda url: b"<bad>")
    assert good["status"] == "COMPLETE" and bad["status"] == "INCOMPLETE"
    assert bad["pages"] and good["pages"][0]["object"] != bad["pages"][0]["object"]
    assert (tmp_path / "objects" / good["pages"][0]["object"]).exists()
