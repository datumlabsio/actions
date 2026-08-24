# Deliberately bad. Every line here is something hadolint must refuse.
FROM python:latest
RUN apt-get update
RUN apt-get install -y curl
ADD https://example.com/thing.tar.gz /tmp/
CMD python app.py
