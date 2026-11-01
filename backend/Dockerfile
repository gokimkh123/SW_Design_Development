# 백엔드 이미지 (빌드 컨텍스트: 저장소 루트)
# 저장소 구조(backend/ · engine/ · data/)를 /srv 아래에 그대로 유지
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv
WORKDIR /srv/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY engine /srv/engine
COPY data /srv/data
COPY backend/app ./app
EXPOSE 8000
# 동시 연결 상한(SSE 포함): 과도한 연결로 스레드가 고갈되기 전에 503으로 거절
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "300"]
