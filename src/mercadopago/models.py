"""
Data models for MercadoPago integration
Pydantic models for validation and serialization
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field, validator, root_validator


class PaymentStatus(str, Enum):
    """Payment status constants"""
    PENDING = "pending"
    APPROVED = "approved"
    AUTHORIZED = "authorized"
    IN_PROCESS = "in_process"
    IN_MEDIATION = "in_mediation"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    CHARGED_BACK = "charged_back"


class PaymentStatusDetail(str, Enum):
    """Payment status detail constants"""
    # Pending
    PENDING_CONTINGENCY = "pending_contingency"
    PENDING_REVIEW_MANUAL = "pending_review_manual"
    PENDING_WAITING_PAYMENT = "pending_waiting_payment"
    PENDING_WAITING_TRANSFER = "pending_waiting_transfer"
    
    # Approved
    ACCREDITED = "accredited"
    
    # Rejected
    CC_REJECTED_BAD_FILLED_CARD_NUMBER = "cc_rejected_bad_filled_card_number"
    CC_REJECTED_BAD_FILLED_DATE = "cc_rejected_bad_filled_date"
    CC_REJECTED_BAD_FILLED_OTHER = "cc_rejected_bad_filled_other"
    CC_REJECTED_BAD_FILLED_SECURITY_CODE = "cc_rejected_bad_filled_security_code"
    CC_REJECTED_BLACKLIST = "cc_rejected_blacklist"
    CC_REJECTED_CALL_FOR_AUTHORIZE = "cc_rejected_call_for_authorize"
    CC_REJECTED_CARD_DISABLED = "cc_rejected_card_disabled"
    CC_REJECTED_CARD_ERROR = "cc_rejected_card_error"
    CC_REJECTED_DUPLICATED_PAYMENT = "cc_rejected_duplicated_payment"
    CC_REJECTED_HIGH_RISK = "cc_rejected_high_risk"
    CC_REJECTED_INSUFFICIENT_AMOUNT = "cc_rejected_insufficient_amount"
    CC_REJECTED_INVALID_INSTALLMENTS = "cc_rejected_invalid_installments"
    CC_REJECTED_MAX_ATTEMPTS = "cc_rejected_max_attempts"
    CC_REJECTED_OTHER_REASON = "cc_rejected_other_reason"


class IdentificationType(str, Enum):
    """Colombian identification types"""
    CC = "CC"  # Cédula de Ciudadanía
    CE = "CE"  # Cédula de Extranjería
    TI = "TI"  # Tarjeta de Identidad
    PP = "PP"  # Pasaporte


class PaymentMethodType(str, Enum):
    """Payment method types"""
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    TICKET = "ticket"
    ACCOUNT_MONEY = "account_money"
    DIGITAL_CURRENCY = "digital_currency"
    DIGITAL_WALLET = "digital_wallet"


class ConversationState(str, Enum):
    """WhatsApp conversation states for payment flow"""
    BROWSING = "browsing"
    ITEM_SELECTED = "item_selected"
    PAYMENT_REQUESTED = "payment_requested"
    PAYMENT_PENDING = "payment_pending"
    PAYMENT_COMPLETED = "payment_completed"
    PAYMENT_FAILED = "payment_failed"
    ORDER_CONFIRMED = "order_confirmed"


# Request Models

class PaymentItem(BaseModel):
    """Payment item model"""
    id: str = Field(..., description="Product ID")
    title: str = Field(..., max_length=256, description="Product title")
    description: Optional[str] = Field(None, max_length=600, description="Product description")
    quantity: int = Field(..., ge=1, le=100, description="Item quantity")
    unit_price: Decimal = Field(..., gt=0, description="Unit price in COP")
    
    @validator('unit_price')
    def validate_unit_price(cls, v):
        if v <= 0:
            raise ValueError('Unit price must be greater than 0')
        # Convert to 2 decimal places
        return round(v, 2)


class CustomerAddress(BaseModel):
    """Customer address model"""
    street: Optional[str] = Field(None, max_length=256)
    city: Optional[str] = Field(None, max_length=64)
    state: Optional[str] = Field(None, max_length=64)
    zip_code: Optional[str] = Field(None, max_length=16)
    country: str = Field(default="CO", description="Country code")


class Customer(BaseModel):
    """Customer information model"""
    phone: str = Field(..., description="Customer phone number")
    name: Optional[str] = Field(None, max_length=128, description="Customer first name")
    surname: Optional[str] = Field(None, max_length=128, description="Customer last name")
    email: Optional[str] = Field(None, description="Customer email")
    identification_type: Optional[IdentificationType] = Field(None, description="ID type")
    identification_number: Optional[str] = Field(None, max_length=32, description="ID number")
    address: Optional[CustomerAddress] = Field(None, description="Customer address")
    
    @validator('phone')
    def validate_phone(cls, v):
        # Colombian phone number validation
        import re
        # Remove all non-digits
        clean_phone = re.sub(r'\D', '', v)
        
        # Should be Colombian format: +57XXXXXXXXX (12 digits total)
        if not (clean_phone.startswith('57') and len(clean_phone) == 12):
            # Try to add 57 prefix if it's missing
            if len(clean_phone) == 10:
                clean_phone = '57' + clean_phone
            else:
                raise ValueError('Invalid Colombian phone number format')
        
        return '+' + clean_phone
    
    @validator('email')
    def validate_email(cls, v):
        if v is not None:
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, v):
                raise ValueError('Invalid email format')
        return v


class PaymentRequest(BaseModel):
    """Payment request model"""
    items: List[PaymentItem] = Field(..., min_items=1, max_items=50, description="Payment items")
    customer: Customer = Field(..., description="Customer information")
    conversation_id: str = Field(..., max_length=128, description="WhatsApp conversation ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    @validator('items')
    def validate_items_total(cls, v):
        total = sum(item.unit_price * item.quantity for item in v)
        if total <= 0:
            raise ValueError('Total amount must be greater than 0')
        if total > 999999999:  # ~10M COP
            raise ValueError('Total amount exceeds maximum allowed')
        return v


# Response Models

class PaymentResponse(BaseModel):
    """Payment response model"""
    id: str = Field(..., description="Payment preference ID")
    checkout_url: str = Field(..., description="Checkout URL for payment")
    qr_code: Optional[str] = Field(None, description="QR code for payment")
    transaction_id: str = Field(..., description="Internal transaction ID")
    expires_at: datetime = Field(..., description="Payment expiration date")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class PaymentPreference(BaseModel):
    """Payment preference model"""
    payment_id: str
    transaction_id: str
    conversation_id: str
    customer_phone: str
    status: PaymentStatus
    total_amount: Decimal
    currency: str = "COP"
    items: List[PaymentItem]
    created_at: datetime
    expires_at: datetime
    checkout_url: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


# Webhook Models

class WebhookData(BaseModel):
    """Webhook data model"""
    id: str = Field(..., description="Payment or resource ID")


class WebhookNotification(BaseModel):
    """MercadoPago webhook notification model"""
    id: int = Field(..., description="Notification ID")
    live_mode: bool = Field(..., description="Live mode flag")
    type: str = Field(..., description="Notification type")
    date_created: str = Field(..., description="Creation date")
    application_id: int = Field(..., description="Application ID")
    user_id: int = Field(..., description="User ID")
    version: int = Field(..., description="API version")
    api_version: str = Field(..., description="API version string")
    action: str = Field(..., description="Action performed")
    data: WebhookData = Field(..., description="Notification data")
    
    @validator('type')
    def validate_type(cls, v):
        valid_types = ['payment', 'plan', 'subscription', 'invoice', 'point_integration_wh']
        if v not in valid_types:
            raise ValueError(f'Invalid notification type: {v}')
        return v
    
    @validator('action')
    def validate_action(cls, v):
        valid_actions = ['payment.created', 'payment.updated']
        if v not in valid_actions:
            raise ValueError(f'Invalid action: {v}')
        return v


# WhatsApp Message Models

class WhatsAppMessage(BaseModel):
    """Base WhatsApp message model"""
    type: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PaymentLinkMessage(WhatsAppMessage):
    """Payment link message for WhatsApp"""
    type: str = Field(default="payment_link")
    customer_name: Optional[str]
    payment_url: str
    total_amount: Decimal
    currency: str = "COP"
    items: List[PaymentItem]
    expires_at: datetime
    brand_name: str = "KOAJ"


class PaymentConfirmationMessage(WhatsAppMessage):
    """Payment confirmation message for WhatsApp"""
    type: str = Field(default="payment_confirmation")
    customer_name: Optional[str]
    payment_id: str
    total_amount: Decimal
    currency: str = "COP"
    items: List[PaymentItem]
    approval_code: Optional[str]
    brand_name: str = "KOAJ"


class PaymentFailureMessage(WhatsAppMessage):
    """Payment failure message for WhatsApp"""
    type: str = Field(default="payment_failure")
    customer_name: Optional[str]
    reason: str
    retry_url: Optional[str]
    support_phone: str = "+573001234567"
    brand_name: str = "KOAJ"


# Error Models

class PaymentError(Exception):
    """Custom payment error class"""
    
    def __init__(self, message: str, code: str = "PAYMENT_ERROR", 
                 status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class ValidationError(PaymentError):
    """Validation error class"""
    
    def __init__(self, message: str, field: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "VALIDATION_ERROR", 400, details)
        self.field = field


# Utility Models

class PaymentSummary(BaseModel):
    """Payment summary for reporting"""
    total_payments: int
    total_amount: Decimal
    approved_payments: int
    approved_amount: Decimal
    pending_payments: int
    pending_amount: Decimal
    rejected_payments: int
    rejected_amount: Decimal
    currency: str = "COP"
    period_start: datetime
    period_end: datetime


class ColombianPaymentMethods:
    """Colombian payment method constants"""
    VISA = "visa"
    MASTERCARD = "master"
    AMERICAN_EXPRESS = "amex"
    DINERS = "diners"
    PSE = "pse"
    EFECTY = "efecty"
    BALOTO = "baloto"
    BANCOLOMBIA = "bancolombia"
    NEQUI = "nequi"
    DAVIPLATA = "daviplata"


# Validation helpers

def format_colombian_currency(amount: Decimal) -> str:
    """Format amount as Colombian currency"""
    return f"${amount:,.0f} COP"


def format_colombian_phone(phone: str) -> str:
    """Format Colombian phone number for display"""
    clean_phone = ''.join(filter(str.isdigit, phone))
    if clean_phone.startswith('57') and len(clean_phone) == 12:
        # Format as +57 XXX XXX XXXX
        return f"+57 {clean_phone[2:5]} {clean_phone[5:8]} {clean_phone[8:]}"
    return phone


def is_payment_successful(status: PaymentStatus) -> bool:
    """Check if payment status indicates success"""
    return status in [PaymentStatus.APPROVED, PaymentStatus.AUTHORIZED]


def is_payment_failed(status: PaymentStatus) -> bool:
    """Check if payment status indicates failure"""
    return status in [PaymentStatus.REJECTED, PaymentStatus.CANCELLED]


def is_payment_pending(status: PaymentStatus) -> bool:
    """Check if payment status indicates pending"""
    return status in [PaymentStatus.PENDING, PaymentStatus.IN_PROCESS]


def get_payment_status_message(status: PaymentStatus, status_detail: Optional[str] = None) -> str:
    """Get user-friendly payment status message in Spanish"""
    status_messages = {
        PaymentStatus.APPROVED: "¡Pago aprobado! Tu compra ha sido procesada exitosamente.",
        PaymentStatus.PENDING: "Tu pago está siendo procesado. Te notificaremos cuando esté listo.",
        PaymentStatus.IN_PROCESS: "Tu pago está en proceso de verificación.",
        PaymentStatus.REJECTED: "Tu pago fue rechazado. Por favor intenta con otro método de pago.",
        PaymentStatus.CANCELLED: "El pago fue cancelado.",
        PaymentStatus.REFUNDED: "Tu pago ha sido reembolsado.",
        PaymentStatus.CHARGED_BACK: "Se ha procesado una devolución del cargo."
    }
    
    base_message = status_messages.get(status, "Estado de pago desconocido.")
    
    # Add specific details for rejected payments
    if status == PaymentStatus.REJECTED and status_detail:
        detail_messages = {
            "cc_rejected_insufficient_amount": "Fondos insuficientes en la tarjeta.",
            "cc_rejected_bad_filled_card_number": "Número de tarjeta incorrecto.",
            "cc_rejected_bad_filled_date": "Fecha de vencimiento incorrecta.",
            "cc_rejected_bad_filled_security_code": "Código de seguridad incorrecto.",
            "cc_rejected_card_disabled": "La tarjeta está deshabilitada.",
            "cc_rejected_call_for_authorize": "Debes autorizar el pago con tu banco.",
            "cc_rejected_duplicated_payment": "Pago duplicado detectado."
        }
        
        if status_detail in detail_messages:
            base_message += f" {detail_messages[status_detail]}"
    
    return base_message