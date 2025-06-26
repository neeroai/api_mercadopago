# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Python-based AWS serverless integration between MercadoPago payment processing and Bird API for WhatsApp Business. The system enables secure payment processing within WhatsApp conversations for KOAJ's e-commerce chatbot, deployed using AWS Lambda, DynamoDB, SQS, and API Gateway.

## Development Environment Setup

### Core Dependencies
```bash
# Install Python dependencies
pip install -r requirements.txt

# Environment configuration
cp .env.example .env
# Edit .env with actual API credentials
```

### AWS Region Configuration
- **Default Region**: us-east-2 (Ohio)
- All AWS services (Lambda, DynamoDB, SQS, SNS, S3, API Gateway) deploy to us-east-2
- This is critical for service integration and latency optimization

### Testing Commands
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

# Type checking
mypy src/

# Code formatting
black src/ tests/
isort src/ tests/

# Linting
flake8 src/ tests/
```

## Architecture Overview

### Core Integration Flow
The system orchestrates payments through three main layers:

1. **API Layer** (`lambda_functions/`): AWS Lambda handlers for webhooks and payment operations
2. **Integration Layer** (`src/integration/`): PaymentOrchestrator coordinates between MercadoPago and Bird APIs
3. **Service Clients** (`src/mercadopago/`, `src/bird/`): API-specific implementations

### Key Architectural Patterns

#### Payment Flow Orchestration
- **PaymentOrchestrator** (`src/integration/payment_orchestrator.py`) is the central coordinator
- Manages complete payment lifecycle: initiation → preference creation → WhatsApp messaging → webhook processing → status updates
- Implements async/await patterns for AWS Lambda compatibility
- Uses singleton pattern for client instances to optimize cold starts

#### AWS Integration Patterns
- **Settings Management**: Pydantic-based configuration with AWS-specific defaults (`src/config/settings.py`)
- **Logging**: Structured logging with AWS Lambda Powertools integration (`src/config/logger.py`) 
- **Error Handling**: Custom exception hierarchy with AWS CloudWatch integration
- **Resource Management**: Lazy-loaded AWS service clients with connection pooling

#### Data Models Architecture
- **Pydantic Models**: All data structures use Pydantic for validation and serialization
- **Payment Models** (`src/mercadopago/models.py`): Colombian-specific payment validation (phone numbers, currency)
- **Conversation Models** (`src/bird/models.py`): WhatsApp Business message templates and state management
- **Integration Models** (`src/integration/models.py`): Payment flow tracking and orchestration

### WhatsApp Message Templates
The Bird client implements specialized message templates:
- **PaymentLinkMessage**: Branded payment link with expiration and item details
- **PaymentConfirmationMessage**: Success notification with order details
- **PaymentFailureMessage**: Error handling with retry options and support contact

### Security Implementation
- **Webhook Signature Verification**: HMAC-SHA256 verification for MercadoPago webhooks
- **Environment-based Configuration**: No hardcoded credentials, AWS Secrets Manager integration
- **Input Validation**: Pydantic models enforce data validation at API boundaries
- **Colombian Compliance**: Phone number validation for Colombian format (+57XXXXXXXXXX)

## Key Development Patterns

### Async/Await Usage
All client operations use async/await for Lambda performance:
```python
# Correct pattern for payment flow
payment_response = await mp_client.create_payment_preference(payment_request)
success = await bird_client.send_payment_link_message(phone, payment_message)
```

### Error Handling Strategy
- **Service-specific Exceptions**: PaymentError, BirdError, IntegrationError
- **Logging Context**: All errors logged with full context for debugging
- **Graceful Degradation**: Webhook processing continues even if individual operations fail

### Configuration Access
```python
# Always use dependency injection pattern
from src.config.settings import get_settings, get_aws_resources
settings = get_settings()
aws_resources = get_aws_resources()
```

### Client Instance Management
```python
# Use singleton getters to optimize Lambda cold starts
mp_client = get_mercadopago_client()
bird_client = get_bird_client() 
orchestrator = get_payment_orchestrator()
```

## AWS Lambda Deployment Context

### Lambda Function Structure
- **Webhook Handler** (`lambda_functions/webhooks/handler.py`): Processes MercadoPago notifications
- **Payment Handler** (`lambda_functions/payments/handler.py`): Creates payment preferences and manages payment operations

### AWS Service Integration
- **DynamoDB**: Payment flow state, conversation context, webhook logs
- **SQS**: Asynchronous payment event processing
- **SNS**: Payment status notifications
- **CloudWatch**: Structured logging and metrics
- **API Gateway**: REST endpoints for payment operations and webhooks

### Environment Variables Priority
1. AWS Lambda environment variables
2. AWS Secrets Manager (for production)
3. .env file (development only)

## MercadoPago Integration Specifics

### Colombian Market Configuration
- **Currency**: Colombian Pesos (COP) with centavos handling
- **Payment Methods**: Credit/debit cards, PSE, Efecty, Baloto
- **Phone Validation**: +57 prefix required for Colombian numbers
- **Sandbox Mode**: Controlled via MERCADOPAGO_SANDBOX environment variable

### Webhook Processing
- **Signature Verification**: Required for all incoming webhooks
- **Idempotency**: Webhook processing handles duplicate notifications
- **Retry Logic**: Failed webhook processing triggers SQS retry mechanism

## Bird API Integration Specifics

### WhatsApp Business Features
- **Template Messages**: Structured payment notifications with buttons
- **Conversation Context**: Persistent shopping cart and customer state
- **Media Support**: Product images and QR codes for payment links

### Authentication Flow
- **Token Management**: Automatic token refresh with expiration handling
- **Rate Limiting**: Built-in backoff strategy for API limits
- **Error Recovery**: Automatic reconnection for transient failures

## Development Workflow Considerations

### Local Development
- Use sandbox mode for both MercadoPago and Bird APIs
- DynamoDB Local or moto for testing AWS services
- Structured logging helps debug complex payment flows

### AWS Deployment
- Lambda functions require layer packaging for dependencies
- Environment-specific resource naming (dev/staging/prod suffixes)
- CloudFormation/Terraform for infrastructure as code

### Testing Strategy
- **Unit Tests**: Mock external API calls using responses library
- **Integration Tests**: Use moto for AWS service testing
- **End-to-End Tests**: Sandbox environments for full payment flow testing