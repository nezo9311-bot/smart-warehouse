import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import requests

st.set_page_config(page_title="نظام إدارة المخازن", layout="wide")

# =========================
# Telegram
# =========================
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"

LOW_STOCK = 5  # حد التنبيه

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

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
    return [f.replace(".db","") for f in os.listdir(DIR) if f.endswith(".db")]

# =========================
# العمليات
# =========================
def add_item(db, name, brand, qty):
    conn = sqlite3.connect(db)
    c = conn.cursor()

    res = c.execute("SELECT quantity FROM inventory WHERE name=? AND brand=?",(name,brand)).fetchone()

    if res:
        c.execute("UPDATE inventory SET quantity=quantity+? WHERE name=? AND brand=?",(qty,name,brand))
    else:
        c.execute("INSERT INTO inventory VALUES(?,?,?)",(name,brand,qty))

    c.execute("INSERT INTO movements VALUES(?,?,?,?,?,?)",
              ("إدخال",name,brand,qty,"",str(datetime.now())))

    conn.commit()
    conn.close()

    send_telegram(f"تم إدخال {qty} من {name} - {brand}")

def remove_item(db,name,brand,qty,dest):
    conn = sqlite3.connect(db)
    c = conn.cursor()

    res = c.execute("SELECT quantity FROM inventory WHERE name=? AND brand=?",(name,brand)).fetchone()

    if not res or res[0] < qty:
        conn.close()
        return False

    new_qty = res[0] - qty

    c.execute("UPDATE inventory SET quantity=quantity-? WHERE name=? AND brand=?",(qty,name,brand))
    c.execute("INSERT INTO movements VALUES(?,?,?,?,?,?)",
              ("إخراج",name,brand,qty,dest,str(datetime.now())))

    conn.commit()
    conn.close()

    send_telegram(f"تم إخراج {qty} من {name} - {brand} إلى {dest}")

    if new_qty <= LOW_STOCK:
        send_telegram(f"تنبيه: المخزون منخفض ({name} - {brand}) المتبقي {new_qty}")

    return True

# =========================
# الواجهة
# =========================
st.title("نظام إدارة المخازن")

warehouses = get_warehouses()

new_wh = st.sidebar.text_input("مخزن جديد")
if st.sidebar.button("إنشاء"):
    if new_wh:
        create_db(new_wh)
        st.rerun()

if not warehouses:
    st.warning("لا يوجد مخازن")
    st.stop()

selected = st.sidebar.selectbox("اختر المخزن",warehouses)
db = db_path(selected)

tab1,tab2,tab3,tab4 = st.tabs(["إدخال","إخراج","المخزون","الإدارة"])

# ================= إدخال =================
with tab1:
    st.subheader("إدخال بضاعة")

    with st.form("add"):
        name = st.text_input("الصنف")
        brand = st.text_input("الماركة")
        qty = st.number_input("الكمية",1)

        if st.form_submit_button("حفظ"):
            add_item(db,name,brand,qty)
            st.success("تم الإدخال")

# ================= إخراج =================
with tab2:
    st.subheader("إخراج بضاعة")

    conn = sqlite3.connect(db)
    df = pd.read_sql("SELECT * FROM inventory",conn)
    conn.close()

    if not df.empty:
        name = st.selectbox("الصنف",df["name"].unique())
        filtered = df[df["name"]==name]

        brand = st.selectbox("الماركة",filtered["brand"])
        available = int(filtered[filtered["brand"]==brand]["quantity"].values[0])

        st.info(f"المتوفر: {available}")

        qty = st.number_input("الكمية",1,available)
        dest = st.text_input("الجهة")

        if st.button("تنفيذ"):
            if remove_item(db,name,brand,qty,dest):
                st.success("تم الإخراج")
            else:
                st.error("الكمية غير كافية")

# ================= المخزون =================
with tab3:
    st.subheader("المخزون")

    conn = sqlite3.connect(db)

    inv = pd.read_sql("""
    SELECT name AS الصنف, brand AS الماركة, quantity AS الكمية FROM inventory
    """,conn)

    mov = pd.read_sql("""
    SELECT type AS النوع, name AS الصنف, brand AS الماركة,
           quantity AS الكمية, destination AS الجهة, date AS التاريخ
    FROM movements ORDER BY date DESC
    """,conn)

    conn.close()

    st.dataframe(inv,use_container_width=True)
    st.dataframe(mov,use_container_width=True)

# ================= الإدارة =================
with tab4:
    st.subheader("لوحة الإدارة")

    wh = st.selectbox("اختر مخزن",warehouses)
    db_admin = db_path(wh)

    conn = sqlite3.connect(db_admin)
    inv = pd.read_sql("SELECT * FROM inventory",conn)
    conn.close()

    for i,row in inv.iterrows():
        col1,col2,col3,col4 = st.columns(4)

        col1.write(row["name"])
        col2.write(row["brand"])
        col3.write(row["quantity"])

        if col4.button("حذف",key=f"d{i}"):
            conn = sqlite3.connect(db_admin)
            c = conn.cursor()
            c.execute("DELETE FROM inventory WHERE name=? AND brand=?",(row["name"],row["brand"]))
            conn.commit()
            conn.close()
            st.rerun()

    st.divider()

    name = st.text_input("الصنف",key="a1")
    brand = st.text_input("الماركة",key="a2")
    qty = st.number_input("الكمية",0,key="a3")

    if st.button("حفظ"):
        add_item(db_admin,name,brand,qty)
        st.success("تم التحديث")
        st.rerun()