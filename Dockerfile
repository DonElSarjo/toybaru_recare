FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENV TOYBARU_DATA_DIR=/data
RUN mkdir -p /data
RUN adduser --disabled-password --no-create-home --uid 1000 app && chown -R app:app /app /data
USER app
EXPOSE 8099

CMD ["toybaru", "dashboard", "--host", "0.0.0.0"]
