import os
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

# ==========================================
# 🌟 1. 한국거래소(KRX) 공식 DB 훔쳐오기 (CSV 장부 완벽 대체!)
# ==========================================
def load_dynamic_krx_map():
    stock_map = {}
    try:
        # KRX 상장법인목록 다운로드 공식 주소 (차단 안 당함!)
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'euc-kr' # 거래소는 옛날 암호를 씁니다
        
        # HTML을 가위(정규식)로 오려서 이름과 코드를 싹 빼옵니다.
        rows = re.findall(r'<tr.*?>(.*?)</tr>', res.text, re.IGNORECASE | re.DOTALL)
        for row in rows:
            cols = re.findall(r'<td.*?>(.*?)</td>', row, re.IGNORECASE | re.DOTALL)
            if len(cols) >= 2:
                name = re.sub(r'<[^>]+>', '', cols[0]).strip().replace('&amp;', '&')
                code = re.sub(r'<[^>]+>', '', cols[1]).strip()
                if code.isdigit() and len(code) in [5, 6]:
                    stock_map[name] = code.zfill(6)
                    
        # 사용자들이 자주 쓰는 애칭들만 보너스로 추가 (공식 명칭은 '현대자동차'이므로)
        aliases = {
            '현대차': '005380', '기아차': '000270', '기아': '000270',
            '네이버': '035420', 'NAVER': '035420', '카카오': '035720',
            'LG엔솔': '373220', '삼전': '005930', 'SK이노': '096770'
        }
        stock_map.update(aliases)
        print(f"✅ KRX 자동 DB 로드 완료: 총 {len(stock_map)}개 종목 기억 완료!")
    except Exception as e:
        print(f"🔥 KRX DB 로드 에러: {e}")
    return stock_map

# 🌟 서버가 켜질 때 딱 1번만! 2,500개 종목을 머릿속에 집어넣습니다.
STOCK_MAP = load_dynamic_krx_map()

@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "Zero-Maintenance Dynamic Engine is running."}

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
        # 🌟 0. 스마트 통합 검색 라우터
        # ==========================================
        if query.isdigit():
            is_korean = True
            target_symbol = query.zfill(6)
        # 🌟 여기서 핵심! 사용자가 검색한 이름이 내가 방금 외운 2,500개 중에 있다면?
        # 네이버 검색 API 거치지 않고 프리패스 통과! (차단 확률 0%)
        elif query in STOCK_MAP:
            is_korean = True
            target_symbol = STOCK_MAP[query]
        elif re.match(r'^[A-Za-z0-9]+$', query) and not any("\u3131" <= char <= "\u318E" or "\uAC00" <= char <= "\uD7A3" for char in query):
            is_korean = False
            target_symbol = query.upper()
        else:
            # 2,500개 목록에 없거나, 미국 주식을 한글로 검색(예: '애플') 했을 때만 야후/네이버 API를 씁니다.
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

            if not target_symbol:
                try:
                    ac_url = "https://ac.finance.naver.com/ac"
                    params = {'q': query, 'q_enc': 'utf-8', 'st': '111', 'r_format': 'json', 't_koreng': '1'}
                    ac_res = requests.get(ac_url, params=params, headers=headers)
                    if ac_res.status_code == 200:
                        items = ac_res.json().get('items', [])
                        for group in items:
                            for item in group:
                                if len(item) >= 2:
                                    code_str = str(item[1])
                                    if code_str.isdigit() and len(code_str) == 6:
                                        is_korean = True
                                        target_symbol = code_str
                                        break
                                if target_symbol: break
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
