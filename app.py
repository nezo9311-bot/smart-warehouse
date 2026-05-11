import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import requests
import os
import google.generativeai as genai

# =========================
# 1. الإعدادات والربط
# =========================
# جلب الروابط من إعدادات Render
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# إعدادات التليجرام والذكاء الاصطناعي
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"
GEMINI_API_KEY = "AIzaSyC11sWBSRyYut0SVzLxYGADh2mEk2HxeVg"
ADMIN_PASSWORD = "123"

st.set_page_config(page_title="نظام النذير - النسخة الذكية", layout="wide")
genai.configure(api_key=GEMINI_API_KEY)

# الاتصال بـ Supabase
@st.cache_resource
def init_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("❗ تأكد من إضافة SUPABASE_URL و SUPABASE_KEY في إعدادات Render")
        st.stop()
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

def get_inventory_df():
    # جلب البيانات من جدول inventory
    res = supabase.table("inventory").select("*").execute()
    if res.data:
        return pd.DataFrame(res.data)
    return pd.DataFrame(columns=["name", "brand", "quantity"])

def get_movements_df():
    # جلب آخر 20 حركة من جدول movements
    res = supabase.table("movements").select("*").order("date", desc=True).limit(20).execute()
    if res.data:
        return pd.DataFrame(res.data)
    return pd.DataFrame(columns=["type", "name", "brand", "quantity", "dest", "date"])

# =========================
# 3. واجهة التطبيق
# =========================
st.sidebar.title("🏢 مستودع النذير")
st.sidebar.success("متصل بـ Supabase ✅")

# تحميل البيانات الحالية
inv_df = get_inventory_df()
mov_df = get_movements_df()

tab1, tab2, tab3, tab4 = st.tabs(["📥 توريد", "📤 صرف", "📊 جرد", "🤖 مستشار AI"])

# --- توريد بضاعة ---
with tab1:
    st.subheader("إضافة بضاعة للمستودع")
    with st.form("in_form", clear_on_submit=True):
        n = st.text_input("اسم الصنف").strip()
        b = st.text_input("الماركة").strip()
        q = st.number_input("الكمية المضافة", min_value=1, step=1)
        
        if st.form_submit_button("حفظ التوريد"):
            if n and b:
                # التأكد إذا كان الصنف موجوداً لزيادة الكمية أو إنشائه
                match = supabase.table("inventory").select("*").eq("name", n).eq("brand", b).execute()
                
                if match.data:
                    new_q = int(match.data[0]['quantity']) + q
                    supabase.table("inventory").update({"quantity": new_q}).eq("name", n).eq("brand", b).execute()
                else:
                    supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q}).execute()
                
                # تسجيل الحركة
                supabase.table("movements").insert({
                    "type": "إدخال", "name": n, "brand": b, "quantity": q, 
                    "date": datetime.now().isoformat()
                }).execute()
                
                send_telegram(f"📥 تم توريد: {n} ({b})\n🔢 الكمية: {q}")
                st.success("تم التحديث بنجاح!")
                st.rerun()

# --- صرف بضاعة ---
with tab2:
    st.subheader("صرف بضاعة إلى جهة")
    if inv_df.empty:
        st.info("المخزن فارغ حالياً.")
    else:
        with st.form("out_form", clear_on_submit=True):
            # اختيار الصنف بناءً على الموجود في المخزن
            n_s = st.selectbox("الصنف", inv_df['name'].unique())
            b_s = st.selectbox("الماركة", inv_df[inv_df['name']==n_s]['brand'])
            q_out = st.number_input("الكمية المراد صرفها", min_value=1)
            dst = st.text_input("الجهة المستلمة")
            
            if st.form_submit_button("تنفيذ الصرف"):
                curr_q = inv_df[(inv_df['name']==n_s) & (inv_df['brand']==b_s)]['quantity'].values[0]
                
                if curr_q >= q_out:
                    new_val = int(curr_q - q_out)
                    supabase.table("inventory").update({"quantity": new_val}).eq("name", n_s).eq("brand", b_s).execute()
                    
                    # تسجيل حركة الصرف
                    supabase.table("movements").insert({
                        "type": "إخراج", "name": n_s, "brand": b_s, "quantity": q_out, 
                        "dest": dst, "date": datetime.now().isoformat()
                    }).execute()
                    
                    send_telegram(f"📤 صرف بضاعة لـ: {dst}\n📦 الصنف: {n_s}\n🔢 الكمية: {q_out}")
                    st.success("تمت عملية الصرف!")
                    st.rerun()
                else:
                    st.error(f"الكمية غير كافية! المتوفر: {curr_q}")

# --- سجل الجرد ---
with tab3:
    st.subheader("📦 حالة المخزون الحالي")
    st.dataframe(inv_df, use_container_width=True)
    
    st.subheader("📜 آخر الحركات")
    st.dataframe(mov_df, use_container_width=True)

# --- مستشار AI ---
with tab4:
    st.subheader("🤖 استشارة الذكاء الاصطناعي")
    if st.text_input("كلمة السر", type="password") == ADMIN_PASSWORD:
        if st.button("تحليل المخزون"):
            with st.spinner("جاري التحليل..."):
                model = genai.GenerativeModel('gemini-1.5-flash')
                data_summary = inv_df.to_string(index=False)
                res = model.generate_content(f"بصفتك خبير تجاري، هذا مخزني: {data_summary}. ما هي نصيحتك لزيادة الربح وإدارة المخزون؟")
                st.markdown(res.text)