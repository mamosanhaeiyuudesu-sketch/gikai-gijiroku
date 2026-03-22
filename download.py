import os
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def download_pdfs(url, save_dir="gijiroku"):
    # 保存用ディレクトリの作成
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        print(f"ディレクトリ '{save_dir}' を作成しました。")

    # ページのHTMLを取得
    try:
        response = requests.get(url)
        response.raise_for_status()  # エラーがあれば例外を発生させる
        response.encoding = response.apparent_encoding # 文字化け対策
    except Exception as e:
        print(f"ページの取得に失敗しました: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')

    # すべての<a>タグ（リンク）を取得
    links = soup.find_all('a')
    
    pdf_count = 0
    for link in links:
        href = link.get('href')
        if href and href.endswith('.pdf'):
            # 相対パスを絶対URLに変換
            pdf_url = urljoin(url, href)
            
            # ファイル名を取得（URLの最後）
            file_name = os.path.join(save_dir, href.split('/')[-1])

            print(f"ダウンロード中: {pdf_url}")
            
            try:
                # PDFをダウンロード
                pdf_res = requests.get(pdf_url)
                with open(file_name, 'wb') as f:
                    f.write(pdf_res.content)
                pdf_count += 1
                
                # サーバーに負荷をかけないよう少し待機（1秒）
                time.sleep(1)
                
            except Exception as e:
                print(f"ダウンロード失敗 ({pdf_url}): {e}")

    print(f"\n完了！合計 {pdf_count} 個のPDFを保存しました。")

if __name__ == "__main__":
    target_url = "https://www.city.miyakojima.lg.jp/gyosei/gikai/gijiroku.html"
    download_pdfs(target_url)
