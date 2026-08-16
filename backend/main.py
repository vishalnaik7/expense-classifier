"""
Fintech Expense Classifier - Flask Backend (FIXED VERSION)
Complete working implementation with proper JWT handling
"""

from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, jwt_required, get_jwt_identity
import bcrypt
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
from dotenv import load_dotenv
import uuid
import io
import re
import statistics
import csv as csv_module
from collections import defaultdict
from sqlalchemy.exc import IntegrityError

from services.csv_parser import CSVParser, CSVParsingError, DuplicateDetector
from services.categorizer import TransactionCategorizer
from services import llm_extractor
from services.llm_extractor import LLMExtractionError
from services import pdf_parser
from services.pdf_parser import PDFParsingError
from services import goal_advisor
from services.goal_advisor import GoalInsightError
from services import chat_advisor
from services.chat_advisor import ChatAdvisorError
from services import ai_client

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

load_dotenv()

# ============================================================================
# INITIALIZE FLASK APP
# ============================================================================

app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///expense.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-super-secret-key-change-in-production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max request/upload size

ALLOWED_UPLOAD_EXTENSIONS = {'csv', 'pdf'}

# Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app, origins=os.getenv('CORS_ORIGINS', 'http://localhost:3000').split(','), supports_credentials=True)

# ============================================================================
# DATABASE MODELS
# ============================================================================

class User(db.Model):
    """User model for authentication and data isolation"""
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(500), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade='all, delete-orphan')
    uploads = db.relationship('Upload', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def to_dict(self):
        """Convert user to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Category(db.Model):
    """Category model for expense categorization"""
    __tablename__ = 'categories'
    
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    color = db.Column(db.String(7))
    # NULL = a shared default category visible to everyone. Set = a custom
    # category created by (and only visible/editable by) that user.
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True, index=True)

    transactions = db.relationship('Transaction', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'color': self.color,
            'is_custom': self.user_id is not None
        }


class Upload(db.Model):
    """Track file uploads for audit trail"""
    __tablename__ = 'uploads'
    
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    status = db.Column(db.String(50), default='pending')
    parsed_count = db.Column(db.Integer, default=0)
    duplicate_count = db.Column(db.Integer, default=0)
    invalid_row_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)

    transactions = db.relationship('Transaction', backref='upload', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'file_size': self.file_size,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None,
            'status': self.status,
            'parsed_count': self.parsed_count,
            'duplicate_count': self.duplicate_count,
            'invalid_row_count': self.invalid_row_count,
            'error_message': self.error_message
        }


class Transaction(db.Model):
    """Transaction model for expense data"""
    __tablename__ = 'transactions'
    
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    upload_id = db.Column(db.String(36), db.ForeignKey('uploads.id'), nullable=True)
    transaction_date = db.Column(db.Date, nullable=False, index=True)
    description = db.Column(db.String(500), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category_id = db.Column(db.String(36), db.ForeignKey('categories.id'), nullable=True)
    transaction_type = db.Column(db.String(20), default='debit')
    confidence = db.Column(db.Float, default=0.0)
    tx_hash = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'tx_hash', name='uq_user_tx_hash'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.transaction_date.isoformat() if self.transaction_date else None,
            'description': self.description,
            'amount': float(self.amount),
            'category': self.category.to_dict() if self.category else None,
            'type': self.transaction_type,
            'confidence': self.confidence,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Budget(db.Model):
    """A user's monthly spending limit for one category"""
    __tablename__ = 'budgets'

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    category_id = db.Column(db.String(36), db.ForeignKey('categories.id'), nullable=False)
    monthly_limit = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = db.relationship('Category', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'category_id', name='uq_user_category_budget'),
    )

    def to_dict(self, spent=0.0):
        limit = float(self.monthly_limit)
        return {
            'id': self.id,
            'category': self.category.to_dict() if self.category else None,
            'monthly_limit': limit,
            'spent': round(spent, 2),
            'remaining': round(limit - spent, 2),
            'percent_used': round((spent / limit) * 100, 1) if limit > 0 else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Goal(db.Model):
    """A user's savings goal - a target amount to reach by an optional date"""
    __tablename__ = 'goals'

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    target_date = db.Column(db.Date, nullable=True)
    icon = db.Column(db.String(10), default='🎯')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        target = float(self.target_amount)
        current = float(self.current_amount)
        return {
            'id': self.id,
            'name': self.name,
            'target_amount': target,
            'current_amount': current,
            'remaining': round(max(target - current, 0), 2),
            'percent_complete': round(min((current / target) * 100, 100), 1) if target > 0 else 0,
            'target_date': self.target_date.isoformat() if self.target_date else None,
            'icon': self.icon,
            'is_complete': current >= target,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ============================================================================
# JWT ERROR HANDLERS
# ============================================================================

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    """Handle expired JWT tokens"""
    return jsonify({'success': False, 'error': 'Token has expired'}), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    """Handle invalid JWT tokens"""
    return jsonify({'success': False, 'error': 'Invalid token format'}), 401


@jwt.unauthorized_loader
def missing_token_callback(error):
    """Handle missing JWT tokens"""
    return jsonify({'success': False, 'error': 'Authorization header missing'}), 401


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Unauthenticated liveness/readiness probe for uptime monitors and hosting platforms (e.g. Railway)."""
    try:
        db.session.execute(db.text('SELECT 1'))
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {e}'
    return jsonify({
        'success': True,
        'data': {'status': 'ok', 'database': db_status}
    }), 200


# ============================================================================
# API ROUTES - AUTHENTICATION
# ============================================================================

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """Register new user account"""
    try:
        data = request.get_json()
        
        # Validate input
        if not all(data.get(k) for k in ['username', 'email', 'password']):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Check if user already exists
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'success': False, 'error': 'Username already exists'}), 409
        
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'success': False, 'error': 'Email already registered'}), 409
        
        # Create new user
        user = User(
            id=str(uuid.uuid4()),
            username=data['username'],
            email=data['email']
        )
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()
        
        # Generate tokens
        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)
        
        return jsonify({
            'success': True,
            'message': 'Account created successfully',
            'data': {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': user.to_dict()
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user and return JWT tokens"""
    try:
        data = request.get_json()
        
        # Validate input
        if not data.get('email') or not data.get('password'):
            return jsonify({'success': False, 'error': 'Missing email or password'}), 400
        
        # Find user by email
        user = User.query.filter_by(email=data['email']).first()
        if not user or not user.check_password(data['password']):
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Generate tokens
        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'data': {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': user.to_dict()
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current authenticated user"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'data': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API ROUTES - TRANSACTIONS
# ============================================================================

@app.route('/api/transactions', methods=['GET'])
@jwt_required()
def get_transactions():
    """Get user's transactions with pagination"""
    try:
        user_id = get_jwt_identity()
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # Base query
        query = Transaction.query.filter_by(user_id=user_id)
        
        # Filters
        category_id = request.args.get('category')
        if category_id:
            query = query.filter_by(category_id=category_id)

        date_from = request.args.get('date_from')
        if date_from:
            query = query.filter(Transaction.transaction_date >= date_from)

        date_to = request.args.get('date_to')
        if date_to:
            query = query.filter(Transaction.transaction_date <= date_to)

        transaction_type = request.args.get('type')
        if transaction_type in ('debit', 'credit'):
            query = query.filter(Transaction.transaction_type == transaction_type)

        search = request.args.get('search')
        if search:
            query = query.filter(Transaction.description.ilike(f'%{search}%'))

        # Sort by date descending
        query = query.order_by(Transaction.transaction_date.desc())
        
        # Paginate
        paginated = query.paginate(page=page, per_page=per_page)
        
        return jsonify({
            'success': True,
            'data': [t.to_dict() for t in paginated.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': paginated.total,
                'pages': paginated.pages
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/transactions/<transaction_id>', methods=['PUT'])
@jwt_required()
def update_transaction(transaction_id):
    """Update transaction category"""
    try:
        user_id = get_jwt_identity()
        transaction = Transaction.query.get(transaction_id)
        
        # Verify ownership
        if not transaction or transaction.user_id != user_id:
            return jsonify({'success': False, 'error': 'Transaction not found'}), 404
        
        data = request.get_json()
        
        # Update category if provided
        if data.get('category_id'):
            category = Category.query.get(data['category_id'])
            if not category:
                return jsonify({'success': False, 'error': 'Category not found'}), 404
            transaction.category_id = data['category_id']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Transaction updated',
            'data': transaction.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API ROUTES - CSV UPLOAD
# ============================================================================

def _get_or_create_category(name):
    """
    Look up a *global* category by name (case-insensitive), falling back to
    Other. The automatic categorizer only ever produces names from its fixed
    system enum, so this always resolves against shared/global categories -
    never a user's custom ones - to avoid ambiguity if a user happens to
    name a custom category the same as a system one.
    """
    category = Category.query.filter(
        Category.user_id.is_(None), db.func.lower(Category.name) == name.lower()
    ).first()
    if category:
        return category
    category = Category.query.filter(
        Category.user_id.is_(None), db.func.lower(Category.name) == 'other'
    ).first()
    if category:
        return category
    # Should not happen once default categories are seeded, but guard anyway
    category = Category(id=str(uuid.uuid4()), name='Other', icon='📦', color='#CCCCCC')
    db.session.add(category)
    db.session.flush()
    return category


@app.route('/api/uploads', methods=['POST'])
@jwt_required()
def upload_csv():
    """Upload a bank statement (CSV or PDF): parse, dedupe, categorize and store transactions."""
    user_id = get_jwt_identity()

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided. Attach a CSV or PDF file under the "file" field.'}), 400

    file = request.files['file']

    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    extension = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({'success': False, 'error': 'Only .csv and .pdf files are supported'}), 400

    file_content = file.read()
    file_size = len(file_content)

    if file_size == 0:
        return jsonify({'success': False, 'error': 'The uploaded file is empty'}), 400

    upload_record = Upload(
        id=str(uuid.uuid4()),
        user_id=user_id,
        filename=file.filename,
        file_size=file_size,
        status='processing'
    )
    db.session.add(upload_record)
    db.session.flush()

    # Parse the file — malformed/corrupt files are caught here. PDFs are
    # handled by extracting their transaction table and reusing the same
    # CSVParser a .csv upload goes through (see services/pdf_parser.py), so
    # both formats get identical date/amount handling and validation. If
    # the deterministic parser can't make sense of the layout (e.g. bank
    # metadata rows it couldn't skip past, or a PDF with no table grid),
    # fall back to AI-assisted extraction when the configured open-source
    # model provider is ready (see services/ai_client.py) before giving up.
    used_ai_fallback = False
    try:
        if extension == 'pdf':
            parsed_transactions = pdf_parser.parse(file_content)
        else:
            parsed_transactions = CSVParser(file_content).parse()
    except (CSVParsingError, PDFParsingError) as parse_error:
        if not llm_extractor.is_configured():
            upload_record.status = 'failed'
            upload_record.error_message = str(parse_error)
            db.session.commit()
            return jsonify({
                'success': False,
                'error': f'Failed to parse {extension.upper()} file',
                'details': str(parse_error),
                'data': {'upload': upload_record.to_dict()}
            }), 422

        try:
            ai_input = pdf_parser.extract_raw_text(file_content).encode('utf-8') if extension == 'pdf' else file_content
            parsed_transactions = llm_extractor.extract_transactions(ai_input)
            used_ai_fallback = True
        except (LLMExtractionError, PDFParsingError) as llm_error:
            upload_record.status = 'failed'
            upload_record.error_message = (
                f'{parse_error} AI-assisted parsing also failed: {llm_error}'
            )
            db.session.commit()
            return jsonify({
                'success': False,
                'error': f'Failed to parse {extension.upper()} file',
                'details': str(parse_error),
                'ai_fallback_error': str(llm_error),
                'data': {'upload': upload_record.to_dict()}
            }), 422
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Unexpected error while reading file: {str(e)}'}), 500

    if not parsed_transactions:
        upload_record.status = 'failed'
        upload_record.error_message = 'No valid transactions found in file'
        db.session.commit()
        return jsonify({
            'success': False,
            'error': 'No valid transactions found in file',
            'data': {'upload': upload_record.to_dict()}
        }), 422

    # Remove duplicates found within the file itself
    unique_transactions, in_file_duplicates = DuplicateDetector(parsed_transactions).detect_duplicates()

    # Remove duplicates that already exist for this user in the database
    existing_hashes = {
        row[0] for row in db.session.query(Transaction.tx_hash).filter_by(user_id=user_id).all()
    }

    categorizer = TransactionCategorizer()
    inserted_count = 0
    db_duplicate_count = 0

    for txn in unique_transactions:
        if txn['hash'] in existing_hashes:
            db_duplicate_count += 1
            continue

        category_name, confidence = categorizer.categorize(txn)
        category = _get_or_create_category(category_name)

        transaction = Transaction(
            id=str(uuid.uuid4()),
            user_id=user_id,
            upload_id=upload_record.id,
            transaction_date=datetime.strptime(txn['date'], '%Y-%m-%d').date(),
            description=txn['description'],
            amount=txn['amount'],
            category_id=category.id,
            transaction_type=txn['type'],
            confidence=confidence,
            tx_hash=txn['hash']
        )
        db.session.add(transaction)
        existing_hashes.add(txn['hash'])
        inserted_count += 1

    upload_record.status = 'completed'
    upload_record.parsed_count = inserted_count
    upload_record.duplicate_count = len(in_file_duplicates) + db_duplicate_count
    if used_ai_fallback:
        upload_record.error_message = (
            'Parsed with AI-assisted extraction — the standard parser could not read this file\'s layout.'
        )

    try:
        db.session.commit()
    except IntegrityError:
        # Safety net in case of a race between the pre-check and the insert
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Duplicate transactions detected during save. Please retry the upload.'}), 409

    return jsonify({
        'success': True,
        'message': f'Uploaded {inserted_count} new transaction(s)',
        'data': {
            'upload': upload_record.to_dict(),
            'inserted': inserted_count,
            'duplicates_skipped': upload_record.duplicate_count,
            'used_ai_fallback': used_ai_fallback
        }
    }), 201


@app.route('/api/uploads', methods=['GET'])
@jwt_required()
def list_uploads():
    """List the current user's upload history"""
    user_id = get_jwt_identity()
    uploads = Upload.query.filter_by(user_id=user_id).order_by(Upload.upload_date.desc()).all()
    return jsonify({'success': True, 'data': [u.to_dict() for u in uploads]}), 200


# ============================================================================
# API ROUTES - ANALYTICS
# ============================================================================

def _resolve_period_range(period, date_from, date_to):
    """
    Resolve a named period (or explicit date_from/date_to) into a (start, end) date pair.
    Returns (None, None) when no filtering should be applied.
    """
    today = datetime.utcnow().date()

    if period == 'current_month':
        return today.replace(day=1), today
    if period == 'last_3_months':
        return (today - relativedelta(months=3)), today
    if period == 'last_6_months':
        return (today - relativedelta(months=6)), today
    if period == 'ytd':
        return today.replace(month=1, day=1), today

    # Custom explicit range
    start = None
    end = None
    if date_from:
        try:
            start = datetime.strptime(date_from, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('date_from must be in YYYY-MM-DD format')
    if date_to:
        try:
            end = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('date_to must be in YYYY-MM-DD format')
    return start, end


def _previous_period(start_date, end_date):
    """The immediately-preceding period of equal length, for % change comparisons."""
    if not start_date or not end_date:
        return None, None
    period_length = (end_date - start_date).days + 1
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_length - 1)
    return prev_start, prev_end


def _percent_change(current, previous):
    """Percent change from previous -> current, or None when there's nothing to compare against."""
    if previous == 0:
        return None if current == 0 else 100.0
    return round(((current - previous) / previous) * 100, 1)


_MERCHANT_NOISE_TOKENS = {
    'upi', 'dr', 'cr', 'payment', 'from', 'sent', 'using', 'for', 'to', 'of', 'the',
    'yesb', 'utib', 'hdfc', 'icic', 'sbin', 'ibkl', 'punb', 'aubl', 'kkbk', 'idfb',
    'barb', 'mahb', 'ubin', 'uco', 'bkid', 'indb', 'nesf', 'axis', 'icici',
    'account', 'verified', 'wallet', 'via', 'phonepe', 'paytm', 'gpay', 'pinelab',
    'nach', 'neft', 'imps', 'rtgs', 'ach', 'emi', 'debit', 'credit', 'ref', 'txn',
}


def _extract_merchant(description: str) -> str:
    """
    Best-effort merchant name extraction from a bank narration string.

    Real UPI/bank narrations are noisy - reference numbers, bank routing
    codes, and payment-service-provider names - so exact "merchant" names
    can't be pulled out reliably. This strips the obvious noise and returns
    the first couple of remaining meaningful tokens as an approximate
    label; it's a heuristic, not a guarantee.
    """
    tokens = re.split(r'[\/\s]+', description)
    cleaned = []
    for token in tokens:
        letters_only = re.sub(r'[^A-Za-z]', '', token)
        if len(letters_only) < 3 or letters_only.lower() in _MERCHANT_NOISE_TOKENS:
            continue
        cleaned.append(letters_only)
        if len(cleaned) == 2:
            break
    return ' '.join(cleaned).title() if cleaned else 'Other'


@app.route('/api/analytics/summary', methods=['GET'])
@jwt_required()
def get_analytics_summary():
    """Get spending/income summary and breakdowns, optionally filtered by time period"""
    try:
        user_id = get_jwt_identity()

        period = request.args.get('period')  # current_month | last_3_months | last_6_months | ytd
        try:
            start_date, end_date = _resolve_period_range(
                period, request.args.get('date_from'), request.args.get('date_to')
            )
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400

        def transactions_in_range(range_start, range_end):
            q = Transaction.query.filter_by(user_id=user_id)
            if range_start:
                q = q.filter(Transaction.transaction_date >= range_start)
            if range_end:
                q = q.filter(Transaction.transaction_date <= range_end)
            return q.all()

        transactions = transactions_in_range(start_date, end_date)
        debit_txns = [t for t in transactions if t.transaction_type == 'debit']
        credit_txns = [t for t in transactions if t.transaction_type == 'credit']

        total_spent = sum(float(t.amount) for t in debit_txns)
        total_income = sum(float(t.amount) for t in credit_txns)
        total_count = len(transactions)
        average = total_spent / len(debit_txns) if debit_txns else 0
        savings = total_income - total_spent

        # Spending by category - debit only, so income doesn't distort "how
        # much did I spend on X" the way it would if credits were mixed in
        category_totals = defaultdict(float)
        for t in debit_txns:
            cat_name = t.category.name if t.category else 'Other'
            category_totals[cat_name] += float(t.amount)
        category_breakdown = [
            {'name': k, 'value': round(v, 2)}
            for k, v in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        ]
        top_categories = category_breakdown[:5]

        # Monthly spending vs income trend (sorted chronologically, not alphabetically)
        monthly_spend = defaultdict(float)
        monthly_income = defaultdict(float)
        for t in debit_txns:
            monthly_spend[(t.transaction_date.year, t.transaction_date.month)] += float(t.amount)
        for t in credit_txns:
            monthly_income[(t.transaction_date.year, t.transaction_date.month)] += float(t.amount)

        monthly_trends = [
            {
                'month': datetime(year, month, 1).strftime('%b %Y'),
                'amount': round(monthly_spend.get((year, month), 0), 2),
                'spending': round(monthly_spend.get((year, month), 0), 2),
                'income': round(monthly_income.get((year, month), 0), 2),
            }
            for year, month in sorted(set(monthly_spend) | set(monthly_income))
        ]

        # Top merchants - approximate, extracted from debit narrations (see _extract_merchant)
        merchant_totals = defaultdict(float)
        for t in debit_txns:
            merchant_totals[_extract_merchant(t.description)] += float(t.amount)
        top_merchants = [
            {'name': k, 'amount': round(v, 2)}
            for k, v in sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        # % change vs the immediately preceding period of equal length
        prev_start, prev_end = _previous_period(start_date, end_date)
        spending_change = income_change = transactions_change = None
        if prev_start and prev_end:
            prev_transactions = transactions_in_range(prev_start, prev_end)
            prev_spent = sum(float(t.amount) for t in prev_transactions if t.transaction_type == 'debit')
            prev_income = sum(float(t.amount) for t in prev_transactions if t.transaction_type == 'credit')
            spending_change = _percent_change(total_spent, prev_spent)
            income_change = _percent_change(total_income, prev_income)
            transactions_change = _percent_change(total_count, len(prev_transactions))

        return jsonify({
            'success': True,
            'data': {
                'totalSpent': round(total_spent, 2),
                'totalIncome': round(total_income, 2),
                'savings': round(savings, 2),
                'totalTransactions': total_count,
                'averageTransaction': round(average, 2),
                'categoryBreakdown': category_breakdown,
                'monthlyTrends': monthly_trends,
                'topCategories': top_categories,
                'topMerchants': top_merchants,
                'change': {
                    'spending': spending_change,
                    'income': income_change,
                    'transactions': transactions_change,
                },
                'period': {
                    'from': start_date.isoformat() if start_date else None,
                    'to': end_date.isoformat() if end_date else None
                }
            }
        }), 200

    except Exception as e:
        print(f'Analytics error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/categories', methods=['GET'])
@jwt_required()
def get_categories():
    """Get all shared categories plus this user's own custom categories"""
    try:
        user_id = get_jwt_identity()
        categories = Category.query.filter(
            db.or_(Category.user_id.is_(None), Category.user_id == user_id)
        ).order_by(Category.user_id.is_(None).desc(), Category.name).all()
        return jsonify({
            'success': True,
            'data': [c.to_dict() for c in categories]
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/categories', methods=['POST'])
@jwt_required()
def create_category():
    """Create a custom category owned by the current user"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()

        if not name:
            return jsonify({'success': False, 'error': 'Category name is required'}), 400

        existing = Category.query.filter(
            db.or_(Category.user_id.is_(None), Category.user_id == user_id),
            db.func.lower(Category.name) == name.lower()
        ).first()
        if existing:
            return jsonify({'success': False, 'error': 'A category with this name already exists'}), 409

        category = Category(
            id=str(uuid.uuid4()),
            name=name,
            icon=data.get('icon', '🏷️'),
            color=data.get('color', '#94A3B8'),
            user_id=user_id
        )
        db.session.add(category)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Category created', 'data': category.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/categories/<category_id>', methods=['PUT'])
@jwt_required()
def update_category(category_id):
    """Rename/recolor a custom category. Shared/system categories cannot be edited."""
    try:
        user_id = get_jwt_identity()
        category = Category.query.get(category_id)

        if not category or category.user_id != user_id:
            return jsonify({'success': False, 'error': 'Custom category not found'}), 404

        data = request.get_json() or {}
        if data.get('name'):
            category.name = data['name'].strip()
        if 'icon' in data:
            category.icon = data['icon']
        if 'color' in data:
            category.color = data['color']

        db.session.commit()
        return jsonify({'success': True, 'message': 'Category updated', 'data': category.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/categories/<category_id>', methods=['DELETE'])
@jwt_required()
def delete_category(category_id):
    """Delete a custom category, reassigning any of its transactions to Other."""
    try:
        user_id = get_jwt_identity()
        category = Category.query.get(category_id)

        if not category or category.user_id != user_id:
            return jsonify({'success': False, 'error': 'Custom category not found'}), 404

        other_category = Category.query.filter(
            Category.user_id.is_(None), db.func.lower(Category.name) == 'other'
        ).first()
        Transaction.query.filter_by(category_id=category.id, user_id=user_id).update(
            {'category_id': other_category.id if other_category else None}
        )
        Budget.query.filter_by(category_id=category.id, user_id=user_id).delete()

        db.session.delete(category)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Category deleted'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API ROUTES - BUDGETS
# ============================================================================

def _current_month_range():
    today = datetime.utcnow().date()
    return today.replace(day=1), today


@app.route('/api/budgets', methods=['GET'])
@jwt_required()
def get_budgets():
    """List the user's budgets with real spend-to-date for the current month"""
    try:
        user_id = get_jwt_identity()
        start_date, end_date = _current_month_range()

        budgets = Budget.query.filter_by(user_id=user_id).all()

        spend_by_category = dict(
            db.session.query(Transaction.category_id, db.func.sum(Transaction.amount))
            .filter(
                Transaction.user_id == user_id,
                Transaction.transaction_type == 'debit',
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date
            )
            .group_by(Transaction.category_id)
            .all()
        )

        data = [
            b.to_dict(spent=float(spend_by_category.get(b.category_id, 0)))
            for b in budgets
        ]
        return jsonify({'success': True, 'data': data}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/budgets', methods=['POST'])
@jwt_required()
def create_budget():
    """Set a monthly spending limit for a category (one budget per category per user)"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        category_id = data.get('category_id')
        monthly_limit = data.get('monthly_limit')

        if not category_id or monthly_limit is None:
            return jsonify({'success': False, 'error': 'category_id and monthly_limit are required'}), 400
        try:
            monthly_limit = float(monthly_limit)
            if monthly_limit <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'monthly_limit must be a positive number'}), 400

        category = Category.query.filter(
            Category.id == category_id,
            db.or_(Category.user_id.is_(None), Category.user_id == user_id)
        ).first()
        if not category:
            return jsonify({'success': False, 'error': 'Category not found'}), 404

        existing = Budget.query.filter_by(user_id=user_id, category_id=category_id).first()
        if existing:
            existing.monthly_limit = monthly_limit
            db.session.commit()
            return jsonify({'success': True, 'message': 'Budget updated', 'data': existing.to_dict()}), 200

        budget = Budget(id=str(uuid.uuid4()), user_id=user_id, category_id=category_id, monthly_limit=monthly_limit)
        db.session.add(budget)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Budget created', 'data': budget.to_dict()}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'A budget for this category already exists'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/budgets/<budget_id>', methods=['PUT'])
@jwt_required()
def update_budget(budget_id):
    """Update a budget's monthly limit"""
    try:
        user_id = get_jwt_identity()
        budget = Budget.query.get(budget_id)
        if not budget or budget.user_id != user_id:
            return jsonify({'success': False, 'error': 'Budget not found'}), 404

        data = request.get_json() or {}
        try:
            monthly_limit = float(data.get('monthly_limit'))
            if monthly_limit <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'monthly_limit must be a positive number'}), 400

        budget.monthly_limit = monthly_limit
        db.session.commit()
        return jsonify({'success': True, 'message': 'Budget updated', 'data': budget.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/budgets/<budget_id>', methods=['DELETE'])
@jwt_required()
def delete_budget(budget_id):
    """Remove a budget"""
    try:
        user_id = get_jwt_identity()
        budget = Budget.query.get(budget_id)
        if not budget or budget.user_id != user_id:
            return jsonify({'success': False, 'error': 'Budget not found'}), 404

        db.session.delete(budget)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Budget deleted'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API ROUTES - GOALS
# ============================================================================

# Heuristic essential/discretionary split of the seeded spending categories,
# used to tell a user which of their top categories are realistic to cut
# back on (discretionary) versus fixed costs (essential). Approximate by
# nature - a category name alone can't capture every real-world case.
_ESSENTIAL_CATEGORIES = {'Groceries', 'Utilities', 'Health & Medical', 'Insurance', 'Transport', 'Education'}
_DISCRETIONARY_CATEGORIES = {'Food & Dining', 'Entertainment', 'Shopping'}


def _category_spend_type(name):
    if name in _ESSENTIAL_CATEGORIES:
        return 'essential'
    if name in _DISCRETIONARY_CATEGORIES:
        return 'discretionary'
    return 'other'


def _trend_direction(recent_avg, earlier_avg, threshold=0.1):
    """Compares two period averages and buckets the change into up/down/flat, ignoring noise under `threshold`."""
    if earlier_avg == 0:
        if recent_avg == 0:
            return 'flat'
        return 'up' if recent_avg > 0 else 'down'
    change = (recent_avg - earlier_avg) / abs(earlier_avg)
    if change > threshold:
        return 'up'
    if change < -threshold:
        return 'down'
    return 'flat'


def _months_until(target_date):
    """Whole months from today until target_date, rounded up, floored at 1 (a deadline this month still needs saving now)."""
    today = datetime.utcnow().date()
    if target_date <= today:
        return 1
    rd = relativedelta(target_date, today)
    months = rd.years * 12 + rd.months
    if rd.days > 0:
        months += 1
    return max(months, 1)


def _build_goal_context(user_id, goal):
    """
    Retrieval step of the goal-insight RAG pipeline. Pulls as much of this
    user's transaction history as is useful (up to 12 months, or less if
    the account is newer) and aggregates it - via SQL/in-memory aggregation,
    not full-text/vector search, since transaction history is structured
    tabular data rather than a free-text document corpus - into the facts
    a real savings advisor would actually ask for:

    - monthly income/spending/net-savings, plus whether savings are
      trending up or down (recent half of the window vs the earlier half)
    - volatility of monthly net savings, so the completion projection can
      give a realistic/optimistic/pessimistic range instead of one number
      that implies false precision
    - top spending categories, each tagged essential vs discretionary and
      with its own recent-vs-earlier spending trend, so advice can target
      categories that are both cuttable and actually growing
    - current-month budget status
    - the user's OTHER active goals and what each would need per month to
      hit its own deadline, so this goal's plan accounts for money that's
      already spoken for elsewhere

    Always scoped to `user_id`, same as every other query in this app.
    """
    today = datetime.utcnow().date()
    earliest = db.session.query(db.func.min(Transaction.transaction_date)).filter_by(user_id=user_id).scalar()
    max_lookback_start = today.replace(day=1) - relativedelta(months=11)  # up to 12 months of history
    window_start = max(earliest.replace(day=1), max_lookback_start) if earliest else max_lookback_start

    txns = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.transaction_date >= window_start,
        Transaction.transaction_date <= today,
    ).all()

    monthly_income = defaultdict(float)
    monthly_spend = defaultdict(float)
    category_totals = defaultdict(float)

    for t in txns:
        key = (t.transaction_date.year, t.transaction_date.month)
        if t.transaction_type == 'credit':
            monthly_income[key] += float(t.amount)
        else:
            monthly_spend[key] += float(t.amount)
            cat_name = t.category.name if t.category else 'Other'
            category_totals[cat_name] += float(t.amount)

    months_seen = sorted(set(monthly_income) | set(monthly_spend))
    monthly_history = [
        {
            'month': datetime(year, month, 1).strftime('%b %Y'),
            'income': round(monthly_income.get((year, month), 0), 2),
            'spending': round(monthly_spend.get((year, month), 0), 2),
            'net_savings': round(monthly_income.get((year, month), 0) - monthly_spend.get((year, month), 0), 2),
        }
        for year, month in months_seen
    ]

    net_values = [m['net_savings'] for m in monthly_history]
    avg_monthly_savings = sum(net_values) / len(net_values) if net_values else 0.0
    savings_volatility = statistics.pstdev(net_values) if len(net_values) >= 2 else 0.0

    income_values = [m['income'] for m in monthly_history]
    avg_monthly_income = sum(income_values) / len(income_values) if income_values else 0.0
    savings_rate_percent = round((avg_monthly_savings / avg_monthly_income) * 100, 1) if avg_monthly_income > 0 else None

    # Recent half of the window vs the earlier half, for trend detection.
    half = max(1, len(months_seen) // 2)
    recent_months = set(months_seen[-half:])
    earlier_months = set(months_seen[:-half]) if len(months_seen) > half else set()

    savings_trend = None
    if earlier_months:
        recent_avg = sum(monthly_income.get(k, 0) - monthly_spend.get(k, 0) for k in recent_months) / len(recent_months)
        earlier_avg = sum(monthly_income.get(k, 0) - monthly_spend.get(k, 0) for k in earlier_months) / len(earlier_months)
        direction = _trend_direction(recent_avg, earlier_avg)
        savings_trend = {
            'direction': {'up': 'improving', 'down': 'declining', 'flat': 'flat'}[direction],
            'recent_avg_monthly_savings': round(recent_avg, 2),
            'earlier_avg_monthly_savings': round(earlier_avg, 2),
        }

    category_recent = defaultdict(float)
    category_earlier = defaultdict(float)
    for t in txns:
        if t.transaction_type != 'debit':
            continue
        key = (t.transaction_date.year, t.transaction_date.month)
        cat_name = t.category.name if t.category else 'Other'
        if key in recent_months:
            category_recent[cat_name] += float(t.amount)
        elif key in earlier_months:
            category_earlier[cat_name] += float(t.amount)

    top_spending_categories = []
    for name, total in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]:
        cat_trend = None
        if earlier_months:
            recent_avg = category_recent.get(name, 0) / len(recent_months)
            earlier_avg = category_earlier.get(name, 0) / len(earlier_months)
            cat_trend = _trend_direction(recent_avg, earlier_avg)
        top_spending_categories.append({
            'name': name,
            'amount': round(total, 2),
            'spend_type': _category_spend_type(name),
            'trend': cat_trend,  # 'up'/'down'/'flat' spend trend, or null with <2 months of history
        })

    month_start, month_end = _current_month_range()
    budgets = Budget.query.filter_by(user_id=user_id).all()
    budget_status = [
        {
            'category': b.category.name if b.category else 'Unknown',
            'monthly_limit': float(b.monthly_limit),
            'spent_this_month': round(sum(
                float(t.amount) for t in txns
                if t.category_id == b.category_id and t.transaction_type == 'debit'
                and month_start <= t.transaction_date <= month_end
            ), 2),
        }
        for b in budgets
    ]

    target = float(goal.target_amount)
    current = float(goal.current_amount)
    remaining = round(max(target - current, 0), 2)
    goal_monthly_required = round(remaining / _months_until(goal.target_date), 2) if goal.target_date and remaining > 0 else None

    other_goals = Goal.query.filter(Goal.user_id == user_id, Goal.id != goal.id).all()
    other_active_goals = []
    for g in other_goals:
        g_target, g_current = float(g.target_amount), float(g.current_amount)
        g_remaining = round(max(g_target - g_current, 0), 2)
        if g_remaining <= 0:
            continue  # already complete, doesn't compete for savings
        other_active_goals.append({
            'name': g.name,
            'remaining': g_remaining,
            'target_date': g.target_date.isoformat() if g.target_date else None,
            'monthly_required': round(g_remaining / _months_until(g.target_date), 2) if g.target_date else None,
        })

    deadline_driven_requirements = [r for r in ([goal_monthly_required] + [g['monthly_required'] for g in other_active_goals]) if r is not None]
    combined_monthly_required = round(sum(deadline_driven_requirements), 2) if deadline_driven_requirements else None

    return {
        'goal': {
            'name': goal.name,
            'target_amount': target,
            'current_amount': current,
            'remaining': remaining,
            'target_date': goal.target_date.isoformat() if goal.target_date else None,
            'monthly_required_for_target_date': goal_monthly_required,
        },
        'history_months_analyzed': len(monthly_history),
        'monthly_history': monthly_history,
        'avg_monthly_income': round(avg_monthly_income, 2),
        'avg_monthly_savings': round(avg_monthly_savings, 2),
        'savings_rate_percent': savings_rate_percent,
        'savings_volatility': round(savings_volatility, 2),
        'savings_trend': savings_trend,
        'top_spending_categories': top_spending_categories,
        'budget_status': budget_status,
        'other_active_goals': other_active_goals,
        'combined_monthly_required_across_goals': combined_monthly_required,
    }


@app.route('/api/goals/<goal_id>/insights', methods=['GET'])
@jwt_required()
def get_goal_insights(goal_id):
    """
    Retrieval-augmented savings insight for one goal. Retrieves this
    user's transaction/budget/other-goals data via SQL aggregation
    (_build_goal_context), always computes a pure-math completion
    projection - with a realistic/optimistic/pessimistic range driven by
    the user's actual savings volatility - and, only if the configured
    open-source model provider is ready, asks it to turn that same
    retrieved context into concrete, referenced savings tips. AI failure
    never breaks the endpoint: the math projection and retrieved context
    are still returned, with ai_advice left null and ai_error explaining why.
    """
    try:
        user_id = get_jwt_identity()
        goal = Goal.query.get(goal_id)
        if not goal or goal.user_id != user_id:
            return jsonify({'success': False, 'error': 'Goal not found'}), 404

        context = _build_goal_context(user_id, goal)

        projection = goal_advisor.project_completion(
            remaining_amount=context['goal']['remaining'],
            avg_monthly_savings=context['avg_monthly_savings'],
            savings_volatility=context['savings_volatility'],
            target_date_iso=context['goal']['target_date'],
        )

        ai_advice = None
        ai_error = None
        if goal_advisor.is_configured():
            try:
                ai_advice = goal_advisor.generate_insight(context)
            except GoalInsightError as e:
                ai_error = str(e)

        return jsonify({
            'success': True,
            'data': {
                'goal': goal.to_dict(),
                'projection': projection,
                'context': context,
                'ai_advice': ai_advice,
                'ai_available': goal_advisor.is_configured(),
                'ai_error': ai_error,
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/goals', methods=['GET'])
@jwt_required()
def get_goals():
    """List the user's savings goals"""
    try:
        user_id = get_jwt_identity()
        goals = Goal.query.filter_by(user_id=user_id).order_by(Goal.created_at.desc()).all()
        return jsonify({'success': True, 'data': [g.to_dict() for g in goals]}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/goals', methods=['POST'])
@jwt_required()
def create_goal():
    """Create a new savings goal"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        target_amount = data.get('target_amount')

        if not name or target_amount is None:
            return jsonify({'success': False, 'error': 'name and target_amount are required'}), 400
        try:
            target_amount = float(target_amount)
            if target_amount <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'target_amount must be a positive number'}), 400

        target_date = None
        if data.get('target_date'):
            try:
                target_date = datetime.strptime(data['target_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'target_date must be in YYYY-MM-DD format'}), 400

        goal = Goal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            target_amount=target_amount,
            current_amount=float(data.get('current_amount', 0) or 0),
            target_date=target_date,
            icon=data.get('icon', '🎯')
        )
        db.session.add(goal)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Goal created', 'data': goal.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/goals/<goal_id>', methods=['PUT'])
@jwt_required()
def update_goal(goal_id):
    """Update a goal's details"""
    try:
        user_id = get_jwt_identity()
        goal = Goal.query.get(goal_id)
        if not goal or goal.user_id != user_id:
            return jsonify({'success': False, 'error': 'Goal not found'}), 404

        data = request.get_json() or {}
        if data.get('name'):
            goal.name = data['name'].strip()
        if data.get('target_amount') is not None:
            goal.target_amount = float(data['target_amount'])
        if 'icon' in data:
            goal.icon = data['icon']
        if 'target_date' in data:
            goal.target_date = datetime.strptime(data['target_date'], '%Y-%m-%d').date() if data['target_date'] else None

        db.session.commit()
        return jsonify({'success': True, 'message': 'Goal updated', 'data': goal.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/goals/<goal_id>/contribute', methods=['POST'])
@jwt_required()
def contribute_to_goal(goal_id):
    """Add an amount toward a goal's progress"""
    try:
        user_id = get_jwt_identity()
        goal = Goal.query.get(goal_id)
        if not goal or goal.user_id != user_id:
            return jsonify({'success': False, 'error': 'Goal not found'}), 404

        data = request.get_json() or {}
        try:
            amount = float(data.get('amount'))
            if amount <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'amount must be a positive number'}), 400

        goal.current_amount = float(goal.current_amount) + amount
        db.session.commit()
        return jsonify({'success': True, 'message': 'Contribution added', 'data': goal.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/goals/<goal_id>', methods=['DELETE'])
@jwt_required()
def delete_goal(goal_id):
    """Delete a savings goal"""
    try:
        user_id = get_jwt_identity()
        goal = Goal.query.get(goal_id)
        if not goal or goal.user_id != user_id:
            return jsonify({'success': False, 'error': 'Goal not found'}), 404

        db.session.delete(goal)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Goal deleted'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API ROUTES - AI ASSISTANT (CHAT)
# ============================================================================

def _build_chat_context(user_id):
    """
    Retrieval step for the AI chat assistant: aggregates this user's
    financial picture via SQL - the same RAG approach used for goal
    insights (_build_goal_context) - so chat answers are grounded in real
    numbers instead of the model guessing or answering from general
    knowledge.

    Includes up to 12 months of per-month income/spending/net-savings AND
    a per-month category breakdown (monthly_history), not just the
    current and previous month - a question about a specific past month
    ("how much did I spend on Transport in May?") needs that month looked
    up directly, not guessed from the current month's numbers or an
    unrelated entry in recent_transactions. Always scoped to `user_id`.
    """
    today = datetime.utcnow().date()
    earliest = db.session.query(db.func.min(Transaction.transaction_date)).filter_by(user_id=user_id).scalar()
    max_lookback_start = today.replace(day=1) - relativedelta(months=11)  # up to 12 months of history
    window_start = max(earliest.replace(day=1), max_lookback_start) if earliest else max_lookback_start

    txns = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.transaction_date >= window_start,
        Transaction.transaction_date <= today,
    ).all()

    monthly_income = defaultdict(float)
    monthly_spend = defaultdict(float)
    monthly_category_totals = defaultdict(lambda: defaultdict(float))

    for t in txns:
        key = (t.transaction_date.year, t.transaction_date.month)
        if t.transaction_type == 'credit':
            monthly_income[key] += float(t.amount)
        else:
            monthly_spend[key] += float(t.amount)
            cat_name = t.category.name if t.category else 'Other'
            monthly_category_totals[key][cat_name] += float(t.amount)

    months_seen = sorted(set(monthly_income) | set(monthly_spend))
    monthly_history = [
        {
            'month': datetime(year, month, 1).strftime('%b %Y'),
            'income': round(monthly_income.get((year, month), 0), 2),
            'spending': round(monthly_spend.get((year, month), 0), 2),
            'net_savings': round(monthly_income.get((year, month), 0) - monthly_spend.get((year, month), 0), 2),
            'category_breakdown': [
                {'name': name, 'amount': round(total, 2)}
                for name, total in sorted(monthly_category_totals[(year, month)].items(), key=lambda x: x[1], reverse=True)
            ],
        }
        for year, month in months_seen
    ]

    month_start, month_end = _current_month_range()
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    current_key = (month_start.year, month_start.month)
    prev_key = (prev_month_start.year, prev_month_start.month)

    current_spent = round(monthly_spend.get(current_key, 0), 2)
    current_income = round(monthly_income.get(current_key, 0), 2)
    prev_spent = round(monthly_spend.get(prev_key, 0), 2)
    prev_income = round(monthly_income.get(prev_key, 0), 2)

    category_breakdown_this_month = [
        {'name': name, 'amount': round(total, 2)}
        for name, total in sorted(monthly_category_totals[current_key].items(), key=lambda x: x[1], reverse=True)
    ]

    merchant_totals = defaultdict(float)
    for t in txns:
        if t.transaction_type == 'debit' and month_start <= t.transaction_date <= month_end:
            merchant_totals[_extract_merchant(t.description)] += float(t.amount)
    top_merchants = [
        {'name': name, 'amount': round(total, 2)}
        for name, total in sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    budgets = Budget.query.filter_by(user_id=user_id).all()
    budget_status = [
        {
            'category': b.category.name if b.category else 'Unknown',
            'monthly_limit': float(b.monthly_limit),
            'spent_this_month': round(sum(
                float(t.amount) for t in txns
                if t.category_id == b.category_id and t.transaction_type == 'debit'
                and month_start <= t.transaction_date <= month_end
            ), 2),
        }
        for b in budgets
    ]

    goals_summary = []
    for g in Goal.query.filter_by(user_id=user_id).all():
        target, current = float(g.target_amount), float(g.current_amount)
        goals_summary.append({
            'name': g.name,
            'target_amount': target,
            'current_amount': current,
            'remaining': round(max(target - current, 0), 2),
            'target_date': g.target_date.isoformat() if g.target_date else None,
            'percent_complete': round(min((current / target) * 100, 100), 1) if target > 0 else 0,
        })

    recent_transactions = [
        {
            'date': t.transaction_date.isoformat(),
            'description': t.description,
            'amount': float(t.amount),
            'type': t.transaction_type,
            'category': t.category.name if t.category else 'Other',
        }
        for t in Transaction.query.filter_by(user_id=user_id)
            .order_by(Transaction.transaction_date.desc()).limit(15).all()
    ]

    return {
        'today': today.isoformat(),
        'current_month': {
            'spent': current_spent,
            'income': current_income,
            'savings': round(current_income - current_spent, 2),
        },
        'previous_month': {
            'spent': prev_spent,
            'income': prev_income,
            'savings': round(prev_income - prev_spent, 2),
        },
        'monthly_history': monthly_history,
        'category_breakdown_this_month': category_breakdown_this_month,
        'top_merchants_this_month': top_merchants,
        'budget_status': budget_status,
        'goals': goals_summary,
        'recent_transactions': recent_transactions,
    }


@app.route('/api/chat/languages', methods=['GET'])
@jwt_required()
def get_chat_languages():
    """The language codes/labels the chat UI can offer in its selector - single source of truth with chat_advisor.SUPPORTED_LANGUAGES."""
    return jsonify({
        'success': True,
        'data': [{'code': code, 'label': label} for code, label in chat_advisor.SUPPORTED_LANGUAGES.items()]
    }), 200


@app.route('/api/chat', methods=['POST'])
@jwt_required()
def chat_with_assistant():
    """
    AI Financial Advisor chat: answers a free-text question grounded in
    this user's real transaction/budget/goal data (_build_chat_context).
    Unlike goal insights, there's no non-AI fallback for a chat reply, so
    this endpoint returns a clear 503 if the configured AI provider isn't
    ready (see services/ai_client.py), rather than a degraded response.
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        message = (data.get('message') or '').strip()

        if not message:
            return jsonify({'success': False, 'error': 'message is required'}), 400
        if len(message) > chat_advisor.MAX_MESSAGE_LENGTH:
            return jsonify({
                'success': False,
                'error': f'message is too long (max {chat_advisor.MAX_MESSAGE_LENGTH} characters)'
            }), 400

        language = data.get('language', 'auto')
        if language not in chat_advisor.SUPPORTED_LANGUAGES:
            return jsonify({
                'success': False,
                'error': f'Unsupported language "{language}". Supported: {", ".join(chat_advisor.SUPPORTED_LANGUAGES)}'
            }), 400

        if not chat_advisor.is_configured():
            hint = 'Set GROQ_API_KEY on the backend.' if ai_client.AI_PROVIDER == 'groq' else 'Make sure Ollama is running locally, or set AI_PROVIDER.'
            return jsonify({
                'success': False,
                'error': f'The AI Assistant is not configured. {hint}'
            }), 503

        history = chat_advisor.sanitize_history(data.get('history'))
        context = _build_chat_context(user_id)

        try:
            reply = chat_advisor.answer_question(context, message, history, language=language)
        except ChatAdvisorError as e:
            return jsonify({'success': False, 'error': str(e)}), 502

        return jsonify({'success': True, 'data': {'reply': reply, 'language': language}}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API ROUTES - EXPORT
# ============================================================================

def _get_filtered_transactions(user_id):
    """Shared helper: fetch a user's transactions filtered by period/date_from/date_to/category."""
    period = request.args.get('period')
    start_date, end_date = _resolve_period_range(
        period, request.args.get('date_from'), request.args.get('date_to')
    )

    query = Transaction.query.filter_by(user_id=user_id)
    if start_date:
        query = query.filter(Transaction.transaction_date >= start_date)
    if end_date:
        query = query.filter(Transaction.transaction_date <= end_date)

    category_id = request.args.get('category')
    if category_id:
        query = query.filter_by(category_id=category_id)

    return query.order_by(Transaction.transaction_date.desc()).all()


@app.route('/api/export/csv', methods=['GET'])
@jwt_required()
def export_csv():
    """Export the user's categorized transactions as a downloadable CSV file"""
    try:
        user_id = get_jwt_identity()
        transactions = _get_filtered_transactions(user_id)

        buffer = io.StringIO()
        writer = csv_module.writer(buffer)
        writer.writerow(['Date', 'Description', 'Category', 'Type', 'Amount', 'Confidence'])

        for t in transactions:
            writer.writerow([
                t.transaction_date.isoformat(),
                t.description,
                t.category.name if t.category else 'Other',
                t.transaction_type,
                f'{float(t.amount):.2f}',
                f'{t.confidence:.2f}'
            ])

        mem_file = io.BytesIO(buffer.getvalue().encode('utf-8'))
        buffer.close()

        return send_file(
            mem_file,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'expenses_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/export/pdf', methods=['GET'])
@jwt_required()
def export_pdf():
    """Export a summary spending report as a downloadable PDF"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        transactions = _get_filtered_transactions(user_id)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph('Expense Report', styles['Title']))
        elements.append(Paragraph(f"Generated for {user.username if user else 'user'} on "
                                   f"{datetime.utcnow().strftime('%d %b %Y')}", styles['Normal']))
        elements.append(Spacer(1, 16))

        total_spent = sum(float(t.amount) for t in transactions if t.transaction_type == 'debit')
        elements.append(Paragraph(f'Total Spent: Rs. {total_spent:,.2f}', styles['Heading2']))
        elements.append(Paragraph(f'Total Transactions: {len(transactions)}', styles['Normal']))
        elements.append(Spacer(1, 16))

        # Category breakdown table
        category_totals = defaultdict(float)
        for t in transactions:
            category_totals[t.category.name if t.category else 'Other'] += float(t.amount)

        elements.append(Paragraph('Spending by Category', styles['Heading2']))
        cat_data = [['Category', 'Amount']] + [
            [name, f'Rs. {amount:,.2f}']
            for name, amount in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        ]
        cat_table = Table(cat_data, colWidths=[300, 150])
        cat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        elements.append(cat_table)
        elements.append(Spacer(1, 20))

        # Transaction detail table (most recent 100 to keep the PDF readable)
        elements.append(Paragraph('Recent Transactions', styles['Heading2']))
        txn_data = [['Date', 'Description', 'Category', 'Amount']] + [
            [t.transaction_date.isoformat(), t.description[:40],
             t.category.name if t.category else 'Other', f'Rs. {float(t.amount):,.2f}']
            for t in transactions[:100]
        ]
        txn_table = Table(txn_data, colWidths=[70, 220, 100, 80])
        txn_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ]))
        elements.append(txn_table)

        doc.build(elements)
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'expense_report_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


@app.errorhandler(413)
def file_too_large(error):
    """Handle uploads exceeding MAX_CONTENT_LENGTH"""
    return jsonify({'success': False, 'error': 'File is too large. Maximum upload size is 10MB.'}), 413


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def _sync_schema(engine=None):
    """
    Add any columns that exist on the models but not yet on the actual
    database tables.

    db.create_all() only creates *missing tables* - it never alters a
    table that already exists, so a database file created before a model
    gained a new column (e.g. Category.user_id) is left permanently out of
    sync and every query touching that column fails with "no such column"
    until the file is deleted and recreated. This makes local schema
    changes self-healing instead: safe for nullable/defaulted columns,
    which covers every column added to this app so far.

    Takes an explicit `engine` (defaulting to db.engine) so it can be
    exercised against an isolated throwaway database in tests.
    """
    engine = engine or db.engine
    inspector = db.inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in db.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all() already creates brand-new tables
            existing_columns = {col['name'] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                if not column.nullable and column.default is None and column.server_default is None:
                    # Can't safely auto-add a required column with no default -
                    # would need a real migration and a value for existing rows.
                    print(f'WARNING: {table.name}.{column.name} is missing and cannot be auto-added '
                          f'(NOT NULL with no default). Delete the database file to recreate it.')
                    continue
                column_type = column.type.compile(engine.dialect)
                conn.execute(db.text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type}'))
                print(f'Auto-migrated: added column {table.name}.{column.name}')


def init_db():
    """Initialize database with default categories"""
    with app.app_context():
        db.create_all()
        _sync_schema()

        # Create default categories if not exist
        default_categories = [
            {'name': 'Groceries', 'icon': '🛒', 'color': '#FF6384'},
            {'name': 'Food & Dining', 'icon': '🍽️', 'color': '#36A2EB'},
            {'name': 'Transport', 'icon': '🚗', 'color': '#FFCE56'},
            {'name': 'Utilities', 'icon': '💡', 'color': '#4BC0C0'},
            {'name': 'Entertainment', 'icon': '🎬', 'color': '#9966FF'},
            {'name': 'Shopping', 'icon': '🛍️', 'color': '#FF9F40'},
            {'name': 'Health & Medical', 'icon': '⚕️', 'color': '#FF6384'},
            {'name': 'Education', 'icon': '📚', 'color': '#C9CBCF'},
            {'name': 'Insurance', 'icon': '🛡️', 'color': '#4BC0C0'},
            {'name': 'Investment', 'icon': '📈', 'color': '#36A2EB'},
            {'name': 'Salary', 'icon': '💵', 'color': '#16A34A'},
            {'name': 'Transfer', 'icon': '🔁', 'color': '#8B5CF6'},
            {'name': 'Other', 'icon': '📦', 'color': '#CCCCCC'},
        ]
        
        for cat_data in default_categories:
            if not Category.query.filter_by(name=cat_data['name']).first():
                category = Category(
                    id=str(uuid.uuid4()),
                    name=cat_data['name'],
                    icon=cat_data['icon'],
                    color=cat_data['color']
                )
                db.session.add(category)
        
        db.session.commit()
        print('Database initialized with default categories')


# ============================================================================
# RUN APPLICATION
# ============================================================================

# Runs on import so tables/default categories exist under gunicorn too
# (gunicorn imports `main:app` and never executes the __main__ block below).
init_db()

if __name__ == '__main__':
    print('Fintech Expense Classifier Backend')
    print('Running on http://0.0.0.0:5000')
    print('Frontend should connect to http://localhost:5000')
    app.run(debug=True, host='0.0.0.0', port=5000)