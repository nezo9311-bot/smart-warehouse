import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import requests
import os

# =========================
# 1. الإعدادات
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"
ADMIN_PASSWORD = "123"

st.set_page_config(page_title="نظام النذير للمخازن", layout="wide")

@st.cache_resource
def init_supabase():
    url = SUPABASE_URL.strip().replace("/rest/v1/", "")
    if url.endswith("/"): url = url[:-1]
    return create_client(url, SUPABASE_KEY)

supabase: Client = init_supabase()

def get_data(table):
    try:
        res = supabase.table(table).select("*").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
        # تنظيف البيانات: حذف الصفوف الفارغة تماماً وتحويل الأنواع
        if not df.empty:
            df = df.dropna(how='all') 
        return df
    except: return pd.DataFrame()

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except: pass

# =========================
# 2. معالجة قائمة المخازن (هنا الحل)
# =========================
inv_df = get_data("inventory")
default_warehouses = ["مخزن البخاري", "مخزن الجديد"]

# التأكد من أن القائمة تحتوي على نصوص فقط ولا تحتوي على قيم NaN
if not inv_df.empty and 'warehouse' in inv_df.columns:
    # 1. استخراج القيم الفريدة 2. تحويلها لنصوص 3. استبعاد أي قيمة فارغة أو None
    db_whs = inv_df['warehouse'].unique().tolist()
    clean_db_whs = [str(x) for x in db_whs if x is not None and str(x).lower() != 'nan']
    # دمج وترتيب
    wh_list = sorted(list(set(default_warehouses + clean_db_whs)))
else:
    wh_list = default_warehouses

# =========================
# 3. الواجهة البرمجية
# =========================
st.sidebar.title("🏢 مستودعات النذير")

tab1, tab2, tab3, tab4 = st.tabs(["📊 جرد المخازن", "📥 توريد", "📤 صرف", "⚙️ إدارة"])

# --- جرد المخازن ---
with tab1:
    sel_wh = st.selectbox("اختر المخزن", wh_list)
    if not inv_df.empty:
        # تحويل عمود المستودع لنص للمقارنة الصحيحة
        inv_df['warehouse'] = inv_df['warehouse'].astype(str)
        disp = inv_df[inv_df['warehouse'] == sel_wh]
        if not disp.empty:
            st.table(disp[['name', 'brand', 'quantity']])
        else:
            st.info(f"المخزن {sel_wh} فارغ حالياً.")

# --- التوريد ---
with tab2:
    with st.form("in_form", clear_on_submit=True):
        t_wh = st.selectbox("إلى مخزن:", wh_list)
        n = st.text_input("اسم الصنف")
        b = st.text_input("الماركة")
        q = st.number_input("الكمية", min_value=1)
        if st.form_submit_button("حفظ التوريد ✅"):
            if n:
                match = supabase.table("inventory").select("*").eq("name", n).eq("warehouse", t_wh).execute()
                if match.data:
                    supabase.table("inventory").update({"quantity": int(match.data[0]['quantity'] + q)}).eq("id", match.data[0]['id']).execute()
                else:
                    supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q, "warehouse": t_wh}).execute()
                send_telegram(f"📥 توريد: {n} لمخزن {t_wh}")
                st.rerun()

# --- الصرف ---
with tab3:
    if not inv_df.empty:
        with st.form("out_form"):
            source_wh = st.selectbox("اصرف من:", wh_list)
            inv_df['warehouse'] = inv_df['warehouse'].astype(str)
            items = inv_df[(inv_df['warehouse'] == source_wh) & (inv_df['quantity'] > 0)]
            if not items.empty:
                n_o = st.selectbox("الصنف", items['name'].unique())
                q_o = st.number_input("الكمية", min_value=1)
                dst = st.text_input("المستلم")
                if st.form_submit_button("تأكيد الصرف"):
                    row = items[items['name'] == n_o].iloc[0]
                    if row['quantity'] >= q_o:
                        supabase.table("inventory").update({"quantity": int(row['quantity'] - q_o)}).eq("id", row['id']).execute()
                        st.success("تمت العملية")
                        st.rerun()
            else: st.warning("لا توجد بضاعة")

# --- الإدارة ---
with tab4:
    if st.text_input("كلمة السر", type="password") == ADMIN_PASSWORD:
        if not inv_df.empty:
            item_manage = st.selectbox("اختر صنفاً", inv_df.apply(lambda x: f"{x['name']} ({x['warehouse']})", axis=1))
            idx = inv_df.index[inv_df.apply(lambda x: f"{x['name']} ({x['warehouse']})", axis=1) == item_manage][0]
            if st.button("حذف نهائي ❌"):
                supabase.table("inventory").delete().eq("id", inv_df.iloc[idx]['id']).execute()
                st.rerun()