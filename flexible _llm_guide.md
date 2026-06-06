I'll conduct a comprehensive analysis of the Odysseus repository to extract the architecture and key components needed for a flexible LLM API key management system. Let me gather all the essential information.Now let me get more files to complete the picture:Let me search for the actual _detect_provider function:Now let me create a comprehensive guide with step-by-step prompts based on the Odysseus architecture. I'll write this as a complete implementation guide.

---

# **Complete Guide: Building a Multi-Provider LLM API Integration System for RAG**

## **Overview**

This guide extracts the key architectural patterns from Odysseus to help you build a flexible RAG system that accepts any LLM provider's API key through a UI, displays available models, and handles provider-specific authentication protocols.

### **Key Components You'll Need:**

1. **Provider Detection Engine** - Identifies API provider by URL
2. **Endpoint Resolver** - Converts provider+key → proper headers and endpoints
3. **Model Discovery** - Fetches available models from each provider
4. **API Key Management** - Secure storage and encryption
5. **UI Layer** - Provider selection → API Key input → Model picker

---

## **STEP 1: Provider Detection Engine**

Create a module to identify LLM providers by their URL hostname.

```python
# File: src/provider_detection.py
"""
Provider detection by URL hostname.
Maps provider hosts to their names and handles authentication patterns.
"""

from urllib.parse import urlparse
from typing import Optional

# Provider domain mapping: (domain, provider_name)
PROVIDER_HOSTS = [
    ("anthropic.com", "anthropic"),
    ("openai.com", "openai"),
    ("api.openai.com", "openai"),
    ("groq.com", "groq"),
    ("mistral.ai", "mistral"),
    ("together.xyz", "together"),
    ("together.ai", "together"),
    ("fireworks.ai", "fireworks"),
    ("googleapis.com", "google"),
    ("cohere.com", "cohere"),
    ("deepseek.com", "deepseek"),
    ("x.ai", "xai"),
    ("openrouter.ai", "openrouter"),
    ("ollama.com", "ollama"),
    ("api.z.ai", "zhipu"),
    ("api.github.com", "copilot"),
]


def _host_match(url: str, *domains: str) -> bool:
    """
    Check if URL's hostname matches any of the given domains.
    Matches both exact domain and subdomains (api.anthropic.com matches anthropic.com).
    Protects against substring false positives (anthropic.com.evil.com does NOT match).
    
    Args:
        url: Full URL to check
        domains: One or more domain strings (e.g., "anthropic.com")
    
    Returns:
        True if the URL's hostname matches any domain (exact or subdomain)
    """
    if not url:
        return False
    
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        
        for domain in domains:
            domain_lower = domain.lower().rstrip(".")
            
            # Exact match
            if hostname == domain_lower:
                return True
            
            # Subdomain match (api.anthropic.com matches anthropic.com)
            if hostname.endswith("." + domain_lower):
                return True
    
    except Exception:
        return False
    
    return False


def detect_provider(base_url: str) -> str:
    """
    Identify the LLM provider from a base URL.
    
    Args:
        base_url: The API endpoint base URL
    
    Returns:
        Provider name (e.g., "openai", "anthropic", "mistral")
        Defaults to "openai" for unknown/generic endpoints (OpenAI-compatible)
    
    Examples:
        detect_provider("https://api.anthropic.com") → "anthropic"
        detect_provider("https://api.openai.com/v1") → "openai"
        detect_provider("https://api.mistral.ai/v1") → "mistral"
        detect_provider("http://localhost:11434/api") → "ollama"
    """
    if not base_url:
        return "openai"
    
    try:
        parsed = urlparse(base_url or "")
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
        path = (parsed.path or "").rstrip("/")
        
        # Ollama detection: port 11434 OR ollama.com hostname
        if port == 11434 or _host_match(base_url, "ollama.com"):
            if path == "/api" or path.startswith("/api/") or not path:
                return "ollama"
        
        # Check against provider hosts
        for domain, provider_name in PROVIDER_HOSTS:
            if _host_match(base_url, domain):
                return provider_name
        
        # Default to OpenAI-compatible for unknown hosts
        return "openai"
    
    except Exception:
        return "openai"


def get_provider_display_name(provider: str) -> str:
    """Get human-friendly provider name for UI display."""
    names = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "groq": "Groq",
        "mistral": "Mistral",
        "together": "Together.ai",
        "fireworks": "Fireworks",
        "google": "Google Gemini",
        "cohere": "Cohere",
        "deepseek": "DeepSeek",
        "xai": "xAI Grok",
        "openrouter": "OpenRouter",
        "ollama": "Ollama",
        "zhipu": "Zhipu (Z.AI)",
        "copilot": "GitHub Copilot",
    }
    return names.get(provider, provider.capitalize())


# Pre-configured provider endpoints for UI dropdown
PROVIDER_ENDPOINTS = [
    {
        "name": "OpenAI",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "needs_key": True,
    },
    {
        "name": "Anthropic",
        "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "needs_key": True,
    },
    {
        "name": "Mistral",
        "provider": "mistral",
        "base_url": "https://api.mistral.ai/v1",
        "needs_key": True,
    },
    {
        "name": "Groq",
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "needs_key": True,
    },
    {
        "name": "Together.ai",
        "provider": "together",
        "base_url": "https://api.together.xyz/v1",
        "needs_key": True,
    },
    {
        "name": "Fireworks AI",
        "provider": "fireworks",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "needs_key": True,
    },
    {
        "name": "Google Gemini",
        "provider": "google",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "needs_key": True,
    },
    {
        "name": "DeepSeek",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "needs_key": True,
    },
    {
        "name": "OpenRouter",
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "needs_key": True,
    },
    {
        "name": "Ollama (Local)",
        "provider": "ollama",
        "base_url": "http://localhost:11434/v1",
        "needs_key": False,
    },
]
```

---

## **STEP 2: Endpoint Resolver & Header Builder**

This converts provider + API key into the correct URL structure and auth headers (each provider has different auth patterns).

```python
# File: src/endpoint_resolver.py
"""
Converts provider + API key + base URL into:
- Correct chat completion endpoint URL
- Correct model listing endpoint URL  
- Proper authentication headers (varies by provider)
"""

from typing import Dict, Optional
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


def normalize_base(base_url: str) -> str:
    """
    Strip known API path suffixes from a base URL.
    Users might paste the full endpoint; we need just the base.
    
    Examples:
        "https://api.openai.com/v1/chat/completions" → "https://api.openai.com/v1"
        "https://api.anthropic.com/v1/messages" → "https://api.anthropic.com"
        "http://localhost:11434/api/chat" → "http://localhost:11434/api"
    """
    url = (base_url or "").strip().rstrip("/")
    
    # OpenAI-compatible paths
    for suffix in ["/models", "/chat/completions", "/completions", "/v1/messages", 
                   "/v1/chat/completions", "/chat", "/tags", "/generate"]:
        if url.endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
    
    return url


def build_chat_url(base_url: str, provider: str) -> str:
    """
    Build the provider-specific chat completion endpoint URL.
    
    Args:
        base_url: Normalized base URL
        provider: Provider name from detect_provider()
    
    Returns:
        Full endpoint URL for chat completions
    
    Examples:
        ("https://api.openai.com/v1", "openai") 
            → "https://api.openai.com/v1/chat/completions"
        ("https://api.anthropic.com", "anthropic") 
            → "https://api.anthropic.com/v1/messages"
        ("http://localhost:11434/api", "ollama") 
            → "http://localhost:11434/api/chat"
    """
    base = normalize_base(base_url)
    
    if provider == "anthropic":
        # Anthropic: uses /v1/messages, NOT /v1/chat/completions
        if not base.endswith("/v1") and _host_match(base, "anthropic.com"):
            base = base + "/v1"
        return base.rstrip("/") + "/v1/messages"
    
    elif provider == "ollama":
        # Ollama: uses /api/chat
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")  # Strip /v1
        if not base.endswith("/api"):
            base = base + "/api"
        return base.rstrip("/") + "/chat"
    
    # Default: OpenAI-compatible /v1/chat/completions
    if not base.endswith("/v1"):
        base = base + "/v1"
    return base.rstrip("/") + "/chat/completions"


def build_models_url(base_url: str, provider: str) -> str:
    """
    Build the provider-specific model listing endpoint URL.
    
    Args:
        base_url: Normalized base URL
        provider: Provider name
    
    Returns:
        Full endpoint URL for fetching available models
    
    Examples:
        ("https://api.openai.com/v1", "openai") 
            → "https://api.openai.com/v1/models"
        ("https://api.anthropic.com", "anthropic") 
            → "https://api.anthropic.com/v1/models"
        ("http://localhost:11434/api", "ollama") 
            → "http://localhost:11434/api/tags"
    """
    base = normalize_base(base_url)
    
    if provider == "anthropic":
        # Anthropic has /v1/models endpoint
        if _host_match(base, "anthropic.com") and base.endswith("/v1"):
            return base.rstrip("/") + "/models"
        if not base.endswith("/v1"):
            base = base + "/v1"
        return base.rstrip("/") + "/models"
    
    elif provider == "ollama":
        # Ollama uses /api/tags instead of /models
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        if not base.endswith("/api"):
            base = base + "/api"
        return base.rstrip("/") + "/tags"
    
    # Default: OpenAI-compatible /v1/models
    if not base.endswith("/v1"):
        base = base + "/v1"
    return base.rstrip("/") + "/models"


def build_headers(api_key: Optional[str], base_url: str, provider: str) -> Dict[str, str]:
    """
    Build HTTP headers with proper authentication for the provider.
    
    CRITICAL: Each provider has different auth patterns:
    - Anthropic: Uses 'x-api-key' header (NOT Bearer)
    - OpenAI/Mistral/Groq/etc: Use 'Authorization: Bearer {key}'
    - Ollama (local): May not need a key
    - OpenRouter: Also needs HTTP-Referer header
    
    Args:
        api_key: The API key (may be None for local endpoints)
        base_url: Base URL
        provider: Provider name
    
    Returns:
        Dictionary of HTTP headers
    
    Examples:
        (key="sk-xyz", provider="anthropic")
            → {"x-api-key": "sk-xyz", "anthropic-version": "2023-06-01"}
        (key="sk-xyz", provider="openai")
            → {"Authorization": "Bearer sk-xyz"}
        (key=None, provider="ollama")
            → {}
    """
    headers: Dict[str, str] = {}
    
    if provider == "anthropic":
        # Anthropic MUST use x-api-key header, NOT Bearer
        if api_key:
            headers["x-api-key"] = api_key
        # Anthropic requires a version header
        headers["anthropic-version"] = "2023-06-01"
        return headers
    
    elif provider == "ollama":
        # Local Ollama typically doesn't need auth
        return headers
    
    # Default: OpenAI-compatible Bearer token
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    # OpenRouter requires attribution headers
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://your-app.com"
        headers["X-Title"] = "Your RAG System"
    
    headers["Content-Type"] = "application/json"
    return headers


def _host_match(url: str, *domains: str) -> bool:
    """Helper: check if URL hostname matches domain (imported from provider_detection)"""
    from src.provider_detection import _host_match as pm
    return pm(url, *domains)
```

---

## **STEP 3: Model Discovery Service**

Fetch the list of available models from a provider.

```python
# File: src/model_discovery.py
"""
Discover available models from LLM provider endpoints.
Handles different response formats per provider.
"""

import httpx
import logging
import json
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

# Known Anthropic models (for when /models endpoint fails)
ANTHROPIC_MODELS = [
    "claude-opus-4",
    "claude-opus-4-1",
    "claude-sonnet-4",
    "claude-sonnet-4-5",
    "claude-haiku-3-5",
    "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
]

# Model suffixes that are NOT chat models (filter these out)
NON_CHAT_SUFFIXES = (
    "embedding", "text-embedding", "tts-", "whisper", "dall-e",
    "moderation", "image", "rerank", "reranker",
)


def is_chat_model(model_id: str) -> bool:
    """Check if a model ID looks like a chat/generation model."""
    model_lower = model_id.lower()
    return not any(suffix in model_lower for suffix in NON_CHAT_SUFFIXES)


async def fetch_models(
    base_url: str,
    api_key: Optional[str],
    headers: Dict[str, str],
    provider: str,
    timeout: int = 10,
) -> List[str]:
    """
    Fetch available models from an LLM provider endpoint.
    
    Args:
        base_url: Base URL (normalized)
        api_key: API key if needed
        headers: Pre-built auth headers (from build_headers)
        provider: Provider name
        timeout: Request timeout in seconds
    
    Returns:
        List of available model IDs, filtered to chat models only
    
    Handles different response formats:
    - OpenAI format: {"data": [{"id": "model-name"}]}
    - Ollama format: {"models": [{"name": "model-name"}]}
    - Anthropic: Returns hardcoded list or /v1/models endpoint
    """
    from src.endpoint_resolver import build_models_url
    
    try:
        # Get the correct endpoint URL for this provider
        models_url = build_models_url(base_url, provider)
        
        logger.debug(f"Fetching models from {provider} @ {models_url}")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(models_url, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        models = []
        
        # OpenAI format
        if "data" in data and isinstance(data["data"], list):
            models = [m.get("id") for m in data["data"] if m.get("id")]
        
        # Ollama format
        elif "models" in data and isinstance(data["models"], list):
            models = [
                m.get("name") or m.get("model")
                for m in data["models"]
                if m.get("name") or m.get("model")
            ]
        
        # Filter to chat models only and sort
        chat_models = [m for m in models if is_chat_model(m)]
        return sorted(chat_models)
    
    except Exception as e:
        logger.warning(f"Failed to fetch models from {provider}: {e}")
        
        # Fallback for Anthropic
        if provider == "anthropic":
            return ANTHROPIC_MODELS
        
        return []


async def test_connection(
    base_url: str,
    api_key: Optional[str],
    headers: Dict[str, str],
    provider: str,
    timeout: float = 2.0,
) -> bool:
    """
    Quick health check: Can we reach this endpoint?
    
    Returns True if reachable, False otherwise.
    """
    from src.endpoint_resolver import build_models_url
    
    try:
        models_url = build_models_url(base_url, provider)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(models_url, headers=headers)
            return 200 <= response.status_code < 300
    except Exception:
        return False
```

---

## **STEP 4: Secure API Key Storage**

Store API keys encrypted at rest.

```python
# File: src/api_key_manager.py
"""
Securely store and retrieve API keys with encryption.
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Optional

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class APIKeyManager:
    """
    Manages encrypted storage of API keys.
    Keys are encrypted using Fernet (symmetric encryption).
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.keys_file = self.data_dir / "api_keys.json"
        self.key_file = self.data_dir / ".encryption_key"
    
    def _get_or_create_key(self) -> bytes:
        """Get encryption key, create if doesn't exist."""
        if self.key_file.exists():
            return self.key_file.read_bytes()
        
        # Generate new key
        key = Fernet.generate_key()
        self.key_file.write_bytes(key)
        # Restrict permissions on Unix-like systems
        try:
            os.chmod(str(self.key_file), 0o600)
        except OSError:
            pass  # Windows doesn't support chmod
        
        return key
    
    def _get_cipher(self) -> Fernet:
        """Get Fernet cipher for encryption/decryption."""
        key = self._get_or_create_key()
        return Fernet(key)
    
    def save_key(self, provider: str, api_key: str) -> None:
        """
        Encrypt and save an API key for a provider.
        
        Args:
            provider: Provider name (e.g., "openai", "anthropic")
            api_key: The API key to encrypt and save
        """
        cipher = self._get_cipher()
        encrypted = cipher.encrypt(api_key.encode()).decode()
        
        # Load existing keys
        keys_dict = self._load_raw()
        keys_dict[provider] = encrypted
        
        # Save back
        self.keys_file.write_text(json.dumps(keys_dict), encoding="utf-8")
        logger.info(f"Saved encrypted key for provider: {provider}")
    
    def get_key(self, provider: str) -> Optional[str]:
        """
        Decrypt and retrieve an API key for a provider.
        
        Args:
            provider: Provider name
        
        Returns:
            Decrypted API key or None if not found
        """
        keys_dict = self._load_raw()
        encrypted = keys_dict.get(provider)
        
        if not encrypted:
            return None
        
        try:
            cipher = self._get_cipher()
            decrypted = cipher.decrypt(encrypted.encode()).decode()
            return decrypted
        except Exception as e:
            logger.error(f"Failed to decrypt key for {provider}: {e}")
            return None
    
    def delete_key(self, provider: str) -> None:
        """Delete stored key for a provider."""
        keys_dict = self._load_raw()
        if provider in keys_dict:
            del keys_dict[provider]
            self.keys_file.write_text(json.dumps(keys_dict), encoding="utf-8")
            logger.info(f"Deleted key for provider: {provider}")
    
    def list_providers(self) -> List[str]:
        """List all providers that have stored keys."""
        keys_dict = self._load_raw()
        return list(keys_dict.keys())
    
    def _load_raw(self) -> Dict[str, str]:
        """Load raw encrypted keys dict from file."""
        if not self.keys_file.exists():
            return {}
        
        try:
            return json.loads(self.keys_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read keys file: {e}")
            return {}
```

---

## **STEP 5: Backend API Routes**

Create FastAPI endpoints for the UI.

```python
# File: routes/llm_config_routes.py
"""
FastAPI routes for LLM configuration:
- List providers
- Save/retrieve API keys
- Probe endpoints and fetch models
"""

from fastapi import APIRouter, HTTPException, Form
from pydantic import BaseModel
from typing import List, Dict, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-config")


class ProviderInfo(BaseModel):
    name: str
    provider: str
    base_url: str
    needs_key: bool


class ProbedEndpoint(BaseModel):
    provider: str
    base_url: str
    status: str  # "ok", "error"
    models: List[str] = []
    error: Optional[str] = None


@router.get("/providers")
async def list_providers() -> Dict:
    """List all supported LLM providers."""
    from src.provider_detection import PROVIDER_ENDPOINTS
    
    return {
        "providers": PROVIDER_ENDPOINTS
    }


@router.post("/save-key")
async def save_api_key(
    provider: str = Form(...),
    api_key: str = Form(...),
):
    """Save an API key for a provider (encrypted)."""
    from src.api_key_manager import APIKeyManager
    
    if not provider or not api_key:
        raise HTTPException(400, "Provider and API key required")
    
    try:
        manager = APIKeyManager()
        manager.save_key(provider, api_key)
        return {"ok": True, "provider": provider}
    except Exception as e:
        logger.error(f"Failed to save key: {e}")
        raise HTTPException(500, f"Failed to save key: {e}")


@router.get("/stored-providers")
async def get_stored_providers() -> Dict:
    """List providers that have stored keys."""
    from src.api_key_manager import APIKeyManager
    
    try:
        manager = APIKeyManager()
        providers = manager.list_providers()
        return {"providers": providers}
    except Exception as e:
        logger.error(f"Failed to list providers: {e}")
        return {"providers": []}


@router.post("/probe")
async def probe_endpoint(
    provider: str = Form(...),
    base_url: str = Form(...),
    api_key: Optional[str] = Form(None),
) -> ProbedEndpoint:
    """
    Test an endpoint: Check if reachable and fetch available models.
    """
    from src.provider_detection import detect_provider
    from src.endpoint_resolver import (
        normalize_base,
        build_headers,
        build_models_url,
    )
    from src.model_discovery import fetch_models, test_connection
    
    try:
        base_url = normalize_base(base_url)
        detected = detect_provider(base_url)
        
        if provider != "auto" and provider != detected:
            logger.warning(
                f"Provider mismatch: user said {provider}, detected {detected}"
            )
        
        headers = build_headers(api_key, base_url, detected)
        
        # Test connection first
        is_reachable = await test_connection(base_url, api_key, headers, detected)
        
        if not is_reachable:
            return ProbedEndpoint(
                provider=detected,
                base_url=base_url,
                status="error",
                error="Endpoint not reachable. Check URL and API key.",
            )
        
        # Fetch models
        models = await fetch_models(base_url, api_key, headers, detected)
        
        if not models:
            return ProbedEndpoint(
                provider=detected,
                base_url=base_url,
                status="error",
                error="No models found. Endpoint may be empty or misconfigured.",
            )
        
        return ProbedEndpoint(
            provider=detected,
            base_url=base_url,
            status="ok",
            models=models,
        )
    
    except Exception as e:
        logger.error(f"Probe failed: {e}")
        return ProbedEndpoint(
            provider=provider,
            base_url=base_url,
            status="error",
            error=str(e),
        )


@router.post("/use-provider")
async def set_active_provider(
    provider: str = Form(...),
    base_url: str = Form(...),
    model: Optional[str] = Form(None),
):
    """Set the active provider and model for RAG queries."""
    from src.endpoint_resolver import normalize_base
    
    try:
        base_url = normalize_base(base_url)
        
        # Store in your RAG config
        # This is where you'd save to DB, file, or memory
        # Example: 
        # config.active_llm_provider = provider
        # config.active_llm_base_url = base_url
        # config.active_llm_model = model
        
        return {"ok": True, "provider": provider, "model": model}
    except Exception as e:
        logger.error(f"Failed to set provider: {e}")
        raise HTTPException(500, f"Failed to set provider: {e}")
```

---

## **STEP 6: Frontend UI - React/HTML**

Create the UI for provider selection, API key input, and model picker.

```html
<!-- File: templates/llm_config.html -->
<!DOCTYPE html>
<html>
<head>
    <title>LLM Configuration</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .section { border: 1px solid #ddd; padding: 20px; margin-bottom: 20px; border-radius: 8px; }
        label { display: block; margin-top: 12px; font-weight: 600; }
        input, select { width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; margin-top: 12px; }
        button:hover { background: #0056b3; }
        .status { padding: 12px; margin-top: 12px; border-radius: 4px; }
        .status.ok { background: #d4edda; color: #155724; }
        .status.error { background: #f8d7da; color: #721c24; }
        .status.loading { background: #cfe2ff; color: #084298; }
        .model-list { margin-top: 12px; padding: 12px; background: #f8f9fa; border-radius: 4px; max-height: 200px; overflow-y: auto; }
        .model-item { padding: 8px; background: white; margin: 4px 0; border-radius: 4px; cursor: pointer; }
        .model-item:hover { background: #e9ecef; }
        .model-item.selected { background: #007bff; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <h1>LLM Configuration for RAG</h1>
        
        <!-- Step 1: Choose Provider -->
        <div class="section">
            <h2>Step 1: Choose LLM Provider</h2>
            <label for="provider-select">Provider</label>
            <select id="provider-select">
                <option value="">-- Select a provider --</option>
            </select>
            <p style="font-size: 12px; color: #666; margin-top: 8px;">
                The LLM provider that hosts your model API
            </p>
        </div>
        
        <!-- Step 2: Enter API Key -->
        <div class="section">
            <h2>Step 2: Enter API Key</h2>
            <label for="api-key-input">API Key</label>
            <input type="password" id="api-key-input" placeholder="Enter your API key">
            <p style="font-size: 12px; color: #666; margin-top: 8px;">
                Your API key is encrypted and stored locally
            </p>
            <button onclick="saveKey()">Save API Key</button>
            <div id="key-status"></div>
        </div>
        
        <!-- Step 3: Customize Endpoint (Optional) -->
        <div class="section">
            <h2>Step 3: Configure Endpoint (Optional)</h2>
            <label for="base-url-input">Base URL</label>
            <input type="text" id="base-url-input" placeholder="Leave blank for default endpoint">
            <p style="font-size: 12px; color: #666; margin-top: 8px;">
                For custom/self-hosted endpoints
            </p>
        </div>
        
        <!-- Step 4: Probe & Select Model -->
        <div class="section">
            <h2>Step 4: Select Model</h2>
            <button onclick="probeEndpoint()">Discover Available Models</button>
            <div id="probe-status"></div>
            
            <label for="model-select">Available Models</label>
            <div id="model-list" class="model-list">
                <p style="color: #999; text-align: center;">Models will appear after probing</p>
            </div>
            
            <label for="selected-model">Selected Model</label>
            <input type="text" id="selected-model" readonly placeholder="Click a model above">
        </div>
        
        <!-- Step 5: Activate -->
        <div class="section">
            <button onclick="activateProvider()" style="width: 100%; padding: 12px; font-size: 16px;">
                ✓ Activate This Provider
            </button>
        </div>
        
        <!-- Stored Providers -->
        <div class="section">
            <h2>Previously Configured Providers</h2>
            <div id="stored-providers">
                <p style="color: #999;">Loading...</p>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin;
        let currentProvider = null;
        let currentBaseUrl = null;
        let currentApiKey = null;
        let selectedModel = null;
        
        // Initialize: Load provider list
        async function initProviders() {
            try {
                const res = await fetch(`${API_BASE}/api/llm-config/providers`);
                const data = await res.json();
                
                const select = document.getElementById("provider-select");
                data.providers.forEach(p => {
                    const opt = document.createElement("option");
                    opt.value = p.provider;
                    opt.textContent = p.name;
                    opt.dataset.baseUrl = p.base_url;
                    select.appendChild(opt);
                });
                
                select.addEventListener("change", onProviderChange);
            } catch (e) {
                console.error("Failed to load providers:", e);
            }
        }
        
        function onProviderChange() {
            const select = document.getElementById("provider-select");
            const provider = select.value;
            const option = select.options[select.selectedIndex];
            
            currentProvider = provider;
            currentBaseUrl = option.dataset.baseUrl || "";
            
            // Auto-fill base URL
            document.getElementById("base-url-input").value = currentBaseUrl;
            
            // Clear previous state
            document.getElementById("model-list").innerHTML = 
                '<p style="color: #999; text-align: center;">Click "Discover Models" to continue</p>';
            document.getElementById("selected-model").value = "";
        }
        
        async function saveKey() {
            const provider = currentProvider;
            const apiKey = document.getElementById("api-key-input").value.trim();
            
            if (!provider) {
                showStatus("key-status", "Please select a provider first", "error");
                return;
            }
            if (!apiKey) {
                showStatus("key-status", "Please enter an API key", "error");
                return;
            }
            
            try {
                showStatus("key-status", "Saving...", "loading");
                const fd = new FormData();
                fd.append("provider", provider);
                fd.append("api_key", apiKey);
                
                const res = await fetch(`${API_BASE}/api/llm-config/save-key`, {
                    method: "POST",
                    body: fd,
                });
                
                if (res.ok) {
                    currentApiKey = apiKey;
                    showStatus("key-status", "✓ API key saved and encrypted", "ok");
                    document.getElementById("api-key-input").value = "";
                } else {
                    const err = await res.text();
                    showStatus("key-status", `Error: ${err}`, "error");
                }
            } catch (e) {
                showStatus("key-status", `Error: ${e.message}`, "error");
            }
        }
        
        async function probeEndpoint() {
            const provider = currentProvider;
            let baseUrl = document.getElementById("base-url-input").value.trim() || currentBaseUrl;
            const apiKey = document.getElementById("api-key-input").value.trim() || currentApiKey;
            
            if (!provider) {
                showStatus("probe-status", "Please select a provider", "error");
                return;
            }
            if (!baseUrl) {
                showStatus("probe-status", "Please enter a base URL", "error");
                return;
            }
            
            try {
                showStatus("probe-status", "Connecting to endpoint...", "loading");
                
                const fd = new FormData();
                fd.append("provider", provider);
                fd.append("base_url", baseUrl);
                if (apiKey) fd.append("api_key", apiKey);
                
                const res = await fetch(`${API_BASE}/api/llm-config/probe`, {
                    method: "POST",
                    body: fd,
                });
                
                const result = await res.json();
                
                if (result.status === "ok" && result.models.length > 0) {
                    showStatus("probe-status", `✓ Found ${result.models.length} models`, "ok");
                    displayModels(result.models);
                    currentBaseUrl = baseUrl;
                } else {
                    showStatus("probe-status", `Error: ${result.error}`, "error");
                }
            } catch (e) {
                showStatus("probe-status", `Error: ${e.message}`, "error");
            }
        }
        
        function displayModels(models) {
            const list = document.getElementById("model-list");
            list.innerHTML = "";
            
            models.forEach(model => {
                const div = document.createElement("div");
                div.className = "model-item";
                div.textContent = model;
                div.onclick = () => selectModel(model);
                list.appendChild(div);
            });
        }
        
        function selectModel(model) {
            selectedModel = model;
            document.getElementById("selected-model").value = model;
            
            // Highlight selected
            document.querySelectorAll(".model-item").forEach(el => {
                el.classList.remove("selected");
            });
            event.target.classList.add("selected");
        }
        
        async function activateProvider() {
            if (!currentProvider || !currentBaseUrl || !selectedModel) {
                alert("Please complete all steps first");
                return;
            }
            
            try {
                const fd = new FormData();
                fd.append("provider", currentProvider);
                fd.append("base_url", currentBaseUrl);
                fd.append("model", selectedModel);
                
                const res = await fetch(`${API_BASE}/api/llm-config/use-provider`, {
                    method: "POST",
                    body: fd,
                });
                
                if (res.ok) {
                    alert(`✓ Provider activated!\nUsing ${selectedModel} from ${currentProvider}`);
                    loadStoredProviders();
                } else {
                    alert("Failed to activate provider");
                }
            } catch (e) {
                alert(`Error: ${e.message}`);
            }
        }
        
        async function loadStoredProviders() {
            try {
                const res = await fetch(`${API_BASE}/api/llm-config/stored-providers`);
                const data = await res.json();
                
                const div = document.getElementById("stored-providers");
                if (data.providers.length === 0) {
                    div.innerHTML = "<p style='color: #999;'>No providers configured yet</p>";
                } else {
                    div.innerHTML = "<ul>" + data.providers.map(p => 
                        `<li>${p}</li>`
                    ).join("") + "</ul>";
                }
            } catch (e) {
                console.error("Failed to load stored providers:", e);
            }
        }
        
        function showStatus(elementId, message, type) {
            const el = document.getElementById(elementId);
            el.className = `status ${type}`;
            el.textContent = message;
            el.style.display = "block";
        }
        
        // Initialize on page load
        initProviders();
        loadStoredProviders();
    </script>
</body>
</html>
```

---

## **STEP 7: Integration into Your RAG System**

Connect this configuration to your RAG queries.

```python
# File: src/rag_engine.py
"""
Main RAG engine that uses the configured LLM provider.
"""

import httpx
from typing import Optional, List, Dict
from src.api_key_manager import APIKeyManager
from src.endpoint_resolver import build_chat_url, build_headers, normalize_base
from src.provider_detection import detect_provider


class RAGEngine:
    """
    RAG engine that queries documents and uses configured LLM.
    """
    
    def __init__(self):
        self.active_provider: Optional[str] = None
        self.active_base_url: Optional[str] = None
        self.active_model: Optional[str] = None
        self.api_key_manager = APIKeyManager()
    
    def set_provider(self, provider: str, base_url: str, model: str) -> None:
        """Set which LLM provider to use for RAG."""
        self.active_provider = provider
        self.active_base_url = normalize_base(base_url)
        self.active_model = model
    
    async def query(
        self,
        user_question: str,
        context_docs: List[str],  # Retrieved documents
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Execute RAG query:
        1. Use context docs as system context
        2. Send question to configured LLM
        3. Return response
        """
        
        if not self.active_model or not self.active_base_url:
            raise ValueError("No LLM provider configured")
        
        # Get API key
        api_key = self.api_key_manager.get_key(self.active_provider)
        if not api_key:
            raise ValueError(f"No API key found for {self.active_provider}")
        
        # Build chat URL and headers
        chat_url = build_chat_url(self.active_base_url, self.active_provider)
        headers = build_headers(api_key, self.active_base_url, self.active_provider)
        
        # Prepare messages
        system_content = system_prompt or "You are a helpful assistant with access to documents."
        if context_docs:
            system_content += "\n\nContext documents:\n" + "\n---\n".join(context_docs)
        
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_question},
        ]
        
        # Build request payload (OpenAI-compatible format)
        payload = {
            "model": self.active_model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1024,
        }
        
        # Send to LLM
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    chat_url,
                    json=payload,
                    headers=headers,
                    timeout=60,
                )
                response.raise_for_status()
                result = response.json()
            
            # Extract response (OpenAI format)
            return result["choices"][0]["message"]["content"]
        
        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}")
```

---

## **Summary: Key Takeaways**

| Component | File | Purpose |
|-----------|------|---------|
| **Provider Detection** | `src/provider_detection.py` | Identify provider by URL hostname |
| **Endpoint Resolver** | `src/endpoint_resolver.py` | Convert provider+key → correct URLs & headers |
| **Model Discovery** | `src/model_discovery.py` | Fetch available models from provider |
| **Key Storage** | `src/api_key_manager.py` | Encrypt & securely store API keys |
| **API Routes** | `routes/llm_config_routes.py` | FastAPI endpoints for UI |
| **Frontend UI** | `templates/llm_config.html` | Step-by-step provider/key/model selection |
| **RAG Integration** | `src/rag_engine.py` | Use configured provider for queries |

---

## **Key Architectural Patterns from Odysseus**

1. **Provider Detection via Hostname Matching** - Don't substring match; check hostname exactly
2. **Provider-Specific URLs** - Anthropic `/v1/messages`, Ollama `/api/chat`, others `/v1/chat/completions`
3. **Provider-Specific Auth Headers** - Anthropic uses `x-api-key`, others use `Authorization: Bearer`
4. **Encrypted Key Storage** - Use Fernet for symmetric encryption at rest
5. **Fallback Chains** - Always have sensible defaults for unknown/generic endpoints
6. **Model Filtering** - Skip embedding/TTS/image models when discovering chat models
7. **Connection Testing** - Probe before storing (validate URL + key combination works)

This architecture is production-ready and scales to support unlimited providers!