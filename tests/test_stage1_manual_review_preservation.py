import pandas as pd

from utils import merge_existing_manual_review


def test_manual_review_preserved_when_context_hash_matches():
    new_queue = pd.DataFrame(
        [{"provision_id": "P1", "review_context_hash": "same"}]
    )
    existing = pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "review_context_hash": "same",
                "human_final_is_institutional_opening": 1,
                "human_review_reason": "checked",
                "human_reviewer": "r",
                "human_reviewed_at": "2026-06-18",
                "human_review_completed": True,
            }
        ]
    )
    merged = merge_existing_manual_review(
        new_queue,
        existing,
        [
            "human_final_is_institutional_opening",
            "human_review_reason",
            "human_reviewer",
            "human_reviewed_at",
            "human_review_completed",
        ],
    )
    assert bool(merged.loc[0, "human_review_completed"])
    assert merged.loc[0, "human_review_reason"] == "checked"


def test_manual_review_reset_when_context_hash_changes():
    new_queue = pd.DataFrame(
        [{"provision_id": "P1", "review_context_hash": "new"}]
    )
    existing = pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "review_context_hash": "old",
                "human_final_is_institutional_opening": 1,
                "human_review_reason": "checked",
                "human_reviewer": "r",
                "human_reviewed_at": "2026-06-18",
                "human_review_completed": True,
            }
        ]
    )
    merged = merge_existing_manual_review(
        new_queue,
        existing,
        [
            "human_final_is_institutional_opening",
            "human_review_reason",
            "human_reviewer",
            "human_reviewed_at",
            "human_review_completed",
        ],
    )
    assert not bool(merged.loc[0, "human_review_completed"])
    assert bool(merged.loc[0, "stale_human_review"])
