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
        # 🇺🇸 3. 미국 주식 로직 (야후 차트 + 네이버 해외주식 퀀트)
        # ==========================================
        else:
            ticker = yf.Ticker(target_symbol)
            
            # 1. 차트와 현재가 (이건 야후가 차단하지 않으니 그대로 씁니다!)
            hist = ticker.history(period="6mo")
            if hist.empty:
                return {"detail": f"미국 주식 '{target_symbol}' 데이터를 찾을 수 없습니다."}
            
            current_price = round(hist['Close'].iloc[-1], 2)
            
            trend_list, date_list = [], []
            for date, row in hist.iterrows():
                date_list.append(date.strftime('%Y-%m-%d'))
                trend_list.append(round(row['Close'], 2))

            # 2. 퀀트 데이터 추출 (네이버 해외주식 API 활용 - 절대 막히지 않음!)
            name = target_symbol
            pbr = 0.0
            per = 0.0
            roe = 0.0
            
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                
                # 1단계: 네이버에서 NVDA를 검색해서 정확한 해외 종목코드(예: NVDA.O) 찾기
                search_url = f"https://m.stock.naver.com/api/search/all?keyword={target_symbol}"
                search_res = requests.get(search_url, headers=headers).json()
                
                reuters_code = ""
                for item in search_res.get('searchList', []):
                    # 해외 주식(worldstock)이고, 심볼이 일치하면 선택!
                    if item.get('stockType') == 'worldstock' and item.get('symbolCode', '').upper() == target_symbol:
                        reuters_code = item.get('reutersCode')
                        name = item.get('stockName') # 🌟 보너스: '엔비디아', '애플' 같은 한글 이름을 가져옵니다!
                        break
                
                # 2단계: 찾아낸 코드(NVDA.O 등)로 네이버에 재무 데이터 요청하기
                if reuters_code:
                    basic_url = f"https://api.stock.naver.com/stock/{reuters_code}/basic"
                    basic_res = requests.get(basic_url, headers=headers).json()
                    
                    pbr_str = basic_res.get('pbr', '0')
                    per_str = basic_res.get('per', '0')
                    
                    # 네이버는 데이터가 없으면 '-' 를 주므로 필터링합니다.
                    if pbr_str and pbr_str != '-':
                        pbr = round(float(str(pbr_str).replace(',', '')), 2)
                    if per_str and per_str != '-':
                        per = round(float(str(per_str).replace(',', '')), 2)
                        
                    # ROE 역산!
                    if pbr > 0 and per > 0:
                        roe = round((pbr / per) * 100, 2)
                        
            except Exception as e:
                print(f"🔥 네이버 글로벌 API 호출 실패: {e}")
                
            # 3. 실제 데이터를 기반으로 퀀트 스코어 계산
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
        return {"detail": f"서버 에러: {str(e)}"}
    
# 실행: uvicorn main:app --reload
