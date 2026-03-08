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
# 🌟 1. 한국거래소(KRX) 2,500개 종목 자동 다운로드 엔진!
# ==========================================
def load_krx_data():
    stock_map = {}
    try:
        # 차단 당하지 않는 KRX 공식 상장법인목록 다운로드 통로!
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        res.encoding = 'euc-kr'
        
        # HTML 가위질로 종목명과 코드를 싹 긁어옵니다 (파마리서치도 여기 들어옵니다!)
        rows = re.findall(r'<tr.*?>(.*?)</tr>', res.text, re.IGNORECASE | re.DOTALL)
        for row in rows:
            cols = re.findall(r'<td.*?>(.*?)</td>', row, re.IGNORECASE | re.DOTALL)
            if len(cols) >= 2:
                name = re.sub(r'<[^>]+>', '', cols[0]).strip().replace('&amp;', '&')
                code = re.sub(r'<[^>]+>', '', cols[1]).strip()
                if code.isdigit() and len(code) in [5, 6]:
                    stock_map[name] = code.zfill(6)
                    
        # 공식 이름 외에 사람들이 부르는 한국 주식 애칭 추가
        kr_aliases = {
            '현대차': '005380', '기아차': '000270', '기아': '000270',
            '삼전': '005930', '삼성전자우': '005935', 'LG엔솔': '373220',
            'SK이노': '096770', '한화에어로': '012450', '카뱅': '323410',
            '엔씨': '036570', '엔씨소프트': '036570', '포스코': '005490', 
            'POSCO': '005490', '포스코홀딩스': '005490', '에코프로': '086520',
            '에코프로비엠': '247540', '루닛': '328130', '삼양식품': '003230'
        }
        stock_map.update(kr_aliases)
        print(f"✅ KRX 맵 로딩 완료! 총 {len(stock_map)}개 종목 기억 완료!")
    except Exception as e:
        print(f"KRX 로딩 실패: {e}")
    return stock_map

# 🌟 2. 해외 주식용 '글로벌 Top 30' 한국어 번역기 (애플, 테슬라 등 해결!)
US_ALIASES = {
    '애플': 'AAPL', '테슬라': 'TSLA', '엔비디아': 'NVDA', '마이크로소프트': 'MSFT', '마소': 'MSFT',
    '아마존': 'AMZN', '구글': 'GOOGL', '알파벳': 'GOOGL', '메타': 'META', '페이스북': 'META',
    '넷플릭스': 'NFLX', 'AMD': 'AMD', '인텔': 'INTC', 'TSMC': 'TSM', '퀄컴': 'QCOM',
    '팔란티어': 'PLTR', '스타벅스': 'SBUX', '코카콜라': 'KO', '펩시': 'PEP', '디즈니': 'DIS',
    '버크셔해서웨이': 'BRK.B', '브로드컴': 'AVGO', 'ASML': 'ASML', '일라이릴리': 'LLY', 
    '노보노디스크': 'NVO', '마이크론': 'MU', '쿠팡': 'CPNG', '코인베이스': 'COIN', '로블록스': 'RBLX'
}

# 서버 켜질 때 KRX 2,500개를 딱 한 번만 외웁니다.
KRX_MAP = load_krx_data()

@app.get("/")
@app.head("/")
def read_root():
    return {"status": "alive", "message": "Zero-Block Native Dictionary Engine is running."}

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
        # 🌟 3. 철통 보안 뚫는 스마트 라우터 (내장 번역기 우선!)
        # ==========================================
        if query.isdigit():
            is_korean = True
            target_symbol = query.zfill(6)
        # 내 머릿속(KRX 2,500개 + 애칭)에 있으면 0.001초 만에 바로 통과!
        elif query in KRX_MAP:
            is_korean = True
            target_symbol = KRX_MAP[query]
        # 미국 유명 주식을 한글로 검색했다면 번역기 가동!
        elif query in US_ALIASES:
            is_korean = False
            target_symbol = US_ALIASES[query]
        # AAPL 처럼 영어로 치면 그대로 패스!
        elif re.match(r'^[A-Za-z0-9\.]+$', query) and not any("\u3131" <= char <= "\u318E" or "\uAC00" <= char <= "\uD7A3" for char in query):
            is_korean = False
            target_symbol = query.upper()
        else:
            # 장부에도 없고 영어도 아니면, 야후 파이낸스 글로벌 검색기로 최후의 시도!
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
        # 🇰🇷 4. 한국 주식 로직 (차단율 0% 데이터 서버)
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
        # 🇺🇸 5. 미국 주식 로직 (차단율 0% 데이터 서버)
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
