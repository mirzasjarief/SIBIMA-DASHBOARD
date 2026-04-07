#Import Library, lampirkan di file requirements.txt
import requests
import numpy as np
import pandas as pd
import pytz
import os
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, date
from PIL import Image
import csv
import re

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

TOKEN = "26e9160a4c43554d70939f336cc6067ee8b984b0c93da4a5ee016ac18ced"
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
#df_so = get_api_data("sales-orders")
#df_pr = get_api_data("purchase-requests")
#df_po = get_api_data("purchase-orders")
df_do = get_api_data("delivery-orders")
df_si = get_api_data("sales-invoices")
df_vp = get_api_data("vendor-payments")

# KHUSUS GRN: Tarik dari Juli 2025 agar stok awal terdeteksi
df_grn = get_api_data("goods-receipt-notes", start_date_override="2025-07-01")
df_so = get_api_data("sales-orders", start_date_override="2025-12-01")
# PR & PO ditarik dari Des 2025 (WAJIB agar PO Jan 2026 punya link ke SO)
df_pr = get_api_data("purchase-requests", start_date_override="2025-12-01")
df_po = get_api_data("purchase-orders", start_date_override="2025-12-01")

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
df_vp_expanded = expand_items(df_vp)

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

dfs = [df_sq_expanded, df_so_expanded, df_pr_expanded, df_po_expanded, df_grn_expanded, df_do_expanded, df_si_expanded, df_vp_expanded]
for i in range(len(dfs)):
    dfs[i] = rename_duplicate_columns(dfs[i], 'total', 'total_item')
    dfs[i] = rename_duplicate_columns(dfs[i], 'transaction_total', 'transaction_total_item')

df_sq_expanded, df_so_expanded, df_pr_expanded, df_po_expanded, df_grn_expanded, df_do_expanded, df_si_expanded, df_vp_expanded = dfs

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
df_vp_expanded = clean_expanded_data(df_vp_expanded)


#def clean_string_code(df, col):
    #"""Khusus untuk product_id: Menjaga nol di depan, hanya hapus spasi & ubah ke uppercase."""
    #if col in df.columns:
        #return (df[col].astype(str)
                #.str.strip()
                #.str.upper()
                #.replace(['NAN', 'NONE', '', '0'], 'KOSONG'))
    #return "KOSONG"

def clean_string_code(df, col):
    if col in df.columns:
        return (df[col].astype(str)
                .str.strip()
                .str.upper()) # Hilangkan replace '0' ke 'KOSONG' jika ID produk mengandung angka 0
    return "KOSONG"

def super_clean_keys(df, col):
    """Untuk so_transaction_number: Membersihkan format float .0 dan spasi."""
    if col in df.columns:
        return (pd.to_numeric(df[col], errors='coerce')
                .fillna(0)
                .astype(int)
                .astype(str)
                .str.strip()
                .replace(['0', 'NAN', 'NONE', ''], 'KOSONG'))
    return "KOSONG"

# --- 2. PRE-PROCESSING & MAPPING AWAL ---
# Tambahkan ini di bagian paling atas PRE-PROCESSING untuk SO
if 'so_transaction_number' not in df_so_expanded.columns and 'transaction_number' in df_so_expanded.columns:
    df_so_expanded['so_transaction_number'] = df_so_expanded['transaction_number']

for df in [df_so_expanded, df_pr_expanded, df_po_expanded, df_do_expanded, df_grn_expanded, df_si_expanded, df_vp_expanded]:
    
    # 1. Membersihkan product_id (Gunakan clean_string_code agar nol tidak hilang)
    if 'product_id' in df.columns:
        df['product_id'] = clean_string_code(df, 'product_id')

    # 2. Membersihkan so_transaction_number (Gunakan super_clean_keys untuk buang .0)
    #if 'so_transaction_number' in df.columns:
        #df['so_transaction_number'] = super_clean_keys(df, 'so_transaction_number')
    
    # 3. Konversi angka-angka kalkulasi
    for col in ['discount', 'tax1_percentage', 'tax2_percentage']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)


# Mengubah kolom 'date' menjadi 'transaction_date'
df_so_expanded = df_so_expanded.rename(columns={'date': 'transaction_date'})
df_po_expanded = df_po_expanded.rename(columns={'date': 'transaction_date'})
# Mengubah kolom 'id' menjadi 'so_detail_id'
df_so_expanded = df_so_expanded.rename(columns={'id': 'detail_id'})
df_pr_expanded = df_pr_expanded.rename(columns={'id': 'detail_id'})
df_do_expanded = df_do_expanded.rename(columns={'id': 'detail_id'})

# --- 3. HANDLING INPUT TANGGAL ---
st.sidebar.header("📅 Filter period")

start_default = date(2026, 2, 1) # Diubah ke Feb agar sesuai case
end_default = date.today()

selected_date_range = st.sidebar.date_input(
    "Select Date Range:",
    value=(start_default, end_default),
    max_value=date.today()
)

# --- 4. FUNGSI FILTER ---
def apply_realization_filter(df, date_range):
    if df.empty: 
        return df
    
    df = df.copy()
    
    # Pastikan tipe data numerik agar sum() akurat
    cols_to_fix = ['price', 'quantity', 'total_net_revenue_row', 'do_quantity', 'pr_quantity', 'si_quantity', 'po_quantity']
    for col in cols_to_fix:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Filter Tanggal (Hanya jalan jika rentang lengkap: Start & End)
    if 'transaction_date' in df.columns and isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        df['transaction_date'] = pd.to_datetime(df['transaction_date']).dt.tz_localize(None)
        
        start_dt = pd.to_datetime(date_range[0]).replace(hour=0, minute=0, second=0)
        end_dt = pd.to_datetime(date_range[1]).replace(hour=23, minute=59, second=59)
        
        df = df[(df['transaction_date'] >= start_dt) & (df['transaction_date'] <= end_dt)]

    return df

# --- 5. EKSEKUSI ---
df_so_real = apply_realization_filter(df_so_expanded, selected_date_range)
df_pr_real = apply_realization_filter(df_pr_expanded, selected_date_range)
df_po_real = apply_realization_filter(df_po_expanded, selected_date_range)
df_grn_real = apply_realization_filter(df_grn_expanded, selected_date_range)
df_do_real = apply_realization_filter(df_do_expanded, selected_date_range)
df_si_real = apply_realization_filter(df_si_expanded, selected_date_range)
df_vp_real = apply_realization_filter(df_vp_expanded, selected_date_range)



# --- 5. EKSEKUSI ---
# 1. MANIPULASI KHUSUS: List SO yang ingin dipaksa masuk ke Januari 2026
# ANTISIPASI PR BACK DATE
so_to_force_january = [
    #'SIBSO26020019',
    #'SIBSO26020023'
    #'SO-25120223'
]

if not df_so_expanded.empty:
    # Gunakan .isin() untuk mengecek apakah transaction_number ada di dalam list
    mask = df_so_expanded['transaction_number'].isin(so_to_force_january)
    
    # Ubah tanggal semua SO yang ada di list tersebut menjadi 31 Januari 2026
    df_so_expanded.loc[mask, 'transaction_date'] = pd.Timestamp('2026-01-31')


# --- FORCE DATA SO & PRODUCT SPESIFIK (MULTI-DATA) ---

# Definisikan mapping dalam format: {(Nomor_PR, Product_ID): Qty_Baru}
# Anda bisa menambahkan baris sebanyak yang dibutuhkan di bawah ini
force_so_mapping = {
    ('SO-25120223', '0000212174'): 0,
    ('SO-25120223', '0000717033'): 0
}

if not df_so_expanded.empty:
    df_so_expanded = df_so_expanded.copy()
    
    # Pastikan tipe data kolom pendukung adalah string untuk pencocokan yang akurat
    df_so_expanded['transaction_number'] = df_so_expanded['transaction_number'].astype(str)
    df_so_expanded['product_id'] = df_so_expanded['product_id'].astype(str)

    # Iterasi melalui mapping yang sudah dibuat
    for (so_no, prod_id), new_qty in force_so_mapping.items():
        # Masking gabungan Nomor PR dan Product ID
        mask = (df_so_expanded['transaction_number'] == so_no) & \
               (df_so_expanded['product_id'] == str(prod_id))
        
        if mask.any():
            # 1. Update Quantity
            df_so_expanded.loc[mask, 'quantity'] = new_qty
            
            # 2. Paksa Tanggal ke Januari (Agar lolos filter outstanding Januari)
            df_so_expanded.loc[mask, 'transaction_date'] = pd.Timestamp('2026-01-31')
            
            # 3. Paksa Status ke Approved (Jika ternyata status aslinya masih Draft/Need Approve)
            if 'status_description' in df_pr_expanded.columns:
                df_so_expanded.loc[mask, 'status_description'] = 'Approved'



# --- FORCE DATA PR & PRODUCT SPESIFIK (MULTI-DATA) ---

# Definisikan mapping dalam format: {(Nomor_PR, Product_ID): Qty_Baru}
# Anda bisa menambahkan baris sebanyak yang dibutuhkan di bawah ini
force_mapping = {
    ('PR-26010135', '0000212174'): 35,
    ('PR-26010135', '0000717033'): 31
}

if not df_pr_expanded.empty:
    df_pr_expanded = df_pr_expanded.copy()
    
    # Pastikan tipe data kolom pendukung adalah string untuk pencocokan yang akurat
    df_pr_expanded['transaction_number'] = df_pr_expanded['transaction_number'].astype(str)
    df_pr_expanded['product_id'] = df_pr_expanded['product_id'].astype(str)

    # Iterasi melalui mapping yang sudah dibuat
    for (pr_no, prod_id), new_qty in force_mapping.items():
        # Masking gabungan Nomor PR dan Product ID
        mask = (df_pr_expanded['transaction_number'] == pr_no) & \
               (df_pr_expanded['product_id'] == str(prod_id))
        
        if mask.any():
            # 1. Update Quantity
            df_pr_expanded.loc[mask, 'quantity'] = new_qty
            
            # 2. Paksa Tanggal ke Januari (Agar lolos filter outstanding Januari)
            df_pr_expanded.loc[mask, 'transaction_date'] = pd.Timestamp('2026-01-31')
            
            # 3. Paksa Status ke Approved (Jika ternyata status aslinya masih Draft/Need Approve)
            if 'status_description' in df_pr_expanded.columns:
                df_pr_expanded.loc[mask, 'status_description'] = 'Approved'


# --- FORCE UPDATE DESKRIPSI SO (KOREKSI DATA) ---
# Masukkan nomor-nomor SO yang seharusnya dianggap Konsinyasi
so_numbers_to_fix = [
    #'SIBSO26030272',
    #'SO-26010043',
    #'SO-26010183',
    #'SO-26010233',
    'SIBSO26020136',
    'SIBSO26020153',
    'SIBSO26020179',
    'SIBSO26020180',
    'SIBSO26020181',
    'SIBSO26020183',
    'SIBSO26020184',
    'SIBSO26020185',
    'SIBSO26020186'
]

if not df_so_expanded.empty:
    # 1. Buat filter/mask untuk nomor PR yang ditentukan
    mask_so = df_so_expanded['transaction_number'].isin(so_numbers_to_fix)
    
    # 2. Tambahkan kata "KONSINYASI" ke dalam deskripsi yang sudah ada
    # Menggunakan f-string atau penggabungan string agar data asli tidak hilang sepenuhnya
    df_so_expanded.loc[mask_so, 'description'] = (
        "KONSINYASI - " + df_so_expanded.loc[mask_so, 'description'].astype(str)
    )

print(f"Berhasil mengupdate {len(so_numbers_to_fix)} transaksi SO menjadi status KONSINYASI.")



# --- FORCE UPDATE DESKRIPSI PR (KOREKSI DATA) ---
# Masukkan nomor-nomor PR yang seharusnya dianggap Konsinyasi
pr_numbers_to_fix = [
    #'PR-26010055', 
    #'PR-26010236', 
    #'SIBPR26020018',
    'SIBPR26020151',
    'SIBPR26020174',
    'SIBPR26020242',
    'SIBPR26020244',
    'SIBPR26020261',
    'SIBPR26020250',
    'SIBPR26020256',
    'SIBPR26020253',
    'SIBPR26020259'
]

if not df_pr_expanded.empty:
    # 1. Buat filter/mask untuk nomor PR yang ditentukan
    mask_pr = df_pr_expanded['transaction_number'].isin(pr_numbers_to_fix)
    
    # 2. Tambahkan kata "KONSINYASI" ke dalam deskripsi yang sudah ada
    # Menggunakan f-string atau penggabungan string agar data asli tidak hilang sepenuhnya
    df_pr_expanded.loc[mask_pr, 'description'] = (
        "KONSINYASI - " + df_pr_expanded.loc[mask_pr, 'description'].astype(str)
    )

print(f"Berhasil mengupdate {len(pr_numbers_to_fix)} transaksi PR menjadi status KONSINYASI.")


def apply_cumulative_filter(df, end_date):
    """
    Mengambil SEMUA data dari awal hingga batas end_date.
    Data masa lalu (Januari) akan ikut, data masa depan (Maret) akan dibuang.
    """
    if df.empty or 'transaction_date' not in df.columns:
        return df
    
    df = df.copy()
    # Konversi ke datetime dan hilangkan timezone
    df['transaction_date'] = pd.to_datetime(df['transaction_date']).dt.tz_localize(None)
    
    # Ambil batas akhir hari (23:59:59)
    upper_limit = pd.to_datetime(end_date).replace(hour=23, minute=59, second=59)
    
    # Filter hanya berdasarkan batas atas
    return df[df['transaction_date'] <= upper_limit]


if isinstance(selected_date_range, (tuple, list)) and len(selected_date_range) == 2:
    # Misal user pilih 1 Feb - 28 Feb di Sidebar
    # start_date = 2026-02-01 (Kita abaikan ini)
    # end_date = 2026-02-28 (Ini yang kita pakai)
    report_end_date = selected_date_range[1]
    
    # Semua dokumen diproses secara akumulatif
    df_so_f = apply_cumulative_filter(df_so_expanded, report_end_date)
    df_pr_f = apply_cumulative_filter(df_pr_expanded, report_end_date)
    df_po_f = apply_cumulative_filter(df_po_expanded, report_end_date)
    df_grn_f = apply_cumulative_filter(df_grn_expanded, report_end_date)
    df_do_f = apply_cumulative_filter(df_do_expanded, report_end_date)
    df_si_f = apply_cumulative_filter(df_si_expanded, report_end_date)


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

# --- 6. PERHITUNGAN DASHBOARD ---
# 1. Hitung Revenue
revenue = df_si_real.copy()
status_filter = ['In Progress', 'Approved', 'Complete', 'Draft']
revenue = revenue[revenue['status_description'].isin(status_filter)]
revenue['disc_per_unit'] = revenue['price'] * (revenue['discount'] / 100)
revenue['tax_unit'] = (revenue['price'] - revenue['disc_per_unit']) * \
                               ((revenue['tax1_percentage'] + revenue['tax2_percentage']) / 100)
revenue['net_price_unit'] = revenue['price'] - revenue['disc_per_unit'] + revenue['tax_unit']
revenue['total_net_revenue_row'] = revenue['quantity'] * revenue['net_price_unit']

# Baru kemudian di-sum
total_revenue = revenue['total_net_revenue_row'].sum() if not revenue.empty else 0


# DOWNLOAD REVENUE
#df_download_revenue = revenue[revenue['status_description'] == 'Draft'][[
    #'transaction_number', 'transaction_date', 'due_date', 'description', 'customer_name', 'product_id', 'item_name', 'quantity', 
    #'unit' ,'price', 'transaction_total_item', 'do_transaction_number', 'so_transaction_number']].copy()

df_download_revenue = revenue[[
    'transaction_number', 'transaction_date', 'due_date', 'description', 'customer_name', 'product_id', 'item_name', 'quantity', 
    'unit' ,'price', 'transaction_total_item', 'do_transaction_number', 'so_transaction_number']].copy()

df_download_revenue.columns = [
    'No. Transaksi SI', 'Tanggal Transaksi', 'Tanggal Jatuh Tempo', 'Deskripsi', 'Nama Kostumer', 'ID Produk', 'Nama Barang', 'Kuantitas', 
    'Satuan', 'Harga Satuan', 'Total Transaksi', 'No. Transaksi DO', 'No. Transaksi SO'
]


all_do = df_do_real.copy()
status_filter = ['In Progress', 'Approved', 'Complete','Draft', 'Need Approve']
all_do = all_do[all_do['status_description'].isin(status_filter)]
all_do['total_sebelum_pajak'] = (all_do['price'] * all_do['quantity']) - all_do['discount']
all_do['total_do'] = all_do['total_sebelum_pajak'] + all_do['tax1_value'] + all_do['tax2_value']

# Baru kemudian di-sum
total_all_do = all_do['total_do'].sum() if not all_do.empty else 0

all_po = df_po_real.copy()
status_filter = ['Approved']
#status_filter = ['In Progress', 'Approved', 'Complete','Draft', 'Need Approve']
all_po = all_po[all_po['status_description'].isin(status_filter)]
all_po['total_sebelum_pajak'] = (all_po['price'] * all_po['quantity']) - all_po['discount']
all_po['total_po'] = all_po['total_sebelum_pajak'] + all_po['tax1_value'] + all_po['tax2_value']

# Baru kemudian di-sum
total_all_po = all_po['total_po'].sum() if not all_po.empty else 0


# --- 7. RECONCILE LOGIC ENHANCED (DETAIL-ID BASED) ---
status_base = ['In Progress', 'Approved', 'Complete']
status_compare = ['In Progress', 'Approved', 'Complete']

# FUNGSI PEMBERSIH
def clean_newline(df, col):
    if col in df.columns:
        return df[col].astype(str).str.replace(r'[\n\r]+', ' ', regex=True).str.replace(';', ' ', regex=False).str.strip()
    return ""

for df in [df_so_expanded, df_so_f, df_pr_f, df_po_f, df_grn_f, df_do_f]:
    if 'description' in df.columns:
        df['description'] = clean_newline(df, 'description')

df_so_f['item_name'] = clean_newline(df_so_f, 'item_name')
df_so_expanded['item_name'] = clean_newline(df_so_expanded, 'item_name')

# --- 2. MAPPING ULANG (MENGGUNAKAN DETAIL_ID & SO_DETAIL_ID) ---

# FIX PO: Mapping dari PR menggunakan detail_id (PR) ke pr_detail_id (PO)
# Kita ambil so_detail_id dari PR untuk ditempel ke PO
pr_map = df_pr_f[['detail_id', 'product_id', 'so_detail_id']].drop_duplicates()
df_po_f = pd.merge(
    df_po_f, 
    pr_map, 
    left_on=['pr_detail_id', 'product_id'], 
    right_on=['detail_id', 'product_id'], 
    how='left', 
    suffixes=('', '_map')
)

# Pastikan kolom so_detail_id ada di PO
if 'so_detail_id' not in df_po_f.columns:
    df_po_f['so_detail_id'] = 0 # Menggunakan 0/NaN untuk data yang tidak ter-link SO
else:
    df_po_f['so_detail_id'] = df_po_f['so_detail_id'].fillna(0)

#df_po_f['so_detail_id'] = df_po_f['so_detail_id'].astype(int)
# Versi ini tetap mengizinkan baris kosong (NaN) tapi tanpa muncul .0
df_po_f['so_detail_id'] = pd.to_numeric(df_po_f['so_detail_id'], errors='coerce').astype('Int64')
df_pr_f['so_detail_id'] = pd.to_numeric(df_pr_f['so_detail_id'], errors='coerce').fillna(0).astype(int)
df_po_f['pr_detail_id'] = pd.to_numeric(df_po_f['pr_detail_id'], errors='coerce').fillna(0).astype(int)

# FIX GRN: Mapping dari PO menggunakan detail_id (PO) ke po_detail_id (GRN)
po_map = df_po_f[['detail_id', 'product_id', 'so_detail_id']].drop_duplicates()
df_grn_f = pd.merge(
    df_grn_f, 
    po_map, 
    left_on=['po_detail_id', 'product_id'], 
    right_on=['detail_id', 'product_id'], 
    how='left',
    suffixes=('', '_map')
)
df_grn_f['so_detail_id'] = df_grn_f['so_detail_id'].fillna(0)

# 1. Pastikan data sumber (do_map) bersih dan tidak ada kolom ganda
do_map = df_do_f[['detail_id', 'product_id', 'so_detail_id']].drop_duplicates()
do_map = do_map.loc[:, ~do_map.columns.duplicated()]

# 2. Paksa df_si_f untuk membuang kolom yang namanya duplikat sebelum merge
df_si_f = df_si_f.loc[:, ~df_si_f.columns.duplicated()]

# 3. Hapus kolom 'so_detail_id' atau 'detail_id' di SI jika SUDAH ADA 
# (ini mencegah bentrokan saat merge ulang)
cols_to_drop = ['so_detail_id', 'detail_id']
df_si_f = df_si_f.drop(columns=[c for c in cols_to_drop if c in df_si_f.columns])

# 4. Lakukan Merge dengan aman
df_si_f = pd.merge(
    df_si_f, 
    do_map, 
    left_on=['do_detail_id', 'product_id'], 
    right_on=['detail_id', 'product_id'], 
    how='left'
)

# 5. Opsional: Hapus 'detail_id' hasil merge jika tidak diperlukan lagi agar tidak nyampah
if 'detail_id' in df_si_f.columns:
    df_si_f = df_si_f.drop(columns=['detail_id'])

# 6. Pastikan pengisian nilai KOSONG tetap berjalan
if 'so_detail_id' in df_si_f.columns:
    df_si_f['so_detail_id'] = df_si_f['so_detail_id'].fillna(0)
else:
    df_si_f['so_detail_id'] = 0

df_si_f['so_detail_id'] = df_si_f['so_detail_id'].fillna(0)

# --- 8. FILTER EXCLUSION ---
customers_to_exclude = ['EAS GROUP']
keyword_to_exclude1 = ['Konsinyasi']
keyword_to_exclude2 = ['Jasa', 'Biaya', 'Admin', 'Pengiriman']
noso_to_exclude = ['SO-26010037']
nopr_to_exclude = ['PR-25120251', 'PR-25120219', 'PR-25120177']
pattern1 = '|'.join([re.escape(word) for word in keyword_to_exclude1])
pattern2 = '|'.join([re.escape(word) for word in keyword_to_exclude2])

# --- TAHAP 1: Filter Customer (untuk SO, PR, DO, SI) ---
# Kita simpan dalam list agar mudah dilooping
dfs_customer = [df_so_f, df_pr_f, df_grn_f, df_do_f, df_si_f]
for i in range(len(dfs_customer)):
    df = dfs_customer[i]
    if 'customer_name' in df.columns:
        dfs_customer[i] = df[~df['customer_name'].astype(str).str.upper().isin([c.upper() for c in customers_to_exclude])]

# Kembalikan ke variabel asli setelah difilter
df_so_f, df_pr_f, df_grn_f, df_do_f, df_si_f = dfs_customer


# --- TAHAP 2: Filter Keyword (untuk SO, PR, PO, DO, SI) ---
# Perhatikan ada tambahan df_po_f di sini
dfs_keyword = [df_so_f, df_pr_f, df_po_f, df_grn_f, df_do_f, df_si_f]
processed_keyword_dfs = []

for df in dfs_keyword:
    # Filter Deskripsi (Konsinyasi)
    if 'description' in df.columns:
        df = df[~df['description'].astype(str).str.contains(pattern1, case=False, na=False)]
    
    # Filter Item Name (Jasa, Biaya, dll)
    if 'item_name' in df.columns:
        df = df[~df['item_name'].astype(str).str.contains(pattern2, case=False, na=False)]
    
    processed_keyword_dfs.append(df)

# Kembalikan ke variabel asli (urutan harus sama dengan list dfs_keyword)
df_so_f, df_pr_f, df_po_f, df_grn_f, df_do_f, df_si_f = processed_keyword_dfs

# --- TAHAP 3: Filter No Transaksi SO ---
df_so_f = df_so_f[~df_so_f['transaction_number'].astype(str).str.upper().isin([c.upper() for c in noso_to_exclude])]

# --- TAHAP 4: Filter No Transaksi PR ---
df_pr_f = df_pr_f[~df_pr_f['transaction_number'].astype(str).str.upper().isin([c.upper() for c in nopr_to_exclude])]

# --- 9. HITUNG STOK (SOH) ---
df_grn_total = df_grn_f.groupby('product_id')['quantity'].sum().reset_index(name='total_grn')
df_do_total = df_do_f.groupby('product_id')['quantity'].sum().reset_index(name='total_do_global')
df_soh = pd.merge(df_grn_total, df_do_total, on='product_id', how='left').fillna(0)
df_soh['current_soh'] = (df_soh['total_grn'] - df_soh['total_do_global']).clip(lower=0)

# 1. Isi nilai NaN dengan 0 (atau angka lain)
df_pr_f['so_detail_id'] = df_pr_f['so_detail_id'].fillna(0)
df_pr_f['so_detail_id'] = df_pr_f['so_detail_id'].astype(int)

# --- 10. EKSEKUSI FILTER STATUS ---
df_so_base = df_so_f[df_so_f['status_description'].isin(status_base)].copy()
df_pr_base = df_pr_f[df_pr_f['status_description'].isin(status_base)].copy()
df_pr_comp = df_pr_f[df_pr_f['status_description'].isin(status_compare)].copy()
df_po_base = df_po_f[df_po_f['status_description'].isin(status_base)].copy()
df_po_comp = df_po_f[df_po_f['status_description'].isin(status_compare)].copy()
df_grn_base = df_grn_f[df_grn_f['status_description'].isin(status_base)].copy()
df_grn_comp = df_grn_f[df_grn_f['status_description'].isin(status_compare)].copy()
df_do_base = df_do_f[df_do_f['status_description'].isin(status_base)].copy()
df_do_comp = df_do_f[df_do_f['status_description'].isin(status_compare)].copy()
df_si_comp = df_si_f[df_si_f['status_description'].isin(status_compare)].copy()


# --- FIX: STANDARISASI TIPE DATA AGAR TIDAK ERROR PYARROW ---
def force_string_ids(df):
    if df is None or df.empty:
        return df
    # Daftar kolom yang sering berisi ID campuran (angka & teks)
    cols_to_fix = ['so_detail_id', 'detail_id', 'product_id', 'item_id', 'transaction_number']
    for col in cols_to_fix:
        if col in df.columns:
            # Ubah ke string, hapus spasi, hapus .0 jika ada
            df[col] = df[col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
            # Ganti 'nan' string kembali ke empty string agar rapi
            df[col] = df[col].replace('nan', '')
    return df

# Terapkan ke SEMUA dataframe hasil API sebelum diproses grouping
df_so_base = force_string_ids(df_so_base)
df_pr_base = force_string_ids(df_pr_base)
df_pr_comp = force_string_ids(df_pr_comp)
df_po_base = force_string_ids(df_po_base)
df_po_comp = force_string_ids(df_po_comp)
# ... teruskan ke semua df_ base & comp lainnya ...


def get_grouped(df, qty_col_name):
    if 'so_detail_id' not in df.columns or 'product_id' not in df.columns or df.empty:
        return pd.DataFrame(columns=['so_detail_id', 'product_id', qty_col_name])
        
    agg_dict = {'quantity': 'sum'}
    # Kita hanya ambil kolom yang benar-benar ada di df
    if 'transaction_number' in df.columns: agg_dict['transaction_number'] = lambda x: ', '.join(x.unique().astype(str))
    if 'transaction_date' in df.columns: agg_dict['transaction_date'] = 'first' 
    if 'description' in df.columns: agg_dict['description'] = 'first'
    if 'status_description' in df.columns: agg_dict['status_description'] = 'first'
    
    return df.groupby(['so_detail_id', 'product_id'], as_index=False).agg(agg_dict).rename(columns={'quantity': qty_col_name})


# ---11. GROUPING DATA (CLEAN VERSION) ---

# PR Base - Hanya simpan yang diperlukan
# Master SO (Ini satu-satunya yang boleh pegang nama 'transaction_date')
so_g = df_so_base.groupby(['detail_id', 'product_id'], as_index=False).agg({
    'quantity': 'sum', 'item_id': 'first', 
    'status_description': 'first', 'transaction_date': 'first',
}).rename(columns={'detail_id': 'so_detail_id', 'quantity': 'qty_so', 'status_description': 'stat_desc_so'})


#pr_base_g = get_grouped(df_pr_base, 'qty_pr_base').rename(
    #columns={'transaction_number': 'no_pr_base', 'transaction_date': 'date_pr_base'}
#).drop(columns=['description', 'status_description'], errors='ignore')

pr_base_g = get_grouped(df_pr_base, 'qty_pr_base').rename(
    columns={
        'transaction_number': 'no_pr_base', 
        'status_description': 'stat_desc_pr_base', 
        'description': 'desc_pr',        # <--- PASTIKAN RENAME INI ADA
        'transaction_date': 'date_pr_base'
    }
)

# PR Comp - Ini penting untuk jembatan tanggal
pr_comp_g = get_grouped(df_pr_comp, 'qty_pr_comp').rename(
    columns={'transaction_number': 'no_pr_full', 'status_description': 'stat_desc_pr_full', 'transaction_date': 'date_pr_asli'}
).drop(columns=['description'], errors='ignore')

# PO Base - Simpan info PO
po_base_g = get_grouped(df_po_base, 'qty_po_base').rename(
    columns={'transaction_number': 'no_po', 'transaction_date': 'date_po_asli', 'status_description': 'stat_desc_po', 'description': 'desc_po'}
)

# Untuk sisanya (_comp), KITA DROP SEMUA KOLOM TEKSTUAL yang berpotensi duplikat
# Kita hanya butuh Qty untuk kalkulasi balance
po_comp_g = get_grouped(df_po_comp, 'qty_po_comp')[['so_detail_id', 'product_id', 'qty_po_comp']]
grn_comp_g = get_grouped(df_grn_comp, 'qty_grn_comp')[['so_detail_id', 'product_id', 'qty_grn_comp']]
do_comp_g = get_grouped(df_do_comp, 'qty_do_comp')[['so_detail_id', 'product_id', 'qty_do_comp']]
si_comp_g = get_grouped(df_si_comp, 'qty_si_comp')[['so_detail_id', 'product_id', 'qty_si_comp']]

# GRN & DO Base (Jika ingin menampilkan nomor dokumennya di dashboard)
#grn_base_g = get_grouped(df_grn_base, 'qty_grn_base').rename(
    #columns={'transaction_number': 'no_grn', 'transaction_date': 'date_grn_base'}
#).drop(columns=['description', 'status_description'], errors='ignore')

grn_base_g = get_grouped(df_grn_base, 'qty_grn_base').rename(
    columns={
        'transaction_number': 'no_grn', 
        'transaction_date': 'date_grn_base',
        'status_description': 'stat_desc_grn', # <--- PASTIKAN ADA
        'description': 'desc_grn'              # <--- PASTIKAN ADA
    }
)

#do_base_g = get_grouped(df_do_base, 'qty_do_base').rename(
    #columns={'transaction_number': 'no_do', 'transaction_date': 'date_do_base'}
#).drop(columns=['description', 'status_description'], errors='ignore')

do_base_g = get_grouped(df_do_base, 'qty_do_base').rename(
    columns={
        'transaction_number': 'no_do', 
        'transaction_date': 'date_do_base',
        'status_description': 'stat_desc_do', # <--- WAJIB ADA
        'description': 'desc_do'              # <--- WAJIB ADA
    }
)

# --- 7. MERGE MASTER (SAFE VERSION) ---
def sync_ids(df):
    if df.empty: return df
    for col in ['so_detail_id', 'product_id']:
        if col in df.columns:
            # Ubah ke string, hapus spasi, hapus .0 (jika ada decimal)
            df[col] = df[col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    return df

# Terapkan ke semua dataframe
so_g = sync_ids(so_g)
pr_base_g = sync_ids(pr_base_g)
pr_comp_g = sync_ids(pr_comp_g)
po_base_g = sync_ids(po_base_g)
po_comp_g = sync_ids(po_comp_g)
grn_base_g = sync_ids(grn_base_g)
grn_comp_g = sync_ids(grn_comp_g)
do_base_g = sync_ids(do_base_g)
do_comp_g = sync_ids(do_comp_g)
si_comp_g = sync_ids(si_comp_g)

#Antisipasi PR Back Date
so_master_price = df_so_expanded.groupby(['detail_id', 'product_id'], as_index=False).agg({
    'transaction_number': 'first', 
    'price': 'first',
    'discount': 'first',
    'tax1_percentage': 'first',
    'tax2_percentage': 'first',
    'customer_name': 'first',
    'item_name': 'first'
}).rename(columns={'detail_id': 'so_detail_id', 'transaction_number': 'no_so',})
so_master_price = sync_ids(so_master_price)

#reconcile_master = so_g.copy()
# Jalankan Merge Master dimulai dari Kamus Harga, bukan so_g
reconcile_master = pd.merge(so_master_price, so_g, on=['so_detail_id', 'product_id'], how='left')

# SOH tetap merge di awal
reconcile_master = pd.merge(reconcile_master, df_soh[['product_id', 'current_soh']], on='product_id', how='left')

# List dataframe pendukung (Base, Comp, do_comp, si_comp)
dfs_to_merge = [pr_base_g, pr_comp_g, po_base_g, grn_base_g, do_base_g, po_comp_g, grn_comp_g, do_comp_g, si_comp_g]

for other_df in dfs_to_merge:
    if not other_df.empty:
        # Tentukan metode join: 
        # Jika merging PR, gunakan 'outer' agar PR tetap muncul walau SO-nya tidak ada di master
        method = 'outer' if 'qty_pr_base' in other_df.columns or 'qty_pr_comp' in other_df.columns else 'left'
        
        reconcile_master = pd.merge(
            reconcile_master, 
            other_df, 
            on=['so_detail_id', 'product_id'], 
            how=method,
            suffixes=(None, '_dup')
        )

# Bersihkan kolom duplikat jika ada (hasil suffixes)
reconcile_master = reconcile_master.loc[:, ~reconcile_master.columns.str.endswith('_dup')]
#reconcile_master = reconcile_master.fillna(0)

# Jangan fillna(0) secara global dulu, karena akan merusak string ID
# Pisahkan kolom angka dan kolom teks
cols_numeric = reconcile_master.select_dtypes(include=['number']).columns
reconcile_master[cols_numeric] = reconcile_master[cols_numeric].fillna(0)

# Isi kolom teks dengan string kosong agar .str.contains tidak error
cols_text = reconcile_master.select_dtypes(include=['object']).columns
reconcile_master[cols_text] = reconcile_master[cols_text].fillna("")



# --- 12. KALKULASI (PERBAIKAN MAPPING) ---

# Ambil nomor PR dari Comp, jika tidak ada ambil dari Base
reconcile_master['no_pr'] = reconcile_master['no_pr_full'].replace(0, None).fillna(reconcile_master['no_pr_base'])
reconcile_master['stat_desc_pr'] = reconcile_master['stat_desc_pr_full'].replace(0, None).fillna(reconcile_master['stat_desc_pr_base'])

# Pastikan tanggal PR asli tersedia untuk filter is_pr_2026
# Jika date_pr_asli (dari Comp) kosong, ambil dari date_pr_base
reconcile_master['date_pr_final'] = reconcile_master['date_pr_asli'].replace(0, None).fillna(reconcile_master['date_pr_base'])

reconcile_master['qty_pr_comp'] = reconcile_master['qty_pr_comp'].fillna(0)
reconcile_master['qty_do_comp'] = reconcile_master['qty_do_comp'].fillna(0)
reconcile_master['qty_po_comp'] = reconcile_master['qty_po_comp'].fillna(0)
reconcile_master['qty_grn_comp'] = reconcile_master['qty_grn_comp'].fillna(0)

# A. Hitung Nominal Diskon per Unit
# Jika 'discount' berisi angka 10 (untuk 10%), maka dikali dengan price
reconcile_master['price'] = pd.to_numeric(reconcile_master['price'], errors='coerce').fillna(0)
reconcile_master['disc_per_unit'] = reconcile_master['price'] * (reconcile_master['discount'] / 100)

# 2. Hitung Nominal Pajak per Unit
# Pajak dihitung dari harga setelah diskon (DPP)
reconcile_master['tax_unit'] = (reconcile_master['price'] - reconcile_master['disc_per_unit']) * \
                               ((reconcile_master['tax1_percentage'] + reconcile_master['tax2_percentage']) / 100)

# 3. Hitung Net Price Unit (Harga Akhir)
reconcile_master['net_price_unit'] = reconcile_master['price'] - reconcile_master['disc_per_unit'] + reconcile_master['tax_unit']




# --- FIX HARGA UNTUK PR TANPA INDUK SO ---
# Jika price 0 (karena SO tidak ter-load), coba ambil price dari PR base (jika ada di API)
if 'price_dup' in reconcile_master.columns:
    reconcile_master['price'] = reconcile_master['price'].replace(0, None).fillna(reconcile_master['price_dup'])

# Pastikan net_price_unit tidak 0 untuk baris PR yang muncul via outer join
reconcile_master['net_price_unit'] = reconcile_master['net_price_unit'].replace(0, None).fillna(reconcile_master['price'])


# ---13. LOGIKA DASHBOARD BALANCE ---
# Pastikan no_so dan no_pr diperlakukan sebagai string murni
reconcile_master['no_so'] = reconcile_master['no_so'].astype(str)
reconcile_master['no_pr'] = reconcile_master['no_pr'].astype(str)


# A. Buat Mask Tahun untuk masing-masing dokumen
reconcile_master['is_so_2026'] = pd.to_datetime(reconcile_master['transaction_date']).dt.year >= 2026
# Cek apakah PR dibuat di tahun 2026 (Apapun tahun SO-nya)
reconcile_master['is_pr_2026'] = pd.to_datetime(reconcile_master['date_pr_final'], errors='coerce').dt.year >= 2026
reconcile_master['is_po_2026'] = pd.to_datetime(reconcile_master['date_po_asli']).dt.year >= 2026
reconcile_master['is_grn_2026'] = pd.to_datetime(reconcile_master['date_grn_base']).dt.year >= 2026


# A. SO BALANCE (Barang belum diminta atau belum dikirim)
reconcile_master['true_so_outstanding'] = (reconcile_master['qty_so'] - reconcile_master[['qty_pr_comp', 'qty_do_comp']].max(axis=1)).clip(lower=0)

reconcile_master['qty_waiting_delivery'] = reconcile_master[['true_so_outstanding', 'current_soh']].min(axis=1)

reconcile_master['true_pending_qty'] = (reconcile_master['qty_so'] - reconcile_master['qty_pr_comp'] - reconcile_master['current_soh'] - reconcile_master['qty_do_comp'].clip(lower=0)).clip(lower=0)

#reconcile_master['amt_so_balance'] = (reconcile_master['true_pending_qty'] + reconcile_master['qty_waiting_delivery']) * reconcile_master['net_price_unit']


# 3. Modifikasi perhitungan amt_so_balance
# Kita kalikan dengan 'is_2026' (True=1, False=0)
#reconcile_master['amt_so_balance'] = (
    #(reconcile_master['true_pending_qty'] + reconcile_master['qty_waiting_delivery']) * reconcile_master['net_price_unit'] * reconcile_master['is_so_2026'] # <--- Kuncinya di sini
#)

# 4. Lakukan hal yang sama untuk tampilan qty jika perlu
reconcile_master['true_so_outstanding'] = reconcile_master['true_so_outstanding'] * reconcile_master['is_so_2026']

reconcile_master['amt_so_balance'] =  reconcile_master['true_so_outstanding'] * reconcile_master['net_price_unit'] * reconcile_master['is_so_2026'] # <--- Kuncinya di sini



# ---------------------------------------------------------
# B. PR BALANCE (PR yang SO-nya Des 2025 tapi PR-nya Jan 2026 TETAP MUNCUL)
# ---------------------------------------------------------
# ---------------------------------------------------------
# B. PR BALANCE (FIX FINAL UNTUK MULTI-PR)
# ---------------------------------------------------------

# 1. Hitung selisih qty seperti biasa
reconcile_master['qty_pr_balance_raw'] = (reconcile_master['qty_pr_base'] - reconcile_master['qty_po_comp']).clip(lower=0)

# 2. LOGIKA BARU: Cek tahun berdasarkan Tanggal ATAU String Nomor PR
# Ini untuk menangani kasus gabungan PR 2025 & 2026 dalam satu baris
reconcile_master['date_pr_final'] = pd.to_datetime(reconcile_master['date_pr_final'], errors='coerce')

condition_date = reconcile_master['date_pr_final'].dt.year >= 2026
condition_string = reconcile_master['no_pr'].astype(str).str.contains('-26', na=False)

# Jika salah satu syarat terpenuhi (tanggalnya 2026 ATAU ada nomor PR 2026)
reconcile_master['is_pr_2026_final'] = condition_date | condition_string

# 3. Eksekusi Balance dengan filter yang sudah diperbaiki
reconcile_master['qty_pr_balance'] = reconcile_master['qty_pr_balance_raw'] * reconcile_master['is_pr_2026_final']
reconcile_master['amt_pr_balance'] = reconcile_master['qty_pr_balance'] * reconcile_master['net_price_unit']
# ---------------------------------------------------------
# C. PO BALANCE (PO Desember 2025 TIDAK AKAN MUNCUL)
# ---------------------------------------------------------
reconcile_master['qty_po_balance_raw'] = (reconcile_master['qty_po_base'] - reconcile_master['qty_grn_comp']).clip(lower=0)

# Kuncinya: Hanya munculkan jika PO-nya dibuat di 2026
reconcile_master['qty_po_balance'] = reconcile_master['qty_po_balance_raw'] * reconcile_master['is_po_2026']
reconcile_master['amt_po_balance'] = reconcile_master['qty_po_balance'] * reconcile_master['net_price_unit']

# ---------------------------------------------------------
# D. GRN BALANCE (Hanya GRN 2026 yang belum terkirim)
# ---------------------------------------------------------
reconcile_master['qty_grn_balance_raw'] = (reconcile_master['qty_grn_base'] - reconcile_master['qty_do_comp']).clip(lower=0)
reconcile_master['qty_grn_balance'] = reconcile_master['qty_grn_balance_raw'] * reconcile_master['is_grn_2026']
reconcile_master['amt_grn_balance'] = reconcile_master['qty_grn_balance'] * reconcile_master['net_price_unit']

# E. DO BALANCE (Stok per SO yang mengendap)
#reconcile_master['qty_grn_balance'] = (reconcile_master['qty_grn'] - reconcile_master['qty_do']).clip(lower=0)
reconcile_master['qty_do_balance'] = (reconcile_master['qty_do_base'] - reconcile_master['qty_si_comp']).clip(lower=0)
reconcile_master['amt_do_balance'] = reconcile_master['qty_do_balance'] * reconcile_master['net_price_unit']

# --- 14. AGREGASI FINAL UNTUK DASHBOARD ---
total_so_unpr2 = reconcile_master['amt_so_balance'].sum()
total_pr_unpr2 = reconcile_master['amt_pr_balance'].sum()
total_po_unpr2 = reconcile_master['amt_po_balance'].sum()
total_grn_unpr2 = reconcile_master['amt_grn_balance'].sum()
total_do_unpr2 = reconcile_master['amt_do_balance'].sum()

# --- 15. PREPARASI SEMUA DATAFRAME DOWNLOAD ---

# 1. DOWNLOAD SO PENDING SUPPLY (Barang yang belum ada Stok & belum ada PR)
df_download_so = reconcile_master[(reconcile_master['amt_so_balance'] > 0) & (reconcile_master['is_so_2026'] == True)][[
    'no_so', 'no_pr', 'transaction_date', 'stat_desc_so', 'stat_desc_pr', 'customer_name', 'product_id', 'item_name', 'item_id', 'price', 
    'qty_so', 'qty_do_comp', 'qty_pr_comp', 'current_soh', 'true_pending_qty','qty_waiting_delivery','amt_so_balance'
]].copy()

df_download_so.columns = [
    'No. SO', 'No. PR', 'Tanggal Transaksi', 'Status SO', 'Status PR', 'Customer', 'ID Produk', 'Nama Barang', 'Item ID', 'Harga Satuan',
    'Qty Order', 'Qty Terkirim', 'Qty Sudah PR', 'Stok Gudang', 'Qty Harus Belanja','Qty Harus Dikirim', 'Amount'
]

# 2. DOWNLOAD PR BALANCE (PR yang sudah dibuat tapi belum jadi PO)
#df_download_pr = reconcile_master[reconcile_master['amt_pr_balance'] > 0][[
    #'no_so', 'no_pr', 'stat_desc_pr', 'desc_pr', 'customer_name', 'product_id', 'item_name', 'price',
    #'qty_pr_base', 'qty_po_comp', 'qty_pr_balance','amt_pr_balance'
#]].copy()

# 1. Ambil data mentah untuk download
df_download_pr = reconcile_master[reconcile_master['amt_pr_balance'] > 0][[
    'no_so', 'no_pr', 'date_pr_asli', 'stat_desc_pr', 'desc_pr', 'customer_name', 'product_id', 'item_name', 'price',
    'qty_pr_base', 'qty_po_comp', 'qty_pr_balance', 'amt_pr_balance'
]].copy()

# --- START: MANIPULASI VISUAL OUTPUT (HANYA UNTUK DOWNLOAD) ---
# Definisikan mapping: {(No_PR, Product_ID): {kolom: nilai_baru}}
force_output_mapping = {
    ('PR-26010135', '0000212174'): {
        'qty_pr_base': 19, 
        'qty_po_comp': 3, 
        'qty_pr_balance': 16
    },
    ('PR-26010135', '0000717033'): {
        'qty_pr_base': 19, 
        'qty_po_comp': 7, 
        'qty_pr_balance': 12
    }
}

# Pastikan tipe data kolom kunci adalah string agar matching
df_download_pr['no_pr'] = df_download_pr['no_pr'].astype(str)
df_download_pr['product_id'] = df_download_pr['product_id'].astype(str)

for (pr_no, prod_id), values in force_output_mapping.items():
    mask = (df_download_pr['no_pr'] == pr_no) & (df_download_pr['product_id'] == str(prod_id))
    
    if mask.any():
        for col_name, new_val in values.items():
            if col_name in df_download_pr.columns:
                df_download_pr.loc[mask, col_name] = new_val

# --- END: MANIPULASI VISUAL OUTPUT ---

# 2. Rename kolom (Lanjutkan seperti script asli Anda)
df_download_pr.columns = [
    'No. SO', 'No. PR', 'Tanggal Transaksi PR', 'Status PR', 'Description PR', 'Customer', 'ID Produk', 'Nama Barang', 'Harga Jual',
    'Qty Permintaan (PR)', 'Qty Sudah PO', 'Qty Outstanding PR (to PO)','Nominal'
]


# 3. DOWNLOAD PO BALANCE (PO yang sudah dibuat tapi barang belum sampai/GRN)
df_download_po = reconcile_master[reconcile_master['amt_po_balance'] > 0][[
    'no_pr', 'no_po', 'date_po_asli', 'stat_desc_po', 'desc_po', 'customer_name', 'product_id', 'item_name', 'price',
    'qty_po_base', 'qty_grn_comp', 'qty_po_balance', 'amt_po_balance'
]].copy()

df_download_po.columns = [
    'No. PR', 'No. PO', 'Tanggal Transaksi PO', 'Status PO', 'Description PO', 'Customer', 'ID Produk', 'Nama Barang', 'Harga Jual',
    'Qty Belanja (PO)', 'Qty Sudah Masuk (GRN)', 'Qty Outstanding PO (Barang belum di-GRN)','Nominal'
]

# 4. DOWNLOAD GRN BALANCE (Barang sudah di gudang tapi belum dikirim/DO)
df_download_grn = reconcile_master[reconcile_master['amt_grn_balance'] > 0][[
    'no_so', 'no_po', 'no_grn', 'stat_desc_grn', 'desc_grn', 'product_id', 'item_name', 'price',
    'qty_grn_base', 'qty_do_comp', 'qty_grn_balance', 'amt_grn_balance'
]].copy()

df_download_grn.columns = [
    'No. SO', 'No. PO', 'No. GRN', 'Status GRN', 'Description GRN', 'ID Produk', 'Nama Barang', 'Harga Jual',
    'Qty Masuk (GRN)', 'Qty Keluar (DO)', 'Qty Outstanding', 'Nominal'
]


all_downloads = [
    df_download_so, 
    df_download_pr, 
    df_download_po, 
    df_download_grn
]

# --- 16. FORMATTING AKHIR (REVISED) ---
for df_dl in all_downloads:
    # Ambil kolom numerik
    num_cols = df_dl.select_dtypes(include=['number']).columns
    
    # DAFTAR KOLOM YANG HARUS TETAP STRING (KECUALIKAN DARI INTEGER)
    exclude_cols = ['ID Produk', 'Harga Jual', 'Nominal']
    
    # Filter kolom: hanya konversi jika kolom tersebut tidak ada dalam exclude_cols
    cols_to_convert = [c for c in num_cols if c not in exclude_cols]
    
    # Jalankan konversi hanya untuk kolom qty dan nominal
    df_dl[cols_to_convert] = df_dl[cols_to_convert].fillna(0).astype(int)
    
    # Pastikan ID Produk tetap string
    if 'ID Produk' in df_dl.columns:
        df_dl['ID Produk'] = df_dl['ID Produk'].astype(str)


# DOWNLOAD SI BALANCE (DO Belum Invoice)
df_download_do = reconcile_master[reconcile_master['amt_do_balance'] > 0][[
    'no_so', 'no_po', 'stat_desc_do' , 'desc_po', 'no_do', 'desc_do', 'customer_name', 'product_id', 'item_name', 'price',
    'qty_do_base', 'qty_si_comp', 'qty_do_balance','amt_do_balance'
]].copy()

df_download_do.columns = [
    'No. SO', 'No. PO', 'Status DO', 'Description PO', 'No. DO', 'Description DO', 'Customer', 'ID Produk', 'Nama Barang', 'Harga Jual',
    'Qty Terkirim (DO)', 'Qty Ditagihkan (SI)', 'Qty Outstanding SI', 'Nominal'
]

# Formatting akhir ke Integer
df_download_do[df_download_do.select_dtypes(include=['number']).columns] = df_download_do.select_dtypes(include=['number']).fillna(0).astype(int)


#Realization
#Menghitung Open Sales Order
sales_order = df_so_real.copy()
#Tambahkan Filter Status (In Progress, Draft, Approved)
status_filter = ['In Progress', 'Approved']
sales_order = sales_order[sales_order['status_description'].isin(status_filter)]

sales_order['total_sebelum_pajak'] = (sales_order['price'] * sales_order['quantity']) - sales_order['discount']
sales_order['open_sales_order'] = sales_order['total_sebelum_pajak'] + sales_order['tax1_value'] + sales_order['tax2_value']

open_sales_order = sales_order['open_sales_order'].sum()
potential_revenue = total_so_unpr2 + total_pr_unpr2 + total_po_unpr2 + total_grn_unpr2 + total_do_unpr2
total_prospektus_si = potential_revenue + total_revenue


#Realization
#Incoming Orders
incoming_orders = df_so_real.copy()
status_filter = ['In Progress', 'Approved', 'Need Approve', 'Draft']
incoming_orders = incoming_orders[incoming_orders['status_description'].isin(status_filter)]

incoming_orders['total_sebelum_pajak'] = (incoming_orders['price'] * incoming_orders['quantity']) - incoming_orders['discount']
incoming_orders['incoming_orders'] = incoming_orders['total_sebelum_pajak'] + incoming_orders['tax1_value'] + incoming_orders['tax2_value']

total_incoming_orders = incoming_orders['incoming_orders'].sum()

#Incoming Supply
incoming_supply = df_grn_real.copy()
incoming_supply['total_sebelum_pajak'] = (incoming_supply['price'] * incoming_supply['quantity']) - incoming_supply['discount']
incoming_supply['incoming_supply'] = incoming_supply['total_sebelum_pajak'] + incoming_supply['tax1_value'] + incoming_supply['tax2_value']

total_incoming_supply = incoming_supply['incoming_supply'].sum()


# Menghitung Total Amount Paid
total_amount_paid = df_vp_real.copy()
#total_amount_paid['price'] = pd.to_numeric(total_amount_paid['price'], errors='coerce')
status_filter = ['Complete']
#total_amount_paid = total_amount_paid[total_amount_paid['status_description'].isin(status_filter)]

#total_amount_paid['total_sebelum_pajak'] = (total_amount_paid['price'] * total_amount_paid['quantity']) - total_amount_paid['discount']
#total_amount_paid['total_amount_paid'] = total_amount_paid['total_sebelum_pajak'] + total_amount_paid['tax1_value'] + total_amount_paid['tax2_value']

#total_amount_paid = total_amount_paid['payment_amount'].sum()

#Total Amount Due
pr_created = df_pr_real.copy()
status_filter = ['In Progress', 'Approved', 'Need Approve']
pr_created = pr_created[pr_created['status_description'].isin(status_filter)]

pr_created['total_sebelum_pajak'] = (pr_created['price'] * pr_created['quantity']) - pr_created['discount']
pr_created['Total_PR_created'] = pr_created['total_sebelum_pajak'] + pr_created['tax1_value'] + pr_created['tax2_value']

Total_PR_created = pr_created['Total_PR_created'].sum()

po_created = df_po_real.copy()
Total_PO_created = po_created.groupby('transaction_number')['transaction_total'].last().sum()
do_created = df_do_real.copy()
Total_DO_created = do_created.groupby('transaction_number')['transaction_total'].last().sum()
#Jika 1 nomor transaksi punya banyak baris (per item)
#total_amount_paid = amount_paid[amount_paid['status_description'].isin(['Complete'])]
# Tambahkan nama kolom yang ingin dijumlahkan di bagian akhir


# --- 22. HEADER DASHBOARD ---
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

# --- 23. CUSTOM CSS (Untuk Mengecilkan Tulisan Angka Metric) ---
st.markdown("""
    <style>
    /* Mengecilkan ukuran angka pada metric */
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important; 
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
st.subheader("💰 Sales Performance Summary")
c1, c2, c3 = st.columns(3)
c1.metric("Revenue", f"Rp {total_revenue:,.0f}")
c2.metric("Potential Revenue", f"Rp {potential_revenue:,.0f}")
c3.metric("Open Sales Order", f"Rp {open_sales_order:,.0f}")
#c4.metric("All DO", f"Rp {total_all_do:,.0f}")
#c5.metric("All PO", f"Rp {total_all_po:,.0f}")

# --- 24. FITUR DOWNLOAD DATA TERFILTER 1 ---
st.subheader("📥 Download Data")

# Kita buat 3 kolom untuk tombol download agar rapi
col_dl1, = st.columns(1)

def convert_df(df):
    # Fungsi untuk konversi ke CSV (UTF-8)
    return df.to_csv(index=False, sep=',', quoting=csv.QUOTE_NONNUMERIC).encode('utf-8')

with col_dl1:
    if not df_download_revenue.empty:
        st.download_button(
            label="REVENUE",
            data=convert_df(df_download_revenue),
            file_name=f'Revenue_Detail_{today}.csv',
            mime='text/csv',
        )

st.subheader("Balance")
b = st.columns(3)
b[0].metric("SO Balance", f"Rp {total_so_unpr2:,.0f}")
#b[0].metric("SO Pending Supply", f"Rp {so_pending_supply:,.0f}")
#b[1].metric("SO Waiting Delivery", f"Rp {so_waiting_delivery:,.0f}")
b[1].metric("PR Balance", f"Rp {total_pr_unpr2:,.0f}")
b[2].metric("PO Balance", f"Rp {total_po_unpr2:,.0f}")
b = st.columns(3)
b[0].metric("GRN Balance", f"Rp {total_grn_unpr2:,.0f}")
b[1].metric("DO Balance", f"Rp {total_do_unpr2:,.0f}")
b[2].metric("Prospektus SI", f"Rp {total_prospektus_si:,.0f}")

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

# --- 24. FITUR DOWNLOAD DATA TERFILTER ---
st.subheader("📥 Download Data")

# Kita buat 3 kolom untuk tombol download agar rapi
col_dl1, col_dl2, col_dl3, col_dl4, col_dl5 = st.columns(5)

def convert_df(df):
    # Fungsi untuk konversi ke CSV (UTF-8)
    return df.to_csv(index=False, sep=',', quoting=csv.QUOTE_NONNUMERIC).encode('utf-8')

with col_dl1:
    if not df_download_so.empty:
        st.download_button(
            label="SO Balance",
            data=convert_df(df_download_so),
            file_name=f'SO_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl2:
    if not df_download_pr.empty:
        st.download_button(
            label="PR Balance",
            data=convert_df(df_download_pr),
            file_name=f'PR_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl3:
    # Contoh download data rekonsiliasi/balance
    if not df_download_po.empty:
        st.download_button(
            label="PO Balance",
            data=convert_df(df_download_po),
            file_name=f'PO_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl4:
    # Contoh download data rekonsiliasi/balance
    if not df_download_grn.empty:
        st.download_button(
            label="GRN Balance",
            data=convert_df(df_download_grn),
            file_name=f'GRN_Balance_Detail_{today}.csv',
            mime='text/csv',
        )

with col_dl5:
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
#b[2].metric("Total Amount Paid", f"Rp {total_amount_paid:,.0f}")
b2 = st.columns(3)
b2[0].metric("Total PR created", f"Rp {Total_PR_created:,.0f}")
b2[1].metric("Total PO created", f"Rp {Total_PO_created:,.0f}")
b2[2].metric("Total DO created", f"Rp {Total_DO_created:,.0f}")


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

# --- 25. FITUR DOWNLOAD DATA TERFILTER ---
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