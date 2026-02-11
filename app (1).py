import requests
import numpy as np
import pandas as pd
import pytz
import os
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime
from PIL import Image
import csv

# --- CONFIGURASI PAGE (WAJIB PALING ATAS) ---
st.set_page_config(layout="wide", page_title="SIBIMA Performance Dashboard")

# --- CSS CUSTOM UNTUK FULL WIDTH ---
st.markdown("""
    <style>
    .block-container {
        padding-top: 3rem;
        padding-bottom: 1rem;
        padding-left: 5rem;
        padding-right: 5rem;
        max-width: 100%;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. KONFIGURASI DATA & API ---
timezone = pytz.timezone('Asia/Jakarta')
now = datetime.now(timezone)
today = now.strftime("%Y-%m-%d")

TOKEN = "f019488b5efcf31b721942570501aeba52284e1f55c2b337d619a139b6ca"
BASE_URL = "https://eas.sibima.id/api/"

@st.cache_data(ttl=600) # Cache selama 10 menit agar tidak terus-menerus hit API
def get_api_data(endpoint):
    url = f"{BASE_URL}{endpoint}"
    params = {"date_start": "2025-12-01", "date_end": today, "token": TOKEN}
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return pd.DataFrame(response.json()['data'])
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# Pengambilan Data
df_sq = get_api_data("sales-quotations")
df_so = get_api_data("sales-orders")
df_pr = get_api_data("purchase-requests")
df_po = get_api_data("purchase-orders")
df_grn = get_api_data("goods-receipt-notes")
df_do = get_api_data("delivery-orders")
df_si = get_api_data("sales-invoices")

# Fungsi Expand
def expand_items(df):
    if df.empty: return df
    df_items = df.explode('items')
    df_items = pd.concat([df_items.drop(['items'], axis=1), df_items['items'].apply(pd.Series)], axis=1)
    return df_items

df_sq_expanded = expand_items(df_sq)
df_so_expanded = expand_items(df_so)
df_pr_expanded = expand_items(df_pr)
df_po_expanded = expand_items(df_po)
df_grn_expanded = expand_items(df_grn)
df_do_expanded = expand_items(df_do)
df_si_expanded = expand_items(df_si)

# Rename Kolom Duplikat
def rename_duplicate_columns(df, target_col, new_name):
    if df is None or df.empty: return df
    new_cols = []
    counter = 0
    for col in df.columns:
        if col == target_col:
            new_cols.append(col if counter == 0 else new_name)
            counter += 1
        else:
            new_cols.append(col)
    df.columns = new_cols
    return df

dfs = [df_sq_expanded, df_so_expanded, df_pr_expanded, df_po_expanded, df_grn_expanded, df_do_expanded, df_si_expanded]
for i in range(len(dfs)):
    dfs[i] = rename_duplicate_columns(dfs[i], 'total', 'total_item')
    dfs[i] = rename_duplicate_columns(dfs[i], 'transaction_total', 'transaction_total_item')

df_sq_expanded, df_so_expanded, df_pr_expanded, df_po_expanded, df_grn_expanded, df_do_expanded, df_si_expanded = dfs

# Cleaning Data
def clean_expanded_data(df: pd.DataFrame) -> pd.DataFrame:
    # 1. Guard clause
    if df is None or df.empty:
        return df

    # 2. Normalisasi nama kolom jadi string lowercase
    cols = df.columns.astype(str)
    df = df.copy()
    df.columns = cols

    # 3. Deteksi kolom tanggal
    date_keywords = ('date', 'transaction_date', 'due_date')
    date_cols = [
        c for c in df.columns
        if any(k in c.lower() for k in date_keywords)
    ]

    # 4. Convert ke datetime
    for c in date_cols:
        df[c] = pd.to_datetime(df[c], errors='coerce')

    # 5. Deteksi kolom numerik
    num_keywords = ('price', 'quantity', 'total')
    num_cols = [
        c for c in df.columns
        if any(k in c.lower() for k in num_keywords)
    ]

    # 6. Convert ke numeric
    for c in num_cols:
        df[c] = (
            pd.to_numeric(df[c], errors='coerce')
              .fillna(0)
        )

    # 7. Drop duplicate rows
    return df.drop_duplicates().reset_index(drop=True)


df_sq_expanded = clean_expanded_data(df_sq_expanded)
df_so_expanded = clean_expanded_data(df_so_expanded)
df_pr_expanded = clean_expanded_data(df_pr_expanded)
df_po_expanded = clean_expanded_data(df_po_expanded)
df_grn_expanded = clean_expanded_data(df_grn_expanded)
df_do_expanded = clean_expanded_data(df_do_expanded)
df_si_expanded = clean_expanded_data(df_si_expanded)

# --- FILTER TANGGAL (KALENDER) ---
st.sidebar.header("📅 Filter Periode")

# Menentukan rentang tanggal default (awal bulan ini sampai hari ini)
start_default = datetime(2025, 12, 1) # Sesuai date_start API
end_default = datetime.now()

selected_date_range = st.sidebar.date_input(
    "Pilih Rentang Tanggal:",
    value=(start_default, end_default),
    max_value=datetime.now()
)

# --- FILTER KATEGORI CUSTOMER ---
st.sidebar.header("👥 Pengelompokan Customer")

# 1. Pilih Kategori
category_options = ["Semua", "Consignment", "Project", "Reguler"]
selected_category = st.sidebar.selectbox("Pilih Kategori:", category_options)

# 2. Logika Penentuan customer_name berdasarkan kategori
# Ambil semua list customer unik dari dataframe asli
if not df_so_expanded.empty:
    all_cust_list = df_so_expanded['customer_name'].unique().tolist()
else:
    all_cust_list = []

# Tentukan list customer berdasarkan pilihan kategori
if selected_category == "Consignment":
    target_customers = ["EAS GROUP"]
elif selected_category == "Project":
    target_customers = ["WAHANA KONSTRUKSI MANDIRI"]
elif selected_category == "Reguler":
    # Reguler adalah semua customer KECUALI yang masuk kategori Consignment & Project
    exclude_list = ["EAS GROUP", "WAHANA KONSTRUKSI MANDIRI"]
    target_customers = [c for c in all_cust_list if c not in exclude_list]
else:
    target_customers = all_cust_list

# 3. (Opsional) Tampilkan Multiselect yang sudah ter-filter otomatis
# Ini agar user tetap bisa memilih nama spesifik di dalam kategori tersebut
final_selected_customers = st.sidebar.multiselect(
    "Detail Nama Customer:",
    options=target_customers,
    default=target_customers
)

def apply_realization_filter(df, start_date, end_date, customer_filter=None):
    """Filter ketat untuk transaksi yang terjadi HANYA di periode terpilih"""
    if df.empty: return df
    df = df.copy()
    
    if 'transaction_date' in df.columns:
        df['transaction_date'] = pd.to_datetime(df['transaction_date']).dt.tz_localize(None)
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        # HANYA yang masuk dalam rentang tanggal
        df = df[(df['transaction_date'] >= start_dt) & (df['transaction_date'] <= end_dt)]

    #if 'status_description' in df.columns and selected_status:
        #df = df[df['status_description'].isin(selected_status)]
    
    if 'customer_name' in df.columns and customer_filter:
        df = df[df['customer_name'].isin(customer_filter)]
    return df

def apply_balance_filter(df, start_date, end_date, customer_filter=None):
    """Filter untuk Outstanding: Data periode ini + Data lama yang belum selesai"""
    if df.empty: return df
    df = df.copy()
    
    if 'transaction_date' in df.columns:
        df['transaction_date'] = pd.to_datetime(df['transaction_date']).dt.tz_localize(None)
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        status_selesai = ['In Progress', 'Approved']
        
        # LOGIKA: (Dalam range tanggal) ATAU (Masa lalu yang belum selesai)
        mask_current = (df['transaction_date'] >= start_dt) & (df['transaction_date'] <= end_dt)
        mask_outstanding = (df['transaction_date'] < start_dt) & (df['status_description'].isin(status_selesai))
        
        df = df[mask_current | mask_outstanding]
        #df = df[mask_current]

    # Status filter untuk Balance biasanya lebih fleksibel, 
    # namun tetap kita terapkan sesuai pilihan user jika ada
    #if 'status_description' in df.columns and selected_status:
        #df = df[df['status_description'].isin(selected_status)]
    
    if 'customer_name' in df.columns and customer_filter:
        df = df[df['customer_name'].isin(customer_filter)]
    return df

if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
    sd, ed = selected_date_range

    # --- KELOMPOK REALIZATION (Hanya periode ini) ---
    df_so_real = apply_realization_filter(df_so_expanded, sd, ed, final_selected_customers)
    df_pr_real = apply_realization_filter(df_pr_expanded, sd, ed, final_selected_customers)
    df_po_real = apply_realization_filter(df_po_expanded, sd, ed, final_selected_customers)
    df_grn_real = apply_realization_filter(df_grn_expanded, sd, ed, final_selected_customers)
    df_do_real = apply_realization_filter(df_do_expanded, sd, ed, final_selected_customers)
    df_si_real = apply_realization_filter(df_si_expanded, sd, ed, final_selected_customers)
    
    # --- KELOMPOK BALANCE (Periode ini + Backlog) ---
    df_so_f = apply_balance_filter(df_so_expanded, sd, ed, final_selected_customers)
    df_pr_f = apply_balance_filter(df_pr_expanded, sd, ed, final_selected_customers)
    df_po_f = apply_balance_filter(df_po_expanded, sd, ed, final_selected_customers)
    df_grn_f = apply_balance_filter(df_grn_expanded, sd, ed, final_selected_customers)
    df_do_f = apply_balance_filter(df_do_expanded, sd, ed, final_selected_customers)
    df_si_f = apply_balance_filter(df_si_expanded, sd, ed, final_selected_customers)


# --- PROSES PERHITUNGAN (Menggunakan Data Transaksi) ---
def count_unique_transactions(df):
    return df['transaction_number'].nunique() if not df.empty else 0

total_trans_so = count_unique_transactions(df_so_f)
total_trans_pr = count_unique_transactions(df_pr_f) 
total_trans_po = count_unique_transactions(df_po_f)
total_trans_grn = count_unique_transactions(df_grn_f)
total_trans_do = count_unique_transactions(df_do_f)
total_trans_si = count_unique_transactions(df_si_f)


# --- PROSES PERHITUNGAN (Menggunakan Data Item) ---
#total_item_so = df_so_f.groupby('transaction_number')['product_id'].nunique().sum() if not df_so_f.empty else 0
total_item_so = df_so_f[['transaction_number', 'product_id']].drop_duplicates().shape[0]
total_item_pr = df_pr_f[['transaction_number', 'product_id']].drop_duplicates().shape[0]
#total_item_pr = df_pr_f.groupby('transaction_number')['product_id'].nunique().sum() if not df_pr_f.empty else 0
#total_item_pr = df_pr_f['product_id'].nunique() if not df_pr_f.empty else 0
total_item_po = df_po_f[['transaction_number', 'product_id']].drop_duplicates().shape[0]
#total_item_po = df_po_f.groupby('transaction_number')['product_id'].nunique().sum() if not df_po_f.empty else 0
total_item_grn = df_grn_f[['transaction_number', 'product_id']].drop_duplicates().shape[0]
#total_item_grn = df_grn_f.groupby('transaction_number')['product_id'].nunique().sum() if not df_grn_f.empty else 0
total_item_do = df_do_f[['transaction_number', 'product_id']].drop_duplicates().shape[0]
#total_item_do = df_do_f.groupby('transaction_number')['product_id'].nunique().sum() if not df_do_f.empty else 0
total_item_si = df_si_f[['transaction_number', 'product_id']].drop_duplicates().shape[0]
#total_item_si = df_si_f.groupby('transaction_number')['product_id'].nunique().sum() if not df_si_f.empty else 0

df_unique_so = df_so_f.drop_duplicates(subset=['transaction_number', 'product_id'])
df_unique_pr = df_pr_f.drop_duplicates(subset=['transaction_number', 'product_id'])
df_unique_po = df_po_f.drop_duplicates(subset=['transaction_number', 'product_id'])
df_unique_grn = df_grn_f.drop_duplicates(subset=['transaction_number', 'product_id'])
df_unique_do = df_do_f.drop_duplicates(subset=['transaction_number', 'product_id'])
df_unique_si = df_si_f.drop_duplicates(subset=['transaction_number', 'product_id'])

prog_so_pr = (total_item_pr / total_item_so * 100) if total_item_so > 0 else 0
prog_pr_po = (total_item_po / total_item_pr * 100) if total_item_pr > 0 else 0
prog_po_grn = (total_item_grn / total_item_po * 100) if total_item_po > 0 else 0
prog_grn_do = (total_item_do / total_item_grn * 100) if total_item_grn > 0 else 0
prog_do_si = (total_item_si / total_item_do * 100) if total_item_do > 0 else 0

net_revenue = df_si_real['total_item'].sum() if not df_si_real.empty else 0
gross_revenue = df_si_real['transaction_total_item'].sum() if not df_si_real.empty else 0

# --- RECONCILE LOGIC (Menggunakan Data _f) ---

#SO vs PR
#SO BALANCE
# --- SO vs PR #SO BALANCE (SESUAI LOGIKA SQL) ---

# 1. Pastikan kolom numerik tersedia dan bersih
cols_to_fix = ['price', 'quantity', 'discount', 'tax1_percentage', 'tax2_percentage']
for col in cols_to_fix:
    if col in df_so_f.columns:
        df_so_f[col] = pd.to_numeric(df_so_f[col], errors='coerce').fillna(0)

# --- SO vs PR #SO BALANCE (VERSI FIX) ---

# 1. Pastikan kolom di df_so_f sudah numerik sebelum diproses
df_so_f['tax1_percentage'] = pd.to_numeric(df_so_f['tax1_percentage'], errors='coerce').fillna(0)
df_so_f['tax2_percentage'] = pd.to_numeric(df_so_f['tax2_percentage'], errors='coerce').fillna(0)
df_so_f['discount'] = pd.to_numeric(df_so_f['discount'], errors='coerce').fillna(0)
df_so_f['price'] = pd.to_numeric(df_so_f['price'], errors='coerce').fillna(0)
df_so_f['quantity'] = pd.to_numeric(df_so_f['quantity'], errors='coerce').fillna(0)
df_so_f['transaction_number'] = df_so_f['transaction_number'].astype(str).str.strip().str.upper()
df_so_f['product_id'] = df_so_f['product_id'].astype(str).str.strip().str.upper()

# 2. Bersihkan data PR
# Pastikan kolom referensi di PR juga dibersihkan
df_pr_f['so_transaction_number'] = df_pr_f['so_transaction_number'].astype(str).str.strip().str.upper()
df_pr_f['product_id'] = df_pr_f['product_id'].astype(str).str.strip().str.upper()
df_pr_f['quantity'] = pd.to_numeric(df_pr_f['quantity'], errors='coerce').fillna(0)

# 2. Bersihkan data DO
# Pastikan kolom referensi di PR juga dibersihkan
df_do_f['so_transaction_number'] = df_do_f['so_transaction_number'].astype(str).str.strip().str.upper()
df_do_f['product_id'] = df_do_f['product_id'].astype(str).str.strip().str.upper()
df_do_f['quantity'] = pd.to_numeric(df_do_f['quantity'], errors='coerce').fillna(0)

# 2. Grouping SO: Ambil detail unik per item per transaksi
df_so_grouped = df_so_f.groupby(['transaction_number', 'product_id'], as_index=False).agg({
    'item_name': 'first',      # Mengambil nama item
    'customer_name': 'first',  # Mengambil nama customer
    'price': 'first',
    'quantity': 'sum',
    'discount': 'sum',
    'tax1_percentage': 'first',
    'tax2_percentage': 'first',
})

# 3. Grouping PR: Agregasi sisa quantity (PENTING: Harus unik per SO + Product)
df_pr_grouped_clean = df_pr_f.groupby(['so_transaction_number', 'product_id'], as_index=False).agg({
    'transaction_number' : 'first',
    'quantity': 'sum'
})

# 3. Grouping PR: Agregasi sisa quantity (PENTING: Harus unik per SO + Product)
df_do_grouped_clean = df_do_f.groupby(['so_transaction_number', 'product_id'], as_index=False).agg({
    'transaction_number' : 'first',
    'quantity': 'sum'
})

# 4. Merge
#Hitung Sisa Qty (Net Qty)
# Merge SO + PR + DO
# 1. Merge SO dengan PR

# Kita ambil 'transaction_number' dari PR dan langsung ubah namanya jadi 'transaction_number_pr'
reconcile = df_so_grouped.merge(
    df_pr_grouped_clean[['so_transaction_number', 'transaction_number', 'product_id', 'quantity']], 
    left_on=['transaction_number', 'product_id'], 
    right_on=['so_transaction_number', 'product_id'], 
    how='left'
).rename(columns={
    'quantity_x': 'quantity_so',
    'quantity_y': 'quantity_pr',
    'transaction_number_y': 'transaction_number_pr', # Jika bentrok
    'transaction_number_x': 'transaction_number_so'  # Jika bentrok
})

# Jika tidak bentrok saat merge pertama, kita rename manual kolom PR-nya
if 'transaction_number_y' not in reconcile.columns:
    reconcile = reconcile.rename(columns={'transaction_number': 'transaction_number_pr'})

# Buang kolom join agar tidak mengganggu merge berikutnya
reconcile = reconcile.drop(columns=['so_transaction_number'], errors='ignore')

# 2. Merge dengan DO
# Kita ambil 'transaction_number' dari DO dan ubah jadi 'transaction_number_do'
reconcile = reconcile.merge(
    df_do_grouped_clean[['so_transaction_number', 'product_id', 'transaction_number', 'quantity']], 
    left_on=['transaction_number_so', 'product_id'], # Gunakan kolom SO sebagai kunci
    right_on=['so_transaction_number', 'product_id'], 
    how='left'
).rename(columns={
    'quantity': 'quantity_do',
    'transaction_number': 'transaction_number_do'
})

# 3. Handle Nilai Kosong & Hitung Net Qty
reconcile[['quantity_pr', 'quantity_do']] = reconcile[['quantity_pr', 'quantity_do']].fillna(0)
# Isi nomor transaksi yang kosong (karena tidak ada match) dengan string '-'
reconcile[['transaction_number_pr', 'transaction_number_do']] = reconcile[['transaction_number_pr', 'transaction_number_do']].fillna('-')

reconcile['total_fulfilled'] = reconcile['quantity_pr'] + reconcile['quantity_do']
reconcile['net_qty'] = (reconcile['quantity_so'] - reconcile['total_fulfilled']).clip(lower=0)

# >> PERBAIKAN DI SINI: Ubah tipe data ke Integer <<
# Kita ubah semua kolom quantity menjadi integer untuk menghilangkan .0
cols_to_int = ['quantity_so', 'quantity_pr', 'quantity_do', 'net_qty']
for col in cols_to_int:
    if col in reconcile.columns:
        reconcile[col] = reconcile[col].astype(int)


# Rumus Rupiah (Pastikan kolom price/discount ada di df_so_grouped)
reconcile['unit_tax1'] = reconcile['price'] * (reconcile['tax1_percentage'] / 100)
reconcile['unit_tax2'] = reconcile['price'] * (reconcile['tax2_percentage'] / 100)

reconcile['so_balance_amount'] = (
    reconcile['net_qty'] * (
        reconcile['price'] - reconcile['discount'] + reconcile['unit_tax1'] + reconcile['unit_tax2']
    )
)

# 5. Summary
total_so_unpr2 = reconcile['so_balance_amount'].sum()
total_item_outstanding_so = reconcile['net_qty'].sum()
total_baris_pending = len(reconcile[reconcile['net_qty'] > 0])

# 4. Finalisasi Data untuk Export
# Pastikan semua kolom yang dipanggil di sini sudah ada di 'reconcile'
df_download_so = reconcile[[
    'transaction_number_so', 
    'transaction_number_pr',
    'transaction_number_do',
    'customer_name', 
    'product_id', 
    'item_name', 
    'price',
    'quantity_so', 
    'quantity_pr', 
    'quantity_do',
    'net_qty'
]].copy()

# Ubah format item_name
df_download_so['item_name'] = df_download_so['item_name'].str.replace(';', ' ', regex=False)

# Rename kolom untuk User
df_download_so.columns = [
    'No. Transaksi SO', 'No. Transaksi PR', 'No. Transaksi DO', 'Customer', 
    'ID Produk', 'Nama Barang', 'Harga Barang', 'Qty Order', 'Qty PR', 'Qty DO', 'Qty Outstanding'
]

df_download_so['Status'] = df_download_so['Qty Outstanding'].apply(lambda x: 'Complete' if x == 0 else 'Pending')

#PR vs PO
#PR BALANCE
# --- PR vs PO #PR BALANCE (SESUAI LOGIKA SQL) ---

# 1. Pastikan kolom numerik tersedia dan bersih
cols_to_fix = ['price', 'quantity', 'discount', 'tax1_percentage', 'tax2_percentage']
for col in cols_to_fix:
    if col in df_pr_f.columns:
        df_pr_f[col] = pd.to_numeric(df_pr_f[col], errors='coerce').fillna(0)

# --- PR vs PO #PR BALANCE (VERSI FIX) ---

# 1. Pastikan kolom di df_pr_f sudah numerik sebelum diproses
df_pr_f['tax1_percentage'] = pd.to_numeric(df_pr_f['tax1_percentage'], errors='coerce').fillna(0)
df_pr_f['tax2_percentage'] = pd.to_numeric(df_pr_f['tax2_percentage'], errors='coerce').fillna(0)
df_pr_f['discount'] = pd.to_numeric(df_pr_f['discount'], errors='coerce').fillna(0)
df_pr_f['price'] = pd.to_numeric(df_pr_f['price'], errors='coerce').fillna(0)
df_pr_f['quantity'] = pd.to_numeric(df_pr_f['quantity'], errors='coerce').fillna(0)
df_pr_f['transaction_number'] = df_pr_f['transaction_number'].astype(str).str.strip().str.upper()
df_pr_f['product_id'] = df_pr_f['product_id'].astype(str).str.strip().str.upper()

# 2. Bersihkan data PO
# Pastikan kolom referensi di PR juga dibersihkan
df_po_f['so_transaction_number'] = df_po_f['so_transaction_number'].astype(str).str.strip().str.upper()
df_po_f['product_id'] = df_po_f['product_id'].astype(str).str.strip().str.upper()
df_po_f['quantity'] = pd.to_numeric(df_po_f['quantity'], errors='coerce').fillna(0)

# 2. Grouping SO: Ambil detail unik per item per transaksi
df_pr_grouped = df_pr_f.groupby(['transaction_number', 'product_id'], as_index=False).agg({
    'item_name': 'first',      # Mengambil nama item
    'customer_name': 'first',  # Mengambil nama customer
    'price': 'first',
    'quantity': 'sum',
    'discount': 'sum',
    'tax1_percentage': 'first',
    'tax2_percentage': 'first'
})

# 3. Grouping PR: Agregasi sisa quantity (PENTING: Harus unik per PR + Product)
df_po_grouped_clean = df_po_f.groupby(['pr_transaction_number', 'product_id'], as_index=False).agg({
    'transaction_number' : 'first',
    'quantity': 'sum'
})

# 4. Merge
#Hitung Sisa Qty (Net Qty)
reconcile_pr_po = df_pr_grouped.merge(df_po_grouped_clean, left_on=['transaction_number', 'product_id'], 
                                     right_on=['pr_transaction_number', 'product_id'], how='left', suffixes=('_pr','_po'))
reconcile_pr_po['quantity_po'] = reconcile_pr_po['quantity_po'].fillna(0)
reconcile_pr_po['net_qty'] = (reconcile_pr_po['quantity_pr'] - reconcile_pr_po['quantity_po']).clip(lower=0)

# 4. HITUNG SALDO BERDASARKAN UNIT PRICE
# Rumus: Sisa Qty * (Harga Satuan - Diskon Satuan + Pajak Satuan)
reconcile_pr_po['unit_tax1'] = reconcile_pr_po['price'] * (reconcile_pr_po['tax1_percentage'] / 100)
reconcile_pr_po['unit_tax2'] = reconcile_pr_po['price'] * (reconcile_pr_po['tax2_percentage'] / 100)

reconcile_pr_po['pr_balance_amount'] = (
    reconcile_pr_po['net_qty'] * (
        reconcile_pr_po['price'] - 
        reconcile_pr_po['discount'] + 
        reconcile_pr_po['unit_tax1'] +
        reconcile_pr_po['unit_tax2'] 
    )
)

total_pr_unpr2 = reconcile_pr_po['pr_balance_amount'].sum()
#pr_belum_proses = reconcile_pr_po[reconcile_pr_po['pr_transaction_number'].isna()]
total_item_outstanding_pr = reconcile_pr_po['net_qty'].sum()
# Menghitung berapa banyak baris item yang masih outstanding
total_baris_pending = len(reconcile_pr_po[reconcile_pr_po['net_qty'] > 0])

# 1. Ubah format item_name
reconcile_pr_po['item_name'] = reconcile_pr_po['item_name'].str.replace(';', ' ', regex=False)
# 2. Ubah tipe data ke integer untuk menghilangkan .0
reconcile_pr_po['quantity_pr'] = reconcile_pr_po['quantity_pr'].astype(int)
reconcile_pr_po['quantity_po'] = reconcile_pr_po['quantity_po'].astype(int)
reconcile_pr_po['net_qty'] = reconcile_pr_po['net_qty'].astype(int)

df_download_pr = reconcile_pr_po[[
    'transaction_number_pr', 
    'transaction_number_po',
    'customer_name', 
    'product_id', 
    'item_name', 
    'price',
    'quantity_pr',      # Qty Awal
    'quantity_po',      # Qty yang sudah diproses
    'net_qty',          # Sisa Qty (Outstanding)
]].copy()

# 1. Ubah format item_name
df_download_pr['item_name'] = df_download_pr['item_name'].str.replace(';', ' ', regex=False)

# Rename kolom agar lebih user-friendly di Excel/CSV
df_download_pr.columns = [
    'No. Transaksi PR', 'No. Transaksi PO','Customer', 'ID Produk', 'Nama Barang', 'Harga Barang',
    'Qty Order', 'Qty Terproses', 'Qty Outstanding'
]

#PO vs GRN
# 1. Pastikan kolom numerik tersedia dan bersih
cols_to_fix = ['price', 'quantity', 'discount', 'tax1_percentage', 'tax2_percentage']
for col in cols_to_fix:
    if col in df_po_f.columns:
        df_po_f[col] = pd.to_numeric(df_po_f[col], errors='coerce').fillna(0)

# --- SO vs PR #SO BALANCE (VERSI FIX) ---

# 1. Pastikan kolom di df_po_f sudah numerik sebelum diproses
df_po_f['tax1_percentage'] = pd.to_numeric(df_po_f['tax1_percentage'], errors='coerce').fillna(0)
df_po_f['tax2_percentage'] = pd.to_numeric(df_po_f['tax2_percentage'], errors='coerce').fillna(0)
df_po_f['discount'] = pd.to_numeric(df_po_f['discount'], errors='coerce').fillna(0)
df_po_f['price'] = pd.to_numeric(df_po_f['price'], errors='coerce').fillna(0)
df_po_f['quantity'] = pd.to_numeric(df_po_f['quantity'], errors='coerce').fillna(0)
df_po_f['transaction_number'] = df_po_f['transaction_number'].astype(str).str.strip().str.upper()
df_po_f['product_id'] = df_po_f['product_id'].astype(str).str.strip().str.upper()

# 2. Bersihkan data GRN
# Pastikan kolom referensi di PR juga dibersihkan
df_grn_f['po_transaction_number'] = df_grn_f['po_transaction_number'].astype(str).str.strip().str.upper()
df_grn_f['product_id'] = df_grn_f['product_id'].astype(str).str.strip().str.upper()
df_grn_f['quantity'] = pd.to_numeric(df_grn_f['quantity'], errors='coerce').fillna(0)

# 2. Grouping SO: Ambil detail unik per item per transaksi
df_po_grouped = df_po_f.groupby(['transaction_number', 'product_id'], as_index=False).agg({
    'item_name': 'first',      # Mengambil nama item
    'customer_name': 'first',  # Mengambil nama customer
    'price': 'first',
    'quantity': 'sum',
    'discount': 'sum',
    'tax1_percentage': 'first',
    'tax2_percentage': 'first',
})

# 3. Grouping PR: Agregasi sisa quantity (PENTING: Harus unik per SO + Product)
df_grn_grouped_clean = df_grn_f.groupby(['po_transaction_number', 'product_id'], as_index=False).agg({
    'transaction_number' : 'first',
    'quantity': 'sum'
})

# 4. Merge
#Hitung Sisa Qty (Net Qty)
reconcile_po_grn = df_po_grouped.merge(df_grn_grouped_clean, left_on=['transaction_number', 'product_id'], 
                                     right_on=['po_transaction_number', 'product_id'], how='left', suffixes=('_po','_grn'))
reconcile_po_grn['quantity_grn'] = reconcile_po_grn['quantity_grn'].fillna(0)
reconcile_po_grn['net_qty'] = (reconcile_po_grn['quantity_po'] - reconcile_po_grn['quantity_grn']).clip(lower=0)

# 4. HITUNG SALDO BERDASARKAN UNIT PRICE
# Rumus: Sisa Qty * (Harga Satuan - Diskon Satuan + Pajak Satuan)
reconcile_po_grn['unit_tax1'] = reconcile_po_grn['price'] * (reconcile_po_grn['tax1_percentage'] / 100)
reconcile_po_grn['unit_tax2'] = reconcile_po_grn['price'] * (reconcile_po_grn['tax2_percentage'] / 100)

reconcile_po_grn['po_balance_amount'] = (
    reconcile_po_grn['net_qty'] * (
        reconcile_po_grn['price'] - 
        reconcile_po_grn['discount'] + 
        reconcile_po_grn['unit_tax1'] +
        reconcile_po_grn['unit_tax2'] 
    )
)

total_po_unpr2 = reconcile_po_grn['po_balance_amount'].sum()
#po_belum_proses = reconcile_po_grn[reconcile_po_grn['transaction_number_grn'].isna()]
total_item_outstanding_po = reconcile_po_grn['net_qty'].sum()
# Menghitung berapa banyak baris item yang masih outstanding
total_baris_pending = len(reconcile_po_grn[reconcile_po_grn['net_qty'] > 0])

# 1. Ubah format item_name
reconcile_po_grn['item_name'] = reconcile_po_grn['item_name'].str.replace(';', ' ', regex=False)
# 2. Ubah tipe data ke integer untuk menghilangkan .0
reconcile_po_grn['quantity_po'] = reconcile_po_grn['quantity_po'].astype(int)
reconcile_po_grn['quantity_grn'] = reconcile_po_grn['quantity_grn'].astype(int)
reconcile_po_grn['net_qty'] = reconcile_po_grn['net_qty'].astype(int)

df_download_po = reconcile_po_grn[[
    'transaction_number_po', 
    'transaction_number_grn',
    'customer_name', 
    'product_id', 
    'item_name', 
    'price',
    'quantity_po',      # Qty Awal
    'quantity_grn',      # Qty yang sudah diproses
    'net_qty',          # Sisa Qty (Outstanding)
]].copy()

# 1. Ubah format item_name
df_download_po['item_name'] = df_download_po['item_name'].str.replace(';', ' ', regex=False)

# Rename kolom agar lebih user-friendly di Excel/CSV
df_download_po.columns = [
    'No. Transaksi PO', 'No. Transaksi GRN','Customer', 'ID Produk', 'Nama Barang', 'Harga Barang',
    'Qty Order', 'Qty Terproses', 'Qty Outstanding'
]

# GRN vs DO
# 1. Pastikan kolom numerik tersedia dan bersih
cols_to_fix = ['price', 'quantity', 'discount', 'tax1_percentage', 'tax2_percentage']
for col in cols_to_fix:
    if col in df_grn_f.columns:
        df_grn_f[col] = pd.to_numeric(df_grn_f[col], errors='coerce').fillna(0)

# --- SO vs PR #SO BALANCE (VERSI FIX) ---

# 1. Pastikan kolom di df_grn_f sudah numerik sebelum diproses
df_grn_f['tax1_percentage'] = pd.to_numeric(df_grn_f['tax1_percentage'], errors='coerce').fillna(0)
df_grn_f['tax2_percentage'] = pd.to_numeric(df_grn_f['tax2_percentage'], errors='coerce').fillna(0)
df_grn_f['discount'] = pd.to_numeric(df_grn_f['discount'], errors='coerce').fillna(0)
df_grn_f['price'] = pd.to_numeric(df_grn_f['price'], errors='coerce').fillna(0)
df_grn_f['quantity'] = pd.to_numeric(df_grn_f['quantity'], errors='coerce').fillna(0)
df_grn_f['transaction_number'] = df_grn_f['transaction_number'].astype(str).str.strip().str.upper()
df_grn_f['product_id'] = df_grn_f['product_id'].astype(str).str.strip().str.upper()

# 2. Bersihkan data GRN
# Pastikan kolom referensi di PR juga dibersihkan
df_do_f['so_transaction_number'] = df_do_f['so_transaction_number'].astype(str).str.strip().str.upper()
df_do_f['product_id'] = df_do_f['product_id'].astype(str).str.strip().str.upper()
df_do_f['quantity'] = pd.to_numeric(df_do_f['quantity'], errors='coerce').fillna(0)

# 2. Grouping SO: Ambil detail unik per item per transaksi
df_grn_grouped = df_grn_f.groupby(['transaction_number', 'product_id'], as_index=False).agg({
    'item_name': 'first',      # Mengambil nama item
    'price': 'first',
    'quantity': 'sum',
    'discount': 'sum',
    'tax1_percentage': 'first',
    'tax2_percentage': 'first',
})

# 3. Grouping PR: Agregasi sisa quantity (PENTING: Harus unik per SO + Product)
df_do_grouped_clean = df_do_f.groupby(['grn_transaction_number', 'product_id'], as_index=False).agg({
    'transaction_number' : 'first',
    'quantity': 'sum'
})

# 4. Merge
#Hitung Sisa Qty (Net Qty)
reconcile_grn_do = df_grn_grouped.merge(df_do_grouped_clean, left_on=['transaction_number', 'product_id'], 
                                     right_on=['grn_transaction_number', 'product_id'], how='left', suffixes=('_grn','_do'))
reconcile_grn_do['quantity_do'] = reconcile_grn_do['quantity_do'].fillna(0)
reconcile_grn_do['net_qty'] = (reconcile_grn_do['quantity_grn'] - reconcile_grn_do['quantity_do']).clip(lower=0)

# 4. HITUNG SALDO BERDASARKAN UNIT PRICE
reconcile_grn_do['unit_tax1'] = reconcile_grn_do['price'] * (reconcile_grn_do['tax1_percentage'] / 100)
reconcile_grn_do['unit_tax2'] = reconcile_grn_do['price'] * (reconcile_grn_do['tax2_percentage'] / 100)

reconcile_grn_do['grn_balance_amount'] = (
    reconcile_grn_do['net_qty'] * (
        reconcile_grn_do['price'] - 
        reconcile_grn_do['discount'] + 
        reconcile_grn_do['unit_tax1'] +
        reconcile_grn_do['unit_tax2'] 
    )
)

total_grn_unpr2 = reconcile_grn_do['grn_balance_amount'].sum()
#grn_belum_proses = reconcile_grn_do[reconcile_grn_do['pr_transaction_number'].isna()]
total_item_outstanding_grn = reconcile_grn_do['net_qty'].sum()
# Menghitung berapa banyak baris item yang masih outstanding
total_baris_pending = len(reconcile_grn_do[reconcile_grn_do['net_qty'] > 0])

# 1. Ubah format item_name
reconcile_grn_do['item_name'] = reconcile_grn_do['item_name'].str.replace(';', ' ', regex=False)
# 2. Ubah tipe data ke integer untuk menghilangkan .0
reconcile_grn_do['quantity_grn'] = reconcile_grn_do['quantity_grn'].astype(int)
reconcile_grn_do['quantity_do'] = reconcile_grn_do['quantity_do'].astype(int)
reconcile_grn_do['net_qty'] = reconcile_grn_do['net_qty'].astype(int)

df_download_grn = reconcile_grn_do[[
    'transaction_number_grn', 
    'transaction_number_do',
    'product_id', 
    'item_name', 
    'price',
    'quantity_grn',      # Qty Awal
    'quantity_do',      # Qty yang sudah diproses
    'net_qty',          # Sisa Qty (Outstanding)
]].copy()

# 1. Ubah format item_name
df_download_grn['item_name'] = df_download_grn['item_name'].str.replace(';', ' ', regex=False)

# Rename kolom agar lebih user-friendly di Excel/CSV
df_download_grn.columns = [
    'No. Transaksi GRN', 'No. Transaksi DO','ID Produk', 'Nama Barang', 'Harga Barang',
    'Qty Order', 'Qty Terproses', 'Qty Outstanding'
]

#DO vs SI
# Menjumlahkan quantity di data DO
cols_to_fix = ['price', 'quantity', 'discount', 'tax1_percentage', 'tax2_percentage']
for col in cols_to_fix:
    if col in df_do_f.columns:
        df_do_f[col] = pd.to_numeric(df_do_f[col], errors='coerce').fillna(0)

# --- SO vs PR #SO BALANCE (VERSI FIX) ---

# 1. Pastikan kolom di df_do_f sudah numerik sebelum diproses
df_do_f['tax1_percentage'] = pd.to_numeric(df_do_f['tax1_percentage'], errors='coerce').fillna(0)
df_do_f['tax2_percentage'] = pd.to_numeric(df_do_f['tax2_percentage'], errors='coerce').fillna(0)
df_do_f['discount'] = pd.to_numeric(df_do_f['discount'], errors='coerce').fillna(0)
df_do_f['price'] = pd.to_numeric(df_do_f['price'], errors='coerce').fillna(0)
df_do_f['quantity'] = pd.to_numeric(df_do_f['quantity'], errors='coerce').fillna(0)
df_do_f['transaction_number'] = df_do_f['transaction_number'].astype(str).str.strip().str.upper()
df_do_f['product_id'] = df_do_f['product_id'].astype(str).str.strip().str.upper()

# 2. Bersihkan data GRN
# Pastikan kolom referensi di PR juga dibersihkan
df_si_f['so_transaction_number'] = df_si_f['so_transaction_number'].astype(str).str.strip().str.upper()
df_si_f['product_id'] = df_si_f['product_id'].astype(str).str.strip().str.upper()
df_si_f['quantity'] = pd.to_numeric(df_si_f['quantity'], errors='coerce').fillna(0)
# 2. Grouping SO: Ambil detail unik per item per transaksi
df_do_grouped = df_do_f.groupby(['transaction_number', 'product_id'], as_index=False).agg({
    'item_name': 'first',      # Mengambil nama item
    'price': 'first',
    'quantity': 'sum',
    'discount': 'sum',
    'tax1_percentage': 'first',
    'tax2_percentage': 'first',
})

# 3. Grouping PR: Agregasi sisa quantity (PENTING: Harus unik per SO + Product)
df_si_grouped_clean = df_si_f.groupby(['do_transaction_number', 'product_id'], as_index=False).agg({
    'transaction_number' : 'first',
    'quantity': 'sum'
})

# 4. Merge
#Hitung Sisa Qty (Net Qty)
reconcile_do_si = df_do_grouped.merge(df_si_grouped_clean, left_on=['transaction_number', 'product_id'], 
                                     right_on=['do_transaction_number', 'product_id'], how='left', suffixes=('_do','_si'))
reconcile_do_si['quantity_si'] = reconcile_do_si['quantity_si'].fillna(0)
reconcile_do_si['net_qty'] = (reconcile_do_si['quantity_do'] - reconcile_do_si['quantity_si']).clip(lower=0)

# 4. HITUNG SALDO BERDASARKAN UNIT PRICE
reconcile_do_si['unit_tax1'] = reconcile_do_si['price'] * (reconcile_do_si['tax1_percentage'] / 100)
reconcile_do_si['unit_tax2'] = reconcile_do_si['price'] * (reconcile_do_si['tax2_percentage'] / 100)

reconcile_do_si['do_balance_amount'] = (
    reconcile_do_si['net_qty'] * (
        reconcile_do_si['price'] - 
        reconcile_do_si['discount'] + 
        reconcile_do_si['unit_tax1'] +
        reconcile_do_si['unit_tax2'] 
    )
)

total_do_unpr2 = reconcile_do_si['do_balance_amount'].sum()
#do_belum_proses = reconcile_do_si[reconcile_do_si['pr_transaction_number'].isna()]
total_item_outstanding_do = reconcile_do_si['net_qty'].sum()
# Menghitung berapa banyak baris item yang masih outstanding
total_baris_pending = len(reconcile_do_si[reconcile_do_si['net_qty'] > 0])

# 1. Ubah format item_name
reconcile_do_si['item_name'] = reconcile_do_si['item_name'].str.replace(';', ' ', regex=False)
# 2. Ubah tipe data ke integer untuk menghilangkan .0
reconcile_do_si['quantity_do'] = reconcile_do_si['quantity_do'].astype(int)
reconcile_do_si['quantity_si'] = reconcile_do_si['quantity_si'].astype(int)
reconcile_do_si['net_qty'] = reconcile_do_si['net_qty'].astype(int)

df_download_do = reconcile_do_si[[
    'transaction_number_do', 
    'transaction_number_si',
    'product_id', 
    'item_name', 
    'price',
    'quantity_do',      # Qty Awal
    'quantity_si',      # Qty yang sudah diproses
    'net_qty',          # Sisa Qty (Outstanding)
]].copy()

# 1. Ubah format item_name
df_download_do['item_name'] = df_download_do['item_name'].str.replace(';', ' ', regex=False)

# Rename kolom agar lebih user-friendly di Excel/CSV
df_download_do.columns = [
    'No. Transaksi GRN', 'No. Transaksi DO', 'ID Produk', 'Nama Barang', 'Harga Barang',
    'Qty Order', 'Qty Terproses', 'Qty Outstanding'
]

# SO Status Check
#so_status = reconcile_so_pr.groupby('transaction_number').agg({'quantity_x':'sum', 'quantity_y':'sum', 'transaction_total_item_x':'sum'}).reset_index()
#fully_unprocessed_value = so_status[so_status['quantity_y'] == 0]['transaction_total_item_x'].sum()
#part_so = so_status[(so_status['quantity_y'] > 0) & (so_status['quantity_y'] < so_status['quantity_x'])]
#partially_unprocessed_value = ((part_so['quantity_x'] - part_so['quantity_y']) / part_so['quantity_x'] * part_so['transaction_total_item_x']).sum()
open_sales_order = total_so_unpr2 + total_pr_unpr2 + total_po_unpr2 + total_grn_unpr2
total_prospektus_si = total_do_unpr2 + open_sales_order


#Realization
#Incoming Orders
incoming_orders = df_so_f.copy()
# Jika 1 nomor transaksi punya banyak baris (per item)
total_incoming_orders = incoming_orders.groupby('transaction_number')['transaction_total'].last().sum()
#total_item_pr = df_pr_f.groupby('transaction_number')['product_id'].nunique().sum() if not df_pr_f.empty else 0
price_qty = incoming_orders['quantity'] * incoming_orders['price']
total_incoming_orders2 = price_qty.sum()
#Menghitung Jumlah PO yang aktif (Volume)
total_sales_count = incoming_orders['transaction_number'].nunique()

#Incoming Supply
incoming_supply = df_grn_real.copy()
#Jika 1 nomor transaksi punya banyak baris (per item)
total_incoming_supply = incoming_supply.groupby('transaction_number')['transaction_total'].last().sum()
#total_item_pr = df_pr_f.groupby('transaction_number')['product_id'].nunique().sum() if not df_pr_f.empty else 0
price_qty = incoming_supply['quantity'] * incoming_supply['price']
total_incoming_supply2 = price_qty.sum()
#Menghitung Jumlah PO yang aktif (Volume)
total_supply_count = incoming_supply['transaction_number'].nunique()

#Total Amount Due
pr_created = df_pr_real.copy()
Total_PR_created = pr_created.groupby('transaction_number')['transaction_total'].last().sum()
po_created = df_po_real.copy()
Total_PO_created = po_created.groupby('transaction_number')['transaction_total'].last().sum()
do_created = df_do_real.copy()
Total_DO_created = do_created.groupby('transaction_number')['transaction_total'].last().sum()
amount_paid = df_si_real.copy()
#Jika 1 nomor transaksi punya banyak baris (per item)
#total_amount_paid = amount_paid[amount_paid['status_description'].isin(['Complete'])]
# Tambahkan nama kolom yang ingin dijumlahkan di bagian akhir
total_amount_paid = amount_paid[amount_paid['status_description'] == 'Complete']['transaction_total'].sum()


# --- 2. HEADER DASHBOARD ---
col_h1, col_h2 = st.columns([0.1, 0.9])
with col_h1:
    try:
        st.markdown('<div style="padding-top: 25px;"></div>', unsafe_allow_html=True)
        st.image(Image.open('image.jpg'), width=500)
    except: pass
with col_h2:
    st.markdown(f"""<h2 style='color: #1E88E5;padding-bottom: 0.1rem;'>SIBIMA <span style='color: white;'>Monitoring Sales & Supply Dashboard</span></h2>
                <p style='font-size: 1.1rem; padding-top: 0.1rem;'>Last updated: {now.strftime('%d %b %Y | %H:%M')}</p>""", unsafe_allow_html=True)

st.divider()

# --- UI METRICS ---
st.subheader("💰 Ringkasan Performa Penjualan")
c1, c2, c3 = st.columns(3)
c1.metric("Net Revenue", f"Rp {net_revenue:,.0f}")
c2.metric("Gross Revenue", f"Rp {gross_revenue:,.0f}")
c3.metric("Open Sales Order", f"Rp {open_sales_order:,.0f}")

st.subheader("Balance")
b = st.columns(3)
b[0].metric("SO Balance", f"Rp {total_so_unpr2:,.0f}")
b[1].metric("PR Balance", f"Rp {total_pr_unpr2:,.0f}")
b[2].metric("PO Balance", f"Rp {total_po_unpr2:,.0f}")
b = st.columns(3)
b[0].metric("GRN Balance", f"Rp {total_grn_unpr2:,.0f}")
b[1].metric("DO Balance", f"Rp {total_do_unpr2:,.0f}")
b[2].metric("Prospektus SI", f"Rp {total_prospektus_si:,.0f}")

# --- 7. FITUR DOWNLOAD DATA TERFILTER ---
st.subheader("📥 Download Data")

# Kita buat 3 kolom untuk tombol download agar rapi
col_dl1, col_dl2, col_dl3, col_dl4, col_dl5 = st.columns(5)

def convert_df(df):
    # Fungsi untuk konversi ke CSV (UTF-8)
    return df.to_csv(index=False, sep=',', quoting=csv.QUOTE_NONNUMERIC).encode('utf-8')

with col_dl1:
    if not df_download_so.empty:
        st.download_button(
            label="Data SO Balance",
            data=convert_df(df_download_so),
            file_name=f'SO_Filtered_{today}.csv',
            mime='text/csv',
        )

with col_dl2:
    if not df_download_pr.empty:
        st.download_button(
            label="Data PR Balance",
            data=convert_df(df_download_pr),
            file_name=f'PR_Filtered_{today}.csv',
            mime='text/csv',
        )

with col_dl3:
    # Contoh download data rekonsiliasi/balance
    if not df_download_po.empty:
        st.download_button(
            label="Data PO Balance",
            data=convert_df(df_download_po),
            file_name=f'PO_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl4:
    # Contoh download data rekonsiliasi/balance
    if not df_download_grn.empty:
        st.download_button(
            label="Data GRN Balance",
            data=convert_df(df_download_grn),
            file_name=f'GRN_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl5:
    # Contoh download data rekonsiliasi/balance
    if not df_download_do.empty:
        st.download_button(
            label="Data DO Balance",
            data=convert_df(df_download_do),
            file_name=f'DO_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

st.subheader("Realization")
b = st.columns(3)
b[0].metric("Incoming Orders", f"Rp {total_incoming_orders:,.0f}")
b[1].metric("Incoming Supply", f"Rp {total_incoming_supply:,.0f}")
b[2].metric("Total PR Created", f"Rp {Total_PR_created:,.0f}")
b = st.columns(3)
b[0].metric("Total PO Created", f"Rp {Total_PO_created:,.0f}")
b[1].metric("Total DO Created", f"Rp {Total_DO_created:,.0f}")
b[2].metric("Total Amount Paid", f"Rp {total_amount_paid:,.0f}")

#st.subheader("CEK SO")
#s1, s2 = st.columns(2)
#s1.metric("Fully Unprocessed SO", f"Rp {fully_unprocessed_value:,.0f}")
#s2.metric("Partially Unprocessed SO", f"Rp {partially_unprocessed_value:,.0f}")
st.divider()
st.subheader("📦 Total Document Summary")
def get_delta(cur, prev): return f"{((cur-prev)/prev*100):.1f}%" if prev > 0 else "0%"
i = st.columns(6)
i[0].metric("Total SO", f"{total_trans_so:,}")
i[1].metric("Total PR", f"{total_trans_pr:,}")
i[2].metric("Total PO", f"{total_trans_po:,}")
i[3].metric("Total GRN", f"{total_trans_grn:,}")
i[4].metric("Total DO", f"{total_trans_do:,}")
i[5].metric("Total SI", f"{total_trans_si:,}")

st.subheader("📦 Total Item Summary")
def get_delta(cur, prev): return f"{((cur-prev)/prev*100):.1f}%" if prev > 0 else "0%"
i = st.columns(6)
i[0].metric("Total SO", f"{total_item_so:,}")
i[1].metric("Total PR", f"{total_item_pr:,}", get_delta(total_item_pr, total_item_so))
i[2].metric("Total PO", f"{total_item_po:,}", get_delta(total_item_po, total_item_pr))
i[3].metric("Total GRN", f"{total_item_grn:,}", get_delta(total_item_grn, total_item_po))
i[4].metric("Total DO", f"{total_item_do:,}", get_delta(total_item_do, total_item_grn))
i[5].metric("Total SI", f"{total_item_si:,}", get_delta(total_item_si, total_item_do))

# --- 7. FITUR DOWNLOAD DATA TERFILTER ---
st.subheader("📥 Download Data")

# Kita buat 3 kolom untuk tombol download agar rapi
col_dl1, col_dl2, col_dl3, col_dl4, col_dl5, col_dl6 = st.columns(6)

def convert_df(df):
    # Fungsi untuk konversi ke CSV (UTF-8)
    return df.to_csv(index=False).encode('utf-8')

with col_dl1:
    if not df_unique_so.empty:
        st.download_button(
            label="Data Item SO",
            data=convert_df(df_unique_so),
            file_name=f'ItemSO_filtered_{today}.csv',
            mime='text/csv',
        )

with col_dl2:
    if not df_unique_pr.empty:
        st.download_button(
            label="Data Item PR",
            data=convert_df(df_unique_pr),
            file_name=f'ItemPR_filtered_{today}.csv',
            mime='text/csv',
        )

with col_dl3:
    # Contoh download data rekonsiliasi/balance
    if not df_unique_po.empty:
        st.download_button(
            label="Data Item PO",
            data=convert_df(df_unique_po),
            file_name=f'ItemPO_filtered__{today}.csv',
            mime='text/csv',
        )

with col_dl4:
    # Contoh download data rekonsiliasi/balance
    if not df_unique_grn.empty:
        st.download_button(
            label="Data Item GRN",
            data=convert_df(df_unique_grn),
            file_name=f'ItemGRN_filtered__{today}.csv',
            mime='text/csv',
        )

with col_dl5:
    # Contoh download data rekonsiliasi/balance
    if not df_unique_do.empty:
        st.download_button(
            label="Data Item DO",
            data=convert_df(df_unique_do),
            file_name=f'ItemDO_filtered__{today}.csv',
            mime='text/csv',
        )

with col_dl6:
    # Contoh download data rekonsiliasi/balance
    if not df_unique_si.empty:
        st.download_button(
            label="Data Item SI",
            data=convert_df(df_unique_si),
            file_name=f'ItemSI_filtered__{today}.csv',
            mime='text/csv',
        )

# Kita buat 3 kolom untuk tombol download agar rapi
col_dl1, col_dl2, col_dl3, col_dl4, col_dl5 = st.columns(5)

def convert_df(df):
    # Fungsi untuk konversi ke CSV (UTF-8)
    return df.to_csv(index=False).encode('utf-8')

with col_dl1:
    if not reconcile.empty:
        st.download_button(
            label="Data Document SO",
            data=convert_df(reconcile),
            file_name=f'SO_Filtered_{today}.csv',
            mime='text/csv',
        )

with col_dl2:
    if not reconcile_pr_po.empty:
        st.download_button(
            label="Data Document SR",
            data=convert_df(reconcile_pr_po),
            file_name=f'PR_Filtered_{today}.csv',
            mime='text/csv',
        )

with col_dl3:
    # Contoh download data rekonsiliasi/balance
    if not reconcile_po_grn.empty:
        st.download_button(
            label="Data Document PO",
            data=convert_df(reconcile_po_grn),
            file_name=f'PO_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl4:
    # Contoh download data rekonsiliasi/balance
    if not reconcile_grn_do.empty:
        st.download_button(
            label="Data Document GRN",
            data=convert_df(reconcile_grn_do),
            file_name=f'GRN_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl5:
    # Contoh download data rekonsiliasi/balance
    if not reconcile_do_si.empty:
        st.download_button(
            label="Data Document DO",
            data=convert_df(reconcile_do_si),
            file_name=f'DO_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

# --- CHARTS ---
st.divider()
st.subheader("📊 Item Progress Visualization")
df_monitor = pd.DataFrame({
    'Tahapan': ['SO ke PR','PR ke PO', 'PO ke GRN', 'GRN ke DO', 'DO ke SI'],
    'Persentase': [prog_so_pr, prog_pr_po, prog_po_grn, prog_grn_do, prog_do_si]
})
fig_bar = px.bar(df_monitor, x='Tahapan', y='Persentase', text='Persentase', 
             color_discrete_sequence=['#3498db'])
fig_bar.update_traces(texttemplate='%{text:.2f}%', textposition='outside', textfont_size=16)
fig_bar.add_hline(y=100, line_dash="dash", line_color="white")
st.plotly_chart(fig_bar, use_container_width=True)

st.subheader("📉 Document Flow Visualization")
df_funnel = pd.DataFrame({
    'Jumlah': [total_item_so, total_item_pr, total_item_po, total_item_grn, total_item_do, total_item_si],
    'Tahapan': ['SO', 'PR','PO', 'GRN', 'DO', 'SI']
})
st.plotly_chart(px.funnel(df_funnel, x='Jumlah', y='Tahapan', color='Tahapan'), use_container_width=True)