"""
AWS Lambda handler for MercadoPago webhooks
Processes payment notifications and triggers downstream actions
"""

import json
import hashlib
import hmac
from typing import Dict, Any

from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.metrics import MetricUnit

from src.config.logger import log_lambda_execution
from src.config.settings import get_settings
from src.mercadopago.client import get_mercadopago_client
from src.mercadopago.models import WebhookNotification, PaymentError

# Initialize AWS Lambda Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()

settings = get_settings()


def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    """
    Verify MercadoPago webhook signature for security
    
    Args:
        payload: Raw webhook payload
        signature: Webhook signature from headers
        secret: Webhook secret
        
    Returns:
        True if signature is valid
    """
    if not signature or not secret:
        return False
    
    try:
        # MercadoPago uses HMAC-SHA256
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures securely
        return hmac.compare_digest(signature, expected_signature)
        
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {str(e)}")
        return False


@tracer.capture_lambda_handler
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@metrics.log_metrics
@log_lambda_execution("mercadopago_webhook_handler")
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    AWS Lambda handler for MercadoPago webhooks
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    
    try:
        # Extract webhook data
        headers = event.get('headers', {})
        body = event.get('body', '')
        
        # Get signature from headers (case-insensitive)
        signature = None
        for key, value in headers.items():
            if key.lower() == 'x-signature':
                signature = value
                break
        
        logger.info("Processing MercadoPago webhook", extra={
            "headers_count": len(headers),
            "body_length": len(body) if body else 0,
            "has_signature": bool(signature)
        })
        
        # Verify webhook signature
        if not verify_webhook_signature(body, signature, settings.mercadopago_webhook_secret):
            logger.warning("Invalid webhook signature")
            metrics.add_metric(name="webhook_signature_invalid", unit=MetricUnit.Count, value=1)
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Invalid signature'})
            }
        
        # Parse webhook payload
        try:
            webhook_data = json.loads(body) if body else {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {str(e)}")
            metrics.add_metric(name="webhook_invalid_json", unit=MetricUnit.Count, value=1)
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid JSON payload'})
            }
        
        # Validate webhook notification structure
        try:
            notification = WebhookNotification(**webhook_data)
        except Exception as e:
            logger.error(f"Invalid webhook structure: {str(e)}")
            metrics.add_metric(name="webhook_invalid_structure", unit=MetricUnit.Count, value=1)
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid webhook structure'})
            }
        
        # Process webhook based on type
        if notification.type == "payment":
            success = process_payment_webhook(notification)
        else:
            logger.warning(f"Unsupported webhook type: {notification.type}")
            metrics.add_metric(name="webhook_unsupported_type", unit=MetricUnit.Count, value=1)
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Webhook type not supported'})
            }
        
        if success:
            metrics.add_metric(name="webhook_processed_success", unit=MetricUnit.Count, value=1)
            logger.info("Webhook processed successfully", extra={
                "webhook_id": str(notification.id),
                "webhook_type": notification.type,
                "action": notification.action
            })
            
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Webhook processed successfully'})
            }
        else:
            metrics.add_metric(name="webhook_processed_error", unit=MetricUnit.Count, value=1)
            logger.error("Failed to process webhook", extra={
                "webhook_id": str(notification.id),
                "webhook_type": notification.type,
                "action": notification.action
            })
            
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Failed to process webhook'})
            }
    
    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {str(e)}")
        metrics.add_metric(name="webhook_unexpected_error", unit=MetricUnit.Count, value=1)
        
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }


@tracer.capture_method
def process_payment_webhook(notification: WebhookNotification) -> bool:
    """
    Process payment webhook notification
    
    Args:
        notification: Validated webhook notification
        
    Returns:
        Processing success status
    """
    
    try:
        logger.info("Processing payment webhook", extra={
            "webhook_id": str(notification.id),
            "payment_id": notification.data.id,
            "action": notification.action
        })
        
        # Get MercadoPago client
        mp_client = get_mercadopago_client()
        
        # Process the webhook
        success = mp_client.process_webhook_notification(notification.dict())
        
        if success:
            logger.info("Payment webhook processed successfully", extra={
                "webhook_id": str(notification.id),
                "payment_id": notification.data.id
            })
        else:
            logger.error("Failed to process payment webhook", extra={
                "webhook_id": str(notification.id),
                "payment_id": notification.data.id
            })
        
        return success
        
    except PaymentError as e:
        logger.error(f"Payment error processing webhook: {str(e)}", extra={
            "webhook_id": str(notification.id),
            "payment_id": notification.data.id,
            "error_code": e.code
        })
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error processing payment webhook: {str(e)}", extra={
            "webhook_id": str(notification.id),
            "payment_id": notification.data.id
        })
        return False


@tracer.capture_method
def health_check() -> Dict[str, Any]:
    """
    Health check for webhook handler
    
    Returns:
        Health status
    """
    
    try:
        # Check if we can access settings
        _ = settings.mercadopago_access_token
        
        # Check if we can initialize MercadoPago client
        mp_client = get_mercadopago_client()
        
        return {
            'status': 'healthy',
            'service': 'mercadopago_webhook_handler',
            'version': settings.app_version,
            'timestamp': json.dumps({"default": None}, default=str)
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'service': 'mercadopago_webhook_handler'
        }


# Handler for health check endpoint
@tracer.capture_lambda_handler
@logger.inject_lambda_context
def health_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Health check Lambda handler
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        Health check response
    """
    
    health_status = health_check()
    status_code = 200 if health_status['status'] == 'healthy' else 503
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(health_status)
    }