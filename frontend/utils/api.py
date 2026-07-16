import requests

def query_api(base_url: str, question: str, source_id: str | None = None) -> dict:
    try:
        payload = {"question": question}
        if source_id:
            payload["source_id"] = source_id
        resp = requests.post(f"{base_url}/api/query", json=payload, timeout=120)
        if resp.ok:
            return resp.json()
        return {"error": f"API error {resp.status_code}", "detail": resp.json().get("detail", resp.text)}
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot reach backend", "detail": f"Is FastAPI running at {base_url}?"}
    except Exception as e:
        return {"error": str(e)}

def fetch_schema(base_url: str, source_id: str | None = None) -> dict | None:
    try:
        params = {"source_id": source_id} if source_id else None
        resp = requests.get(f"{base_url}/api/schema", params=params, timeout=30)
        return resp.json() if resp.ok else None
    except Exception:
        return None

def refresh_schema(base_url: str, source_id: str | None = None) -> bool:
    try:
        params = {"source_id": source_id} if source_id else None
        resp = requests.post(f"{base_url}/api/schema/refresh", params=params, timeout=30)
        return resp.ok
    except Exception:
        return False

def fetch_sources(base_url: str) -> list[dict]:
    try:
        resp = requests.get(f"{base_url}/api/sources", timeout=30)
        return resp.json() if resp.ok else []
    except Exception:
        return []

def upload_file(base_url: str, file_name: str, file_bytes: bytes, source_id: str | None = None) -> dict:
    try:
        data = {"source_id": source_id} if source_id else None
        resp = requests.post(
            f"{base_url}/api/sources/upload",
            files={"file": (file_name, file_bytes)},
            data=data,
            timeout=300,
        )
        if resp.ok:
            return resp.json()
        return {"error": f"API error {resp.status_code}", "detail": resp.json().get("detail", resp.text)}
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot reach backend", "detail": f"Is FastAPI running at {base_url}?"}
    except Exception as e:
        return {"error": str(e)}

def check_health(base_url: str) -> dict:
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        return resp.json() if resp.ok else {"status": "error"}
    except Exception:
        return {"status": "unreachable"}
