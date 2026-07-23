import json
import httpx
from typing import Optional, Dict, Any


class LlmClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def chat(self, messages: list[dict], temperature: float = 0.1) -> Optional[str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return None

    def extract_json(self, messages: list[dict]) -> Optional[Dict[str, Any]]:
        content = self.chat(messages, temperature=0.1)
        if content is None:
            return None

        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                return json.loads(content[json_start:json_end])
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    @classmethod
    def from_config(cls, config: dict) -> "LlmClient":
        return cls(
            base_url=config.get("base_url", "http://localhost:11434/v1"),
            api_key=config.get("api_key", ""),
            model=config.get("model", "qwen2.5:7b"),
        )
