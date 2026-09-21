import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pvb24.data.margin_tier_history import compile_historical_liquidation_evidence
from pvb24.data.margin_tier_source import inspect_margin_tier_response
from pvb24.ids import canonical


def text_node(value):
    return {"node": "text", "text": value}


def element(tag, children):
    return {"node": "element", "tag": tag, "child": children}


def paragraph(value):
    return element("p", [text_node(value)])


def heading(value):
    return element("ul", [text_node(value)])


def table(rows):
    return element(
        "table",
        [
            element("tr", [element("td", [text_node(cell)]) for cell in row])
            for row in rows
        ],
    )


HEADER = [
    "Leverage Before Change",
    "Position Before Change (Notional Value in USDT)",
    "Maintenance Margin Rate Before Change",
    "Leverage After Change",
    "Position After Change (Notional Value in USDT)",
    "Maintenance Margin Rate After Change",
]


def response(*, effective="2024-05-28 10:30", published=1716790000000, affected=False):
    policy = (
        "Please note that existing positions opened before the update will be affected."
        if affected
        else "Please note that existing positions opened before the update will not be affected."
    )
    rows = [
        ["Previous Leverage and Margin Tiers", "New Leverage and Margin Tiers"],
        HEADER,
        ["21 - 50x", "0 < Position ≤ 5,000", "1.00%", "26 - 50x", "0 < Position ≤ 5,000", "1.00%"],
        ["11 - 20x", "5,000 < Position ≤ 50,000", "2.50%", "NA", "21 - 25x", "5,000 < Position ≤ 10,000", "2.00%"],
        ["NA", "11 - 20x", "10,000 < Position ≤ 50,000", "2.50%"],
    ]
    body = canonical(
        {
            "node": "root",
            "child": [
                paragraph(
                    "Binance Futures will update the leverage and margin tiers of the following "
                    f"USDⓈ-M Perpetual Contracts at {effective} (UTC), as per the tables below. "
                    + policy
                ),
                heading("AAAUSDT and BBBUSDT (USDⓈ-M Perpetual Contracts)"),
                table(rows),
                heading("BTCUSD (COIN-M Perpetual Contract)"),
                table(
                    [
                        ["Previous Leverage and Margin Tiers", "New Leverage and Margin Tiers"],
                        [
                            "Leverage Before Change",
                            "Position Before Change (Notional Value in BTC)",
                            "Maintenance Margin Rate Before Change",
                            "Leverage After Change",
                            "Position After Change (Notional Value in BTC)",
                            "Maintenance Margin Rate After Change",
                        ],
                        ["1x", "0 < Position ≤ 5", "50.00%", "1x", "0 < Position ≤ 5", "50.00%"],
                    ]
                ),
            ],
        }
    )
    return canonical(
        {
            "success": True,
            "data": {
                "code": "a" * 32,
                "publishDate": published,
                "lastUpdateTime": 0,
                "version": "1",
                "body": body,
            },
        }
    ).encode()


def retained(tmp_path, raw=None):
    raw = response() if raw is None else raw
    code = "a" * 32
    probe = inspect_margin_tier_response(code, raw)
    root = tmp_path / code
    (root / "objects").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "objects" / f"{probe['source_sha256']}.json").write_bytes(raw)
    report_bytes = (json.dumps(probe, indent=2) + "\n").encode()
    report_hash = hashlib.sha256(report_bytes).hexdigest()
    (root / "reports" / f"{report_hash}.json").write_bytes(report_bytes)
    return code, report_hash


def compile_one(tmp_path, raw=None):
    code, report_hash = retained(tmp_path, raw)
    return compile_historical_liquidation_evidence(tmp_path, [(code, report_hash)])


def test_compiler_extracts_complete_source_tier_sides_without_emitting_rules(tmp_path):
    result = compile_one(tmp_path)
    article = result["articles"][0]
    assert article["timing_relation"] == "ANNOUNCED_BEFORE_EFFECTIVE"
    assert article["new_schedule_causally_announced_before_effective"]
    assert article["coin_m_tables_skipped"] == 1
    assert [row["symbol"] for row in article["usd_m_symbols"]] == ["AAAUSDT", "BBBUSDT"]
    schedule = article["usd_m_symbols"][0]
    assert len(schedule["previous_tiers"]) == 2
    assert len(schedule["new_tiers"]) == 3
    assert schedule["new_tiers"][1]["notional_floor"] == "5000"
    assert schedule["new_tiers"][1]["notional_cap"] == "10000"
    assert schedule["new_tiers"][1]["maintenance_margin_rate"] == "0.02"
    assert schedule["new_tiers"][1]["max_leverage"] == 25
    assert not schedule["maintenance_amounts_present"]
    assert not schedule["liquidation_validated"]
    assert result["contract_rules_emitted"] == 0
    assert not result["historical_liquidation_rules_complete"]


def test_existing_position_policy_is_explicit_and_changes_cohort_requirement(tmp_path):
    result = compile_one(tmp_path, response(affected=False))
    assert result["articles"][0]["position_cohort_selection_required"]
    assert result["position_cohort_policy_observed"]

    other = tmp_path / "affected"
    result = compile_one(other, response(affected=True))
    assert not result["articles"][0]["position_cohort_selection_required"]


def test_post_effective_publication_is_retrospective_not_causal(tmp_path):
    published = int(datetime(2024, 5, 29, tzinfo=UTC).timestamp() * 1000)
    result = compile_one(tmp_path, response(published=published))
    article = result["articles"][0]
    assert article["timing_relation"] == "PUBLISHED_AFTER_EFFECTIVE"
    assert not article["new_schedule_causally_announced_before_effective"]
    assert result["retrospective_change_count"] == 1


@pytest.mark.parametrize(
    "mutator,match",
    [
        (
            lambda rows: rows[2].__setitem__(1, "1,000 < Position ≤ 5,000"),
            "zero-based",
        ),
        (
            lambda rows: rows[3].__setitem__(1, "6,000 < Position ≤ 50,000"),
            "Non-contiguous",
        ),
        (
            lambda rows: rows[3].__setitem__(2, "0.50%"),
            "cannot decrease",
        ),
    ],
)
def test_malformed_previous_schedule_fails_closed(tmp_path, mutator, match):
    value = json.loads(response())
    body = json.loads(value["data"]["body"])
    rows = body["child"][2]["child"]
    rendered = []
    for row in rows:
        rendered.append([cell["child"][0]["text"] for cell in row["child"]])
    mutator(rendered)
    body["child"][2] = table(rendered)
    value["data"]["body"] = canonical(body)
    with pytest.raises(ValueError, match=match):
        compile_one(tmp_path, canonical(value).encode())


def test_source_report_and_raw_object_pins_are_rechecked(tmp_path):
    code, report_hash = retained(tmp_path)
    report_path = Path(tmp_path) / code / "reports" / f"{report_hash}.json"
    report_path.write_bytes(report_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="report hash changed"):
        compile_historical_liquidation_evidence(tmp_path, [(code, report_hash)])

    code, report_hash = retained(tmp_path / "raw")
    object_path = next((tmp_path / "raw" / code / "objects").iterdir())
    object_path.write_bytes(object_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="source bytes changed"):
        compile_historical_liquidation_evidence(tmp_path / "raw", [(code, report_hash)])


def test_missing_existing_position_policy_is_rejected(tmp_path):
    value = json.loads(response())
    body = json.loads(value["data"]["body"])
    body["child"][0]["child"][0]["text"] = body["child"][0]["child"][0]["text"].replace(
        "Please note that existing positions opened before the update will not be affected.",
        "",
    )
    value["data"]["body"] = canonical(body)
    with pytest.raises(ValueError, match="existing-position"):
        compile_one(tmp_path, canonical(value).encode())
