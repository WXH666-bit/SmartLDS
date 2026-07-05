"""
合成物流单证数据生成器
生成多种版式的海运提单/订舱委托书 PDF + 对应的 Ground Truth JSON 标注
"""
'''
关键字段说明：
shipper: 托运人
consignee: 收货人
notify_party: 通知方
bl_no: 提单号
pol: 装货港
pod: 卸货港
vessel: 船名
voyage: 航次
por: 收货地
delivery: 交货地
container1: 箱号1
seal1: 封号1
container2: 箱号2
seal2: 封号2
qty1: 件数1
pkg1: 包装1
qty2: 件数2
pkg2: 包装2
desc1: 货物描述1
desc2: 货物描述2
gw1: 毛重1
cbm1: 体积1
gw2: 毛重2
cbm2: 体积2
total_gw: 总毛重
total_cbm: 总体积
freight: 运费条款
issue_place: 签发地
issue_date: 签发日期
'''

from playwright.sync_api import sync_playwright
from faker import Faker
import random
import string
import os
import json

fake = Faker(["en_US", "zh_CN"])

# ============================================================
# 版式 A：标准海运提单 (Maersk 风格，英文为主)
# ============================================================
TEMPLATE_A = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 10pt; margin: 40px; }}
  h2 {{ text-align: center; font-size: 14pt; }}
  .logo {{ text-align: center; color: #003882; font-size: 18pt; font-weight: bold; margin-bottom: 10px; }}
  table {{ border-collapse: collapse; width: 100%; border: 1px solid black; margin-top: 10px; }}
  th, td {{ border: 1px solid black; padding: 5px; vertical-align: top; }}
  .label {{ color: #555; font-weight: bold; background-color: #f0f0f0; width: 18%; }}
  .section {{ background-color: #003882; color: white; font-weight: bold; padding: 3px 8px; margin-top: 15px; }}
</style>
</head>
<body>
<div class="logo">MAERSK LINE</div>
<h2>BILL OF LADING / 海运提单</h2>
<hr>
<table>
  <tr>
    <td class="label">Shipper:</td>
    <td width="32%">{shipper}</td>
    <td class="label">B/L No.:</td>
    <td width="32%">{bl_no}</td>
  </tr>
  <tr>
    <td class="label">Consignee:</td>
    <td>{consignee}</td>
    <td class="label">Notify Party:</td>
    <td>{notify_party}</td>
  </tr>
  <tr>
    <td class="label">Port of Loading:</td>
    <td>{pol}</td>
    <td class="label">Port of Discharge:</td>
    <td>{pod}</td>
  </tr>
  <tr>
    <td class="label">Vessel:</td>
    <td>{vessel}</td>
    <td class="label">Voyage No.:</td>
    <td>{voyage}</td>
  </tr>
  <tr>
    <td class="label">Place of Receipt:</td>
    <td>{por}</td>
    <td class="label">Place of Delivery:</td>
    <td>{delivery}</td>
  </tr>
</table>

<div class="section">CARGO DETAILS / 货物明细</div>
<table>
  <tr>
    <th width="5%">No.</th>
    <th width="15%">Container No.</th>
    <th width="10%">Seal No.</th>
    <th width="8%">Qty</th>
    <th width="12%">Package</th>
    <th width="25%">Description of Goods</th>
    <th width="12%">Gross Weight</th>
    <th width="13%">Measurement</th>
  </tr>
  <tr>
    <td align="center">1</td>
    <td align="center">{container1}</td>
    <td align="center">{seal1}</td>
    <td align="center">{qty1}</td>
    <td align="center">{pkg1}</td>
    <td>{desc1}</td>
    <td align="center">{gw1} KGS</td>
    <td align="center">{cbm1} CBM</td>
  </tr>
  <tr>
    <td align="center">2</td>
    <td align="center">{container2}</td>
    <td align="center">{seal2}</td>
    <td align="center">{qty2}</td>
    <td align="center">{pkg2}</td>
    <td>{desc2}</td>
    <td align="center">{gw2} KGS</td>
    <td align="center">{cbm2} CBM</td>
  </tr>
</table>

<table>
  <tr>
    <td class="label" width="18%">Total Gross Weight:</td>
    <td width="32%">{total_gw} KGS</td>
    <td class="label" width="18%">Total Measurement:</td>
    <td width="32%">{total_cbm} CBM</td>
  </tr>
  <tr>
    <td class="label">Freight & Charges:</td>
    <td>{freight}</td>
    <td class="label">Place & Date of Issue:</td>
    <td>{issue_place}, {issue_date}</td>
  </tr>
</table>
</body>
</html>
"""

# ============================================================
# 版式 B：订舱委托书 (COSCO 风格，中英混合)
# ============================================================
TEMPLATE_B = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: SimSun, Arial, sans-serif; font-size: 10pt; margin: 30px; }}
  h2 {{ text-align: center; font-size: 15pt; }}
  .logo {{ text-align: center; color: #004080; font-size: 20pt; font-weight: bold; }}
  table {{ border-collapse: collapse; width: 100%; border: 2px solid #004080; }}
  td {{ border: 1px solid #004080; padding: 6px; }}
  .label {{ background-color: #e8f0fe; font-weight: bold; width: 15%; }}
  .section-title {{ background-color: #004080; color: white; text-align: center; font-weight: bold; }}
</style>
</head>
<body>
<div class="logo">COSCO SHIPPING</div>
<h2>出口货物订舱委托书 / Booking Note</h2>
<table>
  <tr><td colspan="4" class="section-title">托运人信息 / Shipper Information</td></tr>
  <tr>
    <td class="label">托运人 Shipper:</td>
    <td width="35%">{shipper}</td>
    <td class="label">订舱号 B/L No.:</td>
    <td width="35%">{bl_no}</td>
  </tr>
  <tr>
    <td class="label">收货人 Consignee:</td>
    <td>{consignee}</td>
    <td class="label">通知方 Notify:</td>
    <td>{notify_party}</td>
  </tr>
  <tr><td colspan="4" class="section-title">运输信息 / Transport Information</td></tr>
  <tr>
    <td class="label">装货港 POL:</td>
    <td>{pol}</td>
    <td class="label">卸货港 POD:</td>
    <td>{pod}</td>
  </tr>
  <tr>
    <td class="label">船名 Vessel:</td>
    <td>{vessel}</td>
    <td class="label">航次 Voyage:</td>
    <td>{voyage}</td>
  </tr>
  <tr>
    <td class="label">收货地 POR:</td>
    <td>{por}</td>
    <td class="label">交货地 Delivery:</td>
    <td>{delivery}</td>
  </tr>
  <tr><td colspan="4" class="section-title">货物信息 / Cargo Information</td></tr>
  <tr>
    <td class="label">箱号 Container:</td>
    <td>{container1}</td>
    <td class="label">封号 Seal:</td>
    <td>{seal1}</td>
  </tr>
  <tr>
    <td class="label">件数 Qty:</td>
    <td>{qty1} {pkg1}</td>
    <td class="label">包装 Pkg:</td>
    <td>{pkg1}</td>
  </tr>
  <tr>
    <td class="label">货名 Description:</td>
    <td colspan="3">{desc1}</td>
  </tr>
  <tr>
    <td class="label">毛重 G.W.:</td>
    <td>{gw1} KGS</td>
    <td class="label">体积 CBM:</td>
    <td>{cbm1} CBM</td>
  </tr>
  <tr>
    <td class="label">运费条款:</td>
    <td>{freight}</td>
    <td class="label">签发地 & 日期:</td>
    <td>{issue_place}, {issue_date}</td>
  </tr>
</table>
</body>
</html>
"""

# ============================================================
# 版式 C：简易货代委托书 (中英双语，紧凑型)
# ============================================================
TEMPLATE_C = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: SimSun, Arial, sans-serif; font-size: 9pt; margin: 25px; }}
  h3 {{ text-align: center; font-size: 14pt; border-bottom: 2px solid black; padding-bottom: 5px; }}
  table {{ border-collapse: collapse; width: 100%; border: 1px solid #333; }}
  td {{ border: 1px solid #666; padding: 4px; }}
  .label {{ font-weight: bold; width: 14%; background-color: #fafafa; }}
  .header {{ background-color: #ddd; text-align: center; font-weight: bold; }}
</style>
</head>
<body>
<h3>货运委托书 / SHIPPING ORDER</h3>
<table>
  <tr><td colspan="4" class="header">基本信息 / Basic Info</td></tr>
  <tr>
    <td class="label">Shipper:</td><td>{shipper}</td>
    <td class="label">B/L No.:</td><td>{bl_no}</td>
  </tr>
  <tr>
    <td class="label">Consignee:</td><td>{consignee}</td>
    <td class="label">Notify:</td><td>{notify_party}</td>
  </tr>
  <tr>
    <td class="label">POL:</td><td>{pol}</td>
    <td class="label">POD:</td><td>{pod}</td>
  </tr>
  <tr>
    <td class="label">Vessel:</td><td>{vessel}</td>
    <td class="label">Voyage:</td><td>{voyage}</td>
  </tr>
  <tr>
    <td class="label">Container:</td><td>{container1}</td>
    <td class="label">Seal No.:</td><td>{seal1}</td>
  </tr>
  <tr>
    <td class="label">Description:</td><td colspan="3">{desc1}</td>
  </tr>
  <tr>
    <td class="label">Qty/Pkg:</td><td>{qty1} {pkg1}</td>
    <td class="label">G.W.(KGS):</td><td>{gw1}</td>
  </tr>
  <tr>
    <td class="label">CBM:</td><td>{cbm1}</td>
    <td class="label">Freight:</td><td>{freight}</td>
  </tr>
  <tr>
    <td class="label">Issue Place:</td><td>{issue_place}</td>
    <td class="label">Date:</td><td>{issue_date}</td>
  </tr>
</table>
</body>
</html>
"""

# ============================================================
# 版式 HTML 模板列表
# ============================================================
TEMPLATES = [
    ("maersk_style", TEMPLATE_A),
    ("cosco_style", TEMPLATE_B),
    ("simple_style", TEMPLATE_C),
]


def gen_container_no():
    """生成随机集装箱号，如 MSKU1234567"""
    prefix = random.choice(["MSKU", "TCLU", "COSU", "OOLU", "EVER", "ONEU", "MAEU", "CMAU"])
    digits = "".join(random.choices(string.digits, k=random.randint(6, 7)))
    return prefix + digits


def gen_seal_no():
    """生成随机封号，如 SL-AB123CD5"""
    return "SL-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def gen_bl_no():
    """生成提单号"""
    return "BL" + "".join(random.choices(string.digits, k=8))


def create_record():
    """为一份单证生成随机的 Ground Truth 数据"""
    gw1 = random.randint(5000, 28000)
    gw2 = random.randint(3000, 20000)
    cbm1 = round(random.uniform(15, 65), 2)
    cbm2 = round(random.uniform(10, 50), 2)

    return {
        "shipper": fake.company(),
        "consignee": fake.company(),
        "notify_party": fake.company(),
        "bl_no": gen_bl_no(),
        "pol": random.choice(["NINGBO", "SHANGHAI", "SHENZHEN", "QINGDAO", "XIAMEN"]),
        "pod": random.choice(["LOS ANGELES", "HAIPHONG", "ROTTERDAM", "HAMBURG", "SINGAPORE", "BUSAN"]),
        "vessel": random.choice(["EVER FAST", "COSCO STAR", "OOCL TOKYO", "MAERSK ESSEN", "ONE HARBOUR"]),
        "voyage": str(random.randint(100, 999)) + random.choice(["E", "W", "S", "N"]),
        "por": random.choice(["NINGBO", "SHANGHAI", "SHENZHEN", "HANGZHOU"]),
        "delivery": random.choice(["LOS ANGELES", "ROTTERDAM", "HAMBURG", "NEW YORK"]),
        "container1": gen_container_no(),
        "seal1": gen_seal_no(),
        "container2": gen_container_no(),
        "seal2": gen_seal_no(),
        "qty1": str(random.randint(10, 200)),
        "pkg1": random.choice(["PKGS", "PALLETS", "CARTONS", "DRUMS"]),
        "qty2": str(random.randint(5, 150)),
        "pkg2": random.choice(["PKGS", "PALLETS", "CARTONS", "DRUMS"]),
        "desc1": fake.catch_phrase().upper() + " / " + fake.word().upper(),
        "desc2": fake.catch_phrase().upper() + " / " + fake.word().upper(),
        "gw1": str(gw1),
        "cbm1": str(cbm1),
        "gw2": str(gw2),
        "cbm2": str(cbm2),
        "total_gw": str(gw1 + gw2),
        "total_cbm": str(round(cbm1 + cbm2, 2)),
        "freight": random.choice(["PREPAID", "COLLECT"]),
        "issue_place": random.choice(["NINGBO", "SHANGHAI", "SHENZHEN"]),
        "issue_date": f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/{random.randint(2023,2026)}",
    }


def create_dataset(num=200):
    """主函数：生成 num 份 PDF + JSON"""
    # 始终在项目根目录创建 dataset（不管从哪里运行脚本）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    pdf_dir = os.path.join(project_root, "dataset", "pdf")
    json_dir = os.path.join(project_root, "dataset", "json")
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)

    for i in range(num):
        rec = create_record()

        # 轮询选择版式
        template_name, template_html = TEMPLATES[i % len(TEMPLATES)]
        html_content = template_html.format(**rec)

        pdf_path = os.path.join(pdf_dir, f"bol_{i+1:03d}.pdf")
        json_path = os.path.join(json_dir, f"bol_{i+1:03d}.json")

        # 用 Playwright (Chromium) 渲染 HTML 为 PDF
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html_content)
            page.pdf(path=pdf_path, format="A4")
            browser.close()

        # 保存 Ground Truth JSON
        rec["template"] = template_name
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)

        if (i + 1) % 20 == 0:
            print(f"  已生成 {i+1}/{num} 份...")

    print(f"数据集生成完成！共 {num} 份单证（3种版式），保存在 dataset/ 目录下。")


if __name__ == "__main__":
    create_dataset(160)
