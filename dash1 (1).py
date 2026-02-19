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

@st.cache_data(ttl=600)
def get_api_data(endpoint, start_date_override=None):
    url = f"{BASE_URL}{endpoint}"
    # Jika ada override (untuk GRN), gunakan itu. Jika tidak, gunakan default 2026-01-01.
    actual_start = start_date_override if start_date_override else "2026-01-01"
    
    params = {"date_start": actual_start, "date_end": today, "token": TOKEN}
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return pd.DataFrame(response.json()['data'])
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# --- EKSEKUSI PENGAMBILAN DATA ---
# SO, PR, DO, PO tetap mulai 2026
df_sq = get_api_data("sales-quotations")
df_so = get_api_data("sales-orders")
df_pr = get_api_data("purchase-requests")
df_po = get_api_data("purchase-orders")
df_do = get_api_data("delivery-orders")
df_si = get_api_data("sales-invoices")

# KHUSUS GRN: Tarik dari Juli 2025 agar stok awal terdeteksi
df_grn = get_api_data("goods-receipt-notes", start_date_override="2025-07-01")

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
    """
    Menghitung data periode terpilih + Outstanding mulai dari Jan 2026.
    """
    if df.empty: return df
    df = df.copy()
    
    if 'transaction_date' in df.columns:
        # 1. Normalisasi Tanggal
        df['transaction_date'] = pd.to_datetime(df['transaction_date']).dt.tz_localize(None)
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        # 2. Batas Bawah Mutlak (Januari 2026)
        absolute_limit = pd.to_datetime("2026-01-01")
        
        # 3. Filter Status yang dianggap Outstanding
        status_outstanding = ['In Progress', 'Approved']
        
        # LOGIKA MASK:
        # Mask A: Data yang masuk dalam rentang filter kalender dashboard
        mask_current = (df['transaction_date'] >= start_dt) & (df['transaction_date'] <= end_dt)
        
        # Mask B: Data dari Jan 2026 sampai sebelum Tanggal Mulai yang dipilih
        # HANYA jika statusnya belum selesai
        mask_outstanding = (df['transaction_date'] >= absolute_limit) & \
                           (df['transaction_date'] < start_dt) & \
                           (df['status_description'].isin(status_outstanding))
        
        # Gabungkan kedua mask
        df = df[mask_current | mask_outstanding]

    # 4. Filter Customer
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

# --- RECONCILE LOGIC ENHANCED (Sesuai Alur Whiteboard) ---
# --- 1. FUNGSI PEMBERSIH ---
def super_clean_keys(df, col):
    if col in df.columns:
        return df[col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).str.upper().replace(['NAN', 'NONE', '0', ''], 'KOSONG')
    return "KOSONG"

# --- 2. PRE-PROCESSING & MAPPING AWAL ---
for df in [df_so_f, df_pr_f, df_po_f, df_do_f, df_grn_f]:
    df['product_id'] = super_clean_keys(df, 'product_id')
    if 'so_id' in df.columns:
        df['so_id'] = super_clean_keys(df, 'so_id')
    
    for col in ['quantity', 'price', 'discount', 'tax1_percentage', 'tax2_percentage']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# FIX ERROR 'so_id' di PO: Mapping ulang dari PR asli
pr_map = df_pr_f[['transaction_number', 'product_id', 'so_id']].drop_duplicates()
df_po_f = pd.merge(df_po_f, pr_map, left_on=['pr_transaction_number', 'product_id'], right_on=['transaction_number', 'product_id'], how='left', suffixes=('', '_map'))

# Pastikan kolom so_id ada di PO sebelum groupby
if 'so_id' not in df_po_f.columns:
    df_po_f['so_id'] = 'KOSONG'
else:
    df_po_f['so_id'] = df_po_f['so_id'].fillna('KOSONG')

# --- 3. HITUNG STOK (SOH) ---
df_grn_total = df_grn_f.groupby('product_id')['quantity'].sum().reset_index(name='total_grn')
df_do_total = df_do_f.groupby('product_id')['quantity'].sum().reset_index(name='total_do_global')
df_soh = pd.merge(df_grn_total, df_do_total, on='product_id', how='left').fillna(0)
df_soh['current_soh'] = (df_soh['total_grn'] - df_soh['total_do_global']).clip(lower=0)

# --- 4. GROUPING DATA ---
df_so_grouped = df_so_f[df_so_f['customer_name'] != 'EAS GROUP'].groupby(['so_id', 'product_id'], as_index=False).agg({
    'transaction_number': lambda x: ', '.join(x.unique().astype(str)), 'item_name': 'first', 'customer_name': 'first',
    'price': 'first', 'quantity': 'sum', 'discount': 'sum',
    'tax1_percentage': 'first', 'tax2_percentage': 'first'
}).rename(columns={'quantity': 'qty_so', 'transaction_number': 'no_so'})

df_pr_grouped = df_pr_f.groupby(['so_id', 'product_id'], as_index=False).agg({
    'so_transaction_number': lambda x: ', '.join(x.unique().astype(str)),'transaction_number': lambda x: ', '.join(x.unique().astype(str)),  'quantity': 'sum'
}).rename(columns={'transaction_number': 'no_pr', 'quantity': 'qty_pr'})

# GRN Grouped (Barang Masuk per SO)
df_grn_grouped = df_grn_f.groupby(['so_id', 'product_id'], as_index=False).agg({
    'transaction_number': lambda x: ', '.join(x.unique().astype(str)), 'quantity': 'sum'
}).rename(columns={'transaction_number': 'no_grn', 'quantity': 'qty_grn'})

# PO Grouped (Belanjaan per SO)
df_po_grouped = df_po_f.groupby(['so_id', 'product_id'], as_index=False).agg({
    'quantity': 'sum'
}).rename(columns={'quantity': 'qty_po'})

df_do_grouped = df_do_f.groupby(['so_id', 'product_id'], as_index=False).agg({
    'so_transaction_number': lambda x: ', '.join(x.unique().astype(str)),'transaction_number': lambda x: ', '.join(x.unique().astype(str)), 'quantity': 'sum'
}).rename(columns={'transaction_number': 'no_do', 'quantity': 'qty_do'})
# --- 5. SMART MERGE FINAL (FIX TRANSACTION_NUMBER ERROR) ---
# --- PERBAIKAN FUNGSI SMART MERGE ---
def smart_merge_final(base_df, target_df, type_name):
    has_id = base_df['so_id'] != 'KOSONG'
    
    # Track 1: Join Berdasarkan ID yang Jelas (Sangat Akurat)
    with_id = base_df[has_id].copy().merge(
        target_df[['so_id', 'product_id', f'no_{type_name}', f'qty_{type_name}']], 
        on=['so_id', 'product_id'], how='left'
    )
    
    # Track 2: Data yang tidak punya ID (Potensi Salah Sambung)
    no_id = base_df[~has_id].copy()
    no_id[f'no_{type_name}'] = np.nan
    no_id[f'qty_{type_name}'] = 0
    
    combined = pd.concat([with_id, no_id], ignore_index=True)
    
    # FIFO Orphan Match: Hanya jalankan jika Anda BENAR-BENAR yakin PR tanpa ID adalah milik SO
    if type_name in ['pr', 'do']:
        still_empty = combined[combined[f'no_{type_name}'].isna()].index
        source_f = df_pr_f if type_name == 'pr' else df_do_f
        
        # Filter orphans: Hanya ambil yang benar-benar tidak punya so_id
        orphans = source_f[source_f['so_id'] == 'KOSONG'].copy()
        
        for idx in still_empty:
            p_id = combined.at[idx, 'product_id']
            needed_qty = combined.at[idx, 'qty_so'] # Ambil kebutuhan SO
            
            # PERBAIKAN: Cari yang product_id SAMA dan QTY juga SAMA (atau mendekati)
            # Ini mencegah PR stok besar masuk ke SO kecil
            match = orphans[
                (orphans['product_id'] == p_id) & 
                (orphans['quantity'] == needed_qty) # Tambahkan syarat QTY harus sama
            ].head(1)
            
            if not match.empty:
                combined.at[idx, f'no_{type_name}'] = match['transaction_number'].values[0]
                combined.at[idx, f'qty_{type_name}'] = match['quantity'].values[0]
                orphans = orphans.drop(match.index[0])
                
    return combined.drop_duplicates(subset=['no_so', 'product_id'], keep='first')

# --- 6. EKSEKUSI & KALKULASI RUPIAH ---
reconcile_master = smart_merge_final(df_so_grouped, df_pr_grouped, 'pr')
reconcile_master = smart_merge_final(reconcile_master, df_do_grouped, 'do')
reconcile_master = pd.merge(reconcile_master, df_po_grouped, on=['so_id', 'product_id'], how='left').fillna(0)
reconcile_master = pd.merge(reconcile_master, df_grn_grouped, on=['so_id', 'product_id'], how='left').fillna(0)
reconcile_master = pd.merge(reconcile_master, df_soh[['product_id', 'current_soh']], on='product_id', how='left').fillna(0)

# --- 6. KALKULASI LOGIKA BARU ---
reconcile_master['qty_pr'] = reconcile_master['qty_pr'].fillna(0)
reconcile_master['qty_do'] = reconcile_master['qty_do'].fillna(0)

# A. Hitung Net Price
reconcile_master['disc_per_unit'] = reconcile_master['discount'] / reconcile_master['qty_so'].replace(0, 1)
reconcile_master['tax_unit'] = reconcile_master['price'] * ((reconcile_master['tax1_percentage'] + reconcile_master['tax2_percentage']) / 100)
reconcile_master['net_price_unit'] = reconcile_master['price'] - reconcile_master['disc_per_unit'] + reconcile_master['tax_unit']

# --- 4. LOGIKA DASHBOARD BALANCE ---
reconcile_master['qty_pr'] = reconcile_master['qty_pr'].fillna(0)
reconcile_master['qty_do'] = reconcile_master['qty_do'].fillna(0)
reconcile_master['qty_po'] = reconcile_master['qty_po'].fillna(0)
reconcile_master['qty_grn'] = reconcile_master['qty_grn'].fillna(0)

# A. Outstanding Pesanan
reconcile_master['qty_outstanding'] = (reconcile_master['qty_so'] - reconcile_master['qty_do']).clip(lower=0)

# B. GRN BALANCE (Stok per SO yang mengendap)
reconcile_master['qty_grn_balance'] = (reconcile_master['qty_grn'] - reconcile_master['qty_do']).clip(lower=0)
reconcile_master['amt_grn_balance'] = reconcile_master['qty_grn_balance'] * reconcile_master['net_price_unit']

# C. PR BALANCE (PR belum di-PO)
reconcile_master['qty_pr_balance'] = (reconcile_master['qty_pr'] - reconcile_master['qty_po']).clip(lower=0)
reconcile_master['amt_pr_balance'] = reconcile_master['qty_pr_balance'] * reconcile_master['net_price_unit']

# D. PO BALANCE (Barang di jalan)
reconcile_master['qty_po_balance'] = (reconcile_master['qty_po'] - reconcile_master['qty_grn']).clip(lower=0)
reconcile_master['amt_po_balance'] = reconcile_master['qty_po_balance'] * reconcile_master['net_price_unit']

# E. WAITING DELIVERY & PENDING SUPPLY
reconcile_master['qty_waiting_delivery'] = reconcile_master[['qty_outstanding', 'current_soh']].min(axis=1)
# Pending Supply = Total Outstanding - (Yang sudah ready di gudang) - (Yang sedang diproses PR/PO)
reconcile_master['true_pending_qty'] = (
    reconcile_master['qty_outstanding'] - 
    reconcile_master['qty_waiting_delivery'] - 
    (reconcile_master['qty_pr'] - reconcile_master['qty_do']).clip(lower=0)
).clip(lower=0)

# HITUNG NILAI RUPIAH (Pastikan baris ini ada agar agregasi tidak error)
reconcile_master['amt_pending_supply'] = reconcile_master['true_pending_qty'] * reconcile_master['net_price_unit']
reconcile_master['amt_waiting_delivery'] = reconcile_master['qty_waiting_delivery'] * reconcile_master['net_price_unit']

# --- 5. AGREGASI FINAL UNTUK DASHBOARD ---
total_pr_unpr2 = reconcile_master['amt_pr_balance'].sum()
total_po_unpr2 = reconcile_master['amt_po_balance'].sum()
so_pending_supply = reconcile_master['amt_pending_supply'].sum()
so_waiting_delivery = reconcile_master['amt_waiting_delivery'].sum()
total_grn_unpr2 = reconcile_master['amt_grn_balance'].sum()

# --- 8. PREPARASI SEMUA DATAFRAME DOWNLOAD ---

# 1. DOWNLOAD SO PENDING SUPPLY (Barang yang belum ada Stok & belum ada PR)
df_download_so_pending_supply = reconcile_master[reconcile_master['true_pending_qty'] > 0][[
    'no_so', 'customer_name', 'product_id', 'item_name', 'price', 
    'qty_so', 'qty_do', 'qty_pr', 'current_soh', 'true_pending_qty'
]].copy()

df_download_so_pending_supply.columns = [
    'No. SO', 'Customer', 'ID Produk', 'Nama Barang', 'Harga Satuan',
    'Qty Order', 'Qty Terkirim', 'Qty Sudah PR', 'Stok Gudang', 'Qty Harus Belanja'
]

# 2. DOWNLOAD PR BALANCE (PR yang sudah dibuat tapi belum jadi PO)
df_download_pr = reconcile_master[reconcile_master['qty_pr_balance'] > 0][[
    'no_so', 'no_pr', 'customer_name', 'product_id', 'item_name', 
    'qty_pr', 'qty_po', 'qty_pr_balance'
]].copy()

df_download_pr.columns = [
    'No. SO', 'No. PR', 'Customer', 'ID Produk', 'Nama Barang',
    'Qty Permintaan (PR)', 'Qty Sudah PO', 'Qty Outstanding PR (to PO)'
]

# 3. DOWNLOAD PO BALANCE (PO yang sudah dibuat tapi barang belum sampai/GRN)
df_download_po = reconcile_master[reconcile_master['qty_po_balance'] > 0][[
    'no_so', 'customer_name', 'product_id', 'item_name', 
    'qty_po', 'qty_grn', 'qty_po_balance'
]].copy()

df_download_po.columns = [
    'No. SO', 'Customer', 'ID Produk', 'Nama Barang',
    'Qty Belanja (PO)', 'Qty Sudah Masuk (GRN)', 'Qty Outstanding PO (Barang di Jalan)'
]

# 4. DOWNLOAD GRN BALANCE (Barang sudah di gudang tapi belum dikirim/DO)
df_download_grn = reconcile_master[reconcile_master['qty_grn_balance'] > 0][[
    'no_so', 'no_grn', 'customer_name', 'product_id', 'item_name', 
    'qty_grn', 'qty_do', 'qty_grn_balance'
]].copy()

df_download_grn.columns = [
    'No. SO', 'No. GRN', 'Customer', 'ID Produk', 'Nama Barang',
    'Qty Masuk (GRN)', 'Qty Keluar (DO)', 'Qty Mengendap di Gudang'
]

# 5. DOWNLOAD SO WAITING DELIVERY (Total sisa SO yang siap dikirim berdasarkan Stok Fisik)
df_download_waiting_delivery = reconcile_master[reconcile_master['qty_waiting_delivery'] > 0][[
    'no_so', 'customer_name', 'product_id', 'item_name', 
    'qty_so', 'qty_do', 'current_soh', 'qty_waiting_delivery'
]].copy()

df_download_waiting_delivery.columns = [
    'No. SO', 'Customer', 'ID Produk', 'Nama Barang', 
    'Qty Order', 'Qty Terkirim', 'Total Stok Gudang', 'Qty Siap Kirim'
]

# --- 9. FORMATTING AKHIR (Membersihkan desimal menjadi Integer) ---
all_downloads = [
    df_download_so_pending_supply, 
    df_download_pr, 
    df_download_po, 
    df_download_grn, 
    df_download_waiting_delivery
]

for df_dl in all_downloads:
    # Mengubah semua kolom numerik menjadi integer agar bersih saat di-download
    num_cols = df_dl.select_dtypes(include=['number']).columns
    df_dl[num_cols] = df_dl[num_cols].fillna(0).astype(int)


#DO vs SI
# --- 1. MAPPING SO_ID KE DATA SI ---
# Karena SI biasanya tidak punya so_id, kita ambil dari mapping DO
# transaction_number di sini adalah No DO
do_map = df_do_f[['transaction_number', 'product_id', 'so_id']].drop_duplicates()

# Gabungkan ke data SI (Invoice)
# Ganti 'delivery_order_number' dengan nama kolom No DO yang ada di file Invoice Anda
df_si_f = pd.merge(
    df_si_f, 
    do_map, 
    left_on=['do_transaction_number', 'product_id'], 
    right_on=['transaction_number', 'product_id'], 
    how='left'
).drop(columns=['transaction_number_y'], errors='ignore')

# --- 2. PRE-PROCESSING (Pembersihan ulang setelah merge) ---
df_si_f['so_id'] = super_clean_keys(df_si_f, 'so_id')
df_si_f['product_id'] = super_clean_keys(df_si_f, 'product_id')

# --- 3. GROUPING DATA SI (Disesuaikan dengan kolom yang ada) ---
# Pastikan nama kolom No Invoice Anda (misal: 'invoice_number' atau 'no_transaksi')
# Jika di file SI Anda namanya 'transaction_number', gunakan itu. 
# Jika error lagi, cek nama kolom di Excel Anda.

df_si_grouped = df_si_f.groupby(['so_id', 'product_id'], as_index=False).agg({
    #'transaction_number': lambda x: ', '.join(x.unique().astype(str)), 
    'do_transaction_number': lambda x: ', '.join(x.unique().astype(str)),# GANTI ke nama kolom No Invoice
    'quantity': 'sum'
}).rename(columns={'transaction_number': 'no_si', 'quantity': 'qty_si'})

# --- 4. MERGE KE MASTER RECONCILE ---
reconcile_master = pd.merge(reconcile_master, df_si_grouped, on=['so_id', 'product_id'], how='left').fillna(0)

# --- 5. HITUNG SI BALANCE (Prospektus SI) ---
reconcile_master['qty_si_balance'] = (reconcile_master['qty_do'] - reconcile_master['qty_si']).clip(lower=0)
reconcile_master['amt_si_balance'] = reconcile_master['qty_si_balance'] * reconcile_master['net_price_unit']

# Update Variabel Dashboard
total_do_unpr2 = reconcile_master['amt_si_balance'].sum()

# DOWNLOAD SI BALANCE (DO Belum Invoice)
df_download_do = reconcile_master[reconcile_master['qty_si_balance'] > 0][[
    'no_so', 'no_do', 'customer_name', 'product_id', 'item_name', 
    'qty_do', 'qty_si', 'qty_si_balance'
]].copy()

df_download_do.columns = [
    'No. SO', 'No. DO', 'Customer', 'ID Produk', 'Nama Barang',
    'Qty Terkirim (DO)', 'Qty Ditagihkan (SI)', 'Qty Outstanding SI'
]

# Formatting akhir ke Integer
df_download_do[df_download_do.select_dtypes(include=['number']).columns] = df_download_do.select_dtypes(include=['number']).fillna(0).astype(int)

open_sales_order = so_pending_supply + so_waiting_delivery + total_pr_unpr2 + total_po_unpr2 + total_grn_unpr2
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

# --- 1. CUSTOM CSS (Untuk Mengecilkan Tulisan Angka Metric) ---
st.markdown("""
    <style>
    /* Mengecilkan ukuran angka pada metric */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important; 
        font-weight: 600;
    }
    /* Mengecilkan ukuran label (judul) pada metric */
    [data-testid="stMetricLabel"] {
        font-size: 1.5rem !important;
        color: #B0B0B0 !important;
    }
    /* Mengurangi padding antar kolom agar lebih rapat */
    [data-testid="column"] {
        padding: 0 5px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- UI METRICS ---
st.subheader("💰 Ringkasan Performa Penjualan")
c1, c2, c3 = st.columns(3)
c1.metric("Net Revenue", f"Rp {net_revenue:,.0f}")
c2.metric("Gross Revenue", f"Rp {gross_revenue:,.0f}")
c3.metric("Open Sales Order", f"Rp {open_sales_order:,.0f}")

st.subheader("Balance")
b = st.columns(3)
#b[0].metric("SO Balance", f"Rp {total_so_unpr2:,.0f}")
b[0].metric("SO Pending Supply", f"Rp {so_pending_supply:,.0f}")
b[1].metric("SO Waiting Delivery", f"Rp {so_waiting_delivery:,.0f}")
b[2].metric("PR Balance", f"Rp {total_pr_unpr2:,.0f}")
b = st.columns(4)
b[0].metric("PO Balance", f"Rp {total_po_unpr2:,.0f}")
b[1].metric("GRN Balance", f"Rp {total_grn_unpr2:,.0f}")
b[2].metric("DO Balance", f"Rp {total_do_unpr2:,.0f}")
b[3].metric("Prospektus SI", f"Rp {total_prospektus_si:,.0f}")

# --- CSS UNTUK MENYAMAKAN Total Baris TOMBOL ---
st.markdown("""
<style>
    /* Memaksa teks tombol tetap satu baris dan tidak pindah ke bawah */
    div.stDownloadButton > button p {
        white-space: nowrap !important;
        font-size: 15px !important; /* Perkecil font sedikit agar muat */
    }
</style>
""", unsafe_allow_html=True)

# --- 7. FITUR DOWNLOAD DATA TERFILTER ---
st.subheader("📥 Download Data")

# Kita buat 3 kolom untuk tombol download agar rapi
col_dl1, col_dl2, col_dl3, col_dl4, col_dl5, col_dl6= st.columns(6)

def convert_df(df):
    # Fungsi untuk konversi ke CSV (UTF-8)
    return df.to_csv(index=False, sep=',', quoting=csv.QUOTE_NONNUMERIC).encode('utf-8')

with col_dl1:
    if not df_download_so_pending_supply.empty:
        st.download_button(
            label="SO Pending Supply",
            data=convert_df(df_download_so_pending_supply),
            file_name=f'SO_Pending_Supply_Filtered_{today}.csv',
            mime='text/csv',
        )

with col_dl2:
    if not df_download_waiting_delivery.empty:
        st.download_button(
            label="SO Waiting Delivery",
            data=convert_df(df_download_waiting_delivery),
            file_name=f'SO_Waiting_Delivery_Filtered_{today}.csv',
            mime='text/csv',
        )

with col_dl3:
    if not df_download_pr.empty:
        st.download_button(
            label="PR Balance",
            data=convert_df(df_download_pr),
            file_name=f'PR_Filtered_{today}.csv',
            mime='text/csv',
        )

with col_dl4:
    # Contoh download data rekonsiliasi/balance
    if not df_download_po.empty:
        st.download_button(
            label="PO Balance",
            data=convert_df(df_download_po),
            file_name=f'PO_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl5:
    # Contoh download data rekonsiliasi/balance
    if not df_download_grn.empty:
        st.download_button(
            label="GRN Balance",
            data=convert_df(df_download_grn),
            file_name=f'GRN_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl6:
    # Contoh download data rekonsiliasi/balance
    if not df_download_do.empty:
        st.download_button(
            label="DO Balance",
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
#col_dl1, col_dl2, col_dl3, col_dl4, col_dl5 = st.columns(5)

#def convert_df(df):
    # Fungsi untuk konversi ke CSV (UTF-8)
    #return df.to_csv(index=False).encode('utf-8')

#with col_dl1:
    #if not reconcile_soprdo.empty:
        #st.download_button(
            #label="Data Document SO",
            #data=convert_df(reconcile_soprdo),
            #file_name=f'SO_Filtered_{today}.csv',
            #mime='text/csv',
        #)

#with col_dl2:
    #if not reconcile_pr_po.empty:
        #st.download_button(
            #label="Data Document SR",
            #data=convert_df(reconcile_pr_po),
            #file_name=f'PR_Filtered_{today}.csv',
            #mime='text/csv',
        #)

#with col_dl3:
    # Contoh download data rekonsiliasi/balance
    #if not reconcile_po_grn.empty:
        #st.download_button(
            #label="Data Document PO",
            #data=convert_df(reconcile_po_grn),
            #file_name=f'PO_Balance_Detail_{today}.csv',
            #mime='text/csv',
        #)

#with col_dl4:
    # Contoh download data rekonsiliasi/balance
    #if not reconcile_grn_do.empty:
        #st.download_button(
            #label="Data Document GRN",
            #data=convert_df(reconcile_grn_do),
            #file_name=f'GRN_Balance_Detail_{today}.csv',
            #mime='text/csv',
        #)

#with col_dl5:
    # Contoh download data rekonsiliasi/balance
    #if not reconcile_do_si.empty:
        #st.download_button(
            #label="Data Document DO",
            #data=convert_df(reconcile_do_si),
            #file_name=f'DO_Balance_Detail_{today}.csv',
            #mime='text/csv',
        #)

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