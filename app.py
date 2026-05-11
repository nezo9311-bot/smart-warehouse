import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import requests
import os
import google.generativeai as genai

# =========================
# 1. إعدادات الربط (من Render)
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"
GEMINI_API_KEY = "AIzaSyC11sWBSRyYut0SVzLxYGADh2mEk2HxeVg"
ADMIN_PASSWORD = "123"

st.set_page_config(page_title="نظام النذير - Supabase", layout="wide")
genai.configure(api_key=GEMINI_API_KEY)

# تهيئة الاتصال بـ Supabase
@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

# =========================
# 2. وظائف النظام
# =========================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except: pass

def get_inventory():
    response = supabase.table("inventory").select("*").execute()
    return pd.DataFrame(response.data)

# =========================
# 3. واجهة المستخدم
# =========================
st.sidebar.title("⚡ مستودع النذير (Supabase)")

inv_df = get_inventory()
if inv_df.empty: inv_df = pd.DataFrame(columns=["name", "brand", "quantity"])

tab1, tab2, tab3 = st.tabs(["📥 توريد", "📤 صرف", "📊 جرد"])

# --- التوريد ---
with tab1:
    with st.form("in"):
        n = st.text_input("الصنف")
        b = st.text_input("الماركة")
        q = st.number_input("الكمية", 1)
        if st.form_submit_button("حفظ"):
            # التحقق إذا كان الصنف موجوداً
            match = supabase.table("inventory").select("*").eq("name", n).eq("brand", b).execute()
            if match.data:
                new_q = match.data[0]['quantity'] + q
                supabase.table("inventory").update({"quantity": new_q}).eq("name", n).eq("brand", b).execute()
            else:
                supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q}).execute()
            
            # تسجيل الحركة
            supabase.table("movements").insert({
                "type": "إدخال", "name": n, "brand": b, "quantity": q, "date": datetime.now().isoformat()
            }).execute()
            
            send_telegram(f"📥 تم توريد {q} من {n}")
            st.success("تم الحفظ في قاعدة البيانات!")
            st.rerun()

# --- الصرف ---
with tab2:
    if not inv_df.empty:
        with st.form("out"):
            n_s = st.selectbox("الصنف", inv_df['name'].unique())
            b_s = st.selectbox("الماركة", inv_df[inv_df['name']==n_s]['brand'])
            q_out = st.number_input("الكمية", 1)
            dst = st.text_input("الجهة")
            if st.form_submit_button("صرف"):
                curr_q = inv_df[(inv_df['name']==n_s) & (inv_df['brand']==b_s)]['quantity'].values[0]
                if curr_q >= q_out:
                    supabase.table("inventory").update({"quantity": int(curr_q - q_out)}).eq("name", n_s).eq("brand", b_s).execute()
                    supabase.table("movements").insert({
                        "type": "إخراج", "name": n_s, "brand": b_s, "quantity": q_out, "dest": dst, "date": datetime.now().isoformat()
                    }).execute()
                    st.success("تم الصرف!")
                    st.rerun()
                else: st.error("الكمية غير كافية")

# --- الجرد ---
with tab3:
    st.dataframe(inv_df, use_container_width=True)