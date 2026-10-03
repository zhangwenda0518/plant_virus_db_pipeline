"""Seven research topics with keyword sets and full-text quotas.

Quotas come from the spec §3.2 (Plan B / 2500 fulltext target).
v1 (this Plan) only uses ``zh_keywords`` + ``en_keywords`` for OpenAlex
metadata harvesting; ``fulltext_*`` fields are reserved for Plan 2.
"""

from pydantic import BaseModel, Field


class TopicConfig(BaseModel):
    id: str
    label_zh: str
    label_en: str
    priority: str  # "must" or "want"
    fulltext_quota: int
    fulltext_zh: int
    fulltext_en: int
    zh_keywords: list[str] = Field(default_factory=list)
    en_keywords: list[str] = Field(default_factory=list)


TOPICS: list[TopicConfig] = [
    TopicConfig(
        id="desertification",
        label_zh="荒漠化监测/机理（含防沙治沙总论）",
        label_en="Desertification monitoring & mechanisms",
        priority="must",
        fulltext_quota=550,
        fulltext_zh=300,
        fulltext_en=250,
        zh_keywords=["荒漠化", "沙漠化", "沙化", "防沙", "治沙"],
        en_keywords=["desertification", "land degradation", "sand control", "sand stabilization"],
    ),
    TopicConfig(
        id="shelterbelt",
        label_zh="三北防护林/农田防护林",
        label_en="Shelterbelt forests",
        priority="must",
        fulltext_quota=500,
        fulltext_zh=350,
        fulltext_en=150,
        zh_keywords=["三北防护林", "农田防护林", "防护林体系", "三北工程"],
        en_keywords=["shelterbelt", "windbreak", "Three-North", "protective forest"],
    ),
    TopicConfig(
        id="horqin_otindag",
        label_zh="科尔沁/浑善达克沙地",
        label_en="Horqin & Otindag sandlands",
        priority="must",
        fulltext_quota=450,
        fulltext_zh=380,
        fulltext_en=70,
        zh_keywords=["科尔沁沙地", "浑善达克沙地", "奥都格沙地", "内蒙古东部沙地"],
        en_keywords=["Horqin", "Hunshandake", "Otindag", "Inner Mongolia sandland"],
    ),
    TopicConfig(
        id="lidar_uav",
        label_zh="无人机/LiDAR 植被遥感",
        label_en="UAV & LiDAR vegetation remote sensing",
        priority="want",
        fulltext_quota=300,
        fulltext_zh=100,
        fulltext_en=200,
        zh_keywords=["无人机", "激光雷达", "LiDAR", "UAV"],
        en_keywords=["UAV", "LiDAR", "drone", "airborne laser scanning"],
    ),
    TopicConfig(
        id="forest_grass",
        label_zh="林草生态系统结构与功能",
        label_en="Forest-grassland ecosystem structure & function",
        priority="want",
        fulltext_quota=250,
        fulltext_zh=150,
        fulltext_en=100,
        zh_keywords=["林草生态", "林分结构", "乔灌草", "草原生态"],
        en_keywords=["forest grassland", "stand structure", "tree shrub grass"],
    ),
    TopicConfig(
        id="soil_water_dryland",
        label_zh="水土保持/草地退化/干旱区生态",
        label_en="Soil-water conservation, grassland degradation, dryland ecology",
        priority="want",
        fulltext_quota=250,
        fulltext_zh=150,
        fulltext_en=100,
        zh_keywords=["水土保持", "草地退化", "干旱区", "退化草地"],
        en_keywords=[
            "soil and water conservation",
            "grassland degradation",
            "drylands",
            "arid ecology",
        ],
    ),
    TopicConfig(
        id="multi_system_coupling",
        label_zh="山水林田湖草沙系统耦合",
        label_en="Mountain-river-forest-farmland-lake-grassland-sand multi-system coupling",
        priority="want",
        fulltext_quota=200,
        fulltext_zh=180,
        fulltext_en=20,
        zh_keywords=["山水林田湖草沙", "多系统耦合", "生态系统耦合"],
        en_keywords=[
            "mountain river forest farmland lake grassland sand",
            "ecosystem coupling China",
        ],
    ),
]


TOPIC_BY_ID: dict[str, TopicConfig] = {t.id: t for t in TOPICS}
