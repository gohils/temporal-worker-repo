# 🟣 TEMPORAL SERVER ON AZURE VM

---

This includes:

* Azure Spot VM setup
* Network Security Group (FULL OPEN demo mode)
* Docker + Temporal + Postgres via docker-compose
* Worker container deployment (FastAPI + Temporal workers)
* Worker deployment via Docker run + docker-compose
* Deployment workflow
* Start/stop + cost behavior

Built on:

* Azure Virtual Machines (Spot instances)
* Docker-based Temporal stack
* External worker containers

---

# 🧭 STEP 0 — ARCHITECTURE OVERVIEW

## 🟣 On Azure VM (server node)

* Temporal Server
* Temporal UI
* PostgreSQL
* docker-compose stack

## 🟢 Workers (same VM or external compute)

* FastAPI worker container
* Payment worker container
* Workflow services

👉 This is:

> **Single-node Temporal backend + distributed worker model**

---
# 🚀 STEP 1 — CREATE AZURE SPOT VM

```bash id="az_vm"
az vm create \
  --resource-group 1-ai-llm-rg \
  --name temporal-server-vm \
  --image Ubuntu2204 \
  --size Standard_D2as_v5 \
  --priority Spot \
  --eviction-policy Deallocate \
  --max-price -1 \
  --admin-username azureuser \
  --ssh-key-values ~/.ssh/id_rsa.pub \
  --public-ip-address-dns-name temporal-server-demo
```

---
# 🔑 STEP 2 - Open ports for demo only

```bash id="ssh"
az vm open-port --resource-group 1-ai-llm-rg --name temporal-server-vm --port "*"
```
---
# 🔑 STEP 3 — SSH INTO VM

```bash id="ssh"
ssh azureuser@temporal-server-demo.australiaeast.cloudapp.azure.com

ssh -o StrictHostKeyChecking=no azureuser@temporal-server-demo.australiaeast.cloudapp.azure.com

upload local folder - sftp
scp -o StrictHostKeyChecking=no -r C:\myproject azureuser@temporal-server-demo.australiaeast.cloudapp.azure.com:/home/azureuser/
```

---

# 🧱 STEP 4 — INSTALL DOCKER

```bash id="docker"
sudo apt update -y

sudo apt install -y docker.io docker-compose python3-pip

sudo usermod -aG docker $USER
newgrp docker
```

---

# 📦 STEP 5 — DEPLOY TEMPORAL STACK

```bash id="git"
git clone https://github.com/gohils/temporal1-repo.git
cd temporal1-repo/linux_v1
```

---

## 🐳 STEP 6 — START TEMPORAL STACK

```bash id="temporal"
docker-compose -f docker-compose-image-postgres.yml up -d
```

---

# 🧪 STEP 7 — VERIFY DEPLOYMENT

```bash id="ps"
docker ps
```

---

## 🌐 ACCESS SERVICES

| Service       | URL                                                                                                                                    |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Temporal UI   | [http://temporal-server-demo.australiaeast.cloudapp.azure.com:8080](http://temporal-server-demo.australiaeast.cloudapp.azure.com:8080) |
| Temporal gRPC | temporal-server-demo.australiaeast.cloudapp.azure.com:7233                                                                             |

---

# ⚙️ STEP 8 — WORKER DEPLOYMENT (FULL COVERAGE)

---

## 🟢 OPTION A — Docker Run (Simple Demo)

### FastAPI + Worker

```bash id="worker_run_1"
docker run -d \
  --name temporal-worker \
  --restart unless-stopped \
  -p 8000:8000 \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e APP_MODULE=wf_fastapi.main:app \
  -e TASK_QUEUE=default-task-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  -e PORT=8000 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest
```

---

## 💳 Payment Worker (Docker Run)

```bash id="worker_run_2"
docker run -d \
  --name temporal-payment-worker \
  --restart unless-stopped \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-template/worker.py \
  -e TASK_QUEUE=payments-task-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest
```

---

# 🐳 OPTION B — WORKER docker-compose (MISSING PIECE ADDED)

## 📄 `temporal-worker.yml`

```yaml id="worker_compose"
version: "3.9"

services:
  temporal-worker:
    image: ghcr.io/gohils/reusable-fastapi-runtime:latest
    container_name: temporal-worker
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
    image: ghcr.io/gohils/reusable-fastapi-runtime:latest
    container_name: temporal-payment-worker
    restart: unless-stopped
    environment:
      GIT_REPO: https://github.com/gohils/temporal-worker-repo.git
      BRANCH: main
      WORKER_FILE: worker-template/worker.py
      TASK_QUEUE: payments-task-queue
      TEMPORAL_HOST: temporal-server-demo.australiaeast.cloudapp.azure.com:7233
```

---

## 🚀 RUN WORKERS VIA COMPOSE

```bash id="worker_compose_run"
docker-compose -f temporal-worker.yml up -d
```

---

# 📊 STEP 9 — OBSERVABILITY

```bash id="logs1"
docker logs -f temporal-worker
```

```bash id="logs2"
docker logs -f temporal-payment-worker
```

Stop:

```bash id="rm"
docker rm -f temporal-worker
```

---

# 💰 STEP 10 — COST MODEL

| Resource      | Cost                       |
| ------------- | -------------------------- |
| Azure Spot VM | very low (~$0.02–$0.06/hr) |
| Storage       | ~$2–5/month                |
| Network       | minimal                    |

---

# 🔴 STOP COST

```bash id="stop"
az vm delete \
  --resource-group 1-ai-llm-rg \
  --name temporal-server-vm \
  --yes
```

---

# 🧠 STEP 11 — START / STOP BEHAVIOR

| Action          | Result          |
| --------------- | --------------- |
| stop/deallocate | ✔ compute stops |
| delete VM       | ✔ cost ends     |
| recreate        | ✔ new VM        |

---

# 🧠 ARCHITECTURE SUMMARY

```text id="arch"
Internet
   ↓
Azure VM (Spot + NSG open)
   ↓
docker-compose
   ├── Temporal Server (7233)
   ├── Temporal UI (8080)
   ├── PostgreSQL (5432)
   └── Worker Containers (8000 + task queues)
```

---

# 🟣 BEST PRACTICE

| Component       | Best placement      |
| --------------- | ------------------- |
| Temporal Server | Azure VM Spot       |
| Workers         | VM / Container Apps |
| APIs            | Container Apps      |
| UI              | VM or container     |



