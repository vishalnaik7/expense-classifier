from functools import wraps
from flask import request
from app.utils.helpers import send_response, log_error
import traceback
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def handle_errors(f):
    """Decorator to handle errors globally"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        
        except IntegrityError as e:
            log_error(e, "Database integrity error")
            return send_response(
                success=False,
                message='Database error: Duplicate entry or constraint violation',
                status_code=409
            )
        
        except SQLAlchemyError as e:
            log_error(e, "Database error")
            return send_response(
                success=False,
                message='Database error occurred',
                status_code=500
            )
        
        except ValueError as e:
            log_error(e, "Validation error")
            return send_response(
                success=False,
                message=str(e),
                status_code=400
            )
        
        except Exception as e:
            log_error(e, "Unexpected error")
            return send_response(
                success=False,
                message='An unexpected error occurred',
                status_code=500
            )
    
    return decorated_function


def validate_json(f):
    """Decorator to validate JSON content type"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.is_json:
            return send_response(
                success=False,
                message='Content-Type must be application/json',
                status_code=400
            )
        return f(*args, **kwargs)
    
    return decorated_function


def require_data_keys(required_keys):
    """Decorator to require specific keys in request data"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            data = request.get_json()
            
            if not data:
                return send_response(
                    success=False,
                    message='Request body is required',
                    status_code=400
                )
            
            missing_keys = [key for key in required_keys if key not in data]
            
            if missing_keys:
                return send_response(
                    success=False,
                    message='Missing required fields',
                    data={'missing_keys': missing_keys},
                    status_code=400
                )
            
            return f(*args, **kwargs)
        
        return decorated_function
    
    return decorator


def rate_limit(max_requests=100, window_seconds=3600):
    """Simple rate limiting decorator"""
    def decorator(f):
        requests_dict = {}
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from datetime import datetime, timedelta
            
            client_ip = request.remote_addr
            now = datetime.utcnow()
            
            if client_ip not in requests_dict:
                requests_dict[client_ip] = []
            
            # Remove old requests outside the window
            window_start = now - timedelta(seconds=window_seconds)
            requests_dict[client_ip] = [
                req_time for req_time in requests_dict[client_ip]
                if req_time > window_start
            ]
            
            # Check if limit exceeded
            if len(requests_dict[client_ip]) >= max_requests:
                return send_response(
                    success=False,
                    message='Rate limit exceeded. Please try again later.',
                    status_code=429
                )
            
            # Add current request
            requests_dict[client_ip].append(now)
            
            return f(*args, **kwargs)
        
        return decorated_function
    
    return decorator
