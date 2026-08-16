"""Unit tests for the CSV parsing and duplicate-detection engine."""
import pytest

from services.csv_parser import CSVParser, CSVParsingError, DuplicateDetector


def test_parses_valid_csv():
    csv_bytes = (
        b'Date,Description,Amount\n'
        b'2024-01-15,Grocery Shopping,1500\n'
        b'2024-01-16,Electricity Bill,2000\n'
    )
    transactions = CSVParser(csv_bytes).parse()

    assert len(transactions) == 2
    assert transactions[0]['date'] == '2024-01-15'
    assert transactions[0]['amount'] == 1500.0
    assert transactions[0]['type'] == 'debit'


def test_handles_multiple_date_formats():
    csv_bytes = (
        b'Date,Description,Amount\n'
        b'15/01/2024,DD/MM/YYYY format,100\n'
        b'2024-01-16,ISO format,200\n'
    )
    transactions = CSVParser(csv_bytes).parse()

    assert transactions[0]['date'] == '2024-01-15'
    assert transactions[1]['date'] == '2024-01-16'


def test_empty_file_raises():
    with pytest.raises(CSVParsingError):
        CSVParser(b'').parse()


def test_missing_required_columns_raises():
    csv_bytes = b'Foo,Bar\n1,2\n'
    with pytest.raises(CSVParsingError):
        CSVParser(csv_bytes).parse()


def test_header_case_and_alias_normalization():
    csv_bytes = (
        b'Transaction Date,Narration,Debit\n'
        b'2024-01-15,Coffee shop,150\n'
    )
    transactions = CSVParser(csv_bytes).parse()
    assert len(transactions) == 1
    assert transactions[0]['description'] == 'Coffee shop'


def test_invalid_rows_are_skipped_not_fatal():
    csv_bytes = (
        b'Date,Description,Amount\n'
        b'2024-01-15,Valid row,100\n'
        b'not-a-date,Bad date row,50\n'
        b'2024-01-17,Bad amount row,notanumber\n'
    )
    transactions = CSVParser(csv_bytes).parse()
    assert len(transactions) == 1
    assert transactions[0]['description'] == 'Valid row'


def test_all_rows_invalid_raises():
    csv_bytes = (
        b'Date,Description,Amount\n'
        b'not-a-date,Bad row,notanumber\n'
    )
    with pytest.raises(CSVParsingError):
        CSVParser(csv_bytes).parse()


def test_csv_injection_characters_are_stripped():
    csv_bytes = b'Date,Description,Amount\n2024-01-15,=cmd|calc,100\n'
    transactions = CSVParser(csv_bytes).parse()
    assert not transactions[0]['description'].startswith('=')


def test_skips_bank_metadata_rows_above_the_real_header():
    """A real-world layout (IDFC FIRST-style export): title/account-summary
    rows above the actual Date/Description/Debit/Credit table."""
    csv_bytes = (
        b'STATEMENT OF ACCOUNT,,,,\n'
        b'IDFC FIRST Bank,,,,\n'
        b'Account No: 1234567890,,,,\n'
        b',,,,\n'
        b'Date,Description,Debit,Credit,Balance\n'
        b'2024-01-15,Grocery Shopping BigBasket,1500,,24500.00\n'
        b'2024-01-16,Salary Credit,,50000,74500.00\n'
        b'2024-01-17,Uber Ride,450,,74050.00\n'
    )
    transactions = CSVParser(csv_bytes).parse()

    assert len(transactions) == 3
    assert transactions[0]['description'] == 'Grocery Shopping BigBasket'
    assert transactions[0]['amount'] == 1500.0
    assert transactions[0]['type'] == 'debit'
    assert transactions[1]['description'] == 'Salary Credit'
    assert transactions[1]['amount'] == 50000.0
    assert transactions[1]['type'] == 'credit'
    assert transactions[2]['description'] == 'Uber Ride'


def test_metadata_only_file_still_raises():
    csv_bytes = (
        b'STATEMENT OF ACCOUNT,,,,\n'
        b'IDFC FIRST Bank,,,,\n'
        b'Account No: 1234567890,,,,\n'
    )
    with pytest.raises(CSVParsingError):
        CSVParser(csv_bytes).parse()


def test_credit_only_row_resolves_from_credit_column():
    """A blank Debit cell must not slip through as a NaN amount (NaN
    comparisons are always False, so `amount <= 0` alone won't catch it) -
    it should instead resolve the amount from the Credit column."""
    csv_bytes = (
        b'Date,Description,Debit,Credit\n'
        b'2024-01-16,Salary Credit,,50000\n'
    )
    transactions = CSVParser(csv_bytes).parse()
    assert len(transactions) == 1
    assert transactions[0]['amount'] == 50000.0
    assert transactions[0]['type'] == 'credit'
    assert transactions[0]['raw_amount'] == -50000.0


def test_withdrawal_deposit_headers_resolve_like_debit_credit():
    """
    Some banks (e.g. HDFC) label the split-amount columns "Withdrawal
    Amt."/"Deposit Amt." instead of "Debit"/"Credit". Only "Withdrawal"
    matches HEADER_PATTERNS['debit'], not HEADER_PATTERNS['amount'] (which
    only recognizes the literal word "debit"), so this column lands as a
    'debit'-named column rather than 'amount' - _resolve_amount_and_type()
    must check that column too, not just 'amount' and 'credit'.
    """
    csv_bytes = (
        b'Date,Narration,Withdrawal Amt.,Deposit Amt.\n'
        b'2024-01-15,ATM Cash Withdrawal,5000,\n'
        b'2024-01-16,Salary Credit,,60000\n'
    )
    transactions = CSVParser(csv_bytes).parse()

    assert len(transactions) == 2
    assert transactions[0]['amount'] == 5000.0
    assert transactions[0]['type'] == 'debit'
    assert transactions[1]['amount'] == 60000.0
    assert transactions[1]['type'] == 'credit'


def test_row_with_both_debit_and_credit_blank_is_rejected():
    csv_bytes = (
        b'Date,Description,Debit,Credit\n'
        b'2024-01-16,No amount at all,,\n'
    )
    with pytest.raises(CSVParsingError):
        CSVParser(csv_bytes).parse()


def test_wrapped_narration_lines_merge_into_previous_transaction():
    """Some bank exports wrap a transaction's narration onto extra lines
    below it (every column blank except the description)."""
    csv_bytes = (
        b'Date,Description,Amount\n'
        b'2024-01-15,UPI/DR/12345/CHALO,75\n'
        b',HDFC/chalo1./Pay,\n'
        b'2024-01-16,Uber Ride,450\n'
    )
    transactions = CSVParser(csv_bytes).parse()
    assert len(transactions) == 2
    assert transactions[0]['description'] == 'UPI/DR/12345/CHALO HDFC/chalo1./Pay'
    assert transactions[1]['description'] == 'Uber Ride'


def test_parses_month_abbreviation_date_format():
    """Common Indian bank statement format: 01-Jun-2026."""
    csv_bytes = b'Date,Description,Amount\n01-Jun-2026,Coffee,100\n'
    transactions = CSVParser(csv_bytes).parse()
    assert transactions[0]['date'] == '2026-06-01'


def test_repeated_page_summary_rows_are_not_merged_as_continuations():
    """Multi-page statement exports repeat the account-summary block on
    every page; a row like "Opening Balance,,Total Debit,Total Credit,,..."
    has several non-description columns populated and must not get glued
    onto the previous transaction's description."""
    csv_bytes = (
        b'Date,Description,Debit,Credit,Balance\n'
        b'2024-01-15,Grocery Shopping,1500,,24500.00\n'
        b'Opening Balance,,Total Debit,Total Credit,Closing Balance\n'
        b'2024-01-17,Uber Ride,450,,74050.00\n'
    )
    transactions = CSVParser(csv_bytes).parse()
    assert len(transactions) == 2
    assert transactions[0]['description'] == 'Grocery Shopping'
    assert transactions[1]['description'] == 'Uber Ride'


def test_duplicate_detector_flags_repeats():
    csv_bytes = (
        b'Date,Description,Amount\n'
        b'2024-01-15,Coffee,100\n'
        b'2024-01-15,Coffee,100\n'
        b'2024-01-16,Lunch,300\n'
    )
    transactions = CSVParser(csv_bytes).parse()
    unique, duplicate_indices = DuplicateDetector(transactions).detect_duplicates()

    assert len(unique) == 2
    assert len(duplicate_indices) == 1
