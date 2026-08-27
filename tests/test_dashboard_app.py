from dashboard.components.ui import get_badge_html
from dashboard.api_client import APIClient


def test_dashboard_ui_badge_helper() -> None:
    html = get_badge_html("SUCCESS", "success")
    assert "badge-success" in html
    assert "SUCCESS" in html

    html_danger = get_badge_html("DANGER", "danger")
    assert "badge-danger" in html_danger


def test_dashboard_api_client_instantiation() -> None:
    client = APIClient("http://localhost:8000")
    assert client.base_url == "http://localhost:8000"
