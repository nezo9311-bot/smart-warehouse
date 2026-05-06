import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import requests

# ---------------- Telegram ----------------
TELEGRAM_TOKEN = os.getenv("8691308758:AAFNrLc7UAofgEGvYi-s9-qJB20mqA9n4XM")
CHAT_ID = os.getenv("5716145319")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except:
        pass

# ---------------- Warehouses ----------------
WAREHOUSE_DIR = "warehouses"

if not os.path.exists(WAREHOUSE_DIR):
    os.makedirs(WAREHOUSE_DIR)

def get_warehouses():
    return [f.replace(".db", "") for f in os.listdir(WAREHOUSE_DIR) if f.endswith(".db")]

def create_warehouse(name):
    conn = sqlite3.connect(f"{WAREHOUSE_DIR}/{name}.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        name TEXT,
        brand TEXT,
        quantity INTEGER,
        PRIMARY KEY(name, brand)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS movements (
        type TEXT,
        name TEXT,
        brand TEXT,
        quantity INTEGER,
        destination TEXT,
        date TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def db_path(name):
    return f"{WAREHOUSE_DIR}/{name}.db"

# ---------------- Operations ----------------
def add_item(db, name, brand, qty):
    conn = sqlite3.connect(db)
    c = conn.cursor()

    res = c.execute(
        "SELECT quantity FROM inventory WHERE name=? AND brand=?",
        (name, brand)
    ).fetchone()

    if res:
        c.execute(
            "UPDATE inventory SET quantity = quantity + ? WHERE name=? AND brand=?",
            (qty, name, brand)
        )
    else:
        c.execute(
            "INSERT INTO inventory VALUES (?, ?, ?)",
            (name, brand, qty)
        )

    c.execute(
        "INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
        ("IN", name, brand, qty, "", datetime.now())
    )

    conn.commit()
    conn.close()

    send_telegram(f"Stock Added\n{name} ({brand})\nQty: {qty}")


def remove_item(db, name, brand, qty, dest):
    conn = sqlite3.connect(db)
    c = conn.cursor()

    res = c.execute(
        "SELECT quantity FROM inventory WHERE name=? AND brand=?",
        (name, brand)
    ).fetchone()

    if res and res[0] >= qty:
        new_qty = res[0] - qty

        c.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE name=? AND brand=?",
            (qty, name, brand)
        )

        c.execute(
            "INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?)",
            ("OUT", name, brand, qty, dest, datetime.now())
        )

        conn.commit()
        conn.close()

        send_telegram(f"Stock Removed\n{name} ({brand})\nQty: {qty}\nTo: {dest}")

        if new_qty <= 5:
            send_telegram(f"Low Stock Warning\n{name} ({brand}) Remaining: {new_qty}")

        return True

    conn.close()
    return False

# ---------------- UI ----------------
def main():
    st.set_page_config(page_title="Warehouse System", layout="wide")

    st.title("Warehouse Management System")

    # ---------- Warehouses ----------
    st.sidebar.header("Warehouses")

    warehouses = get_warehouses()

    new_wh = st.sidebar.text_input("Create warehouse")
    if st.sidebar.button("Create"):
        if new_wh:
            create_warehouse(new_wh)
            st.rerun()

    if not warehouses:
        st.warning("No warehouses available")
        return

    selected = st.sidebar.selectbox("Select warehouse", warehouses)
    db = db_path(selected)

    tab1, tab2, tab3 = st.tabs(["Add Stock", "Remove Stock", "Dashboard"])

    # ---------------- Add ----------------
    with tab1:
        st.subheader("Add Stock")

        conn = sqlite3.connect(db)
        data = pd.read_sql("SELECT * FROM inventory", conn)
        conn.close()

        name = st.selectbox("Product", ["New"] + list(data['name'].unique()))

        if name == "New":
            name = st.text_input("Product name")
            brand = st.text_input("Brand")
        else:
            brands = data[data['name'] == name]['brand'].unique()
            brand = st.selectbox("Brand", list(brands) if len(brands) > 0 else ["New"])

            if brand == "New":
                brand = st.text_input("New brand")

        qty = st.number_input("Quantity", min_value=1)

        if st.button("Save"):
            add_item(db, name, brand, qty)
            st.success("Added successfully")

    # ---------------- Remove ----------------
    with tab2:
        st.subheader("Remove Stock")

        conn = sqlite3.connect(db)
        data = pd.read_sql("SELECT * FROM inventory", conn)
        conn.close()

        if data.empty:
            st.info("No stock available")
        else:
            name = st.selectbox("Product", data['name'].unique())
            filtered = data[data['name'] == name]

            options = [
                f"{r['brand']} | Remaining: {r['quantity']}"
                for _, r in filtered.iterrows()
            ]

            selected_brand = st.selectbox("Brand", options)
            brand = selected_brand.split(" |")[0]

            current_qty = filtered[filtered['brand'] == brand]['quantity'].values[0]

            st.write("Available:", current_qty)

            qty = st.number_input("Quantity", min_value=1, max_value=int(current_qty))
            dest = st.text_input("Destination")

            if st.button("Remove"):
                ok = remove_item(db, name, brand, qty, dest)
                if ok:
                    st.success("Removed successfully")
                else:
                    st.error("Not enough stock")

    # ---------------- Dashboard ----------------
    with tab3:
        st.subheader("Inventory")

        conn = sqlite3.connect(db)
        inv = pd.read_sql("SELECT * FROM inventory", conn)
        mov = pd.read_sql("SELECT * FROM movements ORDER BY date DESC", conn)
        conn.close()

        st.dataframe(inv)
        st.dataframe(mov)


if __name__ == "__main__":
    main()