# Deployment & API Key Configuration Guide

This guide provides step-by-step instructions for deploying the **AI Revenue Recovery & Payment Intelligence Platform** to the cloud for live demonstration (Vercel + Render / Railway / Fly.io) and registering your Razorpay test-mode webhooks.

---

## 1. Project Directory Structure

The project is structured into clear modular components:

```text
ai-revenue-recovery/
├── frontend/                 <-- Next.js 16 Control Center (Deploy to Vercel)
│   ├── app/                  <-- App router pages & API proxy handlers
│   ├── components/           <-- React UI components
│   ├── Dockerfile            <-- Next.js standalone container build
│   ├── package.json
│   └── vercel.json           <-- Vercel deployment configuration
│
├── src/revenue_recovery/     <-- Python FastAPI Backend Service (Deploy to Render/Railway)
│   ├── api.py                <-- REST API routes (/events, /cases, /metrics, /webhooks)
│   ├── service.py            <-- Core PaymentRecoveryService logic
│   ├── decision_engine.py    <-- Deterministic recovery decision engine
│   ├── guardrails.py         <-- Fraud hard stop, retry cap, value escalation
│   ├── llm_boundary.py       <-- Google Gemini LLM analyst & communication boundary
│   ├── worker.py             <-- Background task execution engine
│   └── adapters/
│       └── razorpay.py       <-- Razorpay test-mode API adapter
│
├── Dockerfile                <-- Backend Docker image build
├── docker-compose.yml        <-- Full local multi-container orchestration
├── render.yaml               <-- One-click Render cloud blueprint
└── .env.example              <-- Complete environment variable template
```

---

## 2. API Keys Inventory & Where to Find Them

| Key Name | Where to Obtain | Purpose | Default / Example Value |
|---|---|---|---|
| `RAZORPAY_KEY_ID` | [Razorpay Dashboard](https://dashboard.razorpay.com/) -> Settings -> API Keys (Test Mode) | Authentication for outbound payment retry calls | `rzp_test_xxxxxxxxxxxxxx` |
| `RAZORPAY_KEY_SECRET` | [Razorpay Dashboard](https://dashboard.razorpay.com/) -> Settings -> API Keys (Test Mode) | HMAC authorization for outbound retries | `xxxxxxxxxxxxxxxxxxxxxxxx` |
| `RAZORPAY_WEBHOOK_SECRET` | [Razorpay Dashboard](https://dashboard.razorpay.com/) -> Settings -> Webhooks | Validates incoming webhook signature | `test_webhook_secret` (dev) |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) | Powers natural language AI Revenue Analyst & customer outreach | `AIzaSyxxxxxxxxxxxxxxxxxxxx` |
| `JWT_SECRET_KEY` | Generate via terminal: `python -c "import secrets; print(secrets.token_urlsafe(32))"` | Signs session tokens (Required in production, min 32 chars) | Random 32+ char string |

---

## 3. Step-by-Step Backend Cloud Deployment (Render / Railway)

### Option A: Render Deployment via Blueprint (Recommended)
1. Push your code to your GitHub repository.
2. Log into [Render.com](https://render.com).
3. Click **New +** -> **Blueprint**.
4. Connect your GitHub repository. Render will automatically detect `render.yaml`.
5. Fill in the environment secrets when prompted:
   - `RAZORPAY_KEY_ID`
   - `RAZORPAY_KEY_SECRET`
   - `RAZORPAY_WEBHOOK_SECRET`
   - `GEMINI_API_KEY`
6. Click **Apply**. Render will deploy:
   - Managed PostgreSQL Database
   - FastAPI Backend Web Service
   - Background Task Worker
7. Note down your backend live URL: e.g. `https://ai-revenue-recovery-api.onrender.com`

---

## 4. Step-by-Step Frontend Cloud Deployment (Vercel)

1. Log into [Vercel.com](https://vercel.com).
2. Click **Add New** -> **Project** -> Import your GitHub repository.
3. In the setup screen:
   - **Root Directory**: Select `frontend`
   - **Framework Preset**: Next.js (auto-detected)
4. Add **Environment Variables**:
   - `REVENUE_RECOVERY_API_URL` = `https://ai-revenue-recovery-api.onrender.com`
   - `FRONTEND_COOKIE_SECURE` = `true`
5. Click **Deploy**.
6. Note down your frontend live URL: e.g. `https://ai-revenue-recovery.vercel.app`

---

## 5. Razorpay Test-Mode Webhook Registration

1. Log into your [Razorpay Dashboard](https://dashboard.razorpay.com/) and switch to **Test Mode** (toggle on top bar).
2. Navigate to **Account & Settings** -> **Webhooks** -> **Add New Webhook**.
3. Fill in:
   - **Webhook URL**: `https://ai-revenue-recovery-api.onrender.com/webhooks/razorpay`
   - **Secret**: Set your `RAZORPAY_WEBHOOK_SECRET` value.
   - **Active Events**: Check `payment.failed` and `subscription.charged`.
4. Click **Save Webhook**.

---

## 6. Verification & Post-Deployment Setup

After deployment, initialize the production database user:

```bash
# Run against your live API database to create the admin account:
python scripts/create_user.py --username admin --role ADMIN
```

Open `https://ai-revenue-recovery.vercel.app`, sign in with `admin`, and your AI Revenue Recovery Platform is live!
