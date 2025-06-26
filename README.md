# KOAJ MercadoPago-Bird API Integration

This project integrates MercadoPago payment processing with Bird API for WhatsApp Business, enabling secure payment processing within WhatsApp conversations for KOAJ's e-commerce chatbot.

## Overview

The integration allows customers to:
- Browse KOAJ products through WhatsApp
- Receive secure payment links via MercadoPago
- Complete purchases without leaving WhatsApp
- Receive payment confirmations and order updates

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   WhatsApp      │────│   Bird API      │────│   Integration   │
│   Customer      │    │   Platform      │    │   Layer         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                              ┌─────────────────┐
                                              │   MercadoPago   │
                                              │   Payment API   │
                                              └─────────────────┘
```

## Features

- 🛒 **Product Catalog Integration**: Sync KOAJ products with WhatsApp catalog
- 💳 **Secure Payments**: Generate secure MercadoPago payment links
- 📱 **WhatsApp Native**: Complete payment flow within WhatsApp
- 🔄 **Real-time Updates**: Payment status updates via webhooks
- 🔐 **Security**: End-to-end encryption and signature verification
- 📊 **Analytics**: Comprehensive logging and monitoring
- 🚀 **Scalable**: AWS serverless architecture with DynamoDB

## Installation

1. Clone the repository:
```bash
git clone https://github.com/neeroai/api_mercadopago.git
cd api_mercadopago
```

2. Create Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your actual API credentials
```

5. Configure AWS credentials:
```bash
aws configure
# Or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables
```

## Configuration

### Required Environment Variables

#### MercadoPago
- `MERCADOPAGO_ACCESS_TOKEN`: Your MercadoPago access token
- `MERCADOPAGO_PUBLIC_KEY`: Your MercadoPago public key
- `MERCADOPAGO_WEBHOOK_SECRET`: Secret for webhook signature verification

#### Bird API
- `BIRD_API_KEY`: Your Bird API key
- `BIRD_API_SECRET`: Your Bird API secret
- `BIRD_WORKSPACE_ID`: Your Bird workspace ID
- `BIRD_CHANNEL_ID`: Your WhatsApp Business channel ID

#### AWS Configuration
- `AWS_DEFAULT_REGION`: AWS region (default: us-east-2)
- `ENVIRONMENT`: Environment (development/production)
- `LOG_LEVEL`: Logging level (DEBUG/INFO/WARNING/ERROR)

#### DynamoDB Tables
- `PAYMENTS_TABLE_NAME`: Payments storage table
- `CONVERSATIONS_TABLE_NAME`: Conversation state table
- `WEBHOOKS_TABLE_NAME`: Webhook logs table

#### Additional Services
- `PAYMENT_EVENTS_QUEUE`: SQS queue for payment events
- `PAYMENT_NOTIFICATIONS_TOPIC`: SNS topic for notifications

## AWS Lambda Functions

### Payment Handler (`lambda_functions/payments/handler.py`)
- `POST /payments/create` - Create payment preference
- `GET /payments/{id}/status` - Get payment status
- `POST /payments/{id}/cancel` - Cancel payment

### Webhook Handler (`lambda_functions/webhooks/handler.py`)
- `POST /webhooks/mercadopago` - MercadoPago payment notifications
- `POST /webhooks/bird` - Bird API conversation events

### API Gateway Endpoints
All endpoints are deployed via AWS API Gateway in region **us-east-2**:
- Base URL: `https://{api-gateway-id}.execute-api.us-east-2.amazonaws.com/`

## Usage Examples

### 1. Creating a Payment Link

```python
import asyncio
from decimal import Decimal
from src.mercadopago.client import get_mercadopago_client
from src.mercadopago.models import PaymentRequest, PaymentItem, Customer
from src.bird.client import get_bird_client
from src.integration.payment_orchestrator import get_payment_orchestrator

# Create payment for WhatsApp conversation
async def create_payment_example():
    # Initialize payment orchestrator
    orchestrator = get_payment_orchestrator()
    
    # Define payment items
    items = [
        {
            "id": "101114160004-909",
            "title": "SUETER PECHERA CONTRASTE ARMI By KOAJ",
            "description": "Suéter en cuello alto, confeccionado en tejido jersey",
            "quantity": 1,
            "unit_price": Decimal("224750.00")  # Colombian Pesos
        }
    ]
    
    # Customer information
    customer_info = {
        "name": "Juan Pérez",
        "email": "juan.perez@example.com"
    }
    
    # Initiate complete payment flow
    payment_flow = await orchestrator.initiate_payment_flow(
        conversation_id="whatsapp-conversation-id",
        customer_phone="+573001234567",
        items=items,
        customer_info=customer_info
    )
    
    print(f"Payment flow created: {payment_flow.flow_id}")
    print(f"Checkout URL: {payment_flow.checkout_url}")
    
# Run the example
# asyncio.run(create_payment_example())
```

### 2. Processing Payment Webhooks

```python
from src.integration.payment_orchestrator import get_payment_orchestrator

async def process_webhook_example(webhook_data):
    """Process MercadoPago webhook notification"""
    orchestrator = get_payment_orchestrator()
    
    # Extract payment information
    payment_id = webhook_data.get("data", {}).get("id")
    payment_status = "approved"  # From webhook data
    
    # Process status update (automatically sends WhatsApp notifications)
    success = await orchestrator.process_payment_status_update(
        payment_id=payment_id,
        payment_status=payment_status,
        payment_data=webhook_data
    )
    
    return success
```

### 3. Direct API Usage

```python
from src.mercadopago.client import get_mercadopago_client
from src.mercadopago.models import PaymentRequest, PaymentItem, Customer

async def direct_api_example():
    # Get MercadoPago client
    mp_client = get_mercadopago_client()
    
    # Create payment request
    payment_request = PaymentRequest(
        items=[
            PaymentItem(
                id="product-123",
                title="KOAJ Product",
                quantity=1,
                unit_price=Decimal("150000.00")
            )
        ],
        customer=Customer(
            phone="+573001234567",
            name="Cliente KOAJ"
        ),
        conversation_id="conv-123"
    )
    
    # Create payment preference
    payment_response = await mp_client.create_payment_preference(payment_request)
    print(f"Payment URL: {payment_response.checkout_url}")
```

## Testing

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_mercadopago_client.py

# Run integration tests (requires AWS credentials)
pytest tests/integration/

# Run tests in watch mode
pytest-watch

# Code quality checks
black src/ tests/           # Format code
isort src/ tests/           # Sort imports
flake8 src/ tests/          # Linting
mypy src/                   # Type checking
```

## Security

- All webhook payloads are signature-verified using HMAC-SHA256
- API credentials stored in AWS Secrets Manager
- Payment data encrypted in transit and at rest
- HTTPS required for all production endpoints
- Input validation using Pydantic models
- Colombian phone number format validation

## Development

### Project Structure
```
├── lambda_functions/          # AWS Lambda handlers
│   ├── payments/             # Payment operations handler
│   └── webhooks/             # Webhook processing handler
├── src/                      # Core application code
│   ├── config/              # Settings and logging configuration
│   ├── mercadopago/         # MercadoPago API integration
│   ├── bird/                # Bird API WhatsApp integration
│   ├── integration/         # Payment flow orchestration
│   └── utils/               # Shared utilities
├── tests/                   # Test suites
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests
├── infrastructure/         # AWS infrastructure as code
└── docs/                   # Documentation
```

### AWS Services Used
- **Lambda**: Serverless compute for handlers
- **DynamoDB**: Payment and conversation state storage
- **SQS**: Event processing queues
- **SNS**: Payment notifications
- **API Gateway**: REST API endpoints
- **CloudWatch**: Logging and monitoring
- **Secrets Manager**: Secure credential storage

### Local Development

1. **Environment Setup**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configuration**:
   - Copy `.env.example` to `.env`
   - Configure MercadoPago sandbox credentials
   - Set up Bird API test workspace

3. **Testing**:
   - Use `pytest` for unit tests
   - Mock AWS services with `moto`
   - Test webhooks with local tunneling (ngrok)

4. **AWS Local Development**:
   - Use DynamoDB Local for database testing
   - Configure AWS CLI with development credentials
   - Test Lambda functions with SAM CLI

### Deployment

1. **Infrastructure**:
   ```bash
   cd infrastructure/terraform
   terraform init
   terraform plan -var="environment=prod"
   terraform apply
   ```

2. **Lambda Deployment**:
   ```bash
   # Package dependencies
   pip install -r requirements.txt -t lambda_functions/
   
   # Deploy with AWS CLI or Terraform
   aws lambda update-function-code --function-name koaj-webhook-handler
   ```

## Monitoring

### Structured Logging
- Payment events with correlation IDs
- API call performance metrics  
- Webhook processing results
- Error tracking with stack traces

### CloudWatch Integration
- Lambda function metrics and logs
- Custom metrics for payment flows
- Alarms for error rates and latency
- Dashboard for business metrics

### Key Metrics Tracked
- Payment conversion rates
- Average processing time
- Webhook processing success rate
- API response times

## Troubleshooting

### Common Issues

1. **Webhook not receiving notifications**
   - Verify webhook URL is publicly accessible
   - Check webhook signature verification
   - Ensure HTTPS in production

2. **Payment links not working**
   - Verify MercadoPago credentials
   - Check payment preference configuration
   - Validate customer data format

3. **WhatsApp messages not sending**
   - Verify Bird API credentials and workspace configuration
   - Check WhatsApp Business channel status
   - Validate Colombian phone number format (+57XXXXXXXXXX)

4. **AWS Lambda issues**
   - Check CloudWatch logs for error details
   - Verify IAM permissions for DynamoDB and SQS
   - Ensure environment variables are set correctly

5. **DynamoDB connection issues**
   - Verify AWS region is set to us-east-2
   - Check table names match environment configuration
   - Ensure Lambda has DynamoDB permissions

## Support

For technical support or questions:
- Check the troubleshooting section
- Review logs for error details
- Contact the development team

## License

MIT License - See LICENSE file for details