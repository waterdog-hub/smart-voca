# 2026-11-25 - smart-voca - 학교 서버 배포용 이미지 (「Dockerfile 구성」 R-01~R-16)
# 빌드: 리포 루트에서 docker build .
FROM python:3.13-slim

# 서버는 컨테이너를 학교 서버 모드로 띄운다: 가입 즉시 인증, 시작할 때 테이블과 공용 단어장 준비
# SECRET_KEY 는 서버가 환경변수로 넣는다. 이미지에 넣지 않는다 (R-08)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=school \
    DB_PATH=/data/voca.db

WORKDIR /app

# 의존성 파일을 먼저 복사해 설치한다. 소스만 바뀌면 이 층을 다시 쓰므로 빌드가 빠르다 (R-13)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY data/wordbooks.json data/words.csv ./data/

# 서버는 UID 10001 로 실행한다. 쓰기는 /data 에만 하므로 그 소유자를 10001 로 둔다 (R-05, R-06)
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown 10001:10001 /data

USER 10001:10001
EXPOSE 8080

# 운영용 uvicorn 으로 0.0.0.0:8080 에서 듣는다. --reload 는 쓰지 않는다 (R-03, R-14, R-15)
CMD ["uvicorn", "--factory", "web.app:create_app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
