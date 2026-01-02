import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
import numpy as np
import streamlit.components.v1 as components
import requests
from bs4 import BeautifulSoup
import random

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品戰情室 (V29.0)", layout="wide")
st.title("📊 結構型商品 - 關鍵點位與長週期風險回測")
st.markdown("回測區間：**2009/01/01 至今**。資料源：**MoneyDJ (優先) / Yahoo TW (備援)**")
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

# --- 3. 核心函數：精準爬蟲 ---

def get_headers():
    """偽裝成真實瀏覽器，避免被 MoneyDJ 視為機器人"""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.moneydj.com/"
    }

def fetch_moneydj_profile(ticker):
    """
    爬取 MoneyDJ -> 基本資料 -> 公司資料 (rgprofile)
    """
    try:
        # 這是 MoneyDJ 美股「公司資料」的專屬路徑
        url = f"https://www.moneydj.com/us/basic/uslookup.svc/rgprofile?stk={ticker}"
        
        # 使用 Session 來維持連線狀態
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=5)
        response.encoding = 'utf-8'

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # MoneyDJ 結構特徵：
            # 公司簡介通常放在一個 table 裡面，標題是 "經營概述" 或 "公司簡介"
            # 我們直接抓取含有大量文字的 <article> 或 <td>
            
            # 策略 1: 抓取 article (MoneyDJ 常用)
            article = soup.find('article')
            if article:
                text = article.get_text().strip()
                if len(text) > 50: return text

            # 策略 2: 抓取表格內容
            # 尋找所有 td，如果內容包含中文且長度夠長，通常就是簡介
            tds = soup.find_all('td')
            for td in tds:
                text = td.get_text().strip()
                # 排除選單文字，通常簡介會很長
                if len(text) > 100 and "公司簡介" not in text[:20]:
                    return text
                    
        return None
    except Exception:
        return None

def fetch_yahoo_tw_profile(ticker):
    """
    備援：爬取 Yahoo 奇摩股市 (美股)
    """
    try:
        url = f"https://tw.stock.yahoo.com/quote/{ticker}/profile"
        response = requests.get(url, headers=get_headers(), timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Yahoo 的簡介通常在 class="Py(12px)" 或 "Mb(20px)" 的 div 裡
            # 我們直接找頁面中「字數最多」的那個段落 (p tag)
            paragraphs = soup.find_all('p')
            
            # 過濾出最有可能是簡介的段落
            candidates = [p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 100]
            
            if candidates:
                # 回傳最長的那一段
                return max(candidates, key=len)
                
        return None
    except Exception:
        return None

def show_tradingview_widget(symbol):
    """最後防線：TradingView Widget"""
    html_code = f"""
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-symbol-profile.js" async>
      {{
      "width": "100%",
      "height": "300",
      "colorTheme": "light",
      "isTransparent": false,
      "symbol": "{symbol}",
      "locale": "zh_TW"
      }}
      </script>
    </div>
    """
    components.html(html_code, height=310)

def display_smart_profile(ticker):
    """
    智慧顯示邏輯：
    1. 先試 MoneyDJ (精準路徑)
    2. 失敗 -> 試 Yahoo TW
    3. 失敗 -> 顯示 TradingView Widget
    """
    # 建立一個容器，避免畫面跳動
    container = st.container()
    
    # 1. 嘗試 MoneyDJ
    desc = fetch_moneydj_profile(ticker)
    source = "MoneyDJ 理財網"
    
    # 2. 如果 MoneyDJ 失敗 (回傳 None 或太短)，切換 Yahoo
    if not desc or len(desc) < 50:
        desc = fetch_yahoo_tw_profile(ticker)
        source = "Yahoo 奇摩股市"
    
    if desc and len(desc) > 50:
        # 成功抓到純文字
        container.markdown(f"""
        <div style="background-color:#f8f9fa; padding:15px; border-radius:10px; border-left: 5px solid #ff4b4b; margin-bottom:20px;">
            <h4 style="margin-top:0; color:#333;">🏢 發行機構簡介：{ticker}</h4>
            <p style="font-size:15px; line-height:1.6; color:#444; text-align: justify; margin-bottom: 5px;">
                {desc}
            </p>
            <div style="text-align:right; font-size:12px; color:#888;">
                資料來源：{source}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # 3. 都失敗，顯示 Widget
        container.warning(f"⚠️ 無法取得中文純文字簡介，切換至 TradingView 完整模式")
        show_tradingview_widget(ticker)

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
    
    # 統計
    total = len(bt)
    safe_count = len(bt[bt['Result_Type'] == 'Safe'])
    safety_prob = (safe_count / total) * 100
    pos_prob = (len(bt[bt['Final_Price'] > bt['Start_Price']]) / total) * 100
    
    # 損失恢復天數
    loss_idx = bt[bt['Result_Type'] == 'Loss'].index
    recov_days = []
    stuck = 0
    for idx in loss_idx:
        row = bt.loc[idx]
        fut = df[(df['Date'] > row['End_Date']) & (df['Close'] >= row['Strike_Level'])]
        if not fut.empty: recov_days.append((fut.iloc[0]['Date'] - row['End_Date']).days)
        else: stuck += 1
            
    avg_rec = np.mean(recov_days) if recov_days else 0
    
    # Bar Chart Data
    bt['Bar_Value'] = np.where(bt['Result_Type'] == 'Loss', 
                               ((bt['Final_Price'] - bt['Strike_Level'])/bt['Strike_Level'])*100, 
                               np.maximum(0, ((bt['Final_Price'] - bt['Strike_Level'])/bt['Strike_Level'])*100))
    bt['Color'] = np.where(bt['Result_Type'] == 'Loss', 'red', 'green')
    
    return bt, {'safety': safety_prob, 'pos': pos_prob, 'loss_cnt': len(loss_idx), 'stuck': stuck, 'rec_days': avg_rec}

# --- 5. 執行主程式 ---

if run_btn:
    ticker_list = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]
    
    for ticker in ticker_list:
        # 1. 顯示智慧簡介 (MoneyDJ -> Yahoo -> Widget)
        display_smart_profile(ticker)
        
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
            
            # 3. 顯示重點指標
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新股價", f"{current_price:.2f}")
            c2.metric(f"KO ({ko_pct}%)", f"{p_ko:.2f}")
            c3.metric(f"KI ({ki_pct}%)", f"{p_ki:.2f}", delta_color="inverse")
            c4.metric(f"Strike ({strike_pct}%)", f"{p_st:.2f}")
            
            # 4. 顯示主圖
            plot_df = df.tail(750)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['Close'], line=dict(color='black'), name='股價'))
            fig.add_hline(y=p_ko, line_dash="dash", line_color="red")
            fig.add_hline(y=p_ki, line_dash="dot", line_color="orange")
            fig.add_hline(y=p_st, line_color="green")
            fig.update_layout(title=f"{ticker} 關鍵點位 (近3年)", height=400, margin=dict(l=20,r=20,t=40,b=20))
            st.plotly_chart(fig, use_container_width=True)
            
            # 5. 顯示解釋文字
            st.info(f"""
            **📊 {ticker} 分析報告：**
            * **獲利機率**：{stats['pos']:.1f}% (期末股價上漲)
            * **本金安全率**：{stats['safety']:.1f}% (未跌破 KI 或漲回)
            * **風險情境**：若不幸接股 (機率 {100-stats['safety']:.1f}%)，平均需等待 **{stats['rec_days']:.0f} 天** 解套。
            """)
            
            # 6. 顯示 Bar Chart
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(x=bt_data['Start_Date'], y=bt_data['Bar_Value'], marker_color=bt_data['Color']))
            fig_bar.update_layout(title="歷史回測損益分佈", height=300, margin=dict(l=20,r=20,t=40,b=20), showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)
            
            st.markdown("---")
