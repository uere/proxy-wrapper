FROM python:3.11-slim

WORKDIR /app

# Instala dependências
RUN pip install fastapi uvicorn httpx logging

# Copia o código
COPY app.py /app/app.py

ENV UPSTREAM_URL="https://url"
ENV VERIFY_SSL="false"

# Porta padrão do uvicorn
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
