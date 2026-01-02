import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
import numpy as np
import streamlit.components.v1 as components
from deep_translator import GoogleTranslator

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品戰情室 (V34.0)", layout="wide")
st.title("📊 結構型商品 - 關鍵點位與長週期風險回測")
st.markdown("回測區間：**2009/01/01 至今**。資料源：**官方資料庫直連 (無廣告)**。")
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

# --- 3. 核心函數：API 取資料 + AI 翻譯 ---

def get_clean_profile(ticker):
    """
    透過 API 取得官方簡介並翻譯，完全避開網頁廣告。
    """
    try:
        # 1. 連線官方資料庫
        tk = yf.Ticker(ticker)
        
        # 2. 取得 "longBusinessSummary" (這是純文字，沒有任何廣告 HTML)
        eng_summary = tk.info.get('longBusinessSummary', None)
        
        if not eng_summary:
            return None, "官方資料庫無簡介"
            
        # 3. 呼叫 Google 翻譯 (英 -> 繁中)
        translator = GoogleTranslator(source='auto', target='zh-TW')
        
        # 為了翻譯速度與準確度，我們取前 3000 個字元 (通常足夠涵蓋重點)
        cht_summary = translator.translate(eng_summary[:3000])
        
        return cht_summary, "美股官方資料庫 (AI 翻譯)"
        
    except Exception as e:
        return None, str(e)

def show_tradingview_widget(symbol):
    """備案：如果連 API 都失敗才顯示這個"""
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
    """顯示邏輯"""
    container = st.container()
    
    # 呼叫純淨函數
    desc, source = get_clean_profile(ticker)
    
    if desc:
        # 成功！
        container.markdown(f"""
        <div style="background-color:#f8f9fa; padding:20px; border-radius:10px; border-left: 5px solid #0068c9; margin-bottom:20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <h4 style="margin-top:0; color:#202124;">🏢 {ticker} 發行機構簡介</h4>
            <p style="font-size:15px; line-height:1.8; color:#3c4043; text-align: justify; margin-bottom: 5px;">
                {desc}
            </p>
            <div style="text-align:right; font-size:12px; color:#666;">
                資料來源：{source} (無廣告純淨版)
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # 萬一失敗
        container.warning("⚠️ 簡介載入異常，切換至 TradingView 模式")
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

        # 1. 顯示純淨版簡介 (API + 翻譯)
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
    <strong>⚠️ 免責聲明</strong>：本工具僅供教學與模擬試算，不代表投資建議。簡介資料來源為 Yahoo Finance (API) 翻譯。
</div>
""", unsafe_allow_html=True)
