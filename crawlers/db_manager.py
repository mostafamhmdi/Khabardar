import psycopg2
from psycopg2 import sql

class NewsDatabase:
    def __init__(self, dbname, user, password, host="localhost", port="5432"):
        """اتصال به دیتابیس و ساخت جدول در صورت عدم وجود"""
        try:
            self.conn = psycopg2.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port
            )
            self.cursor = self.conn.cursor()
            self.create_table()
            print("✅ اتصال به دیتابیس با موفقیت انجام شد.")
        except Exception as e:
            print(f"❌ خطا در اتصال به دیتابیس: {e}")

    def create_table(self):
        """ساخت جدول با ساختار درخواستی (آیدی دستی)"""
        # آیدی را از نوع TEXT در نظر گرفتیم تا هر فرمتی (ترکیب عدد و حروف) را بپذیرد
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            title TEXT,
            lead TEXT,
            persian_date TEXT,
            gregorian_date TEXT,
            categories TEXT,
            body TEXT,
            tone TEXT
        );
        '''
        self.cursor.execute(create_table_query)
        self.conn.commit()

    def insert_article(self, data):
        """
        دریافت یک دیکشنری از اطلاعات و ذخیره آن در دیتابیس.
        در صورت تکراری بودن آیدی یا لینک، از ذخیره آن صرف‌نظر می‌کند.
        """
        insert_query = '''
        INSERT INTO articles 
        (id, source_name, url, title, lead, persian_date, gregorian_date, categories, body, tone) 
        VALUES (%(id)s, %(source_name)s, %(url)s, %(title)s, %(lead)s, %(persian_date)s, %(gregorian_date)s, %(categories)s, %(body)s, %(tone)s)
        ON CONFLICT (id) DO NOTHING;
        '''
        
        try:
            self.cursor.execute(insert_query, data)
            self.conn.commit()
            
            # بررسی اینکه آیا رکورد جدیدی اضافه شد یا تکراری بود
            if self.cursor.rowcount > 0:
                print(f"  📥 خبر ذخیره شد: {data['title'][:30]}...")
            else:
                print(f"  ⚠️ خبر تکراری بود (رد شد): {data['id']}")
                
        except Exception as e:
            self.conn.rollback()
            print(f"❌ خطا در ذخیره خبر {data.get('id')}: {e}")

    def close(self):
        """بستن ایمن ارتباط با دیتابیس"""
        self.cursor.close()
        self.conn.close()
        print("🔌 ارتباط با دیتابیس قطع شد.")