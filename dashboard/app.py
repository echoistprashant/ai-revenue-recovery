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
