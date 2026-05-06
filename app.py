import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import requests

# --- إعدادات ---
TELEGRAM_TOKEN = os.getenv("8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM")
CHAT_ID = os.getenv("5716145319")

WAREHOUSE_DIR = "warehouses"

# --- إنشاء مجلد المخازن ---
if not os.path.exists(WAREHOUSE_DIR):
    os.makedirs(WAREHOUSE_DIR)

# --- إدارة المخازن ---
def get_warehouses():
    return [f.replace(".db", "") for f in os.listdir(WAREHOUSE_DIR) if f.endswith(".db")]

def create_warehouse(name):
    path = f"{WAREHOUSE_DIR}/{name}.db"
    conn = sqlite3.connect(path)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                 (name TEXT, brand TEXT, quantity INTEGER, 
                 PRIMARY KEY(name, brand))''')

    c.execute('''CREATE TABLE IF NOT EXISTS movements 
                 (type TEXT, name TEXT, brand TEXT, quantity INTEGER, 
                  destination TEXT, date TIMESTAMP)''')

    conn.commit()
    conn.close()

def get_db_path(name):
    return f"{WAREHOUSE_DIR}/{name}.db"

# --- تليجرام ---
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# --- العمليات ---
def process_data(db, action, name, brand, qty, dest):
    conn = sqlite3.connect(db)
    c = conn.cursor()

    if action == "إدخال":
        res = c.execute("SELECT quantity FROM inventory WHERE name=? AND brand=?", (name, brand)).fetchone()

        if res:
            c.execute("UPDATE inventory SET quantity = quantity + ? WHERE name=? AND brand=?",
                      (qty, name, brand))
        else:
            c.execute("INSERT INTO inventory VALUES (?, ?, ?)", (name, brand, qty))

        c.execute("INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
                  ("إدخال", name, brand, qty, "", datetime.now()))

    elif action == "إخراج":
        res = c.execute("SELECT quantity FROM inventory WHERE name=? AND brand=?", (name, brand)).fetchone()

        if res and res[0] >= qty:
            c.execute("UPDATE inventory SET quantity = quantity - ? WHERE name=? AND brand=?",
                      (qty, name, brand))

            c.execute("INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
                      ("إخراج", name, brand, qty, dest, datetime.now()))
        else:
            st.error("الكمية غير كافية!")
            conn.close()
            return

    conn.commit()
    conn.close()

# --- التطبيق ---
def main():
    st.set_page_config(page_title="نظام المخازن", layout="wide")

    st.title("📦 نظام إدارة المخازن")

    # --- إدارة المخازن ---
    st.sidebar.header("🏬 إدارة المخازن")

    warehouses = get_warehouses()

    new_wh = st.sidebar.text_input("➕ إضافة مخزن جديد")
    if st.sidebar.button("إنشاء"):
        if new_wh:
            create_warehouse(new_wh)
            st.success("تم إنشاء المخزن")
            st.rerun()

    if not warehouses:
        st.warning("لا يوجد مخازن، قم بإنشاء واحد أولاً")
        return

    selected_wh = st.sidebar.selectbox("اختر المخزن", warehouses)
    db_path = get_db_path(selected_wh)

    menu = st.sidebar.selectbox("القائمة", [
        "إدخال 📥",
        "إخراج 📤",
        "الإدارة 📊"
    ])

    # 📥 إدخال
    if menu == "إدخال 📥":
        st.header(f"📥 إدخال - {selected_wh}")

        conn = sqlite3.connect(db_path)
        data = pd.read_sql("SELECT * FROM inventory", conn)
        conn.close()

        with st.form("in_form"):
            name = st.selectbox("الصنف", ["جديد +"] + list(data['name'].unique()))

            if name == "جديد +":
                name = st.text_input("اسم الصنف")
                brand = st.text_input("الماركة")
            else:
                brands = data[data['name'] == name]['brand'].unique()
                brand = st.selectbox("الماركة", list(brands) + ["جديدة +"])

                if brand == "جديدة +":
                    brand = st.text_input("ماركة جديدة")

            qty = st.number_input("الكمية", min_value=1)

            if st.form_submit_button("حفظ"):
                process_data(db_path, "إدخال", name, brand, qty, "")
                st.success("تم الإدخال")

    # 📤 إخراج
    elif menu == "إخراج 📤":
        st.header(f"📤 إخراج - {selected_wh}")

        conn = sqlite3.connect(db_path)
        data = pd.read_sql("SELECT * FROM inventory", conn)
        conn.close()

        if data.empty:
            st.warning("لا يوجد مخزون")
            return

        name = st.selectbox("الصنف", data['name'].unique())
        filtered = data[data['name'] == name]

        options = [f"{row['brand']} (المتبقي: {row['quantity']})" for _, row in filtered.iterrows()]
        selected = st.selectbox("الماركة", options)

        brand = selected.split(" (")[0]
        current_qty = filtered[filtered['brand'] == brand]['quantity'].values[0]

        st.info(f"المتوفر: {current_qty}")

        with st.form("out_form"):
            qty = st.number_input("الكمية", min_value=1, max_value=int(current_qty))
            dest = st.text_input("الجهة")

            if st.form_submit_button("صرف"):
                process_data(db_path, "إخراج", name, brand, qty, dest)
                st.success("تم الإخراج")

    # 📊 الإدارة
    elif menu == "الإدارة 📊":
        st.header("📊 عرض جميع المخازن")

        for wh in warehouses:
            st.subheader(f"📦 {wh}")

            conn = sqlite3.connect(get_db_path(wh))
            inv = pd.read_sql("SELECT * FROM inventory", conn)
            conn.close()

            inv = inv.rename(columns={
                "name": "الصنف",
                "brand": "الماركة",
                "quantity": "الكمية"
            })

            st.dataframe(inv, use_container_width=True)

if __name__ == "__main__":
    main()