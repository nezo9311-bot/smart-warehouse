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

st.set_page_config(page_title="نظام النذير لإدارة المخازن", layout="wide")

# تنظيف الرابط والاتصال بـ Supabase
@st.cache_resource
def init_supabase():
    if not SUPABASE_URL:
        st.error("خطأ: SUPABASE_URL غير موجود في إعدادات Render")
        st.stop()
    # تنظيف الرابط من أي زيادات
    url = SUPABASE_URL.strip().replace("/rest/v1/", "")
    if url.endswith("/"): url = url[:-1]
    return create_client(url, SUPABASE_KEY)

supabase: Client = init_supabase()

# =========================
# 2. وظائف البيانات والإشعارات
# =========================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except: pass

def get_data(table):
    try:
        res = supabase.table(table).select("*").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.error(f"خطأ في جلب البيانات: {e}")
        return pd.DataFrame()

# =========================
# 3. معالجة قائمة المخازن
# =========================
inv_df = get_data("inventory")
default_warehouses = ["مخزن البخاري", "مخزن الجديد"]

if not inv_df.empty and 'warehouse' in inv_df.columns:
    # تحويل كافة القيم لنصوص لضمان عدم حدوث خطأ الترتيب TypeError
    raw_list = inv_df['warehouse'].dropna().unique().tolist()
    db_warehouses = [str(x) for x in raw_list]
    wh_list = sorted(list(set(default_warehouses + db_warehouses)))
else:
    wh_list = default_warehouses

# =========================
# 4. واجهة المستخدم (التطبيقات)
# =========================
st.sidebar.title("🏢 مستودعات النذير")
st.sidebar.info("تم تفعيل مخزن البخاري والجديد")

tab1, tab2, tab3, tab4 = st.tabs(["📊 جرد المخازن", "📥 توريد بضاعة", "📤 صرف بضاعة", "⚙️ إدارة وحذف"])

# --- التبويب 1: الجرد والعرض ---
with tab1:
    sel_wh = st.selectbox("اختر المخزن للمعاينة", wh_list)
    if not inv_df.empty:
        disp_df = inv_df[inv_df['warehouse'] == sel_wh]
        if not disp_df.empty:
            st.subheader(f"محتويات {sel_wh}")
            st.table(disp_df[['name', 'brand', 'quantity']])
        else:
            st.info(f"المخزن '{sel_wh}' فارغ حالياً.")
    else:
        st.warning("لا توجد بيانات مسجلة بعد.")

# --- التبويب 2: التوريد ---
with tab2:
    st.subheader("إضافة بضاعة للمستودع")
    with st.form("in_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            target_wh = st.selectbox("إلى مخزن:", wh_list)
            n = st.text_input("اسم الصنف (مثلاً: سكر)")
        with col2:
            b = st.text_input("الماركة")
            q = st.number_input("الكمية", min_value=1, step=1)
        
        if st.form_submit_button("حفظ التوريد ✅"):
            if n:
                # التحقق من وجود الصنف مسبقاً
                match = supabase.table("inventory").select("*").eq("name", n).eq("warehouse", target_wh).execute()
                if match.data:
                    new_q = int(match.data[0]['quantity']) + q
                    supabase.table("inventory").update({"quantity": new_q}).eq("id", match.data[0]['id']).execute()
                else:
                    supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q, "warehouse": target_wh}).execute()
                
                send_telegram(f"📥 توريد جديد:\n📦 الصنف: {n}\n🏢 المخزن: {target_wh}\n🔢 الكمية: {q}")
                st.success(f"تمت إضافة {q} إلى {target_wh}")
                st.rerun()

# --- التبويب 3: الصرف ---
with tab3:
    st.subheader("سحب بضاعة من المخزن")
    source_wh = st.selectbox("اصرف من:", wh_list)
    wh_items = inv_df[inv_df['warehouse'] == source_wh] if not inv_df.empty else pd.DataFrame()
    
    if not wh_items.empty and not wh_items[wh_items['quantity'] > 0].empty:
        with st.form("out_form", clear_on_submit=True):
            available = wh_items[wh_items['quantity'] > 0]
            item_n = st.selectbox("اختر الصنف المتوفر", available['name'].unique())
            q_out = st.number_input("الكمية المراد صرفها", min_value=1)
            dst = st.text_input("الجهة المستلمة")
            
            if st.form_submit_button("تأكيد الصرف 📤"):
                row = wh_items[wh_items['name'] == item_n].iloc[0]
                if row['quantity'] >= q_out:
                    new_val = int(row['quantity'] - q_out)
                    supabase.table("inventory").update({"quantity": new_val}).eq("id", row['id']).execute()
                    send_telegram(f"📤 صرف بضاعة:\n📦 الصنف: {item_n}\n🏢 من: {source_wh}\n🚚 إلى: {dst}\n🔢 الكمية: {q_out}")
                    st.success("تمت العملية بنجاح!")
                    st.rerun()
                else:
                    st.error("الكمية المطلوبة غير متوفرة!")
    else:
        st.warning("لا توجد بضاعة قابلة للصرف في هذا المخزن.")

# --- التبويب 4: الإدارة ---
with tab4:
    st.subheader("🛠️ لوحة تحكم الإدارة")
    pwd = st.text_input("أدخل كلمة المرور", type="password")
    if pwd == ADMIN_PASSWORD:
        st.divider()
        if not inv_df.empty:
            # خيار الحذف أو التعديل اليدوي
            item_to_manage = st.selectbox("اختر صنفاً للإدارة", 
                                          inv_df.apply(lambda x: f"{x['name']} | {x['warehouse']}", axis=1))
            
            idx = inv_df.index[inv_df.apply(lambda x: f"{x['name']} | {x['warehouse']}", axis=1) == item_to_manage][0]
            target = inv_df.iloc[idx]
            
            c1, c2 = st.columns(2)
            with c1:
                new_manual_q = st.number_input("تعديل الكمية يدوياً إلى:", value=int(target['quantity']))
                if st.button("تحديث الكمية ✅"):
                    supabase.table("inventory").update({"quantity": new_manual_q}).eq("id", target['id']).execute()
                    st.success("تم التحديث")
                    st.rerun()
            with c2:
                st.write("🗑️ حذف السجل نهائياً")
                if st.button("حذف الصنف ❌"):
                    supabase.table("inventory").delete().eq("id", target['id']).execute()
                    st.rerun()
        else:
            st.info("لا توجد بيانات للإدارة.")