"""Unit tests for the normaliser module."""
import pytest
from app.pipeline.normalise import (
    normalise_area_to_sqm, normalise_area_to_acres,
    normalise_currency_to_crores, normalise_integer,
    normalise_name, normalise_date,
)


class TestAreaNormalisation:
    def test_acres_to_sqm(self):
        result = normalise_area_to_sqm("2.10 acres")
        assert result.valid
        assert abs(result.value - 2.10 * 4046.856) < 1.0

    def test_sqft_to_sqm(self):
        result = normalise_area_to_sqm("18000 sq ft")
        assert result.valid
        assert abs(result.value - 18000 * 0.0929) < 1.0

    def test_sqm_passthrough(self):
        result = normalise_area_to_sqm("1200 sq m")
        assert result.valid
        assert abs(result.value - 1200.0) < 0.01

    def test_guntha(self):
        result = normalise_area_to_sqm("5 guntha")
        assert result.valid
        assert abs(result.value - 5 * 101.17) < 1.0

    def test_invalid(self):
        result = normalise_area_to_sqm("not an area")
        assert not result.valid

    def test_acres_round_trip(self):
        result = normalise_area_to_acres("3.00 acres")
        assert result.valid
        assert abs(result.value - 3.00) < 0.01


class TestCurrencyNormalisation:
    def test_crore(self):
        result = normalise_currency_to_crores("Rs. 6 crore")
        assert result.valid
        assert abs(result.value - 6.0) < 0.01

    def test_lakh(self):
        result = normalise_currency_to_crores("50 lakh")
        assert result.valid
        assert abs(result.value - 0.5) < 0.001

    def test_indian_format(self):
        result = normalise_currency_to_crores("6,00,00,000")
        assert result.valid
        # 6 crore = 6e7
        assert abs(result.value - 6.0) < 0.01

    def test_cr_abbreviation(self):
        result = normalise_currency_to_crores("3.5 cr")
        assert result.valid
        assert abs(result.value - 3.5) < 0.01


class TestIntegerNormalisation:
    def test_plain(self):
        result = normalise_integer("1200")
        assert result.valid and result.value == 1200

    def test_indian_format(self):
        result = normalise_integer("1,200")
        assert result.valid and result.value == 1200

    def test_with_text(self):
        result = normalise_integer("Total 58 faculty")
        assert result.valid and result.value == 58


class TestNameNormalisation:
    def test_strips_title(self):
        assert normalise_name("Dr. A.B. Sharma") == "ab sharma"

    def test_lowercase(self):
        assert normalise_name("SUNRISE INSTITUTE") == "sunrise institute"

    def test_strips_punctuation(self):
        result = normalise_name("Prof. R.K. Singh, Ph.D.")
        assert "rk singh" in result or "r k singh" in result


class TestDateNormalisation:
    def test_indian_format(self):
        assert normalise_date("15/08/2026") == "2026-08-15"

    def test_dash_format(self):
        assert normalise_date("15-08-2026") == "2026-08-15"

    def test_iso_passthrough(self):
        assert normalise_date("2026-08-15") == "2026-08-15"

    def test_invalid(self):
        assert normalise_date("not a date") is None
