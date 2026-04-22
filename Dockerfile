FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar os arquivos necessários
COPY requirements.txt .
COPY brain_mcp_server.py .
COPY brain_indexer.py .
COPY query_engine.py .
COPY config.py .
COPY constants.py .
COPY chunking.py .
COPY logging_config.py .
COPY mcp_wrapper.py .
COPY init_mcp.sh .

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Criar usuário não-root
RUN useradd --create-home --shell /bin/bash appuser

# Tornar o script executável e mudar o proprietário
RUN chown appuser:appuser /app/init_mcp.sh && \
    chmod +x /app/init_mcp.sh && \
    chown -R appuser:appuser /app

USER appuser

# Healthcheck para o serviço MCP (verifica se a porta está ouvindo)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('localhost', 8006), timeout=5)" || exit 1

# Comando padrão
CMD ["/app/init_mcp.sh"]
