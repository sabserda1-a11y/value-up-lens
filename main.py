import os
import re
import pandas as pd
import requests
import yfinance as yf
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_stock_map():
    try:
        df = pd.read_csv('stocks.csv', dtype={'code': str})
        return df.set_index('name')['code'].to_dict()
    except:
        return {}

STOCK_MAP = load_stock_map()

@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "Global Hybrid Engine (Naver + Yahoo) is running."}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        
        # 🌟 1. 스마트 라우팅 (한국 vs 미국 구분)
        is_korean = True
        target_symbol = ""

        if query.isdigit():
            # 숫자면 한국 주식
            target_symbol = query.zfill(6)
        elif query in STOCK_MAP:
            # 장부에 있으면 한국 주식 (SK하이닉스 통과!)
            target_symbol = STOCK_MAP[query].zfill(6)
        elif re.match(r'^[A-Za-z]+$', query):
            # 오직 순수 영어로만 되어 있다면 미국 주식! (AAPL, TSLA 등)
            is_korean = False
            target_symbol = query.upper()
        else:
            return {"detail": f"'{query}' 종목을 찾을 수 없습니다."}

        # ==========================================
        # 🇰🇷 2. 한국 주식 로직 (네이버 금융)
        # ==========================================
        if is_korean:
            headers = {"User-Agent": "Mozilla/5.0"}
            symbol = target_symbol
            
            # 실시간 주가
            rt_url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{symbol}"
            rt_res = requests.get(rt_url, headers=headers).json()
            item_data = rt_res['result']['areas'][0]['datas'][0]
            name = item_data['nm']
            current_price = int(str(item_data['nv']).replace(',', ''))
            
            # 120일 차트
            hist_url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=120&requestType=0"
            hist_res = requests.get(hist_url, headers=headers).text
            trend_list, date_list = [], []
            for line in hist_res.split('\n'):
                if '<item data=' in line:
                    parts = line.split('"')[1].split('|')
                    date_list.append(f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:]}")
                    trend_list.append(int(parts[4]))
                    
            # 퀀트 (PBR, PER)
            pbr, per, roe = 0.0, 0.0, 0.0
            main_html = requests.get(f"https://finance.naver.com/item/main.naver?code={symbol}", headers=headers).text
            if 'id="_pbr">' in main_html:
                pbr = float(main_html.split('id="_pbr">')[1].split('</')[0].strip().replace(',', ''))
            if 'id="_per">' in main_html:
                per = float(main_html.split('id="_per">')[1].split('</')[0].strip().replace(',', ''))
            if per > 0 and pbr > 0:
                roe = round((pbr / per) * 100, 2)

            score = min(max(int(50 + (25 if pbr <= 0.8 else -15 if pbr > 2 else 0) + (20 if roe >= 15 else -10 if roe < 0 else 0)), 10), 98)

            return {
                "name": name,
                "price": f"{current_price:,}",
                "currency": "원", # 통화 단위 추가
                "pbr": pbr, "roe": roe, "score": score,
                "trend": trend_list, "dates": date_list
            }

        # ==========================================
        # 🇺🇸 3. 미국 주식 로직 (야후 파이낸스)
        # ==========================================
        else:
            ticker = yf.Ticker(target_symbol)
            info = ticker.info
            
            if 'currentPrice' not in info and 'regularMarketPrice' not in info:
                return {"detail": f"미국 주식 '{target_symbol}' 데이터를 찾을 수 없습니다."}
                
            current_price = info.get('currentPrice', info.get('regularMarketPrice'))
            name = info.get('shortName', target_symbol)
            
            # 미국 주식은 야후가 PBR, ROE를 바로 줍니다!
            pbr = round(info.get('priceToBook', 0), 2)
            roe = round(info.get('returnOnEquity', 0) * 100, 2) if info.get('returnOnEquity') else 0.0
            
            # 차트 데이터 (최근 6개월)
            hist = ticker.history(period="6mo")
            trend_list, date_list = [], []
            if not hist.empty:
                for date, row in hist.iterrows():
                    date_list.append(date.strftime('%Y-%m-%d'))
                    trend_list.append(round(row['Close'], 2)) # 달러는 소수점 유지
            else:
                trend_list = [current_price] * 5
                date_list = ["데이터 없음"] * 5

            score = min(max(int(50 + (15 if 0 < pbr <= 2.0 else 0) + (20 if roe >= 15 else 0)), 10), 98)

            return {
                "name": name,
                "price": f"{current_price:,}", # 소수점 포함 달러 표기
                "currency": "달러", # 미국 주식은 달러!
                "pbr": pbr, "roe": roe, "score": score,
                "trend": trend_list, "dates": date_list
            }

    except Exception as e:
        return {"detail": f"서버 에러: {str(e)}"}
    
# 실행: uvicorn main:app --reload
