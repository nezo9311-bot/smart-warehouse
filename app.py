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
    
    today_transactions = get_transactions(date=today)
    inv_df = get_data("inventory")
    
    supply_count = len(today_transactions[today_transactions['type'] == 'توريد']) if not today_transactions.empty else 0
    withdraw_count = len(today_transactions[today_transactions['type'] == 'صرف']) if not today_transactions.empty else 0
    delete_count = len(today_transactions[today_transactions['type'] == 'حذف']) if not today_transactions.empty else 0
    supply_qty = today_transactions[today_transactions['type'] == 'توريد']['quantity'].sum() if not today_transactions.empty else 0
    withdraw_qty = today_transactions[today_transactions['type'] == 'صرف']['quantity'].sum() if not today_transactions.empty else 0
    
    total_items = len(inv_df) if not inv_df.empty else 0
    total_quantity = inv_df['quantity'].sum() if not inv_df.empty else 0
    
    message = f"📊 التقرير اليومي - {today}\n"
    message += "━━━━━━━━━━━━━━━━━━\n"
    message += f"📥 إجمالي التوريدات: {supply_count} عملية (+{int(supply_qty)})\n"
    message += f"📤 إجمالي الصرفيات: {withdraw_count} عملية (-{int(withdraw_qty)})\n"
    if delete_count > 0:
        message += f"🗑️ المحذوفات: {delete_count}\n"
    message += f"📦 إجمالي المخزون: {total_items} صنف ({int(total_quantity)} قطعة)\n"
    
    warehouses = wh_list if wh_list else []
    if not today_transactions.empty or not inv_df.empty:
        message += "\n📋 تفاصيل المخازن:"
        for wh in warehouses:
            wh_today = today_transactions[today_transactions['warehouse'] == wh] if not today_transactions.empty else pd.DataFrame()
            wh_supply_count = len(wh_today[wh_today['type'] == 'توريد']) if not wh_today.empty else 0
            wh_withdraw_count = len(wh_today[wh_today['type'] == 'صرف']) if not wh_today.empty else 0
            wh_delete_count = len(wh_today[wh_today['type'] == 'حذف']) if not wh_today.empty else 0
            wh_supply_qty = wh_today[wh_today['type'] == 'توريد']['quantity'].sum() if not wh_today.empty else 0
            wh_withdraw_qty = wh_today[wh_today['type'] == 'صرف']['quantity'].sum() if not wh_today.empty else 0
            
            wh_inv = inv_df[inv_df['warehouse'] == wh] if not inv_df.empty else pd.DataFrame()
            wh_items_count = len(wh_inv) if not wh_inv.empty else 0
            wh_qty_total = wh_inv['quantity'].sum() if not wh_inv.empty else 0
            
            message += f"\n\n🏢 {wh}:"
            if wh_supply_count > 0 or wh_withdraw_count > 0 or wh_delete_count > 0:
                if wh_supply_count > 0:
                    message += f"\n   📥 توريد: {wh_supply_count} عمليات (+{int(wh_supply_qty)})"
                if wh_withdraw_count > 0:
                    message += f"\n   📤 صرف: {wh_withdraw_count} عمليات (-{int(wh_withdraw_qty)})"
                if wh_delete_count > 0:
                    message += f"\n   🗑️ حذف: {wh_delete_count}"
            else:
                message += "\n   لا توجد حركات اليوم"
            message += f"\n   📦 المخزون الحالي: {wh_items_count} صنف ({int(wh_qty_total)} قطعة)"
            
            if not wh_today.empty:
                supplies = wh_today[wh_today['type'] == 'توريد']
                if not supplies.empty:
                    message += "\n   🔹 التوريدات:"
                    for _, row in supplies.iterrows():
                        message += f"\n      • {row['item_name']} ({row['brand']}): +{int(row['quantity'])}"
                
                withdraws = wh_today[wh_today['type'] == 'صرف']
                if not withdraws.empty:
                    message += "\n   🔸 الصرفيات:"
                    for _, row in withdraws.iterrows():
                        destination = row.get('destination', 'غير محدد')
                        message += f"\n      • {row['item_name']} ({row['brand']}): -{int(row['quantity'])} → {destination}"
    
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

# --- التبويب 1: الجرد ---
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
            st.dataframe(
                disp[['name', 'brand', 'quantity']].rename(
                    columns={'name': 'الصنف', 'brand': 'الماركة', 'quantity': 'الكمية'}
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

# --- التبويب 2: التوريد ---
with tab2:
    st.header("توريد بضاعة")
    
    if 'supply_pending' not in st.session_state:
        st.session_state.supply_pending = False
        st.session_state.supply_data = {}
    
    with st.form("supply_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            t_wh = st.selectbox("إلى مخزن:", wh_list, key="supply_warehouse")
            n = st.text_input("اسم الصنف *", key="supply_name").strip()
            b = st.text_input("الماركة *", key="supply_brand").strip()
        with col2:
            q = st.number_input("الكمية الموردة *", min_value=1, value=1, key="supply_qty")
            notes = st.text_area("ملاحظات (اختياري)", key="supply_notes")
        
        submitted = st.form_submit_button("متابعة التوريد", use_container_width=True)
        
        if submitted:
            if not n or not b:
                st.error("الرجاء إدخال اسم الصنف والماركة")
            else:
                st.session_state.supply_pending = True
                st.session_state.supply_data = {
                    'warehouse': t_wh,
                    'name': n,
                    'brand': b,
                    'quantity': q,
                    'notes': notes
                }
                st.rerun()
    
    if st.session_state.supply_pending:
        @st.dialog("تأكيد التوريد", width="large")
        def show_supply_dialog():
            data = st.session_state.supply_data
            st.write(f"""
            **تفاصيل التوريد:**
            - الصنف: {data['name']}
            - الماركة: {data['brand']}
            - المخزن: {data['warehouse']}
            - الكمية الموردة: {data['quantity']}
            """)
            if data['notes']:
                st.write(f"- ملاحظات: {data['notes']}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ تأكيد", use_container_width=True):
                    existing = supabase.table("inventory").select("*").eq("name", data['name']).eq("brand", data['brand']).eq("warehouse", data['warehouse']).execute()
                    if existing.data and len(existing.data) > 0:
                        old_qty = int(existing.data[0]['quantity'])
                        new_qty = old_qty + data['quantity']
                        supabase.table("inventory").update({"quantity": new_qty}).eq("id", existing.data[0]['id']).execute()
                        save_transaction("توريد", data['name'], data['brand'], data['quantity'], data['warehouse'])
                        send_telegram_supply(data['name'], data['brand'], data['quantity'], data['warehouse'], new_qty, data['notes'])
                        st.success(f"تم تحديث الكمية: {data['name']} ({data['brand']}) - الكمية الجديدة: {new_qty}")
                    else:
                        supabase.table("inventory").insert({"name": data['name'], "brand": data['brand'], "quantity": data['quantity'], "warehouse": data['warehouse']}).execute()
                        save_transaction("توريد", data['name'], data['brand'], data['quantity'], data['warehouse'])
                        send_telegram_supply(data['name'], data['brand'], data['quantity'], data['warehouse'], data['quantity'], data['notes'])
                        st.success(f"تم إضافة صنف جديد: {data['name']} ({data['brand']}) - الكمية: {data['quantity']}")
                    
                    st.session_state.supply_pending = False
                    st.session_state.supply_data = {}
                    st.cache_resource.clear()
                    st.rerun()
            with col2:
                if st.button("❌ إلغاء", use_container_width=True):
                    st.session_state.supply_pending = False
                    st.session_state.supply_data = {}
                    st.rerun()
        
        show_supply_dialog()

# --- التبويب 3: الصرف ---
with tab3:
    st.header("صرف بضاعة")
    if not inv_df.empty:
        source_wh = st.selectbox("اصرف من:", wh_list, key="withdraw_warehouse")
        items = inv_df[(inv_df['warehouse'] == source_wh) & (inv_df['quantity'] > 0)]
        
        if 'withdraw_pending' not in st.session_state:
            st.session_state.withdraw_pending = False
            st.session_state.withdraw_data = {}
        
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
                
                submitted = st.form_submit_button("متابعة الصرف", use_container_width=True)
                
                if submitted:
                    if not dst:
                        st.error("الرجاء إدخال الجهة المستلمة")
                    elif q_o <= 0:
                        st.error("الرجاء إدخال كمية صحيحة")
                    else:
                        sel_idx = item_options.index(sel_item_full)
                        row = items.iloc[sel_idx]
                        if q_o > int(row['quantity']):
                            st.error(f"الكمية غير متوفرة! المتاح: {row['quantity']}")
                        else:
                            st.session_state.withdraw_pending = True
                            st.session_state.withdraw_data = {
                                'warehouse': source_wh,
                                'name': row['name'],
                                'brand': row['brand'],
                                'quantity': q_o,
                                'remaining': int(row['quantity']) - q_o,
                                'destination': dst,
                                'row_id': row['id']
                            }
                            st.rerun()
            
            if st.session_state.withdraw_pending:
                @st.dialog("تأكيد الصرف", width="large")
                def show_withdraw_dialog():
                    data = st.session_state.withdraw_data
                    st.write(f"""
                    **تفاصيل الصرف:**
                    - الصنف والماركة: {data['name']} ({data['brand']})
                    - المخزن: {data['warehouse']}
                    - الكمية المطلوبة: {data['quantity']}
                    - الجهة المستلمة: {data['destination']}
                    - الكمية المتبقية بعد الصرف: {data['remaining']}
                    """)
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ تأكيد", use_container_width=True):
                            new_qty = data['remaining']
                            supabase.table("inventory").update({"quantity": new_qty}).eq("id", data['row_id']).execute()
                            save_transaction("صرف", str(data['name']), str(data['brand']), data['quantity'], data['warehouse'], data['destination'])
                            send_telegram_withdraw(str(data['name']), str(data['brand']), data['quantity'], data['warehouse'], data['destination'], new_qty)
                            st.success(f"تم صرف {data['quantity']} من {data['name']} إلى {data['destination']}")
                            st.session_state.withdraw_pending = False
                            st.session_state.withdraw_data = {}
                            st.cache_resource.clear()
                            st.rerun()
                    with col2:
                        if st.button("❌ إلغاء", use_container_width=True):
                            st.session_state.withdraw_pending = False
                            st.session_state.withdraw_data = {}
                            st.rerun()
                
                show_withdraw_dialog()
        else:
            st.warning(f"المخزن {source_wh} فارغ")
    else:
   