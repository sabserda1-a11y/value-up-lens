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

# 🌟 0단계: 가장 많이 찾는 인기 종목은 0초 만에 바로 통과시키기 위한 미니 장부!
ALIASES = {
    '현대차': '005380', '기아차': '000270', '기아': '000270',
    '삼전': '005930', '삼성전자우': '005935', 'LG엔솔': '373220',
    'SK이노': '096770', '한화에어로': '012450', '카뱅': '323410',
    '엔씨': '036570', '엔씨소프트': '036570', '포스코': '005490', 
    'POSCO': '005490', '포스코홀딩스': '005490', '에코프로': '086520',
    '에코프로비엠': '247540', '루닛': '328130', '삼양식품': '003230',
    '삼성전자': '005930', '카카오': '035720', 'NAVER': '035420', '네이버': '035420'
}

@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "Ultimate 4-Stage Rocket Search Engine is running."}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        is_korean = None
        target_symbol = ""
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.naver.com/"
        }

        # ==========================================
        # 🌟 절대 안 뻗는 4중 방어망 통합 검색 라우터
        # ==========================================
        if query.isdigit():
            is_korean = True
            target_symbol = query.zfill(6)
        elif query in ALIASES:
            is_korean = True
            target_symbol = ALIASES[query]
        elif re.match(r'^[A-Za-z0-9]+$', query) and not any("\u3131" <= char <= "\u318E" or "\uAC00" <= char <= "\uD7A3" for char in query):
            is_korean = False
            target_symbol = query.upper()
        else:
            # 🚀 1단 로켓: 네이버 자동완성 API (가장 빠르고 차단 안 됨!)
            if not target_symbol:
                try:
                    ac_url = "https://ac.finance.naver.com/ac"
                    res = requests.get(ac_url, params={'q': query, 'q_enc': 'utf-8', 'st': '111', 'r_format': 'json', 't_koreng': '1'}, headers=headers)
                    if res.status_code == 200:
                        for group in res.json().get('items', []):
                            for item in group:
                                if len(item) >= 2:
                                    code = str(item[1])
                                    if code.isdigit() and len(code) == 6:
                                        is_korean = True
                                        target_symbol = code
                                        break
                                    elif re.match(r'^[A-Z0-9\.]+$', code) and not code.isdigit():
                                        is_korean = False
                                        target_symbol = code.split('.')[0]
                                        break
                            if target_symbol: break
                except: pass

            # 🚀 2단 로켓: 네이버 모바일 검색 API (1단이 실패했을 때)
            if not target_symbol:
                try:
                    m_url = "https://m.stock.naver.com/api/search/all"
                    res = requests.get(m_url, params={'keyword': query}, headers=headers)
                    if res.status_code == 200:
                        items = res.json().get('searchList', [])
                        if items:
                            first = items[0]
                            if first.get('stockType') == 'worldstock':
                                is_korean = False
                                target_symbol = str(first.get('symbolCode', '')).split('.')[0].upper()
                            else:
                                is_korean = True
                                target_symbol = str(first.get('itemCode', ''))
                except: pass

            # 🚀 3단 로켓: 야후 파이낸스 글로벌 검색 (해외 주식 한글 검색 특화 - 예: 애플)
            if not target_symbol:
                try:
                    yh_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(query)}"
                    res = requests.get(yh_url, headers=headers)
                    if res.status_code == 200:
                        for q in res.json().get('quotes', []):
                            sym = str(q.get('symbol', ''))
                            if sym.endswith('.KS') or sym.endswith('.KQ'):
                                is_korean = True
                                target_symbol = sym.split('.')[0]
                                break
                            elif re.match(r'^[A-Z]+$', sym):
                                is_korean = False
                                target_symbol = sym
                                break
                except: pass

            # 🚀 4단 로켓: 네이버 스크래핑 (최후의 보루)
            if not target_symbol:
                try:
                    euc_kr_query = urllib.parse.quote(query.encode('euc-kr'))
                    search_url = f"https://finance.naver.com/search/searchList.naver?query={euc_kr_query}"
                    res = requests.get(search_url, headers=headers)
                    if "item/main.naver?code=" in res.url:
                        is_korean = True
                        target_symbol = res.url.split("code=")[-1][:6]
                    else:
                        match = re.search(r'code=(\d{6})', res.text)
                        if match:
                            is_korean = True
                            target_symbol = match.group(1)
                except: pass

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
                except: pass
            
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
