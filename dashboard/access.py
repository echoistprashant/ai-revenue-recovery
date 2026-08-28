"""Which dashboard modules a role may see.

This is presentation only. The backend re-checks the caller's role on every request
and a 403 from the API is the authoritative answer — hiding a module keeps a viewer
from being offered a control that would only fail, it does not enforce anything.
Keeping the map here (rather than inline in the Streamlit script) makes it testable
without a Streamlit runtime.
"""

ROLE_RANK = {"VIEWER": 1, "OPERATOR": 2, "ADMIN": 3}

# Each module and the minimum role the backend requires for its main call. Reading the
# review queue needs only VIEWER; resolving a case needs OPERATOR and is gated inside
# the panel, so a viewer can see what is waiting without being able to act on it.
MODULES: list[tuple[str, str]] = [
    ("📊 Executive Overview", "VIEWER"),
    ("💳 Payment Operations", "OPERATOR"),
    ("🎯 Priority Cases", "VIEWER"),
    ("🧑‍⚖️ Human Review Queue", "VIEWER"),
    ("🧠 Decision Center", "VIEWER"),
    ("🔮 Recovery Optimization", "VIEWER"),
    ("🏦 Gateway Health", "VIEWER"),
    ("💬 Customer Communication", "OPERATOR"),
    ("🤖 AI Revenue Analyst", "VIEWER"),
    ("🧪 Experiments & What-If", "VIEWER"),
    ("📈 Monitoring & Data Drift", "VIEWER"),
    ("📜 Audit & Decision History", "VIEWER"),
    ("👥 User Administration", "ADMIN"),
]


def allowed(role: str, minimum: str) -> bool:
    """Whether ``role`` outranks or equals ``minimum``.

    An unknown role ranks 0, so a role this build does not recognise is shown nothing
    rather than everything.
    """
    return ROLE_RANK.get(role, 0) >= ROLE_RANK[minimum]


def menu_for(role: str) -> list[str]:
    return [label for label, minimum in MODULES if allowed(role, minimum)]
