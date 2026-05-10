import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import requests
import json
import os
import google.generativeai as genai

# =========================
# الإعدادات
# =========================
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"
GEMINI_API_KEY = "AIzaSyC11sWBSRyYut0SVzLxYGADh2mEk2HxeVg"
ADMIN_PASSWORD = "123"

st.set_page_config(page_title="نظام النذير الذكي v4.0", layout="wide")
genai.configure(api_key=GEMINI_API_KEY)

# =========================
# الاتصال المصلح بـ Google Sheets
# =========================
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    creds_json = os.getenv("GOOGLE_SHEETS_CREDS")
    
    if not creds_json:
        st.error("❗ المتغير GOOGLE_SHEETS_CREDS غير موجود في إعدادات Render")
        st.stop()

    try:
        # تحويل النص إلى قاموس
        info = json.loads(creds_json, strict=False)
        
        # إصلاح المفتاح الخاص: استبدال الأسطر المكسورة لضمان قبول JWT
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
            # ضمان عدم وجود مسافات زائدة حول المفتاح
            info["private_key"] = info["private_key"].strip()
        
        creds = Credentials.from_service_account_info(info, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"❌ خطأ في معالجة المفاتيح: {e}")
        st.stop()

# تفعيل العميل
client = get_gspread_client()

# =========================
# الوظائف المساعدة
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
        # إذا لم يجد الملف، يحاول إنشاءه
        sh = client.create(sheet_name)
        # هام: يجب أن تذهب لجوجل شيت وتشارك الملف مع الايميل:
        # ware-382@atomic-vault-483410-b4.iam.gserviceaccount.com
    
    try:
        ws = sh.worksheet(ws_title)
    except:
        ws = sh.add_worksheet(title=ws_title, rows="1000", cols=str(len(cols)))
        ws.insert_row(cols, 1)
    return ws

# =========================
# واجهة التطبيق
# =========================
st.sidebar.title("🏢 مستودع النذير")
# اسم الملف الذي سيظهر في جوجل شيت الخاص بك
sheet_file_name = st.sidebar.text_input("اسم الملف في Google Sheets", value="Nazeer_Inventory_2026")

if sheet_file_name:
    try:
        ws_inv = get_worksheet(sheet_file_name, "inventory", ["name", "brand", "quantity"])
        ws_mov = get_worksheet(sheet_file_name, "movements", ["type", "name", "brand", "quantity", "dest", "date"])

        # جلب البيانات للعرض
        inv_data = ws_inv.get_all_records()
        inv_df = pd.DataFrame(inv_data) if inv_data else pd.DataFrame(columns=["name", "brand", "quantity"])
        
        mov_data = ws_mov.get_all_records()
        mov_df = pd.DataFrame(mov_data) if mov_data else pd.DataFrame(columns=["type", "name", "brand", "quantity", "dest", "date"])

        t1, t2, t3, t4 = st.tabs(["📥 توريد", "📤 صرف", "📊 جرد", "🤖 AI"])

        with t1:
            with st.form("in"):
                n, b = st.text_input("الصنف"), st.text_input("الماركة")
                q = st.number_input("الكمية", 1)
                if st.form_submit_button("حفظ"):
                    mask = (inv_df['name'] == n) & (inv_df['brand'] == b)
                    if mask.any():
                        idx = inv_df.index[mask][0] + 2
                        new_q = int(inv_df.loc[mask, 'quantity'].values[0]) + q
                        ws_inv.update_cell(idx, 3, new_q)
                    else:
                        ws_inv.append_row([n, b, q])
                    ws_mov.append_row(["إدخال", n, b, q, "", str(datetime.now())])
                    send_telegram(f"📥 توريد: {n} ({q})")
                    st.success("تم التحديث")
                    st.rerun()

        with t2:
            if not inv_df.empty:
                with st.form("out"):
                    n_s = st.selectbox("الصنف", inv_df['name'].unique())
                    b_s = st.selectbox("الماركة", inv_df[inv_df['name']==n_s]['brand'])
                    q_s = st.number_input("الكمية", 1)
                    dst = st.text_input("الجهة المستلمة")
                    if st.form_submit_button("تنفيذ"):
                        curr = inv_df[(inv_df['name']==n_s) & (inv_df['brand']==b_s)]['quantity'].values[0]
                        if curr >= q_s:
                            idx = inv_df.index[(inv_df['name']==n_s) & (inv_df['brand']==b_s)][0] + 2
                            ws_inv.update_cell(idx, 3, int(curr - q_s))
                            ws_mov.append_row(["إخراج", n_s, b_s, q_s, dst, str(datetime.now())])
                            send_telegram(f"📤 صرف: {n_s} لـ {dst}")
                            st.success("تم الصرف")
                            st.rerun()
                        else: st.error("الكمية غير كافية")

        with t3:
            st.write("📦 المخزون الحالي")
            st.table(inv_df)

        with t4:
            if st.text_input("كلمة السر", type="password") == ADMIN_PASSWORD:
                if st.button("تحليل الذكاء الاصطناعي"):
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    res = model.generate_content(f"مخزني الحالي: {inv_df.to_string()}. أعطني نصيحة تجارية.")
                    st.info(res.text)

    except Exception as e:
        st.error(f"حدث خطأ في الوصول للملف: {e}")
        st.info("تأكد من مشاركة ملف Google Sheet مع الايميل الموجود في ملفك!")
