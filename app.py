import os
import platform
import streamlit as st
import pandas as pd
import re
import io
import zipfile
import string
import MeCab

# 環境に応じた mecabrc のパスを自動判定
if platform.system() == "Darwin":
    # macOSの場合
    if os.path.exists("/etc/mecabrc"):
        mecabrc_path = "/etc/mecabrc"
    else:
        mecabrc_path = "/opt/homebrew/etc/mecabrc"
else:
    # Linux環境（Herokuなど）
    mecabrc_path = "/etc/mecabrc"

# MeCabの初期化
mecab = MeCab.Tagger(f"-r {mecabrc_path} -Ochasen")

# 役職リスト（よくある役職名を追加）
job_titles = ["代表", "取締役", "部長", "社長", "専務", "理事", "監査役", "役員", 
              "議員", "審議官", "教授", "会長", "研究員"]

# 関数1: 記事の文章単位で「人名 + 役職」の割合を計算し、名詞・動詞の割合も取得
def calculate_text_ratios(text):
    sentences = re.split(r'[。！？]', text)
    total_sentences = len(sentences)
    relevant_sentences = 0

    num_words = 0
    num_nouns = 0
    num_verbs = 0

    for sentence in sentences:
        parsed = mecab.parse(sentence)
        lines = parsed.split("\n")
        has_person = False
        has_job = False

        for line in lines:
            parts = line.split("\t")
            if len(parts) > 3:
                word = parts[0]
                pos = parts[3]
                num_words += 1

                if "名詞" in pos:
                    num_nouns += 1
                    if "人名" in pos:
                        has_person = True  # 人名を含む
                    elif any(title in word for title in job_titles):
                        has_job = True     # 役職を含む
                elif "動詞" in pos:
                    num_verbs += 1

        if has_person or has_job:
            relevant_sentences += 1  # 人名 or 役職を含む文章カウント

    people_job_ratio = relevant_sentences / total_sentences if total_sentences > 0 else 0
    noun_ratio = num_nouns / num_words if num_words > 0 else 0
    verb_ratio = num_verbs / num_words if num_words > 0 else 0
    
    return noun_ratio, verb_ratio, people_job_ratio

# 関数2: 記事の精査関数（フィルタリング）
def process_articles(df, keywords, column_name):
    if keywords:
        filtered_df = df[df[column_name].str.contains('|'.join(keywords), na=False)]
    else:
        filtered_df = df.copy()

    # x000D比率フィルタ
    filtered_df['x000D_ratio'] = filtered_df[column_name].apply(lambda x: x.count('x000D') / len(x) if isinstance(x, str) else 0)
    filtered_df = filtered_df[filtered_df['x000D_ratio'] < 0.018]

    # 名詞・動詞・人名 + 役職の割合を計算
    filtered_df[['noun_ratio', 'verb_ratio', 'people_job_sentence_ratio']] = \
        filtered_df[column_name].apply(lambda x: pd.Series(calculate_text_ratios(str(x))))

    # **名詞の割合が 80% 以上 & 動詞の割合が 5% 以下の記事を除外**
    filtered_df = filtered_df[(filtered_df['noun_ratio'] < 0.8) | (filtered_df['verb_ratio'] > 0.05)]

    # **「人名 + 役職の文章割合が50%以上」なら除外**
    filtered_df = filtered_df[filtered_df['people_job_sentence_ratio'] < 0.5]

    return filtered_df

# 関数3: 各行の先頭空白を除去する補助関数
def remove_leading_spaces_from_each_line(text):
    return "\n".join(line.lstrip() for line in text.splitlines())

# 関数4: 記号だけの文章を削除し、各行の先頭空白も取り除く関数
def clean_sentences(sentences):
    cleaned_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        sentence = remove_leading_spaces_from_each_line(sentence)
        if any(char.isalnum() or char in "ぁ-ゔァ-ヴ一-龠々〆ヵヶ" for char in sentence):
            cleaned_sentences.append(sentence)
    return cleaned_sentences

# 関数5: 不要な記号の削除 & 文頭の空白削除
def clean_text(text):
    unwanted_symbols = ["●", "■", "×", "▼", "◇", "x000D", "＿", "_"]
    for symbol in unwanted_symbols:
        text = text.replace(symbol, "")
    text = text.strip()
    text = remove_leading_spaces_from_each_line(text)
    return text

# 関数6: 文ごとに分割しつつ、各行の先頭空白も確実に削除
def split_sentences(text):
    sentences = re.split(r'[。！？]', text)
    sentences = [remove_leading_spaces_from_each_line(sentence.strip()) for sentence in sentences if sentence.strip()]
    return sentences

# 関数7: セルの途中で分割しないように調整する分割処理
def save_processed_text(sentences, output_dir):
    file_paths = []
    os.makedirs(output_dir, exist_ok=True)
    
    part = []
    total_sentences = 0
    file_index = 1

    for sentence in sentences:
        if total_sentences + len(part) >= 200:
            file_name = f"{output_dir}/processed_part_{file_index}.txt"
            with open(file_name, "w", encoding="utf-8") as file:
                file.write("\n".join(part))
            file_paths.append(file_name)
            part = []
            file_index += 1
            total_sentences = 0

        part.append(sentence)
        total_sentences += 1

    if part:
        file_name = f"{output_dir}/processed_part_{file_index}.txt"
        with open(file_name, "w", encoding="utf-8") as file:
            file.write("\n".join(part))
        file_paths.append(file_name)

    return file_paths

# 関数8: ZIPファイルを作成
def create_zip_from_files(file_paths):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in file_paths:
            zip_file.write(file_path, os.path.basename(file_path))
    zip_buffer.seek(0)
    return zip_buffer

# メイン処理（UI）
def main():
    st.title("digduck")

    uploaded_file = st.file_uploader("CSVファイルをアップロード", type=["csv"])
    if uploaded_file is not None:
        # CSV文字コード選択機能
        encoding_option = st.selectbox(
            "CSVの文字コードを選択してください",
            options=["utf-8 (ほとんどのファイルはこちら)", "shift_jis"],
            index=0
        )
        if "utf-8" in encoding_option.lower():
            encoding = "utf-8"
        else:
            encoding = "shift_jis"
            
        df = pd.read_csv(uploaded_file, encoding=encoding)
        column_name = st.text_input("抽出する記事が格納されている列名を入力", "honbun")
        keywords_input = st.text_input("キーワードをスペース区切りで入力（任意）")
        
        # 2カラムでボタンを横並びに配置
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("記事の絞り込み"):
                keywords = keywords_input.split() if keywords_input else []
                # 関数1～2を使ってフィルタリング処理
                filtered_articles = process_articles(df, keywords, column_name)
                original_count = len(df[column_name])
                filtered_count = len(filtered_articles)
                st.write(f"全 {original_count} 件中、フィルタリングにより {filtered_count} 件の記事が抽出されました。")
                
                # 関数3～9を実施
                all_sentences = []
                for article in filtered_articles[column_name]:
                    cleaned_article = clean_text(article)
                    sentences = split_sentences(cleaned_article)
                    all_sentences.extend(sentences)
                all_sentences = clean_sentences(all_sentences)
                
                output_dir = "/Users/quartermaster/Desktop/python/processed_files"
                file_paths = save_processed_text(all_sentences, output_dir)
                zip_file = create_zip_from_files(file_paths)
                
                st.text_area("処理結果", "\n".join(all_sentences), height=300)
                default_zip_name = uploaded_file.name.rsplit('.', 1)[0] + ".zip"
                download_filename = st.text_input("ダウンロードファイル名を入力してください", default_zip_name)
                st.download_button("処理結果をダウンロード", zip_file, download_filename, mime="application/zip")
        
        with col2:
            if st.button("箇条書き処理をする"):
                # 関数1～2は実施せず、関数3～9のみを実施
                all_sentences = []
                for article in df[column_name]:
                    cleaned_article = clean_text(article)
                    sentences = split_sentences(cleaned_article)
                    all_sentences.extend(sentences)
                all_sentences = clean_sentences(all_sentences)
                
                st.text_area("箇条書き処理結果", "\n".join(all_sentences), height=300)
                
                output_dir = "/Users/quartermaster/Desktop/python/processed_files"
                file_paths = save_processed_text(all_sentences, output_dir)
                zip_file = create_zip_from_files(file_paths)
                
                default_zip_name = uploaded_file.name.rsplit('.', 1)[0] + "_bullet.zip"
                download_filename = st.text_input("ダウンロードファイル名を入力してください", default_zip_name)
                st.download_button("処理結果をダウンロード", zip_file, download_filename, mime="application/zip")

if __name__ == "__main__":
    main()
