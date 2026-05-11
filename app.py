import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import requests
import os

# =========================
# 1. الإعدادات والربط
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"
ADMIN_PASSWORD = "123"

st.set_page_config(page_title="نظام النذير للمخازن", layout="wide")

# تنظيف الرابط والاتصال بـ Supabase
@st.cache_resource
def init_supabase():
    if not SUPABASE_URL:
        st.error("خطأ: SUPABASE_URL غير موجود في إعدادات Render")
        st.stop()
    url = SUPABASE_URL.strip().replace("/rest/v1/", "")
    if url.endswith("/"): url = url[:-1]
    return create_client(url, SUPABASE_KEY)

supabase: Client = init_supabase()

# =========================
# 2. وظائف مساعدة
# =========================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except: pass

def get_data(table):
    try:
        res = supabase.table(table).select("*").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except:
        return pd.DataFrame()

# =========================
# 3. واجهة المستخدم
# =========================
st.sidebar.title("🏢 مستودعات النذير")
st.sidebar.markdown("---")

inv_df = get_data("inventory")

if not inv_df.empty and 'warehouse' in inv_df.columns:
    wh_list = sorted(inv_df['warehouse'].unique().tolist())
else:
    wh_list = ["المخزن الرئيسي"]

tab1, tab2, tab3, tab4 = st.tabs(["📊 عرض وجرد", "📥 توريد", "📤 صرف", "🛠️ إدارة"])

# --- التبويب 1: العرض ---
with tab1:
    sel_wh = st.selectbox("اختر المخزن", wh_list)
    if not inv_df.empty:
        disp_df = inv_df[inv_df['warehouse'] == sel_wh]
        st.table(disp_df[['name', 'brand', 'quantity']])

# --- التبويب 2: التوريد ---
with tab2:
    with st.form("in_form", clear_on_submit=True):
        wh_name = st.text_input("المخزن", value=wh_list[0])
        n = st.text_input("الصنف")
        b = st.text_input("الماركة")
        q = st.number_input("الكمية", min_value=1)
        if st.form_submit_button("حفظ التوريد"):
            match = supabase.table("inventory").select("*").eq("name", n).eq("warehouse", wh_name).execute()
            if match.data:
                new_q = int(match.data[0]['quantity']) + q
                supabase.table("inventory").update({"quantity": new_q}).eq("id", match.data[0]['id']).execute()
            else:
                supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q, "warehouse": wh_name}).execute()
            
            supabase.table("movements").insert({"type": "إدخال", "name": n, "brand": b, "quantity": q, "warehouse": wh_name, "date": datetime.now().isoformat()}).execute()
            send_telegram(f"📥 توريد: {n} لمخزن {wh_name}")
            st.success("تم الحفظ!")
            st.rerun()

# --- التبويب 3: الصرف ---
with tab3:
    if not inv_df.empty:
        with st.form("out_form"):
            wh_out = st.selectbox("اصرف من", wh_list)
            items = inv_df[inv_df['warehouse'] == wh_out]
            if not items.empty:
                n_o = st.selectbox("الصنف", items['name'].unique())
                q_o = st.number_input("الكمية", min_value=1)
                dst = st.text_input("المستلم")
                if st.form_submit_button("تأكيد"):
                    row = items[items['name']==n_o].iloc[0]
                    if row['quantity'] >= q_o:
                        supabase.table("inventory").update({"quantity": int(row['quantity'] - q_o)}).eq("id", row['id']).execute()
                        supabase.table("movements").insert({"type": "إخراج", "name": n_o, "brand": row['brand'], "quantity": q_o, "warehouse": wh_out, "dest": dst, "date": datetime.now().isoformat()}).execute()
                        st.success("تم الصرف")
                        st.rerun()

# --- التبويب 4: الإدارة ---
with tab4:
    if st.text_input("كلمة السر", type="password") == ADMIN_PASSWORD:
        if not inv_df.empty:
            item_manage = st.selectbox("الصنف للإدارة", inv_df.apply(lambda x: f"{x['name']} | {x['warehouse']}", axis=1))
            idx = inv_df.index[inv_df.apply(lambda x: f"{x['name']} | {x['warehouse']}", axis=1) == item_manage][0]
            item = inv_df.iloc[idx]
            if st.button("حذف نهائي ❌"):
                supabase.table("inventory").delete().eq("id", item['id']).execute()
                st.rerun()