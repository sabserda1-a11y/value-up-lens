import os
import pandas as pd
import requests
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
    return {"status": "alive", "message": "Value-Up Lens API (Naver Finance) is running."}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        
        if query.isdigit():
            symbol = query
        else:
            symbol = STOCK_MAP.get(query)

        if not symbol:
            return {"detail": f"'{query}' 종목을 찾을 수 없습니다."}
        
        symbol = str(symbol).strip().zfill(6)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # 1. 실시간 주가 및 이름 가져오기
        realtime_url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{symbol}"
        realtime_res = requests.get(realtime_url, headers=headers).json()
        
        try:
            item_data = realtime_res['result']['areas'][0]['datas'][0]
            name = item_data['nm']
            # 주가에 쉼표가 섞여 올 수 있으므로 순수 숫자로 변환 (예: "80,000" -> 80000)
            current_price = int(str(item_data['nv']).replace(',', ''))
        except (KeyError, IndexError):
            return {"detail": "종목 실시간 데이터를 가져오는 데 실패했습니다."}

# 2. [완벽 수정] 120일(약 6개월) 과거 주가 + 날짜 가져오기
        try:
            history_url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=120&requestType=0"
            history_res = requests.get(history_url, headers=headers).text
            
            trend_list = []
            date_list = [] # 🌟 날짜를 담을 새로운 상자 준비!
            
            for line in history_res.split('\n'):
                if '<item data=' in line:
                    data_str = line.split('"')[1]
                    parts = data_str.split('|')
                    
                    # parts[0]은 날짜(20260308), parts[4]는 종가(73000)
                    raw_date = parts[0]
                    # 날짜를 예쁘게 '2026-03-08' 형태로 조립
                    formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}" 
                    close_price = int(parts[4])
                    
                    date_list.append(formatted_date)
                    trend_list.append(close_price)
            
            if not trend_list:
                trend_list = [current_price] * 5
                date_list = ["데이터 없음"] * 5

        except Exception as e:
            print(f"🔥 차트 데이터 에러: {e}")
            trend_list = [current_price] * 5
            date_list = ["데이터 없음"] * 5 

        # 3. 프론트엔드로 날짜(dates) 데이터까지 묶어서 전송!
        return {
            "name": name,
            "price": f"{current_price:,}",
            "pbr": 0.85,    
            "roe": 12.5,    
            "score": 85,    
            "trend": trend_list,
            "dates": date_list   # 🌟 새로 추가된 날짜 데이터 
        }

    except Exception as e:
        return {"detail": f"서버 내부 에러: {str(e)}"}
    
# 실행: uvicorn main:app --reload
