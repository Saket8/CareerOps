"""Unit tests for experience parser."""

import pytest
from src.utils.experience_parser import parse_experience


def test_parse_experience_ranges():
    assert parse_experience("0-0 Yrs") == (0.0, 0.0)
    assert parse_experience("0 - 1 Yrs") == (0.0, 1.0)
    assert parse_experience("10-15 Yrs") == (10.0, 15.0)
    assert parse_experience("12 to 17 years") == (12.0, 17.0)
    assert parse_experience("8-12 Yrs") == (8.0, 12.0)
    assert parse_experience("10+ Yrs") == (10.0, 15.0)
    assert parse_experience("0 Yrs") == (0.0, 0.0)
    assert parse_experience("0 yr") == (0.0, 0.0)
    assert parse_experience("") == (None, None)
    assert parse_experience(None) == (None, None)
