import re
import requests
import urllib.parse # 🌟 한글을 네이버가 좋아하는 암호(EUC-KR)로 포장하는 도구!
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
    return {"status": "alive", "message": "100% Auto Search (Bypass Engine) is running."}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        is_korean = None
        target_symbol = ""
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://finance.naver.com/" # 🌟 나 봇 아니고 진짜 네이버에서 검색하는 거야~ 하고 속이는 신분증
        }

        # ==========================================
        # 🌟 0. 스마트 통합 검색 라우터 (EUC-KR 웹 스크래핑 + API 백업 하이브리드)
        # ==========================================
        if query.isdigit():
            is_korean = True
            target_symbol = query.zfill(6)
        elif re.match(r'^[A-Za-z]+$', query):
            is_korean = False
            target_symbol = query.upper()
        else:
            # 1. 네이버 금융 메인 검색창 스크래핑 (서버 차단 100% 우회 및 EUC-KR 인코딩!)
            try:
                # 🌟 핵심 마법: '카카오' -> '%C4%AB%C4%AB%BF%C0' (네이버가 알아듣는 EUC-KR 암호로 변환)
                euc_kr_query = urllib.parse.quote(query.encode('euc-kr'))
                search_url = f"https://finance.naver.com/search/searchList.naver?query={euc_kr_query}"
                res = requests.get(search_url, headers=headers)
                
                # 검색이 완벽히 일치해서 종목 페이지로 바로 리다이렉트 된 경우
                if "item/main.naver?code=" in res.url:
                    is_korean = True
                    target_symbol = res.url.split("code=")[-1][:6]
                else:
                    # 리스트가 나온 경우 첫 번째 종목 코드 긁어오기
                    match = re.search(r'/item/main\.naver\?code=(\d{6})', res.text)
                    if match:
                        is_korean = True
                        target_symbol = match.group(1)
            except Exception as e:
                print(f"스크래핑 우회 에러: {e}")

            # 2. 미국 주식을 한글로 쳤거나 (예: 애플), 못 찾았을 때의 최후 백업 API
            if not target_symbol:
                ac_url = "https://ac.finance.naver.com/ac"
                params = {'q': query, 'q_enc': 'utf-8', 'st': '111', 'r_format': 'json', 't_koreng': '1'}
                try:
                    ac_res = requests.get(ac_url, params=params, headers=headers)
                    if ac_res.status_code == 200:
                        items = ac_res.json().get('items', [])
                        for group in items:
                            for item in group:
                                if len(item) >= 3:
                                    market = str(item[2]).upper()
                                    if market in ['KOSPI', 'KOSDAQ', 'KONEX']:
                                        is_korean = True
                                        target_symbol = str(item[1])
                                        break
                                    elif market in ['NASDAQ', 'NYSE', 'AMEX', 'NYSEAMEX'] or not str(item[1]).isdigit():
                                        is_korean = False
                                        target_symbol = str(item[1]).split('.')[0].upper()
                                        break
                            if target_symbol: break
                except Exception as e:
                    print(f"API 백업 검색 에러: {e}")

        # 찾지 못했을 때의 방어막
        if not target_symbol:
            return JSONResponse(status_code=404, content={"detail": f"'{query}' 종목을 찾을 수 없습니다. 정확한 이름을 입력해주세요."})

        # ==========================================
        # 🇰🇷 1. 한국 주식 로직
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
        # 🇺🇸 2. 미국 주식 로직
        # ==========================================
        else:
            reuters_code = ""
            name = target_symbol
            pbr = 0.0
            per = 0.0
            roe = 0.0
            current_price = 0
            
            chart_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{target_symbol}?interval=1d&range=6mo"
            chart_res = requests.get(chart_url, headers=headers)
            
            trend_list = []
            date_list = []
            
            if chart_res.status_code == 200:
                try:
                    chart_data = chart_res.json()
                    result = chart_data['chart']['result'][0]
                    timestamps = result.get('timestamp', [])
                    closes = result['indicators']['quote'][0].get('close', [])
                    
                    for t, c in zip(timestamps, closes):
                        if c is not None:
                            dt = datetime.fromtimestamp(t).strftime('%Y-%m-%d')
                            date_list.append(dt)
                            trend_list.append(round(c, 2))
                except Exception as e:
                    print(f"야후 차트 파싱 에러: {e}")
            
            if trend_list:
                current_price = trend_list[-1]
            else:
                trend_list = [0] * 5
                date_list = ["데이터 없음"] * 5

            for ext in ['.O', '.N', '.A']:
                basic_url = f"https://api.stock.naver.com/stock/{target_symbol}{ext}/basic"
                res = requests.get(basic_url, headers=headers)
                
                if res.status_code == 200:
                    basic_res = res.json()
                    
                    if 'stockItemTotalInfos' in basic_res:
                        reuters_code = f"{target_symbol}{ext}"
                        name = basic_res.get('stockName', target_symbol)
                        
                        if current_price == 0:
                            try:
                                cp_str = str(basic_res.get('closePrice', '0')).replace(',', '')
                                current_price = round(float(cp_str), 2)
                                trend_list = [current_price] * 5
                            except: pass
                        
                        for info in basic_res.get('stockItemTotalInfos', []):
                            key_str = str(info.get('key', '')).upper()
                            val_str = str(info.get('value', ''))
                            clean_val = re.sub(r'[^\d.]', '', val_str)
                            
                            if clean_val and clean_val != '.':
                                if 'PBR' in key_str and pbr == 0.0:
                                    pbr = round(float(clean_val), 2)
                                elif 'PER' in key_str and per == 0.0:
                                    per = round(float(clean_val), 2)
                        break 
            
            if not reuters_code and current_price == 0:
                return JSONResponse(status_code=404, content={"detail": f"'{target_symbol}' 종목 데이터를 불러올 수 없습니다. 티커를 확인해주세요."})
                
            if pbr > 0 and per > 0:
                roe = round((pbr / per) * 100, 2)
                
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
        return JSONResponse(status_code=500, content={"detail": f"서버 내부 에러: {str(e)}"})
        
# 실행: uvicorn main:app --reload
