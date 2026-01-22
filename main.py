def find_best_notice(keyword):
    """학사공지 상세 페이지 주소 체계(stdViewBtin.action)에 맞춰 링크를 생성합니다."""
    search_keyword = re.sub(r'\(.*?\)', '', keyword).strip()
    search_keyword = re.sub(r'\d+\.\d+\.?\s*~?\s*\d*\.?\d*\.?', '', search_keyword).strip()
    
    # 1. 학사공지 상세 페이지 베이스 URL
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
            
            # 2. 자바스크립트 인자 중 3번째 숫자가 bltn_no (고유번호) 임
            # 예: doRead('stu_812', 'top', '11768380391709') -> '11768380391709' 추출
            doc_id_match = re.search(r"'\w+'\s*,\s*'\w+'\s*,\s*'(\d+)'", js_link)
            
            if doc_id_match:
                # 추출한 번호를 베이스 URL 뒤에 결합
                final_link = view_base + doc_id_match.group(1)
            else:
                final_link = url # 못 찾으면 리스트 페이지로 연결
                
            score = difflib.SequenceMatcher(None, search_keyword.replace(" ",""), title.replace(" ","")).ratio()
            if search_keyword in title: score += 0.3
            notices.append({"title": title, "link": final_link, "score": score})
        
        if not notices: return None
        best = max(notices, key=lambda x: x['score'])
        return best if best['score'] >= 0.4 else None
    except Exception as e:
        print(f"공지사항 링크 생성 중 오류: {e}")
        return None
