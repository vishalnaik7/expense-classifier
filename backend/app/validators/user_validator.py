import re
from email_validator import validate_email, EmailNotValidError


class UserValidator:
    """Validate user input"""
    
    MIN_USERNAME_LENGTH = 3
    MAX_USERNAME_LENGTH = 80
    MIN_PASSWORD_LENGTH = 8
    MAX_PASSWORD_LENGTH = 128
    
    ERRORS = {
        'username_required': 'Username is required',
        'username_short': f'Username must be at least {MIN_USERNAME_LENGTH} characters',
        'username_long': f'Username must be at most {MAX_USERNAME_LENGTH} characters',
        'username_invalid': 'Username can only contain letters, numbers, and underscores',
        'username_exists': 'Username already exists',
        'email_required': 'Email is required',
        'email_invalid': 'Invalid email address',
        'email_exists': 'Email already exists',
        'password_required': 'Password is required',
        'password_short': f'Password must be at least {MIN_PASSWORD_LENGTH} characters',
        'password_long': f'Password must be at most {MAX_PASSWORD_LENGTH} characters',
        'password_weak': 'Password must contain uppercase, lowercase, numbers, and special characters',
        'confirm_password_mismatch': 'Passwords do not match',
        'first_name_invalid': 'First name can only contain letters and spaces',
        'last_name_invalid': 'Last name can only contain letters and spaces',
    }
    
    @staticmethod
    def validate_username(username):
        """Validate username format"""
        errors = []
        
        if not username:
            errors.append(UserValidator.ERRORS['username_required'])
            return errors
        
        username = username.strip()
        
        if len(username) < UserValidator.MIN_USERNAME_LENGTH:
            errors.append(UserValidator.ERRORS['username_short'])
        
        if len(username) > UserValidator.MAX_USERNAME_LENGTH:
            errors.append(UserValidator.ERRORS['username_long'])
        
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append(UserValidator.ERRORS['username_invalid'])
        
        return errors
    
    @staticmethod
    def validate_email(email):
        """Validate email format"""
        errors = []
        
        if not email:
            errors.append(UserValidator.ERRORS['email_required'])
            return errors
        
        try:
            validate_email(email.strip(), check_deliverability=False)
        except EmailNotValidError:
            errors.append(UserValidator.ERRORS['email_invalid'])
        
        return errors
    
    @staticmethod
    def validate_password(password):
        """Validate password strength"""
        errors = []
        
        if not password:
            errors.append(UserValidator.ERRORS['password_required'])
            return errors
        
        if len(password) < UserValidator.MIN_PASSWORD_LENGTH:
            errors.append(UserValidator.ERRORS['password_short'])
        
        if len(password) > UserValidator.MAX_PASSWORD_LENGTH:
            errors.append(UserValidator.ERRORS['password_long'])
        
        # Check for complexity
        has_upper = re.search(r'[A-Z]', password)
        has_lower = re.search(r'[a-z]', password)
        has_digit = re.search(r'\d', password)
        has_special = re.search(r'[!@#$%^&*(),.?":{}|<>]', password)
        
        if not (has_upper and has_lower and has_digit and has_special):
            errors.append(UserValidator.ERRORS['password_weak'])
        
        return errors
    
    @staticmethod
    def validate_passwords_match(password, confirm_password):
        """Validate passwords match"""
        if password != confirm_password:
            return [UserValidator.ERRORS['confirm_password_mismatch']]
        return []
    
    @staticmethod
    def validate_name(name, field_name='name'):
        """Validate name field"""
        if not name:
            return []
        
        if not re.match(r'^[a-zA-Z\s]+$', name.strip()):
            return [UserValidator.ERRORS[f'{field_name}_invalid']]
        
        return []
    
    @staticmethod
    def validate_signup_data(data):
        """Validate complete signup data"""
        all_errors = {}
        
        # Username validation
        username_errors = UserValidator.validate_username(data.get('username'))
        if username_errors:
            all_errors['username'] = username_errors
        
        # Email validation
        email_errors = UserValidator.validate_email(data.get('email'))
        if email_errors:
            all_errors['email'] = email_errors
        
        # Password validation
        password_errors = UserValidator.validate_password(data.get('password'))
        if password_errors:
            all_errors['password'] = password_errors
        
        # Confirm password validation
        confirm_errors = UserValidator.validate_passwords_match(
            data.get('password', ''),
            data.get('confirm_password', '')
        )
        if confirm_errors:
            all_errors['confirm_password'] = confirm_errors
        
        # Optional name fields
        if data.get('first_name'):
            first_name_errors = UserValidator.validate_name(data.get('first_name'), 'first_name')
            if first_name_errors:
                all_errors['first_name'] = first_name_errors
        
        if data.get('last_name'):
            last_name_errors = UserValidator.validate_name(data.get('last_name'), 'last_name')
            if last_name_errors:
                all_errors['last_name'] = last_name_errors
        
        return all_errors
    
    @staticmethod
    def validate_login_data(data):
        """Validate login data"""
        all_errors = {}
        
        if not data.get('email'):
            all_errors['email'] = [UserValidator.ERRORS['email_required']]
        elif UserValidator.validate_email(data.get('email')):
            all_errors['email'] = [UserValidator.ERRORS['email_invalid']]
        
        if not data.get('password'):
            all_errors['password'] = [UserValidator.ERRORS['password_required']]
        
        return all_errors
