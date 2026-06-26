"""Smoke test — confirms the package imports and the toolchain runs.

Real tests arrive with each phase (retrieval, agent loop, evaluation).
"""

from policy_copilot import __version__


def test_version_is_set() -> None:
    assert __version__ == "0.1.0"
