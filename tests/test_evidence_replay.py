from pvb24.data.evidence_replay import _subset_mismatches


def test_replay_subset_accepts_exact_expected_values():
    assert (
        _subset_mismatches(
            "qualification",
            {"candidate_count": 148, "source_fetch_complete": True},
            {
                "candidate_count": 148,
                "source_fetch_complete": True,
                "extra_diagnostic": "allowed",
            },
        )
        == []
    )


def test_replay_subset_reports_exact_drift():
    assert _subset_mismatches(
        "recovery",
        {"recovered_fact_count": 48},
        {"recovered_fact_count": 47},
    ) == [
        {
            "section": "recovery",
            "field": "recovered_fact_count",
            "expected": 48,
            "actual": 47,
        }
    ]
