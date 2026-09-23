import time
import random
import re
import jdatetime
import urllib.parse
from bs4 import BeautifulSoup
from db_manager import NewsDatabase

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

# ==========================================
# تنظیمات مرورگر سلنیوم
# ==========================================
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    chrome_options.add_argument(f'user-agent={user_agent}')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    driver.set_page_load_timeout(30) 
    return driver

# ==========================================
# توابع کمکی
# ==========================================
def parse_arman_date(raw_date_str):
    if not raw_date_str:
        return "", None

    # حذف عبارت اضافی پیش از پردازش
    clean_str = raw_date_str.replace('تاریخ و زمان ارسال:', '')
    
    # پاکسازی کاراکترهای اضافی (تبدیل فاصله‌های زیاد به یک فاصله)
    clean_str = re.sub(r'\s+', ' ', clean_str).strip()
    
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

def filter_new_links(db, links_set):
    if not links_set:
        return set()
        
    print(f"  🔍 بررسی {len(links_set)} لینک با دیتابیس جهت یافتن اخبار جدید...")
    new_links = set()
    try:
        # چون آیدی‌ها رندوم شده‌اند، بررسی تکراری بودن باید روی خود url انجام شود
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
# بدنه اصلی کرالر آرمان
# ==========================================
def crawl_armandaily():
    db = NewsDatabase(dbname="news_db", user="postgres", password="bvncxz62")
    
    categories = {
        'note-of-the-day': 'یادداشت روز',
        'economy': 'اقتصادی',
        'political': 'سیاسی',
        'diplomacy': 'دیپلماسی',
        'collective': 'اجتماعی',
        'cultural': 'فرهنگی'
    }

    all_scraped_links = {}

    print("🚀 راه‌اندازی مرورگر سلنیوم...")
    driver = setup_driver()

    print("🔍 جمع‌آوری لینک‌های اولیه از سایت روزنامه آرمان...")
    print("-" * 50)

    # ۱. جمع‌آوری لینک‌ها
    for cat_slug, cat_name in categories.items():
        for page in [1, 2]:
            if page == 1:
                url = f"https://armandaily.ir/category/last-news/{cat_slug}/"
            else:
                url = f"https://armandaily.ir/category/last-news/{cat_slug}/page/{page}/"

            try:
                driver.get(url)
                time.sleep(random.uniform(3, 5))
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                elements = soup.select('h2 a')
                
                for el in elements:
                    href = el.get('href')
                    if href:
                        all_scraped_links[href] = cat_name
                        
                print(f"  ✔️ صفحه {page} از دسته [{cat_name}] بررسی شد.")
            except TimeoutException:
                print(f"  ⏳ تایم‌اوت در دریافت صفحه: {url}")
            except WebDriverException as e:
                print(f"  ❌ خطای مرورگر: {e}")

    print("-" * 50)
    
    # ۲. فیلتر کردن لینک‌های تکراری (بر اساس URL)
    unique_new_links = filter_new_links(db, set(all_scraped_links.keys()))
    
    if not unique_new_links:
        print("🎉 هیچ خبر جدیدی برای دانلود وجود ندارد.")
        driver.quit()
        if 'db' in locals():
            db.close()
        return

    print("-" * 50)
    
    # ایجاد یک عدد رندوم پایه برای تخصیص آیدی (مثلاً 100000 تا 999999)
    current_random_id = random.randint(100000, 999999)

    # ۳. ورود به اخبار جدید
    counter = 1
    for url in unique_new_links:
        print(f"[{counter}/{len(unique_new_links)}] پردازش: {urllib.parse.unquote(url.split('/')[-1][:30])}...")

        try:
            driver.get(url)
            time.sleep(random.uniform(3, 5))
            
            art_soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- تیتر ---
            title_tag = art_soup.select_one('h1')
            title_text = title_tag.get_text(strip=True) if title_tag else "بدون تیتر"

            # --- تاریخ ---
            date_tag = art_soup.select_one('#sidebar_right li:nth-child(2)')
            raw_date = date_tag.get_text(strip=True) if date_tag else ""
            persian_date, gregorian_date = parse_arman_date(raw_date)

            # --- بدنه ---
            p_tags = art_soup.select('.news_article_body p+ p')
            if not p_tags:
                p_tags = art_soup.select('.news_article_body p')
                
            body_text = "\n\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])

            # --- آیدی رندوم افزایشی ---
            news_id = f"arman_{current_random_id}"
            current_random_id += 1

            # --- آماده‌سازی و ذخیره ---
            article_data = {
                'id': news_id,
                'source_name': 'armandaily',
                'url': url,
                'title': title_text,
                'lead': "",
                'persian_date': persian_date,
                'gregorian_date': gregorian_date,
                'categories': all_scraped_links[url],
                'body': body_text,
                'tone': None
            }

            db.insert_article(article_data)

        except TimeoutException:
            print("  ⏳ اسکیپ شد (تایم‌اوت مرورگر).")
        except WebDriverException as e:
            print(f"  ❌ خطای مرورگر در پردازش محتوا: {e}")
        except Exception as e:
            print(f"  ❌ خطای غیرمنتظره در پردازش: {e}")

        counter += 1

    print("🛑 در حال بستن مرورگر...")
    driver.quit()
    
    if 'db' in locals():
        db.close()

if __name__ == "__main__":
    crawl_armandaily()