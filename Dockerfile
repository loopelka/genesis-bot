FROM python:3.12-slim

WORKDIR /app

# Mount point for runtime state (carts/users/orders/fsm_state.json). On the host,
# back this with a persistent volume and set DATA_DIR=/data so state survives
# redeploys/restarts.
RUN mkdir -p /data

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
