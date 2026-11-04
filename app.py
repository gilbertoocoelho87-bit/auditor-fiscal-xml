# -*- coding: utf-8 -*-
"""
AUDITOR FISCAL DE XML (NF-e) - em lote
--------------------------------------
Funcionalidades
  1. Análise em lote de XMLs de NF-e/NFC-e (upload múltiplo ou .zip)
  2. Conferência por NCM de:
       - Substituição Tributária (ST) por UF  (base CSV: dados/st_base.csv)
       - Produtos monofásicos (Tabelas 4.3.10 e 4.3.11 do SPED Contribuições)
                                              (base CSV: dados/monofasico.csv)
       - CFOP x CST/CSOSN x UF destino, alíquota de ICMS, PIS/COFINS, IPI
  3. Mostra o ERRO de emissão, o valor CORRETO e a LEGISLAÇÃO
  4. Consulta por NCM no formato "ficha" (estilo Econet)
  5. Exporta o resultado em Excel e PDF

IMPORTANTE
  As bases embutidas abaixo são SEMENTES (exemplos por prefixo de NCM).
  Para cobertura completa, importe as bases oficiais pela barra lateral:
    - Tabelas 4.3.10 / 4.3.11: baixe no portal do SPED (Receita Federal)
    - ST: Convênio ICMS 142/2018 (CEST) + protocolos/anexos de cada UF
  Colunas esperadas nos CSVs estão descritas na aba "Bases de dados".
"""

import io
import os
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Auditor Fiscal XML", page_icon="🧾", layout="wide")

DADOS_DIR = "dados"

# ---------------------------------------------------------------------------
# 1) TABELAS DE REFERÊNCIA
# ---------------------------------------------------------------------------
UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
       "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]

# Alíquota modal interna (sem FECP). CONFIRA a vigência - altere conforme necessário.
ALIQ_INTERNA = {
    "AC": 19, "AL": 20, "AM": 20, "AP": 18, "BA": 20.5, "CE": 20, "DF": 20, "ES": 17,
    "GO": 19, "MA": 22, "MG": 18, "MS": 17, "MT": 17, "PA": 19, "PB": 20, "PE": 20.5,
    "PI": 21, "PR": 19.5, "RJ": 20, "RN": 20, "RO": 19.5, "RR": 20, "RS": 17, "SC": 17,
    "SE": 19, "SP": 18, "TO": 20,
}
SUL_SUDESTE_SEM_ES = {"SP", "RJ", "MG", "PR", "SC", "RS"}

RICMS = {
    "PE": "RICMS/PE - Decreto nº 44.650/2017",
    "SP": "RICMS/SP - Decreto nº 45.490/2000",
    "RJ": "RICMS/RJ - Decreto nº 27.427/2000",
    "BA": "RICMS/BA - Decreto nº 13.780/2012",
    "CE": "RICMS/CE - Decreto nº 24.569/1997",
    "PR": "RICMS/PR - Decreto nº 7.871/2017",
    "RS": "RICMS/RS - Decreto nº 37.699/1997",
    "MG": "RICMS/MG - Decreto nº 48.589/2023",
}

def ricms(uf):
    return RICMS.get(uf, f"RICMS/{uf} (consultar legislação estadual vigente)")

# Sementes (prefixos de NCM). Substitua pelas bases oficiais via upload.
MONOFASICO_SEED = pd.DataFrame([
    # tabela, prefixo NCM, descrição, legislação
    ("4.3.10", "3003", "Medicamentos", "Lei 10.147/2000, art. 1º, I"),
    ("4.3.10", "3004", "Medicamentos", "Lei 10.147/2000, art. 1º, I"),
    ("4.3.10", "3303", "Perfumes e águas-de-colônia", "Lei 10.147/2000, art. 1º, II"),
    ("4.3.10", "3304", "Produtos de beleza/maquilagem", "Lei 10.147/2000, art. 1º, II"),
    ("4.3.10", "3305", "Preparações capilares", "Lei 10.147/2000, art. 1º, II"),
    ("4.3.10", "3307", "Desodorantes/outros de perfumaria", "Lei 10.147/2000, art. 1º, II"),
    ("4.3.10", "34011", "Sabonetes", "Lei 10.147/2000, art. 1º, II"),
    ("4.3.10", "960321", "Escovas de dentes", "Lei 10.147/2000, art. 1º, II"),
    ("4.3.10", "3306", "Higiene bucal", "Lei 10.147/2000, art. 1º, II"),
    ("4.3.10", "4011", "Pneus novos", "Lei 10.485/2002, art. 5º / Lei 10.865/2004"),
    ("4.3.10", "4013", "Câmaras de ar", "Lei 10.485/2002, art. 5º / Lei 10.865/2004"),
    ("4.3.10", "8702", "Veículos (ônibus)", "Lei 10.485/2002, art. 1º"),
    ("4.3.10", "8703", "Automóveis", "Lei 10.485/2002, art. 1º"),
    ("4.3.10", "8704", "Veículos de carga", "Lei 10.485/2002, art. 1º"),
    ("4.3.10", "8711", "Motocicletas", "Lei 10.485/2002, art. 1º"),
    ("4.3.10", "8708", "Autopeças (Anexos I/II)", "Lei 10.485/2002, art. 3º"),
    ("4.3.10", "8714", "Partes de motos (Anexos I/II)", "Lei 10.485/2002, art. 3º"),
    ("4.3.10", "2106906", "Preparações p/ elaboração de bebidas", "Lei 13.097/2015, arts. 14 a 20"),
    ("4.3.10", "2201", "Águas minerais/gaseificadas", "Lei 13.097/2015, arts. 14 a 20"),
    ("4.3.10", "2202", "Refrigerantes/bebidas não alcoólicas", "Lei 13.097/2015, arts. 14 a 20"),
    ("4.3.10", "2203", "Cervejas de malte", "Lei 13.097/2015, arts. 14 a 20"),
    ("4.3.11", "2710", "Gasolina/diesel/óleos (combustíveis)", "Lei 9.718/1998, art. 4º; Lei 9.990/2000"),
    ("4.3.11", "2711", "GLP/gás natural", "Lei 9.718/1998, art. 4º; Lei 11.909/2009"),
    ("4.3.11", "2207", "Etanol", "Lei 9.718/1998, art. 5º; Lei 11.727/2008"),
    ("4.3.11", "3826", "Biodiesel", "Lei 11.116/2005"),
], columns=["tabela", "ncm_prefixo", "descricao", "legislacao"])

_SEGMENTOS_ST = {
    "01 Autopeças": ["8708", "8409", "8483", "8511", "8512", "8714", "7007", "8707", "842123", "842131"],
    "02 Bebidas alcoólicas (exceto cerveja e chope)": ["2204", "2205", "2206", "2208"],
    "03 Cervejas, chopes, refrigerantes, águas e outras bebidas": ["2201", "2202", "2203", "2106906"],
    "04 Cigarros e outros derivados do fumo": ["2402", "2403"],
    "05 Cimentos": ["2523"],
    "06 Combustíveis e lubrificantes": ["2710", "2711", "2207", "3403", "3811", "3819"],
    "08 Ferramentas": ["8201", "8202", "8203", "8204", "8205", "8206", "8207", "8208", "8467"],
    "09 Lâmpadas, reatores e starter": ["8539", "850410"],
    "10 Materiais de construção e congêneres": ["3214", "3506", "3816", "3917", "3918", "3922", "3925",
                                                "4410", "4411", "4412", "4418", "6802", "6810", "6907",
                                                "6908", "6910", "7003", "7004", "7005", "7308", "7317",
                                                "7318", "7610", "8301", "8302", "8481", "9406"],
    "11 Materiais de limpeza": ["2828", "3401", "3402", "3405", "380894", "9603"],
    "12 Materiais elétricos": ["8535", "8536", "8537", "8538", "8544", "8545", "8546", "8547"],
    "13 Medicamentos de uso humano": ["3001", "3002", "3003", "3004", "3005", "3006"],
    "14 Papéis": ["4802", "4810", "4818", "4819", "4823"],
    "15 Pneumáticos": ["4011", "4012", "4013"],
    "16 Produtos alimentícios": ["1704", "1806", "1902", "1905"],
    "17 Eletrônicos, eletroeletrônicos e eletrodomésticos": ["8471", "8517", "8518", "8519", "8521", "8525",
                                                             "8527", "8528", "8506", "8507", "8509", "8516"],
    "18 Produtos de papelaria": ["4817", "4820", "9608", "9609", "3213"],
    "19 Perfumaria e higiene pessoal": ["3303", "3304", "3305", "3306", "3307", "340111", "960321"],
    "21 Rações para animais": ["2309"],
    "22 Sorvetes": ["2105"],
    "23 Tintas e vernizes": ["3208", "3209", "3210", "3212"],
    "24 Veículos automotores": ["8701", "8702", "8703", "8704", "8705", "8706"],
    "25 Veículos de duas e três rodas": ["8711"],
}
ST_SEED = pd.DataFrame(
    [("*", ncm, seg, "", f"Convênio ICMS 142/2018 - Segmento {seg}")
     for seg, ncms in _SEGMENTOS_ST.items() for ncm in ncms],
    columns=["uf", "ncm_prefixo", "segmento", "mva", "legislacao"])


def _ler_csv(nome, seed):
    caminho = os.path.join(DADOS_DIR, nome)
    if os.path.exists(caminho):
        try:
            return pd.read_csv(caminho, dtype=str, sep=None, engine="python").fillna("")
        except Exception:
            pass
    return seed.copy()


@st.cache_data
def carregar_bases():
    return _ler_csv("monofasico.csv", MONOFASICO_SEED), _ler_csv("st_base.csv", ST_SEED)


if "mono" not in st.session_state:
    st.session_state["mono"], st.session_state["st"] = carregar_bases()


def so_digitos(v):
    return "".join(c for c in str(v or "") if c.isdigit())


def buscar_mono(ncm):
    ncm = so_digitos(ncm)
    df = st.session_state["mono"]
    for _, r in df.iterrows():
        p = so_digitos(r["ncm_prefixo"])
        if p and ncm.startswith(p):
            return r
    return None


def buscar_st(ncm, uf):
    ncm = so_digitos(ncm)
    df = st.session_state["st"]
    so_uf = st.session_state.get("so_base_uf", False)
    achados = []
    for _, r in df.iterrows():
        p = so_digitos(r["ncm_prefixo"])
        if not (p and ncm.startswith(p)):
            continue
        if r["uf"] == uf or (not so_uf and r["uf"] in ("*", "")):
            achados.append((0 if r["uf"] == uf else 1, -len(p), r))
    achados.sort(key=lambda x: (x[0], x[1]))
    return achados[0][2] if achados else None


def uf_da_st(nota):
    esc = st.session_state.get("uf_st", "")
    return esc if esc in UFS else (nota["dest_uf"] or nota["emit_uf"])


def normaliza_st(df):
    """Aceita lista oficial de uma UF (só NCM, ou NCM+CEST) e completa as colunas."""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    for alt in ("ncm", "ncm/sh", "ncm_sh"):
        if alt in df.columns and "ncm_prefixo" not in df.columns:
            df = df.rename(columns={alt: "ncm_prefixo"})
    uf_esc = st.session_state.get("uf_st", "")
    if "uf" not in df.columns:
        df["uf"] = uf_esc if uf_esc in UFS else "*"
    for c in ("segmento", "mva", "legislacao"):
        if c not in df.columns:
            df[c] = ""
    df["ncm_prefixo"] = df["ncm_prefixo"].map(so_digitos)
    df["legislacao"] = [l or f"Lista de ST importada - {ricms(u)}" for l, u in zip(df["legislacao"], df["uf"])]
    return df.fillna("")


# ---------------------------------------------------------------------------
# 2) LEITURA DO XML
# ---------------------------------------------------------------------------
def _tag(el):
    return el.tag.split("}")[-1]


def _find(el, path):
    """Busca ignorando namespace. path = 'a/b/c'."""
    atual = [el]
    for parte in path.split("/"):
        prox = []
        for e in atual:
            prox += [c for c in e if _tag(c) == parte]
        atual = prox
        if not atual:
            return None
    return atual[0]


def _txt(el, path, default=""):
    e = _find(el, path) if el is not None else None
    return (e.text or "").strip() if e is not None and e.text else default


def _num(el, path):
    try:
        return float(_txt(el, path, "0") or 0)
    except ValueError:
        return 0.0


def parse_nfe(conteudo, nome):
    root = ET.fromstring(conteudo)
    inf = None
    for e in root.iter():
        if _tag(e) == "infNFe":
            inf = e
            break
    if inf is None:
        raise ValueError("Não é um XML de NF-e/NFC-e (infNFe não encontrado).")
    nota = {
        "arquivo": nome,
        "chave": inf.attrib.get("Id", "")[3:],
        "numero": _txt(inf, "ide/nNF"),
        "serie": _txt(inf, "ide/serie"),
        "emissao": _txt(inf, "ide/dhEmi") or _txt(inf, "ide/dEmi"),
        "tpNF": _txt(inf, "ide/tpNF"),
        "idDest": _txt(inf, "ide/idDest"),
        "emit_cnpj": _txt(inf, "emit/CNPJ"),
        "emit_nome": _txt(inf, "emit/xNome"),
        "emit_uf": _txt(inf, "emit/enderEmit/UF"),
        "crt": _txt(inf, "emit/CRT"),
        "dest_uf": _txt(inf, "dest/enderDest/UF"),
        "dest_ie": _txt(inf, "dest/indIEDest"),
    }
    itens = []
    for det in [c for c in inf if _tag(c) == "det"]:
        prod = _find(det, "prod")
        imp = _find(det, "imposto")
        icms_grp = None
        icms = _find(imp, "ICMS")
        if icms is not None and len(icms):
            icms_grp = list(icms)[0]
        pis_grp = None
        pis = _find(imp, "PIS")
        if pis is not None and len(pis):
            pis_grp = list(pis)[0]
        cof_grp = None
        cof = _find(imp, "COFINS")
        if cof is not None and len(cof):
            cof_grp = list(cof)[0]
        ipi = _find(imp, "IPI")
        ipi_grp = None
        if ipi is not None:
            for c in ipi:
                if _tag(c) in ("IPITrib", "IPINT"):
                    ipi_grp = c
        itens.append({
            "item": det.attrib.get("nItem", ""),
            "cProd": _txt(prod, "cProd"),
            "xProd": _txt(prod, "xProd"),
            "ncm": so_digitos(_txt(prod, "NCM")),
            "cest": _txt(prod, "CEST"),
            "cfop": _txt(prod, "CFOP"),
            "vProd": _num(prod, "vProd"),
            "orig": _txt(icms_grp, "orig"),
            "cst_icms": _txt(icms_grp, "CST") or _txt(icms_grp, "CSOSN"),
            "pICMS": _num(icms_grp, "pICMS"),
            "vICMS": _num(icms_grp, "vICMS"),
            "vICMSST": _num(icms_grp, "vICMSST"),
            "vBCST": _num(icms_grp, "vBCST"),
            "cst_pis": _txt(pis_grp, "CST"),
            "pPIS": _num(pis_grp, "pPIS"),
            "vPIS": _num(pis_grp, "vPIS"),
            "cst_cofins": _txt(cof_grp, "CST"),
            "pCOFINS": _num(cof_grp, "pCOFINS"),
            "vCOFINS": _num(cof_grp, "vCOFINS"),
            "cst_ipi": _txt(ipi_grp, "CST"),
            "pIPI": _num(ipi_grp, "pIPI"),
        })
    return nota, itens


# ---------------------------------------------------------------------------
# 3) MOTOR DE REGRAS
# ---------------------------------------------------------------------------
CST_ST = {"10", "30", "70", "201", "202", "203"}
CST_ST_RETIDA = {"60", "500"}
CST_TRIBUTADO_INTEGRAL = {"00", "20", "101", "102", "103", "900"}
CFOP_ST_SUBST = {"5401", "5403", "6401", "6403"}
CFOP_ST_RETIDA = {"5405", "6404"}


def aliq_interestadual(uf_o, uf_d, orig):
    if orig in ("1", "2", "3", "8"):
        return 4.0
    if uf_o in SUL_SUDESTE_SEM_ES and uf_d not in SUL_SUDESTE_SEM_ES:
        return 7.0
    return 12.0


def aliq_esperada(uf_o, uf_d, orig):
    if uf_o == uf_d:
        return float(ALIQ_INTERNA.get(uf_o, 0))
    return aliq_interestadual(uf_o, uf_d, orig)


def aliq_pc_correta():
    reg = st.session_state.get("regime_pc", "Cumulativo (Lucro Presumido)")
    return (0.65, 3.0) if reg.startswith("Cumulativo") else (1.65, 7.6)


def auditar_item(nota, it):
    erros = []
    uf_o, uf_d = nota["emit_uf"], nota["dest_uf"] or nota["emit_uf"]
    simples = True  # análise SEMPRE para empresas do Simples Nacional
    cst, cf = it["cst_icms"], it["cfop"]
    interna = uf_o == uf_d

    def add(campo, informado, correto, leg):
        erros.append({
            "Nota": nota["numero"], "Série": nota["serie"], "Item": it["item"],
            "Produto": it["xProd"][:60], "NCM": it["ncm"], "Campo": campo,
            "Informado": informado, "Correto": correto, "Gravidade": "ERRO",
            "Legislação": leg, "Arquivo": nota["arquivo"], "Chave": nota["chave"],
        })

    if nota["crt"] not in ("1", "2") and it["item"] in ("1", ""):
        add("CRT", nota["crt"] or "(vazio)", "1 - Simples Nacional (ou 2 - excesso de sublimite)",
            "LC 123/2006; leiaute NF-e (Ajuste SINIEF 07/2005)")

    # --- NCM ---
    if len(it["ncm"]) != 8:
        add("NCM", it["ncm"], "8 dígitos válidos (TIPI/NCM)", "Ajuste SINIEF 07/2005; Resolução Gecex vigente (NCM)")

    # --- CFOP x UF ---
    if cf and cf[0] in "56":
        if interna and cf[0] != "5":
            add("CFOP", cf, "Iniciar com 5 (operação interna)", "Ajuste SINIEF 07/2001 (Tabela de CFOP)")
        elif not interna and cf[0] != "6":
            add("CFOP", cf, "Iniciar com 6 (operação interestadual)", "Ajuste SINIEF 07/2001 (Tabela de CFOP)")

    # --- ICMS: ST x tributado normal (veredito pela base) ---
    uf_st = uf_da_st(nota)
    regra_st = buscar_st(it["ncm"], uf_st)
    if regra_st is not None:
        seg = regra_st["segmento"]
        leg = f"{regra_st['legislacao']} | {ricms(uf_st)} | LC 87/1996, arts. 6º a 10"
        if cst not in CST_ST | CST_ST_RETIDA:
            add("CST/CSOSN ICMS", cst,
                ("500" if simples else "60") + f" - ICMS-ST já retido na entrada (NCM do segmento {seg})", leg)
        cf_ok = "5405" if interna else "6404"
        if cst in CST_ST:
            if cf not in CFOP_ST_SUBST:
                add("CFOP", cf, "5403" if interna else "6403", leg)
        elif cf != cf_ok:
            add("CFOP", cf, cf_ok + " - revenda de mercadoria com ST já retida", leg)
        if not it["cest"]:
            add("CEST", "(vazio)", f"Informar o CEST do segmento {seg} (obrigatório para NCM sujeito à ST)",
                "Convênio ICMS 142/2018, cláusula 1ª-A")
    else:
        leg = f"{ricms(uf_st)} - NCM sem ST em {uf_st}"
        if cst in CST_ST | CST_ST_RETIDA:
            add("CST/CSOSN ICMS", cst, ("102" if simples else "00") + " - tributação normal (NCM sem ST)", leg)
        if cf in CFOP_ST_SUBST | CFOP_ST_RETIDA:
            add("CFOP", cf, "5102" if interna else "6102", leg)

    # --- Alíquota ICMS (regime normal, tributado) ---
    if not simples and cst in {"00", "10", "20", "70"} and it["pICMS"]:
        esperada = aliq_esperada(uf_o, uf_d, it["orig"])
        if abs(it["pICMS"] - esperada) > 0.01:
            base = ("Resolução do Senado nº 13/2012 (4%) e nº 22/1989 (7%/12%)" if not interna else ricms(uf_o))
            add("Alíquota ICMS", f"{it['pICMS']:.2f}%", f"{esperada:.2f}%", base)

    # --- PIS/COFINS: monofásico x tributado ---
    mono = buscar_mono(it["ncm"])
    if mono is not None:
        leg = f"Tabela SPED {mono['tabela']} - {mono['descricao']} | {mono['legislacao']}"
        for tributo, cst_p, v in (("PIS", it["cst_pis"], it["vPIS"]), ("COFINS", it["cst_cofins"], it["vCOFINS"])):
            if cst_p != "04":
                add(f"CST {tributo}", cst_p, "04 - Operação tributável monofásica (revenda a alíquota zero)", leg)
            if v and v > 0:
                add(f"Valor {tributo}", f"{v:.2f}", "0,00 - já recolhido pelo fabricante/importador", leg)
    else:
        leg = "Leis 9.718/1998, 10.637/2002 e 10.833/2003 - NCM fora das Tabelas 4.3.10/4.3.11"
        if it["cst_pis"] == "04" or it["cst_cofins"] == "04":
            add("CST PIS/COFINS", f"{it['cst_pis']}/{it['cst_cofins']}",
                ("49" if simples else "01") + " - NCM não é monofásico: receita tributável", leg)
        if not simples:
            ap, ac = aliq_pc_correta()
            if it["cst_pis"] == "01" and abs(it["pPIS"] - ap) > 0.001:
                add("Alíquota PIS", f"{it['pPIS']:.2f}%", f"{ap:.2f}%", leg)
            if it["cst_cofins"] == "01" and abs(it["pCOFINS"] - ac) > 0.001:
                add("Alíquota COFINS", f"{it['pCOFINS']:.2f}%", f"{ac:.2f}%", leg)

    # --- CRT x tipo de código ---
    if simples and len(cst) == 2:
        add("CRT x CST", cst, "Usar CSOSN (3 dígitos) - emitente do Simples Nacional", "LC 123/2006; leiaute NF-e (Aj. SINIEF 07/2005)")
    if not simples and len(cst) == 3:
        add("CRT x CSOSN", cst, "Usar CST (2 dígitos) - emitente do Regime Normal", "Leiaute NF-e (Aj. SINIEF 07/2005)")
    return erros


def classificar(nota, it):
    e_st = buscar_st(it["ncm"], uf_da_st(nota)) is not None
    e_mono = buscar_mono(it["ncm"]) is not None
    return {"nota": nota["numero"], "item": it["item"], "ncm": it["ncm"], "vProd": it["vProd"],
            "vICMSST": it["vICMSST"], "vPISCOF": it["vPIS"] + it["vCOFINS"], "st": e_st, "mono": e_mono}


def montar_resumo(it_df):
    cols = ["Classificação", "Itens", "Valor dos produtos (R$)", "% do total",
            "ICMS-ST destacado (R$)", "PIS+COFINS destacados (R$)"]
    if it_df is None or it_df.empty:
        return pd.DataFrame(columns=cols)
    total = it_df["vProd"].sum()

    def linha(nome, m):
        sub = it_df[m]
        return {"Classificação": nome, "Itens": int(m.sum()),
                "Valor dos produtos (R$)": round(sub["vProd"].sum(), 2),
                "% do total": round(100 * sub["vProd"].sum() / total, 2) if total else 0.0,
                "ICMS-ST destacado (R$)": round(sub["vICMSST"].sum(), 2),
                "PIS+COFINS destacados (R$)": round(sub["vPISCOF"].sum(), 2)}

    todos = pd.Series(True, index=it_df.index)
    linhas = [linha("SUBSTITUIÇÃO TRIBUTÁRIA (ICMS-ST)", it_df["st"]),
              linha("MONOFÁSICO (PIS/COFINS)", it_df["mono"]),
              linha("TRIBUTADO NORMAL (sem ST e sem monofásico)", ~it_df["st"] & ~it_df["mono"]),
              linha("TOTAL GERAL DOS PRODUTOS", todos)]
    return pd.DataFrame(linhas, columns=cols)


# ---------------------------------------------------------------------------
# 4) FICHA POR NCM (estilo Econet)
# ---------------------------------------------------------------------------
def ficha_ncm(ncm, uf_o, uf_d, crt):
    ncm = so_digitos(ncm)
    mono = buscar_mono(ncm)
    regra_st = buscar_st(ncm, uf_d)
    simples = crt == "Simples Nacional"
    interna = uf_o == uf_d

    out = {"ncm": ncm}
    # ICMS
    if regra_st is not None:
        out["cfop_saida"] = "5405 / 6404 (ST já retida)  |  5401/5403 / 6401/6403 (substituto)"
        out["cst_icms"] = "500 / 201 / 202" if simples else "60 (ST retida) / 10 / 70"
        out["icms_texto"] = f"Produto sujeito à ST ({regra_st['segmento']}). MVA/base: consultar anexo da UF."
        out["icms_leg"] = f"{regra_st['legislacao']} | {ricms(uf_d)}"
    else:
        out["cfop_saida"] = "5102 (interna) / 6102 (interestadual)"
        out["cst_icms"] = "102" if simples else "00 (tributada integralmente)"
        out["icms_texto"] = "Tributação normal."
        out["icms_leg"] = ricms(uf_o)
    out["aliquota_icms"] = f"{aliq_esperada(uf_o, uf_d, '0'):.2f}%"
    out["tipo_oper"] = "interna" if interna else "interestadual"
    # PIS/COFINS
    if mono is not None:
        out["pis_cofins"] = "CST 04 - Monofásico (alíquota zero na revenda)"
        out["pis_leg"] = f"Tabela SPED {mono['tabela']} - {mono['descricao']} | {mono['legislacao']}"
    else:
        out["pis_cofins"] = "CST 01 - Tributável (0,65%/3,00% cumulativo ou 1,65%/7,60% não cumulativo)"
        out["pis_leg"] = "Leis 9.718/1998, 10.637/2002 e 10.833/2003"
    out["ipi"] = "Consultar TIPI (Decreto 11.158/2022) para a alíquota do NCM"
    return out


# ---------------------------------------------------------------------------
# 5) EXPORTAÇÃO
# ---------------------------------------------------------------------------
def to_excel(df, resumo):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Inconsistências")
        resumo.to_excel(w, index=False, sheet_name="Resumo ST-Mono-Tributado")
        for ws in w.sheets.values():
            for col in ws.columns:
                largura = max(len(str(c.value or "")) for c in col[:200]) + 2
                ws.column_dimensions[col[0].column_letter].width = min(largura, 60)
    return buf.getvalue()


def to_pdf(df, resumo):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    estilos = getSampleStyleSheet()
    pequeno = estilos["BodyText"].clone("p")
    pequeno.fontSize = 6.5
    pequeno.leading = 8
    elems = [Paragraph("Relatório de Inconsistências Fiscais - XML", estilos["Title"]), Spacer(1, 8)]
    cols = ["Nota", "Item", "NCM", "Campo", "Informado", "Correto", "Gravidade", "Legislação"]
    df = df.reindex(columns=cols)
    dados = [cols] + [[Paragraph(str(r[c]), pequeno) for c in cols] for _, r in df.iterrows()]
    t = Table(dados, repeatRows=1, colWidths=[35, 25, 55, 70, 65, 170, 45, 280])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elems.append(t)
    elems += [Spacer(1, 14), Paragraph("Resumo final: ST, Monofásico e Tributado", estilos["Heading2"])]
    rc = list(resumo.columns)
    rd = [rc] + [[Paragraph(str(v), pequeno) for v in row] for row in resumo.values.tolist()]
    t2 = Table(rd, repeatRows=1, colWidths=[230, 40, 110, 55, 110, 120])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
    ]))
    elems += [t2, Spacer(1, 6), Paragraph("Item com ST e monofásico aparece nas duas primeiras linhas (impostos distintos: ICMS e PIS/COFINS).", pequeno)]
    doc.build(elems)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 6) INTERFACE
# ---------------------------------------------------------------------------
st.title("🧾 Auditor Fiscal de XML")
st.caption("Análise em lote de NF-e: ST por UF, monofásicos (SPED 4.3.10 / 4.3.11), CFOP, CST, alíquotas e legislação.")

with st.sidebar:
    st.header("Bases de dados")
    up_mono = st.file_uploader("Monofásicos (CSV)", type="csv", key="up_mono")
    up_st = st.file_uploader("Base ST por UF (CSV)", type="csv", key="up_st")
    if up_mono:
        st.session_state["mono"] = pd.read_csv(up_mono, dtype=str, sep=None, engine="python").fillna("")
        st.success(f"{len(st.session_state['mono'])} linhas de monofásicos carregadas")
    if up_st:
        novo_st = normaliza_st(pd.read_csv(up_st, dtype=str, sep=None, engine="python"))
        base_st = st.session_state["st"].reindex(columns=list(novo_st.columns)).fillna("")
        st.session_state["st"] = (pd.concat([base_st, novo_st], ignore_index=True)
                                  .drop_duplicates(subset=["uf", "ncm_prefixo"], keep="last"))
        st.success(f"{len(novo_st)} linhas de ST importadas (UF: {', '.join(sorted(set(novo_st['uf'])))})")
    st.info(f"Monofásicos: {len(st.session_state['mono'])} regras\n\nST: {len(st.session_state['st'])} regras")

aba1, aba2, aba3 = st.tabs(["📂 Análise em lote", "🔎 Consulta por NCM", "🗄️ Bases de dados"])

# ---- Aba 1 ----
with aba1:
    cA, cB = st.columns([1, 2])
    cA.selectbox("UF da legislação de ST", ["Automático (UF do destinatário)"] + UFS, key="uf_st")
    cB.checkbox("Usar somente os NCMs cadastrados para esta UF (ignorar a base nacional '*')", key="so_base_uf")
    st.caption("Análise fixa para empresas do **Simples Nacional** (CSOSN). A UF escolhida define a lista de ST, "
               "a legislação citada e o CFOP/CSOSN correto.")
    _uf = st.session_state.get("uf_st", "")
    if st.session_state.get("so_base_uf") and _uf in UFS and not (st.session_state["st"]["uf"] == _uf).any():
        st.warning(f"Não há NCMs cadastrados para {_uf}. Importe a lista de ST de {_uf} na barra lateral, "
                   "senão todos os itens serão tratados como SEM ST.")
    arquivos = st.file_uploader("Envie XMLs (ou ZIP com XMLs)", type=["xml", "zip"], accept_multiple_files=True)
    if arquivos and st.button("Analisar", type="primary"):
        todos, itens_total, falhas, linhas_itens = [], 0, [], []
        entradas = []
        for f in arquivos:
            if f.name.lower().endswith(".zip"):
                with zipfile.ZipFile(f) as z:
                    for n in z.namelist():
                        if n.lower().endswith(".xml"):
                            entradas.append((n, z.read(n)))
            else:
                entradas.append((f.name, f.read()))
        barra = st.progress(0.0)
        for i, (nome, conteudo) in enumerate(entradas):
            try:
                nota, itens = parse_nfe(conteudo, nome)
                itens_total += len(itens)
                for it in itens:
                    todos += auditar_item(nota, it)
                    linhas_itens.append(classificar(nota, it))
            except Exception as e:
                falhas.append((nome, str(e)))
            barra.progress((i + 1) / max(len(entradas), 1))
        st.session_state["resultado"] = pd.DataFrame(todos)
        st.session_state["itens_df"] = pd.DataFrame(linhas_itens)
        st.session_state["resumo"] = (len(entradas), itens_total, falhas)

    if "resultado" in st.session_state:
        df = st.session_state["resultado"]
        n_xml, n_itens, falhas = st.session_state["resumo"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("XMLs lidos", n_xml)
        c2.metric("Itens analisados", n_itens)
        c3.metric("Erros", int((df["Gravidade"] == "ERRO").sum()) if not df.empty else 0)
        c4.metric("Alertas", int((df["Gravidade"] == "ALERTA").sum()) if not df.empty else 0)
        for nome, msg in falhas:
            st.warning(f"{nome}: {msg}")
        if df.empty:
            st.success("Nenhuma inconsistência encontrada.")
            vis = df
        else:
            f1, f2 = st.columns(2)
            grav = f1.multiselect("Gravidade", ["ERRO"], default=["ERRO"])
            campos = f2.multiselect("Campo", sorted(df["Campo"].unique()))
            vis = df[df["Gravidade"].isin(grav)]
            if campos:
                vis = vis[vis["Campo"].isin(campos)]
            st.dataframe(vis, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("📊 Resumo final: ST, Monofásico e Tributado")
        st.caption(f"Legislação de ST aplicada: {st.session_state.get('uf_st', '')}  |  Simples Nacional")
        resumo = montar_resumo(st.session_state.get("itens_df"))
        if not resumo.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("ST (ICMS-ST)", f"R$ {resumo.iloc[0]['Valor dos produtos (R$)']:,.2f}")
            m2.metric("Monofásico (PIS/COFINS)", f"R$ {resumo.iloc[1]['Valor dos produtos (R$)']:,.2f}")
            m3.metric("Tributado normal", f"R$ {resumo.iloc[2]['Valor dos produtos (R$)']:,.2f}")
            st.dataframe(resumo, use_container_width=True, hide_index=True)
            st.caption("Item com ST e monofásico entra nas duas primeiras linhas (ICMS e PIS/COFINS são impostos distintos).")
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Excel", to_excel(vis, resumo), "inconsistencias.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        d2.download_button("⬇️ PDF", to_pdf(vis, resumo), "inconsistencias.pdf", "application/pdf")

# ---- Aba 2 ----
with aba2:
    c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
    ncm_q = c1.text_input("NCM (8 dígitos)", value="")
    uf_o = c2.selectbox("UF origem", UFS, index=UFS.index("PE"))
    uf_d = c3.selectbox("UF destino", UFS, index=UFS.index("PE"))
    regime = c4.selectbox("Regime do emitente", ["Lucro Presumido / Real", "Simples Nacional"])
    if ncm_q:
        r = ficha_ncm(ncm_q, uf_o, uf_d, regime)
        st.subheader(f"Ficha - NCM {r['ncm']}  ({r['tipo_oper']})")
        e, s = st.columns(2)
        with e:
            st.markdown("**ICMS**")
            st.write(f"CFOP: {r['cfop_saida']}")
            st.write(f"CST/CSOSN: {r['cst_icms']}")
            st.write(f"Alíquota: {r['aliquota_icms']}")
            st.write(r["icms_texto"])
            st.caption(r["icms_leg"])
        with s:
            st.markdown("**PIS / COFINS**")
            st.write(r["pis_cofins"])
            st.caption(r["pis_leg"])
            st.markdown("**IPI**")
            st.write(r["ipi"])
        st.warning("Resultado baseado nas bases carregadas. Confirme a vigência da legislação antes de aplicar.")

# ---- Aba 3 ----
with aba3:
    st.markdown("""
**Formato dos CSVs (separador `;` ou `,`):**

`monofasico.csv` → `tabela;ncm_prefixo;descricao;legislacao`
(tabela = 4.3.10 ou 4.3.11; `ncm_prefixo` aceita 4, 6 ou 8 dígitos)

`st_base.csv` → `uf;ncm_prefixo;segmento;mva;legislacao`
(use `*` em `uf` para valer em todos os estados; linhas com UF específica têm prioridade)

Salve em uma pasta `dados/` junto do `app.py` para carregar automaticamente.
""")
    st.markdown("**Monofásicos (4.3.10 / 4.3.11)**")
    st.session_state["mono"] = st.data_editor(st.session_state["mono"], num_rows="dynamic", use_container_width=True, key="ed_mono")
    st.markdown("**Substituição Tributária por UF**")
    st.session_state["st"] = st.data_editor(st.session_state["st"], num_rows="dynamic", use_container_width=True, key="ed_st")
    st.download_button("⬇️ Baixar monofasico.csv", st.session_state["mono"].to_csv(index=False, sep=";"), "monofasico.csv")
    st.download_button("⬇️ Baixar st_base.csv", st.session_state["st"].to_csv(index=False, sep=";"), "st_base.csv")
