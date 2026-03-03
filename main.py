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
TWELVE_DATA_API_KEY = "여기에_복사한_API_KEY를_넣으세요"

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
        symbol = STOCK_MAP.get(query)
        if not symbol:
            return {"detail": f"'{query}' 종목을 찾을 수 없습니다."}
        
        # 6자리 코드로 맞추기 (005930 등)
        symbol = symbol.zfill(6)

        # 1. Twelve Data API 호출 (한국 주식은 :XKRX 접미사가 붙습니다)
        # 주가 정보(Quote) 가져오기
        url = f"https://api.twelvedata.com/quote?symbol={symbol}:XKRX&apikey={TWELVE_DATA_API_KEY}"
        response = requests.get(url).json()

        if "code" in response and response["code"] != 200:
            return {"detail": f"API 에러: {response.get('message')}"}

        # 2. 데이터 추출
        current_price = float(response.get('close', 0))
        name = response.get('name', query)
        
        # 3. 퀀트 지표 (Twelve Data 무료플랜은 재무지표가 제한적일 수 있어 
        # 야후에서 PBR/ROE만 살짝 가져오거나 기본값을 사용합니다.)
        # 일단은 안정적인 연결을 위해 기본 수치와 가상 데이터를 조합합니다.
        pbr = 0.85 # 실제 서비스 시 재무 API 추가 연동 가능
        roe = 12.5
        
        # 4. 퀀트 스코어 계산
        score = int((0.85 / pbr * 50) + (roe * 0.5))
        score = min(max(score, 10), 95)

        # 5. 차트 데이터 (Twelve Data의 time_series API 사용 가능)
        # 무료 플랜은 요청 횟수 제한이 있으므로 주가 위주로 먼저 구현합니다.
        
        return {
    "name": name,
    "price": f"{int(current_price):,}",
    "pbr": pbr,
    "roe": roe,
    "score": score,
    "trend": [int(current_price * 0.98), int(current_price * 0.99), int(current_price)] # 최소한의 리스트라도 보냅니다.
}

    except Exception as e:
        return {"detail": str(e)}
    
# 실행: uvicorn main:app --reload
