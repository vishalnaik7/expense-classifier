from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token
from datetime import datetime, timedelta
from app.extensions import db
from app.models.user import User, RefreshTokenBlacklist
from app.validators.user_validator import UserValidator


class AuthService:
    """Handle authentication logic"""
    
    @staticmethod
    def register_user(username, email, password, first_name=None, last_name=None):
        """Register a new user"""
        
        # Check if user exists
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            errors = {}
            if existing_user.username == username:
                errors['username'] = [UserValidator.ERRORS['username_exists']]
            if existing_user.email == email:
                errors['email'] = [UserValidator.ERRORS['email_exists']]
            return None, errors
        
        # Create new user
        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        return user, {}
    
    @staticmethod
    def login_user(email, password):
        """Authenticate user"""
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return None, {'email': ['Email not found']}
        
        if not user.verify_password(password):
            return None, {'password': ['Invalid password']}
        
        if not user.is_active:
            return None, {'account': ['Account is deactivated']}
        
        user.update_last_login()
        
        return user, {}
    
    @staticmethod
    def create_tokens(user_id):
        """Create access and refresh tokens"""
        
        access_token = create_access_token(
            identity=user_id,
            expires_delta=current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
        )
        
        refresh_token = create_refresh_token(
            identity=user_id,
            expires_delta=current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
        )
        
        return access_token, refresh_token
    
    @staticmethod
    def refresh_access_token(user_id):
        """Create new access token from refresh token"""
        
        access_token = create_access_token(
            identity=user_id,
            expires_delta=current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
        )
        
        return access_token
    
    @staticmethod
    def revoke_token(user_id, jti, expires_at):
        """Revoke a refresh token"""
        
        token_entry = RefreshTokenBlacklist(
            user_id=user_id,
            jti=jti,
            expires_at=expires_at
        )
        
        db.session.add(token_entry)
        db.session.commit()
    
    @staticmethod
    def is_token_revoked(jti):
        """Check if token is revoked"""
        
        return RefreshTokenBlacklist.query.filter_by(jti=jti).first() is not None
    
    @staticmethod
    def get_user_by_id(user_id):
        """Get user by ID"""
        return User.query.get(user_id)
    
    @staticmethod
    def update_user_profile(user_id, first_name=None, last_name=None):
        """Update user profile"""
        
        user = AuthService.get_user_by_id(user_id)
        
        if not user:
            return None, {'user': ['User not found']}
        
        if first_name:
            errors = UserValidator.validate_name(first_name, 'first_name')
            if errors:
                return None, {'first_name': errors}
            user.first_name = first_name
        
        if last_name:
            errors = UserValidator.validate_name(last_name, 'last_name')
            if errors:
                return None, {'last_name': errors}
            user.last_name = last_name
        
        db.session.commit()
        
        return user, {}
