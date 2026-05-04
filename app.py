import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import requests

# --- إعدادات النظام الحقيقية ---
# تم وضع التوكن الخاص بك هنا
TELEGRAM_TOKEN = "8691308758:AAEwlVzXLo8EykZtYju6ZBkyzfJdEGhnhsE"
# ملاحظة: تأكد من الحصول على CHAT_ID الخاص بك ووضعه هنا
CHAT_ID = "5716145319" 
ADMIN_PASSWORD = "123"

# --- وظائف النظام الأساسية ---
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

# --- واجهة المستخدم ---
def main():
    st.set_page_config(page_title="مستودع nezo9311", layout="centered")
    init_db()

    page = st.sidebar.selectbox("الانتقال إلى", ["واجهة المخزن", "لوحة الإدارة"])

    if page == "واجهة المخزن":
        st.header("📲 قسم العمليات الميدانية")
        action = st.radio("نوع العملية", ["إدخال بضاعة 📥", "إخراج بضاعة 📤"])
        
        with st.form("movement_form"):
            conn = sqlite3.connect('warehouse.db')
            existing_data = pd.read_sql("SELECT DISTINCT name FROM inventory", conn)
            conn.close()
            
            name = st.selectbox("اسم الصنف", options=["إضافة صنف جديد +"] + list(existing_data['name'].unique()))
            if name == "إضافة صنف جديد +":
                name = st.text_input("اكتب اسم الصنف الجديد")
            
            brand = st.text_input("الماركة / النوع")
            qty = st.number_input("الكمية", min_value=1, step=1)
            dest = ""
            if "إخراج" in action:
                dest = st.text_input("الجهة المستلمة")
            
            # تم إصلاح الزر هنا ليعمل بشكل صحيح
            submit = st.form_submit_button("✅ تنفيذ وحفظ البيانات")
            
            if submit:
                if name and brand:
                    save_data(action, name, brand, qty, dest)
                else:
                    st.error("الرجاء إكمال كافة البيانات")

    elif page == "لوحة الإدارة":
        st.sidebar.title("🔐 الإدارة")
        pw = st.sidebar.text_input("كلمة السر", type="password")
        if pw == ADMIN_PASSWORD:
            show_admin_dashboard()

def save_data(action, name, brand, qty, dest):
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    if "إدخال" in action:
        c.execute("INSERT OR REPLACE INTO inventory VALUES (?, ?, COALESCE((SELECT quantity FROM inventory WHERE name=? AND brand=?), 0) + ?)", (name, brand, name, brand, qty))
        c.execute("INSERT INTO movements VALUES ('IN', ?, ?, ?, '', ?)", (name, brand, qty, datetime.now()))
        send_telegram(f"📥 توريد جديد:\nصنف: {name}\nنوع: {brand}\nكمية: {qty}")
        st.success("تم التحديث!")
    else:
        res = c.execute("SELECT quantity FROM inventory WHERE name=? AND brand=?", (name, brand)).fetchone()
        if res and res[0] >= qty:
            c.execute("UPDATE inventory SET quantity = quantity - ? WHERE name=? AND brand=?", (qty, name, brand))
            c.execute("INSERT INTO movements VALUES ('OUT', ?, ?, ?, ?, ?)", (name, brand, qty, dest, datetime.now()))
            send_telegram(f"📤 صرف مخزني:\nصنف: {name}\nإلى: {dest}\nكمية: {qty}")
            st.warning("تم الإخراج!")
        else:
            st.error("الكمية غير كافية!")
    conn.commit()
    conn.close()

def show_admin_dashboard():
    st.header("📊 تحليلات السوق")
    conn = sqlite3.connect('warehouse.db')
    df = pd.read_sql("SELECT * FROM movements", conn)
    inv = pd.read_sql("SELECT * FROM inventory", conn)
    conn.close()
    
    st.subheader("📦 المخزون الحالي")
    st.table(inv)
    
    if not df.empty:
        st.subheader("📈 حركة السحب")
        st.bar_chart(df[df['type']=='OUT'].groupby('name')['quantity'].sum())

if __name__ == "__main__":
    main()
