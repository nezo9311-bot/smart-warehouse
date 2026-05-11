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

@st.cache_resource
def init_supabase():
    url = SUPABASE_URL.strip().replace("/rest/v1/", "")
    if url.endswith("/"): url = url[:-1]
    return create_client(url, SUPABASE_KEY)

supabase: Client = init_supabase()

def get_data(table):
    try:
        res = supabase.table(table).select("*").execute()
        if not res.data:
            return pd.DataFrame()
        
        df = pd.DataFrame(res.data)
        
        # --- تنظيف البيانات فور جلبها ---
        if not df.empty and 'warehouse' in df.columns:
            # تحويل العمود لنصوص وحذف الفراغات
            df['warehouse'] = df['warehouse'].fillna('unknown').astype(str)
            # حذف أي صفوف تحمل قيم "غير معرفة" أو فارغة
            df = df[~df['warehouse'].lower().isin(['nan', 'none', 'null', '', 'unknown'])]
        
        return df
    except:
        return pd.DataFrame()

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except: pass

# =========================
# 2. بناء قائمة المخازن
# =========================
inv_df = get_data("inventory")
default_warehouses = ["مخزن البخاري", "مخزن الجديد"]

# استخلاص الأسماء بأمان تام
if not inv_df.empty:
    db_whs = inv_df['warehouse'].unique().tolist()
    # دمج القائمة الافتراضية مع ما في القاعدة والترتيب
    wh_list = sorted(list(set(default_warehouses + db_whs)))
else:
    wh_list = default_warehouses

# =========================
# 3. واجهة المستخدم
# =========================
st.sidebar.title("🏢 مستودعات النذير")

tab1, tab2, tab3, tab4 = st.tabs(["📊 جرد المخازن", "📥 توريد", "📤 صرف", "⚙️ إدارة"])

# --- التبويب 1: الجرد ---
with tab1:
    sel_wh = st.selectbox("اختر المخزن", wh_list)
    if not inv_df.empty:
        disp = inv_df[inv_df['warehouse'] == sel_wh]
        if not disp.empty:
            st.table(disp[['name', 'brand', 'quantity']])
        else:
            st.info(f"المخزن {sel_wh} لا يحتوي على بضائع.")

# --- التبويب 2: التوريد ---
with tab2:
    st.subheader("إضافة بضاعة")
    with st.form("in_form", clear_on_submit=True):
        t_wh = st.selectbox("إلى مخزن:", wh_list)
        n = st.text_input("اسم الصنف")
        b = st.text_input("الماركة")
        q = st.number_input("الكمية الموردة", min_value=1)
        
        if st.form_submit_button("حفظ التوريد ✅"):
            if n and b:
                # البحث عن تطابق (اسم + ماركة + مخزن)
                match = supabase.table("inventory").select("*")\
                    .eq("name", n).eq("brand", b).eq("warehouse", t_wh).execute()
                
                if match.data:
                    new_q = int(match.data[0]['quantity'] + q)
                    supabase.table("inventory").update({"quantity": new_q}).eq("id", match.data[0]['id']).execute()
                else:
                    supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q, "warehouse": t_wh}).execute()
                
                send_telegram(f"📥 توريد: {n} ({b}) لـ {t_wh}")
                st.success(f"تم الحفظ!")
                st.rerun()

# --- التبويب 3: الصرف ---
with tab3:
    st.subheader("سحب بضاعة")
    if not inv_df.empty:
        source_wh = st.selectbox("اصرف من:", wh_list)
        items = inv_df[(inv_df['warehouse'] == source_wh) & (inv_df['quantity'] > 0)]
        
        if not items.empty:
            with st.form("out_form"):
                item_options = items.apply(lambda x: f"{x['name']} ({x['brand']})", axis=1).tolist()
                sel_item_full = st.selectbox("اختر الصنف والماركة", item_options)
                q_o = st.number_input("الكمية", min_value=1)
                dst = st.text_input("الجهة المستلمة")
                
                if st.form_submit_button("تأكيد الصرف"):
                    sel_idx = item_options.index(sel_item_full)
                    row = items.iloc[sel_idx]
                    if row['quantity'] >= q_o:
                        supabase.table("inventory").update({"quantity": int(row['quantity'] - q_o)}).eq("id", row['id']).execute()
                        send_telegram(f"📤 صرف: {row['name']} ({row['brand']}) من {source_wh}")
                        st.success("تم الصرف")
                        st.rerun()
        else: st.warning("المخزن فارغ.")

# --- التبويب 4: الإدارة ---
with tab4:
    st.subheader("🛠️ الإدارة")
    if st.text_input("كلمة السر", type="password") == ADMIN_PASSWORD:
        if not inv_df.empty:
            item_manage = st.selectbox("اختر صنفاً للحذف", 
                                      inv_df.apply(lambda x: f"{x['name']} | {x['brand']} | {x['warehouse']}", axis=1))
            idx = inv_df.index[inv_df.apply(lambda x: f"{x['name']} | {x['brand']} | {x['warehouse']}", axis=1) == item_manage][0]
            if st.button("حذف نهائي ❌"):
                supabase.table("inventory").delete().eq("id", inv_df.iloc[idx]['id']).execute()
                st.rerun()