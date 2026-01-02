import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
import numpy as np
import streamlit.components.v1 as components
import requests
from bs4 import BeautifulSoup
import random
from deep_translator import GoogleTranslator

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品戰情室 (V33.0)", layout="wide")
st.title("📊 結構型商品 - 關鍵點位與長週期風險回測")
st.markdown("資料源順序：**Yahoo 奇摩 -> 富途牛牛 -> AI 自動翻譯 (保底機制)**")
st.divider()

# --- 2. 側邊欄 ---
st.sidebar.header("1️⃣ 輸入標的")
default_tickers = "TSLA, NVDA, GOOG"
tickers_input = st.sidebar.text_area("股票代碼 (逗號分隔)", value=default_tickers, height=80)

st.sidebar.divider()
st.sidebar.header("2️⃣ 結構條件 (%)")
ko_pct = st.sidebar.number_input("KO (%)", value=100.0, step=0.5)
strike_pct = st.sidebar.number_input("Strike (%)", value=80.0, step=1.0)
ki_pct = st.sidebar.number_input("KI (%)", value=65.0, step=1.0)

st.sidebar.divider()
st.sidebar.header("3️⃣ 回測參數設定")
period_months = st.sidebar.number_input("觀察天期 (月)", min_value=1, max_value=60, value=6)

run_btn = st.sidebar.button("🚀 開始分析", type="primary")

# --- 3. 核心函數：多重來源爬蟲 ---

def get_headers():
    """偽裝 Header"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]
    return {"User-Agent": random.choice(user_agents)}

def fetch_yahoo_tw_robust(ticker):
    """
    來源 1: Yahoo 奇摩股市 (最穩定)
    策略：不找特定 class，直接找頁面上「最長的一段純文字」，通常就是簡介。
    """
    try:
        url = f"https://tw.stock.yahoo.com/quote/{ticker}/profile"
        response = requests.get(url, headers=get_headers(), timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 抓取所有 p 和 div 標籤
            tags = soup.find_all(['p', 'div'])
            
            candidates = []
            for tag in tags:
                text = tag.get_text().strip()
                # 簡介通常大於 50 字，且不含某些雜訊
                if len(text) > 50 and len(text) < 3000:
                    candidates.append(text)
            
            if candidates:
                # 回傳最長的那一段
                return max(candidates, key=len)
        return None
    except:
        return None

def fetch_futu_profile(ticker):
    """
    來源 2: 富途牛牛 (Futu)
    網址結構: https://www.futunn.com/hk/stock/{ticker}-US/company-profile
    """
    try:
        url = f"https://www.futunn.com/hk/stock/{ticker}-US/company-profile"
        response = requests.get(url, headers=get_headers(), timeout=6)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 富途的簡介通常在特定的 div class 中，但也可能變動
            # 這裡同樣使用「尋找長文字」的通用策略
            divs = soup.find_all('div')
            candidates = []
            for div in divs:
                text = div.get_text().strip()
                if 100 < len(text) < 3000 and "簡介" not in text[:10]: # 避開標題
                    candidates.append(text)
            
            if candidates:
                return max(candidates, key=len)
        return None
    except:
        return None

def fetch_translated_fallback(ticker):
    """
    來源 3: 終極保底 (yfinance API + Google Translate)
    優點：絕對不會被擋 IP，保證有字。
    """
    try:
        tk = yf.Ticker(ticker)
        eng_summary = tk.info.get('longBusinessSummary', "")
        
        if not eng_summary:
            return None
            
        # 進行翻譯
        translator = GoogleTranslator(source='auto', target='zh-TW')
        # 限制長度避免翻譯逾時
        cht_summary = translator.translate(eng_summary[:3000])
        return cht_summary
    except:
        return None

def display_issuer_profile(ticker):
    """
    整合顯示邏輯
    """
    container = st.container()
    
    # 1. 嘗試 Yahoo TW (內容最接近 MoneyDJ/財報狗)
    desc = fetch_yahoo_tw_robust(ticker)
    source = "Yahoo 奇摩股市"
    
    # 2. 失敗 -> 嘗試 富途牛牛
    if not desc:
        desc = fetch_futu_profile(ticker)
        source = "富途牛牛 (Futu)"
        
    # 3. 再失敗 -> 啟動 AI 翻譯 (終極救援)
    if not desc:
        desc = fetch_translated_fallback(ticker)
        source = "AI 自動翻譯 (來源: 美股官方資料)"
    
    # 顯示結果
    if desc:
        container.markdown(f"""
        <div style="background-color:#f8f9fa; padding:20px; border-radius:10px; border-left: 5px solid #28a745; margin-bottom:20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
            <h4 style="margin-top:0; color:#333;">🏢 {ticker} 發行機構簡介</h4>
            <p style="font-size:15px; line-height:1.8; color:#444; text-align: justify; margin-bottom: 5px;">
                {desc}
            </p>
            <div style="text-align:right; font-size:12px; color:#666;">
                資料來源：{source}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # 真的完全沒資料 (非常罕見)
        container.warning(f"⚠️ 暫無 {ticker} 的簡介資料")

# --- 4. 回測核心邏輯 (維持不變) ---

def get_stock_data_from_2009(ticker):
    try:
        start_date = "2009-01-01"
        df = yf.download(ticker, start=start_date, progress=False)
        if df.empty: return None, f"無資料"
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()]
        if 'Close' not in df.columns: return None, "無收盤價"
        df['Date'] = pd.to_datetime(df['Date'])
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df = df.dropna(subset=['Close'])
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA240'] = df['Close'].rolling(window=240).mean()
        return df, None
    except Exception as e: return None, str(e)

def run_backtest(df, ki_pct, strike_pct, months):
    trading_days = int(months * 21)
    bt = df[['Date', 'Close']].copy()
    bt.columns = ['Start_Date', 'Start_Price']
    bt['End_Date'] = bt['Start_Date'].shift(-trading_days)
    bt['Final_Price'] = bt['Start_Price'].shift(-trading_days)
    
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=trading_days)
    bt['Min_Price_During'] = bt['Start_Price'].rolling(window=indexer, min_periods=1).min()
    bt = bt.dropna()
    
    bt['KI_Level'] = bt['Start_Price'] * (ki_pct / 100)
    bt['Strike_Level'] = bt['Start_Price'] * (strike_pct / 100)
    bt['Touched_KI'] = bt['Min_Price_During'] < bt['KI_Level']
    bt['Below_Strike'] = bt['Final_Price'] < bt['Strike_Level']
    
    conditions = [
        (bt['Touched_KI'] == True) & (bt['Below_Strike'] == True),
        (bt['Touched_KI'] == True) & (bt['Below_Strike'] == False),
        (bt['Touched_KI'] == False)
    ]
    bt['Result_Type'] = np.select(conditions, ['Loss', 'Safe', 'Safe'], default='Unknown')
    
    total = len(bt)
    safe_count = len(bt[bt['Result_Type'] == 'Safe'])
    safety_prob = (safe_count / total) * 100
    pos_prob = (len(bt[bt['Final_Price'] > bt['Start_Price']]) / total) * 100
    
    loss_idx = bt[bt['Result_Type'] == 'Loss'].index
    recov_days = []
    stuck = 0
    for idx in loss_idx:
        row = bt.loc[idx]
        fut = df[(df['Date'] > row['End_Date']) & (df['Close'] >= row['Strike_Level'])]
        if not fut.empty: recov_days.append((fut.iloc[0]['Date'] - row['End_Date']).days)
        else: stuck += 1
            
    avg_rec = np.mean(recov_days) if recov_days else 0
    
    bt['Bar_Value'] = np.where(bt['Result_Type'] == 'Loss', 
                               ((bt['Final_Price'] - bt['Strike_Level'])/bt['Strike_Level'])*100, 
                               np.maximum(0, ((bt['Final_Price'] - bt['Strike_Level'])/bt['Strike_Level'])*100))
    bt['Color'] = np.where(bt['Result_Type'] == 'Loss', 'red', 'green')
    
    return bt, {'safety': safety_prob, 'pos': pos_prob, 'loss_cnt': len(loss_idx), 'stuck': stuck, 'rec_days': avg_rec}

def plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st):
    plot_df = df.tail(750).copy()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['Close'], line=dict(color='black'), name='股價'))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['MA20'], line=dict(color='#3498db'), name='月線'))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['MA60'], line=dict(color='#f1c40f'), name='季線'))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['MA240'], line=dict(color='#9b59b6'), name='年線'))

    fig.add_hline(y=p_ko, line_dash="dash", line_color="red")
    fig.add_annotation(x=1, y=p_ko, xref="paper", yref="y", text=f"KO: {p_ko:.2f}", showarrow=False, xanchor="left", font=dict(color="red"))
    fig.add_hline(y=p_st, line_color="green")
    fig.add_annotation(x=1, y=p_st, xref="paper", yref="y", text=f"Strike: {p_st:.2f}", showarrow=False, xanchor="left", font=dict(color="green"))
    fig.add_hline(y=p_ki, line_dash="dot", line_color="orange")
    fig.add_annotation(x=1, y=p_ki, xref="paper", yref="y", text=f"KI: {p_ki:.2f}", showarrow=False, xanchor="left", font=dict(color="orange"))

    all_prices = [p_ko, p_ki, p_st, plot_df['Close'].max(), plot_df['Close'].min()]
    y_min, y_max = min(all_prices)*0.9, max(all_prices)*1.05
    fig.update_layout(title=f"{ticker} 走勢與關鍵價位", height=450, margin=dict(r=80), yaxis_range=[y_min, y_max], hovermode="x unified")
    return fig

# --- 5. 執行主程式 ---

if run_btn:
    ticker_list = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]
    
    for ticker in ticker_list:
        st.markdown(f"### 📌 標的：{ticker}")

        # 1. 顯示智慧簡介 (Yahoo/Futu/AI)
        display_issuer_profile(ticker)
        
        # 2. 執行回測
        with st.spinner(f"正在計算 {ticker} 數據..."):
            df, err = get_stock_data_from_2009(ticker)
            
            if err:
                st.error(f"{ticker} 資料讀取錯誤")
                continue
                
            current_price = df['Close'].iloc[-1]
            p_ko = current_price * (ko_pct/100)
            p_ki = current_price * (ki_pct/100)
            p_st = current_price * (strike_pct/100)
            
            bt_data, stats = run_backtest(df, ki_pct, strike_pct, period_months)
            
            if bt_data is None:
                st.warning("資料不足")
                continue

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新股價", f"{current_price:.2f}")
            c2.metric(f"KO ({ko_pct}%)", f"{p_ko:.2f}")
            c3.metric(f"KI ({ki_pct}%)", f"{p_ki:.2f}", delta_color="inverse")
            c4.metric(f"Strike ({strike_pct}%)", f"{p_st:.2f}")
            
            fig_main = plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st)
            st.plotly_chart(fig_main, use_container_width=True)
            
            loss_pct = 100 - stats['safety_prob']
            stuck_rate = 0
            if stats['loss_count'] > 0:
                stuck_rate = (stats['stuck_count'] / stats['loss_count']) * 100
            
            st.info(f"""
            **📊 回測結果：**
            * **本金安全率**：{stats['safety']:.1f}% (過去16年未發生虧損的機率)
            * **解套時間**：若不幸發生虧損，平均需 **{stats['rec_days']:.0f} 天** 股價可漲回 Strike。
            """)
            
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(x=bt_data['Start_Date'], y=bt_data['Bar_Value'], marker_color=bt_data['Color']))
            fig_bar.update_layout(title="歷史回測損益分佈", height=300, margin=dict(l=20,r=20,t=40,b=20), showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)
            
            st.markdown("---")

else:
    st.info("👈 請在左側設定參數，按下「開始分析」。")

st.markdown("""
<style>
.disclaimer-box {
    background-color: #fff3f3;
    border: 1px solid #e0b4b4;
    padding: 15px;
    border-radius: 5px;
    color: #8a1f1f;
    font-size: 0.9em;
    margin-top: 30px;
}
</style>
<div class='disclaimer-box'>
    <strong>⚠️ 免責聲明</strong>：本工具僅供教學與模擬試算，不代表投資建議。簡介資料來源為 Yahoo/Futu/AI翻譯，內容僅供參考。
</div>
""", unsafe_allow_html=True)
