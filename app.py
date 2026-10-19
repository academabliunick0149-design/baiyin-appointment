import streamlit as st
import pandas as pd
import urllib.request
import io
import re
import ssl
from collections import defaultdict

# 🌟 破解 Mac 與 Windows SSL 檢查
ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(page_title="百胤預約自動化系統", layout="centered")
st.title("🏥 百胤視力整復所 - 預約訊息 (V19 雙分店與智慧分頁最終版 v12)")

# 🌟 初始化排除關鍵字
if 'admin_keywords' not in st.session_state:
    st.session_state['admin_keywords'] = [
        '進修', '跟診', '需調時間', '看醫生', '休診', '會議', 
        '家裡有事取消', '鄭秉萱陪診', '林芸榛出差取消看診'
    ]

sheet_url = st.text_input(
    "🔗 Google 試算表網址：", 
    value="https://docs.google.com/spreadsheets/d/1vPi0H9hK-oKOIv0f3dnPR0EylcY2ICwgTYAUQQUne-c/edit?usp=sharing"
)

def trigger_analysis():
    st.session_state['analysis_done'] = False
    st.session_state['unknown_entities'] = []
    st.session_state['auto_run_stage1'] = True
    # Clear any cached daily reconciliation sheets
    for k in list(st.session_state.keys()):
        if k.startswith("reconcile_df_"):
            del st.session_state[k]

target_date_input = st.text_input("📅 請輸入日期 (例如 20260530)：", on_change=trigger_analysis)

# 🌟 時間與日期轉換輔助工具
v0, v1, v2, v4, v6, v8 = 0, 1, 2, 4, 6, 8

def format_date(d_str):
    d_str = str(d_str).replace(" 00:00:00", "").strip()
    if "-" in d_str:
        parts = d_str.split("-")
        if len(parts) == 3:
            parts.pop(v0)
            return f"{int(parts.pop(v0))}/{int(parts.pop(v0))}"
    return d_str

def parse_cell_date(cell_val):
    s = str(cell_val).strip()
    if not s or s.lower() == 'nan':
        return None
    s = s.replace(" 00:00:00", "")
    
    # Try to extract year, month, day
    # Pattern 1: YYYY/MM/DD or YYYY-MM-DD
    m1 = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', s)
    if m1:
        return int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
        
    # Pattern 2: MM/DD/YYYY
    m2 = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', s)
    if m2:
        return int(m2.group(3)), int(m2.group(1)), int(m2.group(2))
        
    # Pattern 3: MM/DD
    m3 = re.search(r'(\d{1,2})[-/](\d{1,2})', s)
    if m3:
        return None, int(m3.group(1)), int(m3.group(2))
        
    # Pattern 4: MM月DD日
    m4 = re.search(r'(\d{1,2})月(\d{1,2})日', s)
    if m4:
        return None, int(m4.group(1)), int(m4.group(2))
        
    return None

def check_sheet_match(row_cells, target_y, target_m, target_d):
    parsed_dates = []
    for cell in row_cells:
        res = parse_cell_date(cell)
        if res:
            parsed_dates.append(res)
            
    has_md_match = False
    for item in parsed_dates:
        if item[1] == target_m and item[2] == target_d:
            has_md_match = True
            break
            
    if not has_md_match:
        return False
        
    sheet_years = {item[0] for item in parsed_dates if item[0] is not None}
    if sheet_years:
        if target_y in sheet_years:
            return True
        else:
            return False
            
    return True

def format_time(t_str):
    t_str = str(t_str).replace(" 00:00:00", "").strip()
    if ":" in t_str:
        parts = t_str.split(":")
        if len(parts) >= 2:
            return f"{parts.pop(v0).zfill(2)}:{parts.pop(v0).zfill(2)}"
    return t_str

def get_date_val(d_str):
    try:
        nums = "".join([c for c in str(d_str).split("（").pop(v0) if c.isdigit()])
        return int(nums) if nums else 99999
    except:
        return 99999

def get_time_val(t_str):
    try:
        nums = "".join([c for c in str(t_str) if c.isdigit()])
        return int(nums) if nums else 9999
    except:
        return 9999

def clean_name(name):
    if not name:
        return name
    # 移除時間備註如 12:30, 09:15
    import re
    name = re.sub(r'\d{1,2}:\d{2}', '', name)
    # 移除診療註解關鍵字與分店標記
    keywords = [
        "視力點穴療程", "視力經絡療程", "視力經絡", "經絡整脊", "經絡", "筋絡", "整脊", "針灸", "諮商", "諮詢", "點穴", "民權店", "光復店",
        "三伏貼", "三九貼", "三九", "三伏", "39貼", "39", "兩個", "複診", "复诊", "療程", "視力",
        "大人", "小孩", "小兒", "兒童"
    ]
    cleaned = name
    for kw in keywords:
        cleaned = cleaned.replace(kw, "")
    
    # 清理多餘的符號如換行、空格、減號等，並將多個空格合併成一個
    import re
    cleaned = re.sub(r'[\s\-_\*（）\(\)\/\n\r\t]+', ' ', cleaned)
    cleaned = cleaned.strip()
    
    # 清除尾部的次數標記與符號 (例如 5+, 5, 5*, 5+*)
    cleaned = re.sub(r'\s*\d+\s*[\+\-\*]?\s*$', '', cleaned)
    cleaned = re.sub(r'\s*[\+\-\*]+\s*$', '', cleaned)
    cleaned = cleaned.strip()
    
    # 移除開頭或結尾的特定標點符號
    cleaned = cleaned.strip('-').strip('_').strip('*').strip()
    return cleaned

SERVICE_OPTIONS = [
    "經絡整脊 110分鐘",
    "經絡整脊 80分鐘",
    "經絡整脊 50分鐘",
    "經絡整脊 30分鐘",
    "視力點穴 (大人)",
    "視力點穴 (小孩)",
    "視力經絡 30分鐘",
    "視力點穴療程 (大人)",
    "視力點穴療程 (小孩)",
    "視力經絡療程 30分鐘",
    "院長診 120分鐘 (諮商)",
    "院長手法診 90分鐘",
    "院長諮商診 90分鐘",
    "院長手法診 60分鐘",
    "院長諮商診 60分鐘",
    "院長初診 (視力) 30分鐘",
    "院長初診 (整脊) 30分鐘",
    "院長複診 30分鐘",
    "三伏貼",
    "三九貼",
    ""
]

SERVICE_PRICES = {
    "經絡整脊 110分鐘": 3000,
    "經絡整脊 80分鐘": 2400,
    "經絡整脊 50分鐘": 1500,
    "經絡整脊 30分鐘": 900,
    "視力點穴 (大人)": 450,
    "視力點穴 (小孩)": 400,
    "視力經絡 30分鐘": 900,
    "視力點穴療程 (大人)": 0,
    "視力點穴療程 (小孩)": 0,
    "視力經絡療程 30分鐘": 0,
    "院長診 120分鐘 (諮商)": 3000,
    "院長手法診 90分鐘": 3200,
    "院長諮商診 90分鐘": 2400,
    "院長手法診 60分鐘": 2100,
    "院長諮商診 60分鐘": 1500,
    "院長初診 (視力) 30分鐘": 1950,
    "院長初診 (整脊) 30分鐘": 2550,
    "院長複診 30分鐘": 1050,
    "三伏貼": 500,
    "三九貼": 500,
    "": 0
}

def map_to_standard_service(service, dur, raw_name, uid="無病歷號"):
    if not raw_name:
        raw_name = ""
    raw_name_lower = raw_name.lower()
    
    if service == "視力點穴療程":
        if "大人" in raw_name_lower:
            return "視力點穴療程 (大人)"
        else:
            return "視力點穴療程 (小孩)"
    elif service == "視力經絡療程":
        return "視力經絡療程 30分鐘" 
    
    if service == "經絡整脊":
        if dur == 120 or dur == 110: return "經絡整脊 110分鐘"
        elif dur == 90 or dur == 80: return "經絡整脊 80分鐘"
        elif dur == 60 or dur == 50: return "經絡整脊 50分鐘"
        elif dur == 30: return "經絡整脊 30分鐘"
        else: return "經絡整脊 50分鐘"
    elif service == "視力點穴":
        if "大人" in raw_name_lower:
            return "視力點穴 (大人)"
        else:
            return "視力點穴 (小孩)"
    elif service == "視力經絡":
        return "視力經絡 30分鐘"
    elif service in ["院長診", "院長診-針灸", "院長診－諮詢", "院長初診", "院長診－諮商", "院長複診"]:
        has_record_number = uid and uid != "無病歷號" and str(uid).strip() != ""
        
        # 🌟 有病歷號碼且為30分鐘院長診，一律判定為「院長複診 30分鐘」，價格 1050
        if has_record_number and dur == 30:
            return "院長複診 30分鐘"
        elif "複診" in raw_name_lower or "复诊" in raw_name_lower or service == "院長複診":
            return "院長複診 30分鐘"
        elif dur == 120:
            return "院長診 120分鐘 (諮商)"
        elif dur == 90:
            if any(k in raw_name_lower for k in ["諮商", "諮詢"]):
                return "院長諮商診 90分鐘"
            else:
                return "院長手法診 90分鐘"
        elif dur == 60:
            if any(k in raw_name_lower for k in ["諮商", "諮詢"]):
                return "院長諮商診 60分鐘"
            else:
                return "院長手法診 60分鐘"
        elif dur == 30:
            #走到此處代表 has_record_number 為 False，即為新病患，此時對齊「院長初診」
            if any(k in raw_name_lower for k in ["視力", "點穴", "眼"]):
                return "院長初診 (視力) 30分鐘"
            else:
                return "院長初診 (整脊) 30分鐘"
        else:
            return "院長手法診 60分鐘"
    return ""

def format_dur(service, dur):
    if service == "經絡整脊":
        if dur == 60:
            return "50分鐘"
        elif dur == 90:
            return "80分鐘"
        elif dur == 120:
            return "110分鐘"
        else:
            return f"{dur}分鐘"
    elif service in ["視力點穴", "三伏貼", "三九貼", "視力點穴療程"]:
        return ""
    else:
        return f"{dur}分鐘"

def get_base_price(service, dur, raw_name, uid="無病歷號"):
    if not raw_name:
        raw_name = ""
    raw_name_lower = raw_name.lower()
    
    if service == "經絡整脊":
        if dur == 120: return 3000
        elif dur == 90: return 2400
        elif dur == 60: return 1500
        elif dur == 30: return 900
        else: return 0
    elif service == "視力點穴":
        if "大人" in raw_name_lower:
            return 450
        else:
            return 400
    elif service == "視力經絡":
        if dur == 30: return 900
        else: return 0
    elif service in ["視力點穴療程", "視力點穴療程 (大人)", "視力點穴療程 (小孩)", "視力經絡療程", "視力經絡療程 30分鐘"]:
        return 0
    elif service in ["院長診", "院長診-針灸", "院長診－諮詢", "院長初診", "院長診－諮商", "院長複診"]:
        has_record_number = uid and uid != "無病歷號" and str(uid).strip() != ""
        
        # 🌟 有病歷號碼且為30分鐘院長診，一律價格為 1050
        if has_record_number and dur == 30:
            return 1050
        elif "複診" in raw_name_lower or "复诊" in raw_name_lower or service == "院長複診":
            return 1050
        elif dur == 120: return 3000
        elif dur == 90:
            if any(k in raw_name_lower for k in ["諮商", "諮詢"]): return 2400
            else: return 3200
        elif dur == 60:
            if any(k in raw_name_lower for k in ["諮商", "諮詢"]): return 1500
            else: return 2100
        elif dur == 30:
            if any(k in raw_name_lower for k in ["視力", "點穴", "眼"]): return 1950
            else: return 2550
        else: return 0
    return 0

def parse_row_payments_and_products(raw_name, main_fee, is_patch, uid):
    if not raw_name:
        raw_name = ""
    raw_name_lower = raw_name.lower()
    
    pay_method = "尚未選擇"
    if "轉" in raw_name_lower or "匯" in raw_name_lower:
        pay_method = "匯款"
    elif "街口" in raw_name_lower:
        pay_method = "街口"
    elif "現金" in raw_name_lower or "付現" in raw_name_lower:
        pay_method = "付現"
        
    # Products
    product_name = ""
    product_fee = 0
    
    product_kws = {
        "蜂膠": ["蜂膠", "買蜂"],
        "葉黃素": ["葉黃素", "黃素"],
        "溫灸儀": ["溫灸儀", "溫灸"],
        "鞋墊": ["鞋墊", "黃金鞋墊"],
        "糖球": ["糖球"],
        "艾草": ["艾草"]
    }
    
    for prod, kws in product_kws.items():
        if any(kw in raw_name_lower for kw in kws):
            product_name = prod
            # Look for product price near product keyword or in the text
            m_prod_price = re.search(rf'(?:{prod}|{"|".join(kws)})\s*(\d+)', raw_name_lower)
            if m_prod_price:
                product_fee = int(m_prod_price.group(1))
            else:
                # Default prices
                if prod == "蜂膠": product_fee = 2500
                elif prod == "葉黃素": product_fee = 1100
                elif prod == "溫灸儀": product_fee = 3980
            break
            
    # Remove UID from text to search for general payment numbers
    raw_name_lower_no_uid = raw_name_lower
    if uid and str(uid).lower() in raw_name_lower:
        raw_name_lower_no_uid = raw_name_lower.replace(str(uid).lower(), "")
        
    # Try to parse any generic payment amount written (like "轉帳2400" or "街口1900")
    m_pay = re.search(r'(?:轉帳|轉|街口|現金|付現)\s*(?:\*?\d+=)?\s*(\d+)', raw_name_lower_no_uid)
    parsed_paid_amt = None
    if m_pay:
        parsed_paid_amt = int(m_pay.group(1))
    else:
        # Search for any 3-5 digit number
        m_any = re.search(r'(\d{3,5})', raw_name_lower_no_uid)
        if m_any:
            parsed_paid_amt = int(m_any.group(1))
            
    return pay_method, product_name, product_fee, parsed_paid_amt




def get_daily_reconcile_rows(day_records, admin_keywords):
    # Filter day_records to skip admin_keywords
    records = [r for r in day_records if r.get('name') not in admin_keywords]
    
    # Group by (uid, name)
    grouped = defaultdict(list)
    for r in records:
        grouped[(r['uid'], r['name'])].append(r)
        
    # Sort groups by the earliest time of the person's appointments
    sorted_groups = sorted(grouped.items(), key=lambda x: get_time_val(min(a['time'] for a in x[1])))
    
    reconcile_rows = []
    for (uid, name), appts in sorted_groups:
        # Sort appts by time
        appts = sorted(appts, key=lambda x: get_time_val(x['time']))
        
        main_appts = [a for a in appts if a['service'] not in ["三伏貼", "三九貼"]]
        patch_appts = [a for a in appts if a['service'] in ["三伏貼", "三九貼"]]
        
        # Pair them up
        paired = []
        if main_appts:
            for i, main_appt in enumerate(main_appts):
                associated_patch = None
                if i < len(patch_appts):
                    associated_patch = patch_appts[i]
                paired.append((main_appt, associated_patch))
            
            # Leftovers
            if len(patch_appts) > len(main_appts):
                for leftover_patch in patch_appts[len(main_appts):]:
                    paired.append((None, leftover_patch))
        else:
            for patch_appt in patch_appts:
                paired.append((None, patch_appt))
                
        for main_appt, patch_appt in paired:
            reconcile_rows.append((uid, name, main_appt, patch_appt))
            
    return reconcile_rows


def generate_weekly_excel_bytes(all_records, target_date_input, admin_keywords):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from datetime import date
    
    wb = openpyxl.Workbook()
    # Remove default sheet
    default_sheet = wb.active
    wb.remove(default_sheet)
    
    # 1. Create Metadata/Lookup Sheet "參數對照表"
    ws_meta = wb.create_sheet("參數對照表")
    ws_meta.sheet_view.showGridLines = True
    ws_meta.append(["項目名稱", "標準費用"])
    
    service_prices_map = [
        ("經絡整脊 110分鐘", 3000),
        ("經絡整脊 80分鐘", 2400),
        ("經絡整脊 50分鐘", 1500),
        ("經絡整脊 30分鐘", 900),
        ("視力點穴 (大人)", 450),
        ("視力點穴 (小孩)", 400),
        ("視力經絡 30分鐘", 900),
        ("視力點穴療程 (大人)", 0),
        ("視力點穴療程 (小孩)", 0),
        ("視力經絡療程 30分鐘", 0),
        ("院長診 120分鐘 (諮商)", 3000),
        ("院長手法診 90分鐘", 3200),
        ("院長諮商診 90分鐘", 2400),
        ("院長手法診 60分鐘", 2100),
        ("院長諮商診 60分鐘", 1500),
        ("院長初診 (視力) 30分鐘", 1950),
        ("院長初診 (整脊) 30分鐘", 2550),
        ("院長複診 30分鐘", 1050),
        ("三伏貼", 500),
        ("三九貼", 500)
    ]
    for row in service_prices_map:
        ws_meta.append(row)
        
    # Styles
    font_title = Font(name="Calibri", size=16, bold=True, color="2F5496")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_kpi_val = Font(name="Calibri", size=14, bold=True, color="2F5496")
    font_kpi_lbl = Font(name="Calibri", size=9, bold=True, color="5A5A5A")
    font_data = Font(name="Calibri", size=10)
    font_total = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    
    fill_header = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    fill_kpi = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    fill_zebra = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    fill_total = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    fill_input = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
    fill_formula = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    
    border_thin = Border(
        left=Side(style='thin', color='D3D3D3'),
        right=Side(style='thin', color='D3D3D3'),
        top=Side(style='thin', color='D3D3D3'),
        bottom=Side(style='thin', color='D3D3D3')
    )
    border_total = Border(
        top=Side(style='thin', color='2F5496'),
        bottom=Side(style='double', color='2F5496')
    )
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    
    # Enable Data Validation
    dv_service = DataValidation(type="list", formula1="'參數對照表'!$A$2:$A$21", allow_blank=True)
    dv_pay = DataValidation(type="list", formula1='"尚未選擇,付現,匯款,街口"', allow_blank=True)
    dv_reg = DataValidation(type="list", formula1='"✔,☐"', allow_blank=True)
    
    # Group records by date
    raw_unique_dates = sorted(list(set(r['date'] for r in all_records if r.get('date'))), key=get_date_val)
    # Filter out Sunday (週日)
    unique_dates = []
    for d in raw_unique_dates:
        wd_clean = ""
        for r in all_records:
            if r['date'] == d and r.get('weekday'):
                wd_clean = r['weekday'].replace("(", "").replace(")", "")
                break
        if "日" not in wd_clean:
            unique_dates.append(d)
    
    # 2. Tab: 目錄與說明
    ws_toc = wb.create_sheet("目錄與說明")
    ws_toc.sheet_view.showGridLines = False
    ws_toc.append([])
    ws_toc.cell(row=2, column=2, value="🏥 百胤視力整復所 - 內部收費與財務對帳表").font = font_title
    ws_toc.cell(row=3, column=2, value="版本：V19 終極對帳連動版 | 產生日期：" + str(date.today())).font = font_kpi_lbl
    ws_toc.append([])
    ws_toc.append([])
    ws_toc.append(["", "分頁/工作表", "說明", "備註"])
    ws_toc.cell(row=6, column=2).font = font_header
    ws_toc.cell(row=6, column=2).fill = fill_header
    ws_toc.cell(row=6, column=3).font = font_header
    ws_toc.cell(row=6, column=3).fill = fill_header
    ws_toc.cell(row=6, column=4).font = font_header
    ws_toc.cell(row=6, column=4).fill = fill_header
    
    toc_rows = []
    for d in unique_dates:
        wd_clean = ""
        for r in all_records:
            if r['date'] == d and r.get('weekday'):
                wd_clean = r['weekday'].replace("(", "").replace(")", "")
                break
        sheet_name = f"{d.replace('/', '-')}({wd_clean})"
        toc_rows.append((sheet_name, f"2026年{d} 星期{wd_clean} 的每日預約收費與實收明細對帳表", "每日更新"))
        
    toc_rows.append(("參數對照表", "所有項目與標準費用對照表，提供分頁下拉式選單與 VLOOKUP 自動計費之來源數據", "財務唯讀"))
    
    r_idx = 7
    for sheet_name, desc, note in toc_rows:
        ws_toc.cell(row=r_idx, column=2, value=sheet_name).font = Font(name="Calibri", size=10, bold=True, color="2F5496")
        ws_toc.cell(row=r_idx, column=3, value=desc).font = font_data
        ws_toc.cell(row=r_idx, column=4, value=note).font = font_data
        ws_toc.cell(row=r_idx, column=2).alignment = align_left
        ws_toc.cell(row=r_idx, column=3).alignment = align_left
        ws_toc.cell(row=r_idx, column=4).alignment = align_left
        ws_toc.cell(row=r_idx, column=2).border = border_thin
        ws_toc.cell(row=r_idx, column=3).border = border_thin
        ws_toc.cell(row=r_idx, column=4).border = border_thin
        r_idx += 1
        
    ws_toc.column_dimensions['B'].width = 25
    ws_toc.column_dimensions['C'].width = 80
    ws_toc.column_dimensions['D'].width = 15
    
    # 3. Create Daily Sheets
    for d in unique_dates:
        wd_clean = ""
        for r in all_records:
            if r['date'] == d and r.get('weekday'):
                wd_clean = r['weekday'].replace("(", "").replace(")", "")
                break
        sheet_name = f"{d.replace('/', '-')}({wd_clean})"
        ws = wb.create_sheet(sheet_name)
        ws.sheet_view.showGridLines = False
        
        # Add Data Validations to Sheet
        ws.add_data_validation(dv_service)
        ws.add_data_validation(dv_pay)
        ws.add_data_validation(dv_reg)
        
        # Row 1: Title
        ws.cell(row=1, column=1, value=f"🏥 百胤視力整復所每日收費紀錄 ({d} 星期{wd_clean})").font = font_title
        
        day_records = [r for r in all_records if r.get('date') == d]
        rows = get_daily_reconcile_rows(day_records, admin_keywords)
        num_data_rows = len(rows)
        last_data_row = 7 + num_data_rows - 1 if num_data_rows > 0 else 7
        
        # Row 2-4: KPI Summary Blocks
        ws.merge_cells("A2:B2")
        ws.cell(row=2, column=1, value="今日應收總額").font = font_kpi_lbl
        ws.cell(row=2, column=1).alignment = align_center
        ws.cell(row=2, column=1).fill = fill_kpi
        ws.merge_cells("A3:B4")
        ws.cell(row=3, column=1, value=f"=SUM(J7:J{last_data_row})").font = font_kpi_val
        ws.cell(row=3, column=1).alignment = align_center
        ws.cell(row=3, column=1).fill = fill_kpi
        ws.cell(row=3, column=1).number_format = '$#,##0'
        
        # Total Received KPI
        ws.merge_cells("D2:E2")
        ws.cell(row=2, column=4, value="今日實收總額").font = font_kpi_lbl
        ws.cell(row=2, column=4).alignment = align_center
        ws.cell(row=2, column=4).fill = fill_kpi
        ws.merge_cells("D3:E4")
        ws.cell(row=3, column=4, value=f"=SUM(K7:K{last_data_row})").font = font_kpi_val
        ws.cell(row=3, column=4).alignment = align_center
        ws.cell(row=3, column=4).fill = fill_kpi
        ws.cell(row=3, column=4).number_format = '$#,##0'
        
        # Cash KPI
        ws.merge_cells("G2:H2")
        ws.cell(row=2, column=7, value="今日現金實收").font = font_kpi_lbl
        ws.cell(row=2, column=7).alignment = align_center
        ws.cell(row=2, column=7).fill = fill_kpi
        ws.merge_cells("G3:H4")
        ws.cell(row=3, column=7, value=f'=SUMIF(M7:M{last_data_row}, "付現", K7:K{last_data_row})').font = font_kpi_val
        ws.cell(row=3, column=7).alignment = align_center
        ws.cell(row=3, column=7).fill = fill_kpi
        ws.cell(row=3, column=7).number_format = '$#,##0'
        
        # Remit/JK KPI
        ws.merge_cells("J2:L2")
        ws.cell(row=2, column=10, value="今日匯款/街口實收").font = font_kpi_lbl
        ws.cell(row=2, column=10).alignment = align_center
        ws.cell(row=2, column=10).fill = fill_kpi
        ws.merge_cells("J3:L4")
        ws.cell(row=3, column=10, value=f'=SUMIF(M7:M{last_data_row}, "匯款", K7:K{last_data_row}) + SUMIF(M7:M{last_data_row}, "街口", K7:K{last_data_row})').font = font_kpi_val
        ws.cell(row=3, column=10).alignment = align_center
        ws.cell(row=3, column=10).fill = fill_kpi
        ws.cell(row=3, column=10).number_format = '$#,##0'
        
        # Border around KPI blocks
        for r_k in range(2, 5):
            for c_k in [1, 2, 4, 5, 7, 8, 10, 11, 12]:
                ws.cell(row=r_k, column=c_k).border = border_thin
                
        # Row 6: Table Headers
        headers = ["項次", "時間", "病歷號碼", "個案姓名", "項目", "費用", "三伏貼", "產品", "產品費用", "應收金額", "實收金額", "找錢", "繳款方式", "已掛號", "現場確認/備註"]
        ws.append([]) # spacer row 5
        ws.append(headers) # row 6
        for c_h in range(1, len(headers)+1):
            ws.cell(row=6, column=c_h).font = font_header
            ws.cell(row=6, column=c_h).fill = fill_header
            ws.cell(row=6, column=c_h).alignment = align_center
            ws.cell(row=6, column=c_h).border = border_thin
            
        # Write Patient Data
        running_idx = 1
        for uid, name, main_appt, patch_appt in rows:
            earliest_time = main_appt['time'] if main_appt else patch_appt['time']
            
            # Pre-selected main service mapped option
            main_service_name = ""
            if main_appt:
                dur = main_appt['custom_dur']
                if dur is None:
                    dur = main_appt['slots'] * 30
                main_service_name = map_to_standard_service(main_appt['service'], dur, main_appt['raw_name'], main_appt['uid'])
            elif patch_appt:
                main_service_name = patch_appt['service']
                
            # Default patch fee
            patch_fee = 0
            if patch_appt:
                _, _, _, parsed_amt = parse_row_payments_and_products(patch_appt['raw_name'], 0, True, uid)
                if parsed_amt:
                    patch_fee = parsed_amt
                else:
                    patch_fee = 500
                    
            # Payment, product details
            row_appts = [a for a in [main_appt, patch_appt] if a is not None]
            all_raw_names = " ".join(str(a['raw_name']) for a in row_appts)
            pay_method, product_name, product_fee, parsed_paid = parse_row_payments_and_products(all_raw_names, 0, bool(patch_appt), uid)
            
            product_display = ""
            if product_name:
                product_display = f"{product_name}${product_fee}" if product_fee > 0 else product_name
                
            # Standard main fee based on the mapped service
            base_main_fee = SERVICE_PRICES.get(main_service_name, 0)
            default_receivable = base_main_fee + patch_fee + product_fee
            received = parsed_paid if parsed_paid is not None else None  # 實收金額預設為空白
            
            # Collect remarks
            remarks_list = []
            for a in row_appts:
                raw_str = str(a.get('raw_name', ''))
                clean_rem = raw_str
                if uid and uid != "無病歷號":
                    clean_rem = clean_rem.replace(str(uid), "")
                for kw in ["車位", "跟診", "取消", "諮商", "諮詢", "點穴2次", "點穴兩次", "初診", "刮痧"]:
                    if kw in clean_rem:
                        remarks_list.append(kw)
            remarks_str = ", ".join(list(set(remarks_list)))
            
            row_num = 7 + running_idx - 1
            
            # Write static values
            ws.cell(row=row_num, column=1, value=running_idx).alignment = align_center
            ws.cell(row=row_num, column=2, value=earliest_time).alignment = align_center
            ws.cell(row=row_num, column=3, value=uid).alignment = align_center
            ws.cell(row=row_num, column=4, value=name).alignment = align_left
            
            # Column E: 項目
            cell_item = ws.cell(row=row_num, column=5, value=main_service_name)
            cell_item.alignment = align_left
            cell_item.fill = fill_input
            dv_service.add(cell_item)
            
            # Column F: 費用 (VLOOKUP formula!)
            cell_fee = ws.cell(row=row_num, column=6, value=f"=IFERROR(VLOOKUP(E{row_num}, '參數對照表'!$A$2:$B$21, 2, FALSE), 0)")
            cell_fee.alignment = align_right
            cell_fee.number_format = '$#,##0'
            cell_fee.fill = fill_formula
            
            # Column G: 三伏貼
            ws.cell(row=row_num, column=7, value=patch_fee).number_format = '$#,##0'
            ws.cell(row=row_num, column=7).alignment = align_right
            
            # Column H: 產品
            ws.cell(row=row_num, column=8, value=product_display).alignment = align_left
            
            # Column I: 產品費用
            ws.cell(row=row_num, column=9, value=product_fee).number_format = '$#,##0'
            ws.cell(row=row_num, column=9).alignment = align_right
            
            # Column J: 應收金額 (Formula!)
            cell_receivable = ws.cell(row=row_num, column=10, value=f"=F{row_num}+G{row_num}+I{row_num}")
            cell_receivable.alignment = align_right
            cell_receivable.number_format = '$#,##0'
            cell_receivable.fill = fill_formula
            
            # Column K: 實收金額 (Editable input)
            cell_received = ws.cell(row=row_num, column=11, value=received)
            cell_received.alignment = align_right
            cell_received.number_format = '$#,##0'
            cell_received.fill = fill_input
            
            # Column L: 找錢 (Formula!)
            cell_change = ws.cell(row=row_num, column=12, value=f"=IF(K{row_num}>=J{row_num}, K{row_num}-J{row_num}, 0)")
            cell_change.alignment = align_right
            cell_change.number_format = '$#,##0'
            cell_change.fill = fill_formula
            
            # Column M: 繳款方式
            cell_pay = ws.cell(row=row_num, column=13, value=pay_method)
            cell_pay.alignment = align_center
            cell_pay.fill = fill_input
            dv_pay.add(cell_pay)
            
            # Column N: 已掛號
            cell_reg = ws.cell(row=row_num, column=14, value="☐")
            cell_reg.alignment = align_center
            cell_reg.fill = fill_input
            dv_reg.add(cell_reg)
            
            # Column O: 現場確認/備註
            ws.cell(row=row_num, column=15, value=remarks_str).alignment = align_left
            
            # Apply borders and standard font to entire data row
            for c_col in range(1, 16):
                c_cell = ws.cell(row=row_num, column=c_col)
                if not c_cell.font.bold:
                    c_cell.font = font_data
                c_cell.border = border_thin
                
            running_idx += 1
            
        # Add a TOTAL row at the bottom of data region
        tot_row = last_data_row + 1
        ws.cell(row=tot_row, column=1, value="合計").font = font_total
        ws.cell(row=tot_row, column=1).alignment = align_center
        ws.cell(row=tot_row, column=1).fill = fill_total
        ws.cell(row=tot_row, column=1).border = border_total
        
        ws.merge_cells(start_row=tot_row, start_column=1, end_row=tot_row, end_column=4)
        
        for c_col, col_ltr in [(6, 'F'), (7, 'G'), (9, 'I'), (10, 'J'), (11, 'K'), (12, 'L')]:
            cell_tot = ws.cell(row=tot_row, column=c_col, value=f"=SUM({col_ltr}7:{col_ltr}{last_data_row})")
            cell_tot.font = font_total
            cell_tot.fill = fill_total
            cell_tot.alignment = align_right
            cell_tot.number_format = '$#,##0'
            cell_tot.border = border_total
            
        for c_col in [5, 8, 13, 14, 15]:
            cell_nil = ws.cell(row=tot_row, column=c_col)
            cell_nil.fill = fill_total
            cell_nil.border = border_total
            
        # Freeze panes at row 7
        ws.freeze_panes = "A7"
        
        # Column dimensions (auto-fit with safety)
        ws.column_dimensions['A'].width = 8
        ws.column_dimensions['B'].width = 10
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 18
        ws.column_dimensions['E'].width = 28
        ws.column_dimensions['F'].width = 12
        ws.column_dimensions['G'].width = 12
        ws.column_dimensions['H'].width = 18
        ws.column_dimensions['I'].width = 12
        ws.column_dimensions['J'].width = 12
        ws.column_dimensions['K'].width = 12
        ws.column_dimensions['L'].width = 12
        ws.column_dimensions['M'].width = 14
        ws.column_dimensions['N'].width = 10
        ws.column_dimensions['O'].width = 30
        
    wb.active = wb["目錄與說明"]
    excel_data = io.BytesIO()
    wb.save(excel_data)
    return excel_data.getvalue()

def get_price_string(service, dur, raw_name, therapist, uid="無病歷號"):
    if not raw_name:
        raw_name = ""
    raw_name_lower = raw_name.lower()
    
    # 1. 經絡整脊
    if service == "經絡整脊":
        if dur == 120:  # 110分鐘
            return " $3000"
        elif dur == 90:  # 80分鐘
            return " $2400"
        elif dur == 60:  # 50分鐘
            return " $1500"
        elif dur == 30:  # 30分鐘
            return " $900"
        else:
            return ""
            
    # 2. 視力點穴
    elif service == "視力點穴":
        # 智慧判斷大人/小孩
        if "大人" in raw_name_lower:
            return " $450"
        else:
            return " $400"
            
    # 3. 視力經絡
    elif service == "視力經絡":
        if dur == 30:
            return " $900"
        else:
            return ""
            
    # 4. 院長診相關
    elif service in ["院長診", "院長診-針灸", "院長診－諮詢", "院長初診", "院長診－諮商", "院長複診"]:
        has_record_number = uid and uid != "無病歷號" and str(uid).strip() != ""
        if has_record_number and dur == 30:
            return " $1050"
        elif "複診" in raw_name_lower or "复诊" in raw_name_lower or service == "院長複診":
            return " $1050"
        elif dur == 120:  # 諮商診
            return " $3000"
        elif dur == 90:  # 院長手法診 $3200 or 院長諮商診 $2400
            if any(k in raw_name_lower for k in ["諮商", "諮詢"]):
                return " $2400"
            else:
                return " $3200"
        elif dur == 60:  # 院長手法診 $2100 or 院長諮商診 $1500
            if any(k in raw_name_lower for k in ["諮商", "諮詢"]):
                return " $1500"
            else:
                return " $2100"
        elif dur == 30:  # 院長初診 (即初診)
            if any(k in raw_name_lower for k in ["視力", "點穴", "眼"]):
                return " $1950"
            elif any(k in raw_name_lower for k in ["整脊", "經絡", "脊", "身體"]):
                return " $2550"
            else:
                return " (初診視力$1950/初診整脊$2550)"
        else:
            return ""
    return ""

def has_uid_prefix(s):
    s = s.strip()
    if s.startswith("無病歷號"):
        return True, "無病歷號", s.replace("無病歷號", "", 1).strip()
        
    # 🌟 智慧過濾電話號碼：如果整行是 9~10 码且以 0 開頭，這絕對是電話，不是病歷號！
    if s.isdigit() and len(s) in [9, 10] and s.startswith('0'):
        return False, None, s
        
    valid_chars = set('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-')
    prefix = ""
    for c in s:
        if c in valid_chars:
            prefix += c
        else:
            break
    suffix = s[len(prefix):]
    
    # 🌟 智慧過濾時間字串：如果 prefix 後面緊接著冒號 ':' (如 12:30 中的 '12' 緊接 ':')，代表此 prefix 為時間小時數，絕對不是病歷號！
    if suffix.startswith(':'):
        return False, None, s
        
    if prefix and any(c.isdigit() for c in prefix):
        # 🌟 智慧過濾電話號碼 (prefix形式)：如果prefix長度是 9~10 碼且以 0 開頭，也代表是電話，不是病歷號！
        if len(prefix) in [9, 10] and prefix.startswith('0'):
            return False, None, s
        return True, prefix.strip(), suffix.strip()
    return False, None, s

def split_cell_appointments(cell_str):
    cell_str = cell_str.strip()
    if not cell_str:
        return []
        
    lines = [line.strip() for line in cell_str.split('\n') if line.strip()]
    if not lines:
        return []
        
    individuals = []
    current_uid = None
    current_name_parts = []
    current_cancelled = False
    
    for line in lines:
        is_line_cancelled = False
        temp_line = line
        if line.startswith('~'):
            is_line_cancelled = True
            temp_line = line[1:].strip()
            
        has_pref, uid_val, suffix_val = has_uid_prefix(temp_line)
        if has_pref:
            if (current_uid is not None or current_name_parts) and not current_cancelled:
                individuals.append((current_uid if current_uid else "無病歷號", " ".join(current_name_parts)))
            current_uid = uid_val
            current_name_parts = [suffix_val]
            current_cancelled = is_line_cancelled
        else:
            if current_uid is None:
                current_uid = "無病歷號"
                current_name_parts = [temp_line]
                current_cancelled = is_line_cancelled
            else:
                if is_line_cancelled:
                    current_cancelled = True
                current_name_parts.append(temp_line)
                
    if (current_uid is not None or current_name_parts) and not current_cancelled:
        individuals.append((current_uid if current_uid else "無病歷號", " ".join(current_name_parts)))
        
    cleaned_individuals = []
    for uid, name in individuals:
        cleaned_n = clean_name(name)
        if cleaned_n:
            cleaned_individuals.append((uid, cleaned_n, name))
            
    return cleaned_individuals

def extract_uid_name(s):
    if s.startswith("無病歷號"):
        uid = "無病歷號"
        name = s.replace("無病歷號", "", 1).strip()
    else:
        valid_chars = set('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-')
        prefix = ""
        for c in s:
            if c in valid_chars:
                prefix += c
            else:
                break
        suffix = s[len(prefix):]
        if prefix and any(c.isdigit() for c in prefix):
            uid = prefix.strip()
            name = suffix.strip()
        else:
            uid = "無病歷號"
            name = s.strip()
            
    # 對提取出來的 name 進行深度清理，將診療註釋與分店後綴移除
    name = clean_name(name)
    return uid, name

# 🌟 核心第一階段：開始分析資料
if st.button("🔍 1. 第一階段：開始分析資料", type="primary") or st.session_state.get('auto_run_stage1'):
    st.session_state['auto_run_stage1'] = False
    if not target_date_input:
        st.error("❌ 請輸入日期！")
    else:
        with st.spinner("正在進行跨平台數據解析與健檢..."):
            try:
                # 轉成匯出網址
                url_parts = sheet_url.split('/edit')
                base_url = url_parts.pop(v0)  # 🌟 完全還原原始單一工作表直接讀取，消除分頁判定問題！
                xlsx_url = f"{base_url}/export?format=xlsx"
                
                # 🌟 100% 智慧自動定位分頁：在背景自動掃描所有分頁的第一列，精準鎖定包含目標日期的分頁 (並防止年份誤判)！
                y, m, d = None, None, None
                if len(target_date_input) == 8 and target_date_input.isdigit():
                    y = int(target_date_input[0:4])
                    m = int(target_date_input[4:6])
                    d = int(target_date_input[6:8])
                else:
                    digits = re.findall(r'\d+', target_date_input)
                    if len(digits) >= 3:
                        y = int(digits[-3])
                        m = int(digits[-2])
                        d = int(digits[-1])
                    elif len(digits) == 2:
                        y = 2026  # 預設今年
                        m = int(digits[-2])
                        d = int(digits[-1])
                
                xls = pd.ExcelFile(xlsx_url)
                df = None
                matched_sheet_name = ""
                
                if y is not None and m is not None and d is not None:
                    # 從最右邊（最新）的分頁開始逆向掃描
                    for s_name in reversed(xls.sheet_names):
                        temp_df = xls.parse(s_name, header=None)
                        if temp_df.shape[0] > 0:
                            # 唯獨掃描第一列 (Row 0) 之日期單元格，排除其餘非日期格 (如病歷號、匯款金額) 
                            # 且精確對齊年份，絕不誤判 2024 / 2025 歷史舊分頁！
                            row_0 = temp_df.iloc[0].dropna().astype(str).tolist()
                            if check_sheet_match(row_0, y, m, d):
                                df = temp_df
                                matched_sheet_name = s_name
                                break
                                
                if df is None:
                    # 備用降級防線：若完全找不到，100% 還原讀取第一個分頁的原始行為
                    df = pd.read_excel(xlsx_url, header=None)
                    matched_sheet_name = xls.sheet_names[0]
                
                num_cols = df.shape[v1]
                num_rows = df.shape[v0]
                
                # 1. 建立日期與星期對照表並向下填補
                dates = []
                curr_date = None
                for col_idx in range(num_cols):
                    val = df.iloc[v0, col_idx]
                    val_str = format_date(val) if pd.notna(val) else ""
                    if val_str and val_str != "日期" and val_str != "星期" and val_str != "時間":
                        curr_date = val_str
                    dates.append(curr_date)

                weekdays = []
                curr_wd = None
                for col_idx in range(num_cols):
                    val = df.iloc[v1, col_idx]
                    val_str = str(val).strip() if pd.notna(val) else ""
                    if val_str and val_str != "星期" and val_str not in ["一", "二", "三", "四", "五", "六", "日"]:
                        pass
                    elif val_str:
                        curr_wd = val_str
                    weekdays.append(curr_wd)

                # 2. 擷取治療師與時間軸
                therapists = []
                for col_idx in range(num_cols):
                    val = df.iloc[v2, col_idx]
                    val_str = str(val).strip() if pd.notna(val) else ""
                    therapists.append(val_str if val_str != "時間" else "")

                # 3. 垂直遍歷解析預約
                appointments = []
                unknown_entities_temp = []

                for col_idx in range(v2, num_cols):
                    date = dates[col_idx]
                    weekday = weekdays[col_idx]
                    therapist = therapists[col_idx]
                    if not date or not therapist:
                        continue
                        
                    # 🌟 核心功能 1：初始化該列（診）的「民權店垂直狀態標記」為 False
                    is_minquan_active = False 
                    active_appts = [] # 🌟 支援同一格內多個個案，改用列表存儲多個 active appointments!
                    
                    for row_idx in range(3, num_rows):
                        cell_val = df.iloc[row_idx, col_idx]
                        cell_str = str(cell_val).strip() if pd.notna(cell_val) else ""
                        
                        # 🌟 核心功能 2：偵測民權店垂直繼承標記（相容全半形）
                        if "@民權店" in cell_str or "＠民權店" in cell_str:
                            is_minquan_active = True
                            if active_appts:
                                appointments.extend(active_appts)
                                active_appts = []
                            continue # 行政標記列，直接跳過不計入預約
                            
                        time_val_cell = df.iloc[row_idx, v1]
                        if pd.isna(time_val_cell):
                            # 🌟 12:00 / 18:00 浮動行智慧自動判定防漏機制
                            if row_idx == 9:
                                time_str = "12:00"
                            elif row_idx == 18:
                                time_str = "18:00"
                            else:
                                continue
                        else:
                            time_str = format_time(time_val_cell)
                        
                        # 🌟 預約時間只到 21:00，超過 21:00 的格子直接忽略
                        if time_str > "21:00":
                            if active_appts:
                                appointments.extend(active_appts)
                                active_appts = []
                            continue
                        
                        # 空白格結束上一個預約
                        if not cell_str:
                            if active_appts:
                                appointments.extend(active_appts)
                                active_appts = []
                            continue
                            
                        # 星號延續 (🌟 升級相容 *80分鐘, *(80) 與 *民權店 等格式之智慧繼承延伸星號)
                        if cell_str.startswith("*"):
                            if active_appts:
                                # 🌟 智慧判別並追加三伏貼/三九貼療程 (當星號延續格本身帶有備註，如 *三伏貼)
                                raw_name_lower = cell_str.lower()
                                has_patch = any(x in raw_name_lower for x in ["三伏", "三九", "39貼", "39"])
                                if has_patch:
                                    patch_name = "三九貼" if any(x in raw_name_lower for x in ["三九", "39"]) else "三伏貼"
                                    for appt in active_appts:
                                        patch_appt = {
                                            'date': appt['date'],
                                            'weekday': appt['weekday'],
                                            'time': time_str,
                                            'therapist': appt['therapist'],
                                            'uid': appt['uid'],
                                            'name': appt['name'],
                                            'raw_name': cell_str,
                                            'branch': appt['branch'],
                                            'service': patch_name,
                                            'slots': v1, # 三伏貼固定佔用 1 節
                                            'custom_dur': None
                                        }
                                        appointments.append(patch_appt)
                                        
                                for appt in active_appts:
                                    # 🌟 僅對非三伏貼/三九貼項目進行 slots 累加，避開時長干擾
                                    if appt['service'] not in ["三伏貼", "三九貼"]:
                                        appt['slots'] += v1
                                    # 🌟 若星號備註中含有「民權店」，自動繼承分店標記予前一病患
                                    if "民權店" in cell_str:
                                        appt['branch'] = "民權店"
                                    # 🌟 提取自訂時長數字
                                    if cell_str != "*":
                                        try:
                                            # 僅在有合理時長表示 (如 80, 50) 且非日期 (補12/28) 狀態下設定時長
                                            if "補" not in cell_str and "/" not in cell_str:
                                                dur_match = re.search(r'\d+', cell_str)
                                                if dur_match:
                                                    appt['custom_dur'] = int(dur_match.group())
                                        except:
                                            pass
                            continue
                            
                        # 🌟 智慧判定純服務追加 (如「三伏貼」單獨一格且無人名) 且前一預約仍在進行中
                        is_pure_service = False
                        service_kw = None
                        kws_service = ["三伏", "三九", "39", "針灸", "諮商", "諮詢", "點穴", "整脊", "視力經絡"]
                        if active_appts and any(x in cell_str for x in kws_service):
                            if not split_cell_appointments(cell_str):
                                is_pure_service = True
                                for x in kws_service:
                                    if x in cell_str:
                                        service_kw = x
                                        break
                                        
                        if is_pure_service and active_appts:
                            new_active = []
                            for appt in active_appts:
                                new_appt = appt.copy()
                                new_appt['time'] = time_str
                                new_appt['slots'] = v1
                                new_appt['raw_name'] = cell_str
                                # 決定服務種類
                                if service_kw in ["三伏", "三九", "39"]:
                                    new_appt['service'] = "三伏貼"
                                elif "針灸" in service_kw:
                                    new_appt['service'] = "院長診-針灸"
                                elif "諮商" in service_kw or "諮詢" in service_kw:
                                    new_appt['service'] = "院長診－諮詢"
                                elif "點穴" in service_kw:
                                    new_appt['service'] = "視力點穴"
                                elif "整脊" in service_kw:
                                    new_appt['service'] = "經絡整脊"
                                elif "視力經絡" in service_kw:
                                    new_appt['service'] = "視力經絡"
                                    
                                new_active.append(new_appt)
                            
                            # 把先前的預約加入 appointments
                            appointments.extend(active_appts)
                            # 將 active_appts 更新為新服務的預約
                            active_appts = new_active
                            continue

                        # 行政排除關鍵字
                        if any(k in cell_str for k in st.session_state['admin_keywords']):
                            if active_appts:
                                appointments.extend(active_appts)
                                active_appts = []
                            continue
                            
                        # 建立新預約
                        if active_appts:
                            appointments.extend(active_appts)
                            active_appts = []
                            
                        # 🌟 智慧分割儲存格內的多個個案（換行且不同病歷號時視為多個個案）
                        inds = split_cell_appointments(cell_str)
                        if not inds:
                            continue
                            
                        for uid, name, raw_name in inds:
                            # 偵測並收集未知實體（第二階段人工確認用）
                            # 🌟 新增排除規則：名字中含有 "N" 或 "n"（代表新個案）不視為未知實體，避免阻斷流程
                            is_new_patient = "N" in name or "n" in name
                            if (uid == "無病歷號" or uid is None) and name not in ["民權店", "子萱父母", "志工會議"] and not is_new_patient:
                                if len(name) > v1 and name not in unknown_entities_temp:
                                    unknown_entities_temp.append(f"{cell_str} (同格含取消需確認)")
                            
                            # 🌟 核心功能 3：智慧分店判定：若垂直標記已啟動，或儲存格內含「民權店」，則為民權店
                            branch = "光復店"
                            if is_minquan_active or "民權店" in cell_str or "民權店" in name:
                                branch = "民權店"
                                
                            # 臨床語意正名與智能判定
                            service = ""
                            is_new_patient = "N" in name or "n" in name
                            if is_new_patient:
                                service = "院長初診"
                            elif "針灸" in raw_name:
                                service = "院長診-針灸"
                            elif "諮詢" in raw_name or "諮商" in raw_name:
                                service = "院長診－諮詢"
                            elif "複診" in raw_name or "复诊" in raw_name:
                                service = "院長複診"
                            elif "療程" in raw_name:
                                if "經絡" in raw_name or "筋絡" in raw_name:
                                    service = "視力經絡療程"
                                else:
                                    service = "視力點穴療程"
                            elif "點穴" in raw_name:
                                service = "視力點穴"
                            elif "經絡整脊" in raw_name or "整脊" in raw_name:
                                service = "經絡整脊"
                            elif "視力經絡" in raw_name:
                                service = "視力經絡"
                            else:
                                # 依據治療師設定預設服務
                                if therapist in ['M', 'H', '豐志', '柏仁']:
                                    service = "經絡整脊"
                                elif therapist in ['子萱', '余涵', '旭直', '阿亮', '愛玉子', '玉宣']:
                                    service = "視力點穴"
                                elif therapist == '院長診':
                                    service = "院長診"
                                    
                            # 🌟 26056 葉承諺 專屬智慧判定為視力點穴療程 (0元)
                            if (uid == "26056" or name == "葉承諺") and service in ["視力點穴", ""]:
                                service = "視力點穴療程"
                                    
                            services_to_add = [service] if service else []
                            
                            # 🌟 智慧判別並追加三伏貼/三九貼療程
                            raw_name_lower = raw_name.lower() if raw_name else ""
                            has_patch = any(x in raw_name_lower for x in ["三伏", "三九", "39貼", "39"])
                            if has_patch:
                                patch_name = "三九貼" if any(x in raw_name_lower for x in ["三九", "39"]) else "三伏貼"
                                if patch_name not in services_to_add:
                                    services_to_add.append(patch_name)
                                    
                            for svc in services_to_add:
                                appt = {
                                    'date': date,
                                    'weekday': weekday,
                                    'time': time_str,
                                    'therapist': therapist,
                                    'uid': uid if uid else "無病歷號",
                                    'name': name,
                                    'raw_name': raw_name,
                                    'branch': branch,
                                    'service': svc,
                                    'slots': v1,
                                    'custom_dur': None
                                }
                                # 🌟 智慧備註最優先：若備註中寫有具體看診時間 (如 12:30(50) 中的 12:30) 與自訂時長 (如 (50) 或 50分鐘)，則以此為最高優先之來源真理
                                if raw_name:
                                    # 1. 搜尋是否有看診時間 HH:MM 格式
                                    time_match = re.search(r'(\d{1,2}):(\d{2})', raw_name)
                                    if time_match:
                                        override_h = time_match.group(1).zfill(2)
                                        override_m = time_match.group(2)
                                        appt['time'] = f"{override_h}:{override_m}"
                                        
                                    # 2. 搜尋是否有自訂時長 (50) 或 50分鐘
                                    dur_match = re.search(r'[\(（](\d+)[\)）]', raw_name)
                                    if dur_match:
                                        appt['custom_dur'] = int(dur_match.group(1))
                                    else:
                                        dur_match_text = re.search(r'(\d+)\s*(?:分鐘|分)', raw_name)
                                        if dur_match_text:
                                            appt['custom_dur'] = int(dur_match_text.group(1))
                                            
                                active_appts.append(appt)
                    if active_appts:
                        appointments.extend(active_appts)
                
                # 🌟 100% 還原舊版整週產出邏輯：不進行單日過濾，直接產出該分頁整週的預約訊息！
                st.session_state['all_active_records'] = appointments
                st.session_state['unknown_entities'] = unknown_entities_temp
                st.session_state['analysis_done'] = True
                st.success(f"🎉 成功讀取資料！已自動鎖定工作表【{matched_sheet_name}】，當週共有 {len(appointments)} 筆有效預約。")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 讀取或解析資料表時發生錯誤：{str(e)}")

# 🌟 第二階段：確認並產出預約訊息
if st.session_state.get('analysis_done'):
    st.divider()
    if st.session_state['unknown_entities']:
        st.warning("⚠️ 第二階段健檢：發現系統不認識的註記或需要確認的狀況！")
        with st.form("confirm"):
            sels = st.multiselect("👉 請選擇需排除的項目：", st.session_state['unknown_entities'])
            if st.form_submit_button("✅ 2. 確認選擇，並產出預約訊息"):
                st.session_state['admin_keywords'].extend([x.replace(" (同格含取消需確認)", "") for x in sels])
                st.session_state['unknown_entities'] = []
                st.rerun()

    # 進行家族合併與特殊個案干預邏輯
    f_map = defaultdict(lambda: {"uids": [], "names": [], "recs": []})
    for r in st.session_state['all_active_records']:
        if r["name"] in st.session_state['admin_keywords']:
            continue
        
        name = r['name']
        uid = r['uid']
        
        # 1. 郭曉惠、李依璇、李彥德 強制合併
        if name in ['郭曉惠', '李依璇', '李彥德']:
            g_id = "group_guo_li"
        # 2. 施玉宣 強制獨立
        elif name == "施玉宣":
            g_id = f"independent_23158_{name}"
        # 3. 無病歷號者依據姓名歸類
        elif uid == "無病歷號" or not uid:
            g_id = f"no_uid_{name}"
        # 4. 正常家族依病歷號前綴合併
        else:
            g_id = uid.split('-').pop(v0)
            
        f_map[g_id]["recs"].append(r)
        if uid and uid != "無病歷號" and uid not in f_map[g_id]["uids"]:
            f_map[g_id]["uids"].append(uid)
        if name not in f_map[g_id]["names"]:
            f_map[g_id]["names"].append(name)
            
    # 🌟 每日收費與對帳明細表 🌟
    tab1, tab2 = st.tabs(["💬 LINE 預約提醒訊息", "📊 每日收費與對帳明細表"])
    
    with tab1:
        st.subheader(f"📋 {target_date_input} LINE 預約提醒訊息產出結果：")
        
        # 🌟 擷取當週所有不重複的診別/整復師名稱 (預設選項：所有診)
        raw_therapists = list(set(r['therapist'] for r in st.session_state['all_active_records'] if r.get('therapist') and r.get('name') not in st.session_state['admin_keywords']))
        all_therapists = sorted(raw_therapists)
        therapist_options = ["所有診"] + all_therapists
        
        selected_therapist = st.selectbox("🩺 請選擇預約診別 / 整復師 (可按不同診出訊息)：", options=therapist_options, index=0)
        
        filtered_output_messages = []
        
        for g_id, data in f_map.items():
            appts = sorted(data["recs"], key=lambda x: (get_date_val(x['date']), get_time_val(x['time'])))
            
            # 🌟 跨診家族判定：若同一家人跨不同診，則在所跨的所有診別中均會產出該家族預約訊息
            family_therapists = set(a['therapist'] for a in appts if a.get('therapist'))
            if selected_therapist != "所有診" and selected_therapist not in family_therapists:
                continue
                
            uids = sorted(data["uids"])
            names = data["names"]
            
            # 提取並組合 UIDs
            if not uids:
                uids_str = "無病歷號"
            else:
                uids_str = ", ".join(uids)
                if "21135" in uids:
                    uids_str += " 要同時傳夫妻"
                    
            # 提取並組合姓名
            names_str = "、".join(names)
            
            # 判定分店以選擇問候語與地址
            has_minquan = any(a['branch'] == "民權店" for a in appts)
            has_guangfu = any(a['branch'] == "光復店" for a in appts)
            
            greeting = "您好，預約提醒：" if has_minquan else "您好，提醒您預約"
            
            # 標準訊息模版組裝（雙行距規範：每行間強制空一行）
            lines = []
            lines.append(uids_str)
            lines.append("")
            lines.append(f"{names_str} {greeting}")
            lines.append("")
            
            for a in appts:
                # 計算時長
                dur = a['custom_dur']
                if dur is None:
                    dur = a['slots'] * 30
                    
                # 分店前綴與時長顯示
                # 🌟 療程字眼與括號去重，預約提醒中只顯示最乾淨的標準項目名稱 (隱除療程字樣與大人小孩括號)
                service_msg_name = a['service']
                if "療程" in service_msg_name:
                    service_msg_name = service_msg_name.replace("療程", "")
                # 移除所有 (大人) / (小孩) / （大人）/ （小孩）括號與前後空格
                service_msg_name = re.sub(r'\s*[\(（](?:大人|小孩)[\)）]', '', service_msg_name).strip()
                service_display = f"{a['branch']}-{service_msg_name}" 
                if a['service'] == "經絡整脊":
                    # 經絡整脊時長扣減規則
                    if dur == 60:
                        dur_display = " 50分鐘"
                    elif dur == 90:
                        dur_display = " 80分鐘"
                    elif dur == 120:
                        dur_display = " 110分鐘"
                    else:
                        dur_display = f" {dur}分鐘"
                elif a['service'] in ["視力點穴", "三伏貼", "三九貼", "視力點穴療程", "視力點穴療程 (大人)", "視力點穴療程 (小孩)"]:
                    dur_display = "" # 點穴、三伏貼、三九貼、點穴療程不標時長
                else:
                    dur_display = f" {dur}分鐘"
                    
                # 🌟 解決時長重複標註問題：若服務名稱中已含有「分鐘」，尾部自動不重複顯示時長
                if "分鐘" in service_msg_name:
                    dur_display = ""
                    
                # 家族合併時，時段前加上姓名區別
                name_prefix = f" {a['name']}" if len(names) > v1 else ""
                
                # 整理星期格式（全形括號）
                wd_clean = a['weekday'].replace("(", "（").replace(")", "）") if a['weekday'] else ""
                if wd_clean and "（" not in wd_clean:
                    wd_clean = f"（{wd_clean}）"
                    
                price_display = get_price_string(a['service'], dur, a.get('raw_name', ''), a['therapist'], a['uid'])
                lines.append(f"{a['date']}{wd_clean} {a['time']}{name_prefix} {service_display}{dur_display}")
                lines.append("")
                
            # 地址與入店說明條件式注入
            if has_minquan:
                lines.append("進民權店後請先至進門右手邊鞋櫃旁的小教室等待")
                lines.append("")
                lines.append("民權店地址:臺北市中山區民權東路二段67號3樓")
                lines.append("")
            if has_guangfu:
                lines.append("光復店地址:臺北市大安區正聲里光復南路308巷31號2F")
                lines.append("")
                
            lines.append("請準時抵達報到。")
            lines.append("")
            lines.append("感謝您的預約，百胤視力整復所 敬上")
            
            filtered_output_messages.append("\n".join(lines))
            
        all_text = "\n\n================================================================================\n\n".join(filtered_output_messages)
        
        if filtered_output_messages:
            st.text_area("訊息複製區", value=all_text, height=450)
            
            fn_suffix = f"_{selected_therapist}" if selected_therapist != "所有診" else ""
            st.download_button(
                label=f"📥 一鍵下載預約訊息文字檔 (TXT) - {selected_therapist}",
                data=all_text,
                file_name=f"百胤預約訊息_{target_date_input}{fn_suffix}.txt",
                mime="text/plain"
            )
        else:
            st.info(f"ℹ️ 在【{selected_therapist}】診別中未發現有效預約訊息。")

    with tab2:
        st.subheader("📊 每日收費明細與財務對帳表 (內部用)")
        
        # Get list of unique dates sorted
        raw_unique_dates = sorted(list(set(r['date'] for r in st.session_state['all_active_records'] if r.get('date'))), key=get_date_val)
        # Filter out Sunday (週日)
        unique_dates = []
        for d in raw_unique_dates:
            wd_clean = ""
            for r in st.session_state['all_active_records']:
                if r['date'] == d and r.get('weekday'):
                    wd_clean = r['weekday'].replace("(", "").replace(")", "")
                    break
            if "日" not in wd_clean:
                unique_dates.append(d)
        if not unique_dates:
            st.info("無預約日期資料")
        else:
            # Let staff toggle day-by-day
            selected_date = st.selectbox("📅 請選擇對帳日期：", options=unique_dates)
            
            state_key = f"reconcile_df_{selected_date}"
            
            # Filter active records for that date (and skip admin/cancelled)
            day_records = [r for r in st.session_state['all_active_records'] if r.get('date') == selected_date]
            
            # If not in session state, initialize it
            if state_key not in st.session_state:
                reconcile_data = []
                running_idx = 1
                
                rows = get_daily_reconcile_rows(day_records, st.session_state['admin_keywords'])
                for uid, name, main_appt, patch_appt in rows:
                    earliest_time = main_appt['time'] if main_appt else patch_appt['time']
                    
                    # Calculate main fee
                    main_service_name = ""
                    main_fee = 0
                    if main_appt:
                        dur = main_appt['custom_dur']
                        if dur is None:
                            dur = main_appt['slots'] * 30
                        main_service_name = map_to_standard_service(main_appt['service'], dur, main_appt['raw_name'], uid)
                        main_fee = SERVICE_PRICES.get(main_service_name, 0)
                    elif patch_appt:
                        main_service_name = patch_appt['service']
                        
                    # Calculate patch fee
                    patch_fee = 0
                    if patch_appt:
                        _, _, _, parsed_amt = parse_row_payments_and_products(patch_appt['raw_name'], 0, True, uid)
                        if parsed_amt:
                            patch_fee = parsed_amt
                        else:
                            patch_fee = 500 # Default package price
                    
                    # Combine raw names to look for products and payment details
                    row_appts = [a for a in [main_appt, patch_appt] if a is not None]
                    all_raw_names = " ".join(str(a['raw_name']) for a in row_appts)
                    pay_method, product_name, product_fee, parsed_paid = parse_row_payments_and_products(all_raw_names, main_fee, bool(patch_appt), uid)
                    
                    # Combine product name and fee to display, e.g. "蜂膠$2500"
                    product_display = ""
                    if product_name:
                        product_display = f"{product_name}${product_fee}" if product_fee > 0 else product_name
                        
                    receivable = main_fee + patch_fee + product_fee
                    if parsed_paid is not None:
                        received = parsed_paid
                        change = max(0, received - receivable)
                    else:
                        received = None  # 實收金額預設為空白
                        change = 0
                    
                    # Combine remarks
                    remarks_list = []
                    for a in row_appts:
                        raw_str = str(a.get('raw_name', ''))
                        clean_rem = raw_str
                        if uid and uid != "無病歷號":
                            clean_rem = clean_rem.replace(str(uid), "")
                        for kw in ["車位", "跟診", "取消", "諮商", "諮詢", "點穴2次", "點穴兩次", "初診", "刮痧"]:
                            if kw in clean_rem:
                                remarks_list.append(kw)
                    remarks_str = ", ".join(list(set(remarks_list)))
                    
                    reconcile_data.append({
                        "項次": running_idx,
                        "時間": earliest_time,
                        "病歷號碼": uid,
                        "個案姓名": name,
                        "項目": main_service_name,
                        "費用": main_fee,
                        "三伏貼": patch_fee,
                        "產品": product_display,
                        "產品費用": product_fee,
                        "應收金額": receivable,
                        "實收金額": received,
                        "找錢": change,
                        "繳款方式": pay_method,
                        "已掛號": "☐",
                        "現場確認/備註": remarks_str
                    })
                    running_idx += 1
                
                st.session_state[state_key] = pd.DataFrame(reconcile_data)
                
            reconcile_df = st.session_state[state_key]
            
            if reconcile_df.empty:
                st.info("當日無有效收費明細")
            else:
                metric_container = st.container()
                
                # Render interactive table editor
                edited_df = st.data_editor(
                    reconcile_df,
                    column_config={
                        "項目": st.column_config.SelectboxColumn(
                            "項目",
                            options=SERVICE_OPTIONS,
                            required=True,
                            width="medium"
                        ),
                        "繳款方式": st.column_config.SelectboxColumn(
                            "繳款方式",
                            options=["尚未選擇", "付現", "匯款", "街口"],
                            required=True,
                        ),
                        "已掛號": st.column_config.SelectboxColumn(
                            "已掛號",
                            options=["✔", "☐"],
                            required=True,
                        ),
                    },
                    use_container_width=True,
                    disabled=["項次", "時間", "病歷號碼", "個案姓名", "費用", "三伏貼", "產品", "產品費用", "應收金額", "找錢"],
                    key=f"editor_{selected_date}"
                )
                
                # Check for edits and dynamically recalculate dependent financial columns
                has_changes = False
                for idx, row in edited_df.iterrows():
                    item = row["項目"]
                    expected_fee = SERVICE_PRICES.get(item, 0)
                    
                    # 1. Update individual fee based on selected service
                    if row["費用"] != expected_fee:
                        edited_df.at[idx, "費用"] = expected_fee
                        has_changes = True
                        
                    # 2. Update receivable amount = fee + patch_fee + product_fee
                    expected_receivable = expected_fee + int(row["三伏貼"]) + int(row["產品費用"])
                    if row["應收金額"] != expected_receivable:
                        edited_df.at[idx, "應收金額"] = expected_receivable
                        has_changes = True
                        
                    # 3. Update change = max(0, received - receivable)
                    received_val = row["實收金額"]
                    if pd.isna(received_val) or received_val is None or str(received_val).strip() == "":
                        received = None
                    else:
                        try:
                            received = int(float(received_val))
                        except:
                            received = None
                    
                    if received is not None:
                        expected_change = max(0, received - expected_receivable)
                    else:
                        expected_change = 0
                        
                    if pd.isna(row["找錢"]) or row["找錢"] != expected_change:
                        edited_df.at[idx, "找錢"] = expected_change
                        has_changes = True
                        
                if has_changes:
                    st.session_state[state_key] = edited_df
                    st.rerun()
                    
                # Display metrics summary using finalized edited_df
                m_total_receivable = edited_df["應收金額"].sum()
                m_total_received = edited_df["實收金額"].sum()
                m_cash = edited_df[edited_df["繳款方式"] == "付現"]["實收金額"].sum()
                m_remit = edited_df[edited_df["繳款方式"] == "匯款"]["實收金額"].sum()
                m_jk = edited_df[edited_df["繳款方式"] == "街口"]["實收金額"].sum()
                
                with metric_container:
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        st.metric("今日應收總額", f"${m_total_receivable}")
                    with c2:
                        st.metric("今日實收總額", f"${m_total_received}")
                    with c3:
                        st.metric("今日現金實收", f"${m_cash}")
                    with c4:
                        st.metric("今日匯款/街口實收", f"${m_remit + m_jk}")
                        
                # 🌟 CSV Daily & Weekly Excel Dual Export 🌟
                col_dl1, col_col2 = st.columns(2)
                
                with col_dl1:
                    # CSV Export with BOM utf-8-sig for Excel
                    csv_buffer = io.StringIO()
                    edited_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                    csv_data = csv_buffer.getvalue()
                    
                    st.download_button(
                        label=f"📥 下載 {selected_date.replace('/', '_')} 收費對帳表 (CSV)",
                        data=csv_data,
                        file_name=f"百胤收費對帳表_{selected_date.replace('/', '')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                with col_col2:
                    # Weekly Excel Export
                    try:
                        excel_data = generate_weekly_excel_bytes(
                            st.session_state['all_active_records'],
                            target_date_input,
                            st.session_state['admin_keywords']
                        )
                        # 🌟 智慧動態產生含有當週日期範圍的檔名，方便行政人員辨識與整理
                        try:
                            if unique_dates:
                                # 取得目標年份，預設為輸入日期的年份或今年
                                y_match = re.search(r'\d{4}', target_date_input)
                                y_str = y_match.group() if y_match else str(date.today().year)
                                
                                # 格式化首日 (週一)
                                start_parts = unique_dates[0].split('/')
                                start_m = start_parts[0].zfill(2)
                                start_d = start_parts[1].zfill(2) if len(start_parts) > 1 else "01"
                                
                                # 格式化末日 (週六)
                                end_parts = unique_dates[-1].split('/')
                                end_m = end_parts[0].zfill(2)
                                end_d = end_parts[1].zfill(2) if len(end_parts) > 1 else "01"
                                
                                range_str = f"{y_str}_{start_m}{start_d}-{end_m}{end_d}"
                                excel_filename = f"百胤收費對帳明細表_{range_str}.xlsx"
                            else:
                                excel_filename = "百胤收費對帳明細表_V19當週.xlsx"
                        except Exception as e_fn:
                            excel_filename = "百胤收費對帳明細表_V19當週.xlsx"

                        st.download_button(
                            label="📥 一鍵下載整週收費對帳表 (Excel)",
                            data=excel_data,
                            file_name=excel_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except Exception as e_excel:
                        st.error(f"Excel 匯出失敗：{str(e_excel)}")
