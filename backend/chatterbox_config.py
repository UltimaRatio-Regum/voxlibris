"""
Configuration for Chatterbox TTS paid API.
Update these settings when using a custom Chatterbox endpoint.
"""
import os

# Chatterbox Paid API Configuration
CHATTERBOX_PAID_CONFIG = {
    # API endpoint URL for the paid Chatterbox service
    # Example: "https://your-chatterbox-api.com/generate"
    "api_url": os.environ.get("CHATTERBOX_API_URL", ""),
    
    # API key for authentication
    "api_key": os.environ.get("CHATTERBOX_API_KEY", ""),
    
    # Request timeout in seconds
    "timeout": int(os.environ.get("CHATTERBOX_TIMEOUT", "120")),
    
    # Maximum characters per request (0 = no limit)
    "max_chars": int(os.environ.get("CHATTERBOX_MAX_CHARS", "0")),
    
    # Default parameters
    "default_exaggeration": 0.5,
    "default_temperature": 0.8,
    "default_cfg_weight": 0.5,
}

# Free HuggingFace Spaces configuration
CHATTERBOX_FREE_CONFIG = {
    # HuggingFace Spaces endpoint
    "space_id": "ResembleAI/Chatterbox",
    
    # Character limit for free tier
    "max_chars": 300,
    
    # Default parameters
    "default_exaggeration": 0.5,
    "default_temperature": 0.8,
    "default_cfg_weight": 0.5,
}


def is_paid_chatterbox_configured() -> bool:
    """Check if paid Chatterbox API is properly configured."""
    return bool(CHATTERBOX_PAID_CONFIG["api_url"] and CHATTERBOX_PAID_CONFIG["api_key"])


def get_chatterbox_config(use_paid: bool = False) -> dict:
    """Get the appropriate Chatterbox configuration."""
    if use_paid:
        return CHATTERBOX_PAID_CONFIG
    return CHATTERBOX_FREE_CONFIG
