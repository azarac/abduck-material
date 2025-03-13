import streamlit as st
import os
import streamlit as st

def main():
    st.title("Abduck Material")
    st.write("Herokuで動作中！")

# タイトル
st.title("Hello, Heroku!")

# メッセージを表示
st.write("Streamlit アプリが Heroku で動作しています 🎉")

# Heroku のポートを取得
port = int(os.environ.get("PORT", 8501))

# Streamlit を起動
if __name__ == "__main__":
    st.run(port=port, address="0.0.0.0")
