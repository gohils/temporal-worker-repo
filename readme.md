# 🔁 Reusable Temporal Worker Runtime — Build & Deploy Guide

## 🚀 Step 1 — Build Docker Image Locally

```bash
docker build -t ghcr.io/<github-username>/reusable-temporal-runtime:latest .
```

---

## 🔐 Step 2 — Login to GitHub Container Registry (GHCR)

```bash
echo <YOUR_GITHUB_PAT> | docker login ghcr.io -u <GITHUB_USERNAME> --password-stdin
```

---

## 📦 Step 3 — Push Image to GHCR

```bash
docker push ghcr.io/<github-username>/reusable-temporal-runtime:latest
```

---

## 🧪 Step 4 — Run Locally (POC / Testing)

### 💳 Payments Worker

```bash
docker run -it --rm \
  -e GIT_REPO=https://github.com/<org>/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=run_payments_worker.py \
  -e TASK_QUEUE=payments-task-queue \
  -e TEMPORAL_HOST=temporal-server:7233 \
  ghcr.io/<github-username>/reusable-temporal-runtime:latest
```

---

### 🧾 KYC Worker

```bash
docker run -it --rm \
  -e GIT_REPO=https://github.com/<org>/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=run_kyc_worker.py \
  -e TASK_QUEUE=kyc-task-queue \
  -e TEMPORAL_HOST=temporal-server:7233 \
  ghcr.io/<github-username>/reusable-temporal-runtime:latest
```

---

### 🛡 Fraud Worker

```bash
docker run -it --rm \
  -e GIT_REPO=https://github.com/<org>/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=run_fraud_worker.py \
  -e TASK_QUEUE=fraud-task-queue \
  -e TEMPORAL_HOST=temporal-server:7233 \
  ghcr.io/<github-username>/reusable-temporal-runtime:latest
```

---

### 🧾 Invoice Worker

```bash
docker run -it --rm \
  -e GIT_REPO=https://github.com/<org>/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=run_invoice_worker.py \
  -e TASK_QUEUE=invoice-task-queue \
  -e TEMPORAL_HOST=temporal-server:7233 \
  ghcr.io/<github-username>/reusable-temporal-runtime:latest
```

---

# ☁️ Step 5 — Deploy to Azure Container Apps

## 💳 Payments Worker Deployment

```bash
az containerapp create \
  --name temporal-worker-payments \
  --resource-group my-rg \
  --environment my-env \
  --image ghcr.io/<github-username>/reusable-temporal-runtime:latest \
  --ingress disabled \
  --env-vars \
    GIT_REPO=https://github.com/<org>/temporal-worker-repo.git \
    BRANCH=main \
    WORKER_FILE=run_payments_worker.py \
    TASK_QUEUE=payments-task-queue \
    TEMPORAL_HOST=temporal-server:7233
```

---

## 🧾 KYC Worker Deployment

```bash
az containerapp create \
  --name temporal-worker-kyc \
  --resource-group my-rg \
  --environment my-env \
  --image ghcr.io/<github-username>/reusable-temporal-runtime:latest \
  --ingress disabled \
  --env-vars \
    GIT_REPO=https://github.com/<org>/temporal-worker-repo.git \
    BRANCH=main \
    WORKER_FILE=run_kyc_worker.py \
    TASK_QUEUE=kyc-task-queue \
    TEMPORAL_HOST=temporal-server:7233
```

---

## 🧾 Invoice Worker Deployment

```bash
az containerapp create \
  --name temporal-worker-invoice \
  --resource-group my-rg \
  --environment my-env \
  --image ghcr.io/<github-username>/reusable-temporal-runtime:latest \
  --ingress disabled \
  --env-vars \
    GIT_REPO=https://github.com/<org>/temporal-worker-repo.git \
    BRANCH=main \
    WORKER_FILE=run_invoice_worker.py \
    TASK_QUEUE=invoice-task-queue \
    TEMPORAL_HOST=temporal-server:7233
```

---

## 🛡 Fraud Worker Deployment

```bash
az containerapp create \
  --name temporal-worker-fraud \
  --resource-group my-rg \
  --environment my-env \
  --image ghcr.io/<github-username>/reusable-temporal-runtime:latest \
  --ingress disabled \
  --env-vars \
    GIT_REPO=https://github.com/<org>/temporal-worker-repo.git \
    BRANCH=main \
    WORKER_FILE=run_fraud_worker.py \
    TASK_QUEUE=fraud-task-queue \
    TEMPORAL_HOST=temporal-server:7233
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
