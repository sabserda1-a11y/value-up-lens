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

# 🌟 1. 사람들이 자주 쓰는 '줄임말'만 소수로 기억해둡니다. (이외의 수천 개는 웹에서 자동 검색합니다)
ALIASES = {
    '현대차': '005380', '기아차': '000270', '기아': '000270',
    '삼전': '005930', '삼성전자우': '005935', 'LG엔솔': '373220',
    'SK이노': '096770', '한화에어로': '012450', '카뱅': '323410',
    '엔씨': '036570', '엔씨소프트': '036570', '포스코': '005490', 
    'POSCO': '005490', '포스코홀딩스': '005490'
}

@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "Ultimate Anti-Block Search Engine is running."}

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
        # 🌟 0. 절대 안 막히는 3단계 무적 검색 라우터
        # ==========================================
        if query.isdigit():
            is_korean = True
            target_symbol = query.zfill(6)
        elif query in ALIASES:
            # 1단계: 애칭 사전에 있으면 0초 만에 바로 통과!
            is_korean = True
            target_symbol = ALIASES[query]
        elif re.match(r'^[A-Za-z0-9]+$', query) and not any("\u3131" <= char <= "\u318E" or "\uAC00" <= char <= "\uD7A3" for char in query):
            # 순수 영문(AAPL 등)은 미국 주식
            is_korean = False
            target_symbol = query.upper()
        else:
            # 2단계: 글로벌 야후 파이낸스 검색 (Render 차단 확률 0%)
            try:
                yh_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(query)}"
                yh_res = requests.get(yh_url, headers=headers)
                if yh_res.status_code == 200:
                    quotes = yh_res.json().get('quotes', [])
                    for q in quotes:
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

            # 3단계: 최후의 보루! 네이버 금융 웹페이지 직접 긁어오기 (절대 차단당하지 않는 통로)
            if not target_symbol:
                try:
                    # '한미반도체'를 네이버가 좋아하는 옛날 암호(EUC-KR)로 변환
                    euc_kr_query = urllib.parse.quote(query.encode('euc-kr'))
                    search_url = f"https://finance.naver.com/search/searchList.naver?query={euc_kr_query}"
                    res = requests.get(search_url, headers=headers)
                    
                    # 검색 결과가 하나라서 바로 주식 화면으로 넘어간 경우
                    if "item/main.naver?code=" in res.url:
                        is_korean = True
                        target_symbol = res.url.split("code=")[-1][:6]
                    else:
                        # 검색 결과가 여러 개 나와서 리스트가 뜬 경우 첫 번째 종목 가져오기
                        match = re.search(r'href="/item/main\.naver\?code=(\d{6})"', res.text)
                        if match:
                            is_korean = True
                            target_symbol = match.group(1)
                except Exception as e:
                    print(f"네이버 웹 스크래핑 에러: {e}")

        # 모든 길을 다 거쳤는데도 없으면 404 에러 팝업!
        if not target_symbol:
            return JSONResponse(status_code=404, content={"detail": f"'{query}' 종목을 찾을 수 없습니다. 정확한 이름을 입력해주세요."})

        # ==========================================
        # 🇰🇷 1. 한국 주식 로직 (차단 안 됨!)
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
        # 🇺🇸 2. 미국 주식 로직 (차단 안 됨!)
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
