import re
import requests
from datetime import datetime
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

@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "100% Auto Search Global Engine is running."}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        is_korean = True
        target_symbol = ""
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # ==========================================
        # 🌟 0. 스마트 통합 검색 라우터 (CSV 장부 완전 대체!)
        # ==========================================
        if query.isdigit():
            # 숫자만 치면 한국 주식 코드로 인식
            is_korean = True
            target_symbol = query.zfill(6)
        elif re.match(r'^[A-Za-z]+$', query):
            # 순수 영어만 치면 미국 주식 티커로 인식 (예: AAPL)
            is_korean = False
            target_symbol = query.upper()
        else:
            # 한글이나 섞인 글자를 치면 네이버 검색 API에 먼저 물어봅니다! (예: 카카오, 애플)
            search_url = f"https://m.stock.naver.com/api/search/all?keyword={query}"
            res = requests.get(search_url, headers=headers)
            
            if res.status_code == 200:
                search_data = res.json()
                items = search_data.get('searchList', [])
                
                if not items:
                    return {"detail": f"'{query}' 종목을 찾을 수 없습니다. 정확한 이름을 입력해주세요."}
                
                # 가장 정확한 첫 번째 검색 결과를 가져옵니다.
                first_item = items[0]
                
                # 네이버가 "이건 해외 주식이야!" 라고 알려주면 미국 주식 로직으로 패스
                if first_item.get('stockType') == 'worldstock':
                    is_korean = False
                    target_symbol = first_item.get('symbolCode', '').upper()
                else:
                    # 한국 주식이라면 6자리 코드를 빼옵니다.
                    is_korean = True
                    target_symbol = first_item.get('itemCode')
                    
                if not target_symbol:
                    return {"detail": f"'{query}'의 종목 코드를 확인할 수 없습니다."}
            else:
                return {"detail": "네이버 검색 서버에 연결할 수 없습니다."}

        # ==========================================
        # 🇰🇷 1. 한국 주식 로직 (실시간 주가 + 차트 + 퀀트)
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
        # 🇺🇸 2. 미국 주식 로직 (야후 다이렉트 차트 + 네이버 퀀트 지표)
        # ==========================================
        else:
            reuters_code = ""
            name = target_symbol
            pbr = 0.0
            per = 0.0
            roe = 0.0
            current_price = 0
            
            # 1단계: 차트 데이터 (야후 다이렉트 API)
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

            # 2단계: 퀀트 데이터 (네이버 해외주식 직통 타격)
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
                return {"detail": f"'{target_symbol}' 종목 데이터를 불러올 수 없습니다. 티커를 확인해주세요."}
                
            if pbr > 0 and per > 0:
                roe = round((pbr / per) * 100, 2)
                
            # 3단계: 스코어 계산
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
