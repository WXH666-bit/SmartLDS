"""生成两种全新版式：报关单 + 仓库入库单 → bol_201~210"""
import json, random, os, sys
from playwright.sync_api import sync_playwright
from dataset_organizer import write_dataset_index

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(ROOT, "dataset", "fewshot_samples")

ports = ["上海海关", "深圳海关", "天津海关", "宁波海关"]
transports = ["海运", "空运", "铁路", "公路"]
companies = ["华贸进出口有限公司", "远洋贸易集团", "中商国际贸易公司"]
goods = [("电子元器件", "IC芯片"), ("纺织品", "棉布"), ("机械设备", "电机")]
currencies = ["USD", "EUR", "RMB"]
origins = ["日本", "德国", "美国", "韩国"]
warehouses = ["A区-01库", "B区-03库", "C区-02库"]
suppliers = ["恒达制造有限公司", "瑞丰供应链管理公司"]
items_pool = [
    ("MAT-001", "不锈钢管", "25mm"),
    ("MAT-002", "轴承", "6205"),
    ("MAT-003", "液压油", "46号"),
    ("MAT-004", "螺栓", "M12"),
]

T_A = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font:10pt SimSun,sans-serif;padding:20px}
h3{text-align:center;margin:0 0 10px}
table{border-collapse:collapse;width:100%%}
td{border:1px solid #000;padding:6px}
.lb{background:#eee;font-weight:bold;width:18%%}
</style></head><body>
<h3>中华人民共和国海关进口货物报关单</h3>
<p style="text-align:center;font-size:9pt;margin:0 0 12px">海关编号：%(customs_no)s &nbsp; 申报日期：%(declare_date)s</p>
<table>
<tr><td class="lb">进口口岸</td><td width="32%%">%(import_port)s</td><td class="lb">运输方式</td><td width="32%%">%(transport)s</td></tr>
<tr><td class="lb">经营单位</td><td>%(company)s</td><td class="lb">收货单位</td><td>%(receiver)s</td></tr>
<tr><td class="lb">商品名称</td><td>%(goods_name)s</td><td class="lb">数量及单位</td><td>%(qty)s %(unit)s</td></tr>
<tr><td class="lb">总价</td><td>%(total_price)s %(currency)s</td><td class="lb">原产国</td><td>%(origin)s</td></tr>
<tr><td class="lb">毛重</td><td>%(gross_weight)s KG</td><td class="lb">净重</td><td>%(net_weight)s KG</td></tr>
</table></body></html>"""

T_B = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font:10pt SimSun,sans-serif;padding:20px}
h3{text-align:center;margin:0 0 10px}
.info{margin:8px 0;font-size:11pt}
.info b{display:inline-block;width:80px}
table{border-collapse:collapse;width:100%%;margin-top:12px}
th{background:#333;color:#fff;padding:6px}
td{border:1px solid #ccc;padding:5px;text-align:center}
</style></head><body>
<h3>仓库入库单</h3>
<p class="info"><b>入库单号：</b>%(receipt_no)s</p>
<p class="info"><b>入库日期：</b>%(date)s</p>
<p class="info"><b>供应商：</b>%(supplier)s</p>
<p class="info"><b>仓库：</b>%(warehouse)s</p>
<table>
<tr><th>序号</th><th>物料编码</th><th>物料名称</th><th>规格</th><th>数量</th><th>单位</th></tr>
<tr><td>1</td><td>%(item_code1)s</td><td>%(item_name1)s</td><td>%(spec1)s</td><td>%(qty1)s</td><td>%(unit1)s</td></tr>
<tr><td>2</td><td>%(item_code2)s</td><td>%(item_name2)s</td><td>%(spec2)s</td><td>%(qty2)s</td><td>%(unit2)s</td></tr>
</table></body></html>"""

with sync_playwright() as p:
    browser = p.chromium.launch()
    for i in range(10):
        idx = 201 + i
        if i < 5:
            data = {
                "template": "customs_declaration",
                "customs_no": f"CUS{random.randint(10000,99999)}{random.randint(100,999)}",
                "declare_date": f"2024/{random.randint(1,12):02d}/{random.randint(1,28):02d}",
                "import_port": random.choice(ports),
                "transport": random.choice(transports),
                "company": random.choice(companies),
                "receiver": random.choice(companies),
                "goods_name": random.choice(goods)[0],
                "qty": str(random.randint(1, 99)),
                "unit": "件",
                "total_price": str(random.randint(1000, 50000)),
                "currency": random.choice(currencies),
                "origin": random.choice(origins),
                "gross_weight": str(random.randint(100, 5000)),
                "net_weight": str(random.randint(80, 4800)),
            }
            html = T_A % data
        else:
            i1 = random.choice(items_pool)
            i2 = random.choice(items_pool)
            data = {
                "template": "warehouse_receipt",
                "receipt_no": f"RK{random.randint(2024,2026)}{random.randint(1000,9999)}",
                "date": f"2024/{random.randint(1,12):02d}/{random.randint(1,28):02d}",
                "supplier": random.choice(suppliers),
                "warehouse": random.choice(warehouses),
                "item_code1": i1[0], "item_name1": i1[1], "spec1": i1[2],
                "qty1": str(random.randint(10, 200)),
                "unit1": random.choice(["个", "件", "套"]),
                "item_code2": i2[0], "item_name2": i2[1], "spec2": i2[2],
                "qty2": str(random.randint(10, 200)),
                "unit2": random.choice(["个", "件", "套"]),
            }
            html = T_B % data

        group_dir = "customs_declaration" if i < 5 else "warehouse_receipt"
        out_dir = os.path.join(DATASET_DIR, group_dir)
        os.makedirs(out_dir, exist_ok=True)
        json_path = os.path.join(out_dir, f"bol_{idx:03d}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        pdf_path = os.path.join(out_dir, f"bol_{idx:03d}.pdf")
        page = browser.new_page()
        page.set_content(html)
        page.pdf(path=pdf_path, format="A4")
        page.close()
        print(f"  bol_{idx:03d} ← [{data['template']}]")

    browser.close()
write_dataset_index(os.path.join(ROOT, "dataset"))
print(f"\nDone: bol_201~{idx}")
