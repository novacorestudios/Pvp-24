import json
from datetime import UTC, datetime

import pytest
from test_announcement_catalog import END, START, article, payload

from pvb24.data.acquisition import object_write
from pvb24.data.announcement_catalog import acquire_slice, load_slice
from pvb24.data.announcement_inventory import CatalogSlice, build_candidate_inventory
from pvb24.ids import canonical, digest


def selection(tmp_path, catalog=48):
    report, path = acquire_slice(
        catalog,
        tmp_path,
        start_page=5,
        start=START,
        end=END,
        fetch=lambda url: payload(
            catalog,
            [
                article(
                    title=(
                        "Binance Futures Will Launch TESTUSDT Perpetual Contract"
                        if catalog == 48
                        else "Binance Futures Will Delist TESTUSDT Perpetual Contract"
                    )
                )
            ],
            total=81,
        ),
    )
    return report, CatalogSlice(tmp_path, "reports/" + path.name, path.stem)


def repin(tmp_path, report):
    name = object_write(tmp_path / "reports", canonical(report).encode(), ".json")
    return CatalogSlice(tmp_path, "reports/" + name, name[:-5])


def test_public_inventory_uses_retained_pages_and_preserves_discovery_only_provenance(tmp_path):
    _, source = selection(tmp_path)
    inventory = build_candidate_inventory(source)
    assert inventory["source_page_chain_revalidated"] is True
    assert inventory["source_reports"][0]["report_sha256"] == source.sha256
    candidate = inventory["candidates"][0]
    assert candidate["source_report_sha256"] == source.sha256
    assert candidate["qualification"] == "BODY_REVIEW_REQUIRED"
    assert "available_at" not in candidate
    assert not candidate["lifecycle_fact"]
    assert not inventory["historical_publication_times_verified"]
    assert not inventory["operational_ready"] and not inventory["live_enabled"]
    assert inventory["candidate_hash"] == digest(inventory["candidates"])
    with pytest.raises(ValueError, match="Pinned CatalogSlice"):
        build_candidate_inventory(json.loads(canonical(inventory)))


@pytest.mark.parametrize(
    "change",
    [
        "fabricated_title",
        "omitted_row",
        "empty_pages",
        "page_url",
        "page_number",
        "receipt",
        "scope",
        "quality",
        "promote",
        "unlocked",
        "future_window",
        "missing_complete",
    ],
)
def test_rehashing_a_report_cannot_fabricate_or_promote_source_evidence(tmp_path, change):
    report, _ = selection(tmp_path)
    if change == "fabricated_title":
        report["in_window_articles"][0]["title"] = "Invented Launch FAKEUSDT Perpetual Contract"
        report["articles"] = report["in_window_articles"]
        report["article_hash"] = digest(report["in_window_articles"])
    elif change == "omitted_row":
        report["in_window_articles"] = report["articles"] = []
        report["article_hash"] = digest([])
    elif change == "empty_pages":
        report["pages"] = []
    elif change == "page_url":
        report["pages"][0]["url"] += "&pageNo=99"
    elif change == "page_number":
        report["pages"][0]["page_no"] += 1
    elif change == "receipt":
        report["pages"][0]["received_at"] = "2099-01-01T00:00:00Z"
    elif change == "scope":
        report["catalog_scope"] = "DELISTING"
    elif change == "quality":
        report["quality"] = "VERIFIED"
    elif change == "promote":
        report["historical_universe_complete"] = True
    elif change == "unlocked":
        report["final_test_access"] = "OPEN"
    elif change == "future_window":
        report["window_end"] = "2025-07-02T00:00:00Z"
    else:
        report["catalog_slice_complete"] = False
    source = repin(tmp_path, report)
    with pytest.raises(ValueError):
        build_candidate_inventory(source)


def test_full_last_page_requires_terminal_evidence_and_no_pages_after_terminal(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        when = (
            datetime(2024, 1, 1, tzinfo=UTC)
            if len(calls) == 1
            else datetime(2019, 1, 1, tzinfo=UTC)
        )
        return payload(48, [article(code=f"{len(calls):032x}", when=when)])

    report, path = acquire_slice(
        48, tmp_path, start_page=1, start=START, end=END, page_size=1, fetch=fetch
    )
    assert len(report["pages"]) == 2
    load_slice(tmp_path, "reports/" + path.name, expected_report_sha256=path.stem)
    truncated = json.loads(canonical(report))
    truncated["pages"].pop()
    source = repin(tmp_path, truncated)
    with pytest.raises(ValueError, match="truncated"):
        build_candidate_inventory(source)
    report["pages"].append(report["pages"][-1])
    source = repin(tmp_path, report)
    with pytest.raises(ValueError, match="after terminal"):
        build_candidate_inventory(source)


@pytest.mark.parametrize("change", ["ascending", "duplicate"])
def test_cross_page_order_or_duplicate_ambiguity_is_not_coverage(tmp_path, change):
    calls = []

    def fetch(url):
        calls.append(url)
        first = article(when=datetime(2023, 1, 1, tzinfo=UTC))
        if len(calls) == 1 or change == "duplicate":
            return payload(48, [first])
        return payload(48, [article(code="f" * 32, when=datetime(2024, 1, 1, tzinfo=UTC))])

    report, _ = acquire_slice(
        48, tmp_path, start_page=1, start=START, end=END, page_size=1, fetch=fetch
    )
    assert report["status"] == "INCOMPLETE"
    assert len(report["pages"]) == 1
    assert len(list((tmp_path / "objects").glob("*.json"))) == 1


def test_naive_catalog_request_fails_before_fetch(tmp_path):
    calls = []
    with pytest.raises(ValueError, match="Timezone-aware"):
        acquire_slice(
            48,
            tmp_path,
            start_page=1,
            start=datetime(2024, 1, 1),
            fetch=lambda url: calls.append(url),
        )
    assert not calls


def test_rehashed_final_source_page_is_rejected_even_if_report_omits_it(tmp_path):
    report, _ = selection(tmp_path)
    report["pages"][0]["object"] = object_write(
        tmp_path / "objects", payload(48, [article(when=END)], total=81), ".json"
    )
    with pytest.raises(ValueError, match="locked/upper"):
        build_candidate_inventory(repin(tmp_path, report))


@pytest.mark.parametrize("rows", [[], [article()]])
def test_short_or_empty_page_cannot_prove_completion_when_total_says_more(tmp_path, rows):
    report, _ = acquire_slice(
        48,
        tmp_path,
        start_page=1,
        start=START,
        end=END,
        fetch=lambda url: payload(48, rows, total=40),
    )
    assert report["status"] == "INCOMPLETE"
    assert "declared total/position" in report["error"]
    assert not list((tmp_path / "objects").glob("*"))


def test_offline_inventory_cli_writes_a_content_addressed_discovery_report(tmp_path):
    import hashlib
    import subprocess
    import sys
    from pathlib import Path

    _, source = selection(tmp_path / "source")
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/build_announcement_inventory.py"),
            "--slice",
            str(source.root),
            source.report,
            source.sha256,
            "--output",
            str(tmp_path / "inventory"),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    summary = json.loads(run.stdout)
    output = Path(summary["report"]).read_bytes()
    assert hashlib.sha256(output).hexdigest() == summary["report_sha256"]
    assert summary["candidates"] == 1 and not summary["operational_ready"]
    assert json.loads(output)["source_page_chain_revalidated"] is True
