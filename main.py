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
            current_price_raw = item_data['nv']  
            name = item_data['nm']           
        except:
            return {"detail": "종목 데이터를 가져오는 데 실패했습니다."}

        # 2. [신규 기능] 최근 120일(약 6개월) 일별 주가 가져오기
        try:
            history_url = f"https://m.stock.naver.com/api/stock/{symbol}/price?pageSize=120&page=1"
            history_res = requests.get(history_url, headers=headers).json()
            
            trend_list = []
            # 네이버는 최신 날짜부터 주므로 리스트에 담습니다.
            for item in history_res:
                # "80,000" 처럼 쉼표가 섞인 문자열을 순수 숫자로 변환
                price_str = str(item.get('closePrice', '0')).replace(',', '')
                trend_list.append(int(price_str))
                
            # 차트는 왼쪽(과거)에서 오른쪽(현재)으로 그려져야 하므로 순서를 뒤집습니다.
            trend_list.reverse()
            
        except Exception as e:
            print(f"차트 데이터 에러: {e}")
            # 에러 시 빈 차트 방지용 임시 데이터
            trend_list = [int(current_price_raw)] * 5 

        # 3. 최종 데이터 전송
        return {
            "name": name,
            "price": f"{current_price_raw:,}",
            "pbr": 0.85,    
            "roe": 12.5,    
            "score": 85,    
            "trend": trend_list  # 이제 여기에 120일치 찐 데이터가 들어갑니다!
        }

    except Exception as e:
        return {"detail": f"서버 에러: {str(e)}"}
    
# 실행: uvicorn main:app --reload
