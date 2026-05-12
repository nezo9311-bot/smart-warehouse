import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, time
import requests
import os
import numpy as np
import pytz
import threading
import time as time_module

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = "8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM"
CHAT_ID = "5716145319"

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
    try:
        cleaned = str(value).strip()
        if cleaned.lower() in ['nan', 'none', 'null', '', 'unknown', 'nat']:
            return None
        return cleaned
    except:
        return None

def get_data(table):
    try:
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
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return pd.DataFrame()

def get_transactions(warehouse=None, date=None):
    try:
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
    except:
        return pd.DataFrame()

def save_transaction(trans_type, item_name, brand, quantity, warehouse, destination=None):
    try:
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
    except:
        return False

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message}, timeout=5)
    except:
        pass

def send_telegram_supply(item_name, brand, quantity, warehouse, notes=""):
    message = f"📥 توريد جديد:\n📦 الصنف: {item_name}\n🏷️ الماركة: {brand}\n🏢 المخزن: {warehouse}\n🔢 الكمية: {quantity}"
    if notes:
        message += f"\n📝 ملاحظات: {notes}"
    send_telegram_message(message)

def send_telegram_withdraw(item_name, brand, quantity, warehouse, destination):
    message = f"📤 صرف:\n📦 الصنف: {item_name}\n🏷️ الماركة: {brand}\n🏢 من مخزن: {warehouse}\n👤 الجهة: {destination}\n🔢 الكمية: {quantity}"
    send_telegram_message(message)

def send_telegram_delete(item_name, brand, quantity, warehouse):
    message = f"🗑️ حذف صنف:\n📦 الصنف: {item_name}\n🏷️ الماركة: {brand}\n🏢 المخزن: {warehouse}\n🔢 الكمية المحذوفة: {quantity}"
    send_telegram_message(message)

def send_daily_report():
    try:
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
        
        send_telegram_message(message)
        return True
    except Exception as e:
        print(f"Error sending daily report: {str(e)}")
        return False

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

try:
    start_scheduler()
except:
    pass

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
    try:
        return sorted(clean_list)
    except:
        return default_warehouses

try:
    wh_list = build_warehouse_list()
except:
    wh_list = ["مخزن البخاري", "مخزن الجديد"]

inv_df = get_data("inventory")

st.sidebar.title("مستودعات النذير")

if not inv_df.empty:
    st.sidebar.metric("إجمالي الأصناف", len(inv_df))
    st.sidebar.metric("عدد المخازن", len(wh_list))
    try:
        total_qty = inv_df['quantity'].sum()
        st.sidebar.metric("إجمالي الكميات", int(total_qty))
    except:
        pass

if st.sidebar.button("📊 إرسال تقرير يومي الآن", use_container_width=True):
    with st.spinner("جاري إرسال التقرير..."):
        if send_daily_report():
            st.sidebar.success("تم إرسال التقرير!")
        else:
            st.sidebar.error("فشل في إرسال التقرير")

tab1, tab2, tab3, tab4 = st.tabs(["جرد المخازن", "توريد", "صرف", "سجل التحركات والإدارة"])

with tab1:
    st.header("جرد المخازن")
    col1, col2 = st.columns([2, 1])
    with col1:
        if wh_list:
            sel_wh = st.selectbox("اختر المخزن", wh_list, key="tab1_warehouse")
        else:
            st.warning("لا توجد مخازن متاحة")
            sel_wh = None
    with col2:
        search_term = st.text_input("بحث عن صنف", key="search_inventory")
    
    if sel_wh and not inv_df.empty:
        disp = inv_df[inv_df['warehouse'] == sel_wh].copy()
        if search_term and not disp.empty:
            try:
                name_match = disp['name'].astype(str).str.contains(search_term, case=False, na=False)
                brand_match = disp['brand'].astype(str).str.contains(search_term, case=False, na=False)
                disp = disp[name_match | brand_match]
            except:
                pass
        if not disp.empty:
            st.dataframe(disp[['name', 'brand', 'quantity']].rename(columns={'name': 'الصنف', 'brand': 'الماركة', 'quantity': 'الكمية'}), use_container_width=True, hide_index=True)
            try:
                total_qty = disp['quantity'].sum()
                st.info(f"إجمالي الكميات في {sel_wh}: {int(total_qty)}")
            except:
                pass
        else:
            st.info(f"لا توجد نتائج في {sel_wh}")
    else:
        st.info("اختر مخزناً لعرض محتوياته")

with tab2:
    st.header("توريد بضاعة")
    if wh_list:
        with st.form("supply_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                t_wh = st.selectbox("إلى مخزن:", wh_list, key="supply_warehouse")
                n = st.text_input("اسم الصنف *", key="supply_name").strip()
                b = st.text_input("الماركة *", key="supply_brand").strip()
            with col2:
                q = st.number_input("الكمية الموردة *", min_value=1, value=1, key="supply_qty")
                notes = st.text_area("ملاحظات (اختياري)", key="supply_notes")
            
            submitted = st.form_submit_button("حفظ التوريد", use_container_width=True)
            
            if submitted:
                if not n or not b:
                    st.error("الرجاء إدخال اسم الصنف والماركة")
                else:
                    with st.spinner("جاري الحفظ..."):
                        try:
                            existing = supabase.table("inventory").select("*").eq("name", n).eq("brand", b).eq("warehouse", t_wh).execute()
                            
                            if existing.data and len(existing.data) > 0:
                                old_qty = int(existing.data[0]['quantity'])
                                new_qty = old_qty + q
                                supabase.table("inventory").update({"quantity": new_qty}).eq("id", existing.data[0]['id']).execute()
                                save_transaction("توريد", n, b, q, t_wh)
                                send_telegram_supply(n, b, q, t_wh, notes)
                                st.success(f"تم تحديث الكمية: {n} ({b}) - الكمية الجديدة: {new_qty}")
                            else:
                                supabase.table("inventory").insert({"name": n, "brand": b, "quantity": q, "warehouse": t_wh}).execute()
                                save_transaction("توريد", n, b, q, t_wh)
                                send_telegram_supply(n, b, q, t_wh, notes)
                                st.success(f"تم إضافة صنف جديد: {n} ({b}) - الكمية: {q}")
                            
                            st.cache_resource.clear()
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"حدث خطأ: {str(e)}")
    else:
        st.warning("لا توجد مخازن متاحة")

with tab3:
    st.header("صرف بضاعة")
    if not inv_df.empty and wh_list:
        source_wh = st.selectbox("اصرف من:", wh_list, key="withdraw_warehouse")
        items = inv_df[(inv_df['warehouse'] == source_wh) & (inv_df['quantity'] > 0)]
        if not items.empty:
            with st.form("withdraw_form"):
                col1, col2 = st.columns(2)
                with col1:
                    item_options = []
                    for idx, row in items.iterrows():
                        try:
                            option_text = f"{row['name']} ({row['brand']}) - المتاح: {row['quantity']}"
                            item_options.append(option_text)
                        except:
                            continue
                    if item_options:
                        sel_item_full = st.selectbox("اختر الصنف", item_options, key="withdraw_item")
                        q_o = st.number_input("الكمية المطلوبة *", min_value=1, value=1, key="withdraw_qty")
                    else:
                        st.warning("لا توجد خيارات متاحة")
                        sel_item_full = None
                with col2:
                    dst = st.text_input("الجهة المستلمة *", key="withdraw_dest")
                
                submitted = st.form_submit_button("تأكيد الصرف", use_container_width=True)
                
                if submitted and sel_item_full:
                    if not dst:
                        st.error("الرجاء إدخال الجهة المستلمة")
                    else:
                        try:
                            sel_idx = item_options.index(sel_item_full)
                            row = items.iloc[sel_idx]
                            if q_o > int(row['quantity']):
                                st.error(f"الكمية غير متوفرة! المتاح: {row['quantity']}")
                            else:
                                with st.spinner("جاري الصرف..."):
                                    new_qty = int(row['quantity']) - q_o
                                    supabase.table("inventory").update({"quantity": new_qty}).eq("id", row['id']).execute()
                                    save_transaction("صرف", str(row['name']), str(row['brand']), q_o, source_wh, dst.strip())
                                    send_telegram_withdraw(str(row['name']), str(row['brand']), q_o, source_wh, dst.strip())
                                    st.success(f"تم صرف {q_o} من {row['name']} إلى {dst}")
                                    st.cache_resource.clear()
                                    st.rerun()
                        except Exception as e:
                            st.error(f"حدث خطأ: {str(e)}")
        else:
            st.warning(f"المخزن {source_wh} فارغ")
    else:
        st.info("قاعدة البيانات فارغة")

with tab4:
    st.header("سجل التحركات والإدارة")
    admin_tab1, admin_tab2 = st.tabs(["سجل التحركات", "حذف الأصناف"])
    
    with admin_tab1:
        st.subheader("سجل التحركات اليومية")
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            filter_options = ["الكل"] + wh_list if wh_list else ["الكل"]
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
                    transactions_df['date'] = transactions_df['created_at'].dt.strftime('%Y-%m-%d')
                    transactions_df['time'] = transactions_df['created_at'].dt.strftime('%H:%M:%S')
                display_df = transactions_df.rename(columns={'type': 'النوع', 'item_name': 'الصنف', 'brand': 'الماركة', 'quantity': 'الكمية', 'warehouse': 'المخزن', 'destination': 'الجهة'})
                display_columns = ['النوع', 'date', 'time', 'الصنف', 'الماركة', 'الكمية', 'المخزن', 'الجهة']
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
        if not inv_df.empty and wh_list:
            del_warehouse = st.selectbox("اختر المخزن", wh_list, key="delete_warehouse")
            del_items = inv_df[inv_df['warehouse'] == del_warehouse]
            if not del_items.empty:
                delete_options = []
                for idx, row in del_items.iterrows():
                    try:
                        option = f"{row['name']} | {row['brand']} | الكمية: {row['quantity']}"
                        delete_options.append(option)
                    except:
                        continue
                if delete_options:
                    item_to_delete = st.selectbox("اختر الصنف للحذف", delete_options, key="delete_item")
                    if st.button("حذف نهائي", type="primary", use_container_width=True):
                        try:
                            idx = delete_options.index(item_to_delete)
                            item = del_items.iloc[idx]
                            save_transaction("حذف", str(item['name']), str(item['brand']), int(item['quantity']), del_warehouse, "حذف من النظام")
                            send_telegram_delete(str(item['name']), str(item['brand']), int(item['quantity']), del_warehouse)
                            supabase.table("inventory").delete().eq("id", item['id']).execute()
                            st.success(f"تم حذف {item['name']} ({item['brand']})"}