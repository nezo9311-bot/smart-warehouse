import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests
import json
import os
import google.generativeai as genai

# =========================
# الإعدادات الأساسية
# =========================
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"
GEMINI_API_KEY = "AIzaSyC11sWBSRyYut0SVzLxYGADh2mEk2HxeVg"

st.set_page_config(page_title="نظام النذير الذكي - Google Sheets", layout="wide")

# إعداد AI
genai.configure(api_key=GEMINI_API_KEY)

# =========================
# Google Sheets اتصال آمن
# =========================
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # محاولة القراءة من المتغير الذي أنشأته GOOGLE_SHEETS_CREDS
    creds_json = os.getenv("GOOGLE_SHEETS_CREDS")
    
    if creds_json:
        # إذا كان التطبيق يعمل على الرابط (Render/Streamlit Cloud)
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_dict(creds_dict, scope)
    else:
        # إذا كنت تعمل على جهازك الشخصي وتملك ملف creds.json
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
        except:
            st.error("خطأ: لم يتم العثور على متغير GOOGLE_SHEETS_CREDS أو ملف creds.json")
            st.stop()
            
    return gspread.authorize(creds)

client = get_gspread_client()

# =========================
# وظائف مساعدة
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
        # تأكد من مشاركة الملف مع بريدك الشخصي يدوياً من جوجل شيت إذا لزم الأمر
    
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
# واجهة التطبيق الرئيسية
# =========================
st.sidebar.title("🏢 إدارة المخازن الذكية")
warehouse_name = st.sidebar.text_input("اسم ملف Google Sheet", value="Smart_Warehouse_Data")

if not warehouse_name:
    st.info("الرجاء كتابة اسم المخزن في القائمة الجانبية للبدء")
    st.stop()

# تحميل أوراق العمل
ws_inv = get_worksheet(warehouse_name, "inventory", ["name", "brand", "quantity"])
ws_mov = get_worksheet(warehouse_name, "movements", ["type", "name", "brand", "quantity", "dest", "date"])

inv_df = load_data(ws_inv)
mov_df = load_data(ws_mov)

tab1, tab2, tab3, tab4 = st.tabs(["📥 توريد بضاعة", "📤 صرف مخزني", "📦 جرد وتحليل", "🤖 المستشار الذكي"])

# --- تبويب التوريد ---
with tab1:
    st.subheader("إضافة بضاعة جديدة للمخزن")
    with st.form("in_form", clear_on_submit=True):
        name = st.text_input("اسم الصنف (مثلاً: سكر)")
        brand = st.text_input("الماركة (مثلاً: كنانة)")
        qty = st.number_input("الكمية", min_value=1, step=1)
        submit = st.form_submit_button("حفظ التوريد")
        
        if submit and name:
            # تحديث المخزون
            mask = (inv_df['name'] == name) & (inv_df['brand'] == brand)
            if mask.any():
                new_qty = int(inv_df.loc[mask, 'quantity'].values[0]) + qty
                # تحديث في جوجل شيت (نبحث عن السطر)
                cell = ws_inv.find(name) # تبسيط للبحث
                ws_inv.update_cell(cell.row, 3, new_qty)
            else:
                ws_inv.append_row([name, brand, qty])
            
            # تسجيل الحركة
            ws_mov.append_row(["إدخال", name, brand, qty, "", str(datetime.now())])
            send_telegram(f"📥 توريد جديد: {name} - {qty}")
            st.success("تم الحفظ في Google Sheets وإرسال إشعار تليجرام")
            st.rerun()

# --- تبويب الصرف ---
with tab2:
    st.subheader("صرف بضاعة من المخزن")
    if inv_df.empty:
        st.warning("المخزن فارغ حالياً")
    else:
        with st.form("out_form", clear_on_submit=True):
            options = inv_df['name'].unique()
            name_select = st.selectbox("اختر الصنف", options)
            brand_select = st.selectbox("الماركة", inv_df[inv_df['name']==name_select]['brand'])
            qty_out = st.number_input("الكمية المراد صرفها", min_value=1)
            dest = st.text_input("الجهة المستلمة")
            submit_out = st.form_submit_button("تنفيذ الصرف")
            
            if submit_out:
                current_qty = inv_df[(inv_df['name']==name_select) & (inv_df['brand']==brand_select)]['quantity'].values[0]
                if current_qty >= qty_out:
                    new_qty = int(current_qty - qty_out)
                    # تحديث شيت المخزون
                    cell = ws_inv.find(name_select)
                    ws_inv.update_cell(cell.row, 3, new_qty)
                    # تسجيل حركة الصرف
                    ws_mov.append_row(["إخراج", name_select, brand_select, qty_out, dest, str(datetime.now())])
                    send_telegram(f"📤 صرف مخزني: {name_select} إلى {dest} (كمية: {qty_out})")
                    st.warning("تم الصرف وتحديث البيانات")
                    st.rerun()
                else:
                    st.error(f"الكمية غير كافية! المتوفر هو {current_qty} فقط")

# --- تبويب الجرد ---
with tab3:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📦 الجرد الحالي")
        st.dataframe(inv_df, use_container_width=True)
    with col2:
        st.subheader("📜 آخر العمليات")
        st.dataframe(mov_df.tail(10), use_container_width=True)

# --- تبويب المستشار الذكي ---
with tab4:
    st.subheader("🤖 تحليل السوق والذكاء الاصطناعي")
    if st.button("اطلب نصيحة الخبير (AI)"):
        if inv_df.empty:
            st.error("أدخل بعض البيانات أولاً ليتمكن الذكاء الاصطناعي من تحليلها")
        else:
            with st.spinner("جاري التواصل مع Gemini AI..."):
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"هذه بيانات مخزني الحالية: {inv_df.to_string()}. بناءً على السوق الحالي، ما هي نصيحتك لي كتاجر؟ ركز على الأسعار وتوقيت البيع."
                response = model.generate_content(prompt)
                st.write(response.text)
                send_telegram(f"💡 نصيحة AI للنذير:\n{response.text[:200]}...")
