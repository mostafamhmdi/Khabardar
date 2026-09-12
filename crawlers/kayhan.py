import requests
from bs4 import BeautifulSoup
import time
import re
import jdatetime
from datetime import date
from db_manager import NewsDatabase

# ==========================================
# توابع کمکی
# ==========================================

def get_today_issue_number():
    """
    محاسبه خودکار شماره روزنامه کیهان بر اساس تاریخ روز.
    مبنا: شماره 3646 برای تاریخ 7 سپتامبر 2026 (16 شهریور 1405)
    """
    base_date = date(2026, 9, 7)
    base_issue = 3646
    
    # محاسبه اختلاف روزها
    delta_days = (date.today() - base_date).days
    
    # روزنامه جمعه‌ها چاپ نمی‌شود، اما چون فرمودید هر روز یکی اضافه می‌شود
    # فعلاً به صورت خطی جمع می‌زنیم.
    return base_issue + delta_days

def get_category_by_page(page_num):
    """تخصیص دسته‌بندی بر اساس شماره صفحه کیهان"""
    if page_num in [1, 2, 3, 7]:
        return "سیاسی"
    elif page_num == 4:
        return "اقتصادی"
    elif page_num == 5:
        return "ورزشی"
    elif page_num == 6:
        return "جامعه"
    elif page_num == 8:
        return "خارجی"
    return None

def parse_and_convert_date(raw_date_str):
    """تمیز کردن تاریخ شمسی و تولید تاریخ میلادی استاندارد"""
    if not raw_date_str:
        return "", None

    # حذف بخش متنی اضافه بدون آسیب زدن به ساعت
    clean_persian = re.sub(r'تاریخ انتشار\s*:\s*', '', raw_date_str).strip()
    
    # تبدیل اعداد فارسی به انگلیسی برای پردازش
    persian_to_eng_map = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    eng_digits_str = clean_persian.translate(persian_to_eng_map)
    
    match = re.search(r'(\d{1,2})\s+([آ-یي]+)\s+(\d{4})', eng_digits_str)
    gregorian_date = None
    
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3))
        
        months = {
            'فروردین': 1, 'اردیبهشت': 2, 'خرداد': 3, 'تیر': 4, 'مرداد': 5,
            'شهریور': 6, 'شهريور': 6, 'مهر': 7, 'آبان': 8, 'آذر': 9, 'اذر': 9,
            'دی': 10, 'بهمن': 11, 'اسفند': 12
        }
        
        month = months.get(month_name)
        if month:
            try:
                greg_date = jdatetime.date(year, month, day).togregorian()
                gregorian_date = greg_date.strftime("%Y-%m-%d")
            except Exception as e:
                print(f"  ⚠️ خطا در محاسبه تاریخ میلادی: {e}")
                
    return clean_persian, gregorian_date

# ==========================================
# بدنه اصلی کرالر
# ==========================================

def crawl_kayhan():
    # محاسبه شماره کیهانِ امروز
    # issue_number = get_today_issue_number()
    issue_number = 3648
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive"
    }

    db = NewsDatabase(dbname="news_db", user="postgres", password="bvncxz62")
    
    # این دیکشنری حالا اطلاعات دسته‌بندی را هم نگه می‌دارد
    unique_links_data = {}

    print(f"📰 در حال دریافت شماره {issue_number} روزنامه کیهان (تاریخ امروز)...")
    print("-" * 50)
    
    # ۱. استخراج لینک‌ها از صفحات 1 تا 10
    for page_num in range(1, 11):
        url = f"https://kayhan.ir/fa/issue/{issue_number}/{page_num}"
        category = get_category_by_page(page_num)
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                break # صفحه وجود ندارد
                
            soup = BeautifulSoup(resp.text, 'html.parser')
            target_links = soup.select('a.news_tag')
            
            if not target_links:
                continue

            for link in target_links:
                href = link.get('href')
                title = link.get('title') or link.get_text(strip=True)
                
                if href and title:
                    full_url = f"https://kayhan.ir{href}" if href.startswith('/') else href
                    # لینک را کلید قرار می‌دهیم تا تکراری‌ها حذف شوند
                    # ولی تیتر و دسته‌بندی را به عنوان مقدار ذخیره می‌کنیم
                    unique_links_data[full_url] = {
                        'title': title,
                        'category': category
                    }
                    
            print(f"  ✔️ صفحه {page_num} ({category or 'بدون دسته'}) بررسی شد.")
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            print(f"  ❌ خطا در صفحه {page_num}: {e}")
            break

    print("-" * 50)
    print(f"✅ مجموعاً {len(unique_links_data)} خبر یکتا استخراج شد. شروع دریافت جزئیات داخلی...\n")
    
    # ۲. ورود به تک‌تک اخبار و استخراج متن
    counter = 1
    for url, info in unique_links_data.items():
        print(f"[{counter}/{len(unique_links_data)}] پردازش: {info['title'][:30]}...")
        
        try:
            art_resp = requests.get(url, headers=headers, timeout=10)
            if art_resp.status_code == 200:
                art_soup = BeautifulSoup(art_resp.text, 'html.parser')
                
                # تاریخ
                persian_date, gregorian_date = "", None
                date_div = art_soup.select_one('.col-sm-16')
                if date_div:
                    raw_date = date_div.get_text(strip=True)
                    persian_date, gregorian_date = parse_and_convert_date(raw_date)

                # متن اصلی
                body_text = ""
                body_container = art_soup.select_one('.body p') or art_soup.select_one('p:nth-child(1)')
                if body_container:
                    body_text = body_container.get_text(separator='\n\n', strip=True)

                # ساخت آیدی یکتا
                try:
                    news_code = url.split('/')[5]
                    news_id = f"kayhan_{news_code}"
                except IndexError:
                    news_id = f"kayhan_{url.split('/')[-1]}"

                # آماده‌سازی دیتای نهایی
                article_data = {
                    'id': news_id,
                    'source_name': 'kayhan',
                    'url': url,
                    'title': info['title'],
                    'lead': None,
                    'persian_date': persian_date,
                    'gregorian_date': gregorian_date,
                    'categories': info['category'],
                    'body': body_text,
                    'tone': None
                }
                
                db.insert_article(article_data)
                
        except Exception as e:
            print(f"  ❌ خطا در پردازش خبر: {e}")
        
        counter += 1
        time.sleep(1)

    if 'db' in locals():
        db.close()

if __name__ == "__main__":
    crawl_kayhan()