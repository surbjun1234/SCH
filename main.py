import requests
import re
import os
from datetime import datetime
import difflib
from bs4 import BeautifulSoup
from urllib.parse import quote

# --- [전역 설정값] ---
TARGET_YEAR = "2026"
# 깃허브 액션 환경변수에서 웹훅 주소를 가져옵니다.
DISCORD_WEBHOOK_URL = os.environ.get("WEBHOOK_DATE") 
# 배포용이므로 TEST_DATE는 None으로 설정
TEST_DATE = None 

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.knu.ac.kr/"
}

def is_date_in_range(target_date_str, period_str):
    try:
        t_month, t_day = map(int, target_date_str.split('.'))
        dates = re.findall(r'(\d{1,2})\.(\d{1,2})', period_str)
        if not dates: return False
        start_m, start_d = map(int, dates[0])
        if len(dates) == 1:
            return t_month == start_m and t_day == start_d
        else:
            target_dt = datetime(int(TARGET_YEAR), t_month, t_day)
            start_dt = datetime(int(TARGET_YEAR), start_m, start_d)
            end_dt = datetime(int(TARGET_YEAR), int(dates[1][0]), int(dates[1][1])) if len(dates) > 1 else start_dt
            return start_dt <= target_dt <= end_dt
    except: return False

def find_best_notice(keyword):
    search_keyword = re.sub(r'\(.*?\)', '', keyword).strip()
    search_keyword = re.sub(r'\d+\.\d+\.?\s*~?\s*\d*\.?\d*\.?', '', search_keyword).strip()
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
            doc_id = re.search(r"'\d+'\s*,\s*'\w+'\s*,\s*'(\d+)'", js_link)
            final_link = f"https://www.knu.ac.kr/wbbs/wbbs/bbs/btin/stdRead.action?menu_idx=42&btin_num={doc_id.group(1)}" if doc_id else url
            score = difflib.SequenceMatcher(None, search_keyword.replace(" ",""), title.replace(" ","")).ratio()
            if search_keyword in title: score += 0.3
            notices.append({"title": title, "link": final_link, "score": score})
        if not notices: return None
        best = max(notices, key=lambda x: x['score'])
        return best if best['score'] >= 0.4 else None
    except: return None

def send_discord(schedule_list, best_notice, current_date):
    if not DISCORD_WEBHOOK_URL:
        print("WEBHOOK_DATE 설정이 되어있지 않습니다.")
        return

    # 메시지 구성
    description = "**📌 오늘 진행되는 일정**\n" + "\n".join([f"• {item}" for item in schedule_list])
    notice_value = f"[{best_notice['title']}]({best_notice['link']})" if best_notice else "🔍 비슷한 학사공지를 찾지 못했습니다."
    color = 15158332 if best_notice else 8421504

    payload = {
        "embeds": [{
            "title": f"❗ 오늘의 일정 ({current_date})",
            "description": description,
            "fields": [{"name": "🔗 관련 공지사항", "value": notice_value}],
            "color": color,
            "footer": {"text": "KNU Scheduler Bot"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def main():
    raw_date = TEST_DATE if TEST_DATE else datetime.now().strftime("%m.%d")
    parts = raw_date.split('.')
    target_date = f"{int(parts[0]):02d}.{int(parts[1]):02d}"

    schedule_url = f"https://www.knu.ac.kr/wbbs/wbbs/user/yearSchedule/index.action?menu_idx=43&vo.search_year={TARGET_YEAR}"
    resp = requests.get(schedule_url, headers=HEADERS)
    matches = re.findall(r'(\d{2}\.\d{2}\(.\))(.*?)</li>', resp.text, re.DOTALL)
    
    today_items = []
    for date_label, raw_content in matches:
        content = re.sub(r'<.*?>', '', raw_content).replace('</span>', '').strip()
        content = re.sub(r'\s+', ' ', content)
        period_match = re.search(r'\((\d{1,2}\.\d{1,2}\.?.*?)\)$', content)
        if (period_match and is_date_in_range(target_date, period_match.group(1))) or (target_date in date_label):
            today_items.append(content)

    if today_items:
        best_notice = find_best_notice(today_items[0])
        send_discord(today_items, best_notice, target_date)

if __name__ == "__main__":
    main()
