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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

st.set_page_config(page_title="نظام النذير للمخازن", layout="wide")

@st.cache_resource
def init_supabase():
    url = SUPABASE_URL.strip().replace("/rest/v1/", "")
    if url.endswith("/"): url = url[:-1]
    return create_client(url, SUPABASE_KEY)

supabase: Client = init_supabase()

# =========================
# 2. دوال جلب البيانات
# =========================
def get_data(table):
    try:
        res = supabase.table(table).select("*").execute()
        if not res.data:
            return pd.DataFrame()
        
        df = pd.DataFrame(res.data)
        
        if not df.empty and 'warehouse' in df.columns:
            df['warehouse'] = df['warehouse'].fillna('unknown').astype(str)
            df = df[~df['warehouse'].lower().isin(['nan', 'none', 'null', '', 'unknown'])]
        
        return df
    except Exception as e:
        st.error(f"خطأ في جلب البيانات: {e}")
        return pd.DataFrame()

def get_transactions(warehouse=None, date=None):
    """جلب سجل التحركات مع إمكانية الفلترة"""
    try:
        query = supabase.table("transactions").select("*")
        
        if warehouse and warehouse != "الكل":
            query = query.eq("warehouse", warehouse)
        
        if date:
            query = query.gte("created_at", f"{date}T00:00:00")
            query = query.lte("created_at", f"{date}T23:59:59")
        
        res = query.order("created_at", desc=True).execute()
        
        if not res.data:
            return pd.DataFrame()
        return pd.DataFrame(res.data)
    except Exception as e:
        return pd.DataFrame()

def save_transaction(trans_type, item_name, brand, quantity, warehouse, destination=None):
    """حفظ حركة في سجل التحركات"""
    try:
        data = {
            "type": trans_type,
            "item_name": item_name,
            "brand": brand,
            "quantity": quantity,
            "warehouse": warehouse,
            "destination": destination or "",
            "created_at": datetime.now().isoformat()
        }
        supabase.table("transactions").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"لم يتم حفظ السجل: {e}")
        return False

def send_telegram(msg):
    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
        except:
            pass

# =========================
# 3. بناء قائمة المخازن
# =========================
inv_df = get_data("inventory")
default_warehouses = ["مخزن البخاري", "مخزن الجديد"]

if not inv_df.empty:
    db_whs = inv_df['warehouse'].unique().tolist()
    wh_list = sorted(list(set(default_warehouses + db_whs)))
else:
    wh_list = default_warehouses

# =========================
# 4. واجهة المستخدم
# =========================
st.sidebar.title("🏢 مستودعات النذير")

# إحصائيات سريعة في الشريط الجانبي
if not inv_df.empty:
    st.sidebar.metric("📦 إجمالي الأصناف", len(inv_df))
    st.sidebar.metric("🏭 عدد المخازن", inv_df['warehouse'].nunique())
    st.sidebar.metric("📊 إجمالي الكميات", inv_df['quantity'].sum())

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 جرد المخازن", 
    "📥 توريد", 
    "📤 صرف", 
    "📋 سجل التحركات والإدارة"
])

# --- التبويب 1: الجرد ---
with tab1:
    st.header("📊 جرد المخازن")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        sel_wh = st.selectbox("اختر المخزن", wh_list, key="tab1_warehouse")
    
    with col2:
        search_term = st.text_input("🔍 بحث عن صنف", "")
    
    if not inv_df.empty:
        disp = inv_df[inv_df['warehouse'] == sel_wh].copy()
        
        if search_term:
            disp = disp[disp['name'].str.contains(search_term, case=False) | 
                       disp['brand'].str.contains(search_term, case=False)]
        
        if not disp.empty:
            st.dataframe(
                disp[['name', 'brand', 'quantity']],
                use_container_width=True,
                hide_index=True
            )
            
            # إظهار إجمالي الكميات
            total_qty = disp['quantity'].sum()
            st.info(f"إجمالي الكميات في {sel_wh}: **{total_qty}**")
        else:
            st.info(f"لا توجد نتائج في {sel_wh}")
    else:
        st.info("قاعدة البيانات فارغة حالياً")

# --- التبويب 2: التوريد ---
with tab2:
    st.header("📥 توريد بضاعة")
    
    with st.form("supply_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            t_wh = st.selectbox("إلى مخزن:", wh_list, key="supply_warehouse")
            n = st.text_input("اسم الصنف *")
            b = st.text_input("الماركة *")
        
        with col2:
            q = st.number_input("الكمية الموردة *", min_value=1, value=1)
            notes = st.text_area("ملاحظات (اختياري)")
        
        submitted = st.form_submit_button("✅ حفظ التوريد", use_container_width=True)
        
        if submitted:
            if not n or not b:
                st.error("الرجاء إدخال اسم الصنف والماركة")
            else:
                with st.spinner("جاري الحفظ..."):
                    # البحث عن تطابق (اسم + ماركة + مخزن)
                    match = supabase.table("inventory").select("*")\
                        .eq("name", n).eq("brand", b).eq("warehouse", t_wh).execute()
                    
                    if match.data:
                        new_q = int(match.data[0]['quantity']) + q
                        supabase.table("inventory").update({"quantity": new_q})\
                            .eq("id", match.data[0]['id']).execute()
                    else:
                        supabase.table("inventory").insert({
                            "name": n, "brand": b, 
                            "quantity": q, "warehouse": t_wh
                        }).execute()
                    
                    # حفظ في سجل التحركات
                    save_transaction("توريد", n, b, q, t_wh)
                    
                    # إرسال إشعار تيليجرام
                    note_text = f" - {notes}" if notes else ""
                    send_telegram(f"📥 توريد: {n} ({b}) | الكمية: {q} | إلى: {t_wh}{note_text}")
                    
                    st.success(f"✅ تم توريد {q} من {n} ({b}) إلى {t_wh}")
                    st.rerun()

# --- التبويب 3: الصرف ---
with tab3:
    st.header("📤 صرف بضاعة")
    
    if not inv_df.empty:
        source_wh = st.selectbox("اصرف من:", wh_list, key="withdraw_warehouse")
        items = inv_df[(inv_df['warehouse'] == source_wh) & (inv_df['quantity'] > 0)]
        
        if not items.empty:
            with st.form("withdraw_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    item_options = items.apply(
                        lambda x: f"{x['name']} ({x['brand']}) - المتاح: {x['quantity']}", 
                        axis=1
                    ).tolist()
                    sel_item_full = st.selectbox("اختر الصنف", item_options)
                    q_o = st.number_input("الكمية المطلوبة *", min_value=1)
                
                with col2:
                    dst = st.text_input("الجهة المستلمة *")
                    reason = st.text_area("سبب الصرف (اختياري)")
                
                submitted = st.form_submit_button("✅ تأكيد الصرف", use_container_width=True)
                
                if submitted:
                    if not dst:
                        st.error("الرجاء إدخال الجهة المستلمة")
                    else:
                        sel_idx = item_options.index(sel_item_full)
                        row = items.iloc[sel_idx]
                        
                        if q_o > row['quantity']:
                            st.error(f"الكمية غير متوفرة! المتاح: {row['quantity']}")
                        else:
                            with st.spinner("جاري الصرف..."):
                                new_qty = int(row['quantity'] - q_o)
                                supabase.table("inventory").update({"quantity": new_qty})\
                                    .eq("id", row['id']).execute()
                                
                                # حفظ في سجل التحركات
                                save_transaction("صرف", row['name'], row['brand'], q_o, source_wh, dst)
                                
                                # إرسال إشعار تيليجرام
                                reason_text = f" - {reason}" if reason else ""
                                send_telegram(
                                    f"📤 صرف: {row['name']} ({row['brand']}) | الكمية: {q_o} | "
                                    f"من: {source_wh} | إلى: {dst}{reason_text}"
                                )
                                
                                st.success(f"✅ تم صرف {q_o} من {row['name']} إلى {dst}")
                                st.rerun()
        else:
            st.warning(f"⚠️ المخزن {source_wh} فارغ أو لا يحتوي على بضائع")
    else:
        st.info("قاعدة البيانات فارغة")

# --- التبويب 4: سجل التحركات والإدارة ---
with tab4:
    st.header("📋 سجل التحركات والإدارة")
    
    # تقسيم الصفحة إلى جزئين
    admin_tab1, admin_tab2 = st.tabs(["📊 سجل التحركات", "🗑️ حذف الأصناف"])
    
    # ====== سجل التحركات ======
    with admin_tab1:
        st.subheader("📊 سجل التحركات اليومية")
        
        # فلترة السجل
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            filter_warehouse = st.selectbox(
                "تصفية حسب المخزن",
                ["الكل"] + wh_list,
                key="log_warehouse"
            )
        
        with col2:
            filter_date = st.date_input(
                "تصفية حسب التاريخ",
                value=None,
                key="log_date"
            )
        
        with col3:
            filter_type = st.selectbox(
                "نوع الحركة",
                ["الكل", "توريد", "صرف"],
                key="log_type"
            )
        
        # جلب السجل
        transactions_df = get_transactions(
            warehouse=None if filter_warehouse == "الكل" else filter_warehouse,
            date=filter_date.isoformat() if filter_date else None
        )
        
        if not transactions_df.empty:
            # تطبيق فلتر النوع
            if filter_type != "الكل":
                transactions_df = transactions_df[transactions_df['type'] == filter_type]
            
            # تنسيق العرض
            display_df = transactions_df.copy()
            if 'created_at' in display_df.columns:
                display_df['created_at'] = pd.to_datetime(display_df['created_at'])
                display_df['التاريخ'] = display_df['created_at'].dt.strftime('%Y-%m-%d')
                display_df['الوقت'] = display_df['created_at'].dt.strftime('%H:%M:%S')
            
            # إعادة تسمية الأعمدة للعرض
            column_mapping = {
                'type': 'النوع',
                'item_name': 'الصنف',
                'brand': 'الماركة',
                'quantity': 'الكمية',
                'warehouse': 'المخزن',
                'destination': 'الجهة',
                'التاريخ': 'التاريخ',
                'الوقت': 'الوقت'
            }
            
            display_columns = ['النوع', 'التاريخ', 'الوقت', 'الصنف', 'الماركة', 
                             'الكمية', 'المخزن', 'الجهة']
            
            # عرض البيانات
            available_columns = [col for col in display_columns if col in column_mapping.values()]
            
            st.dataframe(
                display_df[available_columns],
                use_container_width=True,
                hide_index=True
            )
            
            # إحصائيات سريعة
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📥 إجمالي التوريدات", 
                         len(transactions_df[transactions_df['type'] == 'توريد']))
            with col2:
                st.metric("📤 إجمالي الصرفيات", 
                         len(transactions_df[transactions_df['type'] == 'صرف']))
            with col3:
                st.metric("📦 إجمالي العمليات", len(transactions_df))
            
            # تصدير السجل
            if st.button("📥 تصدير السجل إلى Excel", use_container_width=True):
                csv = transactions_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="اضغط للتحميل",
                    data=csv,
                    file_name=f"سجل_التحركات_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
        else:
            st.info("لا توجد تحركات مسجلة بعد")
    
    # ====== حذف الأصناف ======
    with admin_tab2:
        st.subheader("🗑️ حذف الأصناف")
        st.warning("⚠️ تنبيه: الحذف نهائي ولا يمكن التراجع عنه!")
        
        if not inv_df.empty:
            # فلترة قبل الحذف
            del_warehouse = st.selectbox(
                "اختر المخزن",
                wh_list,
                key="delete_warehouse"
            )
            
            del_items = inv_df[inv_df['warehouse'] == del_warehouse]
            
            if not del_items.empty:
                item_to_delete = st.selectbox(
                    "اختر الصنف للحذف",
                    del_items.apply(
                        lambda x: f"{x['name']} | {x['brand']} | الكمية: {x['quantity']}",
                        axis=1
                    ).tolist(),
                    key="delete_item"
                )
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    confirm = st.checkbox("تأكيد الحذف")
                
                if confirm:
                    if st.button("🗑️ حذف نهائي", type="primary", use_container_width=True):
                        idx = del_items.index[
                            del_items.apply(
                                lambda x: f"{x['name']} | {x['brand']} | الكمية: {x['quantity']}",
                                axis=1
                            ) == item_to_delete
                        ][0]
                        
                        item = del_items.iloc[idx]
                        supabase.table("inventory").delete().eq("id", item['id']).execute()
                        
                        # تسجيل الحذف في السجل
                        save_transaction("حذف", item['name'], item['brand'], 
                                       item['quantity'], del_warehouse, "حذف من النظام")
                        
                        st.success(f"تم حذف {item['name']} ({item['brand']})")
                        st.rerun()
            else:
                st.info(f"المخزن {del_warehouse} فارغ")
        else:
            st.info("لا توجد أصناف للحذف")

# =========================
# 5. تذييل الصفحة
# =========================
st.sidebar.markdown("---")
st.sidebar.markdown(f"آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M')}")