import asyncio
import os
import sys

# Add the backend directory to sys.path so we can import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.llm.ollama_client import OllamaClient


def test_connection():
    print("Settings:")
    print("OLLAMA_BASE_URL:", settings.OLLAMA_BASE_URL)
    print("OLLAMA_MODEL:", settings.OLLAMA_MODEL)
    print("LLM_PROVIDER:", settings.LLM_PROVIDER)

    async def run_check():
        try:
            print("\nSending 'hi' to Ollama...")
            response = await OllamaClient.generate("hi")
            print("Response received successfully:")
            print(response)
        except Exception as e:
            print("\nConnection failed with exception:")
            import traceback
            traceback.print_exc()
            raise

    asyncio.run(run_check())


if __name__ == "__main__":
    test_connection()
