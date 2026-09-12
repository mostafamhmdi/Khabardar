import requests
from bs4 import BeautifulSoup
import time
import re
import jdatetime
from datetime import date, timedelta
import urllib.parse
from db_manager import NewsDatabase

# ==========================================
# توابع تاریخ و زمان
# ==========================================

def clean_and_convert_date(raw_date_str):
    """
    متن تاریخ سازندگی را می‌گیرد، تمیز می‌کند و تاریخ میلادی را برمی‌گرداند.
    خروجی: (متن تمیز شده شمسی، متن تاریخ میلادی، آبجکت تاریخ میلادی برای مقایسه)
    """
    if not raw_date_str:
        return "", None, None

    # تبدیل اعداد فارسی به انگلیسی
    persian_to_eng_map = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    eng_digits_str = raw_date_str.translate(persian_to_eng_map).strip()

    # استخراج روز، ماه و سال
    match = re.search(r'(\d{1,2})\s+([آ-یي]+)\s+(\d{4})', eng_digits_str)

    gregorian_date = None
    greg_date_obj = None

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
                greg_date_obj = jdatetime.date(year, month, day).togregorian()
                gregorian_date = greg_date_obj.strftime("%Y-%m-%d")
            except Exception as e:
                print(f"  ⚠️ خطا در محاسبه تاریخ میلادی: {e}")

    return eng_digits_str, gregorian_date, greg_date_obj

# ==========================================
# بدنه اصلی کرالر سازندگی
# ==========================================

def crawl_saazandegi():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    db = NewsDatabase(dbname="news_db", user="postgres", password="bvncxz62")

    # ---------------------------------------------------------
    # منطق تولید آیدی افزایشی (Incremental ID)
    # ---------------------------------------------------------
    current_id_counter = 85000  # عدد رندوم اولیه به دلخواه شما
    
    if db.conn:
        try:
            # جستجو در دیتابیس برای پیدا کردن بزرگترین آیدی سازندگی
            db.cursor.execute("SELECT id FROM articles WHERE id LIKE 'sazandegi_%';")
            rows = db.cursor.fetchall()
            for row in rows:
                try:
                    num = int(row[0].split('_')[1])
                    if num >= current_id_counter:
                        current_id_counter = num + 1
                except ValueError:
                    pass # اگر ساختار آیدی به هر دلیلی عدد نبود رد شو
        except Exception as e:
            db.conn.rollback()
            print(f"⚠️ خطا در خواندن آیدی‌های قبلی: {e}")

    # محاسبه تاریخ دیروز برای فیلتر کردن
    yesterday = date.today() - timedelta(days=1)
    print(f"🔍 در حال جمع‌آوری اخبار دیروز (تاریخ: {yesterday})...")
    print(f"🔢 شماره‌گذاری اخبار سازندگی از {current_id_counter} شروع می‌شود.")
    print("-" * 50)

    categories = {
        'policy': 'سیاسی',
        'economy': 'اقتصادی',
        'culture': 'فرهنگی',
        'society': 'جامعه'
    }

    target_links_data = []

    # ۱. استخراج لینک‌های مربوط به اخبار دیروز از صفحات کتگوری
    for cat_slug, cat_name in categories.items():
        print(f"📂 در حال بررسی دسته: {cat_name}")
        page = 1
        stop_pagination = False

        # حلقه روی صفحات تا زمانی که به اخبار قدیمی‌تر از دیروز نرسیده‌ایم
        while not stop_pagination and page <= 20: 
            if page == 1:
                url = f"https://saazandegi.ir/category/{cat_slug}/"
            else:
                url = f"https://saazandegi.ir/category/{cat_slug}/page/{page}/"

            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, 'html.parser')

                link_elements = soup.select('.entry-title a')
                date_elements = soup.select('#content .date')

                if not link_elements or not date_elements:
                    break

                for link_el, date_el in zip(link_elements, date_elements):
                    href = link_el.get('href')
                    title = link_el.get_text(strip=True)
                    raw_date = date_el.get_text(strip=True)

                    p_date, g_date, g_date_obj = clean_and_convert_date(raw_date)

                    if g_date_obj:
                        if g_date_obj == yesterday:
                            target_links_data.append({
                                'url': href,
                                'title': title,
                                'category': cat_name,
                                'persian_date': p_date,
                                'gregorian_date': g_date
                            })
                        elif g_date_obj < yesterday:
                            stop_pagination = True
                            break

                print(f"  ✔️ صفحه {page} پردازش شد.")
                page += 1
                time.sleep(0.5)

            except Exception as e:
                print(f"  ❌ خطا در صفحه {page} دسته‌بندی {cat_name}: {e}")
                break

    print("-" * 50)
    print(f"✅ مجموعاً {len(target_links_data)} خبر برای دیروز پیدا شد. ورود به لینک‌ها...\n")

    # ۲. ورود به تک‌تک اخبار و استخراج لید و بدنه
    counter = 1
    for info in target_links_data:
        url = info['url']
        print(f"[{counter}/{len(target_links_data)}] پردازش: {info['title'][:30]}...")

        try:
            art_resp = requests.get(url, headers=headers, timeout=10)
            if art_resp.status_code == 200:
                art_soup = BeautifulSoup(art_resp.text, 'html.parser')

                # استخراج لید خبر
                lead_tag = art_soup.select_one('.elementor-widget-theme-post-content h3')
                lead_text = lead_tag.get_text(strip=True) if lead_tag else ""

                # استخراج بدنه خبر
                body_tags = art_soup.select('.elementor-widget-theme-post-content h3 ~ p')
                if not body_tags:
                    body_tags = art_soup.select('.elementor-widget-theme-post-content p')

                body_text = "\n\n".join([p.get_text(strip=True) for p in body_tags if p.get_text(strip=True)])

                # تنظیم آیدی به شکل درخواست شده (ترکیب پیشوند و کانتر عددی)
                news_id = f"sazandegi_{current_id_counter}"
                
                # ذخیره در دیتابیس
                article_data = {
                    'id': news_id,
                    'source_name': 'saazandegi',
                    'url': url,
                    'title': info['title'],
                    'lead': lead_text,
                    'persian_date': info['persian_date'],
                    'gregorian_date': info['gregorian_date'],
                    'categories': info['category'],
                    'body': body_text,
                    'tone': None
                }

                db.insert_article(article_data)
                
                # اضافه کردن یکی به کانتر برای خبر بعدی
                current_id_counter += 1

        except Exception as e:
            print(f"  ❌ خطا در پردازش خبر: {e}")

        counter += 1
        time.sleep(1)

    if 'db' in locals():
        db.close()

if __name__ == "__main__":
    crawl_saazandegi()