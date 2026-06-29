import re


TERM_WEIGHTS: dict[str, float] = {
    **dict.fromkeys(
        [
            "加热",
            "热处理",
            "固溶热处理",
            "预热段",
            "第一加热段",
            "第二加热段",
            "均热段",
            "炉膛",
            "炉膛压力",
            "排气温度",
            "烧嘴",
            "燃气",
            "天然气",
            "高炉煤气",
            "混合煤气",
            "氮气",
            "汽化冷却",
            "换热器",
            "蓄热室",
            "辐射管",
            "烟囱",
            "烟道闸阀",
            "热处理曲线",
            "加热速度曲线",
            "吨钢能耗",
            "热效率",
            "燃料单耗",
            "炉温制度",
            "板坯热渗",
            "板坯冷渗",
            "水梁",
            "固定梁",
            "活动梁",
            "支撑梁",
            "水封槽",
            "水梁黑印",
            "温差",
            "批料温差",
            "出炉批料温差",
            "筑炉",
            "焊接",
            "气割",
            "步进框架",
            "水平框架",
            "升降框架",
            "液压缸",
        ],
        3.0,
    ),
    **dict.fromkeys(
        [
            "步进炉",
            "辊底式炉",
            "环形炉",
            "推钢式加热炉",
            "均热炉",
            "退火炉",
            "淬火炉",
            "回火炉",
            "正火炉",
            "时效炉",
            "蓄热式加热炉",
            "钢坯",
            "板坯",
            "方坯",
            "圆坯",
            "钢锭",
            "锭块",
            "氧化铁皮",
            "送风机",
            "助燃风机",
            "业主经济性分析",
            "设计承包方经济性分析",
            "设计周期",
            "施工周期",
            "施工难点",
        ],
        2.5,
    ),
    **dict.fromkeys(
        [
            "炉拱",
            "炉门",
            "炉底机件",
            "炉辊",
            "炉喉",
            "炉鼻",
            "水冷集管",
            "循环管路",
            "密封室",
            "排烟烟道",
            "装钢机",
            "出钢机",
            "推钢机",
            "步进梁",
            "炉内辊道",
            "耐火材料",
            "耐火纤维",
            "重质浇筑料",
            "轻质浇筑料",
            "捣打料",
            "硅砖",
            "高铝砖",
            "刚玉砖",
            "镁碳砖",
            "耐火浇注料",
            "陶瓷纤维",
            "点火器",
            "长明灯",
            "调风挡板",
            "引射器",
            "烧嘴风箱",
            "热电偶",
            "PID 温控",
            "压力传感器",
            "流量仪表",
            "PLC 控制系统",
        ],
        2.0,
    ),
}

ORDERED_TERMS = sorted(TERM_WEIGHTS, key=len, reverse=True)


def normalize_term_text(text: str) -> str:
    return (text or "").lower().replace(" ", "")


def weighted_terms(text: str) -> dict[str, float]:
    normalized = normalize_term_text(text)
    return {term: weight for term, weight in TERM_WEIGHTS.items() if normalize_term_text(term) in normalized}


def weighted_term_score(text: str, keywords: list[str] | None = None) -> float:
    normalized = normalize_term_text(text)
    score = 0.0
    for term, weight in TERM_WEIGHTS.items():
        count = normalized.count(normalize_term_text(term))
        if count:
            score += weight * max(1, len(term) / 2) * count
    for keyword in keywords or []:
        if keyword and normalize_term_text(keyword) in normalized:
            score += max(1.0, len(keyword) / 3)
    return score


def weighted_query_terms(question: str) -> list[str]:
    return sorted(weighted_terms(question), key=lambda term: (-TERM_WEIGHTS[term], -len(term), term))


def protect_term_boundary(text: str, boundary: int) -> int:
    if boundary <= 0 or boundary >= len(text):
        return max(0, min(boundary, len(text)))
    for term in ORDERED_TERMS:
        start = max(0, boundary - len(term) + 1)
        end = min(len(text), boundary + len(term))
        window = text[start:end]
        for match in re.finditer(re.escape(term), window, flags=re.IGNORECASE):
            term_start = start + match.start()
            term_end = start + match.end()
            if term_start < boundary < term_end:
                return term_end
    return boundary


def term_protected_chunks(text: str, chunk_size: int = 1800, overlap: int = 180) -> list[str]:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(compact):
        end = protect_term_boundary(compact, min(len(compact), start + chunk_size))
        if end <= start:
            end = min(len(compact), start + chunk_size)
        chunks.append(compact[start:end].strip())
        if end >= len(compact):
            break
        start = max(end - overlap, start + 1)
    anchors = []
    for term, weight in TERM_WEIGHTS.items():
        if weight < 3.0:
            continue
        normalized_term = normalize_term_text(term)
        normalized_text = normalize_term_text(compact)
        position = normalized_text.find(normalized_term)
        if position >= 0:
            anchors.append(compact[max(0, position - 500) : min(len(compact), position + len(term) + 500)].strip())
    return chunks + [anchor for anchor in anchors if anchor and anchor not in chunks]
