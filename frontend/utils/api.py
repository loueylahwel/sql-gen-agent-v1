import requests

def query_api(base_url: str, question: str) -> dict:
    try:
        resp = requests.post(f"{base_url}/api/query", json={"question": question}, timeout=120)
        if resp.ok:
            return resp.json()
        return {"error": f"API error {resp.status_code}", "detail": resp.json().get("detail", resp.text)}
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot reach backend", "detail": f"Is FastAPI running at {base_url}?"}
    except Exception as e:
        return {"error": str(e)}

def fetch_schema(base_url: str) -> dict | None:
    try:
        resp = requests.get(f"{base_url}/api/schema", timeout=30)
        return resp.json() if resp.ok else None
    except Exception:
        return None

def check_health(base_url: str) -> dict:
    try:
        resp = requests.get(f"{base_url}/api/health/db", timeout=10)
        return resp.json() if resp.ok else {"clickhouse": "error"}
    except Exception:
        return {"clickhouse": "unreachable"}