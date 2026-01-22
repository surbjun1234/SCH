import requests
import re
import os
from datetime import datetime, timedelta, timezone
import difflib
from bs4 import BeautifulSoup
from urllib.parse import quote

# --- [1. 전역 설정값] ---
TARGET_YEAR = "2026"
# GitHub Actions Secrets의 'WEBHOOK_DATE' 환경변수 사용
DISCORD_WEBHOOK_URL = os.environ.get("WEBHOOK_DATE") 

# 실전 배포용 (None일 때 한국 시간 기준 작동)
TEST_DATE = "1.22."

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.knu.ac.kr/"
}

# --- [2. 로직 함수] ---

def is_date_in_range(target_date_str, period_str):
    """숫자 기반 정밀 비교로 날짜 오탐지를 방지하고 기간 내 포함 여부를 체크합니다."""
    try:
        t_month, t_day = map(int, target_date_str.split('.'))
        dates = re.findall(r'(\d{1,2})\.(\d{1,2})', period_str)
        if not dates: return False
        
        start_m, start_d = map(int, dates[0])
        # 단일 날짜 체크 (예: 11.24.)
        if len(dates) == 1:
            return t_month == start_m and t_day == start_d
        # 기간 체크 (예: 1.20.~1.22.)
        else:
            target_dt = datetime(int(TARGET_YEAR), t_month, t_day)
            start_dt = datetime(int(TARGET_YEAR), start_m, start_d)
            end_m, end_d = map(int, dates[1])
            end_dt = datetime(int(TARGET_YEAR), end_m, end_d)
            return start_dt <= target_dt <= end_dt
    except:
        return False

def find_best_notice(keyword):
    """학사공지 상세 페이지 링크를 생성하고 유사도 임계값(0.4)을 체크합니다."""
    search_keyword = re.sub(r'\(.*?\)', '', keyword).strip()
    search_keyword = re.sub(r'\d+\.\d+\.?\s*~?\s*\d*\.?\d*\.?', '', search_keyword).strip()
    
    view_base = "https://www.knu.ac.kr/wbbs/wbbs/bbs/btin/stdViewBtin.action?search_type=&search_text=&popupDeco=&note_div=row&menu_idx=42&bbs_cde=stu_812&bltn_no="
    
    encoded_key = quote(search_keyword, encoding='utf-8')
    url = f"https://www.knu.ac.kr/wbbs/wbbs/bbs/btin/stdList.action?search_type=search_subject&search_text={encoded_key}&menu_idx=42"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        subjects = soup.select("td.subject a")
        
        notices = []
        for a in subjects:
            title = a.get_text(strip=True)
            js_link = a.get('href', '')
            doc_id_match = re.search(r"'\w+'\s*,\s*'\w+'\s*,\s*'(\d+)'", js_link)
            
            if doc_id_match:
                final_link = view_base + doc_id_match.group(1)
            else:
                final_link = "https://www.knu.ac.kr/wbbs/wbbs/bbs/btin/stdList.action?menu_idx=42"
                
            score = difflib.SequenceMatcher(None, search_keyword.replace(" ",""), title.replace(" ","")).ratio()
            if search_keyword in title: score += 0.3
            notices.append({"title": title, "link": final_link, "score": score})
        
        if not notices: return None
        best = max(notices, key=lambda x: x['score'])
        return best if best['score'] >= 0.4 else None
    except:
        return None

def send_discord(schedule_list, best_notice, current_date):
    """필드 제목을 없애고 본문 내에 일정과 링크를 통합하여 전송합니다."""
    if not DISCORD_WEBHOOK_URL:
        print("WEBHOOK_DATE 환경변수가 설정되지 않았습니다.")
        return

    # 1. 휴대폰 알림바 요약 (content)
    summary_items = ", ".join(schedule_list)
    alert_payload_text = f"❗ **오늘의 일정: {summary_items}**"

    # 2. 본문 내용 구성 (embed description)
    # 각 일정 항목을 두껍게 강조
    description_content = "".join([f"• **{item}**\n" for item in schedule_list])
    
    # 공지사항 링크 직접 노출 (불필요한 설명 문구 제거)
    if best_notice:
        description_content += f"\n🔗 **[{best_notice['title']}]({best_notice['link']})**"
    else:
        description_content += "\n🔍 **관련 공지사항 없음**"
    
    color = 15158332 if best_notice else 8421504 # Crimson or Grey

    payload = {
        "content": alert_payload_text,
        "embeds": [{
            "title": "❗ 오늘의 일정",
            "description": f"{description_content}",
            "color": color,
            "footer": {"text": "KNU Scheduler Bot"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

# --- [3. 메인 실행부] ---

def main():
    # 한국 표준시(KST) 설정 (UTC+9)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)

    # 날짜 보정 (서버 위치와 상관없이 한국 시간 기준)
    raw_date = TEST_DATE if TEST_DATE else now_kst.strftime("%m.%d")
    parts = raw_date.split('.')
    target_date = f"{int(parts[0]):02d}.{int(parts[1]):02d}"

    print(f"🚀 {target_date} (KST 기준) 일정 체크 시작...")
    
    # 학사일정 로드
    schedule_url = f"https://www.knu.ac.kr/wbbs/wbbs/user/yearSchedule/index.action?menu_idx=43&vo.search_year={TARGET_YEAR}"
    resp = requests.get(schedule_url, headers=HEADERS)
    matches = re.findall(r'(\d{2}\.\d{2}\(.\))(.*?)</li>', resp.text, re.DOTALL)
    
    today_items = []
    for date_label, raw_content in matches:
        content = re.sub(r'<.*?>', '', raw_content).replace('</span>', '').strip()
        content = re.sub(r'\s+', ' ', content)
        
        # 일정 괄호 안의 기간 정보 추출
        period_match = re.search(r'\((\d{1,2}\.\d{1,2}\.?.*?)\)$', content)
        
        is_matched = False
        if period_match and is_date_in_range(target_date, period_match.group(1)):
            is_matched = True
        elif target_date in date_label:
            is_matched = True
            
        if is_matched:
            today_items.append(content)

    # 일정이 있을 때만 전송
    if today_items:
        print(f"🎯 {len(today_items)}개의 일정이 발견되었습니다.")
        # 대표 키워드로 공지 검색
        best_notice = find_best_notice(today_items[0])
        send_discord(today_items, best_notice, target_date)
    else:
        print(f"ℹ️ {target_date}에는 해당하는 학사일정이 없어 알림을 보내지 않습니다.")

if __name__ == "__main__":
    main()
