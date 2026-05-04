import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import requests
import google.generativeai as genai

# --- الإعدادات النهائية (بياناتك الحقيقية) ---
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"
GEMINI_API_KEY = "AIzaSyC11sWBSRyYut0SVzLxYGADh2mEk2HxeVg"
ADMIN_PASSWORD = "123"

# إعداد الذكاء الاصطناعي
genai.configure(api_key=GEMINI_API_KEY)

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

# --- وظيفة جلب سعر الدولار ---
def get_exchange_rate():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        data = requests.get(url).json()
        return data['rates']['SDG']
    except:
        return "غير متوفر"

# --- وظيفة إرسال تليجرام ---
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={msg}"
    try: requests.get(url)
    except: pass

# --- وظيفة المستشار الذكي ---
def ask_ai_advisor(inventory_df, dollar_rate):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    أنت مستشار اقتصادي خبير في السوق السوداني.
    بيانات المخزن الحالية: {inventory_df.to_string()}
    سعر الدولار الرسمي التقريبي: {dollar_rate} SDG
    حلل البيانات وأعطِ نصيحة تجارية ذكية لصاحب المستودع (النذير). 
    تحدث عن: السلع التي قد يرتفع سعرها، متى يقلل البيع، وماذا يشتري الآن.
    اجعل النصيحة مختصرة وقوية وباللهجة السودانية أو العربية البسيطة.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"عذراً، حدث خطأ في التحليل: {e}"

# --- واجهة المستخدم ---
def main():
    st.set_page_config(page_title="نظام النذير الذكي v2.0", layout="wide")
    init_db()
    
    menu = st.sidebar.selectbox("القائمة الرئيسية", ["العمليات اليومية", "لوحة التحكم الذكية"])

    if menu == "العمليات اليومية":
        st.header("📲 قسم العمليات الميدانية")
        action = st.radio("نوع العملية", ["إدخال بضاعة 📥", "إخراج بضاعة 📤"])
        
        with st.form("main_form"):
            conn = sqlite3.connect('warehouse.db')
            existing_data = pd.read_sql("SELECT DISTINCT name FROM inventory", conn)
            conn.close()
            
            name = st.selectbox("اسم الصنف", ["إضافة جديد +"] + list(existing_data['name'].unique()))
            if name == "إضافة جديد +":
                name = st.text_input("اسم الصنف الجديد")
            
            brand = st.text_input("الماركة")
            qty = st.number_input("الكمية", min_value=1)
            dest = st.text_input("الجهة (في حال الإخراج فقط)") if "إخراج" in action else ""
            
            if st.form_submit_button("حفظ العملية"):
                process_data(action, name, brand, qty, dest)

    elif menu == "لوحة التحكم الذكية":
        pw = st.sidebar.text_input("كلمة السر", type="password")
        if pw == ADMIN_PASSWORD:
            show_admin_section()
        else:
            st.warning("يرجى إدخال كلمة السر للوصول للتحليلات")

def process_data(action, name, brand, qty, dest):
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()
    if "إدخال" in action:
        c.execute("INSERT OR REPLACE INTO inventory VALUES (?, ?, COALESCE((SELECT quantity FROM inventory WHERE name=? AND brand=?), 0) + ?)", (name, brand, name, brand, qty))
        c.execute("INSERT INTO movements VALUES ('IN', ?, ?, ?, '', ?)", (name, brand, qty, datetime.now()))
        send_telegram(f"📥 تم توريد {qty} {name} ({brand})")
        st.success("تم الحفظ بنجاح")
    else:
        res = c.execute("SELECT quantity FROM inventory WHERE name=? AND brand=?", (name, brand)).fetchone()
        if res and res[0] >= qty:
            c.execute("UPDATE inventory SET quantity = quantity - ? WHERE name=? AND brand=?", (qty, name, brand))
            c.execute("INSERT INTO movements VALUES ('OUT', ?, ?, ?, ?, ?)", (name, brand, qty, dest, datetime.now()))
            send_telegram(f"📤 تم صرف {qty} {name} إلى {dest}")
            st.warning("تم تسجيل الخروج")
        else:
            st.error("الكمية غير كافية!")
    conn.commit()
    conn.close()

def show_admin_section():
    st.header("📊 التحليل الذكي ومراقبة السوق")
    
    rate = get_exchange_rate()
    st.metric("سعر الدولار (مؤشر رسمي)", f"{rate} SDG")
    
    conn = sqlite3.connect('warehouse.db')
    inv = pd.read_sql("SELECT * FROM inventory", conn)
    conn.close()
    
    st.subheader("📦 حالة المخزون الحالية")
    st.dataframe(inv, use_container_width=True)
    
    st.divider()
    st.subheader("🤖 مستشار الذكاء الاصطناعي")
    if st.button("توليد نصيحة تجارية بناءً على حالة السوق"):
        with st.spinner("الذكاء الاصطناعي يحلل البيانات الآن..."):
            advice = ask_ai_advisor(inv, rate)
            st.markdown(f"### 💡 نصيحة الخبير:\n{advice}")
            send_telegram(f"💡 نصيحة AI للنذير:\n{advice}")

if __name__ == "__main__":
    main()
