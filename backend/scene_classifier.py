import httpx
import json
import base64
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma3" # Fallback to "llava" if gemma3 is not available

SYSTEM_PROMPT = """
You are a trauma scene severity classifier for emergency medical dispatch.
Analyze the accident scene image and respond ONLY with a valid JSON object.
No explanation, no markdown, no extra text.
JSON schema:
{
  "severity": "HIGH" | "MEDIUM" | "LOW",
  "confidence": 0.0-1.0,
  "indicators": ["list", "of", "visual", "cues"],
  "reasoning": "one sentence"
}
HIGH = crushed vehicle, visible serious wounds, multi-vehicle crash, fire, entrapment
MEDIUM = deployed airbags, minor deformation, single vehicle, ambulatory patients
LOW = minor fender bender, no visible injuries, low-speed impact
"""

async def classify_scene(image_base64: str) -> dict:
    fallback = {
        "severity": "MEDIUM", 
        "confidence": 0.5, 
        "indicators": [], 
        "reasoning": "parse error fallback"
    }

    payload = {
        "model": MODEL_NAME,
        "prompt": SYSTEM_PROMPT,
        "images": [image_base64],
        "stream": False,
        "format": "json"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            
            result = response.json()
            # Ollama returns the generated text in the 'response' field
            content = result.get("response", "{}")
            return json.loads(content)
            
    except Exception as e:
        logger.error(f"Ollama Vision Error: {e}")
        return fallback
