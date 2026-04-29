import logging
import os
import json
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Dict, Any

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Separate log files for different purposes
APP_LOG_FILE = os.path.join(LOG_DIR, 'app.log')
ERROR_LOG_FILE = os.path.join(LOG_DIR, 'error.log')
ACCESS_LOG_FILE = os.path.join(LOG_DIR, 'access.log')

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# Enhanced formatter with more details
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
            
        # Add extra fields if present
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                          'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                          'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process', 'getMessage']:
                log_entry[key] = value
                
        return json.dumps(log_entry, default=str)

# Standard formatter for console
standard_formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s %(name)s:%(lineno)d: %(message)s'
)

# JSON formatter for files
json_formatter = JSONFormatter()

# App log handler (general application logs)
app_handler = RotatingFileHandler(APP_LOG_FILE, maxBytes=10*1024*1024, backupCount=10)
app_handler.setFormatter(json_formatter)
app_handler.setLevel(LOG_LEVEL)

# Error log handler (only errors and critical)
error_handler = RotatingFileHandler(ERROR_LOG_FILE, maxBytes=10*1024*1024, backupCount=10)
error_handler.setFormatter(json_formatter)
error_handler.setLevel(logging.ERROR)

# Access log handler (API requests/responses)
access_handler = RotatingFileHandler(ACCESS_LOG_FILE, maxBytes=10*1024*1024, backupCount=10)
access_handler.setFormatter(json_formatter)
access_handler.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(standard_formatter)
console_handler.setLevel(LOG_LEVEL)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)

# Remove existing handlers to avoid duplicates
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Add handlers
root_logger.addHandler(app_handler)
root_logger.addHandler(error_handler)
root_logger.addHandler(console_handler)

# Create access logger separately
access_logger = logging.getLogger('access')
access_logger.setLevel(logging.INFO)
access_logger.addHandler(access_handler)
access_logger.propagate = False  # Don't propagate to root logger

# Utility to get a module-specific logger
def get_logger(name=None):
    return logging.getLogger(name)

# Utility to log API requests
def log_api_request(method: str, path: str, user_id: str = None, 
                   status_code: int = None, response_time: float = None, 
                   request_data: Dict[str, Any] = None, response_data: Dict[str, Any] = None):
    """Log API request/response details"""
    log_data = {
        'type': 'api_request',
        'method': method,
        'path': path,
        'user_id': user_id,
        'status_code': status_code,
        'response_time_ms': round(response_time * 1000, 2) if response_time else None,
        'request_data': request_data,
        'response_data': response_data
    }
    access_logger.info("API Request", extra=log_data)

# Utility to log errors with context
def log_error(error: Exception, context: Dict[str, Any] = None, user_id: str = None):
    """Log errors with additional context"""
    log_data = {
        'type': 'error',
        'error_type': type(error).__name__,
        'error_message': str(error),
        'user_id': user_id,
        'context': context
    }
    error_logger = logging.getLogger('error')
    error_logger.error(f"Error occurred: {str(error)}", extra=log_data)

# Utility to log business events
def log_business_event(event_type: str, user_id: str = None, details: Dict[str, Any] = None):
    """Log business events like user actions, subscription changes, etc."""
    log_data = {
        'type': 'business_event',
        'event_type': event_type,
        'user_id': user_id,
        'details': details
    }
    business_logger = logging.getLogger('business')
    business_logger.info(f"Business event: {event_type}", extra=log_data) 