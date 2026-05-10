import streamlit as st
import pandas as pd
import gspread
# لاحظ السطر التالي، هذا هو البديل الجديد والمطلوب:
from google.oauth2.service_account import Credentials 
from datetime import datetime
import requests
import json
import os
import google.generativeai as genai
# =========================
# الإعدادات الأساسية (بياناتك)
# =========================
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"
GEMINI_API_KEY = "AIzaSyC11sWBSRyYut0SVzLxYGADh2mEk2HxeVg"
ADMIN_PASSWORD = "123"

st.set_page_config(page_title="نظام النذير الذكي v3.0", layout="wide")

# إعداد الذكاء الاصطناعي
genai.configure(api_key=GEMINI_API_KEY)

# =========================
# الاتصال بـ Google Sheets (المطور)
# =========================
def get_gspread_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # جلب المفاتيح من Render Environment Variable
    creds_json = os.getenv("GOOGLE_SHEETS_CREDS")
    
    if creds_json:
        try:
            info = json.loads(creds_json)
            # إصلاح مشكلة الأسطر الجديدة في المفتاح الخاص (حل خطأ JWT Signature)
            if "private_key" in info:
                info["private_key"] = info["private_key"].replace("\\n", "\n")
            
            creds = Credentials.from_service_account_info(info, scopes=scope)
            return gspread.authorize(creds)
        except Exception as e:
            st.error(f"خطأ في معالجة مفاتيح جوجل: {e}")
            st.stop()
    else:
        st.error("لم يتم العثور على متغير GOOGLE_SHEETS_CREDS. تأكد من إضافته في إعدادات Render.")
        st.stop()

# تفعيل الاتصال
client = get_gspread_client()

# =========================
# وظائف النظام المساعدة
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
    
    try:
        ws = sh.worksheet(ws_title)
    except:
        ws = sh.add_worksheet(title=ws_title, rows="1000", cols=str(len(cols)))
        ws.append_row(cols)
    return ws

def load_data(ws):
    data = ws.get_all_records()
    return pd.DataFrame(data)

# =========================
# واجهة المستخدم الرئيسية
# =========================
st.sidebar.title("🏢 مستودع النذير الذكي")
warehouse_name = st.sidebar.text_input("اسم ملف البيانات (Google Sheets)", value="My_Warehouse_2026")

if not warehouse_name:
    st.warning("يرجى إدخال اسم للمستودع في القائمة الجانبية.")
    st.stop()

# تحميل الجداول
ws_inv = get_worksheet(warehouse_name, "inventory", ["name", "brand", "quantity"])
ws_mov = get_worksheet(warehouse_name, "movements", ["type", "name", "brand", "quantity", "dest", "date"])

inv_df = load_data(ws_inv)
mov_df = load_data(ws_mov)

tab1, tab2, tab3, tab4 = st.tabs(["📥 توريد", "📤 صرف", "📊 جرد", "🤖 مستشار AI"])

# --- تبويب التوريد ---
with tab1:
    st.subheader("تسجيل دخول بضاعة")
    with st.form("in_form", clear_on_submit=True):
        name = st.text_input("اسم الصنف")
        brand = st.text_input("الماركة")
        qty = st.number_input("الكمية", min_value=1)
        if st.form_submit_button("حفظ العملية"):
            if name and brand:
                mask = (inv_df['name'] == name) & (inv_df['brand'] == brand)
                if mask.any():
                    row_idx = inv_df.index[mask][0] + 2 # +2 لأن جوجل يبدأ من 1 وهناك رأس للجدول
                    new_qty = int(inv_df.loc[mask, 'quantity'].values[0]) + qty
                    ws_inv.update_cell(row_idx, 3, new_qty)
                else:
                    ws_inv.append_row([name, brand, qty])
                
                ws_mov.append_row(["إدخال", name, brand, qty, "", str(datetime.now())])
                send_telegram(f"✅ توريد جديد: {name} ({brand}) - كمية: {qty}")
                st.success("تم الحفظ بنجاح!")
                st.rerun()

# --- تبويب الصرف ---
with tab2:
    st.subheader("تسجيل خروج بضاعة")
    if inv_df.empty:
        st.info("المخزن فارغ.")
    else:
        with st.form("out_form", clear_on_submit=True):
            name_sel = st.selectbox("الصنف", inv_df['name'].unique())
            brand_sel = st.selectbox("الماركة", inv_df[inv_df['name']==name_sel]['brand'])
            qty_out = st.number_input("الكمية", min_value=1)
            dest = st.text_input("الجهة المستلمة")
            if st.form_submit_button("تنفيذ الصرف"):
                curr_qty = inv_df[(inv_df['name']==name_sel) & (inv_df['brand']==brand_sel)]['quantity'].values[0]
                if curr_qty >= qty_out:
                    row_idx = inv_df.index[(inv_df['name']==name_sel) & (inv_df['brand']==brand_sel)][0] + 2
                    ws_inv.update_cell(row_idx, 3, int(curr_qty - qty_out))
                    ws_mov.append_row(["إخراج", name_sel, brand_sel, qty_out, dest, str(datetime.now())])
                    send_telegram(f"⚠️ صرف مخزني: {name_sel} إلى {dest} - كمية: {qty_out}")
                    st.success("تم التحديث!")
                    st.rerun()
                else:
                    st.error("الكمية غير كافية!")

# --- تبويب الجرد ---
with tab3:
    st.subheader("المخزون المتوفر حالياً")
    st.dataframe(inv_df, use_container_width=True)
    st.subheader("سجل الحركات الأخير")
    st.dataframe(mov_df.tail(20), use_container_width=True)

# --- تبويب الذكاء الاصطناعي ---
with tab4:
    st.subheader("التحليل الذكي (Gemini AI)")
    pw = st.text_input("أدخل كلمة سر الإدارة للتحليل", type="password")
    if pw == ADMIN_PASSWORD:
        if st.button("تحليل حالة السوق والمخزن"):
            with st.spinner("جاري التواصل مع الخبير الرقمي..."):
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    prompt = f"أنا تاجر في السودان، وهذا مخزني: {inv_df.to_string()}. أعطني نصيحة تجارية بخصوص الأسعار والدولار والسلع التي يجب أن أتمسك بها."
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
                    send_telegram(f"💡 نصيحة AI للنذير:\n{response.text[:200]}...")
                except Exception as e:
                    st.error(f"فشل التحليل: {e}")
