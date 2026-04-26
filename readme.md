# 🔁 Reusable Temporal Worker Runtime — Build & Deploy Guide

## 🚀 Step 1 — Build Docker Image Locally

```bash
docker build -t ghcr.io/gohils/reusable-temporal-runtime:latest .
```

---

## 🔐 Step 2 — Login to GitHub Container Registry (GHCR)

```bash
echo <YOUR_GITHUB_PAT> | docker login ghcr.io -u <GITHUB_USERNAME> --password-stdin
```

---

## 📦 Step 3 — Push Image to GHCR

```bash
docker push ghcr.io/gohils/reusable-temporal-runtime:latest
```

---

## 🧪 Step 4 — Run Locally (POC / Testing)

### 🧾 Fastapi docker local test with .env

```bash
docker run -it --rm --env-file .env -p 8000:8000 \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e APP_MODULE=wf_ai_fastapi.main:app \
  -e TASK_QUEUE=default-task-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  -e PORT=8000 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest
```

---

### 💳 Invoice Worker

```bash
docker run -it --rm \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-invoice/ai_doc_invoice_worker_v2.py \
  -e TASK_QUEUE=finance-invoice-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest
```

---

### 🧾 KYC Worker

```bash
  docker run -it --rm \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-kyc/ai_doc_kyc_worker_v2.py \
  -e TASK_QUEUE=kyc-onboarding-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest
```

---

# ☁️ Step 5 — Deploy to Azure Container Apps

## 🧾 Fastapi on ACA Deployment

```bash
# Step 2: $(cat .env | grep -v '^#' | xargs)

az containerapp create \
  --name temporal-fastapi \
  --resource-group 1-aca-rg \
  --environment zacaenv1 \
  --image ghcr.io/gohils/reusable-fastapi-runtime:latest \
  --ingress external \
  --target-port 8000 \
  --env-vars \
    GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
    BRANCH=main \
    APP_MODULE=wf_ai_fastapi.main:app \
    TASK_QUEUE=default-task-queue \
    TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
    PORT=8000 \
    $(cat .env | grep -v '^#' | xargs)
```

---
## 💳 Invoice Worker Deployment

```bash
az containerapp create \
  --name temporal-worker-invoice \
  --resource-group 1-aca-rg \
  --environment zacaenv1 \
  --image ghcr.io/gohils/reusable-fastapi-runtime:latest \
  --ingress disabled \
  --env-vars \
    GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
    BRANCH=main \
    WORKER_FILE=worker-invoice/ai_doc_invoice_worker_v2.py \
    TASK_QUEUE=finance-invoice-queue \
    TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233
```

---

## 🧾 KYC Worker Deployment

```bash
az containerapp create \
  --name temporal-worker-kyc \
  --resource-group 1-aca-rg \
  --environment zacaenv1 \
  --image ghcr.io/gohils/reusable-fastapi-runtime:latest \
  --ingress disabled \
  --env-vars \
    GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
    BRANCH=main \
    WORKER_FILE=worker-kyc/ai_doc_kyc_worker_v2.py \
    TASK_QUEUE=kyc-onboarding-queue \
    TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233
```

---

# 🔁 Step 6 — Updating / Redeploying Workers

### Option 1 — Git-based update (recommended)

1. Push changes to GitHub repo
2. Restart container app:

```bash
az containerapp revision restart \
  --name temporal-worker-payments \
  --resource-group my-rg
```

--
