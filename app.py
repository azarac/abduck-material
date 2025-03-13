import os
import re
import io
import zipfile
import string
import pandas as pd
import streamlit as st
import MeCab

# MeCabの準備
mecab = MeCab.Tagger("-r /etc/mecabrc -Ochasen")

# 役職リスト（よくある役職名を追加）
job_titles = ["代表", "取締役", "部長", "社長", "専務", "理事", "監査役", "役員", 
              "議員", "審議官", "教授", "会長", "研究員"]

# 記事の文章単位で「人名 + 役職」の割合を計算し、名詞・動詞の割合も取得
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

# 記事の精査関数
def process_articles(df, keywords, column_name):
    if keywords:
        filtered_df = df[df[column_name].str.contains('|'.join(keywords), na=False)]
    else:
        filtered_df = df.copy()

    # x000D比率フィルタ
    filtered_df['x000D_ratio'] = filtered_df[column_name].apply(
        lambda x: x.count('x000D') / len(x) if isinstance(x, str) else 0
    )
    filtered_df = filtered_df[filtered_df['x000D_ratio'] < 0.018]

    # 名詞・動詞・人名 + 役職の割合を計算
    filtered_df[['noun_ratio', 'verb_ratio', 'people_job_sentence_ratio']] = \
        filtered_df[column_name].apply(lambda x: pd.Series(calculate_text_ratios(str(x))))

    # **名詞の割合が 80% 以上 & 動詞の割合が 5% 以下の記事を除外**
    filtered_df = filtered_df[(filtered_df['noun_ratio'] < 0.8) | (filtered_df['verb_ratio'] > 0.05)]

    # **「人名 + 役職の文章割合が50%以上」なら除外**
    filtered_df = filtered_df[filtered_df['people_job_sentence_ratio'] < 0.5]

    return filtered_df

# 各行の先頭空白を除去する補助関数
def remove_leading_spaces_from_each_line(text):
    return "\n".join(line.lstrip() for line in text.splitlines())

# 記号だけの文章を削除し、各行の先頭空白も取り除く関数
def clean_sentences(sentences):
    cleaned_sentences = []
    for sentence in sentences:
        # 全体の余分な空白を除去
        sentence = sentence.strip()
        # 各行ごとに先頭の空白を除去
        sentence = remove_leading_spaces_from_each_line(sentence)
        if any(char.isalnum() or char in "ぁ-ゔァ-ヴ一-龠々〆ヵヶ" for char in sentence):
            cleaned_sentences.append(sentence)
    return cleaned_sentences

# 不要な記号の削除 & 文頭の空白削除
def clean_text(text):
    unwanted_symbols = ["●", "■", "×", "▼", "◇", "x000D", "＿", "_"]
    for symbol in unwanted_symbols:
        text = text.replace(symbol, "")
    # 全体の余分な空白を除去
    text = text.strip()
    # 各行ごとに先頭の空白を除去
    text = remove_leading_spaces_from_each_line(text)
    return text

# 文ごとに分割しつつ、各行の先頭空白も確実に削除
def split_sentences(text):
    sentences = re.split(r'[。！？]', text)
    sentences = [
        remove_leading_spaces_from_each_line(sentence.strip())
        for sentence in sentences if sentence.strip()
    ]
    return sentences

# **セルの途中でファイルが分かれないように調整する分割処理**
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

# ZIPファイルを作成
def create_zip_from_files(file_paths):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in file_paths:
            zip_file.write(file_path, os.path.basename(file_path))
    zip_buffer.seek(0)
    return zip_buffer

# メイン処理
def main():
    st.title("abduck material ver.1")

    uploaded_file = st.file_uploader("CSVファイルをアップロード", type=["csv"])
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)

        column_name = st.text_input("抽出する記事が格納されている列名を入力", "honbun")
        keywords_input = st.text_input("キーワードをスペース区切りで入力（任意）")

        if st.button("記事の絞り込み"):
            keywords = keywords_input.split() if keywords_input else []
            filtered_articles = process_articles(df, keywords, column_name)
            st.write(f"{len(filtered_articles)}件の記事が抽出されました。")

            all_sentences = []
            for article in filtered_articles[column_name]:
                cleaned_article = clean_text(article)
                sentences = split_sentences(cleaned_article)
                all_sentences.extend(sentences)

            # 記号だけの文章を削除し、各行の先頭空白も取り除く処理
            all_sentences = clean_sentences(all_sentences)

            # **セルの途中で分割しないように調整**
            output_dir = "/Users/quartermaster/Desktop/python/processed_files"
            file_paths = save_processed_text(all_sentences, output_dir)
            zip_file = create_zip_from_files(file_paths)

            # 結果を表示
            st.text_area("処理結果", "\n".join(all_sentences), height=300)

            # ダウンロードファイル名の設定（アップロードファイル名を元にデフォルト設定）
            default_zip_name = uploaded_file.name.rsplit('.', 1)[0] + ".zip"
            download_filename = st.text_input("ダウンロードファイル名を入力してください", default_zip_name)
            
            # ダウンロードボタン（ユーザーが入力したファイル名を使用）
            st.download_button("処理結果をダウンロード", zip_file, download_filename, mime="application/zip")

# Heroku対応: ポートを指定して起動
if __name__ == "__main__":
    main()
