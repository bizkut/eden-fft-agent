"""
LLM Client with OpenAI-compatible endpoint support.
Works with: OpenAI, Azure OpenAI, Ollama, LM Studio, vLLM, etc.
"""
import os
from dataclasses import dataclass
from typing import Optional
import json

try:
    import httpx
except ImportError:
    httpx = None


@dataclass
class LLMConfig:
    base_url: str = "http://localhost:11434/v1"  # Default: Ollama
    api_key: str = "ollama"  # Some servers require any non-empty key
    model: str = "llama3"
    temperature: float = 0.7
    max_tokens: int = 500


class LLMClient:
    """
    OpenAI-compatible LLM client.
    
    Works with any server exposing /v1/chat/completions endpoint:
    - OpenAI: base_url="https://api.openai.com/v1"
    - Ollama: base_url="http://localhost:11434/v1"
    - LM Studio: base_url="http://localhost:1234/v1"
    - vLLM: base_url="http://localhost:8000/v1"
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        if httpx is None:
            raise ImportError("httpx required: pip install httpx")
        
        self.config = config or LLMConfig()
        self.client = httpx.Client(timeout=60.0)
        
    def chat(self, prompt: str, system_prompt: Optional[str] = None, image_data: Optional[str] = None) -> str:
        """
        Send chat request.
        image_data: Base64 encoded image string (optional)
        """
        import time
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        if image_data:
            # Multimodal request
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
            ]
            messages.append({"role": "user", "content": content})
        else:
            # Text-only request
            messages.append({"role": "user", "content": prompt})
        
        max_retries = 3
        base_delay = 2.0
        
        for attempt in range(max_retries + 1):
            try:
                response = self.client.post(
                    f"{self.config.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.config.model,
                        "messages": messages,
                        "temperature": self.config.temperature,
                        "max_tokens": self.config.max_tokens,
                    },
                )
                
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        print(f"Warning: Rate limited (429). Retrying in {delay}s...")
                        time.sleep(delay)
                        continue
    def chat_with_images(self, prompt: str, images: list, system_prompt: Optional[str] = None) -> str:
        """
        Send chat request with multiple images.
        images: List of base64 encoded image strings
        """
        import time
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Build content with multiple images
        content = [{"type": "text", "text": prompt}]
        for img_b64 in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })
        
        messages.append({"role": "user", "content": content})
        
        max_retries = 3
        base_delay = 2.0
        
        for attempt in range(max_retries + 1):
            try:
                response = self.client.post(
                    f"{self.config.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.config.model,
                        "messages": messages,
                        "temperature": self.config.temperature,
                        "max_tokens": self.config.max_tokens,
                    },
                )
                
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        print(f"Warning: Rate limited (429). Retrying in {delay}s...")
                        time.sleep(delay)
                        continue
                raise
    
    def close(self):
        self.client.close()


# Convenience function
def create_client_from_env() -> LLMClient:
    """Create client from environment variables."""
    config = LLMConfig(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "ollama"),
        model=os.getenv("LLM_MODEL", "llama3"),
    )
    return LLMClient(config)


if __name__ == "__main__":
    # Test with local Ollama
    client = LLMClient()
    response = client.chat("Say 'Hello FFT!' in 5 words or less.")
    print(f"LLM Response: {response}")
    client.close()
