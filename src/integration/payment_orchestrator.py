"""
Payment Orchestrator - Central integration layer
Coordinates payment flows between MercadoPago and Bird API
"""

import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from ..config.settings import get_settings, get_aws_resources
from ..config.logger import get_logger
from ..mercadopago.client import get_mercadopago_client
from ..mercadopago.models import (
    PaymentRequest, PaymentResponse, PaymentStatus, PaymentError,
    PaymentLinkMessage, PaymentConfirmationMessage, PaymentFailureMessage,
    format_colombian_currency, get_payment_status_message,
    is_payment_successful, is_payment_failed, is_payment_pending
)
from ..bird.client import get_bird_client
from ..bird.models import ConversationContext, BirdError
from .conversation_manager import get_conversation_manager
from .models import PaymentFlow, PaymentFlowStatus, IntegrationError

settings = get_settings()
aws_resources = get_aws_resources()
logger = get_logger()


class PaymentOrchestrator:
    """
    Central orchestrator for payment flows
    Manages the complete payment lifecycle between MercadoPago and Bird API
    """
    
    def __init__(self):
        self.mp_client = get_mercadopago_client()
        self.bird_client = get_bird_client()
        self.conversation_manager = get_conversation_manager()
    
    async def initiate_payment_flow(
        self,
        conversation_id: str,
        customer_phone: str,
        items: List[Dict[str, Any]],
        customer_info: Optional[Dict[str, Any]] = None
    ) -> PaymentFlow:
        """
        Initiate a complete payment flow
        
        Args:
            conversation_id: WhatsApp conversation ID
            customer_phone: Customer phone number
            items: List of items to purchase
            customer_info: Optional customer information
            
        Returns:
            PaymentFlow object with flow details
        """
        
        flow_id = f"flow_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{conversation_id}"
        
        try:
            logger.log_business_event(
                "payment_flow_initiated",
                customer_id=customer_phone,
                flow_id=flow_id,
                items_count=len(items)
            )
            
            # Create payment flow record
            payment_flow = PaymentFlow(
                flow_id=flow_id,
                conversation_id=conversation_id,
                customer_phone=customer_phone,
                items=items,
                customer_info=customer_info or {},
                status=PaymentFlowStatus.INITIATED,
                created_at=datetime.now(timezone.utc)
            )
            
            # Update conversation context
            await self.conversation_manager.update_conversation_state(
                conversation_id,
                "payment_requested",
                {"payment_flow_id": flow_id, "items": items}
            )
            
            # Create MercadoPago payment preference
            payment_request = self._build_payment_request(
                conversation_id, customer_phone, items, customer_info
            )
            
            payment_response = await self.mp_client.create_payment_preference(payment_request)
            
            # Update payment flow with MercadoPago data
            payment_flow.payment_id = payment_response.id
            payment_flow.transaction_id = payment_response.transaction_id
            payment_flow.checkout_url = payment_response.checkout_url
            payment_flow.expires_at = payment_response.expires_at
            payment_flow.status = PaymentFlowStatus.PREFERENCE_CREATED
            
            # Store payment flow
            await self._store_payment_flow(payment_flow)
            
            # Send payment link via WhatsApp
            success = await self._send_payment_link_message(payment_flow, payment_response)
            
            if success:
                payment_flow.status = PaymentFlowStatus.LINK_SENT
                await self._update_payment_flow_status(flow_id, PaymentFlowStatus.LINK_SENT)
                
                logger.log_business_event(
                    "payment_link_sent_successfully",
                    customer_id=customer_phone,
                    flow_id=flow_id,
                    payment_id=payment_response.id
                )
            else:
                payment_flow.status = PaymentFlowStatus.FAILED
                await self._update_payment_flow_status(flow_id, PaymentFlowStatus.FAILED)
                
                raise IntegrationError("Failed to send payment link via WhatsApp")
            
            return payment_flow
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "payment_orchestrator",
                "action": "initiate_payment_flow",
                "flow_id": flow_id,
                "customer_phone": customer_phone
            })
            
            # Update flow status to failed
            try:
                await self._update_payment_flow_status(flow_id, PaymentFlowStatus.FAILED)
            except:
                pass
            
            if isinstance(e, (PaymentError, BirdError, IntegrationError)):
                raise
            raise IntegrationError(f"Failed to initiate payment flow: {str(e)}")
    
    async def process_payment_status_update(
        self,
        payment_id: str,
        payment_status: str,
        payment_data: Dict[str, Any]
    ) -> bool:
        """
        Process payment status update from MercadoPago webhook
        
        Args:
            payment_id: MercadoPago payment ID
            payment_status: New payment status
            payment_data: Complete payment data
            
        Returns:
            Processing success status
        """
        
        try:
            logger.log_business_event(
                "payment_status_update_received",
                payment_id=payment_id,
                status=payment_status
            )
            
            # Get payment flow by payment ID
            payment_flow = await self._get_payment_flow_by_payment_id(payment_id)
            
            if not payment_flow:
                logger.warning(f"Payment flow not found for payment ID: {payment_id}")
                return True  # Don't fail webhook processing
            
            # Update payment flow status
            old_status = payment_flow.status
            payment_flow.payment_status = payment_status
            payment_flow.payment_data = payment_data
            payment_flow.updated_at = datetime.now(timezone.utc)
            
            # Determine new flow status
            if is_payment_successful(PaymentStatus(payment_status)):
                payment_flow.status = PaymentFlowStatus.PAYMENT_APPROVED
                await self._handle_payment_success(payment_flow, payment_data)
                
            elif is_payment_failed(PaymentStatus(payment_status)):
                payment_flow.status = PaymentFlowStatus.PAYMENT_FAILED
                await self._handle_payment_failure(payment_flow, payment_data)
                
            elif is_payment_pending(PaymentStatus(payment_status)):
                payment_flow.status = PaymentFlowStatus.PAYMENT_PENDING
                await self._handle_payment_pending(payment_flow, payment_data)
            
            # Update stored payment flow
            await self._update_payment_flow(payment_flow)
            
            logger.log_business_event(
                "payment_status_processed",
                payment_id=payment_id,
                old_status=old_status,
                new_status=payment_flow.status,
                flow_id=payment_flow.flow_id
            )
            
            return True
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "payment_orchestrator",
                "action": "process_payment_status_update",
                "payment_id": payment_id,
                "payment_status": payment_status
            })
            return False
    
    async def handle_conversation_message(
        self,
        conversation_id: str,
        message_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Handle incoming WhatsApp message and determine payment-related actions
        
        Args:
            conversation_id: WhatsApp conversation ID
            message_data: Message data from Bird webhook
            
        Returns:
            Response action if needed
        """
        
        try:
            message_text = message_data.get('content', {}).get('text', '').lower()
            sender_phone = message_data.get('sender', {}).get('identifier_value', '')
            
            logger.log_business_event(
                "conversation_message_received",
                customer_id=sender_phone,
                conversation_id=conversation_id,
                message_length=len(message_text)
            )
            
            # Get conversation context
            context = await self.conversation_manager.get_conversation_context(conversation_id)
            
            if not context:
                # Create new conversation context
                context = await self.conversation_manager.create_conversation_context(
                    conversation_id, sender_phone
                )
            
            # Check for payment-related intents
            if self._is_payment_intent(message_text):
                return await self._handle_payment_intent(context, message_text)
                
            elif self._is_cart_action(message_text):
                return await self._handle_cart_action(context, message_text)
                
            elif self._is_product_inquiry(message_text):
                return await self._handle_product_inquiry(context, message_text)
            
            # Update last activity
            await self.conversation_manager.update_last_activity(conversation_id)
            
            return None
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "payment_orchestrator",
                "action": "handle_conversation_message",
                "conversation_id": conversation_id
            })
            return None
    
    async def retry_failed_payment(
        self,
        flow_id: str,
        customer_phone: str
    ) -> bool:
        """
        Retry a failed payment flow
        
        Args:
            flow_id: Original payment flow ID
            customer_phone: Customer phone number
            
        Returns:
            Retry success status
        """
        
        try:
            # Get original payment flow
            payment_flow = await self._get_payment_flow(flow_id)
            
            if not payment_flow:
                logger.error(f"Payment flow not found for retry: {flow_id}")
                return False
            
            # Create new payment flow for retry
            retry_flow = await self.initiate_payment_flow(
                payment_flow.conversation_id,
                customer_phone,
                payment_flow.items,
                payment_flow.customer_info
            )
            
            # Link retry to original flow
            retry_flow.metadata["original_flow_id"] = flow_id
            retry_flow.metadata["retry_attempt"] = payment_flow.metadata.get("retry_attempt", 0) + 1
            
            await self._update_payment_flow(retry_flow)
            
            logger.log_business_event(
                "payment_retry_initiated",
                customer_id=customer_phone,
                original_flow_id=flow_id,
                retry_flow_id=retry_flow.flow_id
            )
            
            return True
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "payment_orchestrator",
                "action": "retry_failed_payment",
                "flow_id": flow_id,
                "customer_phone": customer_phone
            })
            return False
    
    async def cancel_payment_flow(
        self,
        flow_id: str,
        reason: str = "user_cancellation"
    ) -> bool:
        """
        Cancel an active payment flow
        
        Args:
            flow_id: Payment flow ID to cancel
            reason: Cancellation reason
            
        Returns:
            Cancellation success status
        """
        
        try:
            # Get payment flow
            payment_flow = await self._get_payment_flow(flow_id)
            
            if not payment_flow:
                logger.error(f"Payment flow not found for cancellation: {flow_id}")
                return False
            
            # Cancel MercadoPago preference if exists
            if payment_flow.payment_id:
                await self.mp_client.cancel_payment_preference(payment_flow.payment_id)
            
            # Update flow status
            payment_flow.status = PaymentFlowStatus.CANCELLED
            payment_flow.metadata["cancellation_reason"] = reason
            payment_flow.metadata["cancelled_at"] = datetime.now(timezone.utc).isoformat()
            
            await self._update_payment_flow(payment_flow)
            
            # Update conversation state
            await self.conversation_manager.update_conversation_state(
                payment_flow.conversation_id,
                "browsing",
                {"cancelled_flow_id": flow_id}
            )
            
            logger.log_business_event(
                "payment_flow_cancelled",
                flow_id=flow_id,
                reason=reason,
                customer_id=payment_flow.customer_phone
            )
            
            return True
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "service": "payment_orchestrator",
                "action": "cancel_payment_flow",
                "flow_id": flow_id
            })
            return False
    
    # Private helper methods
    
    def _build_payment_request(
        self,
        conversation_id: str,
        customer_phone: str,
        items: List[Dict[str, Any]],
        customer_info: Optional[Dict[str, Any]]
    ) -> PaymentRequest:
        """Build MercadoPago payment request"""
        
        from ..mercadopago.models import PaymentItem, Customer
        
        # Convert items
        payment_items = []
        for item in items:
            payment_items.append(PaymentItem(
                id=item["id"],
                title=item["title"],
                description=item.get("description"),
                quantity=item["quantity"],
                unit_price=Decimal(str(item["unit_price"]))
            ))
        
        # Build customer data
        customer_data = {
            "phone": customer_phone,
            "name": customer_info.get("name") if customer_info else None,
            "email": customer_info.get("email") if customer_info else None
        }
        
        customer = Customer(**customer_data)
        
        return PaymentRequest(
            items=payment_items,
            customer=customer,
            conversation_id=conversation_id,
            metadata={
                "source": "whatsapp_integration",
                "brand": settings.koaj_brand_name
            }
        )
    
    async def _send_payment_link_message(
        self,
        payment_flow: PaymentFlow,
        payment_response: PaymentResponse
    ) -> bool:
        """Send payment link message via WhatsApp"""
        
        from ..mercadopago.models import PaymentItem
        
        # Convert items for message
        message_items = []
        for item_data in payment_flow.items:
            message_items.append(PaymentItem(
                id=item_data["id"],
                title=item_data["title"],
                description=item_data.get("description"),
                quantity=item_data["quantity"],
                unit_price=Decimal(str(item_data["unit_price"]))
            ))
        
        # Create payment link message
        payment_message = PaymentLinkMessage(
            customer_name=payment_flow.customer_info.get("name"),
            payment_url=payment_response.checkout_url,
            total_amount=sum(Decimal(str(item["unit_price"])) * item["quantity"] for item in payment_flow.items),
            currency="COP",
            items=message_items,
            expires_at=payment_response.expires_at,
            brand_name=settings.koaj_brand_name
        )
        
        # Send via Bird API
        return await self.bird_client.send_payment_link_message(
            payment_flow.customer_phone,
            payment_message,
            payment_flow.conversation_id
        )
    
    async def _handle_payment_success(
        self,
        payment_flow: PaymentFlow,
        payment_data: Dict[str, Any]
    ) -> None:
        """Handle successful payment"""
        
        # Send confirmation message
        from ..mercadopago.models import PaymentItem
        
        message_items = []
        for item_data in payment_flow.items:
            message_items.append(PaymentItem(
                id=item_data["id"],
                title=item_data["title"],
                description=item_data.get("description"),
                quantity=item_data["quantity"],
                unit_price=Decimal(str(item_data["unit_price"]))
            ))
        
        confirmation_message = PaymentConfirmationMessage(
            customer_name=payment_flow.customer_info.get("name"),
            payment_id=payment_flow.payment_id,
            total_amount=sum(Decimal(str(item["unit_price"])) * item["quantity"] for item in payment_flow.items),
            currency="COP",
            items=message_items,
            approval_code=payment_data.get("authorization_code"),
            brand_name=settings.koaj_brand_name
        )
        
        await self.bird_client.send_payment_confirmation_message(
            payment_flow.customer_phone,
            confirmation_message,
            payment_flow.conversation_id
        )
        
        # Update conversation state
        await self.conversation_manager.update_conversation_state(
            payment_flow.conversation_id,
            "payment_completed",
            {"completed_flow_id": payment_flow.flow_id}
        )
        
        # Clear cart
        await self.conversation_manager.clear_cart(payment_flow.conversation_id)
    
    async def _handle_payment_failure(
        self,
        payment_flow: PaymentFlow,
        payment_data: Dict[str, Any]
    ) -> None:
        """Handle failed payment"""
        
        # Get failure reason
        status_detail = payment_data.get("status_detail", "")
        failure_reason = get_payment_status_message(
            PaymentStatus.REJECTED, 
            status_detail
        )
        
        # Send failure message with retry option
        failure_message = PaymentFailureMessage(
            customer_name=payment_flow.customer_info.get("name"),
            reason=failure_reason,
            retry_url=None,  # Could generate new link here
            support_phone=settings.koaj_support_phone,
            brand_name=settings.koaj_brand_name
        )
        
        await self.bird_client.send_payment_failure_message(
            payment_flow.customer_phone,
            failure_message,
            payment_flow.conversation_id
        )
        
        # Update conversation state
        await self.conversation_manager.update_conversation_state(
            payment_flow.conversation_id,
            "payment_failed",
            {"failed_flow_id": payment_flow.flow_id, "failure_reason": failure_reason}
        )
    
    async def _handle_payment_pending(
        self,
        payment_flow: PaymentFlow,
        payment_data: Dict[str, Any]
    ) -> None:
        """Handle pending payment"""
        
        # Send pending notification
        # Could use a simple text message for pending status
        # Implementation depends on business requirements
        
        # Update conversation state
        await self.conversation_manager.update_conversation_state(
            payment_flow.conversation_id,
            "payment_pending",
            {"pending_flow_id": payment_flow.flow_id}
        )
    
    def _is_payment_intent(self, message_text: str) -> bool:
        """Check if message indicates payment intent"""
        payment_keywords = [
            "pagar", "comprar", "precio", "costo", "checkout", "pago"
        ]
        return any(keyword in message_text for keyword in payment_keywords)
    
    def _is_cart_action(self, message_text: str) -> bool:
        """Check if message is a cart action"""
        cart_keywords = [
            "carrito", "agregar", "quitar", "vaciar", "eliminar"
        ]
        return any(keyword in message_text for keyword in cart_keywords)
    
    def _is_product_inquiry(self, message_text: str) -> bool:
        """Check if message is a product inquiry"""
        product_keywords = [
            "producto", "talla", "color", "disponible", "stock"
        ]
        return any(keyword in message_text for keyword in product_keywords)
    
    async def _handle_payment_intent(
        self,
        context: ConversationContext,
        message_text: str
    ) -> Optional[Dict[str, Any]]:
        """Handle payment intent from customer"""
        
        if not context.cart_items:
            return {
                "type": "text",
                "message": "Tu carrito está vacío. ¿Te gustaría ver nuestros productos?"
            }
        
        # Initiate payment flow
        try:
            payment_flow = await self.initiate_payment_flow(
                context.conversation_id,
                context.customer_phone,
                context.cart_items,
                context.customer_info
            )
            
            return {
                "type": "payment_initiated",
                "flow_id": payment_flow.flow_id
            }
            
        except Exception as e:
            logger.log_error_with_context(e, {
                "action": "handle_payment_intent",
                "conversation_id": context.conversation_id
            })
            
            return {
                "type": "text",
                "message": "Hubo un error al procesar tu pago. Por favor intenta de nuevo."
            }
    
    async def _handle_cart_action(
        self,
        context: ConversationContext,
        message_text: str
    ) -> Optional[Dict[str, Any]]:
        """Handle cart-related actions"""
        
        if "vaciar" in message_text or "eliminar" in message_text:
            await self.conversation_manager.clear_cart(context.conversation_id)
            return {
                "type": "text",
                "message": "Tu carrito ha sido vaciado."
            }
        
        # Other cart actions could be implemented here
        return None
    
    async def _handle_product_inquiry(
        self,
        context: ConversationContext,
        message_text: str
    ) -> Optional[Dict[str, Any]]:
        """Handle product inquiries"""
        
        # This would integrate with the existing KOAJ catalog system
        # For now, return a generic response
        return {
            "type": "text",
            "message": "¿En qué producto estás interesado? Puedo ayudarte con información sobre tallas, colores y disponibilidad."
        }
    
    # DynamoDB operations (to be implemented with conversation manager)
    
    async def _store_payment_flow(self, payment_flow: PaymentFlow) -> None:
        """Store payment flow in DynamoDB"""
        # Implementation will be in conversation_manager
        pass
    
    async def _update_payment_flow(self, payment_flow: PaymentFlow) -> None:
        """Update payment flow in DynamoDB"""
        # Implementation will be in conversation_manager
        pass
    
    async def _update_payment_flow_status(self, flow_id: str, status: PaymentFlowStatus) -> None:
        """Update payment flow status"""
        # Implementation will be in conversation_manager
        pass
    
    async def _get_payment_flow(self, flow_id: str) -> Optional[PaymentFlow]:
        """Get payment flow by ID"""
        # Implementation will be in conversation_manager
        pass
    
    async def _get_payment_flow_by_payment_id(self, payment_id: str) -> Optional[PaymentFlow]:
        """Get payment flow by MercadoPago payment ID"""
        # Implementation will be in conversation_manager
        pass


# Global orchestrator instance
_orchestrator_instance = None

def get_payment_orchestrator() -> PaymentOrchestrator:
    """Get payment orchestrator singleton"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = PaymentOrchestrator()
    return _orchestrator_instance