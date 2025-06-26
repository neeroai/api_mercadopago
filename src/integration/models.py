"""
Integration models for payment orchestration
Data structures for managing payment flows and conversation states
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field, validator


class PaymentFlowStatus(str, Enum):
    """Payment flow status enumeration"""
    INITIATED = "initiated"
    PREFERENCE_CREATED = "preference_created"
    LINK_SENT = "link_sent"
    PAYMENT_PENDING = "payment_pending"
    PAYMENT_APPROVED = "payment_approved"
    PAYMENT_FAILED = "payment_failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    COMPLETED = "completed"
    FAILED = "failed"


class IntegrationEventType(str, Enum):
    """Integration event types for tracking"""
    PAYMENT_FLOW_STARTED = "payment_flow_started"
    PAYMENT_LINK_GENERATED = "payment_link_generated"
    PAYMENT_LINK_SENT = "payment_link_sent"
    PAYMENT_STATUS_UPDATED = "payment_status_updated"
    CONVERSATION_MESSAGE_RECEIVED = "conversation_message_received"
    WEBHOOK_PROCESSED = "webhook_processed"
    ERROR_OCCURRED = "error_occurred"


class PaymentFlow(BaseModel):
    """
    Complete payment flow model
    Tracks the entire payment lifecycle from initiation to completion
    """
    flow_id: str = Field(..., description="Unique flow identifier")
    conversation_id: str = Field(..., description="WhatsApp conversation ID")
    customer_phone: str = Field(..., description="Customer phone number")
    
    # Payment data
    items: List[Dict[str, Any]] = Field(..., description="Items being purchased")
    customer_info: Dict[str, Any] = Field(default_factory=dict, description="Customer information")
    
    # MercadoPago integration
    payment_id: Optional[str] = Field(None, description="MercadoPago payment/preference ID")
    transaction_id: Optional[str] = Field(None, description="Internal transaction ID")
    checkout_url: Optional[str] = Field(None, description="MercadoPago checkout URL")
    
    # Status and timing
    status: PaymentFlowStatus = Field(..., description="Current flow status")
    payment_status: Optional[str] = Field(None, description="MercadoPago payment status")
    created_at: datetime = Field(..., description="Flow creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    expires_at: Optional[datetime] = Field(None, description="Payment expiration timestamp")
    
    # Additional data
    payment_data: Optional[Dict[str, Any]] = Field(None, description="Complete payment response data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    @validator('customer_phone')
    def validate_phone(cls, v):
        # Basic Colombian phone validation
        clean_phone = ''.join(filter(str.isdigit, v))
        if not (clean_phone.startswith('57') and len(clean_phone) == 12):
            raise ValueError('Invalid Colombian phone number format')
        return v
    
    @property
    def total_amount(self) -> Decimal:
        """Calculate total amount from items"""
        return sum(
            Decimal(str(item["unit_price"])) * item["quantity"] 
            for item in self.items
        )
    
    @property
    def is_active(self) -> bool:
        """Check if payment flow is still active"""
        active_statuses = [
            PaymentFlowStatus.INITIATED,
            PaymentFlowStatus.PREFERENCE_CREATED,
            PaymentFlowStatus.LINK_SENT,
            PaymentFlowStatus.PAYMENT_PENDING
        ]
        return self.status in active_statuses
    
    @property
    def is_completed(self) -> bool:
        """Check if payment flow is completed"""
        completed_statuses = [
            PaymentFlowStatus.PAYMENT_APPROVED,
            PaymentFlowStatus.COMPLETED
        ]
        return self.status in completed_statuses
    
    @property
    def is_failed(self) -> bool:
        """Check if payment flow has failed"""
        failed_statuses = [
            PaymentFlowStatus.PAYMENT_FAILED,
            PaymentFlowStatus.CANCELLED,
            PaymentFlowStatus.EXPIRED,
            PaymentFlowStatus.FAILED
        ]
        return self.status in failed_statuses


class ConversationSession(BaseModel):
    """
    Conversation session for tracking customer interactions
    """
    session_id: str = Field(..., description="Unique session identifier")
    conversation_id: str = Field(..., description="WhatsApp conversation ID")
    customer_phone: str = Field(..., description="Customer phone number")
    
    # Session state
    current_state: str = Field(default="browsing", description="Current conversation state")
    previous_state: Optional[str] = Field(None, description="Previous conversation state")
    
    # Customer data
    customer_info: Dict[str, Any] = Field(default_factory=dict, description="Customer information")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="Customer preferences")
    
    # Cart and shopping
    cart_items: List[Dict[str, Any]] = Field(default_factory=list, description="Shopping cart items")
    cart_total: Decimal = Field(default=Decimal('0'), description="Cart total amount")
    
    # Active flows
    active_payment_flow: Optional[str] = Field(None, description="Active payment flow ID")
    payment_history: List[str] = Field(default_factory=list, description="Payment flow history")
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.now, description="Session creation")
    last_activity: datetime = Field(default_factory=datetime.now, description="Last activity")
    expires_at: Optional[datetime] = Field(None, description="Session expiration")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Session metadata")
    
    def add_cart_item(self, item: Dict[str, Any]) -> None:
        """Add item to cart"""
        # Check if item already exists
        existing_item = next(
            (cart_item for cart_item in self.cart_items if cart_item.get('id') == item.get('id')),
            None
        )
        
        if existing_item:
            # Update quantity
            existing_item['quantity'] += item.get('quantity', 1)
        else:
            # Add new item
            self.cart_items.append({
                **item,
                'added_at': datetime.now().isoformat()
            })
        
        self._update_cart_total()
        self.last_activity = datetime.now()
    
    def remove_cart_item(self, item_id: str) -> bool:
        """Remove item from cart"""
        original_length = len(self.cart_items)
        self.cart_items = [item for item in self.cart_items if item.get('id') != item_id]
        
        if len(self.cart_items) < original_length:
            self._update_cart_total()
            self.last_activity = datetime.now()
            return True
        return False
    
    def clear_cart(self) -> None:
        """Clear all items from cart"""
        self.cart_items = []
        self.cart_total = Decimal('0')
        self.last_activity = datetime.now()
    
    def update_state(self, new_state: str) -> None:
        """Update conversation state"""
        self.previous_state = self.current_state
        self.current_state = new_state
        self.last_activity = datetime.now()
    
    def _update_cart_total(self) -> None:
        """Recalculate cart total"""
        self.cart_total = sum(
            Decimal(str(item.get('unit_price', 0))) * item.get('quantity', 1)
            for item in self.cart_items
        )


class IntegrationEvent(BaseModel):
    """
    Integration event for tracking and monitoring
    """
    event_id: str = Field(..., description="Unique event identifier")
    event_type: IntegrationEventType = Field(..., description="Event type")
    timestamp: datetime = Field(default_factory=datetime.now, description="Event timestamp")
    
    # Context
    conversation_id: Optional[str] = Field(None, description="Associated conversation ID")
    payment_flow_id: Optional[str] = Field(None, description="Associated payment flow ID")
    customer_phone: Optional[str] = Field(None, description="Customer phone number")
    
    # Event data
    data: Dict[str, Any] = Field(default_factory=dict, description="Event data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Event metadata")
    
    # Status
    success: bool = Field(default=True, description="Event success status")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # Processing
    processed_at: Optional[datetime] = Field(None, description="Processing completion time")
    retry_count: int = Field(default=0, description="Number of retry attempts")


class WebhookEvent(BaseModel):
    """
    Webhook event model for processing external notifications
    """
    webhook_id: str = Field(..., description="Webhook identifier")
    source: str = Field(..., description="Webhook source (mercadopago, bird)")
    event_type: str = Field(..., description="Source-specific event type")
    received_at: datetime = Field(default_factory=datetime.now, description="Reception timestamp")
    
    # Webhook data
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    payload: Dict[str, Any] = Field(..., description="Webhook payload")
    signature: Optional[str] = Field(None, description="Webhook signature")
    
    # Processing
    processed: bool = Field(default=False, description="Processing status")
    processed_at: Optional[datetime] = Field(None, description="Processing timestamp")
    processing_result: Optional[Dict[str, Any]] = Field(None, description="Processing result")
    
    # Validation
    signature_valid: bool = Field(default=False, description="Signature validation status")
    payload_valid: bool = Field(default=False, description="Payload validation status")


class PaymentSummaryReport(BaseModel):
    """
    Payment summary report for analytics
    """
    report_id: str = Field(..., description="Report identifier")
    period_start: datetime = Field(..., description="Report period start")
    period_end: datetime = Field(..., description="Report period end")
    generated_at: datetime = Field(default_factory=datetime.now, description="Report generation time")
    
    # Summary statistics
    total_flows: int = Field(default=0, description="Total payment flows")
    successful_payments: int = Field(default=0, description="Successful payments")
    failed_payments: int = Field(default=0, description="Failed payments")
    pending_payments: int = Field(default=0, description="Pending payments")
    
    # Financial data
    total_amount: Decimal = Field(default=Decimal('0'), description="Total transaction amount")
    successful_amount: Decimal = Field(default=Decimal('0'), description="Successful payment amount")
    average_transaction: Decimal = Field(default=Decimal('0'), description="Average transaction amount")
    
    # Performance metrics
    conversion_rate: float = Field(default=0.0, description="Payment conversion rate")
    average_completion_time: float = Field(default=0.0, description="Average completion time in minutes")
    
    # Breakdown by status
    status_breakdown: Dict[str, int] = Field(default_factory=dict, description="Breakdown by status")
    
    # Top products/categories
    top_products: List[Dict[str, Any]] = Field(default_factory=list, description="Top selling products")
    
    @property
    def success_rate(self) -> float:
        """Calculate payment success rate"""
        if self.total_flows == 0:
            return 0.0
        return (self.successful_payments / self.total_flows) * 100


class IntegrationHealth(BaseModel):
    """
    Integration health status model
    """
    service: str = Field(..., description="Service name")
    status: str = Field(..., description="Health status (healthy, degraded, unhealthy)")
    last_check: datetime = Field(default_factory=datetime.now, description="Last health check")
    
    # Service metrics
    response_time_ms: Optional[int] = Field(None, description="Average response time")
    error_rate: float = Field(default=0.0, description="Error rate percentage")
    success_rate: float = Field(default=100.0, description="Success rate percentage")
    
    # Dependencies
    dependencies: Dict[str, str] = Field(default_factory=dict, description="Dependency health status")
    
    # Issues
    issues: List[str] = Field(default_factory=list, description="Current issues")
    warnings: List[str] = Field(default_factory=list, description="Current warnings")
    
    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy"""
        return self.status == "healthy" and len(self.issues) == 0


# Error Models

class IntegrationError(Exception):
    """Base integration error class"""
    
    def __init__(self, message: str, code: str = "INTEGRATION_ERROR", 
                 status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class PaymentFlowError(IntegrationError):
    """Payment flow specific error"""
    
    def __init__(self, message: str, flow_id: Optional[str] = None, 
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "PAYMENT_FLOW_ERROR", 500, details)
        self.flow_id = flow_id


class ConversationError(IntegrationError):
    """Conversation management error"""
    
    def __init__(self, message: str, conversation_id: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "CONVERSATION_ERROR", 500, details)
        self.conversation_id = conversation_id


# Utility functions

def create_payment_flow_id(conversation_id: str) -> str:
    """Create unique payment flow ID"""
    from uuid import uuid4
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid4())[:8]
    return f"flow_{timestamp}_{conversation_id}_{unique_id}"


def create_session_id(conversation_id: str, customer_phone: str) -> str:
    """Create unique session ID"""
    from hashlib import md5
    data = f"{conversation_id}_{customer_phone}_{datetime.now().date()}"
    return f"session_{md5(data.encode()).hexdigest()[:12]}"


def calculate_conversion_rate(successful: int, total: int) -> float:
    """Calculate conversion rate percentage"""
    if total == 0:
        return 0.0
    return (successful / total) * 100


def format_duration_minutes(start_time: datetime, end_time: datetime) -> float:
    """Calculate duration in minutes between two timestamps"""
    delta = end_time - start_time
    return delta.total_seconds() / 60