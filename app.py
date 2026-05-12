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
            # تحويل العمود لنصوص وتنظيفه
            df['warehouse'] = df['warehouse'].fillna('').astype(str).str.strip()
            # حذف الصفوف الفارغة أو غير الصالحة
            df = df[df['warehouse'] != '']
            df = df[~df['warehouse'].isin(['nan', 'None', 'null', 'unknown', 'NoneType'])]
        
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
        st.error(f"خطأ في جلب التحركات: {e}")
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
# 3. بناء قائمة المخازن - مع إصلاح المشكلة
# =========================
inv_df = get_data("inventory")
default_warehouses = ["مخزن البخاري", "مخزن الجديد"]

# طريقة آمنة لاستخراج أسماء المخازن
if not inv_df.empty:
    # تحويل كل القيم إلى نصوص والتأكد من نظافتها
    db_warehouses = []
    for wh in inv_df['warehouse'].unique():
        wh_str = str(wh).strip()
        if wh_str and wh_str.lower() not in ['nan', 'none', 'null', '']:
            db_warehouses.append(wh_str)
    
    # دمج مع القائمة الافتراضية
    all_warehouses = default_warehouses + db_warehouses
else:
    all_warehouses = default_warehouses

# إزالة التكرار والترتيب مع معالجة آمنة
try:
    # تصفية أي قيم ليست نصوص
    clean_warehouses = [wh for wh in all_warehouses if isinstance(wh, str) and wh.strip()]
    wh_list = sorted(list(set(clean_warehouses)))
except Exception as e:
    st.error(f"خطأ في ترتيب المخازن: {e}")
    wh_list = default_warehouses

# =========================
# 4. واجهة المستخدم
# =========================
st.sidebar.title("🏢 مستودعات النذير")

# إحصائيات سريعة في الشريط الجانبي
if not inv_df.empty:
    st.sidebar.metric("📦 إجمالي الأصناف", len(inv_df))
    st.sidebar.metric("🏭 عدد المخازن", len(wh_list))
    try:
        # التأكد من أن العمود رقمي
        if inv_df['quantity'].dtype == 'object':
            total_qty = pd.to_numeric(inv_df['quantity'], errors='coerce').fillna(0).sum()
        else:
            total_qty = inv_df['quantity'].sum()
        st.sidebar.metric("📊 إجمالي الكميات", int(total_qty))
    except:
        pass

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
        if wh_list:
            sel_wh = st.selectbox("اختر المخزن", wh_list, key="tab1_warehouse")
        else:
            st.warning("لا توجد مخازن متاحة")
            sel_wh = None
    
    with col2:
        search_term = st.text_input("🔍 بحث عن صنف", "")
    
    if sel_wh and not inv_df.empty:
        disp = inv_df[inv_df['warehouse'] == sel_wh].copy()
        
        if search_term:
            disp = disp[disp['name'].str.contains(search_term, case=False, na=False) | 
                       disp['brand'].str.contains(search_term, case=False, na=False)]
        
        if not disp.empty:
            st.dataframe(
                disp[['name', 'brand', 'quantity']],
                use_container_width=True,
                hide_index=True
            )
            
            # إظهار إجمالي الكميات
            try:
                if disp['quantity'].dtype == 'object':
                    total_qty = pd.to_numeric(disp['quantity'], errors='coerce').fillna(0).sum()
                else:
                    total_qty = disp['quantity'].sum()
                st.info(f"إجمالي الكميات في {sel_wh}: **{int(total_qty)}**")
            except:
                pass
        else:
            st.info(f"لا توجد نتائج في {sel_wh}")
    elif not inv_df.empty:
        st.info("قاعدة البيانات فارغة حالياً")

# --- التبويب 2: التوريد ---
with tab2:
    st.header("📥 توريد بضاعة")
    
    if wh_list:
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
                        try:
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
                        except Exception as e:
                            st.error(f"حدث خطأ: {e}")
    else:
        st.warning("لا توجد مخازن متاحة")

# --- التبويب 3: الصرف ---
with tab3:
    st.header("📤 صرف بضاعة")
    
    if not inv_df.empty and wh_list:
        source_wh = st.selectbox("اصرف من:", wh_list, key="withdraw_warehouse")
        items = inv_df[(inv_df['warehouse'] == source_wh) & (inv_df['quantity'] > 0)]
        
        if not items.empty:
            with st.form("withdraw_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    # إنشاء قائمة الخيارات بشكل آمن
                    item_options = []
                    for idx, row in items.iterrows():
                        try:
                            item_options.append(f"{row['name']} ({row['brand']}) - المتاح: {row['quantity']}")
                        except:
                            continue
                    
                    if item_options:
                        sel_item_full = st.selectbox("اختر الصنف", item_options)
                        q_o = st.number_input("الكمية المطلوبة *", min_value=1)
                    else:
                        st.warning("لا توجد خيارات متاحة")
                        sel_item_full = None
                
                with col2:
                    dst = st.text_input("الجهة المستلمة *")
                    reason = st.text_area("سبب الصرف (اختياري)")
                
                submitted = st.form_submit_button("✅ تأكيد الصرف", use_container_width=True)
                
                if submitted and sel_item_full:
                    if not dst:
                        st.error("الرجاء إدخال الجهة المستلمة")
                    else:
                        sel_idx = item_options.index(sel_item_full)
                        row = items.iloc[sel_idx]
                        
                        if q_o > row['quantity']:
                            st.error(f"الكمية غير متوفرة! المتاح: {row['quantity']}")
                        else:
                            with st.spinner("جاري الصرف..."):
                                try:
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
                                except Exception as e:
                                    st.error(f"حدث خطأ: {e}")
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
            
            if not transactions_df.empty:
                # تنسيق العرض
                display_df = transactions_df.copy()
                if 'created_at' in display_df.columns:
                    display_df['created_at'] = pd.to_datetime(display_df['created_at'], errors='coerce')
                    display_df['التاريخ'] = display_df['created_at'].dt.strftime('%Y-%m-%d')
                    display_df['الوقت'] = display_df['created_at'].dt.strftime('%H:%M:%S')
                
                # اختيار الأعمدة المتاحة للعرض
                display_columns = []
                if 'type' in display_df.columns: display_columns.append('type')
                if 'التاريخ' in display_df.columns: display_columns.append('التاريخ')
                if 'الوقت' in display_df.columns: display_columns.append('الوقت')
                if 'item_name' in display_df.columns: display_columns.append('item_name')
                if 'brand' in display_df.columns: display_columns.append('brand')
                if 'quantity' in display_df.columns: display_columns.append('quantity')
                if 'warehouse' in display_df.columns: display_columns.append('warehouse')
                if 'destination' in display_df.columns: display_columns.append('destination')
                
                # إعادة تسمية الأعمدة للعرض العربي
                arabic_names = {
                    'type': 'النوع',
                    'item_name': 'الصنف',
                    'brand': 'الماركة',
                    'quantity': 'الكمية',
                    'warehouse': 'المخزن',
                    'destination': 'الجهة',
                    'التاريخ': 'التاريخ',
                    'الوقت': 'الوقت'
                }
                
                display_df = display_df[display_columns].rename(columns=arabic_names)
                
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # إحصائيات سريعة
                col1, col2, col3 = st.columns(3)
                with col1:
                    supply_count = len(transactions_df[transactions_df['type'] == 'توريد'])
                    st.metric("📥 إجمالي التوريدات", supply_count)
                with col2:
                    withdraw_count = len(transactions_df[transactions_df['type'] == 'صرف'])
                    st.metric("📤 إجمالي الصرفيات", withdraw_count)
                with col3:
                    st.metric("📦 إجمالي العمليات", len(transactions_df))
                
                # تصدير السجل
                col1, col2 = st.columns([1, 2])
                with col1:
                    if st.button("📥 تحضير التصدير", use_container_width=True):
                        st.session_state['export_ready'] = True
                
                if st.session_state.get('export_ready', False):
                    csv = transactions_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="💾 اضغط لتحميل ملف Excel",
                        data=csv,
                        file_name=f"سجل_التحركات_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
        else:
            st.info("لا توجد تحركات مسجلة بعد")
    
    # ====== حذف الأصناف ======
    with admin_tab2:
        st.subheader("🗑️ حذف الأصناف")
        st.warning("⚠️ تنبيه: الحذف نهائي ولا يمكن التراجع عنه!")
        
        if not inv_df.empty and wh_list:
            # فلترة قبل الحذف
            del_warehouse = st.selectbox(
                "اختر المخزن",
                wh_list,
                key="delete_warehouse"
            )
            
            del_items = inv_df[inv_df['warehouse'] == del_warehouse]
            
            if not del_items.empty:
                # إنشاء قائمة الحذف بشكل آمن
                delete_options = []
                for idx, row in del_items.iterrows():
                    try:
                        delete_options.append(f"{row['name']} | {row['brand']} | الكمية: {row['quantity']}")
                    except:
                        continue
                
                if delete_options:
                    item_to_delete = st.selectbox(
                        "اختر الصنف للحذف",
                        delete_options,
                        key="delete_item"
                    )
                    
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        confirm = st.checkbox("تأكيد الحذف")
                    
                    if confirm and st.button("🗑️ حذف نهائي", type="primary", use_container_width=True):
                        try:
                            idx = delete_options.index(item_to_delete)
                            item = del_items.iloc[idx]
                            
                            # الحذف من قاعدة البيانات
                            supabase.table("inventory").delete().eq("id", item['id']).execute()
                            
                            # تسجيل الحذف في السجل
                            save_transaction("حذف", item['name'], item['brand'], 
                                           item['quantity'], del_warehouse, "حذف من النظام")
                            
                            st.success(f"تم حذف {item['name']} ({item['brand']})")
                            st.rerun()
                        except Exception as e:
                            st.error(f"حدث خطأ في الحذف: {e}")
                else:
                    st.info("لا توجد خيارات متاحة")
            else:
                st.info(f"المخزن {del_warehouse} فارغ")
        else:
            st.info("لا توجد أصناف للحذف")

# =========================
# 5. تذييل الصفحة
# =========================
st.sidebar.markdown("---")
st.sidebar.markdown(f"آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M')}")