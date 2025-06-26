"""
AWS Lambda handler for payment operations
Creates payment preferences and manages payment flow
"""

import json
from typing import Dict, Any

from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.metrics import MetricUnit

from src.config.logger import log_lambda_execution
from src.config.settings import get_settings
from src.mercadopago.client import get_mercadopago_client
from src.mercadopago.models import PaymentRequest, PaymentError, ValidationError

# Initialize AWS Lambda Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()

settings = get_settings()


@tracer.capture_lambda_handler
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@metrics.log_metrics
@log_lambda_execution("payment_handler")
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    AWS Lambda handler for payment operations
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    
    try:
        # Get HTTP method and path
        http_method = event.get('httpMethod', '').upper()
        path = event.get('path', '')
        
        logger.info("Processing payment request", extra={
            "method": http_method,
            "path": path
        })
        
        # Route request based on method and path
        if http_method == 'POST' and path.endswith('/create'):
            return create_payment_preference(event)
        elif http_method == 'GET' and '/status' in path:
            return get_payment_status(event)
        elif http_method == 'POST' and '/cancel' in path:
            return cancel_payment(event)
        else:
            logger.warning(f"Unsupported endpoint: {http_method} {path}")
            return {
                'statusCode': 404,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Endpoint not found'})
            }
    
    except Exception as e:
        logger.error(f"Unexpected error in payment handler: {str(e)}")
        metrics.add_metric(name="payment_handler_error", unit=MetricUnit.Count, value=1)
        
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': 'Internal server error'})
        }


@tracer.capture_method
def create_payment_preference(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create payment preference endpoint
    
    Args:
        event: API Gateway event
        
    Returns:
        API Gateway response with payment preference
    """
    
    try:
        # Parse request body
        body = event.get('body', '{}')
        if isinstance(body, str):
            request_data = json.loads(body)
        else:
            request_data = body
        
        logger.info("Creating payment preference", extra={
            "request_data_keys": list(request_data.keys())
        })
        
        # Validate payment request
        try:
            payment_request = PaymentRequest(**request_data)
        except Exception as e:
            logger.error(f"Invalid payment request: {str(e)}")
            metrics.add_metric(name="payment_validation_error", unit=MetricUnit.Count, value=1)
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({
                    'error': 'Invalid payment request',
                    'details': str(e)
                })
            }
        
        # Get MercadoPago client and create preference
        mp_client = get_mercadopago_client()
        payment_response = mp_client.create_payment_preference(payment_request)
        
        logger.info("Payment preference created successfully", extra={
            "payment_id": payment_response.id,
            "transaction_id": payment_response.transaction_id
        })
        
        metrics.add_metric(name="payment_preference_created", unit=MetricUnit.Count, value=1)
        
        return {
            'statusCode': 201,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'success': True,
                'data': payment_response.dict()
            })
        }
        
    except PaymentError as e:
        logger.error(f"Payment error: {str(e)}", extra={
            "error_code": e.code,
            "status_code": e.status_code
        })
        metrics.add_metric(name="payment_error", unit=MetricUnit.Count, value=1)
        
        return {
            'statusCode': e.status_code,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'error': e.message,
                'code': e.code,
                'details': e.details
            })
        }
        
    except Exception as e:
        logger.error(f"Unexpected error creating payment: {str(e)}")
        metrics.add_metric(name="payment_creation_error", unit=MetricUnit.Count, value=1)
        
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': 'Failed to create payment preference'})
        }


@tracer.capture_method
def get_payment_status(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get payment status endpoint
    
    Args:
        event: API Gateway event
        
    Returns:
        API Gateway response with payment status
    """
    
    try:
        # Extract payment ID from path parameters
        path_parameters = event.get('pathParameters', {})
        payment_id = path_parameters.get('id')
        
        if not payment_id:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Payment ID is required'})
            }
        
        logger.info("Getting payment status", extra={
            "payment_id": payment_id
        })
        
        # Get payment status from MercadoPago
        mp_client = get_mercadopago_client()
        payment_data = mp_client.get_payment(payment_id)
        
        logger.info("Payment status retrieved successfully", extra={
            "payment_id": payment_id,
            "status": payment_data.get("status")
        })
        
        metrics.add_metric(name="payment_status_retrieved", unit=MetricUnit.Count, value=1)
        
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'success': True,
                'data': payment_data
            })
        }
        
    except PaymentError as e:
        logger.error(f"Payment error getting status: {str(e)}", extra={
            "error_code": e.code,
            "payment_id": payment_id
        })
        
        return {
            'statusCode': e.status_code,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'error': e.message,
                'code': e.code
            })
        }
        
    except Exception as e:
        logger.error(f"Unexpected error getting payment status: {str(e)}")
        metrics.add_metric(name="payment_status_error", unit=MetricUnit.Count, value=1)
        
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': 'Failed to get payment status'})
        }


@tracer.capture_method
def cancel_payment(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cancel payment endpoint
    
    Args:
        event: API Gateway event
        
    Returns:
        API Gateway response with cancellation status
    """
    
    try:
        # Extract payment ID from path parameters
        path_parameters = event.get('pathParameters', {})
        payment_id = path_parameters.get('id')
        
        if not payment_id:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Payment ID is required'})
            }
        
        logger.info("Cancelling payment", extra={
            "payment_id": payment_id
        })
        
        # Cancel payment preference
        mp_client = get_mercadopago_client()
        success = mp_client.cancel_payment_preference(payment_id)
        
        if success:
            logger.info("Payment cancelled successfully", extra={
                "payment_id": payment_id
            })
            metrics.add_metric(name="payment_cancelled", unit=MetricUnit.Count, value=1)
            
            return {
                'statusCode': 200,
                'headers': get_cors_headers(),
                'body': json.dumps({
                    'success': True,
                    'message': 'Payment cancelled successfully'
                })
            }
        else:
            logger.error("Failed to cancel payment", extra={
                "payment_id": payment_id
            })
            
            return {
                'statusCode': 500,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Failed to cancel payment'})
            }
        
    except Exception as e:
        logger.error(f"Unexpected error cancelling payment: {str(e)}")
        metrics.add_metric(name="payment_cancellation_error", unit=MetricUnit.Count, value=1)
        
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': 'Failed to cancel payment'})
        }


def get_cors_headers() -> Dict[str, str]:
    """
    Get CORS headers for API responses
    
    Returns:
        CORS headers
    """
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With'
    }


# OPTIONS handler for CORS preflight
@tracer.capture_lambda_handler
@logger.inject_lambda_context
def options_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    CORS preflight handler
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        CORS response
    """
    
    return {
        'statusCode': 200,
        'headers': get_cors_headers(),
        'body': json.dumps({'message': 'CORS preflight'})
    }