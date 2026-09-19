import requests
from bs4 import BeautifulSoup
import time
import random
import re
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
            # استخراج شناسه از لینک (مثال: /بخش-سیاست-6/1128948-آمریکا...)
            match = re.search(r'/(\d+)-', url)
            if match:
                news_id = f"shargh_{match.group(1)}"
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
# بدنه اصلی کرالر شرق
# ==========================================

def crawl_shargh():
    db = NewsDatabase(dbname="news_db", user="postgres", password="bvncxz62")

    target_pages = [
        "https://www.sharghdaily.com/%D8%A8%D8%AE%D8%B4-%D8%B3%DB%8C%D8%A7%D8%B3%D8%AA-6",
        "https://www.sharghdaily.com/%D8%A8%D8%AE%D8%B4-%D8%AC%D9%87%D8%A7%D9%86-219",
        "https://www.sharghdaily.com/%D8%A8%D8%AE%D8%B4-%D8%AC%D8%A7%D9%85%D8%B9%D9%87-220",
        "https://www.sharghdaily.com/%D8%A8%D8%AE%D8%B4-%D8%A7%D9%82%D8%AA%D8%B5%D8%A7%D8%AF%DB%8C-12",
        "https://www.sharghdaily.com/%D8%A8%D8%AE%D8%B4-%D9%81%D8%B1%D9%87%D9%86%DA%AF-%D9%87%D9%86%D8%B1-70"
    ]

    all_scraped_links = set()
    base_domain = "https://www.sharghdaily.com"

    print("🔍 جمع‌آوری لینک‌های اولیه از صفحات روزنامه شرق...")
    print("-" * 50)

    # ۱. استخراج لینک‌ها
    for page_url in target_pages:
        resp = get_page_with_retry(page_url)
        if resp and resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # با توجه به نمونه‌های شما، ویژگی itemprop="url" در تمام لینک‌های خبر مشترک است
            elements = soup.select('a[itemprop="url"]')
            for el in elements:
                href = el.get('href')
                if href:
                    full_url = base_domain + href if href.startswith('/') else href
                    all_scraped_links.add(full_url)
            
            page_name = urllib.parse.unquote(page_url.split('/')[-1])
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
                art_soup = BeautifulSoup(art_resp.text, 'html.parser')

                # --- تیتر ---
                title_tag = art_soup.select_one('#news-page-article .title')
                title_text = title_tag.get_text(strip=True) if title_tag else "بدون تیتر"

                # --- لید ---
                lead_tag = art_soup.select_one('.lead')
                lead_text = lead_tag.get_text(strip=True) if lead_tag else ""

                # --- دسته‌بندی ---
                cat_tag = art_soup.select_one('.bread_list a')
                category = cat_tag.get_text(strip=True) if cat_tag else None

                # --- تاریخ ---
                # روزنامه شرق تاریخ میلادی را تمیز داخل ویژگی datetime قرار داده است
                date_tag = art_soup.select_one('.news_time')
                persian_date, gregorian_date = "", None
                
                if date_tag:
                    raw_persian = date_tag.get_text(separator=' ', strip=True)
                    persian_date = re.sub(r'\s+', ' ', raw_persian)  # مرتب‌سازی فاصله‌های اضافی
                    
                    raw_gregorian = date_tag.get('datetime')
                    if raw_gregorian:
                        # استخراج بخش YYYY-MM-DD از رشته "2026-09-18T23:45:00Z"
                        gregorian_date = raw_gregorian.split('T')[0]

                # --- بدنه ---
                p_tags = art_soup.select('#echo_detail p')
                if p_tags:
                    # بررسی پاراگراف آخر برای کلمات کلیدی تلگرام یا شرق
                    last_p_text = p_tags[-1].get_text()
                    if "تلگرام" in last_p_text or "شرق" in last_p_text:
                        p_tags.pop() # حذف پاراگراف آخر
                        
                body_text = "\n\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])

                # --- آیدی ---
                match_id = re.search(r'/(\d+)-', url)
                news_id = f"shargh_{match_id.group(1)}" if match_id else f"shargh_{url.split('/')[-1][:20]}"

                # --- آماده‌سازی و ذخیره ---
                article_data = {
                    'id': news_id,
                    'source_name': 'shargh',
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
    crawl_shargh()