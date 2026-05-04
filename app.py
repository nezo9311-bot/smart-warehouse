import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import requests

# --- إعدادات النظام ---
ADMIN_PASSWORD = "123"
TELEGRAM_TOKEN = "8691308758:AAEwlVzXLo8EykZtYju6ZBkyzfJdEGhnhsE"
CHAT_ID = "5716145319"

# --- وظائف قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                 (name TEXT, brand TEXT, quantity INTEGER, PRIMARY KEY(name, brand))''')
    c.execute('''CREATE TABLE IF NOT EXISTS movements 
                 (type TEXT, name TEXT, brand TEXT, quantity INTEGER, 
                  destination TEXT, date TIMESTAMP)''')
    conn.commit()
    conn.close()

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={msg}"
    try: requests.get(url)
    except: pass

# --- واجهة أمين المخزن ---
def storekeeper_view():
    st.header("📲 قسم العمليات الميدانية")
    
    action = st.radio("نوع العملية", ["إدخال بضاعة 📥", "إخراج بضاعة 📤"])
    
    with st.form("movement_form"):
        # إكمال تلقائي ذكي للنصف
        conn = sqlite3.connect('warehouse.db')
        existing_data = pd.read_sql("SELECT DISTINCT name, brand FROM inventory", conn)
        conn.close()
        
        name = st.selectbox("اسم الصنف", options=list(existing_data['name'].unique()) + ["+ إضافة صنف جديد"], index=None)
        if name == "+ إضافة صنف جديد":
            name = st.text_input("اكتب اسم الصنف الجديد")
            
        brand = st.text_input("الماركة / النوع")
        qty = st.number_input("الكمية", min_value=1)
        dest = ""
        if "إخراج" in action:
            dest = st.text_input("الجهة المستلمة")
            
        submit = st.form_submit_with_button("تنفيذ وحفظ")
        
        if submit:
            process_data(action, name, brand, qty, dest)

def process_data(action, name, brand, qty, dest):
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    
    if "إدخال" in action:
        c.execute("INSERT OR REPLACE INTO inventory (name, brand, quantity) VALUES (?, ?, COALESCE((SELECT quantity FROM inventory WHERE name=? AND brand=?), 0) + ?)", 
                  (name, brand, name, brand, qty))
        c.execute("INSERT INTO movements VALUES ('IN', ?, ?, ?, '', ?)", (name, brand, qty, datetime.now()))
        send_telegram(f"📥 تم إدخال {qty} {name} ({brand})")
        st.success("تم الحفظ وتحديث المخزون")
    else:
        # فحص المخزون قبل الإخراج
        res = c.execute("SELECT quantity FROM inventory WHERE name=? AND brand=?", (name, brand)).fetchone()
        if res and res[0] >= qty:
            c.execute("UPDATE inventory SET quantity = quantity - ? WHERE name=? AND brand=?", (qty, name, brand))
            c.execute("INSERT INTO movements VALUES ('OUT', ?, ?, ?, ?, ?)", (name, brand, qty, dest, datetime.now()))
            send_telegram(f"📤 تم إخراج {qty} {name} ({brand}) إلى {dest}")
            st.warning("تم الصرف بنجاح")
        else:
            st.error("الكمية غير كافية في المخزن!")
            
    conn.commit()
    conn.close()

# --- واجهة المدير والتحليل ---
def admin_view():
    st.sidebar.title("🔐 منطقة الإدارة")
    pw = st.sidebar.text_input("كلمة السر", type="password")
    
    if pw == ADMIN_PASSWORD:
        st.header("📊 لوحة تحليل السوق والاتجاهات")
        conn = sqlite3.connect('warehouse.db')
        df = pd.read_sql("SELECT * FROM movements", conn)
        
        if not df.empty:
            # تحليل الاتجاهات (مقارنة الأسبوع الحالي بالماضي)
            st.subheader("📈 تحليل حركة الماركات")
            brand_perf = df[df['type']=='OUT'].groupby(['name', 'brand'])['quantity'].sum().reset_index()
            st.dataframe(brand_perf)
            
            # مؤشر النشاط
            total_in = df[df['type']=='IN']['quantity'].sum()
            total_out = df[df['type']=='OUT']['quantity'].sum()
            idx = (total_out / (total_in + 1)) * 100
            st.metric("مؤشر نشاط السوق العام", f"{idx:.1f}%")
        conn.close()

# --- تشغيل التطبيق ---
init_db()
page = st.sidebar.selectbox("انتقل إلى", ["واجهة المخزن", "لوحة الإدارة"])
if page == "واجهة المخزن":
    storekeeper_view()
else:
    admin_view()
