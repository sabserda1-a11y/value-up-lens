import os
import re
import pandas as pd
import requests
from datetime import datetime  # 🌟 날짜 변환을 위해 새로 추가된 도구!
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
    return {"status": "alive", "message": "Pure API Engine (No yfinance) is running."}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        is_korean = True
        target_symbol = ""

        if query.isdigit():
            target_symbol = query.zfill(6)
        elif query in STOCK_MAP:
            target_symbol = STOCK_MAP[query].zfill(6)
        elif re.match(r'^[A-Za-z]+$', query):
            is_korean = False
            target_symbol = query.upper()
        else:
            return {"detail": f"'{query}' 종목을 찾을 수 없습니다."}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # ==========================================
        # 🇰🇷 1. 한국 주식 로직 (기존과 동일)
        # ==========================================
        if is_korean:
            symbol = target_symbol
            rt_url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{symbol}"
            rt_res = requests.get(rt_url, headers=headers).json()
            item_data = rt_res['result']['areas'][0]['datas'][0]
            name = item_data['nm']
            current_price = int(str(item_data['nv']).replace(',', ''))
            
            hist_url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=120&requestType=0"
            hist_res = requests.get(hist_url, headers=headers).text
            trend_list, date_list = [], []
            for line in hist_res.split('\n'):
                if '<item data=' in line:
                    parts = line.split('"')[1].split('|')
                    date_list.append(f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:]}")
                    trend_list.append(int(parts[4]))
                    
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
                "currency": "원",
                "pbr": pbr, "roe": roe, "score": score,
                "trend": trend_list, "dates": date_list
            }

        # ==========================================
        # 🇺🇸 2. 미국 주식 로직 (yfinance 삭제! 100% 순수 API 직접 통신)
        # ==========================================
        else:
            # 1단계: 차트와 현재가 (야후의 진짜 숨겨진 차트 API 직접 찌르기)
            chart_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{target_symbol}?interval=1d&range=6mo"
            chart_res = requests.get(chart_url, headers=headers)
            
            if chart_res.status_code != 200:
                return {"detail": f"미국 주식 '{target_symbol}' 차트 데이터를 불러올 수 없습니다."}
                
            chart_data = chart_res.json()
            result = chart_data['chart']['result'][0]
            
            # 시간(timestamp)과 가격(close) 데이터를 직접 빼옵니다.
            timestamps = result.get('timestamp', [])
            closes = result['indicators']['quote'][0].get('close', [])
            
            trend_list = []
            date_list = []
            
            for t, c in zip(timestamps, closes):
                if c is not None:
                    # 복잡한 숫자로 된 시간을 '2026-03-08' 형태로 예쁘게 바꿉니다.
                    dt = datetime.fromtimestamp(t).strftime('%Y-%m-%d')
                    date_list.append(dt)
                    trend_list.append(round(c, 2))
                    
            if not trend_list:
                return {"detail": f"미국 주식 '{target_symbol}' 차트 데이터가 비어있습니다."}
                
            current_price = trend_list[-1]

            # 2단계: 퀀트 데이터 (네이버 해외주식 API)
            name = target_symbol
            pbr = 0.0
            per = 0.0
            roe = 0.0
            
            try:
                # NVDA를 검색해서 네이버 전용 코드(NVDA.O)를 찾아냅니다.
                search_url = f"https://m.stock.naver.com/api/search/all?keyword={target_symbol}"
                search_res = requests.get(search_url, headers=headers).json()
                
                reuters_code = ""
                for item in search_res.get('searchList', []):
                    if item.get('stockType') == 'worldstock' and item.get('symbolCode', '').upper() == target_symbol:
                        reuters_code = item.get('reutersCode')
                        name = item.get('stockName') # 한글 이름 확보!
                        break
                        
                # 코드를 찾았으면 재무 서랍장을 엽니다.
                if reuters_code:
                    basic_url = f"https://api.stock.naver.com/stock/{reuters_code}/basic"
                    basic_res = requests.get(basic_url, headers=headers).json()
                    
                    for info in basic_res.get('stockItemTotalInfos', []):
                        key_str = str(info.get('key', '')).upper()
                        val_str = str(info.get('value', ''))
                        
                        # 🌟 문자열 가위 (숫자와 소수점만 남기기)
                        clean_val = re.sub(r'[^\d.]', '', val_str)
                        
                        if clean_val and clean_val != '.':
                            if 'PBR' in key_str:
                                pbr = round(float(clean_val), 2)
                            elif 'PER' in key_str:
                                per = round(float(clean_val), 2)
                                
                # ROE 역산!
                if pbr > 0 and per > 0:
                    roe = round((pbr / per) * 100, 2)
            except Exception as e:
                print(f"🔥 네이버 퀀트 에러: {e}")

            # 3단계: 점수 계산
            score = 50 
            if pbr > 0:
                if pbr <= 1.5: score += 20
                elif pbr >= 3.0: score -= 15
            if roe > 0:
                if roe >= 15: score += 20
                elif roe < 0: score -= 15
            score = min(max(int(score), 10), 98)

            return {
                "name": name,
                "price": f"{current_price:,}",
                "currency": "달러",
                "pbr": pbr, 
                "roe": roe, 
                "score": score,
                "trend": trend_list, 
                "dates": date_list
            }

    except Exception as e:
        return {"detail": f"서버 내부 에러: {str(e)}"}
    
# 실행: uvicorn main:app --reload
