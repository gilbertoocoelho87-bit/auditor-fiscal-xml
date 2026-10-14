import argparse
import csv
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import streamlit as st
import pandas as pd

# Configuração da página do Streamlit (deve ser a primeira chamada Streamlit)
st.set_page_config(page_title="Auditor Fiscal XML", layout="wide")

NS = {"nfe": "http://portalfiscal.inf.br"}

# ------------------------------------------------------------------ #
# Auxiliares de leitura do XML
# ------------------------------------------------------------------ #
def tx(el, *caminhos):
    """Retorna o texto do primeiro caminho encontrado."""
    for c in caminhos:
        e = el.find(c, NS)
        if e is not None and e.text:
            return e.text.strip()
    return None

def num(el, *caminhos):
    t = tx(el, *caminhos)
    try:
        return float(t.replace(",", ".")) if t is not None else None
    except ValueError:
        return None

def icms_info(imposto):
    """Extrai dados do grupo ICMS (independe do CST usado)."""
    icms = imposto.find("nfe:ICMS", NS)
    if icms is None or len(icms) == 0:
        return {}
    g = icms[0]
    cst = tx(g, "nfe:CST", "nfe:CSOSN")
    tag = g.tag.split("}")[-1]
    return {
        "grupo": tag, "cst": cst,
        "orig": tx(g, "nfe:orig"),
        "pICMS": num(g, "nfe:pICMS"),
        "vBC": num(g, "nfe:vBC"),
        "vICMS": num(g, "nfe:vICMS"),
        "pRedBC": num(g, "nfe:pRedBC"),
        "pRedBCST": num(g, "nfe:pRedBCST"),
        "vBCST": num(g, "nfe:vBCST"),
        "pICMSST": num(g, "nfe:pICMSST"),
        "vICMSST": num(g, "nfe:vICMSST"),
        "vBCSTRet": num(g, "nfe:vBCSTRet"),
        "pST": num(g, "nfe:pST"),
        "vICMSSTRet": num(g, "nfe:vICMSSTRet"),
        "vICMSSubstituto": num(g, "nfe:vICMSSubstituto"),
        "vBCFCPST": num(g, "nfe:vBCFCPST"),
        "pFCPST": num(g, "nfe:pFCPST"),
        "vFCPST": num(g, "nfe:vFCPST"),
        "motDesICMS": tx(g, "nfe:motDesICMS"),
        # Partilha / EC 87-2015 (NF-e 4.00)
        "vBCUFDest": num(g, "nfe:vBCUFDest"),
        "pFCPUFDest": num(g, "nfe:pFCPUFDest"),
        "pICMSUFDest": num(g, "nfe:pICMSUFDest"),
        "pICMSInter": num(g, "nfe:pICMSInter"),
        "pICMSInterPart": num(g, "nfe:pICMSInterPart"),
        "vFCPUFDest": num(g, "nfe:vFCPUFDest"),
        "vICMSUFDest": num(g, "nfe:vICMSUFDest"),
        "vICMSUFRemet": num(g, "nfe:vICMSUFRemet"),
    }

def pis_cofins(imposto, tag):
    g = imposto.find(f"nfe:{tag}", NS)
    if g is None or len(g) == 0:
        return {"cst": None, "p": None, "v": None}
    s = g[0]
    return {"cst": tx(s, "nfe:CST"),
            "p": num(s, f"nfe:p{tag}"),
            "v": num(s, f"nfe:v{tag}")}

# ------------------------------------------------------------------ #
# Leitura de um XML (aceita nfeProc ou NFe)
# ------------------------------------------------------------------ #
def ler_nfe(xml_bytes, nome_arquivo):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return {"arquivo": nome_arquivo, "erro_xml": f"XML inválido: {e}",
                "emitente": "-", "chave": "-", "numero": "-", "uf_origem": "-",
                "uf_destino": "-", "produtos": [], "consumidor_final": None}

    inf = root.find(".//nfe:infNFe", NS)
    chave_tag = inf.get("Id") if inf is not None else None
    chave = chave_tag.replace("NFe", "") if chave_tag else None

    ide = root.find(".//nfe:ide", NS)
    num_nf = tx(ide, "nfe:nNF") if ide is not None else None
    serie = tx(ide, "nfe:serie") if ide is not None else None

    emit = root.find(".//nfe:emit", NS)
    emitente = tx(emit, "nfe:xNome") if emit is not None else None
    uf_emit = tx(emit, "nfe:enderEmit/nfe:UF") if emit is not None else None

    dest = root.find(".//nfe:dest", NS)
    uf_dest = tx(dest, "nfe:enderDest/nfe:UF") if dest is not None else None
    ind_ie_dest = tx(dest, "nfe:indIEDest") if dest is not None else None
    cons_final = tx(dest, "nfe:indFinal") if dest is not None else None

    produtos = []
    for i, det in enumerate(root.findall(".//nfe:det", NS), start=1):
        prod = det.find("nfe:prod", NS)
        imp = det.find("nfe:imposto", NS)
        ipi = imp.find("nfe:IPI", NS) if imp is not None else None
        produtos.append({
            "item": i,
            "codigo": tx(prod, "nfe:cProd") if prod is not None else None,
            "descricao": tx(prod, "nfe:xProd") if prod is not None else None,
            "ncm": tx(prod, "nfe:NCM") if prod is not None else None,
            "cfop": tx(prod, "nfe:CFOP") if prod is not None else None,
            "cest": tx(prod, "nfe:CEST") if prod is not None else None,
            "qtd": num(prod, "nfe:qCom") if prod is not None else None,
            "v_unit": num(prod, "nfe:vUnCom") if prod is not None else None,
            "ipi_cst": tx(ipi, ".//nfe:CST") if ipi is not None else None,
            "icms": icms_info(imp) if imp is not None else {},
            "pis": pis_cofins(imp, "PIS") if imp is not None else {},
            "cofins": pis_cofins(imp, "COFINS") if imp is not None else {},
        })

    return {"arquivo": nome_arquivo, "erro_xml": None,
            "chave": chave, "numero": num_nf, "serie": serie,
            "emitente": emitente, "uf_origem": uf_emit, "uf_destino": uf_dest,
            "ind_ie_dest": ind_ie_dest, "consumidor_final": cons_final,
            "produtos": produtos}

# ------------------------------------------------------------------ #
# MOTOR DE REGRAS
# ------------------------------------------------------------------ #
def _regra(base, ncm):
    """Localiza o item da base mais específico para o NCM (8→2 dígitos)."""
    for tam in (8, 7, 6, 4, 2):
        p = (ncm or "")[:tam]
        if p in base:
            return p, base[p]
    return None, None

CST_ST_ICMS = {"10", "30", "70", "90", "201", "202", "203", "500", "900"}
CST_ST_CSOSN = {"201", "202", "203", "500", "900"}

def avaliar_nota(nota, base, achados):
    def add(regra, sev, item, prod, ncm, problema, correcao, lei):
        achados.append({
            "arquivo": nota["arquivo"], "chave": nota.get("chave"),
            "numero": nota.get("numero"), "serie": nota.get("serie"),
            "emitente": nota.get("emitente"),
            "uf_origem": nota.get("uf_origem"), "uf_destino": nota.get("uf_destino"),
            "regra": regra, "severidade": sev, "item": item,
            "produto": prod, "ncm": ncm,
            "problema_identificado": problema,
            "correcao_recomendada": correcao,
            "base_legal": lei,
        })

    if nota.get("erro_xml"):
        add("E-XML", "ERRO", "-", "-", "-", nota["erro_xml"],
            "Verificar arquivo, estrutura e schema da NF-e.",
            "Manual de Orientação do Contribuinte - MOC NF-e")
        return

    for p in nota["produtos"]:
        ncm, cfop, item = p["ncm"], p["cfop"], p["item"]
        icms, pis, cofins = p["icms"], p["pis"], p["cofins"]

        # R-01: NCM ausente/mal formado
        if not ncm or not re.fullmatch(r"\d{8}", ncm):
            add("R-01", "ERRO", item, p["descricao"], ncm,
                "NCM ausente ou com formato inválido (deve ter 8 dígitos).",
                "Informar NCM de 8 dígitos, conforme TIPI.",
                "Lei 12.865/2013 art. 2º; Decreto 7.660/2011; TIPI")

        ncm_c, dados = _regra(base, ncm)

        # R-02: NCM não cadastrado na base
        if ncm and dados is None:
            add("R-02", "AVISO", item, p["descricao"], ncm,
                "NCM não localizado na base tributária de referência.",
                "Verificar se o NCM está ativo na TIPI ou se há erro de digitação.",
                "Tabela de Incidência do Imposto sobre Produtos Industrializados - TIPI")

# ------------------------------------------------------------------ #
# INTERFACE EM STREAMLIT
# ------------------------------------------------------------------ #
st.title("📊 Auditor Fiscal de XMLs da NF-e")
st.markdown("Faça o upload de arquivos `.xml` ou arquivos compactados `.zip` para auditar inconsistências fiscais de NCM, CST e CFOP.")

# Base de simulação temporária (Substitua ou integre com seu banco futuramente)
base_tributaria_exemplo = {
    "61091000": {"aliquota": 0.18},
    "62043200": {"aliquota": 0.18}
}

arquivos_carregados = st.file_uploader(
    "Arraste ou selecione os arquivos XML / ZIP aqui", 
    type=["xml", "zip"], 
    accept_multiple_files=True
)

if arquivos_carregados:
    lista_arquivos_processar = []
    
    for arquivo in arquivos_carregados:
        nome = arquivo.name
        conteudo = arquivo.read()
        
        if nome.lower().endswith(".xml"):
            lista_arquivos_processar.append((nome, conteudo))
        elif nome.lower().endswith(".zip"):
            try:
                import io
                with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                    for n in z.namelist():
                        if n.lower().endswith(".xml"):
                            lista_arquivos_processar.append((f"{nome}/{n}", z.read(n)))
            except Exception as e:
                st.error(f"Erro ao descompactar o arquivo ZIP '{nome}': {e}")

    st.info(f"🔍 {len(lista_arquivos_processar)} arquivo(s) XML carregados para análise.")
    
    if st.button("▶️ Executar Auditoria Fiscal"):
        alertas = []
        
        for nome_xml, bytes_xml in lista_arquivos_processar:
            dados_nota = ler_nfe(bytes_xml, nome_xml)
            avaliar_nota(dados_nota, base_tributaria_exemplo, alertas)
            
        if alertas:
            df_resultados = pd.DataFrame(alertas)
            st.success(f"🚨 Auditoria concluída! Foram encontradas {len(alertas)} inconformidades.")
            
            # Exibe os dados de maneira interativa na página
            st.dataframe(df_resultados)
            
            # Botão de download do relatório em formato CSV
