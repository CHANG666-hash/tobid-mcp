# ToBid MCP server — thin wrapper over the public ToBid API.
# Default command speaks MCP over stdio (what most launchers and
# automated checks expect); set MCP_TRANSPORT=streamable-http to serve HTTP.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp_server.py .

ENV TOBID_API=https://api.tobid.tw \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8890

CMD ["python", "mcp_server.py"]
