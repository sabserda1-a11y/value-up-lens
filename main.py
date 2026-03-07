기획자님, 정말 예리하십니다! 퀀트 분석기의 핵심은 역시 '정확한 재무 데이터'죠. 샘플 데이터로 멈춰있던 퀀트 지표(PBR, ROE)와 점수(Score)를 진짜 데이터로 살아 숨 쉬게 만들어보겠습니다.

이걸 해결하기 위해 백엔드에서 네이버 금융의 웹페이지를 살짝 읽어와서 진짜 PBR과 PER을 추출한 뒤, 수학적 금융 공식을 이용해 ROE를 역산하는 똑똑한 기획을 적용해 볼 겁니다.

💡 기획의 묘미: ROE를 구하는 마법의 공식
사실 ROE = PBR / PER * 100 이라는 완벽한 재무 비율 공식이 성립합니다.
네이버 금융은 PBR과 PER을 아주 찾기 쉬운 형태(<em id="_pbr">)로 제공하기 때문에, 이 두 숫자만 쏙 빼온 다음 공식에 대입하면 어렵게 재무제표를 뒤지지 않고도 정확한 ROE를 구할 수 있습니다!

🚀 최종 진화형 main.py (리얼 퀀트 데이터 탑재)
기존 main.py의 코드를 전부 지우고, 아래의 '완전판' 코드로 덮어씌워 주세요. 이 코드는 실시간 주가, 6개월 차트, 그리고 진짜 재무 데이터(PBR, ROE, 퀀트 스코어)까지 모두 자동으로 계산합니다.

Python
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
    return {"status": "alive", "message": "Value-Up Lens API (Naver Finance + Real Quant) is running."}

@app.get("/api/stock/{query}")
def get_stock_data(query: str):
    try:
        query = query.strip()
        
        # 1. 하이브리드 검색 (이름 or 코드)
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

        # 2. 실시간 주가 및 이름 가져오기
        realtime_url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{symbol}"
        realtime_res = requests.get(realtime_url, headers=headers).json()
        
        try:
            item_data = realtime_res['result']['areas'][0]['datas'][0]
            name = item_data['nm']
            current_price = int(str(item_data['nv']).replace(',', ''))
        except:
            return {"detail": "실시간 데이터를 가져오는 데 실패했습니다."}

        # 3. 120일 차트 데이터 가져오기
        try:
            history_url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=120&requestType=0"
            history_res = requests.get(history_url, headers=headers).text
            
            trend_list = []
            date_list = []
            
            for line in history_res.split('\n'):
                if '<item data=' in line:
                    parts = line.split('"')[1].split('|')
                    raw_date = parts[0]
                    formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}" 
                    
                    date_list.append(formatted_date)
                    trend_list.append(int(parts[4]))
            
            if not trend_list:
                trend_list = [current_price] * 5
                date_list = ["데이터 없음"] * 5
        except:
            trend_list = [current_price] * 5
            date_list = ["데이터 없음"] * 5 

        # 4. [신규 기능] 진짜 퀀트 데이터 스크래핑 및 ROE 계산
        pbr = 0.0
        per = 0.0
        roe = 0.0
        
        try:
            main_url = f"https://finance.naver.com/item/main.naver?code={symbol}"
            main_html = requests.get(main_url, headers=headers).text
            
            # id="_pbr" 부분을 찾아서 숫자만 빼오기
            if 'id="_pbr">' in main_html:
                pbr_str = main_html.split('id="_pbr">')[1].split('</')[0].strip()
                pbr = float(pbr_str.replace(',', ''))
            
            # id="_per" 부분을 찾아서 숫자만 빼오기
            if 'id="_per">' in main_html:
                per_str = main_html.split('id="_per">')[1].split('</')[0].strip()
                per = float(per_str.replace(',', ''))
                
            # ROE = PBR / PER * 100 공식 적용!
            if per > 0 and pbr > 0:
                roe = round((pbr / per) * 100, 2)
                
        except Exception as e:
            print(f"🔥 퀀트 파싱 에러: {e}")

        # 5. [신규 기능] 진짜 데이터를 기반으로 한 퀀트 스코어 (100점 만점)
        score = 50 # 기본 점수
        
        # PBR 가치평가 (낮을수록 저평가)
        if 0 < pbr <= 0.8:
            score += 25
        elif 0.8 < pbr <= 1.2:
            score += 15
        elif pbr > 2.0:
            score -= 15
            
        # ROE 수익성 평가 (높을수록 우량기업)
        if roe >= 15:
            score += 20
        elif 8 <= roe < 15:
            score += 10
        elif roe < 0:
            score -= 10
            
        score = min(max(int(score), 10), 98) # 점수가 10~98점 사이를 안 벗어나게 보정

        # 6. 프론트엔드로 최종 발송
        return {
            "name": name,
            "price": f"{current_price:,}",
            "pbr": pbr,    
            "roe": roe,    
            "score": score,    
            "trend": trend_list,
            "dates": date_list
        }

    except Exception as e:
        return {"detail": f"서버 에러: {str(e)}"}
    
# 실행: uvicorn main:app --reload
