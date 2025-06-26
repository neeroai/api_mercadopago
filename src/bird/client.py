"""
Bird API Client for WhatsApp Business integration with payment support
Extended from existing KOAJ Bird integration with payment-specific features
"""

import json
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config.settings import get_settings, get_aws_resources
from ..config.logger import get_logger
from ..mercadopago.models import (
    PaymentLinkMessage, PaymentConfirmationMessage, PaymentFailureMessage,
    PaymentItem, format_colombian_currency
)
from .models import (
    BirdMessage, WhatsAppTemplate, BirdPaymentCatalog, 
    ConversationContext, BirdError
)

settings = get_settings()
aws_resources = get_aws_resources()
logger = get_logger()


class BirdAPIClient:
    """Enhanced Bird API client with payment integration support"""
    
    def __init__(self):
        self.api_key = settings.bird_api_key
        self.api_secret = settings.bird_api_secret
        self.base_url = settings.bird_base_url
        self.workspace_id = settings.bird_workspace_id
        self.channel_id = settings.bird_channel_id
        self.session = None
        self._access_token = None
        self._token_expires_at = None
        self._initialize_session()
    
    def _initialize_session(self):
        """Initialize HTTP session with retry strategy"""
        
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': f'{settings.koaj_brand_name}-Payment-Integration/{settings.app_version}'
        })
        
        logger.info("Bird API session initialized", service="bird_api")
    
    async def _authenticate(self) -> bool:
        """Authenticate with Bird API and get access token"""
        
        # Check if token is still valid
        if (self._access_token and self._token_expires_at and 
            datetime.now(timezone.utc) < self._token_expires_at):
            return True
        
        try:
            auth_endpoint = f"{self.base_url}/auth/token"
            auth_data = {
                "api_key": self.api_key,
                "api_secret": self.api_secret
            }
            
            start_time = time.time()
            response = self.session.post(auth_endpoint, json=auth_data)
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.log_api_call(
                "bird", "POST", "/auth/token",
                duration_ms, response.status_code
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self._access_token = token_data.get('access_token')
                
                # Calculate token expiration (assume 1 hour if not provided)
                expires_in = token_data.get('expires_in', 3600)
                self._token_expires_at = datetime.now(timezone.utc).timestamp() + expires_in
                
                # Update session headers
                self.session.headers.update({
                    'Authorization': f'Bearer {self._access_token}'
                })
                
                logger.info("Bird API authentication successful")
                return True
            else:
                logger.error(f"Bird API authentication failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "bird_api",
                "action": "authenticate"
            })
            return False
    
    async def send_payment_link_message(
        self, 
        phone_number: str, 
        payment_data: PaymentLinkMessage,
        conversation_id: Optional[str] = None
    ) -> bool:
        """
        Send payment link message via WhatsApp
        
        Args:
            phone_number: Customer phone number
            payment_data: Payment link message data
            conversation_id: Optional conversation ID for tracking
            
        Returns:
            Success status
        """
        
        try:
            # Ensure authentication
            if not await self._authenticate():
                raise BirdError("Failed to authenticate with Bird API")
            
            # Build WhatsApp message template
            template = self._build_payment_link_template(payment_data)
            
            # Send message
            success = await self._send_whatsapp_message(
                phone_number, template, conversation_id
            )
            
            if success:
                logger.log_business_event(
                    "payment_link_sent",
                    customer_id=phone_number,
                    payment_url=payment_data.payment_url,
                    total_amount=str(payment_data.total_amount)
                )
            
            return success
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "bird_api",
                "action": "send_payment_link",
                "phone_number": phone_number,
                "conversation_id": conversation_id
            })
            return False
    
    async def send_payment_confirmation_message(
        self,
        phone_number: str,
        payment_data: PaymentConfirmationMessage,
        conversation_id: Optional[str] = None
    ) -> bool:
        """
        Send payment confirmation message via WhatsApp
        
        Args:
            phone_number: Customer phone number
            payment_data: Payment confirmation data
            conversation_id: Optional conversation ID for tracking
            
        Returns:
            Success status
        """
        
        try:
            # Ensure authentication
            if not await self._authenticate():
                raise BirdError("Failed to authenticate with Bird API")
            
            # Build confirmation message template
            template = self._build_payment_confirmation_template(payment_data)
            
            # Send message
            success = await self._send_whatsapp_message(
                phone_number, template, conversation_id
            )
            
            if success:
                logger.log_business_event(
                    "payment_confirmation_sent",
                    customer_id=phone_number,
                    payment_id=payment_data.payment_id,
                    total_amount=str(payment_data.total_amount)
                )
            
            return success
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "bird_api",
                "action": "send_payment_confirmation",
                "phone_number": phone_number,
                "payment_id": payment_data.payment_id
            })
            return False
    
    async def send_payment_failure_message(
        self,
        phone_number: str,
        payment_data: PaymentFailureMessage,
        conversation_id: Optional[str] = None
    ) -> bool:
        """
        Send payment failure message via WhatsApp
        
        Args:
            phone_number: Customer phone number
            payment_data: Payment failure data
            conversation_id: Optional conversation ID for tracking
            
        Returns:
            Success status
        """
        
        try:
            # Ensure authentication
            if not await self._authenticate():
                raise BirdError("Failed to authenticate with Bird API")
            
            # Build failure message template
            template = self._build_payment_failure_template(payment_data)
            
            # Send message
            success = await self._send_whatsapp_message(
                phone_number, template, conversation_id
            )
            
            if success:
                logger.log_business_event(
                    "payment_failure_sent",
                    customer_id=phone_number,
                    reason=payment_data.reason
                )
            
            return success
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "bird_api",
                "action": "send_payment_failure",
                "phone_number": phone_number,
                "reason": payment_data.reason
            })
            return False
    
    async def update_conversation_context(
        self,
        conversation_id: str,
        context_data: Dict[str, Any]
    ) -> bool:
        """
        Update conversation context in Bird platform
        
        Args:
            conversation_id: Conversation ID
            context_data: Context data to update
            
        Returns:
            Success status
        """
        
        try:
            if not await self._authenticate():
                raise BirdError("Failed to authenticate with Bird API")
            
            context_endpoint = f"{self.base_url}/conversations/{conversation_id}/context"
            
            start_time = time.time()
            response = self.session.put(context_endpoint, json=context_data)
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.log_api_call(
                "bird", "PUT", f"/conversations/{conversation_id}/context",
                duration_ms, response.status_code
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Conversation context updated: {conversation_id}")
                return True
            else:
                logger.error(f"Failed to update conversation context: {response.status_code}")
                return False
                
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "bird_api",
                "action": "update_conversation_context",
                "conversation_id": conversation_id
            })
            return False
    
    async def _send_whatsapp_message(
        self,
        phone_number: str,
        template: WhatsAppTemplate,
        conversation_id: Optional[str] = None
    ) -> bool:
        """
        Send WhatsApp message using Bird API
        
        Args:
            phone_number: Target phone number
            template: Message template
            conversation_id: Optional conversation ID
            
        Returns:
            Success status
        """
        
        try:
            message_endpoint = f"{self.base_url}/channels/{self.channel_id}/messages"
            
            message_data = {
                "receiver": {
                    "contacts": [{"identifierValue": phone_number}]
                },
                "template": template.dict(),
                "metadata": {
                    "source": "koaj_payment_integration",
                    "conversation_id": conversation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
            
            start_time = time.time()
            response = self.session.post(message_endpoint, json=message_data)
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.log_api_call(
                "bird", "POST", f"/channels/{self.channel_id}/messages",
                duration_ms, response.status_code,
                phone_number=phone_number,
                template_type=template.type
            )
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                message_id = response_data.get('id')
                
                logger.info(
                    "WhatsApp message sent successfully",
                    message_id=message_id,
                    phone_number=phone_number,
                    template_type=template.type
                )
                return True
            else:
                logger.error(
                    f"Failed to send WhatsApp message: {response.status_code}",
                    phone_number=phone_number,
                    response_text=response.text
                )
                return False
                
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "bird_api",
                "action": "send_whatsapp_message",
                "phone_number": phone_number,
                "template_type": template.type
            })
            return False
    
    def _build_payment_link_template(self, payment_data: PaymentLinkMessage) -> WhatsAppTemplate:
        """Build payment link WhatsApp template"""
        
        # Format items for display
        items_text = self._format_items_for_message(payment_data.items)
        total_formatted = format_colombian_currency(payment_data.total_amount)
        
        message_text = f"""🛍️ *{payment_data.brand_name}* - Completa tu compra

¡Hola {payment_data.customer_name or 'estimado cliente'}! 👋

Tienes los siguientes productos reservados:

{items_text}

💰 *Total: {total_formatted}*

Para completar tu compra, haz clic en el siguiente enlace:
{payment_data.payment_url}

⏰ Este enlace expira el {self._format_expiration_date(payment_data.expires_at)}

¿Necesitas ayuda? Escríbenos, estamos aquí para apoyarte 💬

_{payment_data.brand_name} - Moda que inspira_ ✨"""
        
        return WhatsAppTemplate(
            type="payment_link",
            text=message_text,
            buttons=[
                {
                    "type": "url",
                    "title": "💳 Pagar Ahora",
                    "url": payment_data.payment_url
                }
            ]
        )
    
    def _build_payment_confirmation_template(self, payment_data: PaymentConfirmationMessage) -> WhatsAppTemplate:
        """Build payment confirmation WhatsApp template"""
        
        items_text = self._format_items_for_message(payment_data.items)
        total_formatted = format_colombian_currency(payment_data.total_amount)
        
        message_text = f"""✅ *¡Pago Confirmado!* - {payment_data.brand_name}

¡Hola {payment_data.customer_name or 'estimado cliente'}! 🎉

Tu pago ha sido procesado exitosamente:

📋 *Detalles de la compra:*
{items_text}

💰 *Total pagado: {total_formatted}*
🆔 *ID de pago: {payment_data.payment_id}*"""

        if payment_data.approval_code:
            message_text += f"\n✅ *Código de aprobación: {payment_data.approval_code}*"

        message_text += f"""

📦 *¿Qué sigue?*
• Recibirás un email con los detalles de tu compra
• Tu pedido será procesado en las próximas 24 horas
• Te notificaremos cuando esté listo para envío

¡Gracias por confiar en {payment_data.brand_name}! 💙

_¿Tienes alguna pregunta? Estamos aquí para ayudarte_ 💬"""
        
        return WhatsAppTemplate(
            type="payment_confirmation",
            text=message_text
        )
    
    def _build_payment_failure_template(self, payment_data: PaymentFailureMessage) -> WhatsAppTemplate:
        """Build payment failure WhatsApp template"""
        
        message_text = f"""❌ *Problema con el Pago* - {payment_data.brand_name}

Hola {payment_data.customer_name or 'estimado cliente'} 😔

Hubo un problema procesando tu pago:

⚠️ *Motivo:* {payment_data.reason}

🔄 *¿Qué puedes hacer?*
• Verifica los datos de tu tarjeta
• Intenta con otro método de pago
• Contacta a tu banco si es necesario"""
        
        buttons = []
        
        if payment_data.retry_url:
            message_text += f"\n\n💳 Puedes intentar nuevamente con el enlace:"
            buttons.append({
                "type": "url", 
                "title": "🔄 Intentar de nuevo",
                "url": payment_data.retry_url
            })
        
        message_text += f"""

📞 *¿Necesitas ayuda?*
Contáctanos: {payment_data.support_phone}

¡No te preocupes, estamos aquí para apoyarte! 💪

_{payment_data.brand_name} - Moda que inspira_ ✨"""
        
        return WhatsAppTemplate(
            type="payment_failure",
            text=message_text,
            buttons=buttons
        )
    
    def _format_items_for_message(self, items: List[PaymentItem]) -> str:
        """Format items list for WhatsApp message"""
        
        items_text = ""
        for item in items:
            price_formatted = format_colombian_currency(item.unit_price)
            total_item = format_colombian_currency(item.unit_price * item.quantity)
            
            items_text += f"• {item.title}\n"
            items_text += f"  Cantidad: {item.quantity} x {price_formatted} = {total_item}\n\n"
        
        return items_text.strip()
    
    def _format_expiration_date(self, expires_at: datetime) -> str:
        """Format expiration date for Colombian locale"""
        
        # Convert to Colombian timezone if needed
        colombia_tz = expires_at.astimezone()
        
        months = [
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
        ]
        
        day = colombia_tz.day
        month = months[colombia_tz.month - 1]
        year = colombia_tz.year
        hour = colombia_tz.hour
        minute = colombia_tz.minute
        
        return f"{day} de {month} de {year} a las {hour:02d}:{minute:02d}"
    
    async def get_conversation_history(
        self,
        conversation_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get conversation message history
        
        Args:
            conversation_id: Conversation ID
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of conversation messages
        """
        
        try:
            if not await self._authenticate():
                raise BirdError("Failed to authenticate with Bird API")
            
            history_endpoint = f"{self.base_url}/conversations/{conversation_id}/messages"
            params = {"limit": limit}
            
            start_time = time.time()
            response = self.session.get(history_endpoint, params=params)
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.log_api_call(
                "bird", "GET", f"/conversations/{conversation_id}/messages",
                duration_ms, response.status_code
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('messages', [])
            else:
                logger.error(f"Failed to get conversation history: {response.status_code}")
                return []
                
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "bird_api",
                "action": "get_conversation_history",
                "conversation_id": conversation_id
            })
            return []


# Global client instance
_bird_client_instance = None

def get_bird_client() -> BirdAPIClient:
    """Get Bird API client singleton"""
    global _bird_client_instance
    if _bird_client_instance is None:
        _bird_client_instance = BirdAPIClient()
    return _bird_client_instance