"""
Expense Categorization Engine for Fintech Classifier
Uses keyword matching and pattern recognition to categorize expenses
Supports custom rules and machine learning predictions
"""

import re
from typing import Dict, List, Tuple, Optional
from enum import Enum


class ExpenseCategory(Enum):
    """Standard expense categories"""
    GROCERIES = 'Groceries'
    FOOD_DINING = 'Food & Dining'
    TRANSPORT = 'Transport'
    UTILITIES = 'Utilities'
    ENTERTAINMENT = 'Entertainment'
    SHOPPING = 'Shopping'
    HEALTH_MEDICAL = 'Health & Medical'
    EDUCATION = 'Education'
    INSURANCE = 'Insurance'
    INVESTMENT = 'Investment'
    SALARY = 'Salary'
    TRANSFER = 'Transfer'
    OTHER = 'Other'


class TransactionCategorizer:
    """
    Categorizes transactions using rule-based system with keyword matching
    
    Priority Order:
    1. Exact keyword match
    2. Regex pattern match
    3. Keyword substring match
    4. Default category
    """
    
    # Categorization rules with keywords
    CATEGORY_RULES = {
        ExpenseCategory.GROCERIES: {
            'keywords': [
                'grocery', 'supermarket', 'shopping', 'market', 'walmart', 
                'bigbasket', 'instacart', 'reliance fresh', 'dmart', 'blinkit',
                'store', 'vegetables', 'fruits', 'dairy', 'bakery'
            ],
            'patterns': [r'(?i)(grocery|market|fresh|produce)'],
            'exclude_keywords': ['restaurant', 'cafe', 'hotel']
        },
        
        ExpenseCategory.FOOD_DINING: {
            'keywords': [
                'restaurant', 'cafe', 'coffee', 'food delivery', 'zomato', 'swiggy',
                'uber eats', 'pizza', 'burger', 'pizza hut', 'kfc', 'mcdonalds',
                'dominos', 'cafe coffee', 'starbucks', 'hotel', 'dining', 'pub',
                'bar', 'diner', 'eatery', 'fastfood'
            ],
            'patterns': [r'(?i)(restaurant|cafe|food|pizza|burger|delivery)'],
            'exclude_keywords': []
        },
        
        ExpenseCategory.TRANSPORT: {
            'keywords': [
                'uber', 'ola', 'taxi', 'auto', 'fuel', 'petrol', 'diesel', 'gas',
                'bus', 'train', 'ticket', 'metro', 'parking', 'toll', 'travel',
                'flight', 'booking.com', 'mmt', 'railway', 'rideshare', 'public transport',
                'didi', 'grab', 'lyft', 'irctc', 'chalo'
            ],
            'patterns': [r'(?i)(uber|ola|taxi|fuel|transport|travel|flight)'],
            'exclude_keywords': []
        },
        
        ExpenseCategory.UTILITIES: {
            'keywords': [
                'electricity', 'power', 'water', 'gas', 'wifi', 'internet', 'mobile',
                'phone bill', 'broadband', 'utility', 'bill', 'postpaid', 'prepaid',
                'airtel', 'vodafone', 'jio', 'bsnl', 'telecom', 'electricity board'
            ],
            'patterns': [r'(?i)(electricity|water|internet|mobile|bill|utility)'],
            'exclude_keywords': []
        },
        
        ExpenseCategory.ENTERTAINMENT: {
            'keywords': [
                'movie', 'cinema', 'bookmyshow', 'ticket', 'netflix', 'youtube',
                'spotify', 'amazon prime', 'gaming', 'game', 'concert', 'music',
                'entertainment', 'recreation', 'hobby', 'hobby center',
                'theme park', 'amusement'
            ],
            'patterns': [r'(?i)(movie|cinema|entertainment|netflix|gaming|music)'],
            'exclude_keywords': []
        },
        
        ExpenseCategory.SHOPPING: {
            'keywords': [
                'amazon', 'flipkart', 'shop', 'store', 'shopping', 'mall',
                'retail', 'clothing', 'clothes', 'apparel', 'shoe', 'fashion',
                'swiftui', 'target', 'e-commerce', 'online store', 'myntra',
                'ajio', 'brand', 'boutique'
            ],
            'patterns': [r'(?i)(shopping|store|amazon|flipkart|mall|clothing)'],
            'exclude_keywords': ['grocery', 'food']
        },
        
        ExpenseCategory.HEALTH_MEDICAL: {
            'keywords': [
                'hospital', 'doctor', 'medical', 'pharmacy', 'health', 'clinic',
                'medicine', 'dental', 'gym', 'fitness', 'doctor', 'drugstore',
                'ayush', 'health insurance', 'wellness', 'nutrition'
            ],
            'patterns': [r'(?i)(hospital|doctor|medical|pharmacy|health|clinic|gym)'],
            'exclude_keywords': []
        },
        
        ExpenseCategory.EDUCATION: {
            'keywords': [
                'school', 'college', 'university', 'education', 'course', 'tuition',
                'books', 'udemy', 'coursera', 'educationplatform', 'coaching',
                'training', 'seminar', 'fees', 'admission'
            ],
            'patterns': [r'(?i)(school|college|university|education|course|training)'],
            'exclude_keywords': []
        },
        
        ExpenseCategory.INSURANCE: {
            # Deliberately no bare bank names here (e.g. "hdfc", "icici") -
            # those appear constantly in UPI narrations as the OTHER
            # party's bank, unrelated to insurance, and would false-positive
            # on nearly every transfer/investment payment.
            'keywords': [
                'insurance', 'policy', 'premium', 'claim', 'coverage', 'health insurance',
                'car insurance', 'home insurance', 'travel insurance', 'policybazaar'
            ],
            'patterns': [r'(?i)(insurance|policy|premium|coverage)'],
            'exclude_keywords': []
        },
        
        ExpenseCategory.INVESTMENT: {
            'keywords': [
                'investment', 'stock', 'mutual fund', 'forex', 'broker', 'trading',
                'zerodha', 'upstox', 'groww', 'nifty', 'sensex', 'fund', 'sip'
            ],
            'patterns': [r'(?i)(investment|stock|mutual fund|trading)'],
            'exclude_keywords': []
        },
        
        ExpenseCategory.SALARY: {
            'keywords': [
                'salary', 'payroll', 'wages', 'income', 'earnings', 'stipend',
                'freelance', 'payment received', 'deposit', 'credit'
            ],
            'patterns': [r'(?i)(salary|payroll|income|wages)'],
            'exclude_keywords': []
        },
        
        ExpenseCategory.TRANSFER: {
            'keywords': [
                'transfer', 'sent', 'received', 'peer transfer', 'p2p', 'gpay',
                'phonepe', 'paytm', 'upi', 'bank transfer', 'wire transfer'
            ],
            'patterns': [r'(?i)(transfer|sent|received|upi|gpay)'],
            'exclude_keywords': []
        }
    }
    
    def __init__(self, custom_rules: Optional[Dict] = None):
        """
        Initialize categorizer with optional custom rules
        
        Args:
            custom_rules: Dictionary of custom categorization rules
        """
        self.rules = self.CATEGORY_RULES.copy()
        if custom_rules:
            self._merge_custom_rules(custom_rules)
    
    def categorize(self, transaction: Dict) -> Tuple[str, float]:
        """
        Categorize a single transaction
        
        Args:
            transaction: Transaction dictionary with 'description' and 'amount'
            
        Returns:
            Tuple of (category_name, confidence_score 0-1)
        """
        description = transaction.get('description', '').lower().strip()

        if not description:
            return ExpenseCategory.OTHER.value, 0.0

        # Try exact keyword match first (highest confidence)
        keyword_category, keyword_confidence = self._match_by_keywords(description)
        if keyword_confidence >= 0.9:
            return keyword_category, keyword_confidence

        # Try pattern matching next (medium confidence). Patterns always
        # score a flat 0.75 on any hit, so a keyword match that didn't
        # clear the 0.9 bar above (e.g. a single strong keyword like
        # "irctc" scoring 0.8) can still be a better answer than whatever
        # generic pattern happens to match elsewhere (e.g. "upi") - compare
        # the two rather than always preferring patterns just because
        # they're checked second.
        pattern_category, pattern_confidence = self._match_by_patterns(description)
        if keyword_confidence >= 0.7 and keyword_confidence >= pattern_confidence:
            return keyword_category, keyword_confidence
        if pattern_confidence >= 0.7:
            return pattern_category, pattern_confidence

        # Try substring matching (lower confidence)
        category, confidence = self._match_by_substring(description)
        
        return category, confidence
    
    def categorize_batch(self, transactions: List[Dict]) -> List[Tuple[str, float]]:
        """
        Categorize multiple transactions
        
        Args:
            transactions: List of transaction dictionaries
            
        Returns:
            List of (category, confidence) tuples
        """
        results = []
        for transaction in transactions:
            category, confidence = self.categorize(transaction)
            results.append((category, confidence))
        
        return results
    
    def _match_by_keywords(self, description: str) -> Tuple[str, float]:
        """
        Match transaction by exact keywords (highest priority)
        
        Returns:
            Tuple of (category_name, confidence_score)
        """
        best_match = (ExpenseCategory.OTHER.value, 0.0)
        
        for category, rules in self.CATEGORY_RULES.items():
            keywords = [k.lower() for k in rules.get('keywords', [])]
            exclude = [k.lower() for k in rules.get('exclude_keywords', [])]
            
            # Check for excluded keywords first
            if any(exc in description for exc in exclude):
                continue
            
            # Check for included keywords
            matched_keywords = [k for k in keywords if k in description]
            
            if matched_keywords:
                # Higher confidence if multiple keywords match. Rounded so
                # e.g. 0.7 + 2*0.1 (which is 0.8999999999999999 in floating
                # point, not exactly 0.9) doesn't silently miss the >= 0.9
                # threshold in categorize() and fall through to a much
                # weaker match tier.
                confidence = round(min(0.95, 0.7 + (len(matched_keywords) * 0.1)), 2)
                if confidence > best_match[1]:
                    best_match = (category.value, confidence)
        
        return best_match
    
    def _match_by_patterns(self, description: str) -> Tuple[str, float]:
        """
        Match transaction by regex patterns
        
        Returns:
            Tuple of (category_name, confidence_score)
        """
        best_match = (ExpenseCategory.OTHER.value, 0.0)
        
        for category, rules in self.CATEGORY_RULES.items():
            patterns = rules.get('patterns', [])
            
            for pattern in patterns:
                if re.search(pattern, description):
                    confidence = 0.75
                    if confidence > best_match[1]:
                        best_match = (category.value, confidence)
                    break
        
        return best_match
    
    def _match_by_substring(self, description: str) -> Tuple[str, float]:
        """
        Match transaction by substring (lowest confidence)
        
        Returns:
            Tuple of (category_name, confidence_score)
        """
        best_match = (ExpenseCategory.OTHER.value, 0.0)
        best_length = 0
        
        for category, rules in self.CATEGORY_RULES.items():
            keywords = [k.lower() for k in rules.get('keywords', [])]
            
            for keyword in keywords:
                if keyword in description:
                    # Prefer longer keyword matches
                    if len(keyword) > best_length:
                        best_length = len(keyword)
                        # Lower confidence for substring match
                        confidence = 0.5 + (len(keyword) / len(description)) * 0.15
                        best_match = (category.value, min(0.65, confidence))
        
        return best_match
    
    def _merge_custom_rules(self, custom_rules: Dict) -> None:
        """
        Merge custom categorization rules with default rules
        
        Args:
            custom_rules: Dictionary of custom rules to merge
        """
        for category_name, rules in custom_rules.items():
            # Try to find matching category
            for category in ExpenseCategory:
                if category.value.lower() == category_name.lower():
                    if category in self.rules:
                        # Merge keywords
                        existing_keywords = self.rules[category].get('keywords', [])
                        new_keywords = rules.get('keywords', [])
                        self.rules[category]['keywords'] = list(set(existing_keywords + new_keywords))
                    break


class CategoryConfidenceAnalyzer:
    """
    Analyzes and validates category confidence scores
    """
    
    @staticmethod
    def is_confident_match(category: str, confidence: float, threshold: float = 0.6) -> bool:
        """
        Check if categorization is confident enough
        
        Args:
            category: Category name
            confidence: Confidence score (0-1)
            threshold: Minimum confidence threshold
            
        Returns:
            True if confidence meets threshold
        """
        return confidence >= threshold and category != ExpenseCategory.OTHER.value
    
    @staticmethod
    def get_suggestion_explanation(category: str, confidence: float) -> str:
        """
        Get human-readable explanation of categorization
        
        Args:
            category: Category name
            confidence: Confidence score
            
        Returns:
            Explanation string
        """
        if category == ExpenseCategory.OTHER.value:
            return 'Could not determine category. Please review manually.'
        
        if confidence >= 0.9:
            return f'High confidence: This is likely {category}'
        elif confidence >= 0.7:
            return f'Medium confidence: This appears to be {category}'
        else:
            return f'Low confidence: This might be {category}, but please verify'


# Example usage
if __name__ == '__main__':
    categorizer = TransactionCategorizer()
    
    test_transactions = [
        {'description': 'Walmart grocery shopping', 'amount': 1500},
        {'description': 'Uber taxi ride', 'amount': 450},
        {'description': 'Netflix subscription monthly', 'amount': 499},
        {'description': 'Unknown merchant XYZ', 'amount': 200},
    ]
    
    print('Testing Transaction Categorization:')
    print('-' * 50)
    
    for transaction in test_transactions:
        category, confidence = categorizer.categorize(transaction)
        explanation = CategoryConfidenceAnalyzer.get_suggestion_explanation(category, confidence)
        print(f"Description: {transaction['description']}")
        print(f"Category: {category} (Confidence: {confidence:.2%})")
        print(f"Explanation: {explanation}")
        print()