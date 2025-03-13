# ベースイメージ（Python 3.9を使用）
FROM python:3.9

# MeCabと辞書をインストール
RUN apt-get update && apt-get install -y \
    mecab \
    libmecab-dev \
    mecab-ipadic-utf8 \
    git curl \
    && rm -rf /var/lib/apt/lists/*

# Pythonライブラリをインストール
RUN pip install --no-cache-dir \
    mecab-python3 \
    pandas \
    streamlit

# アプリのコードをコピー
COPY . /app
WORKDIR /app

# Streamlitを実行
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
