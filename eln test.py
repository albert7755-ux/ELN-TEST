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
st.set_page_config(page_title="結構型商品戰情室 (V30.0)", layout="wide")
st.title("📊 結構型商品 - 關鍵點位與長週期風險回測")
st.markdown("回測區間：**2009/01/01 至今**。資料源：**MoneyDJ (經營概述)**。")
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

# --- 3. 核心函數：精準爬蟲 (MoneyDJ 經營概述) ---

def get_headers():
    """偽裝成真實瀏覽器"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]
    return {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.moneydj.com/"
    }

def fetch_moneydj_overview(ticker):
    """
    目標：MoneyDJ 美股 -> 基本資料 (basic0001.xdjhtm) -> 找「經營概述」
    """
    try:
        # 正確的基本資料頁面路徑
        url = f"https://www.moneydj.com/us/basic/basic0001.xdjhtm?a={ticker}"
        
        response = requests.get(url, headers=get_headers(), timeout=6)
        response.encoding = 'utf-8' # 強制編碼

        if response.status_code == 200:
            # 檢查是否被轉址到錯誤頁面 (標題是否包含代碼)
            if ticker not in response.text and ticker.lower() not in response.text:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # MoneyDJ 的資料通常在表格 (table) 裡
            # 我們搜尋所有的 table row (tr)
            rows = soup.find_all('tr')
            
            for row in rows:
                # 找表頭 (th) 或第一格 (td) 是 "經營概述" 的那一列
                text_content = row.get_text()
                if "經營概述" in text_content:
                    # 找到該列後，抓取該列的第二個欄位 (td)
                    # 通常結構是: <th>經營概述</th> <td>內容...</td>
                    cells = row.find_all(['td', 'th'])
                    # 我們要把含有長文字的那一格抓出來
                    for cell in cells:
                        cell_text = cell.get_text().strip()
                        # 排除掉標題本身，且長度足夠長
                        if "經營概述" not in cell_text and len(cell_text) > 20:
                            return cell_text
                            
            # 備用方案：如果表格結構改變，嘗試抓取 article
            article = soup.find('article')
            if article:
                return article.get_text().strip()

        return None
    except Exception:
        return None

def fetch_yahoo_fallback(ticker):
    """備援：Yahoo 奇摩股市 (內容通常與 MoneyDJ 雷同)"""
    try:
        url = f"https://tw.stock.yahoo.com/quote/{ticker}/profile"
        response = requests.get(url, headers=get_headers(), timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 找字數最多的段落
            paragraphs = soup.find_all('p')
            candidates = [p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 50]
            if candidates: return max(candidates, key=len)
        return None
    except Exception:
        return None

def show_tradingview_widget(symbol):
    """最後防線：Widget"""
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
    """整合顯示"""
    container = st.container()
    
    # 1. 優先嘗試 MoneyDJ (經營概述)
    desc = fetch_moneydj_overview(ticker)
    source = "MoneyDJ 理財網"
    
    # 2. 失敗則用 Yahoo
    if not desc:
        desc = fetch_yahoo_fallback(ticker)
        source = "Yahoo 奇摩股市 (備援)"
    
    # 3. 顯示結果
    if desc and len(desc) > 30:
        # 成功抓到文字
        container.markdown(f"""
        <div style="background-color:#f8f9fa; padding:20px; border-radius:10px; border-left: 5px solid #d93025; margin-bottom:20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <h4 style="margin-top:0; color:#202124; font-family:'Microsoft JhengHei';">🏢 {ticker} 經營概述</h4>
            <p style="font-size:15px; line-height:1.8; color:#3c4043; text-align: justify; margin-bottom: 10px;">
                {desc}
            </p>
            <div style="text-align:right; font-size:12px; color:#5f6368;">
                資料來源：{source}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # 都失敗則顯示 Widget
        container.warning("⚠️ 無法取得文字簡介，切換至 TradingView 模式")
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
        # 1. 顯示智慧簡介 (MoneyDJ -> Yahoo)
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
            
            if bt_data is None:
                st.warning("資料不足")
                continue

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新股價", f"{current_price:.2f}")
            c2.metric(f"KO ({ko_pct}%)", f"{p_ko:.2f}")
            c3.metric(f"KI ({ki_pct}%)", f"{p_ki:.2f}", delta_color="inverse")
            c4.metric(f"Strike ({strike_pct}%)", f"{p_st:.2f}")
            
            plot_df = df.tail(750)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['Close'], line=dict(color='black'), name='股價'))
            fig.add_hline(y=p_ko, line_dash="dash", line_color="red")
            fig.add_hline(y=p_ki, line_dash="dot", line_color="orange")
            fig.add_hline(y=p_st, line_color="green")
            fig.update_layout(title=f"{ticker} 關鍵點位 (近3年)", height=400, margin=dict(l=20,r=20,t=40,b=20))
            st.plotly_chart(fig, use_container_width=True)
            
            st.info(f"""
            **📊 {ticker} 分析報告：**
            * **獲利機率**：{stats['pos']:.1f}% (期末股價上漲)
            * **本金安全率**：{stats['safety']:.1f}% (未跌破 KI 或漲回)
            * **風險情境**：若不幸接股 (機率 {100-stats['safety']:.1f}%)，平均需等待 **{stats['rec_days']:.0f} 天** 解套。
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
    <strong>⚠️ 免責聲明</strong>：本工具僅供教學與模擬試算，不代表投資建議。股價資料來源為 Yahoo Finance，發行機構簡介來源為 MoneyDJ/Yahoo 股市。
</div>
""", unsafe_allow_html=True)
