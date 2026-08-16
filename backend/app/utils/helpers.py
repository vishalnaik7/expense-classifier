from flask import jsonify
from datetime import datetime


def send_response(success, message, data=None, status_code=200):
    """Send a standardized JSON response"""
    
    response = {
        'success': success,
        'message': message,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if data is not None:
        response['data'] = data
    
    return jsonify(response), status_code


def log_error(error, context=None):
    """Log error with context"""
    import logging
    logger = logging.getLogger(__name__)
    
    if context:
        logger.error(f"{context}: {str(error)}")
    else:
        logger.error(str(error))


def sanitize_input(data):
    """Sanitize user input"""
    if isinstance(data, str):
        return data.strip()
    elif isinstance(data, dict):
        return {k: sanitize_input(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_input(item) for item in data]
    return data
