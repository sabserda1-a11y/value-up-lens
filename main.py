import os
import pandas as pd
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 1. CORS 설정 (프론트엔드 GitHub Pages에서 API를 호출할 수 있도록 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 주식 종목명 <-> 종목코드 매핑 데이터 로드 (stocks.csv 필요)
def load_stock_map():
    try:
        df = pd.read_csv('stocks.csv', dtype={'code': str})
        return df.set_index('name')['code'].to_dict()
    except Exception as e:
        print(f"CSV 로드 에러: {e}")
        return {}

STOCK_MAP = load_stock_map()

# 3. 서버 생존 확인용 루트 경로 (터미널 404 에러 방지)
@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "Value-Up Lens API (Naver Finance Engine) is running."}

# 4. 메인 주식 검색 API
@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        
        # [하이브리드 검색] 숫자인지 한글인지 판별
        if query.isdigit():
            symbol = query
        else:
            symbol = STOCK_MAP.get(query)

        # 예외 처리: 종목을 못 찾았을 때
        if not symbol:
            return {"detail": f"'{query}' 종목을 찾을 수 없습니다. 정확한 종목명이나 코드를 입력해주세요."}
        
        # 무조건 6자리 숫자로 맞추기 (예: '5930' -> '005930')
        symbol = str(symbol).strip().zfill(6)

        # [핵심] 네이버 금융 실시간 모바일 API 호출
        url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{symbol}"
        # 브라우저인 척 위장하여 네이버 서버의 차단을 방지합니다.
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers)
        data = response.json()

        # 네이버 응답 데이터에서 필요한 정보만 추출
        try:
            item_data = data['result']['areas'][0]['datas'][0]
            current_price = item_data['nv']  # 실시간 현재가 (nv)
            name = item_data['nm']           # 정확한 종목명 (nm)
        except (KeyError, IndexError):
            return {"detail": "네이버 금융에서 데이터를 가져오는 데 실패했습니다. 종목 코드를 확인해주세요."}

        # 프론트엔드로 보낼 최종 데이터 조립
        # (프로토타입 완성을 위해 PBR, ROE 등의 재무 지표는 그럴듯한 샘플로 고정합니다)
        return {
            "name": name,
            "price": f"{current_price:,}",
            "pbr": 0.85,    # 샘플 데이터 (화면 표시용)
            "roe": 12.5,    # 샘플 데이터 (화면 표시용)
            "score": 85,    # 샘플 데이터 (화면 표시용)
            "trend": [int(current_price * 0.98), int(current_price * 0.99), int(current_price)] # 차트용 가상 트렌드
        }

    except Exception as e:
        print(f"🔥 서버 내부 에러: {str(e)}")
        return {"detail": f"서버 내부 에러가 발생했습니다: {str(e)}"}
    
# 실행: uvicorn main:app --reload
