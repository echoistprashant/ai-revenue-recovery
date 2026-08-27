import os

import requests
import streamlit as st


API_URL = os.getenv("REVENUE_RECOVERY_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Revenue Recovery", layout="wide")
st.title("AI Revenue Recovery")

try:
    response = requests.get(f"{API_URL}/metrics", timeout=5)
    response.raise_for_status()
    metrics = response.json()
except requests.RequestException as exc:
    st.error(f"Metrics are unavailable: {exc}")
    st.stop()

columns = st.columns(4)
columns[0].metric("Failed payments", metrics["total_failures"])
columns[1].metric("Recovered", metrics["recovered_events"])
columns[2].metric("Recovery rate", f"{metrics['recovery_rate']:.1%}")
columns[3].metric("Recovered revenue", f"INR {metrics['recovered_revenue']:,.2f}")

st.subheader("Failure breakdown")
st.bar_chart(metrics["failure_breakdown"])

st.subheader("Top priority cases")
try:
    priority_response = requests.get(f"{API_URL}/priority-cases", params={"limit": 10}, timeout=5)
    priority_response.raise_for_status()
    st.dataframe(priority_response.json(), use_container_width=True, hide_index=True)
except requests.RequestException as exc:
    st.warning(f"Priority cases are unavailable: {exc}")
