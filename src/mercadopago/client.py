"""
MercadoPago API Client for Python/AWS integration
Handles payment preferences, webhooks, and payment processing
"""

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import mercadopago
import requests
from botocore.exceptions import ClientError

from ..config.settings import get_settings, get_aws_resources
from ..config.logger import get_logger
from .models import (
    PaymentRequest, PaymentResponse, PaymentStatus, PaymentError,
    WebhookNotification, PaymentPreference
)

settings = get_settings()
aws_resources = get_aws_resources()
logger = get_logger()


class MercadoPagoClient:
    """MercadoPago API client with AWS integration"""
    
    def __init__(self):
        self.sdk = None
        self.access_token = settings.mercadopago_access_token
        self.base_url = settings.mercadopago_base_url
        self.sandbox = settings.mercadopago_sandbox
        self._initialize_sdk()
    
    def _initialize_sdk(self):
        """Initialize MercadoPago SDK"""
        try:
            self.sdk = mercadopago.SDK(self.access_token)
            
            # Configure SDK for sandbox if needed
            if self.sandbox:
                self.sdk.sandbox_mode(True)
            
            logger.info(
                "MercadoPago SDK initialized",
                sandbox=self.sandbox,
                service="mercadopago"
            )
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "mercadopago",
                "action": "sdk_initialization"
            })
            raise PaymentError(f"Failed to initialize MercadoPago SDK: {str(e)}")
    
    async def create_payment_preference(self, payment_request: PaymentRequest) -> PaymentResponse:
        """
        Create payment preference for WhatsApp integration
        
        Args:
            payment_request: Payment request data
            
        Returns:
            PaymentResponse with checkout URL and metadata
        """
        start_time = time.time()
        transaction_id = str(uuid.uuid4())
        
        try:
            logger.log_payment_event(
                "preference_creation_started",
                transaction_id,
                customer_phone=payment_request.customer.phone,
                item_count=len(payment_request.items)
            )
            
            # Build preference data
            preference_data = self._build_preference_data(payment_request, transaction_id)
            
            # Create preference using SDK
            preference_response = self.sdk.preference().create(preference_data)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            if preference_response["status"] == 201:
                preference = preference_response["response"]
                
                logger.log_api_call(
                    "mercadopago", "POST", "/checkout/preferences",
                    duration_ms, 201,
                    preference_id=preference["id"],
                    transaction_id=transaction_id
                )
                
                # Store payment data in DynamoDB
                await self._store_payment_data(preference, payment_request, transaction_id)
                
                # Create response
                payment_response = PaymentResponse(
                    id=preference["id"],
                    checkout_url=preference["sandbox_init_point"] if self.sandbox else preference["init_point"],
                    qr_code=preference.get("qr_code"),
                    transaction_id=transaction_id,
                    expires_at=self._calculate_expiration_date(),
                    metadata={
                        "conversation_id": payment_request.conversation_id,
                        "customer_phone": payment_request.customer.phone,
                        "total_amount": self._calculate_total_amount(payment_request.items),
                        "currency": "COP"
                    }
                )
                
                logger.log_payment_event(
                    "preference_created",
                    transaction_id,
                    preference_id=preference["id"],
                    checkout_url=payment_response.checkout_url
                )
                
                return payment_response
                
            else:
                error_msg = f"MercadoPago API error: {preference_response.get('message', 'Unknown error')}"
                logger.error(error_msg, 
                           transaction_id=transaction_id,
                           api_response=preference_response)
                raise PaymentError(error_msg)
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.log_api_call(
                "mercadopago", "POST", "/checkout/preferences",
                duration_ms, 500,
                error=str(e),
                transaction_id=transaction_id
            )
            
            logger.log_error_with_context(e, {
                "service": "mercadopago",
                "action": "create_preference",
                "transaction_id": transaction_id,
                "payment_request": payment_request.dict()
            })
            
            if isinstance(e, PaymentError):
                raise
            raise PaymentError(f"Failed to create payment preference: {str(e)}")
    
    async def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """
        Get payment details by ID
        
        Args:
            payment_id: MercadoPago payment ID
            
        Returns:
            Payment details
        """
        start_time = time.time()
        
        try:
            payment_response = self.sdk.payment().get(payment_id)
            duration_ms = int((time.time() - start_time) * 1000)
            
            if payment_response["status"] == 200:
                payment = payment_response["response"]
                
                logger.log_api_call(
                    "mercadopago", "GET", f"/payments/{payment_id}",
                    duration_ms, 200,
                    payment_id=payment_id,
                    status=payment["status"]
                )
                
                return self._format_payment_response(payment)
                
            else:
                error_msg = f"Payment not found: {payment_id}"
                logger.error(error_msg, payment_id=payment_id)
                raise PaymentError(error_msg, status_code=404)
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.log_api_call(
                "mercadopago", "GET", f"/payments/{payment_id}",
                duration_ms, 500,
                error=str(e),
                payment_id=payment_id
            )
            
            logger.log_error_with_context(e, {
                "service": "mercadopago",
                "action": "get_payment",
                "payment_id": payment_id
            })
            
            if isinstance(e, PaymentError):
                raise
            raise PaymentError(f"Failed to get payment: {str(e)}")
    
    async def cancel_payment_preference(self, preference_id: str) -> bool:
        """
        Cancel payment preference by expiring it
        
        Args:
            preference_id: Payment preference ID
            
        Returns:
            Success status
        """
        start_time = time.time()
        
        try:
            # Update preference to expire immediately
            update_data = {
                "expires": True,
                "expiration_date_to": datetime.now(timezone.utc).isoformat()
            }
            
            update_response = self.sdk.preference().update(preference_id, update_data)
            duration_ms = int((time.time() - start_time) * 1000)
            
            if update_response["status"] == 200:
                logger.log_api_call(
                    "mercadopago", "PUT", f"/checkout/preferences/{preference_id}",
                    duration_ms, 200,
                    preference_id=preference_id,
                    action="cancel"
                )
                
                logger.log_payment_event("preference_cancelled", preference_id)
                
                # Update DynamoDB record
                await self._update_payment_status(preference_id, PaymentStatus.CANCELLED)
                
                return True
                
            else:
                logger.error(
                    "Failed to cancel preference",
                    preference_id=preference_id,
                    api_response=update_response
                )
                return False
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.log_api_call(
                "mercadopago", "PUT", f"/checkout/preferences/{preference_id}",
                duration_ms, 500,
                error=str(e),
                preference_id=preference_id
            )
            
            logger.log_error_with_context(e, {
                "service": "mercadopago",
                "action": "cancel_preference",
                "preference_id": preference_id
            })
            
            return False
    
    async def process_webhook_notification(self, webhook_data: Dict[str, Any]) -> bool:
        """
        Process webhook notification from MercadoPago
        
        Args:
            webhook_data: Webhook notification data
            
        Returns:
            Processing success status
        """
        try:
            # Validate webhook data
            notification = WebhookNotification(**webhook_data)
            
            logger.log_webhook_event(
                "mercadopago",
                notification.action,
                webhook_id=str(notification.id),
                data_id=notification.data.id
            )
            
            # Process based on notification type
            if notification.type == "payment":
                return await self._process_payment_webhook(notification)
            else:
                logger.warning(
                    f"Unhandled webhook type: {notification.type}",
                    webhook_id=str(notification.id)
                )
                return True
                
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "mercadopago",
                "action": "process_webhook",
                "webhook_data": webhook_data
            })
            return False
    
    def _build_preference_data(self, payment_request: PaymentRequest, transaction_id: str) -> Dict[str, Any]:
        """Build MercadoPago preference data"""
        
        # Format items
        items = []
        for item in payment_request.items:
            items.append({
                "id": item.id,
                "title": item.title,
                "description": item.description or "",
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "currency_id": "COP"
            })
        
        # Format payer
        payer = {
            "name": payment_request.customer.name or "",
            "surname": payment_request.customer.surname or "",
            "email": payment_request.customer.email or f"{payment_request.customer.phone}@temp.koaj.co",
            "phone": {
                "area_code": self._extract_area_code(payment_request.customer.phone),
                "number": self._extract_phone_number(payment_request.customer.phone)
            }
        }
        
        if payment_request.customer.identification_type and payment_request.customer.identification_number:
            payer["identification"] = {
                "type": payment_request.customer.identification_type,
                "number": payment_request.customer.identification_number
            }
        
        # Build preference
        preference_data = {
            "items": items,
            "payer": payer,
            "payment_methods": {
                "excluded_payment_methods": [],
                "excluded_payment_types": [],
                "installments": 12,
                "default_installments": 1
            },
            "back_urls": self._get_back_urls(payment_request.conversation_id),
            "notification_url": settings.webhook_endpoints.get("mercadopago"),
            "external_reference": transaction_id,
            "expires": True,
            "expiration_date_from": datetime.now(timezone.utc).isoformat(),
            "expiration_date_to": self._calculate_expiration_date().isoformat(),
            "auto_return": "approved",
            "metadata": {
                "conversation_id": payment_request.conversation_id,
                "customer_phone": payment_request.customer.phone,
                "source": "whatsapp_integration",
                "koaj_brand": settings.koaj_brand_name,
                "integration_version": settings.app_version
            }
        }
        
        return preference_data
    
    def _get_back_urls(self, conversation_id: str) -> Dict[str, str]:
        """Get back URLs for payment flow"""
        base_url = settings.webhook_base_url or settings.api_gateway_base_url
        
        if not base_url:
            # Fallback URLs
            base_url = "https://api.koaj.co"
        
        return {
            "success": f"{base_url}/payment/success?conversation={conversation_id}",
            "failure": f"{base_url}/payment/failure?conversation={conversation_id}",
            "pending": f"{base_url}/payment/pending?conversation={conversation_id}"
        }
    
    def _calculate_expiration_date(self) -> datetime:
        """Calculate payment expiration date"""
        return datetime.now(timezone.utc) + timedelta(minutes=settings.payment_expiration_minutes)
    
    def _calculate_total_amount(self, items: List[Any]) -> float:
        """Calculate total amount from items"""
        return sum(item.unit_price * item.quantity for item in items)
    
    def _extract_area_code(self, phone: str) -> str:
        """Extract area code from Colombian phone number"""
        if not phone:
            return ""
        
        clean_phone = ''.join(filter(str.isdigit, phone))
        if clean_phone.startswith('57') and len(clean_phone) == 12:
            return "57"
        return ""
    
    def _extract_phone_number(self, phone: str) -> str:
        """Extract phone number without area code"""
        if not phone:
            return ""
        
        clean_phone = ''.join(filter(str.isdigit, phone))
        if clean_phone.startswith('57') and len(clean_phone) == 12:
            return clean_phone[2:]
        return clean_phone
    
    def _format_payment_response(self, payment: Dict[str, Any]) -> Dict[str, Any]:
        """Format payment response for consistent API"""
        return {
            "id": payment["id"],
            "status": payment["status"],
            "status_detail": payment["status_detail"],
            "transaction_amount": payment["transaction_amount"],
            "currency": payment["currency_id"],
            "date_created": payment["date_created"],
            "date_approved": payment.get("date_approved"),
            "payment_method_id": payment.get("payment_method_id"),
            "payment_type_id": payment.get("payment_type_id"),
            "external_reference": payment.get("external_reference"),
            "payer": {
                "id": payment.get("payer", {}).get("id"),
                "email": payment.get("payer", {}).get("email"),
                "phone": payment.get("payer", {}).get("phone")
            },
            "metadata": payment.get("metadata", {})
        }
    
    async def _store_payment_data(self, preference: Dict[str, Any], 
                                 payment_request: PaymentRequest, transaction_id: str):
        """Store payment data in DynamoDB"""
        try:
            table = aws_resources.dynamodb.Table(settings.payments_table_name)
            
            item = {
                "payment_id": preference["id"],
                "transaction_id": transaction_id,
                "conversation_id": payment_request.conversation_id,
                "customer_phone": payment_request.customer.phone,
                "status": PaymentStatus.PENDING,
                "total_amount": self._calculate_total_amount(payment_request.items),
                "currency": "COP",
                "items": [item.dict() for item in payment_request.items],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": self._calculate_expiration_date().isoformat(),
                "checkout_url": preference["sandbox_init_point"] if self.sandbox else preference["init_point"],
                "metadata": {
                    "source": "whatsapp_integration",
                    "koaj_brand": settings.koaj_brand_name
                }
            }
            
            table.put_item(Item=item)
            
            logger.log_dynamodb_operation(
                "put_item", settings.payments_table_name,
                item_key=preference["id"]
            )
            
        except ClientError as e:
            logger.log_error_with_context(e, {
                "service": "dynamodb",
                "action": "store_payment_data",
                "table": settings.payments_table_name,
                "payment_id": preference["id"]
            })
            # Don't fail the payment creation if storage fails
    
    async def _update_payment_status(self, payment_id: str, status: str):
        """Update payment status in DynamoDB"""
        try:
            table = aws_resources.dynamodb.Table(settings.payments_table_name)
            
            table.update_item(
                Key={"payment_id": payment_id},
                UpdateExpression="SET #status = :status, updated_at = :updated_at",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": status,
                    ":updated_at": datetime.now(timezone.utc).isoformat()
                }
            )
            
            logger.log_dynamodb_operation(
                "update_item", settings.payments_table_name,
                item_key=payment_id,
                status=status
            )
            
        except ClientError as e:
            logger.log_error_with_context(e, {
                "service": "dynamodb",
                "action": "update_payment_status",
                "table": settings.payments_table_name,
                "payment_id": payment_id,
                "status": status
            })
    
    async def _process_payment_webhook(self, notification: WebhookNotification) -> bool:
        """Process payment webhook notification"""
        try:
            # Get payment details
            payment_data = await self.get_payment(notification.data.id)
            
            # Update payment status in DynamoDB
            await self._update_payment_status(notification.data.id, payment_data["status"])
            
            # Send SQS message for further processing
            await self._send_payment_event(notification.data.id, payment_data)
            
            logger.log_payment_event(
                f"payment_{payment_data['status']}",
                notification.data.id,
                webhook_id=str(notification.id),
                status=payment_data["status"]
            )
            
            return True
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "mercadopago",
                "action": "process_payment_webhook",
                "webhook_id": str(notification.id),
                "payment_id": notification.data.id
            })
            return False
    
    async def _send_payment_event(self, payment_id: str, payment_data: Dict[str, Any]):
        """Send payment event to SQS for processing"""
        try:
            queue_url = aws_resources.get_queue_url(settings.payment_events_queue)
            
            message = {
                "event_type": "payment_status_changed",
                "payment_id": payment_id,
                "status": payment_data["status"],
                "payment_data": payment_data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            aws_resources.sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    "event_type": {
                        "StringValue": "payment_status_changed",
                        "DataType": "String"
                    },
                    "payment_id": {
                        "StringValue": payment_id,
                        "DataType": "String"
                    }
                }
            )
            
            logger.log_sqs_message(
                settings.payment_events_queue,
                payment_id,
                "sent"
            )
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "sqs",
                "action": "send_payment_event",
                "queue": settings.payment_events_queue,
                "payment_id": payment_id
            })


# Global client instance
_client_instance = None

def get_mercadopago_client() -> MercadoPagoClient:
    """Get MercadoPago client singleton"""
    global _client_instance
    if _client_instance is None:
        _client_instance = MercadoPagoClient()
    return _client_instance