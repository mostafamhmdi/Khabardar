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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0"
]

def get_page_with_retry(url, max_retries=3):
    for attempt in range(1, max_retries + 1):
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive"
        }
        try:
            response = requests.get(url, headers=headers, timeout=(10, 30))
            if response.status_code in [500, 502, 503, 504]:
                print(f"  ⚠️ خطای سرور {response.status_code}. تلاش {attempt}...")
                time.sleep(random.uniform(2, 5))
                continue
            return response
        except requests.exceptions.Timeout:
            print(f"  ⏳ تایم‌اوت. تلاش {attempt}...")
            time.sleep(random.uniform(2, 5))
        except requests.exceptions.RequestException:
            print(f"  ❌ خطای ارتباطی. تلاش {attempt}...")
            time.sleep(random.uniform(2, 5))
    return None

def parse_mehr_date(raw_date_str):
    """
    دریافت تاریخ خام خبرگزاری مهر و تبدیل آن به شمسی تمیز و میلادی
    نمونه: ۲۸ شهریور ۱۴۰۵، ۱۳:۰۰
    """
    if not raw_date_str:
        return "", None

    clean_str = raw_date_str.replace('،', ' - ').strip()
    
    persian_to_eng = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    clean_str_eng = clean_str.translate(persian_to_eng)

    match = re.search(r'(\d{1,2})\s+([آ-یي]+)\s+(\d{4})', clean_str_eng)
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
# منطق بهینه‌سازی (بررسی تکراری بودن در دیتابیس)
# ==========================================

def filter_new_links(db, links_set):
    """
    بررسی دسته‌جمعی لینک‌ها در دیتابیس و برگرداندن فقط لینک‌های جدید
    """
    if not links_set:
        return set()
        
    print(f"  🔍 بررسی {len(links_set)} لینک با دیتابیس جهت یافتن اخبار جدید...")
    
    new_links = set()
    try:
        link_id_map = {}
        for url in links_set:
            match = re.search(r'/news/(\d+)', url)
            if match:
                news_id = f"mehr_{match.group(1)}"
                link_id_map[news_id] = url
        
        if not link_id_map:
            return links_set

        ids_to_check = tuple(link_id_map.keys())
        query = "SELECT id FROM articles WHERE id IN %s"
        
        db.cursor.execute(query, (ids_to_check,))
        existing_ids = {row[0] for row in db.cursor.fetchall()}
        
        for news_id, url in link_id_map.items():
            if news_id not in existing_ids:
                new_links.add(url)
                
        print(f"  ✅ تعداد {len(new_links)} لینک جدید برای دانلود پیدا شد.")
        return new_links

    except Exception as e:
        print(f"  ⚠️ خطا در اعتبارسنجی دیتابیس (ادامه با تمام لینک‌ها): {e}")
        db.conn.rollback()
        return links_set

# ==========================================
# بدنه اصلی کرالر مهر
# ==========================================

def crawl_mehrnews():
    db = NewsDatabase(dbname="news_db", user="postgres", password="bvncxz62")

    target_pages = [
        "https://www.mehrnews.com/",
        "https://www.mehrnews.com/service/Culture",
        "https://www.mehrnews.com/service/Art",
        "https://www.mehrnews.com/service/HiTech",
        "https://www.mehrnews.com/service/Society",
        "https://www.mehrnews.com/service/Economy",
        "https://www.mehrnews.com/service/Politic",
        "https://www.mehrnews.com/service/International"
    ]

    all_scraped_links = set()
    base_domain = "https://www.mehrnews.com"

    print("🔍 جمع‌آوری لینک‌های اولیه از صفحات خبرگزاری مهر...")
    print("-" * 50)

    # ۱. استخراج لینک‌ها
    for page_url in target_pages:
        resp = get_page_with_retry(page_url)
        if resp and resp.status_code == 200:
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            elements = soup.select('.desc a')
            for el in elements:
                href = el.get('href')
                if href and '/news/' in href:
                    full_url = base_domain + href if href.startswith('/') else href
                    all_scraped_links.add(full_url)
            
            page_name = urllib.parse.unquote(page_url.split('/')[-1]) or 'صفحه اصلی'
            print(f"  ✔️ لینک‌های صفحه [{page_name}] استخراج شد.")
        time.sleep(random.uniform(1, 2))

    print("-" * 50)
    
    # ۲. فیلتر کردن لینک‌های تکراری
    unique_new_links = filter_new_links(db, all_scraped_links)
    
    if not unique_new_links:
        print("🎉 هیچ خبر جدیدی برای دانلود وجود ندارد.")
        if 'db' in locals():
            db.close()
        return

    print("-" * 50)
    
    # ۳. ورود به اخبار جدید
    counter = 1
    for url in unique_new_links:
        print(f"[{counter}/{len(unique_new_links)}] پردازش: {urllib.parse.unquote(url.split('/')[-1][:30])}...")

        art_resp = get_page_with_retry(url)
        if art_resp and art_resp.status_code == 200:
            try:
                art_resp.encoding = 'utf-8'
                art_soup = BeautifulSoup(art_resp.text, 'html.parser')

                # --- تیتر ---
                title_tag = art_soup.select_one('.title')
                title_text = title_tag.get_text(strip=True) if title_tag else ""

                # --- لید ---
                lead_tag = art_soup.select_one('.introtext')
                lead_text = lead_tag.get_text(strip=True) if lead_tag else ""

                # --- دسته‌بندی ---
                # با انتخاب اولین لینک داخل breadcrumb، دسته‌بندی اصلی (مثل "فرهنگ و ادب") استخراج می‌شود
                cat_tag = art_soup.select_one('.breadcrumb li a')
                category = cat_tag.get_text(strip=True) if cat_tag else None

                # --- تاریخ ---
                date_tag = art_soup.select_one('.item-date span')
                raw_date = date_tag.get_text(strip=True) if date_tag else ""
                persian_date, gregorian_date = parse_mehr_date(raw_date)

                # --- بدنه ---
                p_tags = art_soup.select('.item-text p')
                body_text = "\n\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])

                # --- آیدی ---
                match_id = re.search(r'/news/(\d+)', url)
                news_id = f"mehr_{match_id.group(1)}" if match_id else f"mehr_{url.split('/')[-1][:20]}"

                # --- آماده‌سازی و ذخیره ---
                article_data = {
                    'id': news_id,
                    'source_name': 'mehr',
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
                print(f"  ❌ خطا در پردازش محتوا: {e}")

        counter += 1
        time.sleep(random.uniform(2, 4))

    if 'db' in locals():
        db.close()

if __name__ == "__main__":
    crawl_mehrnews()