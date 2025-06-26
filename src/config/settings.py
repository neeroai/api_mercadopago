"""
Configuration settings for MercadoPago-Bird API integration
Handles environment variables and AWS-specific configurations
"""

import os
from typing import Optional, List
from pydantic import BaseSettings, Field, validator
import boto3
from botocore.exceptions import ClientError


class Settings(BaseSettings):
    """Application settings with validation"""
    
    # Application Configuration
    app_name: str = Field(default="KOAJ MercadoPago-Bird Integration", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    environment: str = Field(default="development", env="ENVIRONMENT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # MercadoPago Configuration
    mercadopago_access_token: str = Field(..., env="MERCADOPAGO_ACCESS_TOKEN")
    mercadopago_public_key: Optional[str] = Field(None, env="MERCADOPAGO_PUBLIC_KEY")
    mercadopago_client_id: Optional[str] = Field(None, env="MERCADOPAGO_CLIENT_ID")
    mercadopago_client_secret: Optional[str] = Field(None, env="MERCADOPAGO_CLIENT_SECRET")
    mercadopago_webhook_secret: str = Field(..., env="MERCADOPAGO_WEBHOOK_SECRET")
    mercadopago_sandbox: bool = Field(default=True, env="MERCADOPAGO_SANDBOX")
    
    # Bird API Configuration
    bird_api_key: str = Field(..., env="BIRD_API_KEY")
    bird_api_secret: str = Field(..., env="BIRD_API_SECRET")
    bird_base_url: str = Field(default="https://api.bird.com", env="BIRD_BASE_URL")
    bird_workspace_id: str = Field(..., env="BIRD_WORKSPACE_ID")
    bird_channel_id: str = Field(..., env="BIRD_CHANNEL_ID")
    bird_webhook_secret: str = Field(..., env="BIRD_WEBHOOK_SECRET")
    
    # AWS Configuration
    aws_region: str = Field(default="us-east-2", env="AWS_DEFAULT_REGION")
    aws_access_key_id: Optional[str] = Field(None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(None, env="AWS_SECRET_ACCESS_KEY")
    
    # DynamoDB Tables
    payments_table_name: str = Field(default="koaj-payments", env="PAYMENTS_TABLE_NAME")
    conversations_table_name: str = Field(default="koaj-conversations", env="CONVERSATIONS_TABLE_NAME")
    webhooks_table_name: str = Field(default="koaj-webhooks", env="WEBHOOKS_TABLE_NAME")
    
    # SQS Queues
    payment_events_queue: str = Field(default="koaj-payment-events", env="PAYMENT_EVENTS_QUEUE")
    webhook_processing_queue: str = Field(default="koaj-webhook-processing", env="WEBHOOK_PROCESSING_QUEUE")
    
    # SNS Topics
    payment_notifications_topic: str = Field(default="koaj-payment-notifications", env="PAYMENT_NOTIFICATIONS_TOPIC")
    
    # Lambda Functions
    webhook_processor_function: str = Field(default="koaj-webhook-processor", env="WEBHOOK_PROCESSOR_FUNCTION")
    payment_processor_function: str = Field(default="koaj-payment-processor", env="PAYMENT_PROCESSOR_FUNCTION")
    
    # S3 Configuration
    assets_bucket: str = Field(default="koaj-integration-assets", env="ASSETS_BUCKET")
    logs_bucket: str = Field(default="koaj-integration-logs", env="LOGS_BUCKET")
    
    # Security
    jwt_secret: str = Field(..., env="JWT_SECRET")
    encryption_key: str = Field(..., env="ENCRYPTION_KEY")
    
    # API Gateway
    api_gateway_base_url: Optional[str] = Field(None, env="API_GATEWAY_BASE_URL")
    webhook_base_url: Optional[str] = Field(None, env="WEBHOOK_BASE_URL")
    
    # KOAJ Business Configuration
    koaj_catalog_id: str = Field(default="koaj-catalog", env="KOAJ_CATALOG_ID")
    koaj_brand_name: str = Field(default="KOAJ", env="KOAJ_BRAND_NAME")
    koaj_support_phone: str = Field(default="+573001234567", env="KOAJ_SUPPORT_PHONE")
    koaj_store_url: str = Field(default="https://koaj.co", env="KOAJ_STORE_URL")
    
    # Payment Configuration
    payment_expiration_minutes: int = Field(default=30, env="PAYMENT_EXPIRATION_MINUTES")
    max_retry_attempts: int = Field(default=3, env="MAX_RETRY_ATTEMPTS")
    retry_delay_seconds: int = Field(default=5, env="RETRY_DELAY_SECONDS")
    
    # Supported payment methods for Colombia
    supported_payment_methods: List[str] = Field(
        default=["visa", "master", "amex", "diners", "pse", "efecty", "baloto"],
        env="SUPPORTED_PAYMENT_METHODS"
    )
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        
    @validator("log_level")
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()
    
    @validator("supported_payment_methods", pre=True)
    def parse_payment_methods(cls, v):
        if isinstance(v, str):
            return [method.strip() for method in v.split(",")]
        return v
    
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"
    
    @property
    def mercadopago_base_url(self) -> str:
        return "https://api.mercadopago.com"
    
    @property
    def webhook_endpoints(self) -> dict:
        base_url = self.webhook_base_url or self.api_gateway_base_url
        if not base_url:
            return {}
        
        return {
            "mercadopago": f"{base_url}/webhooks/mercadopago",
            "bird": f"{base_url}/webhooks/bird"
        }


class AWSResources:
    """AWS service clients and resources"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._dynamodb = None
        self._sqs = None
        self._sns = None
        self._s3 = None
        self._lambda = None
        self._secrets_manager = None
    
    @property
    def dynamodb(self):
        if not self._dynamodb:
            self._dynamodb = boto3.resource(
                'dynamodb',
                region_name=self.settings.aws_region
            )
        return self._dynamodb
    
    @property
    def sqs(self):
        if not self._sqs:
            self._sqs = boto3.client(
                'sqs',
                region_name=self.settings.aws_region
            )
        return self._sqs
    
    @property
    def sns(self):
        if not self._sns:
            self._sns = boto3.client(
                'sns',
                region_name=self.settings.aws_region
            )
        return self._sns
    
    @property
    def s3(self):
        if not self._s3:
            self._s3 = boto3.client(
                's3',
                region_name=self.settings.aws_region
            )
        return self._s3
    
    @property
    def lambda_client(self):
        if not self._lambda:
            self._lambda = boto3.client(
                'lambda',
                region_name=self.settings.aws_region
            )
        return self._lambda
    
    @property
    def secrets_manager(self):
        if not self._secrets_manager:
            self._secrets_manager = boto3.client(
                'secretsmanager',
                region_name=self.settings.aws_region
            )
        return self._secrets_manager
    
    def get_secret(self, secret_name: str) -> str:
        """Retrieve secret from AWS Secrets Manager"""
        try:
            response = self.secrets_manager.get_secret_value(SecretId=secret_name)
            return response['SecretString']
        except ClientError as e:
            raise Exception(f"Failed to retrieve secret {secret_name}: {e}")
    
    def get_queue_url(self, queue_name: str) -> str:
        """Get SQS queue URL by name"""
        try:
            response = self.sqs.get_queue_url(QueueName=queue_name)
            return response['QueueUrl']
        except ClientError as e:
            raise Exception(f"Failed to get queue URL for {queue_name}: {e}")
    
    def get_topic_arn(self, topic_name: str) -> str:
        """Get SNS topic ARN by name"""
        try:
            response = self.sns.list_topics()
            for topic in response['Topics']:
                if topic['TopicArn'].endswith(f":{topic_name}"):
                    return topic['TopicArn']
            raise Exception(f"Topic {topic_name} not found")
        except ClientError as e:
            raise Exception(f"Failed to get topic ARN for {topic_name}: {e}")


# Global settings instance
settings = Settings()

# Global AWS resources instance
aws_resources = AWSResources(settings)


def get_settings() -> Settings:
    """Get application settings"""
    return settings


def get_aws_resources() -> AWSResources:
    """Get AWS resources"""
    return aws_resources


# Configuration validation
def validate_configuration():
    """Validate required configuration is present"""
    required_settings = [
        settings.mercadopago_access_token,
        settings.bird_api_key,
        settings.bird_api_secret,
        settings.jwt_secret,
        settings.encryption_key
    ]
    
    missing = [name for name, value in zip(
        ["MERCADOPAGO_ACCESS_TOKEN", "BIRD_API_KEY", "BIRD_API_SECRET", "JWT_SECRET", "ENCRYPTION_KEY"],
        required_settings
    ) if not value]
    
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    return True