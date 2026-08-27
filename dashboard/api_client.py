import os
from typing import Any
import requests


class APIClientError(Exception):
    """Base exception for API client errors."""
    pass


class APIClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base_url = (base_url or os.getenv("REVENUE_RECOVERY_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = requests.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout as exc:
            raise APIClientError(f"Request timed out connecting to backend ({url})") from exc
        except requests.exceptions.ConnectionError as exc:
            raise APIClientError(f"Could not connect to backend server at {self.base_url}. Ensure FastAPI is running.") from exc
        except requests.exceptions.HTTPError as exc:
            detail = response.text
            try:
                err_json = response.json()
                detail = err_json.get("detail", detail)
            except Exception:
                pass
            raise APIClientError(f"API Error ({response.status_code}): {detail}") from exc
        except Exception as exc:
            raise APIClientError(f"Unexpected error calling {endpoint}: {exc}") from exc

    def get_health(self) -> dict[str, str]:
        return self._request("GET", "/health")

    def get_metrics(self) -> dict[str, Any]:
        return self._request("GET", "/metrics")

    def get_operational_metrics(self) -> dict[str, Any]:
        return self._request("GET", "/operational-metrics")

    def get_priority_cases(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._request("GET", "/priority-cases", params={"limit": limit})

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._request("GET", "/history", params={"limit": limit})

    def ingest_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/events", json=event_data)

    def get_recommendations(self, recommendation_data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/recommendations", json=recommendation_data)

    def get_decision(self, decision_data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/decisions", json=decision_data)

    def get_gateway_health(self, health_data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/gateway-health", json=health_data)

    def generate_communication(self, comm_data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/communication", json=comm_data)

    def ask_analyst(self, question: str) -> dict[str, Any]:
        return self._request("POST", "/analyst", json={"question": question})

    def run_experiment(self, exp_data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/experiments", json=exp_data)

    def check_drift(self, drift_data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/drift", json=drift_data)

    def send_razorpay_webhook(self, raw_payload: bytes, signature: str) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
        }
        return self._request("POST", "/webhooks/razorpay", data=raw_payload, headers=headers)
