import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import requests
import os
import numpy as np
import pytz
import threading
import time as time_module

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"

CHAT_IDS = [
    "5716145319",
    "8703100900",
]

st.set_page_config(page_title="نظام النذير للمخازن", layout="wide")

@st.cache_resource
def init_supabase():
    url = SUPABASE_URL.strip()
    url = url.replace("/rest/v1/", "").replace("/rest/v1", "")
    if url.endswith("/"):
        url = url[:-1]
    return create_client(url, SUPABASE_KEY)

supabase = init_supabase()

def clean_warehouse_value(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.lower() in ['nan', 'none', 'null', '', 'unknown', 'nat']:
            return None
        return cleaned
    cleaned = str(value).strip()
    if cleaned.lower() in ['nan', 'none', 'null', '', 'unknown', 'nat']:
        return None
    return cleaned

def get_data(table):
    res = supabase.table(table).select("*").execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    if not df.empty and 'warehouse' in df.columns:
        df['warehouse'] = df['warehouse'].apply(clean_warehouse_value)
        df = df.dropna(subset=['warehouse'])
    if not df.empty and 'quantity' in df.columns:
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0).astype(int)
    return df

def get_transactions(warehouse=None, date=None):
    query = supabase.table("transactions").select("*")
    if warehouse and warehouse != "all":
        query = query.eq("warehouse", warehouse)
    if date:
        query = query.gte("created_at", f"{date}T00:00:00")
        query = query.lte("created_at", f"{date}T23:59:59")
    res = query.order("created_at", desc=True).execute()
    if not res.data:
        return pd.DataFrame()
    return pd.DataFrame(res.data)

def save_transaction(trans_type, item_name, brand, quantity, warehouse, destination=None):
    data = {
        "type": str(trans_type),
        "item_name": str(item_name),
        "brand": str(brand),
        "quantity": int(quantity),
        "warehouse": str(warehouse),
        "destination": str(destination) if destination else "",
        "created_at": datetime.now().isoformat()
    }
    supabase.table("transactions").insert(data).execute()
    return True

def send_telegram_supply(item_name, brand, quantity, warehouse, total_after, notes=""):
    message = f"""📥 توريد جديد:
📦 الصنف والماركة: {item_name} ({brand})
🏢 المخزن: {warehouse}
🔢 الكمية الموردة: {quantity}
📊 الكمية الإجمالية: {total_after}"""
    if notes:
        message += f"\n📝 ملاحظات: {notes}"
    
    for chat_id in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=5)
        except:
            pass

def send_telegram_withdraw(item_name, brand, quantity, warehouse, destination, remaining):
    message = f"""📤 صرف بضاعة:
📦 الصنف والماركة: {item_name} ({brand})
🏢 من مخزن: {warehouse}
👤 الجهة المستلمة: {destination}
🔢 الكمية المصروفة: {quantity}
📊 الكمية المتبقية: {remaining}"""
    
    for chat_id in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=5)
        except:
            pass

def send_telegram_delete(item_name, brand, quantity, warehouse):
    message = f"🗑️ حذف صنف:\n📦 الصنف والماركة: {item_name} ({brand})\n🏢 المخزن: {warehouse}\n🔢 الكمية المحذوفة: {quantity}"
    for chat_id in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=5)
        except:
            pass

def send_daily_report():
    khartoum_tz = pytz.timezone('Africa/Khartoum')
    now = datetime.now(khartoum_tz)
    today = now.strftime('%Y-%m-%d')
    yesterday = (now - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    
    today_transactions = get_transactions(date=today)
    yesterday_transactions = get_transactions(date=yesterday)
    
    supply_count = len(today_transactions[today_transactions['type'] == 'توريد']) if not today_transactions.empty else 0
    withdraw_count = len(today_transactions[today_transactions['type'] == 'صرف']) if not today_transactions.empty else 0
    delete_count = len(today_transactions[today_transactions['type'] == 'حذف']) if not today_transactions.empty else 0
    
    supply_qty = today_transactions[today_transactions['type'] == 'توريد']['quantity'].sum() if not today_transactions.empty else 0
    withdraw_qty = today_transactions[today_transactions['type'] == 'صرف']['quantity'].sum() if not today_transactions.empty else 0
    
    yesterday_supply = len(yesterday_transactions[yesterday_transactions['type'] == 'توريد']) if not yesterday_transactions.empty else 0
    yesterday_withdraw = len(yesterday_transactions[yesterday_transactions['type'] == 'صرف']) if not yesterday_transactions.empty else 0
    
    inv_df = get_data("inventory")
    total_items = len(inv_df) if not inv_df.empty else 0
    total_quantity = inv_df['quantity'].sum() if not inv_df.empty else 0
    
    message = f"📊 التقرير اليومي - {today}\n\n"
    message += f"📥 التوريدات:\n🔹 عدد العمليات: {supply_count}\n🔹 الكمية الإجمالية: {int(supply_qty)}\n\n"
    message += f"📤 الصرفيات:\n🔹 عدد العمليات: {withdraw_count}\n🔹 الكمية الإجمالية: {int(withdraw_qty)}\n\n"
    message += f"🗑️ المحذوفات: {delete_count}\n\n"
    message += f"📦 المخزون الحالي:\n🔹 عدد الأصناف: {total_items}\n🔹 الكمية الإجمالية: {int(total_quantity)}\n\n"
    message += f"📊 مقارنة مع أمس:\n🔹 توريدات أمس: {yesterday_supply}\n🔹 صرفيات أمس: {yesterday_withdraw}"

    if supply_count > 0:
        message += "\n📋 تفاصيل التوريدات:"
        supplies = today_transactions[today_transactions['type'] == 'توريد']
        for _, row in supplies.iterrows():
            message += f"\n• {row['item_name']} ({row['brand']}) - {int(row['quantity'])} - {row['warehouse']}"
    
    if withdraw_count > 0:
        message += "\n\n📋 تفاصيل الصرفيات:"
        withdraws = today_transactions[today_transactions['type'] == 'صرف']
        for _, row in withdraws.iterrows():
            message += f"\n• {row['item_name']} ({row['brand']}) - {int(row['quantity'])} - إلى: {row.get('destination', 'غير محدد')}"
    
    for chat_id in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=5)
        except:
            pass
    return True

def daily_report_scheduler():
    khartoum_tz = pytz.timezone('Africa/Khartoum')
    while True:
        now = datetime.now(khartoum_tz)
        target_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now > target_time:
            target_time = target_time + pd.Timedelta(days=1)
        sleep_seconds = (target_time - now).total_seconds()
        time_module.sleep(sleep_seconds)
        send_daily_report()
        time_module.sleep(60)

@st.cache_resource
def start_scheduler():
    scheduler_thread = threading.Thread(target=daily_report_scheduler, daemon=True)
    scheduler_thread.start()
    return True

start_scheduler()

def build_warehouse_list():
    default_warehouses = ["مخزن البخاري", "مخزن الجديد"]
    db_warehouses = []
    df = get_data("inventory")
    if not df.empty and 'warehouse' in df.columns:
        unique_values = df['warehouse'].dropna().unique()
        for val in unique_values:
            cleaned = clean_warehouse_value(val)
            if cleaned:
                db_warehouses.append(cleaned)
    all_warehouses = default_warehouses.copy()
    all_warehouses.extend(db_warehouses)
    clean_list = []
    seen = set()
    for wh in all_warehouses:
        if isinstance(wh, str) and wh not in seen:
            clean_list.append(wh)
            seen.add(wh)
    return sorted(clean_list)

wh_list = build_warehouse_list()
if not wh_list:
    wh_list = ["مخزن البخاري", "مخزن الجديد"]

inv_df = get_data("inventory")

st.sidebar.title("مستودعات النذير")

if not inv_df.empty:
    st.sidebar.metric("إجمالي الأصناف", len(inv_df))
    st.sidebar.metric("عدد المخازن", len(wh_list))
    total_qty = inv_df['quantity'].sum()
    st.sidebar.metric("إجمالي الكميات", int(total_qty))

if st.sidebar.button("📊 إرسال تقرير يومي الآن", use_container_width=True):
    if send_daily_report():
        st.sidebar.success("تم إرسال التقرير للجميع!")
    else:
        st.sidebar.error("فشل في إرسال التقرير")

tab1, tab2, tab3, tab4 = st.tabs(["جرد المخازن", "توريد", "صرف", "سجل التحركات والإدارة"])

# --- التبويب 1: الجرد (RTL) ---
with tab1:
    st.header("جرد المخازن")
    col1, col2 = st.columns([2, 1])
    with col1:
        sel_wh = st.selectbox("اختر المخزن", wh_list, key="tab1_warehouse")
    with col2:
        search_term = st.text_input("بحث عن صنف", key="search_inventory")
    
    if sel_wh and not inv_df.empty:
        disp = inv_df[inv_df['warehouse'] == sel_wh].copy()
        if search_term and not disp.empty:
            name_match = disp['name'].astype(str).str.contains(search_term, case=False, na=False)
            brand_match = disp['brand'].astype(str).str.contains(search_term, case=False, na=False)
            disp = disp[name_match | brand_match]
        if not disp.empty:
            # ترتيب الأعمدة من اليمين لليسار: الكمية، الماركة، الصنف
            st.dataframe(
                disp[['quantity', 'brand', 'name']].rename(
                    columns={'quantity': 'الكمية', 'brand': 'الماركة', 'name': 'الصنف'}
                ),
                use_container_width=True,
                hide_index=True
            )
            total_qty = disp['quantity'].sum()
            st.info(f"إجمالي الكميات في {sel_wh}: {int(total_qty)}")
        else:
            st.info(f"لا توجد نتائج في {sel_wh}")
    else:
        st.info("اختر مخزناً لعرض محتوياته")

# --- التبويب 2: التوريد (مع التأكيد) ---
with tab2:
    st.header("توريد بضاعة")
    with st.form("supply_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            t_wh = st.selectbox("إلى مخزن:", wh_list, key="supply_warehouse")
            n = st.text_input("اسم الصنف *", key="supply_name").strip()
            b = st.text_input("الماركة *", key="supply_brand").strip()
        with col2:
            q = st.number_input("الكمية الموردة *", min_value=1, value=1, key="supply_qty")
            notes = st.text_area("ملاحظات (اختياري)", key="supply_notes")
        
        if n and b and q > 0:
            st.info(f"""
            **تفاصيل التوريد:**
            - الصنف: {n}
            - الماركة: {b}
            - المخزن: {t_wh}
            - الكمية الموردة: {q}
            """)
            confirm = st.checkbox("أؤكد صحة البيانات وأريد إتمام التوريد", key="confirm_supply")
        else:
            confirm = False
        
        submitted = st.form_submit_button("حفظ التوريد", use_container_width=True)
        
        if submitted:
            if not n or not b:
                st.error("الرجاء إدخال اسم الصنف والماركة")
            elif not confirm:
                st.error("الرجاء تأكيد العملية بالضغط على مربع التأكيد")
            else:
                existing = supabase.table("inventory").select("*").eq("name", n).eq("brand", b).eq("warehouse", t_wh).execute()
                
                if existing.data and len(existing.data) > 0:
                    old_qty = int(existing.data[0]['quantity'])
                    new_qty = old_qty + q
                    supabase.table("inventory").update({"quantity": new_qty}).eq("id", existing.data[0]['id']).execute()
                    save_transaction("توريد", n, b, q, t_wh)
                    send_telegram_supply(n, b, q, t_wh, new_qty, notes)
                    st.success(f"تم تحديث الكمية: {n} ({b}) - الكمية الجديدة: {new_qty}")
                else:
                    supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q, "warehouse": t_wh}).execute()
                    save_transaction("توريد", n, b, q, t_wh)
                    send_telegram_supply(n, b, q, t_wh, q, notes)
                    st.success(f"تم إضافة صنف جديد: {n} ({b}) - الكمية: {q}")
                
                st.cache_resource.clear()
                st.rerun()

# --- التبويب 3: الصرف (مع التأكيد) ---
with tab3:
    st.header("صرف بضاعة")
    if not inv_df.empty:
        source_wh = st.selectbox("اصرف من:", wh_list, key="withdraw_warehouse")
        items = inv_df[(inv_df['warehouse'] == source_wh) & (inv_df['quantity'] > 0)]
        if not items.empty:
            with st.form("withdraw_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    item_options = []
                    for idx, row in items.iterrows():
                        option_text = f"{row['name']} ({row['brand']}) - المتاح: {row['quantity']}"
                        item_options.append(option_text)
                    
                    sel_item_full = st.selectbox("اختر الصنف", item_options, key="withdraw_item")
                    q_o = st.number_input("الكمية المطلوبة *", min_value=1, value=1, key="withdraw_qty")
                with col2:
                    dst = st.text_input("الجهة المستلمة *", key="withdraw_dest")
                
                confirm = False
                if dst and q_o > 0 and sel_item_full:
                    sel_idx = item_options.index(sel_item_full)
                    row = items.iloc[sel_idx]
                    if q_o <= int(row['quantity']):
                        st.info(f"""
                        **تفاصيل الصرف:**
                        - الصنف والماركة: {row['name']} ({row['brand']})
                        - المخزن: {source_wh}
                        - الكمية المطلوبة: {q_o}
                        - الجهة المستلمة: {dst}
                        - الكمية المتبقية بعد الصرف: {int(row['quantity']) - q_o}
                        """)
                        confirm = st.checkbox("أؤكد صحة البيانات وأريد إتمام الصرف", key="confirm_withdraw")
                    else:
                        st.error(f"الكمية غير متوفرة! المتاح: {row['quantity']}")
                
                submitted = st.form_submit_button("تأكيد الصرف", use_container_width=True)
                
                if submitted:
                    if not dst:
                        st.error("الرجاء إدخال الجهة المستلمة")
                    elif not confirm:
                        st.error("الرجاء تأكيد العملية بالضغط على مربع التأكيد")
                    elif q_o > 0 and sel_item_full:
                        sel_idx = item_options.index(sel_item_full)
                        row = items.iloc[sel_idx]
                        if q_o > int(row['quantity']):
                            st.error(f"الكمية غير متوفرة! المتاح: {row['quantity']}")
                        else:
                            new_qty = int(row['quantity']) - q_o
                            supabase.table("inventory").update({"quantity": new_qty}).eq("id", row['id']).execute()
                            save_transaction("صرف", str(row['name']), str(row['brand']), q_o, source_wh, dst.strip())
                            send_telegram_withdraw(str(row['name']), str(row['brand']), q_o, source_wh, dst.strip(), new_qty)
                            st.success(f"تم صرف {q_o} من {row['name']} إلى {dst}")
                            st.cache_resource.clear()
                            st.rerun()
        else:
            st.warning(f"المخزن {source_wh} فارغ")
    else:
        st.info("قاعدة البيانات فارغة")

# --- التبويب 4: السجل والإدارة (RTL) ---
with tab4:
    st.header("سجل التحركات والإدارة")
    admin_tab1, admin_tab2 = st.tabs(["سجل التحركات", "حذف الأصناف"])
    
    with admin_tab1:
        st.subheader("سجل التحركات اليومية")
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            filter_options = ["الكل"] + wh_list
            filter_warehouse = st.selectbox("تصفية حسب المخزن", filter_options, key="log_warehouse")
        with col2:
            filter_date = st.date_input("تصفية حسب التاريخ", value=None, key="log_date")
        with col3:
            filter_type = st.selectbox("نوع الحركة", ["الكل", "توريد", "صرف", "حذف"], key="log_type")
        
        transactions_df = get_transactions(warehouse=None if filter_warehouse == "الكل" else filter_warehouse, date=filter_date.isoformat() if filter_date else None)
        
        if not transactions_df.empty:
            if filter_type != "الكل":
                transactions_df = transactions_df[transactions_df['type'] == filter_type]
            if not transactions_df.empty:
                if 'created_at' in transactions_df.columns:
                    transactions_df['created_at'] = pd.to_datetime(transactions_df['created_at'], errors='coerce')
                    transactions_df['التاريخ'] = transactions_df['created_at'].dt.strftime('%Y-%m-%d')
                
                # دمج الصنف والماركة
                transactions_df['الصنف والماركة'] = transactions_df['item_name'] + " (" + transactions_df['brand'] + ")"
                
                # تنسيق الأعمدة
                display_df = transactions_df.rename(columns={
                    'type': 'النوع',
                    'quantity': 'الكمية',
                    'destination': 'الجهة المستلمة',
                    'warehouse': 'المخزن'
                })
                
                # ترتيب الأعمدة من اليمين لليسار (RTL)
                display_columns = ['النوع', 'الصنف والماركة', 'الكمية', 'الجهة المستلمة', 'التاريخ', 'المخزن']
                available_columns = [col for col in display_columns if col in display_df.columns]
                
                st.dataframe(display_df[available_columns], use_container_width=True, hide_index=True, height=400)
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("توريدات", len(transactions_df[transactions_df['type'] == 'توريد']))
                col2.metric("صرفيات", len(transactions_df[transactions_df['type'] == 'صرف']))
                col3.metric("محذوفات", len(transactions_df[transactions_df['type'] == 'حذف']))
                col4.metric("الإجمالي", len(transactions_df))
                
                csv = transactions_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(label="تحميل السجل (CSV)", data=csv, file_name=f"transactions_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", mime="text/csv", use_container_width=True)
            else:
                st.info("لا توجد نتائج مطابقة للفلترة")
        else:
            st.info("لا توجد تحركات مسجلة بعد")
    
    with admin_tab2:
        st.subheader("حذف الأصناف")
        st.warning("تنبيه: الحذف نهائي!")
        if not inv_df.empty:
            del_warehouse = st.selectbox("اختر المخزن", wh_list, key="delete_warehouse")
            del_items = inv_df[inv_df['warehouse'] == del_warehouse]
            if not del_items.empty:
                delete_options = []
                for idx, row in del_items.iterrows():
                    option = f"{row['name']} | {row['brand']} | الكمية: {row['quantity']}"
                    delete_options.append(option)
                
                item_to_delete = st.selectbox("اختر الصنف للحذف", delete_options, key="delete_item")
                if st.button("حذف نهائي", type="primary", use_container_width=True):
                    idx = delete_options.index(item_to_delete)
              