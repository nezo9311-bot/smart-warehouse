tab1, tab2, tab3, tab4 = st.tabs(["إدخال", "إخراج", "المخزون", "الإدارة"])

# ================= إدخال =================
with tab1:
    st.subheader("إدخال بضاعة")

    with st.form("add_form"):
        name = st.text_input("الصنف")
        brand = st.text_input("الماركة")
        qty = st.number_input("الكمية", min_value=1)

        submit = st.form_submit_button("حفظ")

        if submit:
            add_item(db, name, brand, qty)
            st.success("تم الإدخال")

# ================= إخراج =================
with tab2:
    st.subheader("إخراج بضاعة")

    conn = sqlite3.connect(db)
    data = pd.read_sql("SELECT * FROM inventory", conn)
    conn.close()

    if data.empty:
        st.info("لا يوجد مخزون")
    else:
        name = st.selectbox("الصنف", data["name"].unique())
        filtered = data[data["name"] == name]

        brand = st.selectbox("الماركة", filtered["brand"].unique())
        available = filtered[filtered["brand"] == brand]["quantity"].values[0]

        st.write("المتوفر:", available)

        qty = st.number_input("الكمية", 1, int(available))
        dest = st.text_input("الجهة")

        if st.button("تنفيذ"):
            if remove_item(db, name, brand, qty, dest):
                st.success("تم الإخراج")
            else:
                st.error("الكمية غير كافية")

# ================= المخزون =================
with tab3:
    st.subheader("المخزون")

    conn = sqlite3.connect(db)
    inv = pd.read_sql("SELECT name AS الصنف, brand AS الماركة, quantity AS الكمية FROM inventory", conn)
    mov = pd.read_sql("""
        SELECT 
        type AS النوع,
        name AS الصنف,
        brand AS الماركة,
        quantity AS الكمية,
        destination AS الجهة,
        date AS التاريخ
        FROM movements ORDER BY date DESC
    """, conn)
    conn.close()

    st.dataframe(inv)
    st.dataframe(mov)

# ================= الإدارة =================
with tab4:
    st.subheader("لوحة الإدارة")

    warehouses = get_warehouses()

    wh_select = st.selectbox("اختر المخزن", warehouses)
    db_admin = db_path(wh_select)

    conn = sqlite3.connect(db_admin)
    inv = pd.read_sql("SELECT * FROM inventory", conn)
    conn.close()

    st.write("المخزون الحالي")

    if inv.empty:
        st.info("المخزن فارغ")
    else:
        for i, row in inv.iterrows():
            col1, col2, col3, col4 = st.columns(4)

            col1.write(row["name"])
            col2.write(row["brand"])
            col3.write(row["quantity"])

            if col4.button("حذف", key=f"del_{i}"):
                conn = sqlite3.connect(db_admin)
                c = conn.cursor()
                c.execute("DELETE FROM inventory WHERE name=? AND brand=?", (row["name"], row["brand"]))
                conn.commit()
                conn.close()
                st.rerun()

    st.divider()

    st.write("إضافة أو تعديل صنف")

    name = st.text_input("الصنف", key="admin_name")
    brand = st.text_input("الماركة", key="admin_brand")
    qty = st.number_input("الكمية", min_value=0, key="admin_qty")

    if st.button("حفظ في الإدارة"):
        add_item(db_admin, name, brand, qty)
        st.success("تم التحديث")
        st.rerun()