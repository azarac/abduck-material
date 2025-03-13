import os
import streamlit as st

def main():
    st.title("Abduck Material")
    st.write("Herokuで動作中！")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8501))
    st.run(server.port=port, server.address="0.0.0.0")
