import requests
from bs4 import BeautifulSoup
import time

# وارد کردن کلاسی که در فایل db_manager.py ساختیم
from db_manager import NewsDatabase

def crawl_and_extract_to_db():
    base_url = "https://ensafnews.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive"
    }
    
    print("🔍 در حال دریافت لینک‌های صفحه اصلی...")
    
    # ۱. اتصال به دیتابیس (رمز عبور خود را جایگزین کنید)
    db = NewsDatabase(dbname="news_db", user="postgres", password="bvncxz62")
    
    try:
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            print("❌ خطا در دریافت صفحه اصلی!")
            return
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # دیکشنری برای نگهداری لینک‌های یکتا و حذف تکراری‌ها
        unique_links = {}
        selectors = [
            '.category-13117 a',
            '.wp-container-core-columns-is-layout-212c5d24 a',
            '.wp-container-core-post-template-is-layout-d6d2a334 a'
        ]

        # مرحله اول: جمع‌آوری لینک‌های بدون عکس
        for selector in selectors:
            for link in soup.select(selector):
                if link.find('img'):  # حذف لینک‌های دارای تصویر
                    continue
                href = link.get('href')
                title_text = link.get_text(strip=True)
                if href and title_text:
                    unique_links[href] = title_text

        print(f"✅ تعداد {len(unique_links)} لینک یکتا پیدا شد. شروع استخراج و ذخیره در دیتابیس...\n")
        print("-" * 50)

        # مرحله دوم: ورود به هر لینک و استخراج دیتای صفحه خبر
        counter = 1
        for href, title in unique_links.items():
            print(f"[{counter}/{len(unique_links)}] در حال پردازش: {title[:30]}...")
            
            try:
                article_resp = requests.get(href, headers=headers, timeout=10)
                if article_resp.status_code == 200:
                    article_soup = BeautifulSoup(article_resp.text, 'html.parser')
                    
                    # --- متغیرهای پیش‌فرض ---
                    lead = ""
                    body_text = ""
                    persian_date = ""
                    gregorian_date = ""
                    categories = []

                    # --- استخراج محتوای متن (Lead و Body) ---
                    content_div = article_soup.select_one('.entry-content')
                    if content_div:
                        p_tags = content_div.find_all('p')
                        p_texts = [p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)]
                        
                        if p_texts:
                            lead = p_texts[0]
                            if len(p_texts) > 1 and "انتهای پیام" in p_texts[-1]:
                                p_texts.pop() 
                            body_text = "\n\n".join(p_texts[1:])

                    # --- استخراج متادیتا (تاریخ و دسته‌بندی‌ها) ---
                    meta_container = article_soup.select_one('.ct-container .entry-meta')
                    if meta_container:
                        time_tag = meta_container.find('time')
                        if time_tag:
                            persian_date = time_tag.get_text(strip=True)
                            gregorian_date = time_tag.get('datetime', '')
                            
                        category_tags = meta_container.select('.meta-categories a')
                        categories = [a.get_text(strip=True) for a in category_tags]
                    
                    categories_str = "، ".join(categories)

                    # --- ۲. استخراج آیدی یکتا از آدرس لینک ---
                    # مثال لینک: https://ensafnews.com/664590/عنوان-خبر
                    # با اسپلیت کردن با کاراکتر '/' بخش ایندکس ۳ همان عدد است
                    try:
                        news_code = href.split('/')[3]
                        news_id = f"ensaf_{news_code}"  # اضافه کردن پیشوند به عدد
                    except IndexError:
                        # در صورتی که ساختار لینک غیرمعمول بود
                        news_id = f"ensaf_{href}"

                    # --- ۳. ساخت دیکشنری داده‌ها ---
                    article_data = {
                        'id': news_id,
                        'source_name': 'ensafnews',
                        'url': href,
                        'title': title,
                        'lead': lead,
                        'persian_date': persian_date,
                        'gregorian_date': gregorian_date,
                        'categories': categories_str,
                        'body': body_text,
                        'tone': None  # فعلاً نال در نظر گرفته می‌شود
                    }

                    # --- ۴. ذخیره در پایگاه داده ---
                    db.insert_article(article_data)
                    
            except Exception as e:
                print(f"  ❌ خطا در پردازش لینک: {e}")
            
            counter += 1
            time.sleep(1) # تاخیر برای جلوگیری از مسدود شدن توسط سرور

        print("-" * 50)
        print("🎉 عملیات با موفقیت تمام شد! اطلاعات در پایگاه داده ذخیره شد.")

    except Exception as e:
        print(f"⚠️ خطای کلی در برنامه:\n{e}")
    
    finally:
        # ۵. قطع ارتباط با دیتابیس در انتهای کار
        # بلوک finally تحت هر شرایطی (حتی با وجود خطا در کدهای بالا) اجرا می‌شود
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    crawl_and_extract_to_db()