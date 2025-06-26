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
- 🚀 **Scalable**: Redis-based session management

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd api_mercadopago
```

2. Install dependencies:
```bash
npm install
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your actual API credentials
```

4. Start Redis (required for session management):
```bash
redis-server
```

5. Run the application:
```bash
# Development
npm run dev

# Production
npm start
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

#### Optional Configuration
- `NODE_ENV`: Environment (development/production)
- `PORT`: Server port (default: 3000)
- `REDIS_URL`: Redis connection URL
- `LOG_LEVEL`: Logging level (debug/info/warn/error)

## API Endpoints

### Payment Endpoints
- `POST /api/payments/create` - Create payment preference
- `GET /api/payments/:id/status` - Get payment status
- `POST /api/payments/:id/cancel` - Cancel payment

### Webhook Endpoints
- `POST /webhooks/mercadopago` - MercadoPago payment notifications
- `POST /webhooks/bird` - Bird API conversation events

### Health & Monitoring
- `GET /health` - Health check
- `GET /api/stats` - Integration statistics

## Usage Examples

### 1. Creating a Payment Link

```javascript
const { MercadoPagoClient } = require('./src/mercadopago/client');
const { BirdClient } = require('./src/bird/client');

// Create payment for WhatsApp conversation
const paymentData = {
  items: [
    {
      id: '101114160004-909',
      title: 'SUETER PECHERA CONTRASTE ARMI By KOAJ',
      quantity: 1,
      unitPrice: 22475.00
    }
  ],
  customer: {
    phone: '+573001234567',
    name: 'Juan Pérez'
  },
  conversationId: 'whatsapp-conversation-id'
};

const paymentLink = await mercadopagoClient.createPaymentPreference(paymentData);
await birdClient.sendPaymentMessage(paymentData.customer.phone, paymentLink);
```

### 2. Handling Payment Confirmation

```javascript
// Webhook handler automatically processes payment notifications
// and sends confirmation messages via WhatsApp

// Payment successful -> WhatsApp confirmation sent
// Payment failed -> WhatsApp retry message sent
```

## Testing

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run specific test file
npm test src/mercadopago/client.test.js
```

## Security

- All webhook payloads are signature-verified
- API credentials are encrypted at rest
- Payment data is never stored locally
- HTTPS required for production webhooks
- Rate limiting applied to all endpoints

## Development

### Project Structure
```
src/
├── config/           # Configuration and logging
├── mercadopago/      # MercadoPago API integration
├── bird/            # Bird API integration
├── integration/     # Integration orchestration layer
├── utils/           # Shared utilities
└── server.js        # Express server setup
```

### Adding New Features

1. Create feature branch
2. Add comprehensive tests
3. Update documentation
4. Test with sandbox environments
5. Create pull request

## Monitoring

The application provides comprehensive logging:
- Payment events and status changes
- API call performance metrics
- Webhook processing results
- Error tracking and debugging info

Logs are structured JSON format suitable for log aggregation systems.

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
   - Verify Bird API credentials
   - Check WhatsApp channel configuration
   - Validate phone number format

## Support

For technical support or questions:
- Check the troubleshooting section
- Review logs for error details
- Contact the development team

## License

MIT License - See LICENSE file for details