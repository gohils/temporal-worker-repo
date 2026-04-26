---

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
# Run fastapi Locally for POC / Testing
docker run -it --rm -p 8000:8000 \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e APP_MODULE=wf_mgt_api.main:app \
  -e TASK_QUEUE=default-task-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  -e PORT=8000 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest

---- with .env file
.env file contains no spaces around =:

GIT_REPO=https://github.com/gohils/temporal-worker-repo.git
BRANCH=main
APP_MODULE=wf_mgt_api.main:app
TASK_QUEUE=default-task-queue
TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233
PORT=8000

docker run -it --rm --env-file .env -p 8000:8000 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest

# Run fastapi on ACA Azure Container Apps

```bash
az containerapp create \
  --name temporal-worker-fraud \
  --resource-group my-rg \
  --environment my-env \
  --image ghcr.io/gohils/reusable-fastapi-runtime:latest \
  --ingress disabled \
  --target-port 8000 \
  --env-vars \
    GIT_REPO=https://github.com/<org>/temporal-worker-repo.git \
    BRANCH=main \
    APP_MODULE=wf_mgt_api.main:app \
    TASK_QUEUE=default-task-queue \
    TEMPORAL_HOST=temporal-server:7233
```

docker run -it --rm \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-invoice/ai_doc_invoice_worker_v2.py \
  -e TASK_QUEUE=finance-invoice-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest

  docker run -it --rm \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-kyc/ai_doc_kyc_worker_v2.py \
  -e TASK_QUEUE=kyc-onboarding-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest

  https://zreactapp2.z8.web.core.windows.net/

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
# Run fastapi Locally for POC / Testing
docker run -it --rm -p 8000:8000 \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e APP_MODULE=wf_fastapi.main:app \
  -e TASK_QUEUE=default-task-queue\
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  -e PORT=8000 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest

docker run -it --rm \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-invoice/ai_doc_invoice_worker_v2.py \
  -e TASK_QUEUE=finance-invoice-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest

  docker run -it --rm \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-kyc/ai_doc_kyc_worker_v2.py \
  -e TASK_QUEUE=kyc-onboarding-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest

☁️ 1. Finance Invoice Worker (ACA)
az containerapp create \
  --name temporal-worker-invoice \
  --resource-group my-rg \
  --environment my-env \
  --image ghcr.io/gohils/reusable-fastapi-runtime:latest \
  --ingress disabled \
  --env-vars \
    GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
    BRANCH=main \
    WORKER_FILE=worker-invoice/ai_doc_invoice_worker_v2.py \
    TASK_QUEUE=finance-invoice-queue \
    TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233
☁️ 2. KYC Onboarding Worker (ACA)
az containerapp create \
  --name temporal-worker-kyc \
  --resource-group my-rg \
  --environment my-env \
  --image ghcr.io/gohils/reusable-fastapi-runtime:latest \
  --ingress disabled \
  --env-vars \
    GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
    BRANCH=main \
    WORKER_FILE=worker-kyc/ai_doc_kyc_worker_v2.py \
    TASK_QUEUE=kyc-onboarding-queue \
    TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233

⚙️ ACA with .env file
# Step 1: create .env from terminal
cat > .env <<EOF
GIT_REPO=https://github.com/gohils/temporal-worker-repo.git
BRANCH=main
WORKER_FILE=worker-invoice/ai_doc_invoice_worker_v2.py
TASK_QUEUE=finance-invoice-queue
TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233
EOF
# Step 2: 
az containerapp create \
  --name temporal-worker-invoice \
  --resource-group my-rg \
  --environment my-env \
  --image ghcr.io/gohils/reusable-fastapi-runtime:latest \
  --ingress disabled \
  --env-vars \
    $(cat .env | grep -v '^#' | xargs)

  https://zreactapp2.z8.web.core.windows.net/