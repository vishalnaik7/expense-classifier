"""
CSV Parser Service for Fintech Expense Classifier
This module handles parsing and validation of bank statement CSV files
Supports multiple CSV formats and includes error handling for malformed data
"""

import csv
import io
import hashlib
from datetime import datetime
from typing import List, Tuple, Dict, Optional
import pandas as pd


class CSVParsingError(Exception):
    """Custom exception for CSV parsing errors"""
    pass


class CSVParser:
    """
    Handles CSV file parsing with validation and error handling
    
    Supported formats:
    - Date, Description, Amount format
    - Date, Description, Debit, Credit format
    - Bank-specific formats (HDFC, ICICI, Axis, etc.)
    """
    
    # Common header patterns for different banks
    HEADER_PATTERNS = {
        'date': ['date', 'transaction date', 'txn date', 'posting date'],
        'description': ['description', 'narration', 'particulars', 'txn description'],
        'amount': ['amount', 'transacted amount', 'debit', 'credit'],
        'debit': ['debit', 'withdrawal'],
        'credit': ['credit', 'deposit']
    }
    
    # Minimum required columns. 'amount' is checked specially in
    # _validate_headers() rather than listed here directly: a split
    # debit/credit layout can satisfy the "there's a debit-side amount"
    # requirement via either an 'amount' column or a 'debit' column,
    # depending on which literal word that bank's header used (see
    # _resolve_amount_and_type()).
    REQUIRED_COLUMNS = ['date', 'description']

    # How many leading rows to scan for a real header when the first row
    # turns out to be bank metadata (e.g. "STATEMENT OF ACCOUNT", account
    # summary lines) rather than column names.
    HEADER_SCAN_WINDOW = 25

    def __init__(self, file_content: bytes):
        """
        Initialize CSV parser with file content
        
        Args:
            file_content: Byte content of CSV file
            
        Raises:
            CSVParsingError: If file is empty or invalid
        """
        if not file_content:
            raise CSVParsingError('File content is empty')
        
        self.file_content = file_content
        self.df = None
        self.normalized_headers = {}
        
    def parse(self) -> List[Dict]:
        """
        Parse CSV file and return list of validated transactions
        
        Returns:
            List of transaction dictionaries
            
        Raises:
            CSVParsingError: If parsing fails
        """
        try:
            # Read CSV file, auto-detecting the real header row if the file
            # has bank metadata (account summaries, titles) above the table
            self.df = self._read_with_header_detection()

            # Validate file is not empty
            if self.df.empty:
                raise CSVParsingError('CSV file is empty. Please provide a file with data.')

            # Normalize headers
            self._normalize_headers()

            # Validate headers exist
            self._validate_headers()

            # Parse and validate transactions
            transactions = self._parse_transactions()

            return transactions

        except pd.errors.EmptyDataError:
            raise CSVParsingError('CSV file appears to be corrupted or empty')
        except pd.errors.ParserError as e:
            raise CSVParsingError(f'CSV parsing failed: {str(e)}')
        except CSVParsingError:
            raise
        except Exception as e:
            raise CSVParsingError(f'Unexpected error during parsing: {str(e)}')

    def _read_with_header_detection(self) -> pd.DataFrame:
        """
        Read the CSV, tolerating leading metadata rows (bank name, account
        summary, "STATEMENT OF ACCOUNT" banners) that aren't the real header.

        Tries the file as-is first; if the resulting columns don't look like
        a transaction table, scans the first HEADER_SCAN_WINDOW raw rows for
        one that does, and re-reads with that row as the header.
        """
        default_df = None
        try:
            default_df = pd.read_csv(io.BytesIO(self.file_content))
        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            pass

        if default_df is not None and self._looks_like_header(list(default_df.columns)):
            return default_df

        header_row = self._find_header_row()
        if header_row is not None:
            candidate = pd.read_csv(io.BytesIO(self.file_content), header=header_row)
            if not candidate.empty:
                return candidate

        if default_df is not None:
            return default_df

        # Let the original error surface if even the plain read failed
        return pd.read_csv(io.BytesIO(self.file_content))

    def _looks_like_header(self, columns: List[str]) -> bool:
        """
        Heuristic: does this row of column names contain at least a date-like
        and an amount-like (or debit/credit-like) column, and is it not
        mostly pandas' auto-generated "Unnamed: N" placeholders?
        """
        normalized = [str(c).lower().strip() for c in columns]
        if not normalized:
            return False

        unnamed_count = sum(1 for c in normalized if c.startswith('unnamed:'))
        if unnamed_count > len(normalized) / 2:
            return False

        has_date = any(any(p in c for p in self.HEADER_PATTERNS['date']) for c in normalized)
        has_amount_like = any(
            any(p in c for p in self.HEADER_PATTERNS['amount'])
            or any(p in c for p in self.HEADER_PATTERNS['debit'])
            or any(p in c for p in self.HEADER_PATTERNS['credit'])
            for c in normalized
        )
        has_description = any(any(p in c for p in self.HEADER_PATTERNS['description']) for c in normalized)

        return has_date and has_amount_like and has_description

    def _find_header_row(self) -> Optional[int]:
        """
        Scan the first HEADER_SCAN_WINDOW raw rows for one that looks like a
        transaction-table header, skipping bank metadata rows above it.

        Returns:
            0-based row index to pass as pandas' `header=`, or None if no
            such row was found within the scan window.
        """
        try:
            text = self.file_content.decode('utf-8-sig', errors='replace')
        except Exception:
            return None

        reader = csv.reader(io.StringIO(text))
        for index, row in enumerate(reader):
            if index >= self.HEADER_SCAN_WINDOW:
                break
            if not row or all(not str(cell).strip() for cell in row):
                continue
            if self._looks_like_header(row):
                return index

        return None
    
    def _normalize_headers(self) -> None:
        """
        Normalize CSV headers to standard format
        Maps various header names to standard names
        """
        column_mapping = {}
        headers = [h.lower().strip() for h in self.df.columns]

        for standard_name, patterns in self.HEADER_PATTERNS.items():
            for header in headers:
                original_header = self.df.columns[headers.index(header)]
                # A column already claimed by an earlier (higher-priority) standard
                # name must not be silently reassigned - e.g. a lone "Debit" column
                # should resolve to 'amount', not get overwritten by the 'debit' rule.
                if original_header in column_mapping:
                    continue
                if any(pattern in header for pattern in patterns):
                    column_mapping[original_header] = standard_name
                    break
        
        # Rename columns
        self.df.rename(columns=column_mapping, inplace=True)
        self.normalized_headers = column_mapping
    
    def _validate_headers(self) -> None:
        """
        Validate that all required columns are present. A debit-side
        amount column is required too, but - matching
        _resolve_amount_and_type() - it may appear as either 'amount' or
        'debit' depending on which literal word the source header used
        (e.g. HDFC's "Withdrawal Amt." normalizes to 'debit', not
        'amount'), so neither alone is treated as strictly required.

        Raises:
            CSVParsingError: If required columns are missing
        """
        missing_columns = [c for c in self.REQUIRED_COLUMNS if c not in self.df.columns]

        if 'amount' not in self.df.columns and 'debit' not in self.df.columns:
            missing_columns.append('amount (or debit)')

        if missing_columns:
            raise CSVParsingError(
                f'Missing required columns: {", ".join(missing_columns)}. '
                f'Available columns: {", ".join(self.df.columns)}'
            )
    
    def _parse_transactions(self) -> List[Dict]:
        """
        Parse individual transactions with validation
        
        Returns:
            List of validated transaction dictionaries
            
        Raises:
            CSVParsingError: If validation fails
        """
        transactions = []
        errors = []
        last_transaction = None

        for index, row in self.df.iterrows():
            # Some bank exports wrap a transaction's narration onto extra
            # lines below it (every column blank except description) -
            # merge those into the previous transaction instead of treating
            # them as invalid rows.
            if last_transaction is not None and self._is_continuation_row(row):
                continuation_text = self._sanitize_string(str(row['description']).strip())
                if continuation_text:
                    last_transaction['description'] = f"{last_transaction['description']} {continuation_text}".strip()
                    last_transaction['hash'] = self._create_hash(
                        last_transaction['date'], last_transaction['description'], last_transaction['amount']
                    )
                continue

            try:
                transaction = self._validate_row(row, index)
                if transaction:
                    transactions.append(transaction)
                    last_transaction = transaction
                else:
                    last_transaction = None
            except ValueError as e:
                errors.append(f'Row {index + 2}: {str(e)}')
                last_transaction = None

        # Report errors but allow partial success if some rows are valid
        if errors and len(transactions) == 0:
            error_message = '\n'.join(errors[:5])  # Show first 5 errors
            if len(errors) > 5:
                error_message += f'\n... and {len(errors) - 5} more errors'
            raise CSVParsingError(error_message)
        
        if errors:
            # Log warnings for invalid rows but continue
            print(f'Warning: {len(errors)} rows had validation issues')
        
        return transactions
    
    def _is_continuation_row(self, row: pd.Series) -> bool:
        """
        True if every column except 'description' is blank on this row.

        Real continuation lines (wrapped narration text) look like this;
        other blank-date noise - repeated page headers, "Opening Balance"
        summary rows, footer text - always has content in some other
        column too, so this stays narrow enough not to swallow it.
        """
        if 'description' not in self.df.columns:
            return False

        for column in self.df.columns:
            if column == 'description':
                continue
            value = row.get(column)
            if pd.isna(value):
                continue
            if str(value).strip():
                return False

        description = str(row.get('description', '')).strip()
        return bool(description) and description.lower() != 'nan'

    def _validate_row(self, row: pd.Series, index: int) -> Optional[Dict]:
        """
        Validate single transaction row
        
        Args:
            row: DataFrame row
            index: Row index for error reporting
            
        Returns:
            Validated transaction dict or None if invalid
            
        Raises:
            ValueError: If validation fails
        """
        # Extract and clean values
        date_str = str(row.get('date', '')).strip()
        description = str(row.get('description', '')).strip()

        # Validate date
        transaction_date = self._parse_date(date_str)
        if not transaction_date:
            raise ValueError(f'Invalid date format: "{date_str}". Expected YYYY-MM-DD or DD/MM/YYYY')

        # Validate description
        if not description or len(description) < 2:
            raise ValueError('Description is empty or too short (minimum 2 characters)')

        # Remove special characters that might cause issues (CSV injection)
        description = self._sanitize_string(description)

        amount, transaction_type = self._resolve_amount_and_type(row)

        # Create transaction hash for duplicate detection
        transaction_hash = self._create_hash(transaction_date, description, amount)

        return {
            'date': transaction_date,
            'description': description,
            'amount': amount,
            'type': transaction_type,
            'hash': transaction_hash,
            'raw_amount': amount if transaction_type == 'debit' else -amount
        }

    def _resolve_amount_and_type(self, row: pd.Series) -> Tuple[float, str]:
        """
        Resolve the transaction amount and its debit/credit direction.

        Bank exports come in two shapes: a single 'amount' column (this
        parser always treats that as a debit/expense), or a split
        debit/credit pair. After header normalization a split layout can
        land as either an 'amount' + 'credit' column (when the debit-side
        header literally contains "debit", e.g. IDFC's "Debit") or a
        'debit' + 'credit' column (when it uses a synonym instead, e.g.
        HDFC's "Withdrawal Amt." / "Deposit Amt.", matched via
        HEADER_PATTERNS['debit'] = ['debit', 'withdrawal']) - so both the
        'amount' and 'debit' columns need to be checked as possible
        sources for the debit side, not just 'amount'. Use whichever
        column actually has a positive value for this row.

        Raises:
            ValueError: if no column has a usable positive amount
        """
        debit_amount = self._to_positive_float(row.get('amount') if 'amount' in row.index else None)
        if debit_amount is None and 'debit' in row.index:
            debit_amount = self._to_positive_float(row.get('debit'))
        if debit_amount is not None:
            return debit_amount, 'debit'

        if 'credit' in row.index:
            credit_amount = self._to_positive_float(row.get('credit'))
            if credit_amount is not None:
                return credit_amount, 'credit'

        if 'amount' in row.index:
            raw_value = row.get('amount')
        elif 'debit' in row.index:
            raw_value = row.get('debit')
        else:
            raw_value = None
        raise ValueError(f'Invalid amount: "{raw_value}". Must be a valid positive number')

    @staticmethod
    def _to_positive_float(value) -> Optional[float]:
        """Parse value as a positive float, or None if blank/invalid/<=0."""
        if value is None or pd.isna(value):
            return None
        try:
            amount = float(str(value).strip().replace(',', ''))
        except ValueError:
            return None
        return amount if amount > 0 else None
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """
        Parse date string in multiple formats
        
        Supports:
        - YYYY-MM-DD
        - DD/MM/YYYY
        - DD-MM-YYYY
        - MM/DD/YYYY
        
        Returns:
            ISO format date string (YYYY-MM-DD) or None if invalid
        """
        date_formats = [
            '%Y-%m-%d',      # YYYY-MM-DD
            '%d/%m/%Y',      # DD/MM/YYYY
            '%d-%m-%Y',      # DD-MM-YYYY
            '%m/%d/%Y',      # MM/DD/YYYY
            '%d/%m/%y',      # DD/MM/YY
            '%m/%d/%y',      # MM/DD/YY
            '%d-%b-%Y',      # 01-Jun-2026 (common Indian bank statement format)
            '%d-%b-%y',      # 01-Jun-26
            '%d %b %Y',      # 01 Jun 2026
            '%d-%B-%Y',      # 01-June-2026
            '%d %B %Y',      # 01 June 2026
            '%Y/%m/%d',      # 2026/06/01
            '%d.%m.%Y',      # 01.06.2026
        ]
        
        for date_format in date_formats:
            try:
                parsed_date = datetime.strptime(date_str, date_format)
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return None
    
    def _sanitize_string(self, text: str) -> str:
        """
        Sanitize string to prevent CSV injection attacks
        
        Removes leading special characters that could be dangerous
        """
        dangerous_chars = ['=', '+', '-', '@']
        if text and text[0] in dangerous_chars:
            text = text[1:]
        
        return text.strip()
    
    def _create_hash(self, date: str, description: str, amount: float) -> str:
        """
        Create hash of transaction for duplicate detection
        
        Args:
            date: Transaction date
            description: Transaction description
            amount: Transaction amount
            
        Returns:
            SHA256 hash of transaction tuple
        """
        transaction_tuple = f'{date}|{description}|{amount}'.encode('utf-8')
        return hashlib.sha256(transaction_tuple).hexdigest()


class DuplicateDetector:
    """
    Detects duplicate transactions based on various criteria
    """
    
    def __init__(self, transactions: List[Dict]):
        """Initialize with list of transactions"""
        self.transactions = transactions
        self.duplicates = []
    
    def detect_duplicates(self) -> Tuple[List[Dict], List[int]]:
        """
        Detect duplicate transactions
        
        Returns:
            Tuple of (unique transactions, duplicate indices)
        """
        seen_hashes = set()
        unique_transactions = []
        duplicate_indices = []
        
        for index, transaction in enumerate(self.transactions):
            transaction_hash = transaction.get('hash')
            
            if transaction_hash in seen_hashes:
                duplicate_indices.append(index)
            else:
                seen_hashes.add(transaction_hash)
                unique_transactions.append(transaction)
        
        self.duplicates = duplicate_indices
        return unique_transactions, duplicate_indices


# Example usage and testing
if __name__ == '__main__':
    # Example CSV content
    sample_csv = b'''Date,Description,Amount
2024-01-15,Grocery Shopping,1500
2024-01-16,Electricity Bill,2000
2024-01-17,Cab Ride,450
'''
    
    try:
        parser = CSVParser(sample_csv)
        transactions = parser.parse()
        print(f'Parsed {len(transactions)} transactions')
        for t in transactions:
            print(t)
    except CSVParsingError as e:
        print(f'Error: {e}')