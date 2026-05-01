# 🟢 GCP TARGET ARCHITECTURE (ACA equivalent on Google Cloud)

Built on:

* Google Cloud Run

---

## 🧭 Services

1. FastAPI (public API)
2. Invoice Worker (Temporal worker)
3. KYC Worker (Temporal worker)

All use the same container image:

```bash id="img1"
ghcr.io/gohils/reusable-temporal-runtime:latest
```

---

# 🧠 STEP 0 — Design Principle (ACA-style on GCP)

We intentionally design for:

* ✔ scale-to-zero (true serverless)
* ✔ no Kubernetes (no GKE)
* ✔ no NAT Gateway
* ✔ no load balancer cost
* ✔ container registry = GitHub Container Registry (GHCR)

---

# 🚀 STEP 1 — Enable Google Cloud APIs

```bash id="gcp_enable"
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

---

# 🌐 STEP 2 — Authentication

```bash id="gcp_auth"
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud config set run/region australia-southeast1
```

---

# 🟢 STEP 3 — FASTAPI DEPLOYMENT (ACA external ingress equivalent)

## Key behavior:

* Public HTTP endpoint
* Auto HTTPS
* Scale-to-zero enabled by default
* No ALB equivalent required

---

## Deploy FastAPI

```bash id="fastapi_deploy"
gcloud run deploy temporal-fastapi \
  --image ghcr.io/gohils/reusable-temporal-runtime:latest \
  --allow-unauthenticated \
  --port 8000 \
  --set-env-vars \
GIT_REPO=https://github.com/gohils/temporal-worker-repo.git,\
BRANCH=main,\
APP_MODULE=wf_ai_fastapi.main:app,\
TASK_QUEUE=default-task-queue,\
TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233
```

---

## 🔧 What you get automatically:

✔ HTTPS endpoint
✔ global load balancer (managed, no cost control needed)
✔ scale-to-zero
✔ per-request billing

---

# ⚙️ STEP 4 — INVOICE WORKER (no ingress)

Cloud Run supports **always-on or scale-to-zero services**, but Temporal workers need continuous polling.

So we use:

👉 **Cloud Run Service with min instances = 1**

---

## Deploy Invoice Worker

```bash id="invoice_deploy"
gcloud run deploy temporal-worker-invoice \
  --image ghcr.io/gohils/reusable-temporal-runtime:latest \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --set-env-vars \
WORKER_FILE=worker-invoice/ai_doc_invoice_worker_v2.py,\
TASK_QUEUE=finance-invoice-queue,\
TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233
```

---

# ⚙️ STEP 5 — KYC WORKER

```bash id="kyc_deploy"
gcloud run deploy temporal-worker-kyc \
  --image ghcr.io/gohils/reusable-temporal-runtime:latest \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --set-env-vars \
WORKER_FILE=worker-kyc/ai_doc_kyc_worker_v2.py,\
TASK_QUEUE=kyc-onboarding-queue,\
TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233
```

---

# 🧠 STEP 6 — START / STOP BEHAVIOR (ACA-style control)

Unlike AWS ECS, Cloud Run is **truly scale-to-zero capable**, but workers need controlled scaling.

---

## 🟥 STOP ALL (near-zero cost mode)

### FastAPI:

Automatically scales to zero (no action needed)

### Workers:

```bash id="stop_workers"
gcloud run services update temporal-worker-invoice --min-instances 0
gcloud run services update temporal-worker-kyc --min-instances 0
```

---

## 🟢 START ALL (demo mode)

```bash id="start_workers"
gcloud run services update temporal-worker-invoice --min-instances 1
gcloud run services update temporal-worker-kyc --min-instances 1
```

FastAPI:

* auto starts on request
* no manual action required

---

# 💰 STEP 7 — COST BEHAVIOR

## 🟢 When STOPPED (scale-to-zero state)

| Component     | Cost                                          |
| ------------- | --------------------------------------------- |
| FastAPI       | ~$0                                           |
| Workers       | ~$0 (if min-instances = 0)                    |
| Load balancer | included (no extra charge model like AWS ALB) |
| NAT Gateway   | ❌ not used                                    |
| Kubernetes    | ❌ not used                                    |
| Total         | ~ $0–$2/month                                 |

---

## 🟡 When RUNNING

You only pay:

* CPU while containers are active
* memory usage while workers are running

No idle infrastructure cost.

---

# 🧠 STEP 8 — ARCHITECTURE SUMMARY

## 🟢 ACA-equivalent Google Cloud setup

### FastAPI (external API)

* Cloud Run service
* HTTPS endpoint automatically provided
* scale-to-zero enabled
* ❌ no ALB equivalent you manage

---

### Workers (Temporal)

* Cloud Run service
* min instances = 0 or 1
* polling-based execution

---

### Lifecycle

| Action    | Behavior           |
| --------- | ------------------ |
| Stop      | scale-to-zero      |
| Start     | instant cold start |
| Idle cost | near zero          |

---

# 🔥 KEY INSIGHT (IMPORTANT)

> Google Cloud Run is the closest native equivalent to Azure Container Apps.

Compared to AWS:

| Feature                    | GCP Cloud Run | AWS ECS                |
| -------------------------- | ------------- | ---------------------- |
| True scale-to-zero         | ✔ native      | ❌ limited              |
| No infra management        | ✔             | ❌                      |
| Demo start/stop simplicity | ✔             | ⚠ manual desired count |
| Hidden cost traps          | ❌ minimal     | ❌ ALB/NAT risk         |

---

# 🚨 FINAL TAKEAWAY

This setup gives you:

✔ ACA-like experience on GCP
✔ near-zero idle cost
✔ no Kubernetes (no GKE)
✔ no ALB / NAT complexity
✔ fully managed serverless containers

---

