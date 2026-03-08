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

# 🌟 0단계: 가장 많이 찾는 미국 주식 한글 번역기 (야후 검색이 실패할 때를 대비한 철통 방어!)
US_ALIASES = {
    '애플': 'AAPL', '테슬라': 'TSLA', '엔비디아': 'NVDA', '마이크로소프트': 'MSFT', '마소': 'MSFT',
    '아마존': 'AMZN', '구글': 'GOOGL', '알파벳': 'GOOGL', '메타': 'META', '페이스북': 'META',
    '넷플릭스': 'NFLX', 'AMD': 'AMD', '인텔': 'INTC', 'TSMC': 'TSM', '퀄컴': 'QCOM',
    '팔란티어': 'PLTR', '스타벅스': 'SBUX', '코카콜라': 'KO', '펩시': 'PEP', '디즈니': 'DIS',
    '버크셔해서웨이': 'BRK.B', '브로드컴': 'AVGO', 'ASML': 'ASML', '일라이릴리': 'LLY', 
    '노보노디스크': 'NVO', '마이크론': 'MU', '쿠팡': 'CPNG', '코인베이스': 'COIN', '로블록스': 'RBLX'
}

@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "ZUM & StockPlus Bypass Engine is running."}

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
        # 🌟 절대 막히지 않는 스마트 통합 검색 라우터
        # ==========================================
        if query.isdigit():
            is_korean = True
            target_symbol = query.zfill(6)
        elif query in US_ALIASES:
            # 💡 기획자님이 '애플'을 치면 여기서 바로 'AAPL'로 번역해서 프리패스!
            is_korean = False
            target_symbol = US_ALIASES[query]
        elif re.match(r'^[A-Za-z0-9\.]+$', query) and not any("\u3131" <= char <= "\u318E" or "\uAC00" <= char <= "\uD7A3" for char in query):
            is_korean = False
            target_symbol = query.upper()
        else:
            # 🚀 1단 로켓: ZUM 투자 API (외국 IP 절대 차단 안 함!)
            try:
                zum_url = f"https://finance.zum.com/api/search/auto-complete?keyword={urllib.parse.quote(query)}"
                zum_res = requests.get(zum_url, headers=headers)
                if zum_res.status_code == 200:
                    data = zum_res.json()
                    # ZUM에서 국내 주식 코드를 찾아냅니다. (예: 파마리서치 -> 214450)
                    if 'stocks' in data and len(data['stocks']) > 0:
                        is_korean = True
                        target_symbol = str(data['stocks'][0].get('code', ''))
            except Exception as e:
                print(f"ZUM API 에러: {e}")

            # 🚀 2단 로켓: 증권플러스(업비트) API (1단이 실패했을 때, 역시 차단 없음!)
            if not target_symbol:
                try:
                    sp_url = "https://stockplus.com/api/search.json"
                    sp_res = requests.get(sp_url, params={"keyword": query}, headers=headers)
                    if sp_res.status_code == 200:
                        items = sp_res.json().get('items', [])
                        if items:
                            first = items[0].get('item', {})
                            code = str(first.get('code', ''))
                            # 증권플러스는 한국 주식 앞에 'A'를 붙입니다 (예: A214450)
                            if code.startswith('A') and code[1:].isdigit():
                                is_korean = True
                                target_symbol = code[1:]
                except Exception as e:
                    print(f"StockPlus API 에러: {e}")

            # 🚀 3단 로켓: 야후 파이낸스 글로벌 (미국 주식 백업용)
            if not target_symbol:
                try:
                    yh_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(query)}"
                    yh_res = requests.get(yh_url, headers=headers)
                    if yh_res.status_code == 200:
                        for q in yh_res.json().get('quotes', []):
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
            return JSONResponse(status_code=404, content={"detail": f"'{query}' 종목을 찾을 수 없습니다. 정확한 이름을 입력해주세요."})

        # ==========================================
        # 🇰🇷 한국 주식 로직 (데이터 서버는 차단 안 됨!)
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
        # 🇺🇸 미국 주식 로직 (데이터 서버는 차단 안 됨!)
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
