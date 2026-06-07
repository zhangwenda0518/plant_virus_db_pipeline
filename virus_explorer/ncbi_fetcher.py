import io
import re
import pandas as pd
from Bio import Entrez
from Bio import SeqIO

# 填写有效的邮箱以遵循 NCBI 的 API 使用政策
Entrez.email = "plantvirus_viewer@example.com"


def search_ncbi_sequences(organism, countries, start_year, end_year, retmax=500):
    """
    通过 Entrez.esearch 获取指定筛选条件下的 NCBI 核苷酸序列 Accession 列表
    """
    country_queries = [f'"{country}"[Geo_Loc]' for country in countries]
    country_term = f"({' OR '.join(country_queries)})" if country_queries else ""

    query = f'("{organism}"[Organism] OR "{organism}"[All Fields]) AND "virus"[All Fields]'
    if country_term:
        query += f" AND {country_term}"
    query += f" AND {start_year}:{end_year}[DP]"

    print(f"NCBI Search Query: {query}")
    try:
        handle = Entrez.esearch(db="nucleotide", term=query, retmax=retmax, idtype="acc")
        record = Entrez.read(handle)
        handle.close()
        return record.get("IdList", [])
    except Exception as e:
        print(f"NCBI Search Error: {e}")
        return []


def fetch_and_parse_records(id_list, cp_keywords=None):
    """
    使用 Bio.SeqIO 从 GenBank 纯文本数据中精准流式提取元数据及目标 CDS 序列。
    该方法能够处理复杂的互补链（Complement）以及外显子拼接（Join）情况。
    """
    if not id_list:
        return pd.DataFrame()

    batch_size = 50
    parsed_data = []

    for i in range(0, len(id_list), batch_size):
        batch_ids = id_list[i:i+batch_size]
        try:
            # 请求 GenBank 文本格式 (gb)
            handle = Entrez.efetch(db="nucleotide", id=batch_ids, rettype="gb", retmode="text")
            raw_text = handle.read()
            handle.close()

            # 使用 SeqIO 解析文本流
            for record in SeqIO.parse(io.StringIO(raw_text), "genbank"):
                accession = record.id
                definition = record.description
                organism = record.annotations.get('organism', 'Unknown Virus')

                # 从 source 特征提取国家和采集年份
                country = 'Unknown'
                collection_date = 'Unknown'
                year = None

                for feature in record.features:
                    if feature.type == 'source':
                        if 'country' in feature.qualifiers:
                            country = feature.qualifiers['country'][0].split(':')[0].strip()
                        if 'collection_date' in feature.qualifiers:
                            collection_date = feature.qualifiers['collection_date'][0]
                            match = re.search(r'\b(20\d{2}|19\d{2})\b', collection_date)
                            if match:
                                year = int(match.group(1))

                # 回退机制：若无具体采集年份，提取 GenBank 序列创建日期
                if year is None and 'date' in record.annotations:
                    date_str = record.annotations['date']
                    match = re.search(r'\b(20\d{2}|19\d{2})\b', date_str)
                    if match:
                        year = int(match.group(1))

                # 提取特定 CDS 外壳蛋白序列 (自动解决 Join, Complement 坐标)
                cp_sequence = None
                if cp_keywords:
                    for feature in record.features:
                        if feature.type == 'CDS':
                            product = feature.qualifiers.get('product', [''])[0].lower()
                            gene = feature.qualifiers.get('gene', [''])[0].lower()

                            if any(kw.lower() in product or kw.lower() in gene for kw in cp_keywords):
                                try:
                                    cp_sequence = str(feature.location.extract(record.seq))
                                    break
                                except Exception as extract_err:
                                    print(f"Sequence extraction failed for {accession}: {extract_err}")

                parsed_data.append({
                    'Accession': accession,
                    'Definition': definition,
                    'Organism': organism,
                    'Country': country,
                    'CollectionDate': collection_date,
                    'Year': year if year else 'Unknown',
                    'FullSequenceLength': len(record.seq),
                    'CP_Sequence': cp_sequence if cp_sequence else 'Not Extracted'
                })
        except Exception as e:
            print(f"Batch processing error at index {i}: {e}")

    return pd.DataFrame(parsed_data)
