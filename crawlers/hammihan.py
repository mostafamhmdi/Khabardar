import requests
from bs4 import BeautifulSoup
import time
import random
import re
import jdatetime
import urllib.parse
from db_manager import NewsDatabase

# ==========================================
# توابع کمکی و ارتباطی
# ==========================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
]

def get_page_with_retry(url, max_retries=3):
    """
    ارسال درخواست با قابلیت تلاش مجدد و مدیریت تایم‌اوت
    """
    for attempt in range(1, max_retries + 1):
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=(10, 30))
            if response.status_code in [500, 502, 503, 504]:
                print(f"  ⚠️ خطای سرور {response.status_code}. تلاش {attempt} از {max_retries}...")
                time.sleep(random.uniform(2, 5))
                continue
            return response
            
        except requests.exceptions.Timeout:
            print(f"  ⏳ تایم‌اوت رخ داد! تلاش {attempt} از {max_retries}...")
            time.sleep(random.uniform(2, 5))
        except requests.exceptions.RequestException as e:
            print(f"  ❌ خطای ارتباطی موقت. تلاش {attempt} از {max_retries}...")
            time.sleep(random.uniform(2, 5))
            
    return None

def parse_hammihan_date(raw_date_str):
    """
    دریافت تاریخ خام هم‌میهن و تبدیل آن به شمسی تمیز و میلادی
    """
    if not raw_date_str:
        return "", None

    # حذف فاصله‌های اضافی و خطوط جدید
    clean_str = re.sub(r'\s+', ' ', raw_date_str).strip()
    
    # تبدیل اعداد فارسی به انگلیسی
    persian_to_eng_map = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    clean_str = clean_str.translate(persian_to_eng_map)

    # استخراج روز، ماه و سال
    match = re.search(r'(\d{1,2})\s+([آ-یي]+)\s+(\d{4})', clean_str)
    gregorian_date = None

    if match:
        day = int(match.group(1))
        month_name = match.group(2).replace('ي', 'ی')
        year = int(match.group(3))

        months = {
            'فروردین': 1, 'اردیبهشت': 2, 'خرداد': 3, 'تیر': 4, 'مرداد': 5,
            'شهریور': 6, 'مهر': 7, 'آبان': 8, 'آذر': 9, 'دی': 10, 'بهمن': 11, 'اسفند': 12
        }

        month = months.get(month_name)
        if month:
            try:
                greg_date = jdatetime.date(year, month, day).togregorian()
                gregorian_date = greg_date.strftime("%Y-%m-%d")
            except Exception as e:
                print(f"  ⚠️ خطا در محاسبه تاریخ میلادی: {e}")

    return clean_str, gregorian_date

# ==========================================
# بدنه اصلی کرالر هم‌میهن
# ==========================================

def crawl_hammihan():
    db = NewsDatabase(dbname="news_db", user="postgres", password="bvncxz62")

    target_pages = [
        "https://hammihanonline.ir/%D8%A8%D8%AE%D8%B4-%D8%B3%DB%8C%D8%A7%D8%B3%D8%AA-18",
        "https://hammihanonline.ir/%D8%A8%D8%AE%D8%B4-%D8%A7%D9%82%D8%AA%D8%B5%D8%A7%D8%AF-5",
        "https://hammihanonline.ir/%D8%A8%D8%AE%D8%B4-%D8%A8%DB%8C%D9%86-%D8%A7%D9%84%D9%85%D9%84%D9%84-20",
        "https://hammihanonline.ir/%D8%A8%D8%AE%D8%B4-%D8%AC%D8%A7%D9%85%D8%B9%D9%87-23",
        "https://hammihanonline.ir/%D8%A8%D8%AE%D8%B4-%D9%81%D8%B1%D9%87%D9%86%DA%AF-27",
        "https://hammihanonline.ir/%D8%A8%D8%AE%D8%B4-%D8%A7%D8%AE%D8%A8%D8%A7%D8%B1-2"
    ]

    unique_links = set()
    base_domain = "https://hammihanonline.ir"

    print("🔍 در حال جمع‌آوری لینک‌ها از صفحات اصلی هم‌میهن...")
    print("-" * 50)

    # ۱. جمع‌آوری لینک‌ها
    for page_url in target_pages:
        resp = get_page_with_retry(page_url)
        if resp and resp.status_code == 200:
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')

            # جستجو در هر دو ساختاری که معرفی کردید
            selectors = ['.detaile .title', '.latest_news .items a.title']
            
            for selector in selectors:
                elements = soup.select(selector)
                for el in elements:
                    href = el.get('href')
                    if href:
                        # اگر لینک نسبی بود، دامنه را به آن اضافه کن
                        full_url = base_domain + href if href.startswith('/') else href
                        unique_links.add(full_url)
            
            # چاپ نام دسته‌بندی برای پیگیری
            cat_name_display = urllib.parse.unquote(page_url.split('/')[-1])
            print(f"  ✔️ صفحه پردازش شد: {cat_name_display}")
        else:
            print(f"  ❌ دریافت صفحه {page_url} با وجود تلاش مجدد ناموفق بود.")
            
        time.sleep(random.uniform(1, 3))

    print("-" * 50)
    print(f"✅ مجموعاً {len(unique_links)} لینک یکتا استخراج شد. شروع دریافت جزئیات اخبار...\n")

    # ۲. ورود به تک‌تک لینک‌ها
    counter = 1
    for url in unique_links:
        print(f"[{counter}/{len(unique_links)}] پردازش: {urllib.parse.unquote(url.split('/')[-1][:30])}...")

        art_resp = get_page_with_retry(url)
        if art_resp and art_resp.status_code == 200:
            try:
                art_resp.encoding = 'utf-8'
                art_soup = BeautifulSoup(art_resp.text, 'html.parser')

                # --- دسته‌بندی ---
                cat_tag = art_soup.select_one('.space + a')
                category = cat_tag.get_text(strip=True) if cat_tag else None

                # --- تاریخ ---
                date_tag = art_soup.select_one('.time')
                raw_date = date_tag.get_text(strip=True) if date_tag else ""
                persian_date, gregorian_date = parse_hammihan_date(raw_date)

                # --- تیتر و لید ---
                title_tag = art_soup.select_one('.article_header .title')
                title_text = title_tag.get_text(strip=True) if title_tag else "بدون تیتر"

                lead_tag = art_soup.select_one('.article_header .lead')
                lead_text = lead_tag.get_text(strip=True) if lead_tag else ""

                # --- بدنه خبر (Body) ---
                body_text = ""
                body_container = art_soup.select_one('.ck_editor')
                
                if body_container:
                    # گام جادویی: حذف قسمت‌های ناخواسته قبل از استخراج متن
                    
                    # 1. حذف بخش "به کانال تلگرام بپیوندید"
                    end_message = body_container.select_one('.end_message')
                    if end_message:
                        end_message.decompose() # این دستور تگ را به کل از HTML پاک می‌کند
                    
                    # 2. حذف بلوک تبلیغات یا کدهای جاوا اسکریپت داخل بدنه
                    position_h0 = body_container.select_one('#position_H0')
                    if position_h0:
                        position_h0.decompose()

                    # 3. گرفتن پاراگراف‌های باقی‌مانده
                    p_tags = body_container.find_all('p')
                    body_text = "\n\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])

                # --- آیدی یکتا ---
                # استخراج از تگ "کد مطلب: ۷۱۷۹۵"
                code_tag = art_soup.select_one('.news_code')
                news_id = None
                
                if code_tag:
                    raw_code = code_tag.get_text(strip=True)
                    # تبدیل عدد فارسی به انگلیسی برای Regex
                    persian_to_eng = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
                    raw_code_eng = raw_code.translate(persian_to_eng)
                    
                    match_id = re.search(r'(\d+)', raw_code_eng)
                    if match_id:
                        news_id = f"hammihan_{match_id.group(1)}"
                
                # اگر تگ کد مطلب پیدا نشد، از URL استخراج می‌کنیم
                if not news_id:
                    # مثال: /بخش-سیاست-18/71822-جزئیات... -> استخراج 71822
                    match_url_id = re.search(r'/(\d+)-', url)
                    if match_url_id:
                        news_id = f"hammihan_{match_url_id.group(1)}"
                    else:
                        news_id = f"hammihan_{url.split('/')[-1][:20]}"

                # --- ذخیره در دیتابیس ---
                article_data = {
                    'id': news_id,
                    'source_name': 'hammihan',
                    'url': url,
                    'title': title_text,
                    'lead': lead_text,
                    'persian_date': persian_date,
                    'gregorian_date': gregorian_date,
                    'categories': category,
                    'body': body_text,
                    'tone': None
                }

                db.insert_article(article_data)

            except Exception as e:
                print(f"  ❌ خطا در پردازش محتوای خبر: {e}")
        else:
            print("  ❌ اسکیپ شد (عدم پاسخ سرور).")

        counter += 1
        time.sleep(random.uniform(2, 4))

    if 'db' in locals():
        db.close()

if __name__ == "__main__":
    crawl_hammihan()