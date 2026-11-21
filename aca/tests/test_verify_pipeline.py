"""Run the end-to-end verification script under pytest."""

from tests.verify_pipeline import run_verification


def test_verify_pipeline() -> None:
    run_verification()
