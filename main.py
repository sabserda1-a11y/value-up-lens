기획자님, 뚝심 있는 선택! 역시 "본질(국내 저평가 주식 찾기)"을 밀어붙이는 게 기획자의 멋진 자세죠.

그럼 Twelve Data의 얄미운 유료화 장벽은 무시하고, 다시 **야후 파이낸스(yfinance)**로 돌아가겠습니다. 대신 이번에는 **'10분 기억력(Cache)'**이라는 아주 강력한 방어막을 둘러서 야후가 우리를 함부로 차단하지 못하게 만들겠습니다.

이 코드로 main.py를 전체 덮어쓰기 해주세요!

🛡️ 플랜 B-2: 야후 파이낸스 + 강력한 캐시 방어막 (main.py)
이 코드는 사용자가 검색하면 야후에 딱 한 번만 물어보고, 그 결과를 10분 동안 서버 메모리에 저장해 둡니다. 10분 안에 누가 또 검색하면 야후에 가지 않고 바로 꺼내줍니다. 속도도 빠르고 차단도 안 당하는 1석 2조의 마법입니다!

Python
import os
import time
import pandas as pd
import yfinance as yf
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS 설정 (프론트엔드 접속 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. 서버 메모리(Cache) 저장소 세팅
stock_cache = {}
CACHE_TTL = 600  # 600초 = 10분 동안 데이터 기억

# 2. 주식 이름 <-> 코드 매핑
def load_stock_map():
    try:
        df = pd.read_csv('stocks.csv', dtype={'code': str})
        return df.set_index('name')['code'].to_dict()
    except:
        return {}

STOCK_MAP = load_stock_map()

# 루트 경로 (서버 생존 확인용)
@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "Yahoo Finance Engine with Cache is Running!"}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    query = query.strip()
    
    # --- 1. 검색어 처리 (이름 or 코드) ---
    if query.isdigit():
        symbol = query
        name = f"종목코드 {query}"
    else:
        symbol = STOCK_MAP.get(query)
        name = query

    if not symbol:
        return {"detail": f"'{query}' 종목을 찾을 수 없습니다."}

    symbol = str(symbol).strip().zfill(6)
    yf_symbol = f"{symbol}.KS" # 야후 파이낸스용 코스피 코드

    now = time.time()

    # --- 2. 캐시(기억력) 방어막 작동! ---
    # 만약 10분 안에 검색한 적이 있다면 야후에 안 가고 바로 반환!
    if yf_symbol in stock_cache:
        cached_data = stock_cache[yf_symbol]
        if now - cached_data['time'] < CACHE_TTL:
            print(f"📦 캐시에서 초고속 반환: {name} ({yf_symbol})")
            return cached_data['data']

    # --- 3. 야후 파이낸스에서 데이터 가져오기 ---
    try:
        print(f"🌐 야후에서 새로 데이터 수집 중: {name} ({yf_symbol})")
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info

        # 주가가 없으면 에러 처리
        if 'currentPrice' not in info and 'regularMarketPrice' not in info:
             raise ValueError("주가 데이터를 찾을 수 없습니다.")

        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        
        # PBR, ROE (없으면 0으로 처리해서 에러 방지)
        pbr = info.get('priceToBook', 0)
        roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        
        # 퀀트 스코어 계산 (PBR이 낮을수록, ROE가 높을수록 좋은 점수)
        score = 50
        if pbr > 0:
            score += (1 / pbr) * 20
        score += roe * 0.5
        score = min(max(int(score), 10), 95) # 10~95점 사이로 보정

        # 최근 7일 주가 트렌드 (차트용)
        history = ticker.history(period="7d")
        if not history.empty:
            trend_list = history['Close'].astype(int).tolist()
        else:
            trend_list = [int(current_price)] * 5 # 데이터 없으면 일직선

        # 4. 프론트엔드로 보낼 최종 데이터 조립
        result_data = {
            "name": info.get('shortName', name),
            "price": f"{int(current_price):,}",
            "pbr": round(pbr, 2),
            "roe": round(roe, 2),
            "score": score,
            "trend": trend_list
        }

        # 5. 다음 사람을 위해 캐시에 저장!
        stock_cache[yf_symbol] = {
            'data': result_data,
            'time': now
        }

        return result_data

    except Exception as e:
        print(f"🔥 야후 API 에러: {str(e)}")
        # 만약 야후가 차단(Rate Limit)을 걸었는데, 예전에 저장해둔 캐시가 있다면 그거라도 줍니다!
        if yf_symbol in stock_cache:
            print("🛡️ 차단당했지만 과거 캐시 데이터로 방어합니다!")
            return stock_cache[yf_symbol]['data']
            
        return {"detail": "현재 야후 서버 연결이 지연되고 있습니다. 1분 뒤 다시 시도해주세요."}
    
# 실행: uvicorn main:app --reload
