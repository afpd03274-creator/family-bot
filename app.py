import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import requests
import re
import json
import calendar as cal_module
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
def call_gemini(prompt, max_tokens=1500):
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
                "max_tokens": max_tokens,
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
# 献立提案（7日分・豚ロース薄切り）
# ============================================================
def page_meal():
    st.header("🍚 献立提案")
    st.caption("豚ロース薄切り使用・2人分・オーブン不使用・7日分")

    if 'meal_plan' not in st.session_state:
        st.session_state.meal_plan = None

    btn_col, add_col = st.columns([3, 2])
    with btn_col:
        if st.button("7日分の献立を作成", use_container_width=True, type="primary"):
            with st.spinner("献立を考えています...（30秒ほどかかります）"):
                raw = call_gemini(
                    f"7日分の豚ロース薄切りを使った夕食献立（2人分・オーブン不使用・和食中心・各30分以内）を"
                    f"以下のJSON形式のみで返してください。前置きや説明は不要です。\n\n"
                    f'{{"plan":['
                    f'{{"day":"月","name":"料理名","time":"〇分","ingredients":["食材 分量"],"description":"1文説明","url":"https://cookpad.com/search/豚ロース薄切り+料理名キーワード"}},'
                    f'{{"day":"火","name":"...","time":"...","ingredients":[...],"description":"...","url":"..."}},'
                    f'{{"day":"水","name":"...","time":"...","ingredients":[...],"description":"...","url":"..."}},'
                    f'{{"day":"木","name":"...","time":"...","ingredients":[...],"description":"...","url":"..."}},'
                    f'{{"day":"金","name":"...","time":"...","ingredients":[...],"description":"...","url":"..."}},'
                    f'{{"day":"土","name":"...","time":"...","ingredients":[...],"description":"...","url":"..."}},'
                    f'{{"day":"日","name":"...","time":"...","ingredients":[...],"description":"...","url":"..."}}],'
                    f'"shopping":[{{"item":"食材名","amount":"7日分の合計量","price":円}}],'
                    f'"budget":合計円}}',
                    max_tokens=2000
                )
                try:
                    m = re.search(r'\{[\s\S]*\}', raw)
                    if m:
                        st.session_state.meal_plan = json.loads(m.group())
                    else:
                        st.error("献立の生成に失敗しました。もう一度お試しください。")
                except Exception:
                    st.error("献立データの解析に失敗しました。もう一度お試しください。")

    plan = st.session_state.meal_plan

    if plan:
        with add_col:
            if st.button("🛒 買い物リストに追加", use_container_width=True):
                sheet = get_sheet("買い物リスト")
                shopping = plan.get('shopping', [])
                for item in shopping:
                    name = f"{item.get('item', '')} {item.get('amount', '')}".strip()
                    sheet.append_row([name, "", "FALSE", datetime.now().isoformat()])
                st.success(f"{len(shopping)}品目を買い物リストに追加しました！")
                st.rerun()

        st.caption("⚠️ リンクはクックパッドの検索結果です。口コミ10件以上のレシピをご自身でお選びください。")

        days = plan.get('plan', [])
        for day in days:
            with st.expander(
                f"**{day.get('day', '')}曜日**　{day.get('name', '')}　⏱ {day.get('time', '')}",
                expanded=False
            ):
                if day.get('description'):
                    st.write(day['description'])
                st.markdown("**材料（2人分）**")
                for ing in day.get('ingredients', []):
                    st.write(f"• {ing}")
                if day.get('url'):
                    st.markdown(f"🔗 [クックパッドで検索]({day['url']})")

        st.divider()
        st.subheader("🛒 1週間分の材料まとめ")
        shopping = plan.get('shopping', [])
        total = 0
        for item in shopping:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"• {item.get('item', '')}　{item.get('amount', '')}")
            with c2:
                p = item.get('price', 0)
                if p:
                    st.write(f"¥{p:,}")
                    total += p
        st.divider()
        budget = plan.get('budget', total)
        st.metric("1週間の想定予算", f"¥{budget:,}" if budget else "-")

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
def _fetch_url_text(url, now, req_headers):
    fetch_url = re.sub(r'/\d{4}/\d{2}/', f'/{now.year}/{now.month:02d}/', url)
    res = requests.get(fetch_url, timeout=10, headers=req_headers)
    fallback = False
    if res.status_code == 403:
        m = re.match(r'(https?://[^/]+)', fetch_url)
        if m:
            fetch_url = m.group(1) + "/"
            res = requests.get(fetch_url, timeout=10, headers=req_headers)
            fallback = True
    if res.status_code != 200:
        raise Exception(f"HTTP {res.status_code}")
    html = res.content.decode('utf-8', errors='replace')
    html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()[:4000]
    return text, fetch_url, fallback


def page_outing():
    st.header("🗺 お出かけ提案")
    st.caption("毎週月曜朝にLINEへ自動通知されます")

    for key, val in [('outing_events', []), ('outing_day', None), ('outing_notices', [])]:
        if key not in st.session_state:
            st.session_state[key] = val

    col_main, col_cal = st.columns([3, 2])

    with col_main:
        if st.button("今すぐ提案を見る", use_container_width=True, type="primary"):
            st.session_state.outing_day = None
            with st.spinner("お出かけ先を検索中...（20〜30秒かかります）"):
                url_sheet = get_sheet("URLリスト")
                url_data = url_sheet.get_all_values()
                urls = [(row[0], row[1]) for row in url_data[1:]
                        if len(row) >= 3 and row[0] and row[2] not in ("FALSE", False)]

                if not urls:
                    st.warning("URLが登録されていません。「🌐 URL」タブからイベントサイトを登録してください。")
                else:
                    req_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
                    }
                    now = datetime.now()
                    url_content = ""
                    failed, fallback_used = [], []
                    for name, url in urls:
                        try:
                            text, fetch_url, fb = _fetch_url_text(url, now, req_headers)
                            if fb:
                                fallback_used.append(name)
                            url_content += f"\n【サイト名：{name}｜URL：{fetch_url}】\n{text}\n"
                        except Exception:
                            failed.append(name)

                    notices = []
                    if fallback_used:
                        notices.append(f"ℹ️ トップページで代替取得: {', '.join(fallback_used)}")
                    if failed:
                        notices.append(f"⚠️ 取得できなかったサイト: {', '.join(failed)}")
                    st.session_state.outing_notices = notices

                    if url_content:
                        today_str = now.strftime("%Y年%m月%d日")
                        raw = call_gemini(f"""あなたは子育て家族のイベント情報アドバイザーです。
以下の【登録サイトからの情報】から確認できるイベントをすべて抽出し、JSON配列として返してください。

【重要なルール】
- 具体的な「開催イベント」のみ（場所紹介・施設案内は除外）
- イベント名と開催日が明確なものだけを含める
- 登録サイトに掲載されていないイベントは追加しない
- 日付はYYYY-MM-DD形式（年が不明なら{now.year}を使用）
- JSON配列のみを返す（前置き・説明文は不要）

【今日の日付】{today_str}

【登録サイトからの情報】
{url_content}

以下のJSON形式で返してください：
[
  {{
    "name": "イベント名",
    "date": "YYYY-MM-DD",
    "date_display": "〇月〇日（曜日）",
    "location": "開催場所・市区",
    "age": "対象年齢",
    "fee": "参加費",
    "description": "内容（1〜2文）",
    "url": "情報元URL"
  }}
]""")
                        events = []
                        try:
                            m = re.search(r'\[[\s\S]*\]', raw)
                            if m:
                                events = json.loads(m.group())
                        except Exception:
                            pass
                        events.sort(key=lambda e: e.get('date', ''))
                        st.session_state.outing_events = events
                        if not events:
                            st.warning("イベント情報を抽出できませんでした。登録サイトに今月のイベント情報があるか確認してください。")

        for notice in st.session_state.outing_notices:
            st.caption(notice)

        events = st.session_state.outing_events
        selected_day = st.session_state.outing_day

        if events:
            if selected_day:
                filtered = [e for e in events if e.get('date', '') == selected_day]
                try:
                    d = datetime.strptime(selected_day, '%Y-%m-%d')
                    label = d.strftime(f"{d.month}月{d.day}日")
                except Exception:
                    label = selected_day
                st.markdown(f"**{label}のイベント（{len(filtered)}件）**")
                if st.button("← 全件表示に戻る"):
                    st.session_state.outing_day = None
                    st.rerun()
            else:
                filtered = events
                st.markdown(f"**全イベント（{len(filtered)}件）**")

            for event in filtered:
                with st.expander(
                    f"📅 {event.get('date_display', '')}　{event.get('name', '')}",
                    expanded=True
                ):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"📍 {event.get('location', '-')}")
                        st.write(f"👶 {event.get('age', '-')}")
                    with c2:
                        st.write(f"💰 {event.get('fee', '-')}")
                        if event.get('url'):
                            st.markdown(f"🔗 [詳細はこちら]({event['url']})")
                    if event.get('description'):
                        st.write(event['description'])

    with col_cal:
        events = st.session_state.outing_events
        if events:
            now = datetime.now()

            date_counts = {}
            for e in events:
                d_str = e.get('date', '')
                if d_str:
                    date_counts[d_str] = date_counts.get(d_str, 0) + 1

            selected_day = st.session_state.outing_day

            for offset in range(3):
                month_total = now.month - 1 + offset
                yr = now.year + month_total // 12
                mo = month_total % 12 + 1

                st.markdown(
                    f"<div style='font-weight:bold;margin-top:10px;margin-bottom:2px'>"
                    f"📅 {yr}年{mo}月</div>",
                    unsafe_allow_html=True
                )

                hcols = st.columns(7)
                for i, lbl in enumerate(['月', '火', '水', '木', '金', '土', '日']):
                    hcols[i].markdown(
                        f"<div style='text-align:center;font-weight:bold;font-size:11px'>{lbl}</div>",
                        unsafe_allow_html=True
                    )

                for week in cal_module.monthcalendar(yr, mo):
                    wcols = st.columns(7)
                    for i, day in enumerate(week):
                        if day == 0:
                            wcols[i].write("")
                        else:
                            date_key = f"{yr}-{mo:02d}-{day:02d}"
                            count = date_counts.get(date_key, 0)
                            if count > 0:
                                is_sel = selected_day == date_key
                                if wcols[i].button(
                                    f"{'✓' if is_sel else ''}{day}",
                                    key=f"cal_{date_key}",
                                    use_container_width=True,
                                    type="primary" if is_sel else "secondary"
                                ):
                                    st.session_state.outing_day = None if is_sel else date_key
                                    st.rerun()
                            else:
                                wcols[i].markdown(
                                    f"<div style='text-align:center;color:#999;"
                                    f"font-size:12px;padding:3px'>{day}</div>",
                                    unsafe_allow_html=True
                                )

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
