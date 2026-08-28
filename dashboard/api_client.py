import os
from typing import Any
import requests


class APIClientError(Exception):
    """Base exception for API client errors."""
    pass


class AuthenticationRequiredError(APIClientError):
    """Raised when the backend rejects the current token, or there is none.

    The dashboard treats this as "show the login form again" rather than as a
    generic error, so an expired session does not look like a backend outage.
    """


class APIClient:
    """HTTP client for the backend.

    The client holds an access token and sends it as a bearer credential. It has no
    other notion of permission: what a signed-in user may do is decided by the
    backend, and a 403 from the API is the authoritative answer, not the UI's guess.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 10.0, token: str | None = None):
        self.base_url = (base_url or os.getenv("REVENUE_RECOVERY_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.timeout = timeout
        self.token = token

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Send one request and turn a failure into the narrowest error that fits.

        The status code decides the outcome, not the exception type the HTTP layer
        happens to raise: 401 means the session is gone and the dashboard should ask
        for a password again, while 403 is the backend's final word on a permission
        the caller does not have.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if self.token:
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault("Authorization", f"Bearer {self.token}")
            kwargs["headers"] = headers
        try:
            response = requests.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.Timeout as exc:
            raise APIClientError(f"Request timed out connecting to backend ({url})") from exc
        except requests.exceptions.ConnectionError as exc:
            raise APIClientError(f"Could not connect to backend server at {self.base_url}. Ensure FastAPI is running.") from exc
        except Exception as exc:
            raise APIClientError(f"Unexpected error calling {endpoint}: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            if response.status_code == 401:
                raise AuthenticationRequiredError(f"API Error (401): {detail}")
            raise APIClientError(f"API Error ({response.status_code}): {detail}")

        try:
            return response.json()
        except Exception as exc:
            raise APIClientError(f"Backend returned a non-JSON response for {endpoint}") from exc

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Exchange credentials for a token and keep it for later calls."""
        result = self._request("POST", "/auth/token", json={"username": username, "password": password})
        self.token = result["access_token"]
        return result

    def logout(self) -> None:
        self.token = None

    def whoami(self) -> dict[str, Any]:
        return self._request("GET", "/auth/me")

    def list_users(self) -> list[dict[str, Any]]:
        return self._request("GET", "/auth/users")

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/auth/users", json=payload)

    def deactivate_user(self, username: str) -> dict[str, Any]:
        return self._request("POST", f"/auth/users/{username}/deactivate")

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

    def get_audit_log(self, event_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if event_id is not None:
            params["event_id"] = event_id
        return self._request("GET", "/audit-log", params=params)

    def get_review_queue(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._request("GET", "/review-queue", params={"limit": limit})

    def resolve_case(self, event_id: int, resolution: str, note: str = "") -> dict[str, Any]:
        """Close an escalated case.

        The backend re-runs the decision engine for retry resolutions, so a
        resolution posted from here cannot execute an action the engine withholds.
        """
        return self._request(
            "POST",
            f"/review-queue/{event_id}/resolve",
            json={"resolution": resolution, "note": note},
        )

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

    def get_task_stats(self) -> dict[str, Any]:
        return self._request("GET", "/tasks/stats")

    def run_due_tasks(self) -> dict[str, Any]:
        """Flush due background work.

        The worker process normally does this. The endpoint re-checks every task
        against the decision engine, so triggering it from the UI cannot approve
        anything the engine would refuse.
        """
        return self._request("POST", "/tasks/run-due")

    def send_razorpay_webhook(self, raw_payload: bytes, signature: str) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
        }
        return self._request("POST", "/webhooks/razorpay", data=raw_payload, headers=headers)
