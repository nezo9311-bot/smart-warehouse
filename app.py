import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import requests
import json
import os
import base64  # لإصلاح مشكلة تشفير المفاتيح
import google.generativeai as genai

# =========================
# 1. الإعدادات والربط
# =========================
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"
GEMINI_API_KEY = "AIzaSyC11sWBSRyYut0SVzLxYGADh2mEk2HxeVg"
ADMIN_PASSWORD = "123"

st.set_page_config(page_title="نظام النذير الذكي - النسخة الآمنة", layout="wide")
genai.configure(api_key=GEMINI_API_KEY)

# =========================
# 2. الاتصال بـ Google Sheets (حل مشكلة JWT)
# =========================
def get_gspread_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # جلب النص المشفر بـ Base64 من إعدادات Render
    encoded_creds = os.getenv("GOOGLE_SHEETS_CREDS")
    
    if encoded_creds:
        try:
            # فك التشفير لاسترجاع بيانات JSON الأصلية بشكل سليم
            decoded_creds = base64.b64decode(encoded_creds).decode('utf-8')
            info = json.loads(decoded_creds)
            
            # الاتصال الرسمي
            creds = Credentials.from_service_account_info(info, scopes=scope)
            return gspread.authorize(creds)
        except Exception as e:
            st.error(f"❌ خطأ في فك تشفير المفاتيح: {e}")
            st.stop()
    else:
        st.error("❗ لم يتم العثور على متغير GOOGLE_SHEETS_CREDS في Render")
        st.stop()

# تفعيل العميل
client = get_gspread_client()

# =========================
# 3. الوظائف المساعدة
# =========================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except: pass

def get_worksheet(sheet_name, ws_title, cols):
    try:
        sh = client.open(sheet_name)
    except:
        sh = client.create(sheet_name)
        # ملاحظة: يجب مشاركة الشيت يدوياً مع البريد الموجود في ملف الـ JSON
    
    try:
        ws = sh.worksheet(ws_title)
    except:
        ws = sh.add_worksheet(title=ws_title, rows="1000", cols=str(len(cols)))
        ws.append_row(cols)
    return ws

# =========================
# 4. واجهة التطبيق
# =========================
st.sidebar.title("🏢 مستودع النذير")
warehouse_name = st.sidebar.text_input("اسم ملف البيانات", value="Nazeer_Warehouse_Data")

if not warehouse_name:
    st.info("اكتب اسم الملف للبدء")
    st.stop()

# تحميل الجداول من جوجل شيت
ws_inv = get_worksheet(warehouse_name, "inventory", ["name", "brand", "quantity"])
ws_mov = get_worksheet(warehouse_name, "movements", ["type", "name", "brand", "quantity", "dest", "date"])

inv_df = pd.DataFrame(ws_inv.get_all_records())
mov_df = pd.DataFrame(ws_mov.get_all_records())

tab1, tab2, tab3, tab4 = st.tabs(["📥 توريد", "📤 صرف", "📊 جرد", "🤖 مستشار AI"])

# --- توريد بضاعة ---
with tab1:
    with st.form("in"):
        n = st.text_input("اسم الصنف")
        b = st.text_input("الماركة")
        q = st.number_input("الكمية", 1)
        if st.form_submit_button("حفظ التوريد"):
            mask = (inv_df['name'] == n) & (inv_df['brand'] == b)
            if mask.any():
                idx = inv_df.index[mask][0] + 2
                new_q = int(inv_df.loc[mask, 'quantity'].values[0]) + q
                ws_inv.update_cell(idx, 3, new_q)
            else:
                ws_inv.append_row([n, b, q])
            ws_mov.append_row(["إدخال", n, b, q, "", str(datetime.now())])
            send_telegram(f"📥 تم توريد {q} من {n} ({b})")
            st.success("تم الحفظ!")
            st.rerun()

# --- صرف بضاعة ---
with tab2:
    if not inv_df.empty:
        with st.form("out"):
            n_s = st.selectbox("الصنف", inv_df['name'].unique())
            b_s = st.selectbox("الماركة", inv_df[inv_df['name']==n_s]['brand'])
            q_s = st.number_input("الكمية", 1)
            dest = st.text_input("الجهة المستلمة")
            if st.form_submit_button("تنفيذ الصرف"):
                curr = inv_df[(inv_df['name']==n_s) & (inv_df['brand']==b_s)]['quantity'].values[0]
                if curr >= q_s:
                    idx = inv_df.index[(inv_df['name']==n_s) & (inv_df['brand']==b_s)][0] + 2
                    ws_inv.update_cell(idx, 3, int(curr - q_s))
                    ws_mov.append_row(["إخراج", n_s, b_s, q_s, dest, str(datetime.now())])
                    send_telegram(f"📤 صرف بضاعة: {n_s} إلى {dest}")
                    st.success("تم الصرف")
                    st.rerun()
                else: st.error("الكمية غير كافية")

# --- جرد البيانات ---
with tab3:
    st.subheader("📦 المخزون الحالي")
    st.dataframe(inv_df, use_container_width=True)
    st.subheader("📜 سجل العمليات")
    st.dataframe(mov_df.tail(15), use_container_width=True)

# --- المستشار الذكي ---
with tab4:
    st.subheader("🤖 نصيحة الذكاء الاصطناعي")
    if st.text_input("كلمة سر الإدارة", type="password") == ADMIN_PASSWORD:
        if st.button("تحليل المخزون"):
            with st.spinner("جاري التحليل..."):
                model = genai.GenerativeModel('gemini-1.5-flash')
                res = model.generate_content(f"أنا تاجر، مخزني هو: {inv_df.to_string()}. الدولار متقلب، ماذا تنصحني؟")
                st.markdown(res.text)
                send_telegram(f"💡 نصيحة AI: {res.text[:100]}...")
