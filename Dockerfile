# Builds the React frontend, then serves it and the API from one Python process.
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/engireq ./engireq
COPY backend/fixtures ./fixtures
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Render supplies PORT at runtime.
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn engireq.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
