"""各國姓名產生。全部是常見姓與名的隨機組合，不對應任何真實人物。"""

import random
import unicodedata

# (繁體, 簡體, 台灣拼法, 中國拼音)
CN_SURNAMES = [
    ("陳", "陈", "Chen", "Chen"), ("林", "林", "Lin", "Lin"), ("黃", "黄", "Huang", "Huang"),
    ("張", "张", "Chang", "Zhang"), ("李", "李", "Lee", "Li"), ("王", "王", "Wang", "Wang"),
    ("吳", "吴", "Wu", "Wu"), ("劉", "刘", "Liu", "Liu"), ("蔡", "蔡", "Tsai", "Cai"),
    ("楊", "杨", "Yang", "Yang"), ("許", "许", "Hsu", "Xu"), ("鄭", "郑", "Cheng", "Zheng"),
    ("謝", "谢", "Hsieh", "Xie"), ("郭", "郭", "Kuo", "Guo"), ("洪", "洪", "Hung", "Hong"),
    ("曾", "曾", "Tseng", "Zeng"), ("邱", "邱", "Chiu", "Qiu"), ("廖", "廖", "Liao", "Liao"),
    ("賴", "赖", "Lai", "Lai"), ("周", "周", "Chou", "Zhou"), ("葉", "叶", "Yeh", "Ye"),
    ("蘇", "苏", "Su", "Su"), ("何", "何", "Ho", "He"), ("羅", "罗", "Lo", "Luo"),
    ("高", "高", "Kao", "Gao"), ("梁", "梁", "Liang", "Liang"), ("宋", "宋", "Sung", "Song"),
    ("唐", "唐", "Tang", "Tang"), ("馮", "冯", "Feng", "Feng"), ("鍾", "钟", "Chung", "Zhong"),
]
CN_GIVEN = [
    ("志", "志", "Chih", "Zhi"), ("明", "明", "Ming", "Ming"), ("偉", "伟", "Wei", "Wei"),
    ("華", "华", "Hua", "Hua"), ("建", "建", "Chien", "Jian"), ("宏", "宏", "Hung", "Hong"),
    ("俊", "俊", "Chun", "Jun"), ("傑", "杰", "Chieh", "Jie"), ("怡", "怡", "Yi", "Yi"),
    ("婷", "婷", "Ting", "Ting"), ("雅", "雅", "Ya", "Ya"), ("慧", "慧", "Hui", "Hui"),
    ("佳", "佳", "Chia", "Jia"), ("玲", "玲", "Ling", "Ling"), ("美", "美", "Mei", "Mei"),
    ("淑", "淑", "Shu", "Shu"), ("文", "文", "Wen", "Wen"), ("國", "国", "Kuo", "Guo"),
    ("家", "家", "Chia", "Jia"), ("豪", "豪", "Hao", "Hao"), ("欣", "欣", "Hsin", "Xin"),
    ("秀", "秀", "Hsiu", "Xiu"), ("君", "君", "Chun", "Jun"), ("宇", "宇", "Yu", "Yu"),
    ("翔", "翔", "Hsiang", "Xiang"), ("庭", "庭", "Ting", "Ting"), ("冠", "冠", "Kuan", "Guan"),
    ("承", "承", "Cheng", "Cheng"), ("柏", "柏", "Po", "Bo"), ("彥", "彦", "Yen", "Yan"),
    ("瑋", "玮", "Wei", "Wei"), ("鈺", "钰", "Yu", "Yu"), ("涵", "涵", "Han", "Han"),
    ("安", "安", "An", "An"), ("平", "平", "Ping", "Ping"), ("正", "正", "Cheng", "Zheng"),
    ("德", "德", "Te", "De"), ("立", "立", "Li", "Li"), ("信", "信", "Hsin", "Xin"),
]
EN_FIRST = [
    "Kevin", "Jason", "Eric", "Allen", "Vincent", "Jack", "Tony", "Ryan", "Peter",
    "Amy", "Grace", "Irene", "Joyce", "Vivian", "Sandy", "Wendy", "Cindy", "Tina", "Emily",
]
VN_SURNAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ"]
VN_MIDDLE = ["Văn", "Thị", "Minh", "Đức", "Thanh", "Ngọc", "Quốc", "Hữu"]
VN_GIVEN = ["An", "Bình", "Cường", "Dũng", "Hà", "Hải", "Hạnh", "Hiếu", "Hoa", "Hùng", "Hương", "Khánh",
            "Lan", "Linh", "Long", "Mai", "Nam", "Ngân", "Phúc", "Quang", "Sơn", "Tâm", "Thảo", "Trang", "Tuấn", "Vy"]
TH_GIVEN = ["Somchai", "Somsak", "Suda", "Nattapong", "Kanya", "Pimchanok", "Arthit", "Wichai", "Siriporn",
            "Anong", "Chaiwat", "Kittisak", "Ploy", "Thanakorn", "Waraporn", "Prasert", "Jirapat", "Nattaya"]
TH_SURNAMES = ["Srisuk", "Wongsakul", "Chaiyaporn", "Rattanakorn", "Boonmee", "Thongchai", "Saelim",
               "Phromma", "Kaewkla", "Sukprasert", "Inthasorn", "Charoenwong"]
JP_GIVEN = ["Haruto", "Yuki", "Takeshi", "Kenji", "Aiko", "Yui", "Daisuke", "Naoki", "Emi", "Sakura", "Ren", "Mio"]
JP_SURNAMES = ["Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto", "Nakamura", "Kobayashi", "Kato"]
US_GIVEN = ["Michael", "Sarah", "James", "Jennifer", "Robert", "Jessica", "Daniel", "Ashley", "Matthew",
            "Laura", "Brian", "Megan", "Steven", "Rachel", "Mark", "Nicole"]
US_SURNAMES = ["Smith", "Johnson", "Brown", "Miller", "Davis", "Garcia", "Wilson", "Anderson", "Thomas",
               "Moore", "Martin", "Clark", "Lewis", "Walker"]
DE_GIVEN = ["Lukas", "Anna", "Jonas", "Lea", "Felix", "Laura", "Maximilian", "Sophie", "Tobias", "Julia", "Stefan", "Katrin"]
DE_SURNAMES = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Hoffmann", "Koch"]


def ascii_fold(s: str) -> str:
    s = s.replace("Đ", "D").replace("đ", "d").replace("ß", "ss")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def person(rng: random.Random, country: str) -> dict:
    """回傳 display（Entra displayName，用當地寫法）、given / surname（羅馬拼音）、email_local。"""
    if country in ("TW", "CN"):
        sur = rng.choice(CN_SURNAMES)
        g1, g2 = rng.sample(CN_GIVEN, 2)
        if country == "TW":
            display = sur[0] + g1[0] + g2[0]
            given = f"{g1[2]}-{g2[2].lower()}"
            surname = sur[2]
            if rng.random() < 0.45:
                given = rng.choice(EN_FIRST)
        else:
            display = sur[1] + g1[1] + g2[1]
            given = g1[3] + g2[3].lower()
            surname = sur[3]
        local = f"{given}.{surname}"
    elif country == "VN":
        sur, mid, giv = rng.choice(VN_SURNAMES), rng.choice(VN_MIDDLE), rng.choice(VN_GIVEN)
        display = f"{sur} {mid} {giv}"
        given, surname = giv, sur
        local = f"{giv}.{sur}"
    else:
        pools = {"TH": (TH_GIVEN, TH_SURNAMES), "JP": (JP_GIVEN, JP_SURNAMES),
                 "US": (US_GIVEN, US_SURNAMES), "DE": (DE_GIVEN, DE_SURNAMES)}[country]
        given, surname = rng.choice(pools[0]), rng.choice(pools[1])
        display = f"{given} {surname}"
        local = f"{given}.{surname}"
    local = ascii_fold(local).lower().replace("-", "").replace(" ", "")
    return {"display": display, "given": given, "surname": surname, "en_name": ascii_fold(f"{given} {surname}"), "email_local": local}
