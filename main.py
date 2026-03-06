import os
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests # Twelve Data 호출용

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# [발급받은 키를 여기에 넣으세요]
TWELVE_DATA_API_KEY = "65a8d39e8d3945bf82339e9ef483f211"

# [데이터 로드]
def load_stock_map():
    try:
        df = pd.read_csv('stocks.csv', dtype={'code': str})
        return df.set_index('name')['code'].to_dict()
    except:
        return {}

STOCK_MAP = load_stock_map()

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        
        if query.isdigit():
            symbol = query
            name = f"종목코드 {query}"
        else:
            symbol = STOCK_MAP.get(query)
            name = query

        if not symbol:
            return {"detail": f"'{query}' 종목을 찾을 수 없습니다. (CSV 파일 로드 확인 필요)"}
        
        symbol = str(symbol).strip().zfill(6)

        # Twelve Data 규칙에 맞춘 완벽한 URL 포맷
        url = f"https://api.twelvedata.com/quote?symbol={symbol}&mic_code=XKRX&apikey={TWELVE_DATA_API_KEY}"
        
        response = requests.get(url)
        data = response.json()

        # 에러 응답 처리
        if "status" in data and data["status"] == "error":
             # 만약 mic_code=XKRX도 에러가 나면, country=South Korea로 대체하는 방어 로직
             fallback_url = f"https://api.twelvedata.com/quote?symbol={symbol}&country=South%20Korea&apikey={TWELVE_DATA_API_KEY}"
             data = requests.get(fallback_url).json()
             
             if "status" in data and data["status"] == "error":
                 return {"detail": f"API 에러: {data.get('message')}"}
             
        if "close" not in data:
            return {"detail": "종목 데이터를 가져올 수 없습니다."}

        current_price = float(data['close'])
        
        return {
            "name": data.get('name', name),
            "price": f"{int(current_price):,}",
            "pbr": 0.85,
            "roe": 12.5,
            "score": 85,
            "trend": [int(current_price * 0.98), int(current_price * 0.99), int(current_price)]
        }

    except Exception as e:
        return {"detail": f"서버 에러: {str(e)}"}
    
# 실행: uvicorn main:app --reload
