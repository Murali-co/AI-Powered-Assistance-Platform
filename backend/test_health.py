import httpx
import asyncio

async def main():
    url = "http://localhost:11434/api/tags"
    print("Testing connection to:", url)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
            print("Status code:", response.status_code)
            print("Response length:", len(response.text))
    except Exception as e:
        print("Exception type:", type(e))
        print("Exception str:", str(e))
        print("Exception repr:", repr(e))

if __name__ == "__main__":
    asyncio.run(main())
