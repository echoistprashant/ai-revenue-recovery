import streamlit as st


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700;800&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        h1, h2, h3, h4 {
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
        }

        .main-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
            padding: 1.8rem 2.2rem;
            border-radius: 16px;
            color: #ffffff;
            margin-bottom: 1.5rem;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .header-title {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(90deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.3rem;
        }

        .header-subtitle {
            color: #94a3b8;
            font-size: 1.0rem;
            margin: 0;
        }

        .kpi-card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 1.2rem;
            margin-bottom: 1rem;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .kpi-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 16px -4px rgba(0, 0, 0, 0.4);
            border-color: #6366f1;
        }

        .kpi-title {
            color: #94a3b8;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .kpi-value {
            color: #f8fafc;
            font-size: 1.8rem;
            font-weight: 700;
            margin: 0.4rem 0;
            font-family: 'Outfit', sans-serif;
        }

        .kpi-sub {
            color: #64748b;
            font-size: 0.8rem;
        }

        .badge {
            display: inline-block;
            padding: 0.25rem 0.6rem;
            font-size: 0.75rem;
            font-weight: 600;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .badge-success { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }
        .badge-warning { background: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.3); }
        .badge-danger  { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
        .badge-info    { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
        .badge-neutral { background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.3); }

        .safety-callout {
            background: linear-gradient(90deg, rgba(239, 68, 68, 0.1) 0%, rgba(249, 115, 22, 0.1) 100%);
            border-left: 4px solid #ef4444;
            padding: 1rem 1.2rem;
            border-radius: 0 12px 12px 0;
            margin: 1rem 0;
        }

        .architecture-pipeline {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #0f172a;
            padding: 1.2rem;
            border-radius: 12px;
            border: 1px solid #1e293b;
            margin: 1rem 0;
            overflow-x: auto;
        }

        .pipeline-step {
            text-align: center;
            background: #1e293b;
            padding: 0.8rem 1.2rem;
            border-radius: 8px;
            border: 1px solid #334155;
            min-width: 130px;
        }

        .pipeline-step.active {
            border-color: #6366f1;
            box-shadow: 0 0 12px rgba(99, 102, 241, 0.3);
        }

        .pipeline-step .step-title {
            font-size: 0.8rem;
            font-weight: 700;
            color: #e2e8f0;
        }

        .pipeline-step .step-desc {
            font-size: 0.7rem;
            color: #94a3b8;
        }

        .pipeline-arrow {
            color: #6366f1;
            font-size: 1.2rem;
            font-weight: bold;
            padding: 0 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str = "AI Revenue Recovery Platform", subtitle: str = "Operational Control Center & Decision Intelligence Loop") -> None:
    st.markdown(
        f"""
        <div class="main-header">
            <div class="header-title">{title}</div>
            <div class="header-subtitle">{subtitle}</div>
            <div style="margin-top: 0.8rem; display: flex; gap: 0.5rem; align-items: center;">
                <span class="badge badge-info">Phase 9 Completed</span>
                <span class="badge badge-success">56 Tests Passing</span>
                <span class="badge badge-warning">Simulated Synthetic Data</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_disclaimer_banner() -> None:
    st.markdown(
        """
        <div style="background-color: rgba(234, 179, 8, 0.1); border: 1px solid rgba(234, 179, 8, 0.3); border-radius: 8px; padding: 0.6rem 1rem; margin-bottom: 1.5rem; color: #fef08a; font-size: 0.85rem;">
            <strong>⚠️ Synthetic Data Disclaimer:</strong> Metrics, predictions, and financial actions presented in this dashboard are generated by a reproducible synthetic payment simulator. They are intended for demonstration and engineering evaluation only, not commercial financial performance.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_safety_callout() -> None:
    st.markdown(
        """
        <div class="safety-callout">
            <strong style="color: #f87171; font-size: 0.95rem;">🛡️ Critical Safety Architecture Boundary</strong><br/>
            <span style="color: #cbd5e1; font-size: 0.85rem;">
                The LLM is <strong>NOT</strong> a financial decision maker. All recovery retries, method changes, suppressions, and human escalations are decided by the <strong>Deterministic Decision Engine</strong> and gated by strict safety guardrails (Fraud Stop, High-Value Escalation, Retry Cap, Incident Suppression). The LLM only generates customer communications for <em>already-approved</em> actions or performs read-only analytics tool calling.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pipeline_flow(active_step: int = 0) -> None:
    steps = [
        ("1. Ingestion", "Webhooks & Normalization"),
        ("2. Classification", "9 Failure Rules"),
        ("3. ML & Signals", "P(Recovery), Churn, Value"),
        ("4. Guardrails", "Fraud, Cap, Value, Incident"),
        ("5. Decision Engine", "Deterministic Action"),
        ("6. Action & LLM", "Simulated Execution & Msg"),
    ]
    
    html = ['<div class="architecture-pipeline">']
    for idx, (title, desc) in enumerate(steps):
        active_cls = " active" if idx == active_step else ""
        html.append(f"""
            <div class="pipeline-step{active_cls}">
                <div class="step-title">{title}</div>
                <div class="step-desc">{desc}</div>
            </div>
        """)
        if idx < len(steps) - 1:
            html.append('<div class="pipeline-arrow">➔</div>')
    html.append('</div>')
    
    st.markdown("".join(html), unsafe_allow_html=True)


def get_badge_html(text: str, level: str = "neutral") -> str:
    level_map = {
        "success": "badge-success",
        "warning": "badge-warning",
        "danger": "badge-danger",
        "info": "badge-info",
        "neutral": "badge-neutral",
    }
    cls = level_map.get(level.lower(), "badge-neutral")
    return f'<span class="badge {cls}">{text}</span>'
