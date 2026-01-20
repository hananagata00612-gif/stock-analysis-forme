import streamlit as st
import pandas as pd
import feedparser
import plotly.graph_objects as go
import requests
from datetime import datetime

# --- 1. ページ設定 (ブログ用にタイトルを堅く変更) ---
st.set_page_config(
    page_title="Market Sentiment Analyzer", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. スタイル設定 (迷彩用: 白背景・ダークテキスト) ---
# --- 2. スタイル設定 (迷彩用: 視認性改善版) ---
st.markdown("""
    <style>
        /* 1. 全体の背景を白、基本文字色を濃いグレーに */
        .stApp {
            background-color: #ffffff;
            color: #333333;
        }
        
        /* 2. サイドバーを薄いグレーに */
        section[data-testid="stSidebar"] {
            background-color: #f8f9fa;
        }
        
        /* 3. 見出しなどを強制的に黒く */
        h1, h2, h3, p, label {
            color: #2c3e50 !important;
        }
        
        /* 4. 【重要】プルダウン（Selectbox）の修正 */
        div[data-baseweb="select"] > div {
            background-color: #ffffff !important; /* 背景を白 */
            color: #000000 !important;            /* 文字を黒 */
            border: 1px solid #d1d1d1 !important; /* 枠線をグレーでくっきり */
        }
        
        /* プルダウンの中の文字色 */
        div[data-baseweb="select"] span {
            color: #000000 !important;
        }
        
        /* プルダウンを開いた時のリストの色 */
        ul[data-baseweb="menu"] {
            background-color: #ffffff !important;
        }
        ul[data-baseweb="menu"] li {
            color: #000000 !important;
        }

        /* 5. メトリック（株価の数字）の色 */
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
            color: #000000 !important;
        }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Financial Data Visualizer (Alpha)")

# --- ★APIキー設定 ---
API_KEY = "ここにTwelveDataのキーを貼ってください" 

# 銘柄リスト
FAMOUS_STOCKS = {
    "NVIDIA": "NVDA", "Apple": "AAPL", "Microsoft": "MSFT",
    "Tesla": "TSLA", "Amazon": "AMZN", "Google": "GOOGL",
    "Meta": "META", "Eli Lilly": "LLY", "Pfizer": "PFE",
    "JPMorgan": "JPM"
}

st.sidebar.header("Select Ticker")
selected_name = st.sidebar.selectbox("Symbol", list(FAMOUS_STOCKS.keys()))
ticker = FAMOUS_STOCKS[selected_name]

# --- 関数: ニュース取得 ---
@st.cache_data(ttl=600, show_spinner=False)
def get_google_news(ticker):
    query = f"{ticker} stock"
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(rss_url, headers=headers, timeout=5)
        feed = feedparser.parse(response.content)
        news_items = []
        if feed.entries:
            for entry in feed.entries[:5]:
                news_items.append({
                    'title': entry.title,
                    'link': entry.link,
                    'published': entry.published
                })
        return news_items
    except Exception:
        return []

# --- 関数: 株価取得 ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_price(ticker, api_key):
    if "ここに" in api_key:
        return None, "KeyError"

    url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1day&outputsize=365&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10).json()
        
        if "values" not in response:
            return None, "ApiLimit"
            
        df = pd.DataFrame(response['values'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        
        cols = ['open', 'high', 'low', 'close']
        for c in cols:
            df[c] = pd.to_numeric(df[c])
        df = df.sort_index()
        df.columns = [c.capitalize() for c in df.columns]
        
        return df, "Success"
    except Exception:
        return None, "ConnectionError"

# --- 分析ロジック ---
def analyze_market(df, news_list):
    if df is None or len(df) < 20:
        return "Insufficient Data", [], "gray"

    current = df['Close'].iloc[-1]
    sma_50 = df['Close'].rolling(window=50).mean().iloc[-1]
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1] if not rsi.empty else 50

    score = 0
    reasons = []

    if current > sma_50:
        score += 1
        reasons.append(f"📈 [Trend] Bullish (${current:.2f} > SMA50)")
    else:
        score -= 1
        reasons.append(f"📉 [Trend] Bearish (${current:.2f} < SMA50)")

    if current_rsi < 30:
        score += 2
        reasons.append(f"🟢 [RSI] Oversold ({current_rsi:.0f})")
    elif current_rsi > 70:
        score -= 2
        reasons.append(f"🔴 [RSI] Overbought ({current_rsi:.0f})")
    else:
        reasons.append(f"⚖️ [RSI] Neutral ({current_rsi:.0f})")

    keywords_good = ['surge', 'jump', 'record', 'buy', 'beat', 'profit', 'high']
    keywords_bad = ['drop', 'fall', 'miss', 'loss', 'cut', 'low', 'fail']
    
    news_score = 0
    if news_list:
        for n in news_list:
            t = n['title'].lower()
            if any(w in t for w in keywords_good): news_score += 1
            if any(w in t for w in keywords_bad): news_score -= 1
    
    if news_score > 0:
        score += 1
        reasons.append("📰 [News] Positive Sentiment")
    elif news_score < 0:
        score -= 1
        reasons.append("📰 [News] Negative Sentiment")

    if score >= 2:
        judgment, color = "Strong Buy", "#d9534f" # 赤 (白背景用)
    elif score == 1:
        judgment, color = "Buy", "#f0ad4e" # オレンジ
    elif score <= -1:
        judgment, color = "Sell", "#0275d8" # 青
    else:
        judgment, color = "Hold", "gray"

    return judgment, reasons, color

# --- メイン処理 ---
with st.status("Analyzing Market Data...", expanded=True) as status:
    
    st.write("Fetching Market Data...")
    df, api_status = get_stock_price(ticker, API_KEY)
    
    if api_status == "Success":
        st.write("✅ Market Data Loaded")
    else:
        st.write("⚠️ Data Fetching Issue")

    st.write("Scanning News Headlines...")
    news_items = get_google_news(ticker)
    st.write("✅ News Scan Complete")
    
    status.update(label="Analysis Complete", state="complete", expanded=False)

if api_status == "KeyError":
    st.error("⚠️ Please set your API Key.")
elif api_status != "Success" or df is None:
    st.error("Data fetch error. Please reload.")
else:
    current = df['Close'].iloc[-1]
    prev = df['Close'].iloc[-2]
    change = current - prev
    pct = (change / prev) * 100
    
    col1, col2 = st.columns(2)
    col1.metric("Current Price", f"${current:.2f}")
    col2.metric("Change", f"{change:+.2f} ({pct:+.2f}%)")

    judgment, reasons, color = analyze_market(df, news_items)
    
    # 判定ボックス (白背景に合わせて調整)
    st.markdown(f"""
    <div style="border: 2px solid {color}; padding: 15px; border-radius: 10px; margin: 20px 0; text-align: center; background-color: #f9f9f9;">
        <h2 style="color: {color}; margin:0;">AI Verdict: {judgment}</h2>
    </div>
    """, unsafe_allow_html=True)
    
    for r in reasons:
        st.write(r)

    st.subheader("📈 Price Chart")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index,
                    open=df['Open'], high=df['High'],
                    low=df['Low'], close=df['Close'], name='Price'))
    fig.update_layout(
        height=400, 
        margin=dict(l=20, r=20, t=20, b=20),
        plot_bgcolor='white', # チャート背景も白に
        paper_bgcolor='white',
        font=dict(color='black')
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📰 Latest News")
    if news_items:
        for news in news_items:
            pub = news['published'][:16]
            st.markdown(f"**[{news['title']}]({news['link']})**")
            st.caption(f"📅 {pub}")
    else:
        st.info("No news found.")
