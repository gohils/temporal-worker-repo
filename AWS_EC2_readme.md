# 🟣 TEMPORAL SERVER ON AWS EC2

---

This includes:

* EC2 Spot instance setup
* Security configuration (FULL OPEN demo mode)
* Docker + Temporal + Postgres via Docker Compose
* Worker container deployment (FastAPI + Temporal workers)
* Deployment workflow
* Start/stop + cost behavior

Built on:

* Amazon Web Services EC2 Spot Instances
* Docker-based Temporal stack
* External worker containers (Docker runtime)

---

# 🧭 STEP 0 — ARCHITECTURE OVERVIEW

You deploy:

## 🟣 On EC2 (server node)

* Temporal Server
* Temporal UI
* PostgreSQL
* Docker Compose stack

## 🟢 External Workers (can be same VM or other compute)

* FastAPI worker container
* Payment worker container
* Workflow worker services

👉 This is **single-node demo backend + external worker model**

---

# 🌐 STEP 1 — SECURITY GROUP (FULL OPEN DEMO MODE)

## 🔓 Allow ALL traffic (demo only)

```bash id="sg_full"
aws ec2 create-security-group \
  --group-name "temporal-demo-sg" \
  --description "Temporal demo SG" \
  --vpc-id vpc-d7d7e9b0 \
  --query GroupId --output text

aws ec2 authorize-security-group-ingress \
  --group-id sg-0566813465eacc84c \
  --ip-permissions '[
    {
      "IpProtocol": "-1",
      "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
    }
  ]'
```



👉 Equivalent of:

* Azure `open-port "*" `
* GCP `allow all traffic firewall rule`

---
# 🚀 STEP 2 — CREATE EC2 SPOT INSTANCE

```bash id="ec2_spot"
aws ec2 run-instances \
  --image-id ami-0a59248a6294cece2 \
  --instance-type t2.medium \
  --key-name temporal-key \
  --security-group-ids sg-0566813465eacc84c \
  --subnet-id subnet-2e001367 \
  --associate-public-ip-address \
  --instance-market-options '{"MarketType":"spot"}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=temporal-server-vm}]'
```

---
# 🔑 STEP 3 — SSH INTO INSTANCE

```bash id="ssh"
ssh -i temporal-key.pem ubuntu@<PUBLIC_IP>
```

---

# 🧱 STEP 4 — INSTALL DOCKER

```bash id="docker_install"
sudo apt update -y

sudo apt install -y docker.io docker-compose

sudo usermod -aG docker ubuntu
newgrp docker
```

---

# 📦 STEP 5 — DEPLOY TEMPORAL STACK

## Option A — Git clone

```bash id="git"
git clone https://github.com/gohils/temporal1-repo.git
cd temporal1-repo/linux_v1
```
---

# 🐳 STEP 6 — START TEMPORAL STACK

```bash id="compose"
docker compose -f docker-compose-image-postgres.yml up -d
```

---

# 🧪 STEP 7 — VERIFY DEPLOYMENT

```bash id="ps"
docker ps
```

---

## 🌐 Access services

| Service       | URL                     |
| ------------- | ----------------------- |
| Temporal UI   | http://<PUBLIC_IP>:8080 |
| Temporal gRPC | <PUBLIC_IP>:7233        |

---

# ⚙️ STEP 8 — WORKER DEPLOYMENT (IMPORTANT ADDITION)

You can run worker containers in **3 ways**:

---

## 🟢 OPTION A — Same EC2 (simple demo)

### Run FastAPI + Worker container

```bash id="worker1"
docker run -d \
  --name temporal-worker \
  --restart unless-stopped \
  -p 8000:8000 \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e APP_MODULE=wf_fastapi.main:app \
  -e TASK_QUEUE=default-task-queue \
  -e TEMPORAL_HOST=<PUBLIC_IP>:7233 \
  -e PORT=8000 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest
```

---

## 💳 Payment Worker (separate task queue)

```bash id="worker2"
docker run -d \
  --name temporal-payment-worker \
  --restart unless-stopped \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e WORKER_FILE=worker-template/worker.py \
  -e TASK_QUEUE=payments-task-queue \
  -e TEMPORAL_HOST=<PUBLIC_IP>:7233 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest
```

---
#### Deploy containers via docker compose

```yaml 
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
      TEMPORAL_HOST: 3.25.241.18:7233
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
      TEMPORAL_HOST: 3.25.241.18:7233
```
#### docker compose as temporal-worker.yml

```bash id="workers"
docker compose -f temporal-worker.yml up -d
```


# 📊 STEP 9 — WORKER OBSERVABILITY

## Logs

```bash id="logs1"
docker logs -f temporal-worker
```

```bash id="logs2"
docker logs --tail 100 temporal-payment-worker
```

---

## Stop / remove worker

```bash id="rm"
docker rm -f temporal-worker
```

---

# 💰 STEP 10 — COST MODEL

## 🟢 Running Spot EC2

| Resource       | Cost                       |
| -------------- | -------------------------- |
| t3.medium Spot | very low (~$0.02–$0.05/hr) |
| Storage        | ~$1–2/month                |
| Network        | minimal                    |

---

## 🔴 STOP COST

```bash id="delete"
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=temporal-server-vm" \
  --query "Reservations[*].Instances[*].InstanceId" \
  --output text
  
aws ec2 terminate-instances \
  --instance-ids i-xxxxxx
```

👉 Spot = **no stop/start model**
👉 terminate = cost ends

---

# 🧠 STEP 11 — START / STOP BEHAVIOR

| Action        | Result                                |
| ------------- | ------------------------------------- |
| stop instance | ❌ not reliable (Spot may not support) |
| terminate     | ✔ cost = zero                         |
| recreate      | ✔ new instance                        |

---

# 🧠 ARCHITECTURE SUMMARY

```text id="arch"
Internet
   ↓
EC2 Spot (FULL OPEN SG)
   ↓
Docker Compose
   ├── Temporal Server (7233)
   ├── Temporal UI (8080)
   ├── PostgreSQL (5432)
   └── Worker Containers (8000 + task queues)
```

---

# 🟣 BEST PRACTICE (IMPORTANT INSIGHT)

| Component       | Best placement           |
| --------------- | ------------------------ |
| Temporal Server | EC2 Spot                 |
| Workers         | EC2 OR ECS OR Cloud Run  |
| APIs            | Cloud Run / ECS          |
| UI              | EC2 or managed container |

---

# 🎯 FINAL TAKEAWAY

✔ AWS EC2 Spot perfectly replicates your Azure + GCP demo
✔ Security Group = “open-port *” equivalent
✔ Workers can run either:

* same VM (demo)
* separate compute (production style)

✔ This gives you full **distributed Temporal demo architecture**

---
