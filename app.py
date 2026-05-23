import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import requests
import re
from datetime import datetime

st.set_page_config(page_title="家庭管理", page_icon="🏠", layout="centered")

# ============================================================
# Google Sheets接続
# ============================================================
@st.cache_resource
def get_sheets_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

def get_sheet(name):
    client = get_sheets_client()
    ss = client.open_by_key(st.secrets["SPREADSHEET_ID"])
    return ss.worksheet(name)

# ============================================================
# Groq API
# ============================================================
def call_gemini(prompt):
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {st.secrets['GROQ_API_KEY']}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1024,
                "temperature": 0.7
            },
            timeout=30
        )
        data = res.json()
        if data.get("choices"):
            return data["choices"][0]["message"]["content"]
        return f"APIエラー詳細: {data}"
    except Exception as e:
        return f"接続エラー: {e}"

# ============================================================
# 献立提案
# ============================================================
def page_meal():
    st.header("🍚 献立提案")
    st.caption("和食・時短・栄養バランス重視で提案します")

    if st.button("今日の献立を提案する", use_container_width=True, type="primary"):
        with st.spinner("献立を考えています..."):
            result = call_gemini("""あなたは家庭料理の献立アドバイザーです。
以下の条件で今日の夕食献立を提案してください。

条件：
- 和食中心
- 調理時間30分以内の時短レシピ
- 栄養バランスが良く健康的
- レバーは使用しない
- 家族構成：夫婦＋2歳の男の子

以下の形式で回答してください：

【今日の献立提案】
🍚 主食：
🍖 主菜：（調理時間：〇分）
🥗 副菜：
🍵 汁物：

💡 時短ポイント：（1〜2文）
🌿 栄養ポイント：（1〜2文）""")
            st.success(result)

# ============================================================
# 買い物リスト
# ============================================================
def page_shopping():
    st.header("🛒 買い物リスト")

    sheet = get_sheet("買い物リスト")
    data = sheet.get_all_values()
    active_items = [(i + 2, row[0]) for i, row in enumerate(data[1:])
                    if len(row) >= 3 and row[0] and row[2] not in ("TRUE", True)]

    with st.form("add_item", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            new_item = st.text_input("商品名", placeholder="例：牛乳", label_visibility="collapsed")
        with col2:
            submitted = st.form_submit_button("追加", use_container_width=True)
        if submitted and new_item.strip():
            sheet.append_row([new_item.strip(), "", "FALSE", datetime.now().isoformat()])
            st.rerun()

    st.divider()

    if not active_items:
        st.info("買い物リストは空です")
    else:
        for row_num, name in active_items:
            col1, col2 = st.columns([5, 1])
            with col1:
                st.write(f"• {name}")
            with col2:
                if st.button("✓", key=f"del_{row_num}", use_container_width=True):
                    sheet.update_cell(row_num, 3, "TRUE")
                    st.rerun()

        st.divider()
        if st.button("全削除", use_container_width=True):
            for row_num, _ in active_items:
                sheet.update_cell(row_num, 3, "TRUE")
            st.rerun()

# ============================================================
# お出かけ提案
# ============================================================
def page_outing():
    st.header("🗺 お出かけ提案")
    st.caption("毎週月曜朝にLINEへ自動通知されます")

    if st.button("今すぐ提案を見る", use_container_width=True, type="primary"):
        with st.spinner("お出かけ先を検索中...（20〜30秒かかります）"):
            url_sheet = get_sheet("URLリスト")
            url_data = url_sheet.get_all_values()
            urls = [(row[0], row[1]) for row in url_data[1:]
                    if len(row) >= 3 and row[0] and row[2] not in ("FALSE", False)]

            if not urls:
                st.warning("URLが登録されていません。「🌐 URL」タブからイベントサイトを登録してください。")
                return

            url_content = ""
            failed = []
            now = datetime.now()
            for name, url in urls:
                try:
                    # 年月パターン（/YYYY/MM/）を今月に自動置換
                    fetch_url = re.sub(
                        r'/\d{4}/\d{2}/',
                        f'/{now.year}/{now.month:02d}/',
                        url
                    )
                    res = requests.get(fetch_url, timeout=10,
                                       headers={"User-Agent": "Mozilla/5.0"})
                    text = re.sub(r'<[^>]+>', ' ', res.text)
                    text = re.sub(r'\s+', ' ', text).strip()[:2000]
                    url_content += f"\n【{name}の情報（{now.year}年{now.month}月）】\n{text}\n"
                except Exception:
                    failed.append(name)

            if not url_content:
                st.error("登録されたURLからの情報取得に失敗しました。URLが正しいか確認してください。")
                return

            today = datetime.now().strftime("%Y年%m月%d日")
            result = call_gemini(f"""あなたは子育て家族のお出かけアドバイザーです。
{today}時点で、以下の家族に適したお出かけ先・イベントを3つ提案してください。

【家族構成】夫婦＋2歳の男の子（0〜3歳向けイベントが対象）

【対象エリア（必ずこの5市から選ぶこと）】
立川市・小金井市・府中市・三鷹市・八王子市

【条件】
- 0〜3歳の子どもが楽しめるイベント・場所
- 無料または低コスト優先
- 登録サイトに掲載されているイベントを最優先で提案する
- 登録サイトに情報がない場合は、対象5市内の公民館・子育て支援センター・公園等の一般的な場所を提案してよい

【登録サイトからの情報】
{url_content}

以下の形式で提案してください：

【今週のお出かけ候補🗺】

① 【場所名・イベント名】
📍 市区：
🎯 0〜3歳おすすめ理由：
💰 費用：
⏰ 開催日時・所要時間：
📌 情報元：（登録サイト名 または 一般情報）

② 【場所名・イベント名】
（同上）

③ 【場所名・イベント名】
（同上）

✨ 今週のイチオシ：""")
            if failed:
                st.caption(f"⚠️ 取得できなかったサイト: {', '.join(failed)}")
            st.success(result)

# ============================================================
# 育児・家事相談
# ============================================================
def page_advice():
    st.header("💬 育児・家事相談")

    question = st.text_area("質問を入力してください",
                             placeholder="例：2歳の子どもが野菜を食べてくれません。どうすれば？",
                             height=120)

    if st.button("相談する", use_container_width=True, type="primary"):
        if question.strip():
            with st.spinner("回答を考えています..."):
                result = call_gemini(f"""あなたは2歳の男の子を持つ夫婦をサポートするAIアシスタントです。
育児・家事・料理・子育てに関する質問に親切丁寧に答えてください。
回答は簡潔にまとめ、実践しやすいアドバイスを心がけてください。

家族構成：夫婦＋2歳の男の子

質問：{question}""")
                st.success(result)
        else:
            st.warning("質問を入力してください")

# ============================================================
# URL管理
# ============================================================
def page_urls():
    st.header("🌐 イベントサイト管理")
    st.caption("お出かけ提案の参照先サイトを管理します")

    sheet = get_sheet("URLリスト")
    data = sheet.get_all_values()
    active_urls = [(i + 2, row[0], row[1]) for i, row in enumerate(data[1:])
                   if len(row) >= 3 and row[0] and row[2] not in ("FALSE", False)]

    with st.form("add_url", clear_on_submit=True):
        new_url = st.text_input("URLを入力", placeholder="https://...")
        submitted = st.form_submit_button("追加", use_container_width=True)
        if submitted and new_url.strip():
            match = re.search(r'https?://([^/]+)', new_url)
            name = match.group(1) if match else new_url
            sheet.append_row([name, new_url.strip(), "TRUE", datetime.now().isoformat()])
            st.rerun()

    st.divider()

    if not active_urls:
        st.info("URLが登録されていません")
    else:
        for row_num, name, url in active_urls:
            col1, col2 = st.columns([5, 1])
            with col1:
                st.write(f"📎 {name}")
            with col2:
                if st.button("削除", key=f"url_{row_num}", use_container_width=True):
                    sheet.update_cell(row_num, 3, "FALSE")
                    st.rerun()

# ============================================================
# ナビゲーション
# ============================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🍚 献立", "🛒 買い物", "🗺 お出かけ", "💬 相談", "🌐 URL"])

with tab1:
    page_meal()
with tab2:
    page_shopping()
with tab3:
    page_outing()
with tab4:
    page_advice()
with tab5:
    page_urls()
