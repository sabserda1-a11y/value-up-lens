import os
import re
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
    return {"status": "alive", "message": "100% Naver Global Engine is running."}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        is_korean = True
        target_symbol = ""

        # 검색어 분류
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
        # 🇰🇷 1. 한국 주식 로직 (네이버 금융)
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
        # 🇺🇸 2. 미국 주식 로직 (100% 네이버 해외주식 API)
        # ==========================================
        else:
            # 1단계: 검색 API로 네이버 전용 종목코드(reutersCode) 찾기
            search_url = f"https://m.stock.naver.com/api/search/all?keyword={target_symbol}"
            search_res = requests.get(search_url, headers=headers).json()
            
            reuters_code = ""
            name = target_symbol
            
            for item in search_res.get('searchList', []):
                if item.get('stockType') == 'worldstock' and item.get('symbolCode', '').upper() == target_symbol:
                    reuters_code = item.get('reutersCode') # 예: NVDA.O
                    name = item.get('stockName') # 예: 엔비디아
                    break
                    
            if not reuters_code:
                return {"detail": f"네이버 해외주식에서 '{target_symbol}' 종목을 찾을 수 없습니다."}
            
            # 2단계: 과거 120일 차트 및 현재가 가져오기 (네이버 해외차트 API)
            price_url = f"https://api.stock.naver.com/stock/{reuters_code}/price?pageSize=120&page=1"
            price_res = requests.get(price_url, headers=headers).json()
            
            trend_list = []
            date_list = []
            
            for item in price_res:
                # 날짜 "2026-03-08T00:00:00" 형태를 "2026-03-08"로 자르기
                raw_date = item.get('localDate', '').split('T')[0]
                close_str = str(item.get('closePrice', '0')).replace(',', '')
                
                if raw_date and close_str:
                    date_list.append(raw_date)
                    trend_list.append(round(float(close_str), 2))
                    
            if not trend_list:
                return {"detail": f"'{name}'의 차트 데이터를 불러오지 못했습니다."}
            
            # 네이버는 최신 날짜부터 주기 때문에 차트를 위해 순서를 뒤집습니다!
            trend_list.reverse()
            date_list.reverse()
            
            # 현재가는 차트의 맨 마지막(최신) 가격
            current_price = trend_list[-1]

            # 3단계: 퀀트 데이터 가져오기 (네이버 해외 기본정보 API)
            pbr = 0.0
            per = 0.0
            roe = 0.0
            
            basic_url = f"https://api.stock.naver.com/stock/{reuters_code}/basic"
            basic_res = requests.get(basic_url, headers=headers).json()
            
            # 응답 데이터 1차 스캔
            raw_pbr = basic_res.get('pbr', '')
            raw_per = basic_res.get('per', '')
            
            try:
                if raw_pbr and raw_pbr != '-': pbr = round(float(str(raw_pbr).replace(',', '')), 2)
                if raw_per and raw_per != '-': per = round(float(str(raw_per).replace(',', '')), 2)
            except: pass

            # 못 찾았다면 서랍장(stockItemTotalInfos) 2차 스캔 및 정규식 가위질
            if pbr == 0.0 or per == 0.0:
                for info in basic_res.get('stockItemTotalInfos', []):
                    key_str = str(info.get('key', '')).upper()
                    val_str = str(info.get('value', ''))
                    clean_val = re.sub(r'[^\d.]', '', val_str)
                    
                    if clean_val and clean_val != '.':
                        if 'PBR' in key_str and pbr == 0.0:
                            pbr = round(float(clean_val), 2)
                        elif 'PER' in key_str and per == 0.0:
                            per = round(float(clean_val), 2)
                            
            # ROE 역산
            if pbr > 0 and per > 0:
                roe = round((pbr / per) * 100, 2)
                
            # 4단계: 스코어 계산
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
