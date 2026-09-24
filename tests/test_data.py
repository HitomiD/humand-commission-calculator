"""Tests for the CSV loaders: the real files load, and each kind of bad row
blocks only its own deal."""

import shutil
from pathlib import Path

import pytest

from calculator.data import APPROVED_FILE, DATA_DIR, DEALS_FILE, DataError, load_inputs


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A copy of the real data files that a test can break."""
    for name in (DEALS_FILE, APPROVED_FILE):
        shutil.copy(DATA_DIR / name, tmp_path / name)
    return tmp_path


def _append(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# --- Real files ---------------------------------------------------------------

def test_real_files_load_cleanly():
    data = load_inputs()
    assert len(data.deals) == 8
    assert len(data.approved) == 30
    assert data.issues == []
    assert data.blocked_deals == set()


# --- Whole-file problems stop the run -----------------------------------------

def test_missing_file(tmp_path):
    with pytest.raises(DataError, match="hubspot_deals.csv: file not found"):
        load_inputs(tmp_path)


def test_missing_column(data_dir):
    _replace(data_dir / APPROVED_FILE, "meses_cubiertos", "meses")
    with pytest.raises(DataError, match=r"pagos_aprobados.csv: missing columns \['meses_cubiertos'\]"):
        load_inputs(data_dir)


# --- Row problems block only their deal ---------------------------------------

def test_bad_deal_row_blocks_that_deal(data_dir):
    # D01 is the first data row, i.e. row 2 of the file.
    _replace(data_dir / DEALS_FILE, ",No,252.0,", ",Si,252.0,")
    data = load_inputs(data_dir)
    assert data.blocked_deals == {"D01"}
    assert [d.deal_id for d in data.deals] == ["D02", "D03", "D04", "D05", "D06", "D07", "D08"]
    (issue,) = data.issues
    assert (issue.file, issue.row, issue.deal_id) == (DEALS_FILE, 2, "D01")
    assert "commission_on_expansion" in issue.message
    # D01's approved payments are not reported as belonging to an unknown deal.
    assert len(data.approved) == 30


def test_duplicate_deal_id_blocks_that_deal(data_dir):
    _append(data_dir / DEALS_FILE, "D01,X,P,,,10%,,No,1,,")
    data = load_inputs(data_dir)
    assert data.blocked_deals == {"D01"}
    assert "D01" not in {d.deal_id for d in data.deals}
    assert sorted(i.row for i in data.issues) == [2, 10]  # both copies reported


def test_bad_approved_row_blocks_that_deal(data_dir):
    _append(data_dir / APPROVED_FILE, "D05,D05_m5,0")
    data = load_inputs(data_dir)
    assert data.blocked_deals == {"D05"}
    (issue,) = data.issues
    assert (issue.file, issue.row) == (APPROVED_FILE, 32)


def test_duplicate_approved_payment_blocks_that_deal(data_dir):
    _append(data_dir / APPROVED_FILE, "D01,D01_m1,1")
    data = load_inputs(data_dir)
    assert data.blocked_deals == {"D01"}
    assert sorted(i.row for i in data.issues) == [2, 32]


def test_approved_row_for_unknown_deal_is_reported_but_blocks_nothing(data_dir):
    _append(data_dir / APPROVED_FILE, "D99,D99_m1,1")
    data = load_inputs(data_dir)
    assert data.blocked_deals == set()
    (issue,) = data.issues
    assert issue.deal_id == "D99" and not issue.blocks_deal
