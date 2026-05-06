import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import requests

# =========================
# Telegram Settings
# =========================
TELEGRAM_TOKEN = os.getenv("8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM")
CHAT_ID = os.getenv("5716145319")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except:
        pass


# =========================
# Arabic UI (RTL)
# =========================
st.set_page_config(page_title="نظام إدارة المخازن", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600&display=swap');

html, body, [class*="css"] {
    direction: rtl;
    text-align: right;
    font-family: 'Cairo', sans-serif;
}
</style>
""", unsafe_allow_html=True)


# =========================
# Warehouses
# =========================
WAREHOUSE_DIR = "warehouses"

if not os.path.exists(WAREHOUSE_DIR):
    os.makedirs(WAREHOUSE_DIR)

def قائمة_المخازن():
    return [f.replace(".db", "") for f in os.listdir(WAREHOUSE_DIR) if f.endswith(".db")]

def إنشاء_مخزن(name):
    conn = sqlite3.connect(f"{WAREHOUSE_DIR}/{name}.db")
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
        date TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def db(name):
    return f"{WAREHOUSE_DIR}/{name}.db"


# =========================
# Operations
# =========================
def إضافة(db_path, الصنف, الماركة, الكمية):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    موجود = c.execute(
        "SELECT quantity FROM inventory WHERE name=? AND brand=?",
        (الصنف, الماركة)
    ).fetchone()

    if موجود:
        c.execute(
            "UPDATE inventory SET quantity = quantity + ? WHERE name=? AND brand=?",
            (الكمية, الصنف, الماركة)
        )
    else:
        c.execute(
            "INSERT INTO inventory VALUES (?, ?, ?)",
            (الصنف, الماركة, الكمية)
        )

    c.execute(
        "INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
        ("إدخال", الصنف, الماركة, الكمية, "", datetime.now())
    )

    conn.commit()
    conn.close()

    send_telegram(f"تم إدخال بضاعة\nالصنف: {الصنف}\nالماركة: {الماركة}\nالكمية: {الكمية}")


def إخراج(db_path, الصنف, الماركة, الكمية, الجهة):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    موجود = c.execute(
        "SELECT quantity FROM inventory WHERE name=? AND brand=?",
        (الصنف, الماركة)
    ).fetchone()

    if not موجود or موجود[0] < الكمية:
        conn.close()
        return False, 0

    المتبقي = موجود[0] - الكمية

    c.execute(
        "UPDATE inventory SET quantity = quantity - ? WHERE name=? AND brand=?",
        (الكمية, الصنف, الماركة)
    )

    c.execute(
        "INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
        ("إخراج", الصنف, الماركة, الكمية, الجهة, datetime.now())
    )

    conn.commit()
    conn.close()

    send_telegram(
        f"تم إخراج بضاعة\nالصنف: {الصنف}\nالماركة: {الماركة}\nالكمية: {الكمية}\nالجهة: {الجهة}"
    )

    if المتبقي <= 5:
        send_telegram(
            f"تنبيه: مخزون منخفض\nالصنف: {الصنف}\nالماركة: {الماركة}\nالمتبقي: {المتبقي}"
        )

    return True, المتبقي


# =========================
# UI
# =========================
def التطبيق():

    st.title("نظام إدارة المخازن")

    # ===== إدارة المخازن =====
    st.sidebar.header("المخازن")

    المخازن = قائمة_المخازن()

    جديد = st.sidebar.text_input("إنشاء مخزن جديد")
    if st.sidebar.button("إنشاء"):
        if جديد:
            إنشاء_مخزن(جديد)
            st.rerun()

    if not المخازن:
        st.warning("لا توجد مخازن. قم بإنشاء مخزن أولاً.")
        return

    المخزن = st.sidebar.selectbox("اختيار المخزن", المخازن)
    db_path = db(المخزن)

    تبويب1, تبويب2, تبويب3 = st.tabs([
        "إضافة بضاعة",
        "إخراج بضاعة",
        "سجل المخزون"
    ])

    # ================= إضافة =================
    with تبويب1:
        st.subheader("إضافة بضاعة")

        conn = sqlite3.connect(db_path)
        data = pd.read_sql("SELECT * FROM inventory", conn)
        conn.close()

        الصنف = st.selectbox("الصنف", ["صنف جديد"] + list(data["name"].unique()))

        if الصنف == "صنف جديد":
            الصنف = st.text_input("اسم الصنف")
            الماركة = st.text_input("الماركة")
        else:
            ماركات = data[data["name"] == الصنف]["brand"].unique()
            الماركة = st.selectbox("الماركة", list(ماركات) if len(ماركات) > 0 else ["ماركة جديدة"])

            if الماركة == "ماركة جديدة":
                الماركة = st.text_input("اسم الماركة")

        الكمية = st.number_input("الكمية", min_value=1)

        if st.button("حفظ"):
            إضافة(db_path, الصنف, الماركة, الكمية)
            st.success("تم الحفظ بنجاح")

    # ================= إخراج =================
    with تبويب2:
        st.subheader("إخراج بضاعة")

        conn = sqlite3.connect(db_path)
        data = pd.read_sql("SELECT * FROM inventory", conn)
        conn.close()

        if data.empty:
            st.info("لا يوجد مخزون")
        else:

            الصنف = st.selectbox("الصنف", data["name"].unique())
            filtered = data[data["name"] == الصنف]

            خيارات = [
                f"{r['brand']} (المتوفر: {r['quantity']})"
                for _, r in filtered.iterrows()
            ]

            اختيار = st.selectbox("الماركة", خيارات)
            الماركة = اختيار.split(" (")[0]

            المتوفر = filtered[filtered["brand"] == الماركة]["quantity"].values[0]

            st.write("الكمية المتوفرة:", المتوفر)

            الكمية = st.number_input("الكمية", min_value=1, max_value=int(المتوفر))
            الجهة = st.text_input("الجهة")

            if st.button("تنفيذ"):
                ok, remaining = إخراج(db_path, الصنف, الماركة, الكمية, الجهة)

                if ok:
                    st.success("تم الإخراج بنجاح")
                else:
                    st.error("الكمية غير كافية")

    # ================= السجل =================
    with تبويب3:
        st.subheader("سجل العمليات")

        conn = sqlite3.connect(db_path)
        inv = pd.read_sql("SELECT * FROM inventory", conn)
        mov = pd.read_sql("SELECT * FROM movements ORDER BY date DESC", conn)
        conn.close()

        st.write("المخزون الحالي")
        st.dataframe(inv, use_container_width=True)

        st.write("سجل الحركة")
        st.dataframe(mov, use_container_width=True)


if __name__ == "__main__":
    التطبيق()