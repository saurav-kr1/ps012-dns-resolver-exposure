# Image for the probe client. The code is mounted from your folder (see docker-compose.yml),
# so you can edit the Python files and re-run without rebuilding.
FROM python:3.12-slim
RUN pip install --no-cache-dir dnspython pyyaml
WORKDIR /app
