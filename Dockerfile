FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（akshare 可能需要）
RUN apt-get update && apt-get install -y --no-no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8501

# Streamlit 默认端口，由 compose 映射到 3330
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
