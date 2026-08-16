from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from datetime import datetime, timedelta
from app.validators.user_validator import UserValidator
from app.services.auth_service import AuthService
from app.utils.decorators import handle_errors
from app.utils.helpers import send_response

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/signup', methods=['POST'])
@handle_errors
def signup():
    """Register a new user"""
    
    data = request.get_json()
    
    if not data:
        return send_response(
            success=False,
            message='Request body is required',
            status_code=400
        )
    
    # Validate input
    validation_errors = UserValidator.validate_signup_data(data)
    
    if validation_errors:
        return send_response(
            success=False,
            message='Validation failed',
            data={'errors': validation_errors},
            status_code=422
        )
    
    # Register user
    user, errors = AuthService.register_user(
        username=data['username'].strip(),
        email=data['email'].strip(),
        password=data['password'],
        first_name=data.get('first_name', '').strip() or None,
        last_name=data.get('last_name', '').strip() or None
    )
    
    if errors:
        return send_response(
            success=False,
            message='Registration failed',
            data={'errors': errors},
            status_code=409
        )
    
    # Create tokens
    access_token, refresh_token = AuthService.create_tokens(user.id)
    
    return send_response(
        success=True,
        message='User registered successfully',
        data={
            'user': user.to_dict(),
            'tokens': {
                'access_token': access_token,
                'refresh_token': refresh_token
            }
        },
        status_code=201
    )


@auth_bp.route('/login', methods=['POST'])
@handle_errors
def login():
    """Login user"""
    
    data = request.get_json()
    
    if not data:
        return send_response(
            success=False,
            message='Request body is required',
            status_code=400
        )
    
    # Validate input
    validation_errors = UserValidator.validate_login_data(data)
    
    if validation_errors:
        return send_response(
            success=False,
            message='Validation failed',
            data={'errors': validation_errors},
            status_code=422
        )
    
    # Authenticate user
    user, errors = AuthService.login_user(
        email=data['email'].strip(),
        password=data['password']
    )
    
    if errors:
        return send_response(
            success=False,
            message='Login failed',
            data={'errors': errors},
            status_code=401
        )
    
    # Create tokens
    access_token, refresh_token = AuthService.create_tokens(user.id)
    
    return send_response(
        success=True,
        message='Login successful',
        data={
            'user': user.to_dict(),
            'tokens': {
                'access_token': access_token,
                'refresh_token': refresh_token
            }
        },
        status_code=200
    )


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
@handle_errors
def refresh():
    """Refresh access token"""
    
    user_id = get_jwt_identity()
    access_token = AuthService.refresh_access_token(user_id)
    
    return send_response(
        success=True,
        message='Token refreshed successfully',
        data={'access_token': access_token},
        status_code=200
    )


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
@handle_errors
def logout():
    """Logout user (revoke refresh token)"""
    
    user_id = get_jwt_identity()
    claims = get_jwt()
    
    # Get jti from the refresh token if provided
    data = request.get_json() or {}
    refresh_token = data.get('refresh_token')
    
    if refresh_token:
        # Revoke the refresh token
        # In production, extract jti from token and add to blacklist
        pass
    
    return send_response(
        success=True,
        message='Logout successful',
        status_code=200
    )


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
@handle_errors
def get_current_user():
    """Get current authenticated user"""
    
    user_id = get_jwt_identity()
    user = AuthService.get_user_by_id(user_id)
    
    if not user:
        return send_response(
            success=False,
            message='User not found',
            status_code=404
        )
    
    return send_response(
        success=True,
        message='User retrieved successfully',
        data={'user': user.to_dict()},
        status_code=200
    )


@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
@handle_errors
def update_profile():
    """Update user profile"""
    
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data:
        return send_response(
            success=False,
            message='Request body is required',
            status_code=400
        )
    
    # Update user
    user, errors = AuthService.update_user_profile(
        user_id,
        first_name=data.get('first_name'),
        last_name=data.get('last_name')
    )
    
    if errors:
        return send_response(
            success=False,
            message='Update failed',
            data={'errors': errors},
            status_code=400
        )
    
    return send_response(
        success=True,
        message='Profile updated successfully',
        data={'user': user.to_dict()},
        status_code=200
    )


@auth_bp.errorhandler(422)
def handle_validation_error(err):
    """Handle validation errors"""
    headers = err.data.get("headers", None)
    messages = err.data.get("messages", ["Invalid request"])
    
    return send_response(
        success=False,
        message='Validation failed',
        data={'errors': messages},
        status_code=422
    )
