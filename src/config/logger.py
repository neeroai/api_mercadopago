"""
Structured logging configuration for AWS Lambda and CloudWatch
Uses structlog for consistent JSON logging with AWS integration
"""

import os
import json
import logging
import structlog
from typing import Any, Dict, Optional
from aws_lambda_powertools import Logger as PowertoolsLogger
from aws_lambda_powertools.logging import correlation_paths
from datetime import datetime, timezone

from .settings import get_settings

settings = get_settings()


def add_timestamp(logger, method_name, event_dict):
    """Add timestamp to log entries"""
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


def add_service_context(logger, method_name, event_dict):
    """Add service context to log entries"""
    event_dict.update({
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment
    })
    return event_dict


def add_correlation_id(logger, method_name, event_dict):
    """Add correlation ID from Lambda context if available"""
    # Try to get correlation ID from Lambda context
    correlation_id = getattr(logging.getLoggerClass(), '_correlation_id', None)
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    
    # Try to get request ID from AWS Lambda context
    aws_request_id = os.environ.get('_X_AMZN_TRACE_ID')
    if aws_request_id:
        event_dict["aws_request_id"] = aws_request_id
    
    return event_dict


# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        add_timestamp,
        add_service_context,
        add_correlation_id,
        structlog.dev.ConsoleRenderer() if settings.is_development else structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Get structured logger
logger = structlog.get_logger()

# AWS Powertools logger for Lambda integration
powertools_logger = PowertoolsLogger(
    service=settings.app_name,
    level=settings.log_level,
    correlation_id_path=correlation_paths.API_GATEWAY_REST
)

class IntegrationLogger:
    """Specialized logger for payment integration events"""
    
    def __init__(self):
        self.logger = logger
        self.powertools = powertools_logger
    
    def info(self, message: str, **kwargs):
        """Log info level message"""
        self.logger.info(message, **kwargs)
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            self.powertools.info(message, extra=kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error level message"""
        self.logger.error(message, **kwargs)
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            self.powertools.error(message, extra=kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning level message"""
        self.logger.warning(message, **kwargs)
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            self.powertools.warning(message, extra=kwargs)
    
    def debug(self, message: str, **kwargs):
        """Log debug level message"""
        self.logger.debug(message, **kwargs)
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            self.powertools.debug(message, extra=kwargs)
    
    def log_payment_event(self, event: str, payment_id: str, **metadata):
        """Log payment-related events"""
        self.info(
            f"Payment {event}",
            event_type="payment_event",
            event=event,
            payment_id=payment_id,
            **metadata
        )
    
    def log_webhook_event(self, source: str, event: str, webhook_id: Optional[str] = None, **data):
        """Log webhook events"""
        self.info(
            f"Webhook received: {source} - {event}",
            event_type="webhook_event",
            source=source,
            event=event,
            webhook_id=webhook_id,
            **data
        )
    
    def log_api_call(self, service: str, method: str, endpoint: str, 
                     duration_ms: int, status_code: int, **metadata):
        """Log API calls with performance metrics"""
        self.info(
            f"API Call: {service}",
            event_type="api_call",
            service=service,
            method=method,
            endpoint=endpoint,
            duration_ms=duration_ms,
            status_code=status_code,
            **metadata
        )
    
    def log_integration_event(self, source: str, target: str, event: str, **metadata):
        """Log integration events between services"""
        self.info(
            f"Integration: {source} -> {target}",
            event_type="integration_event",
            source=source,
            target=target,
            event=event,
            **metadata
        )
    
    def log_business_event(self, event: str, customer_id: Optional[str] = None, **metadata):
        """Log business-level events"""
        self.info(
            f"Business Event: {event}",
            event_type="business_event",
            event=event,
            customer_id=customer_id,
            **metadata
        )
    
    def log_error_with_context(self, error: Exception, context: Dict[str, Any]):
        """Log errors with full context"""
        self.error(
            f"Application Error: {str(error)}",
            event_type="application_error",
            error_type=type(error).__name__,
            error_message=str(error),
            **context
        )
    
    def log_lambda_start(self, function_name: str, event: Dict[str, Any]):
        """Log Lambda function start"""
        # Sanitize event data (remove sensitive information)
        sanitized_event = self._sanitize_event(event)
        
        self.info(
            f"Lambda function started: {function_name}",
            event_type="lambda_start",
            function_name=function_name,
            event_summary=self._summarize_event(sanitized_event)
        )
    
    def log_lambda_end(self, function_name: str, duration_ms: int, success: bool = True):
        """Log Lambda function completion"""
        self.info(
            f"Lambda function completed: {function_name}",
            event_type="lambda_end",
            function_name=function_name,
            duration_ms=duration_ms,
            success=success
        )
    
    def log_dynamodb_operation(self, operation: str, table_name: str, 
                              item_key: Optional[str] = None, **metadata):
        """Log DynamoDB operations"""
        self.debug(
            f"DynamoDB {operation}: {table_name}",
            event_type="dynamodb_operation",
            operation=operation,
            table_name=table_name,
            item_key=item_key,
            **metadata
        )
    
    def log_sqs_message(self, queue_name: str, message_id: str, action: str):
        """Log SQS message processing"""
        self.debug(
            f"SQS {action}: {queue_name}",
            event_type="sqs_message",
            queue_name=queue_name,
            message_id=message_id,
            action=action
        )
    
    def _sanitize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive data from event logging"""
        sensitive_keys = [
            'authorization', 'password', 'token', 'secret', 'key',
            'mercadopago_access_token', 'bird_api_key', 'bird_api_secret'
        ]
        
        sanitized = {}
        for key, value in event.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_event(value)
            elif isinstance(value, str) and len(value) > 200:
                sanitized[key] = value[:200] + "...[TRUNCATED]"
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _summarize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Create event summary for logging"""
        return {
            "event_keys": list(event.keys()),
            "event_size": len(json.dumps(event)) if event else 0,
            "source": event.get('source', 'unknown'),
            "event_type": event.get('Records', [{}])[0].get('eventSource', 'unknown') if 'Records' in event else 'api_gateway'
        }


# Global logger instance
integration_logger = IntegrationLogger()


def get_logger() -> IntegrationLogger:
    """Get the integration logger instance"""
    return integration_logger


def set_correlation_id(correlation_id: str):
    """Set correlation ID for request tracking"""
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        powertools_logger.append_keys(correlation_id=correlation_id)


def clear_correlation_id():
    """Clear correlation ID"""
    structlog.contextvars.clear_contextvars()


# AWS Lambda logging decorator
def log_lambda_execution(function_name: Optional[str] = None):
    """Decorator to log Lambda function execution"""
    def decorator(func):
        def wrapper(event, context):
            fname = function_name or getattr(context, 'function_name', 'unknown')
            start_time = datetime.now()
            
            # Set correlation ID from Lambda context
            if hasattr(context, 'aws_request_id'):
                set_correlation_id(context.aws_request_id)
            
            integration_logger.log_lambda_start(fname, event)
            
            try:
                result = func(event, context)
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                integration_logger.log_lambda_end(fname, duration_ms, success=True)
                return result
            
            except Exception as e:
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                integration_logger.log_lambda_end(fname, duration_ms, success=False)
                integration_logger.log_error_with_context(e, {
                    'function_name': fname,
                    'event': event,
                    'context': str(context)
                })
                raise
            
            finally:
                clear_correlation_id()
        
        return wrapper
    return decorator