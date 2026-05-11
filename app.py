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

st.set_page_config(page_title="نظام النذير للمخازن المتعددة", layout="wide")

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

# إدارة قائمة المخازن
if not inv_df.empty and 'warehouse' in inv_df.columns:
    wh_list = sorted(inv_df['warehouse'].unique().tolist())
else:
    wh_list = ["المخزن الرئيسي"]

tab1, tab2, tab3, tab4 = st.tabs(["📊 جرد المخازن", "📥 توريد", "📤 صرف", "⚙️ إعدادات المخازن"])

# --- التبويب 1: عرض المخزون حسب المخزن ---
with tab1:
    sel_wh = st.selectbox("اختر المخزن المراد معاينته", wh_list)
    if not inv_df.empty:
        disp_df = inv_df[inv_df['warehouse'] == sel_wh]
        if not disp_df.empty:
            st.table(disp_df[['name', 'brand', 'quantity']])
        else:
            st.info("هذا المخزن لا يحتوي على أصناف حالياً.")

# --- التبويب 2: التوريد (إضافة صنف لمخزن) ---
with tab2:
    st.subheader("إضافة بضاعة لمخزن")
    with st.form("in_form", clear_on_submit=True):
        target_wh = st.selectbox("إلى أي مخزن؟", wh_list)
        n = st.text_input("اسم الصنف")
        b = st.text_input("الماركة")
        q = st.number_input("الكمية", min_value=1)
        
        if st.form_submit_button("حفظ التوريد"):
            if n:
                match = supabase.table("inventory").select("*").eq("name", n).eq("warehouse", target_wh).execute()
                if match.data:
                    new_q = int(match.data[0]['quantity']) + q
                    supabase.table("inventory").update({"quantity": new_q}).eq("id", match.data[0]['id']).execute()
                else:
                    supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q, "warehouse": target_wh}).execute()
                
                st.success(f"تمت إضافة {q} من {n} إلى {target_wh}")
                st.rerun()

# --- التبويب 3: الصرف ---
with tab3:
    st.subheader("صرف بضاعة")
    source_wh = st.selectbox("اصرف من مخزن:", wh_list)
    wh_items = inv_df[inv_df['warehouse'] == source_wh] if not inv_df.empty else pd.DataFrame()
    
    if not wh_items.empty:
        with st.form("out_form"):
            item_n = st.selectbox("اختر الصنف", wh_items['name'].unique())
            q_o = st.number_input("الكمية", min_value=1)
            dst = st.text_input("المستلم")
            if st.form_submit_button("تأكيد الصرف"):
                row = wh_items[wh_items['name'] == item_n].iloc[0]
                if row['quantity'] >= q_o:
                    supabase.table("inventory").update({"quantity": int(row['quantity'] - q_o)}).eq("id", row['id']).execute()
                    st.success("تم الصرف بنجاح")
                    st.rerun()
                else:
                    st.error("الكمية غير كافية!")
    else:
        st.info("لا توجد أصناف في هذا المخزن.")

# --- التبويب 4: إعدادات المخازن (إضافة/حذف مخزن) ---
with tab4:
    st.subheader("🛠️ إدارة المستودعات")
    pwd = st.text_input("كلمة مرور الإدارة", type="password")
    
    if pwd == ADMIN_PASSWORD:
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("➕ **إضافة مخزن جديد**")
            new_wh_name = st.text_input("اسم المخزن الجديد")
            if st.button("إنشاء المخزن"):
                if new_wh_name:
                    # إضافة صنف وهمي لإنشاء المخزن أو مجرد تحديث القائمة
                    supabase.table("inventory").insert({"name": "بداية المخزن", "brand": "-", "quantity": 0, "warehouse": new_wh_name}).execute()
                    st.success(f"تم إنشاء {new_wh_name}")
                    st.rerun()
        
        with col2:
            st.write("🗑️ **حذف مخزن**")
            wh_to_del = st.selectbox("اختر المخزن المراد حذفه نهائياً", wh_list)
            if st.button("حذف المخزن بكل محتوياته"):
                supabase.table("inventory").delete().eq("warehouse", wh_to_del).execute()
                st.warning(f"تم حذف {wh_to_del}")
                st.rerun()
        
        st.divider()
        st.write("📝 **تعديل صنف محدد**")
        if not inv_df.empty:
            item_to_edit = st.selectbox("اختر الصنف للتعديل أو الحذف", 
                                        inv_df.apply(lambda x: f"{x['name']} ({x['warehouse']})", axis=1))
            idx = inv_df.index[inv_df.apply(lambda x: f"{x['name']} ({x['warehouse']})", axis=1) == item_to_edit][0]
            target_item = inv_df.iloc[idx]
            
            if st.button("حذف هذا الصنف فقط ❌"):
                supabase.table("inventory").delete().eq("id", target_item['id']).execute()
                st.rerun()