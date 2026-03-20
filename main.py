import re
import requests
import urllib.parse
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "TradingView Global Search Engine (Granular Scoring V2) is running."}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        is_korean = None
        target_symbol = ""
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # ==========================================
        # 🌟 1. 글로벌 검색 라우터 (트레이딩뷰 + 네이버)
        # ==========================================
        if query.isdigit():
            is_korean = True
            target_symbol = query.zfill(6)
        elif re.match(r'^[A-Za-z0-9\.]+$', query) and not any("\u3131" <= char <= "\u318E" or "\uAC00" <= char <= "\uD7A3" for char in query):
            is_korean = False
            target_symbol = query.upper()
        else:
            try:
                tv_url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={urllib.parse.quote(query)}&hl=1&lang=ko&type=stock"
                tv_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Origin": "https://kr.tradingview.com",
                    "Referer": "https://kr.tradingview.com/"
                }
                tv_res = requests.get(tv_url, headers=tv_headers)
                
                if tv_res.status_code == 200:
                    symbols = tv_res.json().get('symbols', [])
                    if symbols:
                        first_match = symbols[0]
                        sym = str(first_match.get('symbol', ''))
                        country = first_match.get('country', '')
                        
                        if country == 'KR' and sym.isdigit():
                            is_korean = True
                            target_symbol = sym.zfill(6)
                        elif country == 'US':
                            is_korean = False
                            target_symbol = sym
            except: pass

            if not target_symbol:
                try:
                    search_url = f"https://m.search.naver.com/search.naver?query={urllib.parse.quote(query + ' 주가')}"
                    res = requests.get(search_url, headers=headers)
                    match = re.search(r'm\.stock\.naver\.com/(?:domestic|world)/stock/([A-Za-z0-9\.]+)', res.text)
                    if match:
                        code = match.group(1)
                        if code.isdigit():
                            is_korean = True
                            target_symbol = code
                        else:
                            is_korean = False
                            target_symbol = code.split('.')[0]
                except: pass

        if not target_symbol:
            return JSONResponse(status_code=404, content={"detail": f"'{query}' 종목을 찾을 수 없습니다. 정확한 이름을 입력해주세요."})

        # ==========================================
        # 🌟 초정밀 점수 계산기 함수
        # ==========================================
        def calculate_score(pbr, per, roe):
            score = 40 # 기본 점수 깐깐하게 40점 시작
            
            # PBR 세분화
            if pbr > 0:
                if pbr <= 0.8: score += 20
                elif pbr <= 1.2: score += 15
                elif pbr <= 1.5: score += 10
                elif pbr >= 3.0: score -= 10
                
            # PER 세분화
            if per > 0:
                if per <= 10: score += 20
                elif per <= 15: score += 15
                elif per <= 20: score += 5
                elif per > 20: score -= 5
            elif per < 0:
                score -= 15 # 적자 페널티
                
            # ROE 세분화
            if roe > 0:
                if roe >= 20: score += 20
                elif roe >= 15: score += 15
                elif roe >= 10: score += 10
                elif roe >= 5: score += 5
            elif roe < 0:
                score -= 15 # 적자 페널티
                
            return min(max(int(score), 10), 98)

        # ==========================================
        # 🇰🇷 2. 한국 주식 로직
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

            score = calculate_score(pbr, per, roe)

            return {
                "name": name, "price": f"{current_price:,}", "currency": "원",
                "pbr": pbr, "per": per, "roe": roe, "score": score,
                "trend": trend_list, "dates": date_list
            }

        # ==========================================
        # 🇺🇸 3. 미국 주식 로직
        # ==========================================
        else:
            reuters_code = ""
            name = target_symbol
            pbr, per, roe = 0.0, 0.0, 0.0
            current_price = 0
            
            chart_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{target_symbol}?interval=1d&range=6mo"
            chart_res = requests.get(chart_url, headers=headers)
            
            trend_list, date_list = [], []
            
            if chart_res.status_code == 200:
                try:
                    chart_data = chart_res.json()
                    result = chart_data['chart']['result'][0]
                    timestamps = result.get('timestamp', [])
                    closes = result['indicators']['quote'][0].get('close', [])
                    for t, c in zip(timestamps, closes):
                        if c is not None:
                            date_list.append(datetime.fromtimestamp(t).strftime('%Y-%m-%d'))
                            trend_list.append(round(c, 2))
                except: pass
            
            if trend_list: current_price = trend_list[-1]
            else: trend_list, date_list = [0]*5, ["데이터 없음"]*5

            for ext in ['.O', '.N', '.A']:
                basic_url = f"https://api.stock.naver.com/stock/{target_symbol}{ext}/basic"
                res = requests.get(basic_url, headers=headers)
                if res.status_code == 200:
                    basic_res = res.json()
                    if 'stockItemTotalInfos' in basic_res:
                        reuters_code = f"{target_symbol}{ext}"
                        name = basic_res.get('stockName', target_symbol)
                        if current_price == 0:
                            try: current_price = round(float(str(basic_res.get('closePrice', '0')).replace(',', '')), 2); trend_list = [current_price]*5
                            except: pass
                        for info in basic_res.get('stockItemTotalInfos', []):
                            key_str = str(info.get('key', '')).upper()
                            clean_val = re.sub(r'[^\d.]', '', str(info.get('value', '')))
                            if clean_val and clean_val != '.':
                                if 'PBR' in key_str and pbr == 0.0: pbr = round(float(clean_val), 2)
                                elif 'PER' in key_str and per == 0.0: per = round(float(clean_val), 2)
                        break 
            
            if not reuters_code and current_price == 0:
                return JSONResponse(status_code=404, content={"detail": f"'{target_symbol}' 종목 데이터를 불러올 수 없습니다."})
                
            if pbr > 0 and per > 0: roe = round((pbr / per) * 100, 2)
                
            score = calculate_score(pbr, per, roe)

            return {
                "name": name, "price": f"{current_price:,}", "currency": "달러",
                "pbr": pbr, "per": per, "roe": roe, "score": score,
                "trend": trend_list, "dates": date_list
            }

    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"서버 내부 에러: {str(e)}"})
        
# 실행: uvicorn main:app --reload
