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

st.set_page_config(page_title="نظام النذير - المخازن المعتمدة", layout="wide")

@st.cache_resource
def init_supabase():
    if not SUPABASE_URL:
        st.error("خطأ: SUPABASE_URL غير موجود")
        st.stop()
    url = SUPABASE_URL.strip().replace("/rest/v1/", "")
    if url.endswith("/"): url = url[:-1]
    return create_client(url, SUPABASE_KEY)

supabase: Client = init_supabase()

# =========================
# 2. وظائف البيانات
# =========================
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

inv_df = get_data("inventory")

# إعداد قائمة المخازن (دمج المخازن الافتراضية مع المخازن الموجودة في القاعدة)
default_warehouses = ["مخزن البخاري", "مخزن الجديد"]
if not inv_df.empty and 'warehouse' in inv_df.columns:
    db_warehouses = inv_df['warehouse'].unique().tolist()
    # دمج القائمتين وحذف التكرار
    wh_list = sorted(list(set(default_warehouses + db_warehouses)))
else:
    wh_list = default_warehouses

tab1, tab2, tab3, tab4 = st.tabs(["📊 جرد المخازن", "📥 توريد بضاعة", "📤 صرف بضاعة", "⚙️ إدارة النظام"])

# --- التبويب 1: عرض المخزون ---
with tab1:
    sel_wh = st.selectbox("اختر المخزن للمعاينة", wh_list)
    st.info(f"عرض محتويات: {sel_wh}")
    if not inv_df.empty:
        disp_df = inv_df[inv_df['warehouse'] == sel_wh]
        # تصفية الأصناف التي كميتها 0 إذا رغبت، أو عرض الكل
        if not disp_df.empty:
            st.table(disp_df[['name', 'brand', 'quantity']])
        else:
            st.warning("هذا المخزن فارغ حالياً.")
    else:
        st.info("لا توجد بيانات مسجلة في أي مخزن بعد.")

# --- التبويب 2: توريد بضاعة ---
with tab2:
    st.subheader(f"إضافة بضاعة")
    with st.form("in_form", clear_on_submit=True):
        target_wh = st.selectbox("إلى أي مخزن؟", wh_list)
        n = st.text_input("اسم الصنف")
        b = st.text_input("الماركة")
        q = st.number_input("الكمية الموردة", min_value=1)
        
        if st.form_submit_button("اعتماد التوريد ✅"):
            if n:
                # التحقق من وجود الصنف في المخزن المحدد
                match = supabase.table("inventory").select("*").eq("name", n).eq("warehouse", target_wh).execute()
                if match.data:
                    new_q = int(match.data[0]['quantity']) + q
                    supabase.table("inventory").update({"quantity": new_q}).eq("id", match.data[0]['id']).execute()
                else:
                    supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q, "warehouse": target_wh}).execute()
                
                # إرسال تلجرام
                send_telegram(f"📥 توريد جديد\n📦 الصنف: {n}\n🏢 المخزن: {target_wh}\n🔢 الكمية: {q}")
                st.success(f"تمت إضافة {q} من {n} إلى {target_wh}")
                st.rerun()

# --- التبويب 3: صرف بضاعة ---
with tab3:
    st.subheader("سحب بضاعة من مخزن")
    source_wh = st.selectbox("اصرف من:", wh_list)
    wh_items = inv_df[inv_df['warehouse'] == source_wh] if not inv_df.empty else pd.DataFrame()
    
    if not wh_items.empty and not wh_items[wh_items['quantity'] > 0].empty:
        with st.form("out_form"):
            active_items = wh_items[wh_items['quantity'] > 0]
            item_n = st.selectbox("اختر الصنف المتوفر", active_items['name'].unique())
            q_o = st.number_input("الكمية المراد صرفها", min_value=1)
            dst = st.text_input("الجهة المستلمة")
            
            if st.form_submit_button("تأكيد الصرف 📤"):
                row = wh_items[wh_items['name'] == item_n].iloc[0]
                if row['quantity'] >= q_o:
                    new_val = int(row['quantity'] - q_o)
                    supabase.table("inventory").update({"quantity": new_val}).eq("id", row['id']).execute()
                    send_telegram(f"📤 صرف بضاعة\n📦 الصنف: {item_n}\n🏢 من: {source_wh}\n🚚 إلى: {dst}\n🔢 الكمية: {q_o}")
                    st.success("تم الصرف وتحديث المخزن")
                    st.rerun()
                else:
                    st.error("عفواً! الكمية المطلوبة أكبر من المتوفر.")
    else:
        st.warning("لا توجد بضاعة قابلة للصرف في هذا المخزن.")

# --- التبويب 4: إدارة وحذف ---
with tab4:
    st.subheader("🛠️ لوحة التحكم")
    pwd = st.text_input("كلمة مرور المدير", type="password")
    
    if pwd == ADMIN_PASSWORD:
        col1, col2 = st.columns(2)
        with col1:
            st.write("➕ **إضافة مخزن إضافي**")
            new_wh = st.text_input("اسم المخزن الجديد")
            if st.button("إنشاء"):
                if new_wh:
                    # إضافة سجل صفري لتعريف المخزن
                    supabase.table("inventory").insert({"name": "تهيئة", "brand": "-", "quantity": 0, "warehouse": new_wh}).execute()
                    st.rerun()
        
        with col2:
            st.write("🗑️ **حذف صنف**")
            if not inv_df.empty:
                del_item = st.selectbox("اختر صنف لحذفه نهائياً", 
                                       inv_df.apply(lambda x: f"{x['name']} ({x['warehouse']})", axis=1))
                idx = inv_df.index[inv_df.apply(lambda x: f"{x['name']} ({x['warehouse']})", axis=1) == del_item][0]
                if st.button("حذف نهائي ❌"):
                    supabase.table("inventory").delete().eq("id", inv_df.iloc[idx]['id']).execute()
                    st.rerun()