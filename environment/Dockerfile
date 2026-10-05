FROM python:3.13-slim-bookworm
WORKDIR /app
COPY data/ /app/data/
COPY reconcile.py /app/reconcile.py
COPY agent_entrypoint.py /usr/local/bin/agent_entrypoint.py
RUN groupadd --gid 10001 agent \
    && useradd --uid 10001 --gid 10001 --create-home --shell /bin/sh agent \
    && chown -R root:root /app/data \
    && find /app/data -type d -exec chmod 0555 {} + \
    && find /app/data -type f -exec chmod 0444 {} + \
    && chown agent:agent /app/reconcile.py \
    && chmod 1777 /app \
    && chmod 0755 /usr/local/bin/agent_entrypoint.py
ENTRYPOINT ["/usr/local/bin/agent_entrypoint.py"]
CMD ["sleep", "infinity"]
