az webapp up --name <app-name> --location <location-name> --runtime PYTHON:3.12 --sku B1 --logs 

docker test locally
-----
docker build -t fastapi-local .
docker run -p 8000:8000 fastapi-local

---- with .env file
docker run --env-file .env -p 8000:8000 fastapi-local

http://localhost:8000/docs

list running containers:
docker ps
2. Stop ALL running containers
docker stop $(docker ps -q)


Step 2 — Run Locally for POC / Testing from GitHub container
docker run -it --rm -p 8000:8000 \
  -e REPO_URL=https://github.com/gohils/fastapi-repo \
  -e BRANCH=main \
  -e APP_MODULE=app1.main:app \
  -e PORT=8000 \
  ghcr.io/gohils/reusable-fastapi-runtime:latest
