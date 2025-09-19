
import streamlit as st
import pandas as pd
from io import BytesIO
import re

st.set_page_config(page_title="🔄 UPC Merge Tool (UPC Parsing Fixed)", layout="wide")
st.title("🔄 UPC Merge Tool (Fixed UPC Format Parsing)")

st.markdown("""
✅ This version fixes the issue where UPCs formatted with hyphens (like `0-51900-40077-3`) were being parsed as all zeroes.

🔧 Improvements:
- Correctly parses formatted UPCs by removing non-digit characters
- Supports multi-tab Excel, header detection, flexible column mapping, and category parsing
""")

def detect_header_row(df):
    for i in range(min(5, len(df))):
        row = df.iloc[i].astype(str).str.lower().str.strip()
        if any(col in row.tolist() for col in ['title', 'description', 'gtin', 'upc', 'barcode']):
            return i
    return 0

def extract_size_components(desc):
    desc = desc.lower()
    size_match = re.search(r'(\d+(\.\d+)?)\s?(oz|fl oz|l|ml|gallon|gal)', desc)
    count_match = re.search(r'(\d+)\s?ct', desc)
    size_value = size_match.group(1) if size_match else None
    size_measure = size_match.group(3).upper() if size_match else None
    count_value = count_match.group(1) if count_match else None
    count_measure = 'CT' if count_match else None
    return pd.Series({
        'sizeValue': size_value,
        'sizeMeasure': size_measure,
        'itemCountValue': count_value,
        'itemCountMeasure': count_measure
    })

# Upload interface
upc_file = st.file_uploader("📤 Upload Cleaned UPC Excel File", type=["xlsx"])
partner_file = st.file_uploader("📤 Upload Partner Product File", type=["xlsx"])

if upc_file and partner_file:
    raw = pd.read_excel(upc_file, header=None)
    header_row = detect_header_row(raw)
    all_sheets = pd.read_excel(upc_file, sheet_name=None, header=header_row)
    valid_sheets = [s for s in all_sheets.values() if s.shape[0] > 1]

    if not valid_sheets:
        st.error("❌ No usable sheets found.")
    else:
        upc_df = pd.concat(valid_sheets, ignore_index=True)
        partner_df = pd.read_excel(partner_file)

        upc_df.columns = [col.lower().strip() for col in upc_df.columns]
        columns = upc_df.columns.tolist()

        desc_col = 'title' if 'title' in columns else ('description' if 'description' in columns else None)
        if not desc_col:
            desc_col = st.selectbox("⚠️ Select the column to use as product description:", options=columns)

        upc_col = 'gtin' if 'gtin' in columns else (
            'upc' if 'upc' in columns else (
                'barcode' if 'barcode' in columns else None
            )
        )
        if not upc_col:
            upc_col = st.selectbox("⚠️ Select the column to use as UPC/barcode:", options=columns)

        brand_col = 'brand' if 'brand' in columns else None
        cat_col = next((col for col in columns if upc_df[col].astype(str).str.contains('>').any()), None)

        st.markdown("#### Mapped Columns")
        st.write(f"📝 Description: `{desc_col}`")
        st.write(f"🔑 Barcode: `{upc_col}`")
        st.write(f"🏷️ Brand: `{brand_col}`")
        st.write(f"📂 Category Hierarchy: `{cat_col}`")

        if not desc_col or not upc_col:
            st.error("❌ Description and barcode column are required.")
        else:
            if st.button("🚀 Merge & Download"):
                upc_df[upc_col] = (
                    upc_df[upc_col]
                    .astype(str)
                    .str.replace(r'[^\d]', '', regex=True)  # Fix: remove all non-digits
                    .str.zfill(12)
                )
                partner_df['barcode'] = partner_df['barcode'].astype(str).str.extract(r'(\d+)', expand=False).fillna('').str.zfill(12)

                upc_df['STATUS'] = upc_df[upc_col].apply(lambda x: 'Existing' if x in set(partner_df['barcode']) else 'New')
                new_upcs_df = upc_df[upc_df['STATUS'] == 'New'].copy()

                parsed_fields = new_upcs_df[desc_col].fillna('').apply(extract_size_components)
                new_upcs_df = pd.concat([new_upcs_df, parsed_fields], axis=1)

                if cat_col:
                    cats = new_upcs_df[cat_col].fillna('').str.split('>', expand=True)
                    new_upcs_df['ch1Department'] = cats[0].str.strip().fillna("N/A") if 0 in cats else "N/A"
                    new_upcs_df['ch2Category'] = cats[1].str.strip().fillna("N/A") if 1 in cats else "N/A"
                    new_upcs_df['ch3Segment'] = cats[2].str.strip().fillna("N/A") if 2 in cats else "N/A"
                else:
                    new_upcs_df['ch1Department'] = "N/A"
                    new_upcs_df['ch2Category'] = "N/A"
                    new_upcs_df['ch3Segment'] = "N/A"

                new_rows = pd.DataFrame({
                    'barcode': new_upcs_df[upc_col],
                    'bh2Brand': new_upcs_df[brand_col].str.upper() if brand_col else "N/A",
                    'name': new_upcs_df[desc_col],
                    'description': new_upcs_df[desc_col],
                    'ch1Department': new_upcs_df['ch1Department'],
                    'ch2Category': new_upcs_df['ch2Category'],
                    'ch3Segment': new_upcs_df['ch3Segment'],
                    'itemCountValue': new_upcs_df['itemCountValue'],
                    'itemCountMeasure': new_upcs_df['itemCountMeasure'],
                    'sizeValue': new_upcs_df['sizeValue'],
                    'sizeMeasure': new_upcs_df['sizeMeasure'],
                    'partnerProduct': 'Y',
                    'awardPoints': 'N'
                })

                for col in partner_df.columns:
                    if col not in new_rows.columns:
                        new_rows[col] = None
                new_rows = new_rows[partner_df.columns]

                merged_df = pd.concat([partner_df, new_rows], ignore_index=True)

                output = BytesIO()
                merged_df.to_excel(output, index=False, engine='openpyxl')
                output.seek(0)

                st.download_button(
                    label="📥 Download Final Merged File",
                    data=output,
                    file_name="merged_upcs_fixed_format.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
