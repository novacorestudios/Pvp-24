import json
import urllib.error
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from test_archive_acquisition import START, archive
from test_funding_history import payload, row

from pvb24.data.acquisition import object_write
from pvb24.data.archive import ArchiveRequest
from pvb24.data.funding_coverage import audit_month, monthly_requests, resume_results, summarize
from pvb24.data.funding_dataset import load_history
from pvb24.data.funding_history import acquire_history
from pvb24.ids import canonical

REQ = ArchiveRequest("BTCUSDT", "fundingRate", "2024-01")


def history(tmp_path):
    # Three pages with repeated boundary rows, including the terminal short page.
    stamps = [START + i * 8 * 3600000 for i in range(4)]
    pages = {
        stamps[0]: [row(s) for s in stamps[:2]],
        stamps[1]: [row(s) for s in stamps[1:3]],
        stamps[2]: [row(s) for s in stamps[2:]],
        stamps[3]: [row(stamps[3])],
    }
    report, path = acquire_history(
        REQ,
        tmp_path,
        limit=2,
        fetch=lambda url: payload(pages[int(parse_qs(urlsplit(url).query)["startTime"][0])]),
    )
    return report, path


def test_reconsumption_proves_complete_page_chain_exact_data_and_overlap_identity(tmp_path):
    report, path = history(tmp_path)
    source, checked = load_history(tmp_path, path.name, expected_report_hash=path.stem)
    assert source == REQ and checked == report and len(checked["rows"]) == 4
    assert len(checked["pages"]) == 4
    assert not checked["funding_schedule_complete"]


@pytest.mark.parametrize(
    "change", ["truncate", "cursor", "rows", "promote", "mark", "path", "decoder"]
)
def test_rehashed_report_cannot_fake_complete_evidence_or_promote_quality(tmp_path, change):
    report, _ = history(tmp_path)
    if change == "truncate":
        report["pages"].pop()
    elif change == "cursor":
        report["pages"][1]["url"] = report["pages"][0]["url"]
    elif change == "rows":
        report["rows"].pop()
    elif change == "promote":
        report["funding_schedule_complete"] = True
    elif change == "mark":
        report["settlement_mark_complete"] = False
    elif change == "path":
        report["pages"][0]["object"] = "../foreign.json"
    else:
        report["decoder_sha256"] = "0" * 64
    name = object_write(tmp_path / "reports", canonical(report).encode(), ".json")
    with pytest.raises(ValueError):
        load_history(tmp_path, name, expected_report_hash=Path(name).stem)


def test_changed_page_bytes_fail_even_when_report_remains_pinned(tmp_path):
    report, path = history(tmp_path)
    page = tmp_path / "objects" / report["pages"][0]["object"]
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(ValueError, match="page bytes changed"):
        load_history(tmp_path, path.name, expected_report_hash=path.stem)


def test_full_prefinal_request_bounds_include_warmup_but_exclude_final():
    selection = monthly_requests("BTCUSDT", "2019-12", "2025-06")
    assert len(selection) == 67 and selection[-1].end.isoformat().startswith("2025-07-01")
    with pytest.raises(ValueError, match="LOCKED"):
        monthly_requests("BTCUSDT", "2019-12", "2025-07")
    with pytest.raises(ValueError, match="ordered"):
        monthly_requests("BTCUSDT", "2024-02", "2024-01")


def pair(tmp_path, *, missing_archive=False, missing_mark=False, mismatch=False):
    raw, checksum = archive(
        REQ, [[str(START), "8", "0.0001"], [str(START + 8 * 3600000 + 1), "8", "0.0002"]]
    )

    def fetch(url, *, max_bytes):
        if missing_archive:
            raise urllib.error.HTTPError(url, 404, "missing", {}, None)
        return checksum if url.endswith(".CHECKSUM") else raw

    rows = [
        row(markPrice="" if missing_mark else "42000"),
        row(START + 8 * 3600000 + 1, fundingRate="0.0003" if mismatch else "0.0002"),
    ]
    return audit_month(REQ, tmp_path, archive_fetch=fetch, history_fetch=lambda url: payload(rows))


def test_matched_sources_preserve_timestamp_jitter_and_do_not_attest_a_schedule(tmp_path):
    result, name = pair(tmp_path)
    assert result["status"] == "MATCHED_TIME_RATE"
    assert result["archive_interval_discontinuities"] == 1
    assert result["comparison"]["matched_time_and_rate"] == 2
    assert result["history"]["settlement_mark_complete"]
    assert not result["funding_schedule_complete"]
    assert (tmp_path / "months" / name).exists()


@pytest.mark.parametrize(
    "missing_archive,missing_mark,mismatch",
    [
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ],
)
def test_missing_and_mismatched_sources_remain_explicit_in_coverage(
    tmp_path, missing_archive, missing_mark, mismatch
):
    result, name = pair(
        tmp_path, missing_archive=missing_archive, missing_mark=missing_mark, mismatch=mismatch
    )
    report = summarize((REQ,), [(result, name)])
    assert report["completed_months"] == 1
    assert not report["funding_schedule_complete"] and not report["operational_ready"]
    if missing_archive:
        assert result["archive"]["status"] == "UNAVAILABLE"
        assert result["archive"]["rows"] is None and result["comparison"] is None
        assert report["matched_months"] == 0
    elif missing_mark:
        assert result["status"] == "MATCHED_TIME_RATE"
        assert not result["history"]["settlement_mark_complete"]
    else:
        assert len(result["comparison"]["rate_mismatches"]) == 1 and report["matched_months"] == 0


def test_summary_retains_unfinished_periods_and_rejects_duplicates_or_changed_results(tmp_path):
    result, name = pair(tmp_path)
    requests = monthly_requests("BTCUSDT", "2024-01", "2024-03")
    report = summarize(requests, [(result, name)])
    assert report["requested_months"] == 3 and report["completed_months"] == 1
    assert [r["status"] for r in report["coverage"]] == [
        "MATCHED_TIME_RATE",
        "NOT_COMPLETED",
        "NOT_COMPLETED",
    ]
    assert not report["source_time_rate_comparison_complete"]
    with pytest.raises(ValueError, match="selection"):
        summarize(requests, [(result, name), (result, name)])
    result["archive"]["rows"] = 100
    with pytest.raises(ValueError, match="selection"):
        summarize(requests, [(result, name)])


def test_final_month_report_is_rejected_before_retained_page_reads(tmp_path):
    (tmp_path / "reports").mkdir()
    report = {"symbol": "BTCUSDT", "month": "2025-07"}
    name = object_write(tmp_path / "reports", json.dumps(report).encode(), ".json")
    with pytest.raises(ValueError, match="LOCKED"):
        load_history(tmp_path, name, expected_report_hash=Path(name).stem)
    request = REQ
    object.__setattr__(request, "month", "2025-07")
    calls = []
    try:
        with pytest.raises(ValueError, match="LOCKED"):
            audit_month(request, tmp_path, archive_fetch=lambda *a, **kw: calls.append(a))
        assert not calls
    finally:
        object.__setattr__(request, "month", "2024-01")
    assert asdict(REQ)["month"] == "2024-01"


@pytest.mark.parametrize("missing_archive", [False, True])
def test_resume_keeps_pinned_success_or_missing_evidence_without_redownloading(
    tmp_path, missing_archive
):
    result = pair(tmp_path, missing_archive=missing_archive)
    requests = monthly_requests("BTCUSDT", "2024-01", "2024-02")
    summary = {**summarize(requests, [result]), "config_hash": "fixture"}
    name = object_write(tmp_path / "summaries", canonical(summary).encode(), ".json")
    restored = resume_results(
        tmp_path,
        tmp_path / "summaries" / name,
        expected_hash=Path(name).stem,
        requests=requests,
        config_hash="fixture",
    )
    assert restored == [result]


@pytest.mark.parametrize("change", ["selection", "config", "monthly", "summary"])
def test_resume_rejects_changed_selection_or_evidence(tmp_path, change):
    result = pair(tmp_path)
    requests = (REQ,)
    summary = {**summarize(requests, [result]), "config_hash": "fixture"}
    name = object_write(tmp_path / "summaries", canonical(summary).encode(), ".json")
    path = tmp_path / "summaries" / name
    config = "fixture"
    if change == "selection":
        requests = monthly_requests("BTCUSDT", "2024-01", "2024-02")
    elif change == "config":
        config = "different"
    elif change == "monthly":
        (tmp_path / "months" / result[1]).write_bytes(b"{}")
    else:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        resume_results(
            tmp_path, path, expected_hash=Path(name).stem, requests=requests, config_hash=config
        )
