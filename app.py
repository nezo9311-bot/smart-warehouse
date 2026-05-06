import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import requests

# =========================
# إعداد الصفحة (مهم جداً)
# =========================
st.set_page_config(
    page_title="نظام إدارة المخازن",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================
# فرض العربية + RTL
# =========================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600&display=swap');

html, body, [class*="css"] {
    direction: rtl;
    text-align: right;
    font-family: 'Cairo', sans-serif;
}

/* إخفاء أي نص إنجليزي افتراضي */
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# =========================
# إعداد تليجرام
# =========================
TELEGRAM_TOKEN = os.getenv("8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM")
CHAT_ID = os.getenv("5716145319")

def send_telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text})
    except:
        pass


# =========================
# قاعدة البيانات
# =========================
DIR = "warehouses"

if not os.path.exists(DIR):
    os.makedirs(DIR)

def قائمة_المخازن():
    return [f.replace(".db", "") for f in os.listdir(DIR) if f.endswith(".db")]

def إنشاء_مخزن(name):
    conn = sqlite3.connect(f"{DIR}/{name}.db")
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
    return f"{DIR}/{name}.db"


# =========================
# العمليات
# =========================
def إدخال(db_path, الصنف, الماركة, الكمية):
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
        return False

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
        send_telegram(f"تنبيه مخزون منخفض\nالصنف: {الصنف}\nالمتبقي: {المتبقي}")

    return True


# =========================
# الواجهة العربية الكاملة
# =========================
def التطبيق():

    st.title("نظام إدارة المخازن")

    st.sidebar.title("إدارة المخازن")

    المخازن = قائمة_المخازن()

    اسم_جديد = st.sidebar.text_input("إنشاء مخزن جديد")
    if st.sidebar.button("إنشاء مخزن"):
        if اسم_جديد:
            إنشاء_مخزن(اسم_جديد)
            st.rerun()

    if not المخازن:
        st.warning("لا يوجد مخازن حالياً")
        return

    المخزن = st.sidebar.selectbox("اختيار المخزن", المخازن)
    db_path = db(المخزن)

    tab1, tab2, tab3 = st.tabs([
        "إدخال بضاعة",
        "إخراج بضاعة",
        "سجل العمليات"
    ])

    # ================= إدخال =================
    with tab1:
        st.subheader("إدخال بضاعة")

        conn = sqlite3.connect(db_path)
        data = pd.read_sql("SELECT * FROM inventory", conn)
        conn.close()

        الصنف = st.selectbox("الصنف", ["صنف جديد"] + list(data["name"].unique()))

        if الصنف == "صنف جديد":
            الصنف = st.text_input("اسم الصنف")
            الماركة = st.text_input("اسم الماركة")
        else:
            ماركات = data[data["name"] == الصنف]["brand"].unique()
            الماركة = st.selectbox("الماركة", list(ماركات) if len(ماركات) > 0 else ["ماركة جديدة"])

            if الماركة == "ماركة جديدة":
                الماركة = st.text_input("اسم الماركة")

        الكمية = st.number_input("الكمية", min_value=1)

        if st.button("حفظ الإدخال"):
            إدخال(db_path, الصنف, الماركة, الكمية)
            st.success("تم حفظ البيانات")

    # ================= إخراج =================
    with tab2:
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
            الجهة = st.text_input("الجهة المستلمة")

            if st.button("تنفيذ الإخراج"):
                ok = إخراج(db_path, الصنف, الماركة, الكمية, الجهة)

                if ok:
                    st.success("تم تنفيذ الإخراج")
                else:
                    st.error("الكمية غير كافية")

    # ================= السجل =================
    with tab3:
        st.subheader("سجل العمليات")

        conn = sqlite3.connect(db_path)
        inv = pd.read_sql("SELECT * FROM inventory", conn)
        mov = pd.read_sql("SELECT * FROM movements ORDER BY date DESC", conn)
        conn.close()

        st.write("المخزون الحالي")
        st.dataframe(inv)

        st.write("سجل الحركة")
        st.dataframe(mov)


if __name__ == "__main__":
    التطبيق()