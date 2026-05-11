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
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: return pd.DataFrame()

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

if not inv_df.empty and 'warehouse' in inv_df.columns:
    temp_series = inv_df['warehouse'].astype(str)
    db_whs = [x for x in temp_series.unique() if x.lower() not in ['nan', 'none', '', 'null']]
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
        inv_df['warehouse'] = inv_df['warehouse'].astype(str)
        disp = inv_df[inv_df['warehouse'] == sel_wh]
        if not disp.empty:
            # عرض الاسم والماركة والكمية لتمييزهم
            st.table(disp[['name', 'brand', 'quantity']])
        else:
            st.info(f"المخزن {sel_wh} لا يحتوي على بضائع حالياً.")

# --- التبويب 2: التوريد (التعديل الجذري هنا) ---
with tab2:
    st.subheader("إضافة بضاعة")
    with st.form("in_form", clear_on_submit=True):
        t_wh = st.selectbox("إلى مخزن:", wh_list)
        n = st.text_input("اسم الصنف (مثل: سكر)")
        b = st.text_input("الماركة (مثل: كنانة)")
        q = st.number_input("الكمية الموردة", min_value=1)
        
        if st.form_submit_button("حفظ التوريد ✅"):
            if n and b:
                # التحقق بوجود الاسم والماركة والمخزن معاً
                match = supabase.table("inventory").select("*")\
                    .eq("name", n)\
                    .eq("brand", b)\
                    .eq("warehouse", t_wh).execute()
                
                if match.data:
                    # إذا وجد نفس الاسم ونفس الماركة في نفس المخزن -> نحدث الكمية
                    new_q = int(match.data[0]['quantity'] + q)
                    supabase.table("inventory").update({"quantity": new_q}).eq("id", match.data[0]['id']).execute()
                else:
                    # إذا اختلف الاسم أو الماركة أو المخزن -> ننشئ سجلاً جديداً
                    supabase.table("inventory").insert({
                        "name": n, 
                        "brand": b, 
                        "quantity": q, 
                        "warehouse": t_wh
                    }).execute()
                
                send_telegram(f"📥 توريد: {n} ({b}) لـ {t_wh}")
                st.success(f"تم حفظ {n} ماركة {b} بنجاح!")
                st.rerun()

# --- التبويب 3: الصرف ---
with tab3:
    st.subheader("سحب بضاعة")
    if not inv_df.empty:
        source_wh = st.selectbox("اصرف من:", wh_list)
        inv_df['warehouse'] = inv_df['warehouse'].astype(str)
        items = inv_df[(inv_df['warehouse'] == source_wh) & (inv_df['quantity'] > 0)]
        
        if not items.empty:
            with st.form("out_form"):
                # اختيار الصنف + الماركة معاً لضمان الدقة في الصرف
                item_options = items.apply(lambda x: f"{x['name']} ({x['brand']})", axis=1).tolist()
                sel_item_full = st.selectbox("اختر الصنف والماركة", item_options)
                
                q_o = st.number_input("الكمية", min_value=1)
                dst = st.text_input("الجهة المستلمة")
                
                if st.form_submit_button("تأكيد الصرف"):
                    # استخراج الاسم والماركة من الخيار المختار
                    sel_idx = item_options.index(sel_item_full)
                    row = items.iloc[sel_idx]
                    
                    if row['quantity'] >= q_o:
                        supabase.table("inventory").update({"quantity": int(row['quantity'] - q_o)}).eq("id", row['id']).execute()
                        send_telegram(f"📤 صرف: {row['name']} ({row['brand']}) من {source_wh}")
                        st.success("تم الصرف بنجاح")
                        st.rerun()
                    else:
                        st.error("الكمية غير كافية!")
        else:
            st.warning("لا توجد بضاعة في هذا المخزن.")

# --- التبويب 4: الإدارة ---
with tab4:
    st.subheader("🛠️ الإدارة")
    if st.text_input("كلمة السر", type="password") == ADMIN_PASSWORD:
        if not inv_df.empty:
            inv_df['warehouse'] = inv_df['warehouse'].astype(str)
            item_manage = st.selectbox("اختر صنفاً (الاسم والماركة والمخزن)", 
                                      inv_df.apply(lambda x: f"{x['name']} | {x['brand']} | {x['warehouse']}", axis=1))
            
            idx = inv_df.index[inv_df.apply(lambda x: f"{x['name']} | {x['brand']} | {x['warehouse']}", axis=1) == item_manage][0]
            if st.button("حذف نهائي ❌"):
                supabase.table("inventory").delete().eq("id", inv_df.iloc[idx]['id']).execute()
                st.success("تم الحذف")
                st.rerun()