import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import requests

# =========================
# إعداد التليجرام
# =========================
TELEGRAM_TOKEN = os.getenv("8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM")
CHAT_ID = os.getenv("5716145319")

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass


# =========================
# إدارة المخازن
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

def مسار_المخزن(name):
    return f"{WAREHOUSE_DIR}/{name}.db"


# =========================
# العمليات
# =========================
def إضافة_بضاعة(db, الصنف, الماركة, الكمية):
    conn = sqlite3.connect(db)
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


def إخراج_بضاعة(db, الصنف, الماركة, الكمية, الجهة):
    conn = sqlite3.connect(db)
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
        send_telegram(f"تنبيه مخزون منخفض\nالصنف: {الصنف}\nالماركة: {الماركة}\nالمتبقي: {المتبقي}")

    return True, المتبقي


# =========================
# الواجهة
# =========================
def التطبيق():
    st.set_page_config(page_title="نظام إدارة المخازن", layout="wide")

    st.title("نظام إدارة المخازن")

    # ===== الشريط الجانبي =====
    st.sidebar.header("إدارة المخازن")

    المخازن = قائمة_المخازن()

    مخزن_جديد = st.sidebar.text_input("إنشاء مخزن جديد")
    if st.sidebar.button("إنشاء"):
        if مخزن_جديد:
            إنشاء_مخزن(مخزن_جديد)
            st.rerun()

    if not المخازن:
        st.warning("لا توجد مخازن. قم بإنشاء مخزن أولاً.")
        return

    المخزن_المختار = st.sidebar.selectbox("اختيار المخزن", المخازن)
    db = مسار_المخزن(المخزن_المختار)

    تبويب1, تبويب2, تبويب3 = st.tabs([
        "إضافة بضاعة",
        "إخراج بضاعة",
        "سجل المخزون"
    ])

    # ================= إضافة =================
    with تبويب1:
        st.subheader("إضافة بضاعة جديدة")

        conn = sqlite3.connect(db)
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

        if st.button("حفظ الإضافة"):
            إضافة_بضاعة(db, الصنف, الماركة, الكمية)
            st.success("تمت إضافة البضاعة بنجاح")

    # ================= إخراج =================
    with تبويب2:
        st.subheader("إخراج بضاعة")

        conn = sqlite3.connect(db)
        data = pd.read_sql("SELECT * FROM inventory", conn)
        conn.close()

        if data.empty:
            st.info("لا توجد بيانات مخزون")
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
                ok, remaining = إخراج_بضاعة(db, الصنف, الماركة, الكمية, الجهة)

                if ok:
                    st.success("تم الإخراج بنجاح")
                else:
                    st.error("الكمية غير كافية")

    # ================= السجل =================
    with تبويب3:
        st.subheader("سجل العمليات")

        conn = sqlite3.connect(db)
        inv = pd.read_sql("SELECT * FROM inventory", conn)
        mov = pd.read_sql("SELECT * FROM movements ORDER BY date DESC", conn)
        conn.close()

        st.write("المخزون الحالي")
        st.dataframe(inv, use_container_width=True)

        st.write("سجل الحركة")
        st.dataframe(mov, use_container_width=True)


if __name__ == "__main__":
    التطبيق()