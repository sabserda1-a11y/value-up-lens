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
        # 1. 하이브리드 검색: 숫자로 들어왔는지, 한글로 들어왔는지 판별
        query = query.strip()
        
        if query.isdigit():
            # 사용자가 '005380'처럼 숫자만 입력했을 때
            symbol = query
            name = f"종목코드 {query}" # 이름은 코드로 임시 대체
        else:
            # 사용자가 '삼성전자'처럼 이름을 입력했을 때
            symbol = STOCK_MAP.get(query)
            name = query

        # 2. 기획적 방어: 코드를 못 찾았을 때
        if not symbol:
            return {"detail": f"'{query}' 종목을 찾을 수 없습니다. 정확한 종목명이나 코드를 입력해주세요."}
        
        # 3. 코드 전처리 (무조건 6자리 숫자로 만듦)
        symbol = str(symbol).strip().zfill(6)
        
        print(f"🚀 검색어: {query} -> 변환된 코드: {symbol}")

        # 4. Twelve Data API 호출 (한국 거래소 :XKRX 붙이기)
        # 만약 여기서도 에러가 나면 :XKRX를 빼고 symbol만 넣어보세요.
        url = f"https://api.twelvedata.com/quote?symbol={symbol}:XKRX&apikey={TWELVE_DATA_API_KEY}"
        
        response = requests.get(url)
        data = response.json()

        # 에러 응답 처리
        if "status" in data and data["status"] == "error":
             return {"detail": f"API 에러: {data.get('message')}"}
             
        if "close" not in data:
            return {"detail": "종목 데이터를 가져올 수 없습니다."}

        # 5. 프론트엔드와 약속한 '이름표' 그대로 전달
        current_price = float(data['close'])
        
        return {
            "name": data.get('name', name), # Twelve Data가 영어 이름을 주면 그걸 쓰고, 아니면 우리 걸 씁니다.
            "price": f"{int(current_price):,}",
            "pbr": 0.85,  # 샘플 데이터 (Twelve Data 무료는 재무제표 미지원)
            "roe": 12.5,  # 샘플 데이터
            "score": 85,  # 샘플 데이터
            "trend": [int(current_price * 0.98), int(current_price * 0.99), int(current_price)] # 차트용 샘플
        }

    except Exception as e:
        print(f"💥 서버 에러: {str(e)}")
        return {"detail": f"서버 내부 에러가 발생했습니다: {str(e)}"}
    
# 실행: uvicorn main:app --reload
