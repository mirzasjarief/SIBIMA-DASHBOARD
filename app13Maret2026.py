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
df_vp = get_api_data("vendor-payments")

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

def clean_string_code(df, col):
    """Khusus untuk product_id: Menjaga nol di depan, hanya hapus spasi & ubah ke uppercase."""
    if col in df.columns:
        return (df[col].astype(str)
                .str.strip()
                .str.upper()
                .replace(['NAN', 'NONE', '', '0'], 'KOSONG'))
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
    for col in ['quantity', 'price', 'discount', 'tax1_percentage', 'tax2_percentage']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)


# Mengubah kolom 'date' menjadi 'transaction_date'
df_so_expanded = df_so_expanded.rename(columns={'date': 'transaction_date'})
df_po_expanded = df_po_expanded.rename(columns={'date': 'transaction_date'})

# --- 3. HANDLING INPUT TANGGAL ---
st.sidebar.header("📅 Filter period")

start_default = date(2026, 2, 1) # Diubah ke Feb agar sesuai case
end_default = date.today()

selected_date_range = st.sidebar.date_input(
    "Select Date Range:",
    value=(start_default, end_default),
    max_value=date.today()
)

# --- 5. FUNGSI FILTER ---
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

# --- 6. EKSEKUSI ---
df_so_real = apply_realization_filter(df_so_expanded, selected_date_range)
df_pr_real = apply_realization_filter(df_pr_expanded, selected_date_range)
df_po_real = apply_realization_filter(df_po_expanded, selected_date_range)
df_grn_real = apply_realization_filter(df_grn_expanded, selected_date_range)
df_do_real = apply_realization_filter(df_do_expanded, selected_date_range)
df_si_real = apply_realization_filter(df_si_expanded, selected_date_range)
df_vp_real = apply_realization_filter(df_vp_expanded, selected_date_range)

def apply_balance_filter(df, date_range):
    if df.empty: 
        return df
    
    df = df.copy()

    # 1. Pastikan kolom angka bertipe numerik
    if 'total_net_revenue_row' in df.columns:
        df['total_net_revenue_row'] = pd.to_numeric(df['total_net_revenue_row'], errors='coerce').fillna(0)
    
    # 2. Logika Filter Akumulatif (Cut-off)
    if 'transaction_date' in df.columns and isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        # Normalisasi kolom tanggal ke datetime tanpa timezone
        df['transaction_date'] = pd.to_datetime(df['transaction_date']).dt.tz_localize(None)
        
        # Ambil Batas Akhir (End Date) dari filter Streamlit
        # Contoh: Jika filter 1-28 Feb, maka end_dt adalah 28 Feb 23:59:59
        end_dt = pd.to_datetime(date_range[1]).replace(hour=23, minute=59, second=59)
        
        # LOGIKA UTAMA:
        # Kita abaikan 'start_date' dari filter user.
        # Kita ambil SEMUA data yang tanggalnya kurang dari atau sama dengan end_dt.
        # Dengan begini: Januari (masa lalu) IKUT, Maret (masa depan) TIDAK IKUT.
        df = df[df['transaction_date'] <= end_dt]

    return df
    
    # --- KELOMPOK BALANCE (Periode ini + Backlog) ---
if isinstance(selected_date_range, (tuple, list)) and len(selected_date_range) == 2:
    df_so_f = apply_balance_filter(df_so_expanded, selected_date_range)
    df_pr_f = apply_balance_filter(df_pr_expanded, selected_date_range)
    df_po_f = apply_balance_filter(df_po_expanded, selected_date_range)
    df_grn_f = apply_balance_filter(df_grn_expanded, selected_date_range)
    df_do_f = apply_balance_filter(df_do_expanded, selected_date_range)
    df_si_f = apply_balance_filter(df_si_expanded, selected_date_range)


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

#PERHITUNGAN DASHBOARD
# 1. Hitung Revenue
revenue = df_si_real.copy()
status_filter = ['In Progress', 'Approved', 'Draft', 'Complete']
revenue = revenue[revenue['status_description'].isin(status_filter)]
revenue['total_sebelum_pajak'] = (revenue['price'] * revenue['quantity']) - revenue['discount']
revenue['total_net_revenue_row'] = revenue['total_sebelum_pajak'] + revenue['tax1_value'] + revenue['tax2_value']

# Baru kemudian di-sum
revenue = revenue['total_net_revenue_row'].sum() if not revenue.empty else 0


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


# --- RECONCILE LOGIC ENHANCED (Sesuai Alur Whiteboard) ---
status_base = ['In Progress', 'Approved',]
#status_compare = ['In Progress', 'Approved', 'Need Approve', 'Complete', 'Draft']
status_compare = ['In Progress', 'Approved', 'Need Approve', 'Complete']

# --- FUNGSI PEMBERSIH ---
# Tambahkan logika replace pada fungsi pembersih
def clean_special_chars(df, col):
    if col in df.columns:
        # Mengganti ';' dengan spasi atau karakter lain agar aman
        return df[col].astype(str).str.replace(';', ' ', regex=False).str.strip()
    return ""

# Terapkan sebelum grouping
df_so_f['item_name'] = clean_special_chars(df_so_f, 'item_name')

def clean_newline(df, col):
    if col in df.columns:
        # Menghapus enter (\n atau \r) dan mengganti ';' dengan space
        return df[col].astype(str).str.replace(r'[\n\r]+', ' ', regex=True).str.replace(';', ' ', regex=False).str.strip()
    return ""

# Terapkan ke semua dataframe yang memiliki kolom description sebelum di-grouping
df_so_f['description'] = clean_newline(df_so_f, 'description')
df_pr_f['description'] = clean_newline(df_pr_f, 'description')
df_po_f['description'] = clean_newline(df_po_f, 'description')
df_grn_f['description'] = clean_newline(df_grn_f, 'description')
df_do_f['description'] = clean_newline(df_do_f, 'description')


# FIX ERROR 'so_transaction_number' di PO: Mapping ulang dari PR asli
pr_map = df_pr_f[['transaction_number', 'product_id', 'so_transaction_number']].drop_duplicates()
df_po_f = pd.merge(df_po_f, pr_map, left_on=['pr_transaction_number', 'product_id'], right_on=['transaction_number', 'product_id'], how='left', suffixes=('', '_map'))

# Pastikan kolom so_transaction_number ada di PO sebelum groupby
if 'so_transaction_number' not in df_po_f.columns:
    df_po_f['so_transaction_number'] = 'KOSONG'
else:
    df_po_f['so_transaction_number'] = df_po_f['so_transaction_number'].fillna('KOSONG')

# --- FILTER EXCLUSION (Hapus Customer Tertentu) ---
#customers_to_exclude = ['EAS GROUP', 'PT. JHONLIN AGRO RAYA TBK', 'PT. KODECO AGROJAYA MANDIRI', 'PT. TUNAS HUTAN MANDIRI', 'PT. PRADIKSI GUNATAMA', 'PT. MULTI SARANA AGRO MANDIRI', 'PT. HASIL PRIMA JAYA']
customers_to_exclude = ['EAS GROUP']

# Hapus dari data SO agar tidak muncul di dashboard/reconcile
df_so_f = df_so_f[~df_so_f['customer_name'].astype(str).str.upper().isin([c.upper() for c in customers_to_exclude])]
# Hapus dari data PR agar tidak muncul di dashboard/reconcile
df_pr_f = df_pr_f[~df_pr_f['customer_name'].astype(str).str.upper().isin([c.upper() for c in customers_to_exclude])]
# Hapus dari data PO agar tidak muncul di dashboard/reconcile
df_po_f = df_po_f[~df_po_f['customer_name'].astype(str).str.upper().isin([c.upper() for c in customers_to_exclude])]

# Pastikan ini dilakukan sebelum Grouping GRN
po_map = df_po_f[['transaction_number', 'product_id', 'so_transaction_number']].drop_duplicates()

df_grn_f = pd.merge(
    df_grn_f, 
    po_map, 
    left_on=['po_transaction_number', 'product_id'], 
    right_on=['transaction_number', 'product_id'], 
    how='left',
    suffixes=('', '_map')
    )

# Pastikan kolom so_transaction_number ada di PO sebelum groupby
if 'so_transaction_number' not in df_grn_f.columns:
    df_grn_f['so_transaction_number'] = 'KOSONG'
else:
    df_grn_f['so_transaction_number'] = df_grn_f['so_transaction_number'].fillna('KOSONG')


# --- 7. HITUNG STOK (SOH) ---
df_grn_total = df_grn_f.groupby('product_id')['quantity'].sum().reset_index(name='total_grn')
df_do_total = df_do_f.groupby('product_id')['quantity'].sum().reset_index(name='total_do_global')
df_soh = pd.merge(df_grn_total, df_do_total, on='product_id', how='left').fillna(0)
df_soh['current_soh'] = (df_soh['total_grn'] - df_soh['total_do_global']).clip(lower=0)

# --- LOGIKA MAPPING so_transaction_numberD KE SI ---
# SI biasanya tidak punya so_transaction_number langsung, kita ambil dari mapping DO
do_map = df_do_f[['transaction_number', 'product_id', 'so_transaction_number']].drop_duplicates()

# Pastikan menggunakan nama kolom yang benar di file SI (biasanya do_transaction_number)
df_si_f = pd.merge(
    df_si_f, 
    do_map, 
    left_on=['do_transaction_number', 'product_id'], 
    right_on=['transaction_number', 'product_id'], 
    how='left'
).drop(columns=['transaction_number_y'], errors='ignore')

# Ambil kolom so_transaction_number hasil merge, jika tidak ada (NaN) isi KOSONG
if 'so_transaction_number' in df_si_f.columns:
    df_si_f['so_transaction_number'] = df_si_f['so_transaction_number'].fillna('KOSONG')
else:
    df_si_f['so_transaction_number'] = 'KOSONG'

# --- 8. EKSEKUSI FILTER STATUS ---
# --- SO (Selalu sebagai Base) ---
df_so_base = df_so_f[df_so_f['status_description'].isin(status_base)].copy()

# --- PR ---
df_pr_base = df_pr_f[df_pr_f['status_description'].isin(status_base)].copy() # Untuk hitung PR Balance
df_pr_comp = df_pr_f[df_pr_f['status_description'].isin(status_compare)].copy() # Untuk pengurang SO Balance

# --- PO ---
df_po_base = df_po_f[df_po_f['status_description'].isin(status_base)].copy() # Untuk hitung PO Balance
df_po_comp = df_po_f[df_po_f['status_description'].isin(status_compare)].copy() # Untuk pengurang PR Balance

# --- GRN ---
df_grn_base = df_grn_f[df_grn_f['status_description'].isin(status_base)].copy() # Untuk hitung GRN Balance
df_grn_comp = df_grn_f[df_grn_f['status_description'].isin(status_compare)].copy() # Untuk pengurang PO Balance

# --- DO ---
df_do_base = df_do_f[df_do_f['status_description'].isin(status_base)].copy() # Untuk hitung DO Balance
df_do_comp = df_do_f[df_do_f['status_description'].isin(status_compare)].copy() # Untuk pengurang GRN Balance

# --- SI (Selalu sebagai Compare) ---
df_si_comp = df_si_f[df_si_f['status_description'].isin(status_compare)].copy()

# --- 9. GROUPING DATA ---
def get_grouped(df, qty_col_name):
    # Cek apakah kolom yang dibutuhkan ada
    if 'so_transaction_number' not in df.columns or 'product_id' not in df.columns:
        # Jika kolom tidak ada, kembalikan DF kosong dengan struktur yang benar agar merge tidak error
        return pd.DataFrame(columns=['so_transaction_number', 'product_id', qty_col_name])
    
    if df.empty: 
        return pd.DataFrame(columns=['so_transaction_number', 'product_id', qty_col_name])
        
    agg_dict = {'quantity': 'sum'}
    if 'transaction_number' in df.columns: agg_dict['transaction_number'] = lambda x: ', '.join(x.unique().astype(str))
    if 'description' in df.columns: agg_dict['description'] = 'first'
    if 'status_description' in df.columns: agg_dict['status_description'] = 'first'
    
    return df.groupby(['so_transaction_number', 'product_id'], as_index=False).agg(agg_dict).rename(columns={'quantity': qty_col_name})

# Grouping Base (Untuk Header/Saldo Utama)
so_g = df_so_base.groupby(['so_transaction_number', 'product_id'], as_index=False).agg({
    'quantity': 'sum', 'price': 'first', 'discount': 'sum', 'tax1_percentage': 'first', 
    'tax2_percentage': 'first', 'item_name': 'first', 'customer_name': 'first', 'transaction_number': 'first', 'status_description': 'first', 'transaction_date': 'first',
}).rename(columns={'quantity': 'qty_so', 'transaction_number': 'no_so', 'status_description': 'stat_desc_so'})

pr_base_g = get_grouped(df_pr_base, 'qty_pr_base').rename(columns={'transaction_number': 'no_pr', 'description': 'desc_pr', 'status_description': 'stat_desc_pr'})
po_base_g = get_grouped(df_po_base, 'qty_po_base').rename(columns={'transaction_number': 'no_po', 'description': 'desc_po', 'status_description': 'stat_desc_po'})
grn_base_g = get_grouped(df_grn_base, 'qty_grn_base').rename(columns={'transaction_number': 'no_grn', 'description': 'desc_grn', 'status_description': 'stat_desc_grn'})
do_base_g = get_grouped(df_do_base, 'qty_do_base').rename(columns={'transaction_number': 'no_do', 'description': 'desc_do', 'status_description': 'stat_desc_do'})

# Grouping Compare (Hanya ambil Qty-nya saja untuk pengurang)
pr_comp_g = get_grouped(df_pr_comp, 'qty_pr_comp')[['so_transaction_number', 'product_id', 'qty_pr_comp']]
po_comp_g = get_grouped(df_po_comp, 'qty_po_comp')[['so_transaction_number', 'product_id', 'qty_po_comp']]
grn_comp_g = get_grouped(df_grn_comp, 'qty_grn_comp')[['so_transaction_number', 'product_id', 'qty_grn_comp']]
do_comp_g = get_grouped(df_do_comp, 'qty_do_comp')[['so_transaction_number', 'product_id', 'qty_do_comp']]
si_comp_g = get_grouped(df_si_comp, 'qty_si_comp')[['so_transaction_number', 'product_id', 'qty_si_comp']]

# --- 10. MERGE SEMUA KE MASTER ---
reconcile_master = so_g.copy()
for other_df in [pr_base_g, pr_comp_g, po_base_g, po_comp_g, grn_base_g, grn_comp_g, do_base_g, do_comp_g, si_comp_g]:
    reconcile_master = pd.merge(reconcile_master, other_df, on=['so_transaction_number', 'product_id'], how='left').fillna(0)

# Tambahkan stok gudang (SOH) ke master berdasarkan product_id
reconcile_master = pd.merge(reconcile_master, df_soh[['product_id', 'current_soh']], on='product_id', how='left').fillna(0)

# --- 11. KALKULASI LOGIKA BARU ---
reconcile_master['qty_pr_comp'] = reconcile_master['qty_pr_comp'].fillna(0)
reconcile_master['qty_do_comp'] = reconcile_master['qty_do_comp'].fillna(0)
reconcile_master['qty_po_comp'] = reconcile_master['qty_po_comp'].fillna(0)
reconcile_master['qty_grn_comp'] = reconcile_master['qty_grn_comp'].fillna(0)

# A. Hitung Nilai Per Unit yang Akurat
# Kita hitung Pajak per unit berdasarkan (Harga - Diskon per unit)
reconcile_master['disc_per_unit'] = reconcile_master['discount'] / reconcile_master['qty_so'].replace(0, 1)

# Rumus Pajak: (Price - Disc) * Tax%
reconcile_master['tax_unit'] = (reconcile_master['price'] - reconcile_master['disc_per_unit']) * \
                               ((reconcile_master['tax1_percentage'] + reconcile_master['tax2_percentage']) / 100)

# Net Price Unit adalah harga yang sudah bersih (Price - Disc + Tax)
reconcile_master['net_price_unit'] = reconcile_master['price'] - reconcile_master['disc_per_unit'] + reconcile_master['tax_unit']


# ---12. LOGIKA DASHBOARD BALANCE ---

# Outstanding Pesanan
reconcile_master['qty_outstanding'] = (reconcile_master['qty_so'] - reconcile_master['qty_do_comp']).clip(lower=0)

# A. SO BALANCE (Barang belum diminta atau belum dikirim)
reconcile_master['true_so_outstanding'] = (reconcile_master['qty_so'] - reconcile_master[['qty_pr_comp', 'qty_do_comp']].max(axis=1)).clip(lower=0)

reconcile_master['qty_waiting_delivery'] = reconcile_master[['true_so_outstanding', 'current_soh']].min(axis=1)

reconcile_master['true_pending_qty'] = (reconcile_master['qty_so'] - reconcile_master['qty_pr_comp'] - reconcile_master['current_soh'] - reconcile_master['qty_do_comp'].clip(lower=0)).clip(lower=0)

reconcile_master['amt_so_balance'] = (reconcile_master['true_pending_qty'] + reconcile_master['qty_waiting_delivery']) * reconcile_master['net_price_unit']

# B. PR BALANCE (PR belum di-PO)
reconcile_master['qty_pr_balance'] = (reconcile_master['qty_pr_base'] - reconcile_master['qty_po_comp']).clip(lower=0)
reconcile_master['amt_pr_balance'] = reconcile_master['qty_pr_balance'] * reconcile_master['net_price_unit']

# C. PO BALANCE (Barang di jalan)
reconcile_master['qty_po_balance'] = (reconcile_master['qty_po_base'] - reconcile_master['qty_grn_comp']).clip(lower=0)
reconcile_master['amt_po_balance'] = reconcile_master['qty_po_balance'] * reconcile_master['net_price_unit']

# D. GRN BALANCE (Stok per SO yang mengendap)
reconcile_master['qty_grn_balance'] = (reconcile_master['qty_grn_base'] - reconcile_master['qty_do_comp']).clip(lower=0)
reconcile_master['amt_grn_balance'] = reconcile_master['qty_grn_balance'] * reconcile_master['net_price_unit']

# E. DO BALANCE (Stok per SO yang mengendap)
#reconcile_master['qty_grn_balance'] = (reconcile_master['qty_grn'] - reconcile_master['qty_do']).clip(lower=0)
reconcile_master['qty_do_balance'] = (reconcile_master['qty_do_base'] - reconcile_master['qty_si_comp']).clip(lower=0)
reconcile_master['amt_do_balance'] = reconcile_master['qty_do_balance'] * reconcile_master['net_price_unit']

# --- 13. AGREGASI FINAL UNTUK DASHBOARD ---
total_so_unpr2 = reconcile_master['amt_so_balance'].sum()
total_pr_unpr2 = reconcile_master['amt_pr_balance'].sum()
total_po_unpr2 = reconcile_master['amt_po_balance'].sum()
total_grn_unpr2 = reconcile_master['amt_grn_balance'].sum()
total_do_unpr2 = reconcile_master['amt_do_balance'].sum()

# --- 14. PREPARASI SEMUA DATAFRAME DOWNLOAD ---

# 1. DOWNLOAD SO PENDING SUPPLY (Barang yang belum ada Stok & belum ada PR)
df_download_so = reconcile_master[reconcile_master['amt_so_balance'] > 0][[
    'no_so', 'transaction_date', 'stat_desc_so', 'stat_desc_pr', 'customer_name', 'product_id', 'item_name', 'price', 
    'qty_so', 'qty_do_comp', 'qty_pr_comp', 'current_soh', 'true_pending_qty','qty_waiting_delivery','amt_so_balance'
]].copy()

df_download_so.columns = [
    'No. SO', 'Tanggal Transaksi', 'Status SO', 'Status PR', 'Customer', 'ID Produk', 'Nama Barang', 'Harga Satuan',
    'Qty Order', 'Qty Terkirim', 'Qty Sudah PR', 'Stok Gudang', 'Qty Harus Belanja','Qty Harus Dikirim', 'Amount'
]

# 2. DOWNLOAD PR BALANCE (PR yang sudah dibuat tapi belum jadi PO)
df_download_pr = reconcile_master[reconcile_master['amt_pr_balance'] > 0][[
    'no_so', 'no_pr', 'stat_desc_pr', 'desc_pr', 'customer_name', 'product_id', 'item_name', 'price',
    'qty_pr_base', 'qty_po_comp', 'qty_pr_balance','amt_pr_balance'
]].copy()

df_download_pr.columns = [
    'No. SO', 'No. PR', 'Status PR', 'Description PR', 'Customer', 'ID Produk', 'Nama Barang', 'Harga Jual',
    'Qty Permintaan (PR)', 'Qty Sudah PO', 'Qty Outstanding PR (to PO)','Nominal'
]

# 3. DOWNLOAD PO BALANCE (PO yang sudah dibuat tapi barang belum sampai/GRN)
df_download_po = reconcile_master[reconcile_master['amt_po_balance'] > 0][[
    'no_so', 'no_po', 'stat_desc_po', 'desc_po', 'customer_name', 'product_id', 'item_name', 
    'qty_po_base', 'qty_grn_comp', 'qty_po_balance', 'amt_po_balance'
]].copy()

df_download_po.columns = [
    'No. SO', 'No. PO', 'Status PO', 'Description PO', 'Customer', 'ID Produk', 'Nama Barang',
    'Qty Belanja (PO)', 'Qty Sudah Masuk (GRN)', 'Qty Outstanding PO (Barang belum di-GRN)','Nominal'
]

# 4. DOWNLOAD GRN BALANCE (Barang sudah di gudang tapi belum dikirim/DO)
df_download_grn = reconcile_master[reconcile_master['amt_grn_balance'] > 0][[
    'no_so', 'no_po', 'no_grn', 'stat_desc_grn', 'desc_grn', 'customer_name', 'product_id', 'item_name', 
    'qty_grn_base', 'qty_do_comp', 'qty_grn_balance', 'amt_grn_balance'
]].copy()

df_download_grn.columns = [
    'No. SO', 'No. PO', 'No. GRN', 'Status GRN', 'Description GRN', 'Customer', 'ID Produk', 'Nama Barang',
    'Qty Masuk (GRN)', 'Qty Keluar (DO)', 'Qty Outstanding', 'Nominal'
]


# --- 15. FORMATTING AKHIR (Membersihkan desimal menjadi Integer) ---
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
    exclude_cols = ['ID Produk', 'SO. Id', 'ID Produk']
    
    # Filter kolom: hanya konversi jika kolom tersebut tidak ada dalam exclude_cols
    cols_to_convert = [c for c in num_cols if c not in exclude_cols]
    
    # Jalankan konversi hanya untuk kolom qty dan nominal
    df_dl[cols_to_convert] = df_dl[cols_to_convert].fillna(0).astype(int)
    
    # Pastikan ID Produk tetap string
    if 'ID Produk' in df_dl.columns:
        df_dl['ID Produk'] = df_dl['ID Produk'].astype(str)


# DOWNLOAD SI BALANCE (DO Belum Invoice)
df_download_do = reconcile_master[reconcile_master['amt_do_balance'] > 0][[
    'no_so', 'no_po', 'stat_desc_do' , 'desc_po', 'no_do', 'desc_do', 'customer_name', 'product_id', 'item_name', 
    'qty_do_base', 'qty_si_comp', 'qty_do_balance','amt_do_balance'
]].copy()

df_download_do.columns = [
    'No. SO', 'No. PO', 'Status DO', 'Description PO', 'No. DO', 'Description DO', 'Customer', 'ID Produk', 'Nama Barang',
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
total_prospektus_si = potential_revenue + revenue


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

# =========================================================
# REVISI FINAL: MAPPING TAHAN BANTING (ANTI-KEYERROR)
# =========================================================

# --- FUNGSI PEMBERSIH AMAN ---
def clean_key_safe(series):
    if series is None or series.empty:
        return series
    return series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()

# --- 17. PROTEKSI KOLOM AWAL ---
# Pastikan kolom kunci minimal ada (meski kosong) agar tidak error saat dipanggil
for df_tmp in [df_po_f, df_si_f, df_do_f]:
    if 'so_id' not in df_tmp.columns:
        df_tmp['so_id'] = np.nan
    if 'product_id' not in df_tmp.columns:
        df_tmp['product_id'] = "KOSONG"

# --- 18. MAPPING PO ---
# Jika so_id di PO kosong, coba ambil dari PR
if 'pr_transaction_number' in df_po_f.columns and not df_pr_f.empty:
    pr_map = df_pr_f[['transaction_number', 'product_id', 'so_id']].drop_duplicates()
    df_po_f = pd.merge(
        df_po_f, pr_map,
        left_on=['pr_transaction_number', 'product_id'],
        right_on=['transaction_number', 'product_id'],
        how='left', suffixes=('', '_pr_map')
    )
    # Jika ketemu so_id dari PR, pakai itu
    if 'so_id_pr_map' in df_po_f.columns:
        df_po_f['so_id'] = df_po_f['so_id'].fillna(df_po_f['so_id_pr_map'])

# Buat Mapping PO (Hanya yang punya SO ID valid)
df_po_valid = df_po_f.dropna(subset=['so_id']).copy()
# Filter tambahan agar string '0' atau 'KOSONG' tidak ikut masuk mapping
df_po_valid = df_po_valid[~df_po_valid['so_id'].astype(str).isin(['0', '0.0', 'nan', 'KOSONG'])]

if not df_po_valid.empty:
    df_po_valid['so_id_clean'] = clean_key_safe(df_po_valid['so_id'])
    df_po_valid['prod_clean'] = clean_key_safe(df_po_valid['product_id'])

    po_mapping_final = df_po_valid.groupby(['so_id_clean', 'prod_clean'], as_index=False).agg({
        'transaction_number': lambda x: ', '.join(x.unique().astype(str))
    }).rename(columns={'transaction_number': 'no_po_ref'})
else:
    po_mapping_final = pd.DataFrame(columns=['so_id_clean', 'prod_clean', 'no_po_ref'])

# --- 19. PROSES DATA SI & DO ---
# Ambil referensi SO_ID dari DO untuk membantu SI
do_ref = df_do_f[['transaction_number', 'product_id', 'so_id']].drop_duplicates()
do_ref.columns = ['do_transaction_number', 'product_id', 'so_id_from_do']

# Gabung ke SI
df_si_complete = pd.merge(
    df_si_f, do_ref,
    on=['do_transaction_number', 'product_id'],
    how='left'
)

# Gabungkan SO ID asli SI dengan hasil temuan dari DO
df_si_complete['so_id_final'] = df_si_complete['so_id'].fillna(df_si_complete['so_id_from_do'])

# --- 20. MERGE AKHIR (SI + PO MAPPING) ---
df_si_complete['so_id_clean'] = clean_key_safe(df_si_complete['so_id_final'])
df_si_complete['prod_clean'] = clean_key_safe(df_si_complete['product_id'])

df_si_final = pd.merge(
    df_si_complete,
    po_mapping_final,
    on=['so_id_clean', 'prod_clean'],
    how='left'
)

# --- 21. FINISHING & DISPLAY (DENGAN NAMA BARANG & HARGA) ---
cols_to_show = {
    'transaction_number': 'No. SI (Invoice)',
    'do_transaction_number': 'No. DO',
    'no_po_ref': 'No. PO',
    'so_id_clean': 'SO ID',
    'product_id': 'ID Produk',
    'item_name': 'Nama Barang',   # Tambahan Kolom Nama
    'quantity': 'Qty',
    'price': 'Harga Satuan'       # Tambahan Kolom Harga
}

# 1. Pastikan kolom yang dibutuhkan ada di df_si_final
# Jika kolom 'item_name' tidak ada di SI, biasanya ada di df_so_expanded atau df_do_expanded
# Kita lakukan proteksi sederhana:
if 'item_name' not in df_si_final.columns:
    df_si_final['item_name'] = "Nama Tidak Terdeteksi"

# 2. Ambil kolom yang benar-benar ada saja
existing_cols = [c for c in cols_to_show.keys() if c in df_si_final.columns]
df_si_report = df_si_final[existing_cols].rename(columns=cols_to_show)

# 3. Format angka agar lebih enak dibaca (Opsional)
if 'Harga Satuan' in df_si_report.columns:
    df_si_report['Harga Satuan'] = df_si_report['Harga Satuan'].map('{:,.0f}'.format)
if 'Qty' in df_si_report.columns:
    df_si_report['Qty'] = pd.to_numeric(df_si_report['Qty'], errors='coerce').fillna(0).astype(int)

#st.write("### Laporan Penjualan Lengkap (SI, DO, PO)")
#st.dataframe(df_si_report, use_container_width=True)

# --- STEP: MENGHITUNG HPP MOVING AVERAGE ---

def calculate_moving_average_hpp(df_purchase):
    if df_purchase.empty:
        return pd.DataFrame(columns=['product_id', 'hpp_avg'])
    
    # 1. Urutkan berdasarkan tanggal agar urutan pembelian benar
    df_sorted = df_purchase.sort_values(by='transaction_date').copy()
    
    # 2. Hitung Total Nilai (Qty * Harga) per transaksi
    df_sorted['total_value'] = df_sorted['quantity'] * df_sorted['price']
    
    # 3. Grouping berdasarkan product_id
    # Kita hitung kumulatif Nilai dan kumulatif Qty
    ma_data = df_sorted.groupby('product_id').agg({
        'total_value': 'sum',
        'quantity': 'sum'
    }).reset_index()
    
    # 4. Hitung Rata-rata (HPP Average)
    # Gunakan np.where untuk menghindari pembagian dengan nol
    ma_data['hpp_avg'] = np.where(
        ma_data['quantity'] > 0, 
        ma_data['total_value'] / ma_data['quantity'], 
        0
    )
    
    return ma_data[['product_id', 'hpp_avg']]

# --- EKSEKUSI ---
# Gunakan df_po_expanded atau df_grn_expanded sebagai sumber biaya
df_hpp_ma = calculate_moving_average_hpp(df_po_expanded)

# --- GABUNGKAN KE LAPORAN SI ---
df_si_final = pd.merge(
    df_si_final, 
    df_hpp_ma, 
    on='product_id', 
    how='left'
)

# Hitung Margin menggunakan hpp_avg
df_si_final['hpp_avg'] = df_si_final['hpp_avg'].fillna(0)
df_si_final['margin_rp'] = df_si_final['price'] - df_si_final['hpp_avg']
df_si_final['margin_pct'] = (df_si_final['margin_rp'] / df_si_final['price'] * 100).fillna(0)


# MAPPING HARGA DARI PO BERDASARKAN NO_PO_REF
# Pastikan kita ambil harga unik per PO dan Product
po_prices = df_po_expanded[['transaction_number', 'product_id', 'price']].drop_duplicates()
po_prices.columns = ['no_po_ref', 'product_id', 'harga_beli_spesifik']

# Merge ke SI Final
df_si_final = pd.merge(
    df_si_final, 
    po_prices, 
    on=['no_po_ref', 'product_id'], 
    how='left'
)

# 1. Pastikan kolom fallback ada
if 'harga_beli_spesifik' not in df_si_final.columns:
    df_si_final['harga_beli_spesifik'] = np.nan

# 2. Gabungkan prioritas (Pilih Spesifik, kalau kosong pilih Average)
df_si_final['hpp_final'] = df_si_final['harga_beli_spesifik'].fillna(df_si_final['hpp_avg'])

# 3. Hitung Margin Final (Gunakan hpp_final!)
df_si_final['margin_rp'] = df_si_final['price'] - df_si_final['hpp_final']
df_si_final['margin_pct'] = (df_si_final['margin_rp'] / df_si_final['price'] * 100).replace([np.inf, -np.inf], 0).fillna(0)

# 4. Tambahkan Penanda (Opsional tapi sangat membantu untuk audit)
df_si_final['sumber_hpp'] = np.where(df_si_final['harga_beli_spesifik'].notna(), 'PO Spesifik', 'Moving Average')

# 1. Hitung Total Margin dalam Rupiah (Margin per unit x Qty terjual)
df_si_final['total_margin_amount'] = df_si_final['margin_rp'] * df_si_final['quantity']

# 2. Hitung Total Revenue untuk pembanding (Opsional)
df_si_final['total_revenue_amount'] = df_si_final['price'] * df_si_final['quantity']

# Menghitung total keseluruhan
total_margin_rp = df_si_final['total_margin_amount'].sum()
total_revenue_rp = df_si_final['total_revenue_amount'].sum()
avg_margin_pct = (total_margin_rp / total_revenue_rp * 100) if total_revenue_rp > 0 else 0



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
c1.metric("Revenue", f"Rp {revenue:,.0f}")
c2.metric("Potential Revenue", f"Rp {potential_revenue:,.0f}")
c3.metric("Open Sales Order", f"Rp {open_sales_order:,.0f}")
#c4.metric("All DO", f"Rp {total_all_do:,.0f}")
#c5.metric("All PO", f"Rp {total_all_po:,.0f}")

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