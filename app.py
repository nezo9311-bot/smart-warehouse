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

# تنظيف الرابط والاتصال بـ Supabase
@st.cache_resource
def init_supabase():
    url = SUPABASE_URL.strip().replace("/rest/v1/", "")
    if url.endswith("/"): url = url[:-1]
    return create_client(url, SUPABASE_KEY)

supabase: Client = init_supabase()

# =========================
# 2. وظائف مساعدة
# =========================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except: pass

def get_data(table):
    res = supabase.table(table).select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

# =========================
# 3. واجهة المستخدم
# =========================
st.sidebar.title("🏢 مستودعات النذير")
st.sidebar.markdown("---")

# تحميل البيانات
inv_df = get_data("inventory")
mov_df = get_data("movements")

# استخراج قائمة المخازن الفريدة
if not inv_df.empty and 'warehouse' in inv_df.columns:
    wh_list = sorted(inv_df['warehouse'].unique().tolist())
else:
    wh_list = ["المخزن الرئيسي"]

tab1, tab2, tab3, tab4 = st.tabs(["📊 عرض وجرد", "📥 توريد", "📤 صرف", "🛠️ إدارة (تعديل/حذف)"])

# --- التبويب 1: عرض المخازن منفصلة ---
with tab1:
    st.subheader("🔍 عرض مخزون محدد")
    sel_wh = st.selectbox("اختر المخزن لعرض جرد بضاعته", wh_list)
    
    if not inv_df.empty:
        disp_df = inv_df[inv_df['warehouse'] == sel_wh]
        if not disp_df.empty:
            st.dataframe(disp_df[['name', 'brand', 'quantity']], use_container_width=True)
        else:
            st.info("هذا المخزن فارغ حالياً.")
    else:
        st.warning("لا توجد بيانات بضاعة مسجلة.")

# --- التبويب 2: التوريد (إضافة مخزون) ---
with tab2:
    st.subheader("📥 توريد بضاعة جديدة")
    with st.form("in_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            wh_name = st.text_input("اسم المخزن (جديد أو موجود)", value=wh_list[0])
            n = st.text_input("اسم الصنف")
        with col2:
            b = st.text_input("الماركة")
            q = st.number_input("الكمية الموردة", min_value=1)
        
        if st.form_submit_button("اعتماد التوريد"):
            if wh_name and n:
                # التحقق من وجود الصنف في نفس المخزن
                match = supabase.table("inventory").select("*").eq("name", n).eq("warehouse", wh_name).execute()
                
                if match.data:
                    new_q = int(match.data[0]['quantity']) + q
                    supabase.table("inventory").update({"quantity": new_q}).eq("id", match.data[0]['id']).execute()
                else:
                    supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q, "warehouse": wh_name}).execute()
                
                # سجل الحركة
                supabase.table("movements").insert({
                    "type": "إدخال", "name": n, "brand": b, "quantity": q, 
                    "warehouse": wh_name, "date": datetime.now().isoformat()
                }).execute()
                
                send_telegram(f"📥 توريد: {n} ({b})\n📦 المخزن: {wh_name}\n🔢 الكمية: {q}")
                st.success(f"تمت الإضافة لمخزن {wh_name}")
                st.rerun()

# --- التبويب 3: الصرف ---
with tab3:
    st.subheader("📤 صرف بضاعة من مخزن")
    if not inv_df.empty:
        with st.form("out_form", clear_on_submit=True):
            wh_sel_out = st.selectbox("اصرف من مخزن:", wh_list)
            available_items = inv_df[inv_df['warehouse'] == wh_sel_out]
            
            if not available_items.empty:
                n_out = st.selectbox("الصنف", available_items['name'].unique())
                b_out = st.selectbox("الماركة", available_items[available_items['name']==n_out]['brand'])
                q_out = st.number_input("الكمية المنصرفة", min_value=1)
                dst = st.text_input("الجهة المستلمة")
                
                if st.form_submit_button("تأكيد الصرف"):
                    row = available_items[(available_items['name']==n_out) & (available_items['brand']==b_out)].iloc[0]
                    if row['quantity'] >= q_out:
                        new_val = int(row['quantity'] - q_out)
                        supabase.table("inventory").update({"quantity": new_val}).eq("id", row['id']).execute()
                        
                        supabase.table("movements").insert({
                            "type": "إخراج", "name": n_out, "brand": b_out, "quantity": q_out, 
                            "warehouse": wh_sel_out, "dest": dst, "date": datetime.now().isoformat()
                        }).execute()
                        
                        send_telegram(f"📤 صرف: {n_out}\n🚚 للجهة: {dst}\n🏢 المخزن: {wh_sel_out}")
                        st.success("تم الصرف!")
                        st.rerun()
                    else: st.error("الكمية غير كافية!")
            else: st.info("المخزن المختار فارغ.")
    else: st.warning("لا يوجد مخزون متاح للصرف.")

# --- التبويب 4: الإدارة (تعديل وحذف) ---
with tab4:
    st.subheader("🛠️ لوحة تحكم المدير")
    pwd = st.text_input("أدخل كلمة مرور الإدارة", type="password")
    
    if pwd == ADMIN_PASSWORD:
        if not inv_df.empty:
            st.divider()
            item_to_manage = st.selectbox("اختر الصنف المراد تعديله أو حذفه", 
                                        inv_df.apply(lambda x: f"{x['name']} | {x['brand']} | {x['warehouse']}", axis=1))
            
            idx = inv_df.index[inv_df.apply(lambda x: f"{x['name']} | {x['brand']} | {x['warehouse']}", axis=1) == item_to_manage][0]
            item = inv_df.iloc[idx]
            
            c1, c2 = st.columns(2)
            with c1:
                new_qty = st.number_input("تعديل الكمية يدوياً إلى:", value=int(item['quantity']))
                if st.button("تحديث الكمية ✅"):
                    supabase.table("inventory").update({"quantity": new_qty}).eq("id", item['id']).execute()
                    st.success("تم التحديث")
                    st.rerun()
            
            with c2:
                st.write("🗑️ حذف السجل")
                if st.button("حذف الصنف نهائياً ❌"):
                    supabase.table("inventory").delete().eq("id", item['id']).execute()
                    st.warning("تم الحذف من القاعدة")
                    st.rerun()
        else:
            st.info("لا توجد بيانات لإدارتها.")