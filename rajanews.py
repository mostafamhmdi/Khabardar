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

# لیستی از هدرهای مختلف برای جلوگیری از بلاک شدن
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
]

def get_page_with_retry(url, max_retries=3):
    """
    ارسال درخواست با قابلیت تلاش مجدد، تغییر هدر و مدیریت تایم‌اوت
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
            # زمان کانکت 10 ثانیه، زمان خواندن دیتا 30 ثانیه
            response = requests.get(url, headers=headers, timeout=(10, 30))
            
            if response.status_code in [500, 502, 503, 504]:
                print(f"  ⚠️ خطای سرور {response.status_code}. تلاش {attempt} از {max_retries}...")
                time.sleep(random.uniform(3, 6))
                continue
                
            return response
            
        except requests.exceptions.Timeout:
            print(f"  ⏳ تایم‌اوت رخ داد! تلاش {attempt} از {max_retries}...")
            time.sleep(random.uniform(3, 6))
        except requests.exceptions.RequestException as e:
            print(f"  ❌ خطای ارتباطی موقت. تلاش {attempt} از {max_retries}...")
            time.sleep(random.uniform(3, 6))
            
    return None

def parse_rajanews_date(raw_date_str):
    if not raw_date_str:
        return "", None

    persian_to_eng_map = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    clean_str = raw_date_str.translate(persian_to_eng_map).strip()

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
# بدنه اصلی کرالر رجانیوز
# ==========================================

def crawl_rajanews():
    db = NewsDatabase(dbname="news_db", user="postgres", password="bvncxz62")

    target_pages = [
        "https://www.rajanews.com/",
        "https://www.rajanews.com/%D9%85%D9%88%D8%B6%D9%88%D8%B9/%D8%B3%DB%8C%D8%A7%D8%B3%D8%AA",
        "https://www.rajanews.com/%D9%85%D9%88%D8%B6%D9%88%D8%B9/%D8%A8%DB%8C%D9%86-%D8%A7%D9%84%D9%85%D9%84%D9%84",
        "https://www.rajanews.com/%D9%85%D9%88%D8%B6%D9%88%D8%B9/%D8%A7%D9%82%D8%AA%D8%B5%D8%A7%D8%AF",
        "https://www.rajanews.com/%D9%85%D9%88%D8%B6%D9%88%D8%B9/%D9%81%D8%B1%D9%87%D9%86%DA%AF",
        "https://www.rajanews.com/%D9%85%D9%88%D8%B6%D9%88%D8%B9/%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9%DB%8C"
    ]

    unique_links = set()

    print("🔍 در حال جمع‌آوری لینک‌ها از صفحات اصلی رجانیوز...")
    print("-" * 50)

    # ۱. استخراج لینک‌ها
    for page_url in target_pages:
        resp = get_page_with_retry(page_url)
        if resp and resp.status_code == 200:
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')

            selectors = ['.homepage .item a', '#block-views-home-titr2 a', '#yaddasht .item-inner a']
            
            for selector in selectors:
                elements = soup.select(selector)
                for el in elements:
                    href = el.get('href')
                    if href and '/news/' in href:
                        full_url = f"https://www.rajanews.com{href}" if href.startswith('/') else href
                        unique_links.add(full_url)
            
            print(f"  ✔️ صفحه پردازش شد: {urllib.parse.unquote(page_url.split('/')[-1]) or 'صفحه اصلی'}")
        else:
            print(f"  ❌ دریافت صفحه {page_url} با وجود تلاش مجدد ناموفق بود.")
            
        # استراحت تصادفی بین ۱ تا ۳ ثانیه
        time.sleep(random.uniform(1, 3))

    print("-" * 50)
    print(f"✅ مجموعاً {len(unique_links)} لینک یکتا استخراج شد. شروع دریافت جزئیات اخبار...\n")

    # ۲. ورود به اخبار
    counter = 1
    for url in unique_links:
        print(f"[{counter}/{len(unique_links)}] پردازش: {urllib.parse.unquote(url.split('/')[-1][:30])}...")

        art_resp = get_page_with_retry(url)
        if art_resp and art_resp.status_code == 200:
            try:
                art_resp.encoding = 'utf-8'
                art_soup = BeautifulSoup(art_resp.text, 'html.parser')

                title_tag = art_soup.select_one('.title')
                title_text = title_tag.get_text(strip=True) if title_tag else "بدون تیتر"

                lead_tag = art_soup.select_one('.lead')
                lead_text = lead_tag.get_text(strip=True) if lead_tag else ""

                cat_tag = art_soup.select_one('.category-breadcrumb a')
                category = cat_tag.get_text(strip=True) if cat_tag else None

                date_tag = art_soup.select_one('.date-display-single')
                raw_date = date_tag.get_text(strip=True) if date_tag else ""
                persian_date, gregorian_date = parse_rajanews_date(raw_date)

                span_tags = art_soup.select('.body span')
                span_texts = [span.get_text(strip=True) for span in span_tags if span.get_text(strip=True)]
                
                if span_texts and "انتهای پیام" in span_texts[-1]:
                    span_texts.pop()
                
                body_text = "\n\n".join(span_texts)

                match_id = re.search(r'/news/(\d+)', url)
                if match_id:
                    news_id = f"rajanews_{match_id.group(1)}"
                else:
                    news_id = f"rajanews_{url.split('/')[-1][:20]}"

                article_data = {
                    'id': news_id,
                    'source_name': 'rajanews',
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
        # استراحت تصادفی بین ۲ تا ۴ ثانیه برای جلوگیری از شناسایی به عنوان ربات
        time.sleep(random.uniform(2, 4))

    if 'db' in locals():
        db.close()

if __name__ == "__main__":
    crawl_rajanews()