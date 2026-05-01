
# 🔁 Reusable Temporal Worker Runtime — Build & Deploy Guide (WITH SCALING)

---

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

# 🧪 STEP 4 — RUN LOCALLY (POC / TESTING)

## 🧾 FastAPI worker running in background option

```bash
docker run -d \
  --name temporal-worker \
  --restart unless-stopped \
  -p 8000:8000 \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e APP_MODULE=wf_fastapi.main:app \
  -e TASK_QUEUE=default-task-queue \
  -e TEMPORAL_HOST=35.244.75.185:7233 \
  -e PORT=8000 \
  ghcr.io/gohils/reusable-temporal-runtime:latest
```

---

## 🧪 Interactive test

```bash
docker run -it --rm --env-file .env -p 8000:8000 \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e APP_MODULE=wf_ai_fastapi.main:app \
  -e TASK_QUEUE=default-task-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  -e PORT=8000 \
  ghcr.io/gohils/reusable-temporal-runtime:latest
```

---

## 💳 Payment Worker

```bash
docker run -d \
  --name temporal-payment-test-worker \
  --restart unless-stopped \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-template/worker.py \
  -e TASK_QUEUE=payments-task-queue \
  -e TEMPORAL_HOST=35.244.75.185:7233 \
  ghcr.io/gohils/reusable-temporal-runtime:latest
```

---

## 💳 Invoice Worker

```bash
docker run -it --rm \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-invoice/ai_doc_invoice_worker_v2.py \
  -e TASK_QUEUE=finance-invoice-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  ghcr.io/gohils/reusable-temporal-runtime:latest
```

---

## 🧾 KYC Worker

```bash
docker run -it --rm \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-kyc/ai_doc_kyc_worker_v2.py \
  -e TASK_QUEUE=kyc-onboarding-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  ghcr.io/gohils/reusable-temporal-runtime:latest
```

---

# 🐳 OPTION B — DOCKER COMPOSE (WITH SCALING SUPPORT)

## 📄 `temporal-worker.yml`

```yaml
version: "3.9"

services:

  temporal-worker:
    image: ghcr.io/gohils/reusable-temporal-runtime:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      GIT_REPO: https://github.com/gohils/temporal-worker-repo.git
      BRANCH: main
      APP_MODULE: wf_fastapi.main:app
      TASK_QUEUE: default-task-queue
      TEMPORAL_HOST: temporal-server-demo.australiaeast.cloudapp.azure.com:7233
      PORT: 8000


  temporal-payment-worker:
    image: ghcr.io/gohils/reusable-temporal-runtime:latest
    restart: unless-stopped
    environment:
      GIT_REPO: https://github.com/gohils/temporal-worker-repo.git
      BRANCH: main
      WORKER_FILE: worker-template/worker.py
      TASK_QUEUE: payments-task-queue
      TEMPORAL_HOST: temporal-server-demo.australiaeast.cloudapp.azure.com:7233


  temporal-invoice-worker:
    image: ghcr.io/gohils/reusable-temporal-runtime:latest
    restart: unless-stopped
    environment:
      GIT_REPO: https://github.com/gohils/temporal-worker-repo.git
      BRANCH: main
      WORKER_FILE: worker-invoice/ai_doc_invoice_worker_v2.py
      TASK_QUEUE: finance-invoice-queue
      TEMPORAL_HOST: temporal-server-demo.australiaeast.cloudapp.azure.com:7233


  temporal-kyc-worker:
    image: ghcr.io/gohils/reusable-temporal-runtime:latest
    restart: unless-stopped
    environment:
      GIT_REPO: https://github.com/gohils/temporal-worker-repo.git
      BRANCH: main
      WORKER_FILE: worker-kyc/ai_doc_kyc_worker_v2.py
      TASK_QUEUE: kyc-onboarding-queue
      TEMPORAL_HOST: temporal-server-demo.australiaeast.cloudapp.azure.com:7233
```

---

# 🚀 STEP 5 — DEPLOY ALL WORKERS

```bash
docker compose -f temporal-worker.yml up -d
```

---

# 🔁 STEP 6 — SCALING docker WORKERS containers 

---

## 💳 Scale Payment Workers (HIGH LOAD)

```bash
docker compose -f temporal-worker.yml up -d --scale temporal-payment-worker=3
```

---

## 📄 Scale Invoice Workers (burst processing)

```bash
docker compose -f temporal-worker.yml up -d --scale temporal-invoice-worker=2
```

---

## 🧾 Scale KYC Workers (onboarding spike handling)

```bash
docker compose -f temporal-worker.yml up -d --scale temporal-kyc-worker=4
```

---

## 📉 Reduce scaling (downscale)

```bash
docker compose -f temporal-worker.yml up -d --scale temporal-payment-worker=1
```

---

# 🧠 WHAT IS ACTUALLY HAPPENING

After scaling:

### Payment workers

```text
payment-worker-1
payment-worker-2
payment-worker-3
```

### Invoice workers

```text
invoice-worker-1
invoice-worker-2
```

### KYC workers

```text
kyc-worker-1
kyc-worker-2
kyc-worker-3
kyc-worker-4
```

👉 All workers compete on the same Temporal queue

---

# 🧹 STEP 7 — STOP / DELETE SYSTEM

## Stop all containers

```bash
docker compose -f temporal-worker.yml down
```

## Stop + remove volumes (DANGEROUS)

```bash
docker compose -f temporal-worker.yml down -v
```
---

# 🧠 FINAL ARCHITECTURE (WITH SCALING)

```text
                    Temporal Server
                          │
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼

 Payments Queue     Invoice Queue      KYC Queue
   │                  │                 │
   ▼                  ▼                 ▼
Workers xN       Workers xN        Workers xN
(dynamic scaling via docker compose --scale)
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
