# local fastapi run from subfolder via python module like this
python -m wf_ai_fastapi.main

.env file contains no spaces around =:

GIT_REPO=https://github.com/gohils/temporal-worker-repo.git
BRANCH=main
APP_MODULE=wf_mgt_api.main:app
TASK_QUEUE=default-task-queue
TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233
PORT=8000

docker run -it --rm --env-file .env -p 8000:8000 \
  -e GIT_REPO=https://github.com/gohils/temporal-worker-repo.git \
  -e BRANCH=main \
  -e APP_MODULE=wf_ai_fastapi.main:app \
  -e TASK_QUEUE=default-task-queue \
  -e TEMPORAL_HOST=temporal-server-demo.australiaeast.cloudapp.azure.com:7233 \
  -e PORT=8000 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest

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