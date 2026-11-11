# Ohara: Python with Pillow (covers), 7-Zip and bsdtar (to turn .cbr into .cbz)
FROM python:3-alpine
RUN apk add --no-cache 7zip libarchive-tools && pip install --no-cache-dir pillow
WORKDIR /app
COPY ohara.py names.py robin.py brook.py franky.py ./
COPY web ./web
EXPOSE 8585
CMD ["python", "-u", "ohara.py"]
