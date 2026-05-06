import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import requests

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(
    page_title="نظام إدارة المخازن",
    layout="wide"
)

# =========================
# CSS عربي
# =========================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600&display=swap');

html, body {
    font-family: 'Cairo', sans-serif;
}

label, p, h1, h2, h3 {
    text-align: right !important;
}

input {
    text-align: right;
}
</style>
""", unsafe_allow_html=True)

# =========================
# Telegram
# =========================
TELEGRAM_TOKEN = os.getenv("8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM")
CHAT_ID = os.getenv("5716145319")

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram not configured")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
        print("Telegram:", r.text)
    except Exception as e:
        print("Telegram error:", e)

# =========================
# قاعدة البيانات
# =========================
DIR = "warehouses"
os.makedirs(DIR, exist_ok=True)

def db_path(name):
    return f"{DIR}/{name}.db"

def create_db(name):
    conn = sqlite3.connect(db_path(name))
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        name TEXT,
        brand TEXT,
        quantity INTEGER,
        PRIMARY KEY(name, brand)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS movements (
        type TEXT,
        name TEXT,
        brand TEXT,
        quantity INTEGER,
        destination TEXT,
        date TEXT
    )
    """)

    conn.commit()
    conn.close()

def get_warehouses():
    return [f.replace(".db", "") for f in os.listdir(DIR) if f.endswith(".db")]

# =========================
# عمليات
# =========================
def add_item(db, name, brand, qty):
    conn = sqlite3.connect(db)
    c = conn.cursor()

    res = c.execute(
        "SELECT quantity FROM inventory WHERE name=? AND brand=?",
        (name, brand)
    ).fetchone()

    if res:
        c.execute(
            "UPDATE inventory SET quantity = quantity + ? WHERE name=? AND brand=?",
            (qty, name, brand)
        )
    else:
        c.execute(
            "INSERT INTO inventory VALUES (?, ?, ?)",
            (name, brand, qty)
        )

    c.execute(
        "INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
        ("إدخال", name, brand, qty, "", str(datetime.now()))
    )

    conn.commit()
    conn.close()

    send_telegram(f"إدخال: {name} - {brand} - {qty}")


def remove_item(db, name, brand, qty, dest):
    conn = sqlite3.connect(db)
    c = conn.cursor()

    res = c.execute(
        "SELECT quantity FROM inventory WHERE name=? AND brand=?",
        (name, brand)
    ).fetchone()

    if not res or res[0] < qty:
        conn.close()
        return False

    c.execute(
        "UPDATE inventory SET quantity = quantity - ? WHERE name=? AND brand=?",
        (qty, name, brand)
    )

    c.execute(
        "INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
        ("إخراج", name, brand, qty, dest, str(datetime.now()))
    )

    conn.commit()
    conn.close()

    send_telegram(f"إخراج: {name} - {brand} - {qty} إلى {dest}")

    return True

# =========================
# التطبيق
# =========================
st.title("نظام إدارة المخازن")

warehouses = get_warehouses()

new_wh = st.sidebar.text_input("إنشاء مخزن")
if st.sidebar.button("إنشاء"):
    if new_wh:
        create_db(new_wh)
        st.rerun()

if not warehouses:
    st.warning("لا يوجد مخازن")
    st.stop()

selected = st.sidebar.selectbox("اختيار المخزن", warehouses)
db = db_path(selected)

tab1, tab2, tab3 = st.tabs(["إدخال", "إخراج", "المخزون"])

# =========================
# Session State (لحذف الحقول)
# =========================
if "name" not in st.session_state:
    st.session_state.name = ""
if "brand" not in st.session_state:
    st.session_state.brand = ""

# ================= إدخال =================
with tab1:
    st.subheader("إدخال بضاعة")

    name = st.text_input("الصنف", key="name")
    brand = st.text_input("الماركة", key="brand")
    qty = st.number_input("الكمية", min_value=1)

    if st.button("حفظ"):
        add_item(db, name, brand, qty)

        # تفريغ الحقول
        st.session_state.name = ""
        st.session_state.brand = ""

        st.rerun()

# ================= إخراج =================
with tab2:
    st.subheader("إخراج بضاعة")

    conn = sqlite3.connect(db)
    data = pd.read_sql("SELECT * FROM inventory", conn)
    conn.close()

    if data.empty:
        st.info("لا يوجد مخزون")
    else:
        name = st.selectbox("الصنف", data["name"].unique())
        filtered = data[data["name"] == name]

        options = [
            f"{r['brand']} (المتوفر: {r['quantity']})"
            for _, r in filtered.iterrows()
        ]

        selected_brand = st.selectbox("الماركة", options)
        brand = selected_brand.split(" (")[0]

        available = filtered[filtered["brand"] == brand]["quantity"].values[0]

        st.write("المتوفر:", available)

        qty = st.number_input("الكمية", 1, int(available))
        dest = st.text_input("الجهة")

        if st.button("تنفيذ"):
            ok = remove_item(db, name, brand, qty, dest)

            if ok:
                st.success("تم الإخراج")
            else:
                st.error("الكمية غير كافية")

# ================= مخزون =================
with tab3:
    st.subheader("المخزون")

    conn = sqlite3.connect(db)
    inv = pd.read_sql("SELECT * FROM inventory", conn)
    mov = pd.read_sql("SELECT * FROM movements ORDER BY date DESC", conn)
    conn.close()

    st.dataframe(inv)
    st.dataframe(mov)