import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests

st.set_page_config(page_title="نظام إدارة المخازن", layout="wide")

# =========================
# Google Sheets اتصال
# =========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)

# =========================
# Telegram
# =========================
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# =========================
# أدوات Google Sheets
# =========================
def open_sheet(name):
    try:
        return client.open(name)
    except:
        return client.create(name)

def get_ws(sheet, name):
    try:
        return sheet.worksheet(name)
    except:
        return sheet.add_worksheet(title=name, rows=1000, cols=10)

def load_df(sheet, ws_name, cols):
    ws = get_ws(sheet, ws_name)
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=cols)

def save_df(sheet, ws_name, df):
    ws = get_ws(sheet, ws_name)
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())

# =========================
# اختيار المخزن
# =========================
st.sidebar.title("المخازن")

warehouse_name = st.sidebar.text_input("اسم المخزن")
if st.sidebar.button("فتح / إنشاء"):
    st.session_state.warehouse = warehouse_name

if "warehouse" not in st.session_state:
    st.stop()

sheet = open_sheet(st.session_state.warehouse)

# =========================
# تحميل البيانات
# =========================
inv = load_df(sheet, "inventory", ["name","brand","quantity"])
mov = load_df(sheet, "movements", ["type","name","brand","quantity","dest","date"])

# =========================
# Tabs
# =========================
tab1, tab2, tab3, tab4 = st.tabs(["إدخال", "إخراج", "المخزون", "الإدارة"])

# =========================
# إدخال
# =========================
with tab1:
    st.subheader("إدخال بضاعة")

    with st.form("add"):
        name = st.text_input("الصنف")
        brand = st.text_input("الماركة")
        qty = st.number_input("الكمية", 1)

        if st.form_submit_button("حفظ"):
            if ((inv["name"] == name) & (inv["brand"] == brand)).any():
                inv.loc[(inv["name"]==name)&(inv["brand"]==brand),"quantity"] += qty
            else:
                inv.loc[len(inv)] = [name,brand,qty]

            mov.loc[len(mov)] = ["إدخال",name,brand,qty,"",str(datetime.now())]

            save_df(sheet,"inventory",inv)
            save_df(sheet,"movements",mov)

            send_telegram(f"إدخال: {name}-{brand}-{qty}")

            st.success("تم الإدخال")

# =========================
# إخراج
# =========================
with tab2:
    st.subheader("إخراج بضاعة")

    if not inv.empty:
        name = st.selectbox("الصنف",inv["name"].unique())
        filtered = inv[inv["name"]==name]

        brand = st.selectbox("الماركة",filtered["brand"])
        available = int(filtered[filtered["brand"]==brand]["quantity"].values[0])

        st.info(f"المتوفر: {available}")

        qty = st.number_input("الكمية",1,available)
        dest = st.text_input("الجهة")

        if st.button("تنفيذ"):
            if available >= qty:
                inv.loc[(inv["name"]==name)&(inv["brand"]==brand),"quantity"] -= qty

                mov.loc[len(mov)] = ["إخراج",name,brand,qty,dest,str(datetime.now())]

                save_df(sheet,"inventory",inv)
                save_df(sheet,"movements",mov)

                send_telegram(f"إخراج: {name}-{brand}-{qty}")

                st.success("تم الإخراج")
            else:
                st.error("الكمية غير كافية")

# =========================
# المخزون
# =========================
with tab3:
    st.subheader("المخزون الحالي")
    st.dataframe(inv)

    st.subheader("سجل العمليات")
    st.dataframe(mov.sort_values("date",ascending=False))

# =========================
# الإدارة
# =========================
with tab4:
    st.subheader("إدارة المخزن")

    st.write("حذف صنف")

    for i,row in inv.iterrows():
        c1,c2,c3,c4 = st.columns(4)
        c1.write(row["name"])
        c2.write(row["brand"])
        c3.write(row["quantity"])

        if c4.button("حذف",key=i):
            inv = inv.drop(i)
            save_df(sheet,"inventory",inv)
            st.rerun()

    st.divider()

    st.write("إضافة مباشرة")

    n = st.text_input("الصنف",key="n1")
    b = st.text_input("الماركة",key="n2")
    q = st.number_input("الكمية",0,key="n3")

    if st.button("حفظ"):
        inv.loc[len(inv)] = [n,b,q]
        save_df(sheet,"inventory",inv)
        st.success("تم")
        st.rerun()