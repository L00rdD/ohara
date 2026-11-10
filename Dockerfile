# Ohara: Python with Pillow (covers) and 7-Zip (to turn .cbr into .cbz)
FROM python:3-alpine
RUN apk add --no-cache 7zip && pip install --no-cache-dir pillow
WORKDIR /app
COPY ohara.py names.py ./
COPY web ./web
EXPOSE 8585
CMD ["python", "-u", "ohara.py"]
