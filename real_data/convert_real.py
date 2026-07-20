"""
将 real_data/images/ 中的20张真实照片转换为项目 dataset 格式
- 外卖小票写入 dataset/real_scans/food_delivery/
- 快递面单写入 dataset/real_scans/express/
"""

import json
import os
import random
import sys
from PIL import Image

# 随机中文名字生成
SURNAMES = ["王","李","张","刘","陈","杨","赵","黄","周","吴","徐","孙","马","朱","胡","郭","何","高","林","郑","罗","梁","谢","宋","唐","许","韩","邓","冯","萧","彭","曾","田","董","潘","袁","于","蒋","蔡","余","杜","叶","程","苏","魏","吕","丁","任","卢","姚","沈","钟","姜","崔","谭","陆","汪","范","金","石","廖","贾","夏","韦","付","方","白","邹","孟","熊","秦","邱","江","尹","薛","闫","段","雷","侯","龙","史","黎","贺","顾","毛","郝","龚","邵","万","钱","覃","武","戴","孔","汤","庞","樊","兰","殷","施","陶","洪","翟","安","颜","倪","严","牛","温","芦","季","俞","章"]
GIVEN_MALE = ["伟","强","磊","军","洋","勇","杰","明","涛","斌","超","浩","鹏","飞","刚","华","平","辉","宇","亮","峰","文","波","宁","龙","林","建","鑫","旭","瑞","博","阳","帆","晨","哲","铭","豪","恒","睿","轩","昊","然","毅","锐","源","恺","瑜","诚","安"]
GIVEN_FEMALE = ["芳","敏","静","丽","婷","雪","玲","娟","艳","红","霞","云","娜","慧","莉","燕","秀","萍","倩","兰","凤","洁","梅","英","琴","蓉","悦","怡","雯","妍","琪","瑶","萱","薇","珊","琳","婉","月","冰","舒"]
GIVEN_NEUTRAL = ["一","宁","安","然","辰","彦","子","言","若","乐","雨","思","远","新","之","怀","景","天","文","知"]

def gen_name(masked=""):
    """根据脱敏名生成随机全名，保留已知部分"""
    surname = random.choice(SURNAMES)
    # 从 masked 中提取已知字符
    known = ""
    star_count = 0
    for ch in masked:
        if ch == "*":
            star_count += 1
        elif ch != "(" and ch != ")" and not ch.isdigit():
            known += ch
    if known:
        # 用已知部分作为姓
        if len(known) == 1:
            surname = known
        elif len(known) >= 2:
            surname = known[0]
    # 生成名字部分
    given = random.choice(GIVEN_NEUTRAL + GIVEN_MALE + GIVEN_FEMALE)
    if star_count >= 2 or len(masked.replace("*","").replace("(","").replace(")","")) <= 0:
        given = random.choice(GIVEN_NEUTRAL) + random.choice(GIVEN_NEUTRAL)
    return surname + given

def gen_phone(masked=""):
    """根据脱敏号码生成随机11位号码，保留已知尾号"""
    # 提取尾部已知数字（连续数字部分）
    tail_digits = ""
    for ch in reversed(masked):
        if ch.isdigit():
            tail_digits = ch + tail_digits
        else:
            break
    tail_len = len(tail_digits)
    # 前面随机填充到11位
    prefix = random.choice(["13","14","15","16","17","18","19"])
    middle_len = 11 - 2 - tail_len
    middle = "".join(str(random.randint(0,9)) for _ in range(middle_len))
    return prefix + middle + tail_digits

def fix_record(rec):
    """替换记录中的脱敏姓名和电话为随机值"""
    for k, v in rec.items():
        if isinstance(v, str):
            if k in ("customer","recipient","sender") and "*" in v:
                rec[k] = gen_name(v)
            elif k in ("recipient_phone","sender_phone","customer_phone") and "*" in v:
                rec[k] = gen_phone(v)
    return rec

REAL_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(REAL_DIR, "images")
PROJECT_ROOT = os.path.dirname(REAL_DIR)
DATASET_DIR = os.path.join(PROJECT_ROOT, "dataset")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
from dataset_organizer import write_dataset_index

os.makedirs(DATASET_DIR, exist_ok=True)

records = [
    # 1: 古茗奶茶 外卖小票
    {"template":"real_scan","category":"food_delivery","platform":"美团外卖","shop":"古茗(韶关学院店)","order_no":"900571411716984980","order_time":"2023-06-01 19:21:39","delivery_time":"2023-06-01 21:30:00","items":[{"name":"牛油果巴旦木奶昔","spec":"中","qty":1,"price":20},{"name":"杨枝甘露椰奶","spec":"中","qty":1,"price":18},{"name":"超A芝士桃桃","spec":"大","qty":1,"price":20}],"total_amount":60.0,"delivery_fee":2.4,"packing_fee":1.5,"discount":1.9,"note":"姐姐上次给你发消息被姐夫逮到了...","utensils":"环保单不需要餐具","payment":"在线支付"},
    # 2: 张不怂米线 外卖小票
    {"template":"real_scan","category":"food_delivery","platform":"美团外卖","shop":"张不怂生烫牛肉米线(青安路店)","order_no":"2001619190594260328","order_time":"2025-05-29 10:37:16","delivery_time":"2025-05-29 12:30","customer":"邱先生","items":[{"name":"灵魂调料葱花+香菜+柴火糊辣椒","qty":1,"price":3.0},{"name":"开胃小菜","qty":1,"price":3.0},{"name":"经典生烫牛肉肉酱米线","qty":1,"price":45.0},{"name":"加米线","qty":1,"price":3.0},{"name":"网红现炸黄金蛋","qty":1,"price":5.0}],"total_amount":21.19,"original_amount":65.25,"delivery_fee":3.25,"packing_fee":3.0,"discount":41.06,"note":"哥哥昨天晚上辛苦你啦...","payment":"在线支付"},
    # 3: 江苏面馆 外卖小票
    {"template":"real_scan","category":"food_delivery","platform":"美团外卖","shop":"江苏面馆(淮扬特色炒菜)","order_no":"3500849202727247451","order_time":"12-11 17:22","delivery_time":"12-11 17:52","customer":"原(先生)","items":[{"name":"加牛肉","qty":1,"price":12.0},{"name":"加面条","qty":1,"price":2.0},{"name":"牛肉面(干拌面)","qty":1,"price":22.0}],"total_amount":41.0,"original_amount":42.0,"delivery_fee":4.0,"packing_fee":2.0,"discount":1.0,"address":"崇左市边境管理支队","payment":"在线支付"},
    # 4: 布袋炒饭 饿了么
    {"template":"real_scan","category":"food_delivery","platform":"饿了么/淘宝闪购","shop":"亿扬布袋炒饭·炒面·炒河粉(老城区店)","order_no":"8087070242563492151","order_time":"09-23 11:37","delivery_time":"09-23 12:09","customer":"王**","items":[{"name":"经典土鸡蛋炒饭","qty":1,"price":14.70}],"total_amount":7.70,"original_amount":20.70,"delivery_fee":4.0,"packing_fee":2.0,"discount":13.0,"note":"饭多多的给(要饿死了)你滴明白？","payment":"在线支付"},
    # 5: 申通快递
    {"template":"real_scan","category":"express","courier":"申通快递","tracking_no":"770325800536124","sender":"张子硕","sender_phone":"19333996009","sender_addr":"河北省石家庄市栾城区柳林镇","recipient":"陈*","recipient_phone":"15359411408转1713","recipient_addr":"辽宁省大连市金州区大连理工大学开发区校区融苑","item":"泡面麻酱火鸡面定制141克10包","print_time":"2026/06/12 00:10","service_line":"95543"},
    # 6: 京东物流
    {"template":"real_scan","category":"express","courier":"京东物流","tracking_no":"JD0159848202004","order_no":"297333832093","recipient":"赵*","recipient_phone":"1****5381","recipient_addr":"辽宁大连市金州区大连理工大学软件学院生活区","delivery_time":"10月01日 09:00-15:00","print_time":"09月30日 21:40","station":"大连高城山营业部","payment":"在线支付"},
    # 7: 极兔速递
    {"template":"real_scan","category":"express","courier":"极兔速递","tracking_no":"JT3165826117098","order_no":"WPLT260406W","sender":"万国云仓","sender_phone":"18951106662","sender_addr":"江苏省苏州市虎丘区协新路1号","recipient":"魏鑫鸿","recipient_phone":"13342130536","recipient_addr":"辽宁省大连市金州区大连理工大学第三学生公寓","print_time":"2026/06/06 10:35:40","qty":1,"service_line":"956025"},
    # 8: 中国邮政EMS
    {"template":"real_scan","category":"express","courier":"中国邮政EMS","tracking_no":"9803354220262","sender":"李女士","sender_phone":"13516185992","sender_addr":"天津市武清区汉沽港北梆子村","recipient":"赵*","recipient_phone":"15784413275转5381","recipient_addr":"辽宁省大连市金州区图强路321号大连理工大学软件学院生活区","item":"狗牙儿不凡滋脆玉米片88g","print_time":"2024/12/01 06:18:21","qty":1},
    # 9: 京东物流(药品)
    {"template":"real_scan","category":"express","courier":"京东物流","tracking_no":"JD0216411651826","order_no":"343451278313","sender":"沈阳药品仓","recipient":"魏*","recipient_phone":"1****0536","recipient_addr":"辽宁大连市金州区大连理工大学软件学院生活区","item":"药品","print_time":"2025-11-13 21:23","delivery_time":"11月14日 09:00-21:00","station":"大连高城山站","payment":"在线支付"},
    # 10: 中通快递
    {"template":"real_scan","category":"express","courier":"中通快递","tracking_no":"78943137685262","sender":"徐磊","sender_phone":"18434910573","sender_addr":"安徽省阜阳市颍东开发区徽清科技园B4栋","recipient":"魏*","recipient_phone":"18445786574转7198","recipient_addr":"辽宁省大连市金州区图强街321号大连理工大学开发区校区生活区","item":"药品/红包卡片","print_time":"2025/09/26 16:22:48","service_line":"95311"},
    # 11: 中通快递(乌鲁木齐)
    {"template":"real_scan","category":"express","courier":"中通快递","tracking_no":"79011638884235","sender":"普汇供应链","sender_phone":"19999213123","sender_addr":"乌鲁木齐市沙依巴克区兵团工业园迎春二街4号","recipient":"魏*","recipient_phone":"13074137504转4414","recipient_addr":"辽宁省大连市金州区湾里街道图强街321号大连理工大学开发区校区生活区","item":"食品(四口味各10包)","print_time":"2026/06/14 11:19:35","qty":1,"service_line":"95311"},
    # 12: 京东秒送 汉堡
    {"template":"real_scan","category":"food_delivery","platform":"京东秒送","shop":"京东甄选","order_no":"3546205003531122","order_time":"2026-07-01 10:52:28","items":[{"name":"香辣鸡腿中国汉堡","qty":2,"price":15.15}],"total_amount":15.10,"original_amount":30.50,"payment":"在线支付"},
    # 13: 圆通速递
    {"template":"real_scan","category":"express","courier":"圆通速递","tracking_no":"YT1981727819747","sender":"张子硕","sender_phone":"19333998009","sender_addr":"山西省太原市清徐县紫林路1号","recipient":"姜*","recipient_phone":"*******6390","recipient_addr":"辽宁省大连市金州区图强路321号大连理工大学开发区校区","item":"泡面麻酱火鸡面定制141克10包","print_time":"2023/10/28 19:09:05","service_line":"95554"},
    # 14: 京东秒送 汉堡
    {"template":"real_scan","category":"food_delivery","platform":"京东秒送","order_no":"JD3546426000799566","customer":"王**","customer_phone":"177****8696","address":"辽宁大连市金州区大连理工大学(开发区校区)憩苑","items":[{"name":"双层-美式嫩牛堡","qty":1},{"name":"葡式蛋挞","qty":1},{"name":"黄金鸡块5块","qty":1},{"name":"中可","qty":1}],"total_amount":28.80,"original_amount":38.80,"payment":"在线支付"},
    # 15: 京东物流(衣服)
    {"template":"real_scan","category":"express","courier":"京东物流","tracking_no":"JD0248651779819","order_no":"3541426017607564","sender":"武汉蔡甸服饰仓","recipient":"王*","recipient_phone":"177****8696","recipient_addr":"辽宁大连市金州区大连理工大学开发区校区生活区","item":"班尼路冰感空调短裤 中灰 3XL","print_time":"06月26日 15:26","qty":1},
    # 16: 申通快递(擀面皮)
    {"template":"real_scan","category":"express","courier":"申通快递","tracking_no":"777397229509061","sender":"森****","sender_addr":"陕西省宝鸡市凤翔区","recipient":"路*","recipient_phone":"19592546211转0841","recipient_addr":"辽宁省大连市金州区大连理工大学软件学院生活区","item":"秦人瘾面皮 宝鸡擀面皮310g/袋 8袋","print_time":"2026/04/03 10:03:15","service_line":"95543"},
    # 17: 极兔速递(巧克力棒)
    {"template":"real_scan","category":"express","courier":"极兔速递","tracking_no":"JT5471833173783","sender":"王生","sender_phone":"18000949893","sender_addr":"广东省揭阳市揭西县金和镇","recipient":"路*","recipient_phone":"17281436910转4937","recipient_addr":"辽宁省大连市金州区图强路321号大连理工大学软件学院生活区","item":"坚果巧克力棒90g","print_time":"2026/04/02 08:41:13","qty":1,"service_line":"956025"},
    # 18: 中通快递(火鸡面)
    {"template":"real_scan","category":"express","courier":"中通快递","tracking_no":"76927774740128","sender":"张子硕","sender_phone":"19333398009","sender_addr":"河北省邢台市隆尧县东方食品城华统食品有限公司","recipient":"魏*","recipient_phone":"15784307947转9729","recipient_addr":"辽宁省大连市金州区图强路321号大连理工大学软件学院生活区","item":"泡面火鸡5+泡面麻酱5","print_time":"2026/05/03 09:17:38","service_line":"95311"},
    # 19: 韵达快递(零食)
    {"template":"real_scan","category":"express","courier":"韵达快递","tracking_no":"465455618779229","sender":"张哲","sender_phone":"13237329756","sender_addr":"湖南省长沙市长沙县","recipient":"魏*","recipient_phone":"17284464145转8707","recipient_addr":"辽宁省大连市金州区图强路321号大连理工大学软件学院生活区","item":"晏子食品 泡椒臭干子20g*60","print_time":"2020/06/24 14:02:21","service_line":"95546"},
    # 20: 美团外卖 炸鸡腿
    {"template":"real_scan","category":"food_delivery","platform":"美团外卖","shop":"榆树炸鸡腿(嘉乐广场店)","order_no":"6021924037990000933","order_time":"2026-07-01 12:01:01","delivery_time":"12:21前送达","customer":"魏先生","items":[{"name":"小店热线 想吃啥点","qty":1,"price":31.99,"spec":"啥系列(孜然)","addons":["琵琶腿1个x3","炸鸡柳100克"]},{"name":"开业福利(赠品)","qty":1,"price":0,"detail":"豆皮肉卷&爆汁鱼丸"}],"total_amount":31.99,"note":"顾客需要餐具;优先出餐15分钟闪电送单","payment":"在线支付"},
]


def main():
    print(f"处理 {len(records)} 份真实扫描数据\n")
    for i, rec in enumerate(records):
        rec = fix_record(rec)  # 替换脱敏信息
        idx = 181 + i
        img_file = f"real_{i+1:02d}.jpg"
        img_path = os.path.join(IMG_DIR, img_file)
        group = "food_delivery" if rec.get("category") == "food_delivery" else "express"
        out_dir = os.path.join(DATASET_DIR, "real_scans", group)
        os.makedirs(out_dir, exist_ok=True)
        json_path = os.path.join(out_dir, f"bol_{idx:03d}.json")
        pdf_path = os.path.join(out_dir, f"bol_{idx:03d}.pdf")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)

        img = Image.open(img_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(pdf_path, "PDF")

        cat = rec["category"]
        name = rec.get("shop") or rec.get("courier") or ""
        print(f"  bol_{idx:03d} ← [{cat}] {name}")

    write_dataset_index(DATASET_DIR)
    print(f"\n完成！真实数据已写入 dataset/ (bol_181~{idx:03d})")


if __name__ == "__main__":
    main()
