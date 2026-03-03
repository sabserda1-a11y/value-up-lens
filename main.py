import os
import ssl
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf

# [보안 우회] 맥 환경 필수
os.environ['PYTHONHTTPSVERIFY'] = '0'
ssl._create_default_https_context = ssl._create_unverified_context

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        # 1. 일단 매핑 시도
        symbol = STOCK_MAP.get(query, query)
        
        # [핵심 추가] 만약 symbol이 숫자 형태라면 무조건 6자리로 맞추기
        # '5380' -> '005380'으로 강제 변환합니다.
        if symbol.isdigit():
            symbol = symbol.zfill(6)
        
        print(f"변환된 코드: {symbol}") # 터미널에서 확인용

        # 2. 야후 파이낸스 데이터 호출
        ticker = yf.Ticker(f"{symbol}.KS")
        info = ticker.info
        
        # 코스피에 없으면 코스닥 시도
        if not info or 'currentPrice' not in info:
            ticker = yf.Ticker(f"{symbol}.KQ")
            info = ticker.info

        # 3. 핵심 지표 추출 (PBR, ROE)
        # Yahoo Finance에서 데이터가 없을 경우를 대비해 기본값을 설정합니다.
        current_price = info.get('currentPrice', 0)
        pbr = info.get('priceToBook') or info.get('forwardEps', 0.8) # PBR 없으면 대략적 수치
        roe = info.get('returnOnEquity', 0.1) # ROE 없으면 10% 가정
        
        # 4. 퀀트 스코어 계산 (기획자님의 핵심 로직!)
        # PBR이 낮고(저평가), ROE가 높을수록(수익성) 점수가 높음
        avg_pbr = 1.0
        score = int((avg_pbr / pbr * 50) + (roe * 100 * 0.5)) if pbr > 0 else 50
        score = min(max(score, 10), 98) # 점수는 10~98점 사이로 제한

        # 5. 차트용 주가 데이터 (최근 1개월)
        hist = ticker.history(period="1mo")
        # 데이터가 있으면 리스트로 변환, 없으면 [0] 채움
        trend_data = hist['Close'].fillna(0).astype(int).tolist() if not hist.empty else [0,0,0,0,0]

        return {
            "name": info.get('shortName', query),
            "price": f"{current_price:,}",
            "pbr": round(pbr, 2),
            "roe": round(roe * 100, 1),
            "score": score,
            "trend": trend_data
        }

    except Exception as e:
        return {"detail": str(e)}

# 실행: uvicorn main:app --reload