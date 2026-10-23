# Analysis, report generation and chain verification (Python). Pinned dependencies; runs as non-root.
#
#   docker build -f docker/analysis.Dockerfile -t itb-analysis:local .

FROM python:3.12.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
RUN useradd --create-home --uid 10001 itb
WORKDIR /opt/itb
COPY analysis/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY analysis/ ./analysis/
RUN pip install --no-cache-dir --no-deps ./analysis
USER itb
WORKDIR /work
ENTRYPOINT ["python", "-m", "itb_analysis.cli"]
CMD ["reproduce"]
