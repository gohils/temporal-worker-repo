# 🟣 TEMPORAL SERVER ON GOOGLE CLOUD (GCP)

---
This includes:

* GCP VM Spot instance setup
* Security configuration (minimal but safe for demo)
* Docker + Temporal + Postgres via Docker Compose
* Deployment workflow
* Start/stop + cost behavior

Built on:

* GCP VM
* Spot Instances (low-cost compute)
* Docker-based Temporal stack

# 🧭 STEP 0 — ARCHITECTURE OVERVIEW

You will deploy:

### On a single GCP VM:

* Temporal Server
* Temporal UI
* PostgreSQL (demo persistence)
* Docker Compose stack

👉 This is **single-node demo architecture** (NOT production HA)

---

# 🚀 STEP 1 — CREATE GCP PREEMPTIBLE VM (LOW COST)

## Equivalent of AWS Spot / Azure Spot VM

```bash id="gcp_vm_create"
gcloud compute instances create temporal-server-vm \
  --zone=australia-southeast1-a \
  --machine-type=e2-standard-2 \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --tags=temporal-server \
  --boot-disk-size=30GB
```

---

## Why Spot VM here:

* ✔ 60–80% cheaper than normal VM
* ❌ may be stopped by GCP anytime
* ✔ perfect for demo Temporal server

---

# 🌐 STEP 2 — OPEN FIREWALL PORTS

Temporal requires:

| Service       | Port |
| ------------- | ---- |
| Temporal gRPC | 7233 |
| Temporal UI   | 8080 |
| SSH           | 22   |

---

## Create firewall rules:

```bash id="fw_rules"
gcloud compute firewall-rules create temporal-allow-all \
  --allow all \
  --target-tags=temporal-server \
  --description="TEMP ONLY - allow all traffic for testing"
```

---

# 🔑 STEP 3 — SSH INTO VM

```bash id="ssh_gcp"
gcloud compute ssh temporal-server-vm \
  --zone=australia-southeast1-a

ssh -i ~/.ssh/google_compute_engine user@35.244.75.185
```

---

# 🧱 STEP 4 — INSTALL DOCKER + COMPOSE

```bash id="docker_install_gcp"
sudo apt update -y

sudo apt install -y docker.io docker-compose

sudo usermod -aG docker $USER
newgrp docker
```

Verify:

```bash id="docker_check_gcp"
docker --version
docker compose version
```

---

# 📦 STEP 5 — DEPLOY TEMPORAL SERVER STACK

## Option A: Git clone (recommended)

```bash id="git_clone_gcp"
git clone https://github.com/gohils/temporal1-repo.git
cd temporal1-repo/linux_v1
```

---

## Option B: Upload tar (your method)

```bash id="upload_gcp"
git archive -o deploy.tar.gz HEAD
gcloud compute scp deploy.tar.gz temporal-server-vm:/home/ubuntu/
```

On VM:

```bash id="extract_gcp"
mkdir -p temporal-repo
tar -xzf deploy.tar.gz -C temporal-repo
cd temporal-repo/linux_v1
```

---

# 🐳 STEP 6 — START TEMPORAL STACK

```bash id="compose_up_gcp"
docker compose -f docker-compose-image-postgres.yml up -d
```

---

# 🧪 STEP 7 — VERIFY DEPLOYMENT

## Check running containers:

```bash id="ps_gcp"
docker ps
```

---

## Access Temporal UI:

```text id="ui_gcp"
http://<EXTERNAL_IP>:8080
```

---

## Temporal gRPC endpoint:

```text id="grpc_gcp"
<EXTERNAL_IP>:7233
```

---

# ⚙️ STEP 8 — CONNECT EXTERNAL WORKERS (your system)

Your FastAPI / ECS / ACA / Cloud Run workers will use:

```text id="temporal_host"
TEMPORAL_HOST=<GCP_EXTERNAL_IP>:7233
```

### 🧾 Fastapi docker local test with .env or on cloud VM
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
  ghcr.io/gohils/reusable-fastapi-runtime:latest
```

---
### 💳 Payment test Worker

```bash
docker run -d \
  --name temporal-payment-test-worker \
  --restart unless-stopped \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-template/worker.py \
  -e TASK_QUEUE=payments-task-queue \
  -e TEMPORAL_HOST=35.244.75.185:7233 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest
```
#### logs in real time containers
```bash
docker logs -f --timestamps container_name_or_id
docker logs -f container_name_or_id
docker logs --tail 100 container_name_or_id
```

#### delete containers
```bash
docker ps

docker rm -f container_name_or_id
```
---

# 💰 STEP 9 — COST MODEL (IMPORTANT)

## 🟢 When VM is RUNNING

| Component | Cost              |
| --------- | ----------------- |
| Spot VM   | ~$0.02–$0.06/hour |
| Disk      | ~$1–2/month       |
| Network   | minimal           |

---

## 🔴 DELETE VM STOPPED

```bash 
gcloud compute instances delete temporal-server-vm --zone=australia-southeast1-a
```
🚀 Step 1 — Delete the VM (main resource)
gcloud compute instances delete temporal-server-vm \
  --zone=australia-southeast1-a
🚨 Step 2 — Check and delete external IP (VERY IMPORTANT)
List external IPs:
gcloud compute addresses list

If you see a reserved IP:

Delete it:
gcloud compute addresses delete <ADDRESS_NAME> \
  --region=australia-southeast1

👉 If you skip this:

static IP billing continues 💸
💾 Step 3 — Delete boot disk (if NOT auto-deleted)

Sometimes disks remain.

Check:

gcloud compute disks list

Delete:

gcloud compute disks delete <DISK_NAME> \
  --zone=australia-southeast1-a
  
🔥 Step 4 — Delete firewall rules (optional but recommended)

If you created custom rules:

gcloud compute firewall-rules list

Delete:

gcloud compute firewall-rules delete temporal-open-all

✔ compute cost stops
✔ disk cost remains (~$1–2/month)
❌ IP may change unless reserved

---

## 🧠 Key insight:

> GCP VM is NOT scale-to-zero
> it is “cheap always-on or manually stopped compute”

---

# 🧠 STEP 10 — START / STOP (ACA-like simulation)

## STOP (reduce cost)

```bash id="stop_gcp"
gcloud compute instances stop temporal-server-vm \
  --zone=australia-southeast1-a
```

---

## START (resume demo)

```bash id="start_gcp"
gcloud compute instances start temporal-server-vm \
  --zone=australia-southeast1-a
```

---

# 🧠 ARCHITECTURE SUMMARY

## 🟣 Temporal Server on GCP (EC2 equivalent model)

### Components:

* Preemptible VM (Spot equivalent)
* Docker Compose stack:

  * Temporal Server
  * Temporal UI
  * PostgreSQL

---

### Endpoints:

| Service       | Endpoint |
| ------------- | -------- |
| Temporal UI   | :8080    |
| Temporal gRPC | :7233    |


## Best hybrid pattern:

| Component       | Best platform           |
| --------------- | ----------------------- |
| Temporal Server | EC2 Spot or GCP Spot VM |
| FastAPI         | Cloud Run / ACA         |
| Workers         | ECS / ACA / Cloud Run   |

