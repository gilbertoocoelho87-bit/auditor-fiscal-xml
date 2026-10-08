import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io
import os
import re
from datetime import datetime

# ============================================================ #
# AUDITOR FISCAL XML - V2
# ============================================================ #
st.set_page_config(
    page_title="Auditor Fiscal de Divergências",
    page_icon="📊",
    layout="wide"
)
st.title("📊 Auditor Fiscal de Divergências - V2")
st.caption(
    "Leitura de NF-e XML + auditoria automática de inconsistências "
    "e comparação com base tributária automatizada."
)

# ============================================================ #
# CONSTANTES
# ============================================================ #
UF_CODIGOS = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF"
}
UFS = sorted(UF_CODIGOS.values())

COLUNAS_BASE = [
    "UF_ORIGEM", "UF_DESTINO", "NCM", "CEST", "CFOP", "REGIME", "ICMS", "ICMS_ST", 
    "DIFAL", "FCP", "PIS_COFINS", "IPI", "IBS_CBS", "ALIQUOTA_ICMS", "MVA", 
    "REDUCAO_BASE", "CODIGO_BENEFICIO", "LEGISLACAO", "FUNDAMENTO_LEGAL", "OBSERVACAO"
]
ARQUIVO_BASE = "base_tributaria.csv"

# ============================================================ #
# FUNÇÕES BÁSICAS
# ============================================================ #
def normalizar(valor):
    return str(valor or "").strip()

def somente_digitos(valor):
    return re.sub(r"\D", "", normalizar(valor))

def normalizar_ncm(valor):
    v = somente_digitos(valor)
    return v.zfill(8) if v else ""

def normalizar_cest(valor):
    return somente_digitos(valor)

def normalizar_cfop(valor):
    return somente_digitos(valor)

def tag_final(elemento):
    return elemento.tag.split("}")[-1]

def texto(elemento):
    return normalizar(elemento.text if elemento is not None else "")

def encontrar(parent, nome):
    for el in parent.iter():
        if tag_final(el) == nome:
            return el
    return None

def encontrar_texto(parent, nome):
    return texto(encontrar(parent, nome))

# ============================================================ #
# GERAÇÃO AUTOMÁTICA DA BASE LEGAL (MONOFÁSICOS E ST)
# ============================================================ #
def gerar_e_alimentar_base_nacional():
    """Gera regras pré-moldadas baseadas na Lei Federal de Monofásicos e regras macro de ST"""
    regras = []
    
    # 1. PIS/COFINS MONOFÁSICO (Principais Grupos Nacionais)
    grupos_monofasicos = [
        {"NCM_START": "3003", "DESC": "Medicamentos", "LEI": "Lei nº 10.147/2000"},
        {"NCM_START": "3004", "DESC": "Medicamentos para medicina humana/veterinária", "LEI": "Lei nº 10.147/2000"},
        {"NCM_START": "3303", "DESC": "Perfumes e águas-de-colônia", "LEI": "Lei nº 10.147/2000"},
        {"NCM_START": "3304", "DESC": "Produtos de beleza ou de maquilagem", "LEI": "Lei nº 10.147/2000"},
        {"NCM_START": "3305", "DESC": "Produtos para o cabelo", "LEI": "Lei nº 10.147/2000"},
        {"NCM_START": "3307", "DESC": "Produtos para barbear, desodorantes", "LEI": "Lei nº 10.147/2000"},
        {"NCM_START": "8702", "DESC": "Veículos automóveis para transporte de 10 pessoas ou mais", "LEI": "Lei nº 10.485/2002"},
        {"NCM_START": "8703", "DESC": "Automóveis de passageiros e outros veículos", "LEI": "Lei nº 10.485/2002"},
        {"NCM_START": "4011", "DESC": "Pneumáticos novos de borracha", "LEI": "Lei nº 10.485/2002"},
        {"NCM_START": "2201", "DESC": "Águas minerais e águas gaseificadas", "LEI": "Lei nº 10.833/2003"},
        {"NCM_START": "2202", "DESC": "Águas adicionadas de açúcar, refrigerantes", "LEI": "Lei nº 10.833/2003"},
        {"NCM_START": "2203", "DESC": "Cervejas de malte", "LEI": "Lei nº 10.833/2003"},
        {"NCM_START": "2710", "DESC": "Combustíveis e óleos minerais", "LEI": "Lei nº 9.718/1998 / LC 192/22"}
    ]
    
    # Criar mapeamento simplificado expandindo para regras na tabela
    for grupo in grupos_monofasicos:
        regras.append({
            "UF_ORIGEM": "", "UF_DESTINO": "", "NCM": grupo["NCM_START"], "CEST": "", "CFOP": "",
            "REGIME": "", "ICMS": "", "ICMS_ST": "", "DIFAL": "", "FCP": "",
            "PIS_COFINS": "MONOFÁSICO", "IPI": "", "IBS_CBS": "", "ALIQUOTA_ICMS": "", "MVA": "",
            "REDUCAO_BASE": "", "CODIGO_BENEFICIO": "", "LEGISLACAO": "Federal",
            "FUNDAMENTO_LEGAL": grupo["LEI"], "OBSERVACAO": f"Grupo Monofásico: {grupo['DESC']}"
        })
        
    # 2. DIRETRIZES DE ICMS ST (Convênio ICMS 142/18) - Segmentos clássicos
    segmentos_st = [
        {"NCM_START": "2203", "DESC": "Cervejas, Chopes e afins"},
        {"NCM_START": "2402", "DESC": "Cigarros e sucedâneos de tabaco"},
        {"NCM_START": "2710", "DESC": "Combustíveis e lubrificantes"},
        {"NCM_START": "4011", "DESC": "Pneumáticos e Câmaras de ar"},
        {"NCM_START": "3004", "DESC": "Produtos farmacêuticos de uso humano"},
        {"NCM_START": "3304", "DESC": "Cosméticos e Perfumaria"}
    ]
    
    for seg in segmentos_st:
        regras.append({
            "UF_ORIGEM": "", "UF_DESTINO": "", "NCM": seg["NCM_START"], "CEST": "", "CFOP": "",
            "REGIME": "", "ICMS": "ST", "ICMS_ST": "SIM", "DIFAL": "", "FCP": "",
            "PIS_COFINS": "", "IPI": "", "IBS_CBS": "", "ALIQUOTA_ICMS": "", "MVA": "",
            "REDUCAO_BASE": "", "CODIGO_BENEFICIO": "", "LEGISLACAO": "Convênio ICMS 142/18",
            "FUNDAMENTO_LEGAL": "Artigos correspondentes ao segmento no Convênio ICMS 142/18",
            "OBSERVACAO": f"Segmento passível de ST nacionalmente: {seg['DESC']}"
        })
        
    df_inicial = pd.DataFrame(regras, columns=COLUNAS_BASE)
    df_inicial.to_csv(ARQUIVO_BASE, index=False, sep=";", encoding="utf-8-sig")

def carregar_base():
    if not os.path.exists(ARQUIVO_BASE):
        gerar_e_alimentar_base_nacional()
    try:
        df = pd.read_csv(ARQUIVO_BASE, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
        if df.empty:
            gerar_e_alimentar_base_nacional()
            df = pd.read_csv(ARQUIVO_BASE, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
    except Exception:
        return pd.DataFrame(columns=COLUNAS_BASE)
    
    for col in COLUNAS_BASE:
        if col not in df.columns:
            df[col] = ""
    return df[COLUNAS_BASE]

BASE = carregar_base()

# ============================================================ #
# LEITURA DA NF-E
# ============================================================ #
def identificar_uf_origem(root):
    cuf = encontrar_texto(root, "cUF")
    return UF_CODIGOS.get(cuf, "")

def identificar_uf_destino(root):
    dest = None
    for el in root.iter():
        if tag_final(el) == "dest":
            dest = el
            break
    if dest is not None:
        return encontrar_texto(dest, "UF")
    return ""

def extrair_dados_nfe(root):
    return {
        "NF-e": encontrar_texto(root, "nNF"),
        "Série": encontrar_texto(root, "serie"),
        "Data Emissão": encontrar_texto(root, "dhEmi") or encontrar_texto(root, "dEmi"),
        "Natureza": encontrar_texto(root, "natOp"),
        "UF Origem": identificar_uf_origem(root),
        "UF Destino": identificar_uf_destino(root),
        "CNPJ Emitente": somente_digitos(encontrar_texto(root, "CNPJ")),
    }

# ============================================================ #
# EXTRAÇÃO DOS ITENS
# ============================================================ #
def extrair_itens(root):
    itens = []
    for det in root.iter():
        if tag_final(det) != "det":
            continue
        prod = None
        imposto = None
        for filho in det:
            nome = tag_final(filho)
            if nome == "prod":
                prod = filho
            elif nome == "imposto":
                imposto = filho
        if prod is None:
            continue
            
        ncm = normalizar_ncm(encontrar_texto(prod, "NCM"))
        cest = normalizar_cest(encontrar_texto(prod, "CEST"))
        cfop = normalizar_cfop(encontrar_texto(prod, "CFOP"))
        
        item = {
            "Item": det.attrib.get("nItem", ""),
            "Produto": encontrar_texto(prod, "xProd"),
            "NCM": ncm,
            "CEST": cest,
            "CFOP": cfop,
            "cProd": encontrar_texto(prod, "cProd"),
            "Quantidade": encontrar_texto(prod, "qCom"),
            "Valor Unitário": encontrar_texto(prod, "vUnCom"),
            "Valor Produto": encontrar_texto(prod, "vProd"),
            "CST ICMS": "", "CSOSN ICMS": "", "Origem ICMS": "", "Modalidade BC ICMS": "",
            "Alíquota ICMS": "", "Valor ICMS": "", "CST PIS": "", "CST COFINS": "", "CST IPI": "",
        }
        
        # ICMS
        if imposto is not None:
            for el in imposto.iter():
                nome = tag_final(el)
                if nome == "orig":
                    item["Origem ICMS"] = texto(el)
                elif nome == "CST" and not item["CST ICMS"]:
                    item["CST ICMS"] = texto(el)
                elif nome == "CSOSN":
                    item["CSOSN ICMS"] = texto(el)
                elif nome == "modBC":
                    item["Modalidade BC ICMS"] = texto(el)
                elif nome == "pICMS":
                    item["Alíquota ICMS"] = texto(el)
                elif nome == "vICMS":
                    item["Valor ICMS"] = texto(el)
                    
        # PIS / COFINS / IPI
        for el in det.iter():
            tag = tag_final(el)
            if tag in ["PIS", "COFINS", "IPI"]:
                for filho in el.iter():
                    if tag_final(filho) == "CST":
                        item[f"CST {tag}"] = texto(filho)
