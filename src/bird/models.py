"""
Data models for Bird API integration
WhatsApp Business and conversation management models
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union

from pydantic import BaseModel, Field, validator


class MessageType(str, Enum):
    """WhatsApp message types"""
    TEXT = "text"
    TEMPLATE = "template"
    INTERACTIVE = "interactive"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    LOCATION = "location"
    CONTACT = "contact"


class TemplateType(str, Enum):
    """WhatsApp template types"""
    PAYMENT_LINK = "payment_link"
    PAYMENT_CONFIRMATION = "payment_confirmation"
    PAYMENT_FAILURE = "payment_failure"
    ORDER_UPDATE = "order_update"
    PRODUCT_CATALOG = "product_catalog"


class ConversationStatus(str, Enum):
    """Conversation status in Bird platform"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    BLOCKED = "blocked"


class MessageDirection(str, Enum):
    """Message direction"""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


# Bird API Models

class BirdContact(BaseModel):
    """Bird contact model"""
    identifier_value: str = Field(..., description="Phone number or identifier")
    identifier_type: str = Field(default="phone_number", description="Identifier type")
    display_name: Optional[str] = Field(None, description="Contact display name")
    
    @validator('identifier_value')
    def validate_phone_number(cls, v):
        # Basic phone number validation for Colombian numbers
        if v.startswith('+'):
            v = v[1:]
        
        # Should be digits only after cleaning
        clean_number = ''.join(filter(str.isdigit, v))
        if not clean_number:
            raise ValueError('Invalid phone number format')
        
        return clean_number


class BirdButton(BaseModel):
    """WhatsApp button model"""
    type: str = Field(..., description="Button type (url, call, quick_reply)")
    title: str = Field(..., max_length=20, description="Button title")
    url: Optional[str] = Field(None, description="URL for url type buttons")
    phone_number: Optional[str] = Field(None, description="Phone for call type buttons")
    payload: Optional[str] = Field(None, description="Payload for quick_reply buttons")


class WhatsAppTemplate(BaseModel):
    """WhatsApp message template"""
    type: str = Field(default="text", description="Template type")
    text: str = Field(..., max_length=4096, description="Message text")
    buttons: Optional[List[BirdButton]] = Field(None, description="Message buttons")
    header: Optional[Dict[str, Any]] = Field(None, description="Message header")
    footer: Optional[str] = Field(None, max_length=60, description="Message footer")
    
    @validator('text')
    def validate_text_length(cls, v):
        if len(v) > 4096:
            raise ValueError('Message text cannot exceed 4096 characters')
        return v


class BirdMessage(BaseModel):
    """Bird API message model"""
    id: Optional[str] = Field(None, description="Message ID")
    conversation_id: str = Field(..., description="Conversation ID")
    direction: MessageDirection = Field(..., description="Message direction")
    type: MessageType = Field(..., description="Message type")
    content: Dict[str, Any] = Field(..., description="Message content")
    sender: Optional[BirdContact] = Field(None, description="Message sender")
    receiver: Optional[BirdContact] = Field(None, description="Message receiver")
    timestamp: datetime = Field(default_factory=datetime.now, description="Message timestamp")
    status: Optional[str] = Field(None, description="Message status")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Message metadata")


class ConversationContext(BaseModel):
    """Conversation context for payment tracking"""
    conversation_id: str = Field(..., description="Conversation ID")
    customer_phone: str = Field(..., description="Customer phone number")
    current_state: str = Field(default="browsing", description="Current conversation state")
    payment_data: Optional[Dict[str, Any]] = Field(None, description="Active payment data")
    cart_items: List[Dict[str, Any]] = Field(default_factory=list, description="Cart items")
    customer_info: Optional[Dict[str, Any]] = Field(None, description="Customer information")
    last_activity: datetime = Field(default_factory=datetime.now, description="Last activity timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")
    
    def add_cart_item(self, item: Dict[str, Any]):
        """Add item to cart"""
        self.cart_items.append({
            **item,
            "added_at": datetime.now().isoformat()
        })
        self.last_activity = datetime.now()
    
    def remove_cart_item(self, item_id: str):
        """Remove item from cart"""
        self.cart_items = [item for item in self.cart_items if item.get('id') != item_id]
        self.last_activity = datetime.now()
    
    def clear_cart(self):
        """Clear all cart items"""
        self.cart_items = []
        self.last_activity = datetime.now()
    
    def set_state(self, state: str):
        """Update conversation state"""
        self.current_state = state
        self.last_activity = datetime.now()
    
    def set_payment_data(self, payment_data: Dict[str, Any]):
        """Set active payment data"""
        self.payment_data = payment_data
        self.last_activity = datetime.now()


class BirdWebhook(BaseModel):
    """Bird webhook notification model"""
    id: str = Field(..., description="Webhook ID")
    type: str = Field(..., description="Webhook type")
    timestamp: datetime = Field(..., description="Webhook timestamp")
    data: Dict[str, Any] = Field(..., description="Webhook data")
    conversation_id: Optional[str] = Field(None, description="Associated conversation ID")
    
    @validator('type')
    def validate_webhook_type(cls, v):
        valid_types = [
            'message.received', 'message.sent', 'message.delivered', 
            'message.read', 'conversation.created', 'conversation.updated'
        ]
        if v not in valid_types:
            raise ValueError(f'Invalid webhook type: {v}')
        return v


class BirdCatalogItem(BaseModel):
    """Bird catalog item for WhatsApp Business"""
    external_product_id: str = Field(..., description="External product ID")
    external_catalog_id: str = Field(..., description="External catalog ID")
    title: str = Field(..., max_length=256, description="Product title")
    description: Optional[str] = Field(None, max_length=600, description="Product description")
    price: Dict[str, Union[int, str]] = Field(..., description="Product price")
    image_url: Optional[str] = Field(None, description="Product image URL")
    category: Optional[str] = Field(None, description="Product category")
    availability: str = Field(default="in_stock", description="Product availability")
    brand: Optional[str] = Field(None, description="Product brand")
    color: Optional[str] = Field(None, description="Product color")
    material: Optional[str] = Field(None, description="Product material")
    size: Optional[str] = Field(None, description="Product size")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class BirdPaymentCatalog(BaseModel):
    """Bird payment catalog for WhatsApp Commerce"""
    external_catalog_id: str = Field(..., description="Catalog ID")
    name: str = Field(..., description="Catalog name")
    description: Optional[str] = Field(None, description="Catalog description")
    currency: str = Field(default="COP", description="Catalog currency")
    locale: str = Field(default="es-CO", description="Catalog locale")
    items: List[BirdCatalogItem] = Field(default_factory=list, description="Catalog items")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Catalog metadata")


class WhatsAppInteractiveMessage(BaseModel):
    """WhatsApp interactive message model"""
    type: str = Field(..., description="Interactive type (button, list, product)")
    header: Optional[Dict[str, Any]] = Field(None, description="Message header")
    body: str = Field(..., description="Message body")
    footer: Optional[str] = Field(None, description="Message footer")
    action: Dict[str, Any] = Field(..., description="Interactive action")


class ProductMessage(WhatsAppInteractiveMessage):
    """Product-specific WhatsApp message"""
    type: str = Field(default="product", description="Product message type")
    product: BirdCatalogItem = Field(..., description="Product information")
    
    def __init__(self, product: BirdCatalogItem, **kwargs):
        super().__init__(
            type="product",
            body=f"🛍️ {product.title}\n\n{product.description or ''}\n\n💰 {self._format_price(product.price)}",
            action={
                "catalog_id": product.external_catalog_id,
                "product_retailer_id": product.external_product_id
            },
            **kwargs
        )
        self.product = product
    
    def _format_price(self, price: Dict[str, Union[int, str]]) -> str:
        """Format price for display"""
        amount = price.get('amount', 0)
        currency = price.get('currency_code', 'COP')
        
        if isinstance(amount, int):
            # Assume amount is in cents
            formatted_amount = amount / 100
        else:
            formatted_amount = float(amount)
        
        return f"${formatted_amount:,.0f} {currency}"


class CartSummaryMessage(WhatsAppInteractiveMessage):
    """Cart summary interactive message"""
    type: str = Field(default="button", description="Button message type")
    cart_items: List[Dict[str, Any]] = Field(..., description="Cart items")
    total_amount: float = Field(..., description="Cart total amount")
    
    def __init__(self, cart_items: List[Dict[str, Any]], total_amount: float, **kwargs):
        # Build cart summary text
        items_text = ""
        for item in cart_items:
            items_text += f"• {item.get('title', 'Producto')}\n"
            items_text += f"  Cantidad: {item.get('quantity', 1)} x ${item.get('unit_price', 0):,.0f}\n\n"
        
        body_text = f"🛒 *Resumen de tu carrito:*\n\n{items_text}💰 *Total: ${total_amount:,.0f} COP*"
        
        super().__init__(
            type="button",
            body=body_text,
            action={
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "proceed_payment",
                            "title": "💳 Pagar"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "edit_cart",
                            "title": "✏️ Editar"
                        }
                    },
                    {
                        "type": "reply", 
                        "reply": {
                            "id": "clear_cart",
                            "title": "🗑️ Vaciar"
                        }
                    }
                ]
            },
            **kwargs
        )
        self.cart_items = cart_items
        self.total_amount = total_amount


# Error Models

class BirdError(Exception):
    """Bird API error class"""
    
    def __init__(self, message: str, code: str = "BIRD_API_ERROR", 
                 status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class BirdAuthenticationError(BirdError):
    """Bird API authentication error"""
    
    def __init__(self, message: str = "Failed to authenticate with Bird API"):
        super().__init__(message, "BIRD_AUTH_ERROR", 401)


class BirdRateLimitError(BirdError):
    """Bird API rate limit error"""
    
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, "BIRD_RATE_LIMIT", 429)


# Utility Functions

def format_phone_number_for_bird(phone: str) -> str:
    """Format phone number for Bird API"""
    # Remove all non-digits
    clean_phone = ''.join(filter(str.isdigit, phone))
    
    # Add Colombian country code if missing
    if not clean_phone.startswith('57') and len(clean_phone) == 10:
        clean_phone = '57' + clean_phone
    
    return clean_phone


def create_payment_link_template(
    customer_name: str,
    payment_url: str,
    items: List[Dict[str, Any]],
    total_amount: float,
    expires_at: datetime
) -> WhatsAppTemplate:
    """Create payment link template"""
    
    items_text = ""
    for item in items:
        items_text += f"• {item.get('title', 'Producto')}\n"
        items_text += f"  ${item.get('unit_price', 0):,.0f} x {item.get('quantity', 1)}\n\n"
    
    message_text = f"""🛍️ *KOAJ* - Completa tu compra

¡Hola {customer_name}! 👋

Tienes los siguientes productos reservados:

{items_text}💰 *Total: ${total_amount:,.0f} COP*

Para completar tu compra, haz clic en el enlace de pago.

⏰ Este enlace expira el {expires_at.strftime('%d/%m/%Y a las %H:%M')}

¿Necesitas ayuda? Escríbenos 💬"""
    
    return WhatsAppTemplate(
        type="payment_link",
        text=message_text,
        buttons=[
            BirdButton(
                type="url",
                title="💳 Pagar Ahora",
                url=payment_url
            )
        ]
    )


def create_conversation_context(
    conversation_id: str,
    customer_phone: str
) -> ConversationContext:
    """Create new conversation context"""
    
    return ConversationContext(
        conversation_id=conversation_id,
        customer_phone=format_phone_number_for_bird(customer_phone),
        current_state="browsing",
        metadata={
            "created_at": datetime.now().isoformat(),
            "source": "whatsapp_business",
            "brand": "KOAJ"
        }
    )


def is_payment_related_message(message_content: str) -> bool:
    """Check if message is payment-related"""
    
    payment_keywords = [
        "pago", "pagar", "comprar", "precio", "costo", "total",
        "tarjeta", "efectivo", "transferencia", "carrito", "checkout"
    ]
    
    content_lower = message_content.lower()
    return any(keyword in content_lower for keyword in payment_keywords)