"""Browser tool boundary; wire to an approved browser provider in production."""
from urllib.parse import urlparse
import httpx

async def fetch_public_url(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {"ok": False, "error": "Only http and https URLs are supported"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(url)
        return {"ok": response.is_success, "status_code": response.status_code, "text": response.text[:100_000]}
