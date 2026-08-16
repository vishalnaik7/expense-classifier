"""Unit tests for the rule-based transaction categorizer."""
from services.categorizer import TransactionCategorizer, ExpenseCategory


def test_categorizes_groceries():
    categorizer = TransactionCategorizer()
    category, confidence = categorizer.categorize({'description': 'BigBasket grocery order', 'amount': 1500})
    assert category == ExpenseCategory.GROCERIES.value
    assert confidence > 0.5


def test_categorizes_transport():
    categorizer = TransactionCategorizer()
    category, confidence = categorizer.categorize({'description': 'Uber ride to airport', 'amount': 450})
    assert category == ExpenseCategory.TRANSPORT.value
    assert confidence > 0.5


def test_categorizes_entertainment():
    categorizer = TransactionCategorizer()
    category, confidence = categorizer.categorize({'description': 'Netflix subscription', 'amount': 499})
    assert category == ExpenseCategory.ENTERTAINMENT.value


def test_unknown_merchant_falls_back_to_other():
    categorizer = TransactionCategorizer()
    category, confidence = categorizer.categorize({'description': 'XYZ Unrecognized Merchant 12345', 'amount': 10})
    assert category == ExpenseCategory.OTHER.value


def test_empty_description_returns_other_with_zero_confidence():
    categorizer = TransactionCategorizer()
    category, confidence = categorizer.categorize({'description': '', 'amount': 10})
    assert category == ExpenseCategory.OTHER.value
    assert confidence == 0.0


def test_two_keyword_match_clears_the_high_confidence_threshold():
    """Regression test: 0.7 + 2*0.1 is 0.8999999999999999 in floating point,
    not exactly 0.9 - without rounding, a two-keyword match would silently
    miss the `confidence >= 0.9` short-circuit and fall through to a much
    weaker match tier."""
    categorizer = TransactionCategorizer()
    category, confidence = categorizer.categorize({
        'description': '091025002930 SIP ICICI Pru Dividend Yield Equity Fund(G)',
        'amount': 500,
    })
    assert category == ExpenseCategory.INVESTMENT.value
    assert confidence >= 0.9


def test_specific_keyword_beats_generic_pattern_from_another_category():
    """A real UPI narration for an IRCTC (train ticket) payment contains
    both "irctc" (a Transport keyword) and "upi" (a Transfer pattern). The
    more specific keyword match should win even though it scores below the
    0.9 short-circuit threshold and patterns are checked after keywords."""
    categorizer = TransactionCategorizer()
    category, confidence = categorizer.categorize({
        'description': 'UPI/DR/619633007769/IRCTC Ti/pinelab/Paymentforv1',
        'amount': 442.70,
    })
    assert category == ExpenseCategory.TRANSPORT.value


def test_generic_bank_name_no_longer_forces_insurance_category():
    """"icici"/"hdfc" used to be listed as Insurance keywords, which
    false-positived on almost any UPI transfer mentioning the counterparty's
    bank. A plain bank-to-bank transfer must not be miscategorized as
    Insurance just because it names a bank."""
    categorizer = TransactionCategorizer()
    category, _ = categorizer.categorize({
        'description': 'NEFT to HDFC Bank account for rent',
        'amount': 15000,
    })
    assert category != ExpenseCategory.INSURANCE.value


def test_categorize_batch_matches_categorize():
    categorizer = TransactionCategorizer()
    transactions = [
        {'description': 'Uber ride', 'amount': 100},
        {'description': 'Netflix', 'amount': 500},
    ]
    results = categorizer.categorize_batch(transactions)
    assert results[0][0] == ExpenseCategory.TRANSPORT.value
    assert results[1][0] == ExpenseCategory.ENTERTAINMENT.value
