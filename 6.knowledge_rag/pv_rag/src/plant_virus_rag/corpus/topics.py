"""Plant virus topic configuration for OpenAlex paper harvesting.

Reuses the TopicConfig model from neblab_rag.corpus.topics.
"""

from neblab_rag.corpus.topics import TopicConfig

PLANT_VIRUS_TOPICS: list[TopicConfig] = [
    TopicConfig(
        id="plant_virus",
        label_zh="植物病毒",
        label_en="Plant viruses",
        priority="must",
        fulltext_quota=500,
        fulltext_zh=200,
        fulltext_en=300,
        zh_keywords=[
            "植物病毒",
            "植物病原病毒",
            "病毒病害",
            "植物抗病毒",
            "病毒检测",
            "植物病毒病",
        ],
        en_keywords=[
            "plant virus",
            "tospovirus",
            "potyvirus",
            "geminivirus",
            "tobamovirus",
            "plant virology",
            "virus transmission",
            "viral plant disease",
            "plant virus vector",
            "cucumovirus",
            "potexvirus",
            "closterovirus",
            "comovirus",
            "nucleorhabdovirus",
            "ilarvirus",
            "nepovirus",
            "tobravirus",
            "carlavirus",
            "furovirus",
            "hordeivirus",
            "luteovirus",
            "polerovirus",
            "begomovirus",
            "orthotospovirus",
            "plant RNA virus",
            "plant DNA virus",
            "virus host interaction plant",
            "plant virus epidemiology",
        ],
    ),
]

TOPIC_BY_ID: dict[str, TopicConfig] = {t.id: t for t in PLANT_VIRUS_TOPICS}
