# 🟢 AWS ARCHITECTURE (ACA equivalent on AWS)

Built on:
* Amazon ECS
* Amazon ECS Fargate
* GitHub Container Registry (GHCR only)

---

## 🧭 Services

1. FastAPI (public API)
2. Invoice Worker (Temporal)
3. KYC Worker (Temporal)

All use:

```bash
ghcr.io/gohils/reusable-temporal-runtime:latest
```

---

# 🧠 STEP 0 — Core Design Principle (ACA-style behavior)

We intentionally design for:

* ❌ NO ALB (no load balancer cost trap)
* ❌ NO NAT Gateway (no networking cost trap)
* ✔ Public subnet + public IP for API access
* ✔ ECS desired count = 0/1 (start/stop like ACA)
* ✔ GHCR public image (no AWS registry dependency)

---

# 🚀 STEP 1 — Create ECS Cluster

```bash id="ecs_cluster"
aws ecs create-cluster \
  --cluster-name temporal-demo-cluster
```

---

# 🌐 STEP 2 — Networking (CRITICAL)

## Use default VPC OR simple custom VPC:

### Requirements:

* Public subnet enabled
* Auto-assign public IP = ENABLED

### DO NOT create:

❌ NAT Gateway
❌ Private subnet
❌ Route tables for private egress

👉 This is what keeps cost near zero.

---

# ⚙️ STEP 3 — IAM Role for ECS Tasks

Create ECS Task Execution Role:

Attach policy:

* `AmazonECSTaskExecutionRolePolicy`

---

# 🌐 STEP 4 — FASTAPI SERVICE (ACA external ingress equivalent)

## 🧩 Task Definition (FastAPI using GHCR)

```json id="fastapi_task_ghcr"
{
  "family": "temporal-fastapi",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "fastapi",
      "image": "ghcr.io/gohils/reusable-temporal-runtime:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "GIT_REPO",
          "value": "https://github.com/gohils/temporal-worker-repo.git"
        },
        { "name": "BRANCH", "value": "main" },
        { "name": "APP_MODULE", "value": "wf_ai_fastapi.main:app" },
        { "name": "TASK_QUEUE", "value": "default-task-queue" },
        {
          "name": "TEMPORAL_HOST",
          "value": "temporal-server-demo.australiaeast.cloudapp.azure.com:7233"
        }
      ]
    }
  ]
}
```

---

## 🚀 Create ECS Service (NO ALB, NO NAT)

```bash id="fastapi_service"
aws ecs create-service \
  --cluster temporal-demo-cluster \
  --service-name temporal-fastapi \
  --task-definition temporal-fastapi \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

---

# ⚙️ STEP 5 — INVOICE WORKER (no ingress)

```json id="invoice_worker_ghcr"
{
  "family": "temporal-worker-invoice",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "worker",
      "image": "ghcr.io/gohils/reusable-temporal-runtime:latest",
      "essential": true,
      "environment": [
        {
          "name": "WORKER_FILE",
          "value": "worker-invoice/ai_doc_invoice_worker_v2.py"
        },
        { "name": "TASK_QUEUE", "value": "finance-invoice-queue" },
        {
          "name": "TEMPORAL_HOST",
          "value": "temporal-server-demo.australiaeast.cloudapp.azure.com:7233"
        }
      ]
    }
  ]
}
```

```bash id="invoice_service"
aws ecs create-service \
  --cluster temporal-demo-cluster \
  --service-name invoice-worker \
  --task-definition temporal-worker-invoice \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

---

# ⚙️ STEP 6 — KYC WORKER

```bash id="kyc_service"
aws ecs create-service \
  --cluster temporal-demo-cluster \
  --service-name kyc-worker \
  --task-definition temporal-worker-kyc \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

---

# 🧠 STEP 7 — ACA-STYLE START / STOP CONTROL (CORE VALUE)

This is your “click button like Azure Container Apps” replacement.

---

## 🟥 STOP ALL (near-zero cost mode)

```bash id="stop_all"
aws ecs update-service --cluster temporal-demo-cluster --service temporal-fastapi --desired-count 0
aws ecs update-service --cluster temporal-demo-cluster --service invoice-worker --desired-count 0
aws ecs update-service --cluster temporal-demo-cluster --service kyc-worker --desired-count 0
```

---

## 🟢 START ALL (demo mode)

```bash id="start_all"
aws ecs update-service --cluster temporal-demo-cluster --service temporal-fastapi --desired-count 1
aws ecs update-service --cluster temporal-demo-cluster --service invoice-worker --desired-count 1
aws ecs update-service --cluster temporal-demo-cluster --service kyc-worker --desired-count 1
```

---

# 💰 STEP 8 — COST MODEL (ACA-like behavior)

## 🟢 When STOPPED (desired count = 0)

| Component       | Cost                     |
| --------------- | ------------------------ |
| ECS Services    | $0                       |
| Fargate compute | $0                       |
| ALB             | ❌ not used               |
| NAT Gateway     | ❌ not used               |
| GHCR            | $0                       |
| Total           | ~$0–$2/month (logs only) |

---

## 🟡 When RUNNING

You only pay:

* CPU + memory runtime of tasks

No idle infra cost.

---

# 🧠 FINAL ARCHITECTURE (CLEAN VERSION)

## 🟢 FastAPI (ACA external ingress equivalent)

* ECS Fargate
* Public subnet
* Public IP enabled
* ❌ No ALB

---

## ⚙️ Workers (Temporal)

* ECS Fargate
* Public subnet
* ❌ No NAT Gateway
* ❌ No ALB

---

## 🔁 Lifecycle

| Action | ECS Equivalent    |
| ------ | ----------------- |
| Start  | desired count = 1 |
| Stop   | desired count = 0 |

---

# 🔥 KEY INSIGHT (IMPORTANT)

> You do NOT need AWS ECR, ALB, or NAT Gateway to replicate ACA behavior.

The ACA-like experience comes from:

* ECS Fargate
* public IP
* service scaling (0 ↔ 1)
* external container registry (GHCR)

NOT from AWS infrastructure services.

---

# 🚨 FINAL TAKEAWAY

This architecture gives you:

✔ ACA-like start/stop experience
✔ near-zero idle cost
✔ no AWS registry dependency
✔ minimal AWS infra footprint
✔ demo-friendly cloud setup

---
