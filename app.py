import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import requests

# --- إعدادات ---
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                 (name TEXT, brand TEXT, quantity INTEGER, 
                 PRIMARY KEY(name, brand))''')

    c.execute('''CREATE TABLE IF NOT EXISTS movements 
                 (type TEXT, name TEXT, brand TEXT, quantity INTEGER, 
                  destination TEXT, date TIMESTAMP)''')

    conn.commit()
    conn.close()

# --- سعر الدولار ---
def get_exchange_rate():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        data = requests.get(url).json()
        return data['rates']['SDG']
    except:
        return "غير متوفر"

# --- تليجرام ---
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# --- معالجة العمليات ---
def process_data(action, name, brand, qty, dest):
    conn = sqlite3.connect('warehouse.db')
    c = conn.cursor()

    if action == "إدخال":
        c.execute("""
        INSERT OR REPLACE INTO inventory 
        VALUES (?, ?, COALESCE(
            (SELECT quantity FROM inventory WHERE name=? AND brand=?), 0
        ) + ?)
        """, (name, brand, name, brand, qty))

        c.execute("INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
                  ("إدخال", name, brand, qty, "", datetime.now()))

        send_telegram(f"📥 تم إدخال {qty} {name} ({brand})")
        st.success("تم الإدخال بنجاح")

    elif action == "إخراج":
        res = c.execute("SELECT quantity FROM inventory WHERE name=? AND brand=?",
                        (name, brand)).fetchone()

        if res and res[0] >= qty:
            c.execute("UPDATE inventory SET quantity = quantity - ? WHERE name=? AND brand=?",
                      (qty, name, brand))

            c.execute("INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
                      ("إخراج", name, brand, qty, dest, datetime.now()))

            send_telegram(f"📤 تم إخراج {qty} {name} إلى {dest}")
            st.warning("تم الإخراج بنجاح")

            # تنبيه نقص
            if res[0] - qty < 5:
                send_telegram(f"⚠️ المخزون قرب ينتهي من {name}")

        else:
            st.error("الكمية غير كافية!")

    conn.commit()
    conn.close()

# --- لوحة الإدارة ---
def show_admin():
    st.header("📊 لوحة الإدارة")

    rate = get_exchange_rate()
    st.metric("سعر الدولار", f"{rate} SDG")

    conn = sqlite3.connect('warehouse.db')

    inv = pd.read_sql("SELECT * FROM inventory", conn)
    movements = pd.read_sql("SELECT * FROM movements ORDER BY date DESC", conn)

    conn.close()

    st.subheader("📦 المخزون الحالي")
    st.dataframe(inv, use_container_width=True)

    st.divider()

    st.subheader("📜 سجل الحركات")
    filter_type = st.selectbox("فلترة", ["الكل", "إدخال", "إخراج"])

    if filter_type != "الكل":
        movements = movements[movements['type'] == filter_type]

    st.dataframe(movements, use_container_width=True)

    if not inv.empty:
        st.subheader("📈 إحصائيات")
        st.metric("إجمالي الكميات", int(inv['quantity'].sum()))
        st.metric("عدد الأصناف", inv.shape[0])
        st.bar_chart(inv.set_index('name')['quantity'])

# --- التطبيق الرئيسي ---
def main():
    st.set_page_config(page_title="نظام المخازن", layout="wide")
    init_db()

    menu = st.sidebar.selectbox("القائمة", [
        "إدخال بضاعة 📥",
        "إخراج بضاعة 📤",
        "الإدارة 📊"
    ])

    # 📥 إدخال
    if menu == "إدخال بضاعة 📥":
        st.header("📥 إدخال بضاعة")

        with st.form("in_form"):
            conn = sqlite3.connect('warehouse.db')
            data = pd.read_sql("SELECT DISTINCT name FROM inventory", conn)
            conn.close()

            name = st.selectbox("اسم الصنف", ["إضافة جديد +"] + list(data['name'].unique()))
            if name == "إضافة جديد +":
                name = st.text_input("اسم الصنف الجديد")

            brand = st.text_input("الماركة")
            qty = st.number_input("الكمية", min_value=1)

            if st.form_submit_button("حفظ"):
                process_data("إدخال", name, brand, qty, "")

    # 📤 إخراج
    elif menu == "إخراج بضاعة 📤":
        st.header("📤 إخراج بضاعة")

        with st.form("out_form"):
            conn = sqlite3.connect('warehouse.db')
            data = pd.read_sql("SELECT * FROM inventory", conn)
            conn.close()

            if data.empty:
                st.warning("لا يوجد مخزون")
                return

            name = st.selectbox("اسم الصنف", data['name'].unique())
            brand = st.text_input("الماركة")
            qty = st.number_input("الكمية", min_value=1)
            dest = st.text_input("الجهة المستلمة")

            if st.form_submit_button("صرف"):
                process_data("إخراج", name, brand, qty, dest)

    # 📊 الإدارة
    elif menu == "الإدارة 📊":
        show_admin()


if __name__ == "__main__":
    main()