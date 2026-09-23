import time
import random
import re
import jdatetime
import requests
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup
from db_manager import NewsDatabase

# ==========================================
# تنظیمات پایه
# ==========================================
BASE_URL = "https://eslahatnews.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

# ==========================================
# توابع کمکی
# ==========================================
def parse_eslahat_date(raw_date_str):
    if not raw_date_str:
        return "", None

    # پاکسازی متن (حذف فاصله‌ها و کاراکترهای اضافی)
    clean_str = re.sub(r'\s+', ' ', raw_date_str).strip()
    
    # تبدیل اعداد فارسی به انگلیسی
    persian_to_eng = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    clean_str_eng = clean_str.translate(persian_to_eng)

    # جستجوی فرمت YYYY/MM/DD
    match = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})', clean_str_eng)
    gregorian_date = None

    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            greg_date = jdatetime.date(year, month, day).togregorian()
            gregorian_date = greg_date.strftime("%Y-%m-%d")
            # استخراج بخش متنی تاریخ (مثلا ۱۴۰۵/۰۶/۳۰)
            clean_str = f"{year:04d}/{month:02d}/{day:02d}".translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
        except Exception as e:
            print(f"  ⚠️ خطا در محاسبه تاریخ میلادی: {e}")

    return clean_str, gregorian_date

def filter_new_links(db, links_set):
    if not links_set:
        return set()
        
    print(f"  🔍 بررسی {len(links_set)} لینک با دیتابیس جهت یافتن اخبار جدید...")
    new_links = set()
    try:
        urls_to_check = tuple(links_set)
        if not urls_to_check:
            return links_set

        query = "SELECT url FROM articles WHERE url IN %s"
        db.cursor.execute(query, (urls_to_check,))
        existing_urls = {row[0] for row in db.cursor.fetchall()}
        
        for url in links_set:
            if url not in existing_urls:
                new_links.add(url)
                
        print(f"  ✅ تعداد {len(new_links)} لینک جدید برای دانلود پیدا شد.")
        return new_links

    except Exception as e:
        print(f"  ⚠️ خطا در اعتبارسنجی دیتابیس (ادامه با تمام لینک‌ها): {e}")
        db.conn.rollback()
        return links_set

# ==========================================
# بدنه اصلی کرالر اصلاحات نیوز
# ==========================================
def crawl_eslahatnews():
    db = NewsDatabase(dbname="news_db", user="postgres", password="bvncxz62")
    all_scraped_links = set() # استفاده از set برای حذف اتوماتیک تکراری‌ها در مرحله اول

    print("🚀 شروع جمع‌آوری لینک‌های اولیه از سایت اصلاحات نیوز...")
    print("-" * 50)

    # ---------------------------------------------------------
    # ۱. جمع آوری لینک‌ها از صفحه اصلی (Type 1)
    # ---------------------------------------------------------
    try:
        res = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # استخراج تگ‌های لینک داخل .text-box
        homepage_links = soup.select('.text-box a.main_title_a')
        for a in homepage_links:
            href = a.get('href')
            if href:
                full_url = urljoin(BASE_URL, href)
                all_scraped_links.add(full_url)
                
        print(f"  ✔️ صفحه اصلی بررسی شد. (یافتن {len(homepage_links)} لینک)")
    except Exception as e:
        print(f"  ❌ خطا در دریافت صفحه اصلی: {e}")

    # ---------------------------------------------------------
    # ۲. جمع آوری لینک‌ها از صفحات دسته‌بندی (Type 2)
    # ---------------------------------------------------------
    categories = [
        '/fa/political', 
        '/fa/reformnews', 
        '/fa/economic', 
        '/fa/social', 
        '/fa/culture'
    ]
    
    for cat in categories:
        cat_url = urljoin(BASE_URL, cat)
        try:
            res = requests.get(cat_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            cat_links = soup.select('.box_title')
            for a in cat_links:
                href = a.get('href')
                if href:
                    full_url = urljoin(BASE_URL, href)
                    all_scraped_links.add(full_url)
                    
            print(f"  ✔️ دسته‌بندی {cat} بررسی شد.")
            time.sleep(random.uniform(1, 2)) # وقفه کوتاه بین درخواست‌ها
        except Exception as e:
            print(f"  ❌ خطا در دریافت دسته‌بندی {cat}: {e}")

    print("-" * 50)
    
    # ---------------------------------------------------------
    # ۳. فیلتر کردن لینک‌های تکراری با دیتابیس
    # ---------------------------------------------------------
    unique_new_links = filter_new_links(db, all_scraped_links)
    
    if not unique_new_links:
        print("🎉 هیچ خبر جدیدی در اصلاحات نیوز برای دانلود وجود ندارد.")
        if 'db' in locals():
            db.close()
        return

    print("-" * 50)
    
    # ---------------------------------------------------------
    # ۴. ورود به اخبار جدید و استخراج محتوا
    # ---------------------------------------------------------
    counter = 1
    for url in unique_new_links:
        try:
            # استخراج نام خبر برای نمایش در کنسول
            print(f"[{counter}/{len(unique_new_links)}] پردازش: {unquote(url.split('/')[-1][:40])}...")

            res = requests.get(url, headers=HEADERS, timeout=15)
            art_soup = BeautifulSoup(res.text, 'html.parser')

            # --- تیتر ---
            title_tag = art_soup.select_one('.main_news_title')
            title_text = title_tag.get_text(strip=True) if title_tag else "بدون تیتر"

            # --- تاریخ ---
            date_tag = art_soup.select_one('.news_pdate_d')
            raw_date = date_tag.get_text(strip=True) if date_tag else ""
            persian_date, gregorian_date = parse_eslahat_date(raw_date)

            # --- لید (روتیتر / زیرتیتر) ---
            lead_tag = art_soup.select_one('.news_subtitle')
            lead_text = lead_tag.get_text(strip=True) if lead_tag else ""

            # --- بدنه ---
            p_tags = art_soup.select('.body p')
            body_text = "\n\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])

            # --- دسته‌بندی (Breadcrumb) ---
            breadcrumb_tags = art_soup.select('.breadcrumb_news a.news_breadcrumb')
            # اتصال دسته‌ها با ویرگول (مثلا: فرهنگی، سینما و تئاتر)
            categories_text = "، ".join([c.get_text(strip=True) for c in breadcrumb_tags if c.get_text(strip=True)])

            # --- استخراج آیدی از لینک ---
            # لینک نمونه: https://eslahatnews.com/fa/news/117165/...
            match_id = re.search(r'/news/(\d+)', url)
            if match_id:
                news_id = f"eslahat_{match_id.group(1)}"
            else:
                # بک‌آپ در صورتی که ساختار لینک فرق داشت
                news_id = f"eslahat_{random.randint(100000, 999999)}"

            # --- آماده‌سازی و ذخیره ---
            article_data = {
                'id': news_id,
                'source_name': 'eslahatnews',
                'url': url,
                'title': title_text,
                'lead': lead_text,
                'persian_date': persian_date,
                'gregorian_date': gregorian_date,
                'categories': categories_text,
                'body': body_text,
                'tone': None
            }

            db.insert_article(article_data)
            
            # وقفه رندوم برای جلوگیری از بلاک شدن توسط سرور
            time.sleep(random.uniform(1.5, 3))

        except requests.exceptions.RequestException as e:
            print(f"  ⏳ خطای شبکه در دریافت خبر: {e}")
        except Exception as e:
            print(f"  ❌ خطای غیرمنتظره در پردازش: {e}")

        counter += 1

    print("🛑 پایان عملیات.")
    if 'db' in locals():
        db.close()

if __name__ == "__main__":
    crawl_eslahatnews()