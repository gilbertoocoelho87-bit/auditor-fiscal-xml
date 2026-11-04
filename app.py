# -*- coding: utf-8 -*-
"""
AUDITOR FISCAL DE XML (NF-e) com IA  -  empresas do SIMPLES NACIONAL
--------------------------------------------------------------------
Fluxo:
  1. Você envia os XMLs (ou um ZIP) e escolhe a UF da ST.
  2. Para cada NCM x UF o app consulta a IA (Claude + busca na web em fontes
     oficiais: Confaz, Receita/SPED, SEFAZ, Planalto) e obtém:
       - se o NCM tem ICMS-ST na UF, CEST, segmento, MVA e a legislação
       - se é monofásico (Tabelas 4.3.10 / 4.3.11 do SPED) e a legislação
       - alíquota/legislação de IPI (TIPI)
  3. O app compara com o XML, aponta o ERRO e já informa o CORRETO + legislação.
  4. Fecha com o resumo de ST, Monofásico e Tributado (tela, Excel e PDF).

Configuração (uma vez só):  ANTHROPIC_API_KEY em  Settings > Secrets  (Streamlit
Cloud)  ou em  .streamlit/secrets.toml  (local).  Modelo opcional: ANTHROPIC_MODEL.
"""

import io
import json
import os
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Auditor Fiscal XML", page_icon="🧾", layout="wide")

CACHE_PATH = os.path.join("dados", "cache_ia.json")
CACHE_DIAS = 30
LOTE = 5            # NCMs por consulta à IA
MODELO_PADRAO = "claude-sonnet-5-5"

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
       "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
AUTO = "Automático (UF do destinatário)"

RICMS = {
    "PE": "RICMS/PE - Decreto nº 44.650/2017", "SP": "RICMS/SP - Decreto nº 45.490/2000",
    "RJ": "RICMS/RJ - Decreto nº 27.427/2000", "BA": "RICMS/BA - Decreto nº 13.780/2012",
    "CE": "RICMS/CE - Decreto nº 24.569/1997", "PR": "RICMS/PR - Decreto nº 7.871/2017",
    "RS": "RICMS/RS - Decreto nº 37.699/1997", "MG": "RICMS/MG - Decreto nº 48.589/2023",
}


def ricms(uf):
    return RICMS.get(uf, f"RICMS/{uf}")


def so_digitos(v):
    return "".join(c for c in str(v or "") if c.isdigit())


# ---------------------------------------------------------------------------
# 1) IA: classificação por NCM x UF (com busca na web)
# ---------------------------------------------------------------------------
def get_key():
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


def get_modelo():
    try:
        if "ANTHROPIC_MODEL" in st.secrets:
            return st.secrets["ANTHROPIC_MODEL"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_MODEL", MODELO_PADRAO)


SISTEMA = """Você é um especialista tributário brasileiro (ICMS-ST, PIS/COFINS monofásico, IPI, SPED).
Hoje é {hoje}. Use a ferramenta de busca na web para confirmar a legislação VIGENTE em fontes oficiais
(Confaz - Convênio ICMS 142/2018 e protocolos, SEFAZ da UF e seu RICMS, Receita Federal/portal SPED
Tabelas 4.3.10 e 4.3.11, Planalto, TIPI). Seja DEFINITIVO: cada campo booleano é true ou false, sem
'talvez' e sem 'verificar'. Responda SOMENTE com JSON válido, sem texto antes ou depois."""

PROMPT = """UF da legislação de ST: {uf}
Perfil do emitente: empresa do Simples Nacional que REVENDE mercadoria adquirida de terceiros.
NCMs (8 dígitos): {ncms}

Retorne uma LISTA JSON com um objeto por NCM, na mesma ordem, com exatamente estas chaves:
{{
 "ncm": "8 dígitos",
 "descricao": "descrição curta do produto/NCM",
 "st": true|false,                 // o NCM está sujeito a ICMS-ST na UF {uf} (revenda)
 "segmento": "segmento do Convênio ICMS 142/2018 ou \\"\\"",
 "cest": "CEST do item no formato 00.000.00 ou \\"\\"",
 "mva": "MVA/base de cálculo da ST na UF ou \\"\\"",
 "legislacao_st": "norma + artigo/anexo/item que sustenta a resposta (inclusive quando for false: onde a UF define)",
 "monofasico": true|false,         // consta nas Tabelas 4.3.10 ou 4.3.11 do SPED Contribuições
 "tabela_sped": "4.3.10" | "4.3.11" | "",
 "legislacao_pis_cofins": "lei/artigo que sustenta (monofásico ou tributação normal)",
 "ipi_aliquota": "alíquota da TIPI (ex.: 5%) ou NT",
 "ipi_legislacao": "TIPI vigente / decreto",
 "fontes": ["urls oficiais consultadas"]
}}"""


def _extrair_json(texto):
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.M).strip()
    i, j = texto.find("["), texto.rfind("]")
    if i != -1 and j > i:
        return json.loads(texto[i:j + 1])
    i, j = texto.find("{"), texto.rfind("}")
    return [json.loads(texto[i:j + 1])]


def _chamar_ia(ncms, uf, chave, modelo):
    """Uma consulta (lote de NCMs) com busca na web. Sem uso de st.* (roda em thread)."""
    import anthropic
    client = anthropic.Anthropic(api_key=chave)
    mensagens = [{"role": "user", "content": PROMPT.format(uf=uf, ncms=", ".join(ncms))}]
    for _ in range(4):
        msg = client.messages.create(
            model=modelo, max_tokens=6000,
            system=SISTEMA.format(hoje=date.today().strftime("%d/%m/%Y")),
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
            messages=mensagens)
        if msg.stop_reason == "pause_turn":
            mensagens.append({"role": "assistant", "content": msg.content})
            continue
        break
    texto = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return _extrair_json(texto)


def _bool(v):
    return v is True or str(v).strip().lower() in ("true", "sim", "s", "1")


def _normalizar(d, ncm, origem):
    fontes = d.get("fontes") or []
    if isinstance(fontes, str):
        fontes = [fontes]
    return {
        "ncm": ncm, "descricao": str(d.get("descricao", ""))[:120],
        "st": _bool(d.get("st")), "segmento": str(d.get("segmento", "")),
        "cest": str(d.get("cest", "")), "mva": str(d.get("mva", "")),
        "legislacao_st": str(d.get("legislacao_st", "")),
        "monofasico": _bool(d.get("monofasico")), "tabela_sped": str(d.get("tabela_sped", "")),
        "legislacao_pis_cofins": str(d.get("legislacao_pis_cofins", "")),
        "ipi_aliquota": str(d.get("ipi_aliquota", "")), "ipi_legislacao": str(d.get("ipi_legislacao", "")),
        "fontes": [str(f) for f in fontes][:3], "origem": origem, "ts": time.time(),
    }


# --- base interna (reserva, só usada se a IA estiver indisponível) -----------
_ST_INTERNA = {
    "01 Autopeças": ["8708", "8409", "8483", "8511", "8512", "8714", "7007", "8707"],
    "03 Bebidas": ["2201", "2202", "2203", "2106906"], "05 Cimentos": ["2523"],
    "08 Ferramentas": ["8201", "8202", "8203", "8204", "8205", "8206", "8207", "8208"],
    "10 Materiais de construção": ["3917", "3925", "3506", "3214", "4418", "6907", "7318", "8302"],
    "11 Material de limpeza": ["2828", "3401", "3402", "380894"],
    "12 Materiais elétricos": ["8535", "8536", "8537", "8538", "8544"],
    "13 Medicamentos": ["3003", "3004"], "15 Pneumáticos": ["4011", "4012", "4013"],
    "19 Perfumaria e higiene": ["3303", "3304", "3305", "3306", "3307", "340111"],
    "23 Tintas e vernizes": ["3208", "3209", "3210"],
}
_MONO_INTERNA = {
    "3003": "Lei 10.147/2000", "3004": "Lei 10.147/2000", "3303": "Lei 10.147/2000",
    "3304": "Lei 10.147/2000", "3305": "Lei 10.147/2000", "3307": "Lei 10.147/2000",
    "3306": "Lei 10.147/2000", "340111": "Lei 10.147/2000", "4011": "Lei 10.485/2002",
    "4013": "Lei 10.485/2002", "8708": "Lei 10.485/2002", "8714": "Lei 10.485/2002",
    "8703": "Lei 10.485/2002", "8711": "Lei 10.485/2002", "2202": "Lei 13.097/2015",
    "2203": "Lei 13.097/2015", "2201": "Lei 13.097/2015", "2710": "Lei 9.718/1998",
}


def info_interna(ncm, uf):
    seg = next((s for s, l in _ST_INTERNA.items() if any(ncm.startswith(p) for p in l)), "")
    leg_m = next((v for p, v in _MONO_INTERNA.items() if ncm.startswith(p)), "")
    d = {"descricao": "", "st": bool(seg), "segmento": seg, "cest": "", "mva": "",
         "legislacao_st": f"Convênio ICMS 142/2018 - segmento {seg}" if seg else f"{ricms(uf)}",
         "monofasico": bool(leg_m), "tabela_sped": "4.3.10" if leg_m else "",
         "legislacao_pis_cofins": leg_m or "Leis 10.637/2002 e 10.833/2003", "ipi_aliquota": "", "ipi_legislacao": "",
         "fontes": []}
    return _normalizar(d, ncm, "base interna (IA indisponível)")


def _ler_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _salvar_cache(c):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False)
    except Exception:
        pass


def obter_infos(pares):
    """pares: conjunto de (uf, ncm). Retorna ({(uf, ncm): info}, [avisos])."""
    cache = _ler_cache()
    infos, avisos, pendentes = {}, [], {}
    limite = time.time() - CACHE_DIAS * 86400
    for uf, ncm in pares:
        c = cache.get(f"{uf}|{ncm}")
        if c and c.get("ts", 0) > limite and not c["origem"].startswith("base interna"):
            infos[(uf, ncm)] = c
        else:
            pendentes.setdefault(uf, []).append(ncm)

    chave, modelo = get_key(), get_modelo()
    tarefas = [(uf, ncms[i:i + LOTE]) for uf, ncms in pendentes.items() for i in range(0, len(ncms), LOTE)]

    def rodar(t):
        uf, lote = t
        for tentativa in range(2):
            try:
                return t, _chamar_ia(lote, uf, chave, modelo), None
            except Exception as e:  # noqa
                erro = str(e)[:200]
                time.sleep(2)
        return t, None, erro

    if tarefas and chave:
        with ThreadPoolExecutor(max_workers=4) as ex:
            resultados = list(ex.map(rodar, tarefas))
    else:
        resultados = [(t, None, "chave da API não configurada") for t in tarefas]

    for (uf, lote), lista, erro in resultados:
        por_ncm = {}
        if lista:
            for pos, d in enumerate(lista):
                n = so_digitos(d.get("ncm", "")) or (lote[pos] if pos < len(lote) else "")
                por_ncm[n] = d
        for ncm in lote:
            if ncm in por_ncm:
                info = _normalizar(por_ncm[ncm], ncm, "IA + busca web")
                cache[f"{uf}|{ncm}"] = info
            else:
                info = info_interna(ncm, uf)
            infos[(uf, ncm)] = info
        if erro:
            avisos.append(f"UF {uf}, NCMs {', '.join(lote)}: {erro}")
    _salvar_cache(cache)
    return infos, avisos


# ---------------------------------------------------------------------------
# 2) LEITURA DO XML
# ---------------------------------------------------------------------------
def _tag(el):
    return el.tag.split("}")[-1]


def _find(el, path):
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


def _grupo(pai, nome):
    g = _find(pai, nome) if pai is not None else None
    if g is not None and len(g):
        return list(g)[0]
    return None


def parse_nfe(conteudo, nome):
    root = ET.fromstring(conteudo)
    inf = next((e for e in root.iter() if _tag(e) == "infNFe"), None)
    if inf is None:
        raise ValueError("Não é um XML de NF-e/NFC-e (infNFe não encontrado).")
    nota = {
        "arquivo": nome, "chave": inf.attrib.get("Id", "")[3:], "numero": _txt(inf, "ide/nNF"),
        "serie": _txt(inf, "ide/serie"), "idDest": _txt(inf, "ide/idDest"),
        "emit_uf": _txt(inf, "emit/enderEmit/UF"), "crt": _txt(inf, "emit/CRT"),
        "dest_uf": _txt(inf, "dest/enderDest/UF"),
    }
    itens = []
    for det in [c for c in inf if _tag(c) == "det"]:
        prod, imp = _find(det, "prod"), _find(det, "imposto")
        icms, pis, cof = _grupo(imp, "ICMS"), _grupo(imp, "PIS"), _grupo(imp, "COFINS")
        itens.append({
            "item": det.attrib.get("nItem", ""), "xProd": _txt(prod, "xProd"),
            "ncm": so_digitos(_txt(prod, "NCM")), "cest": _txt(prod, "CEST"),
            "cfop": _txt(prod, "CFOP"), "vProd": _num(prod, "vProd"),
            "cst_icms": _txt(icms, "CSOSN") or _txt(icms, "CST"), "vICMSST": _num(icms, "vICMSST"),
            "cst_pis": _txt(pis, "CST"), "vPIS": _num(pis, "vPIS"),
            "cst_cofins": _txt(cof, "CST"), "vCOFINS": _num(cof, "vCOFINS"),
        })
    return nota, itens


# ---------------------------------------------------------------------------
# 3) MOTOR DE REGRAS (Simples Nacional)  -  o "correto" vem da IA + regra fixa
# ---------------------------------------------------------------------------
CSOSN_ST_SUBST = {"201", "202", "203"}
CSOSN_ST_RETIDA = {"500"}
CFOP_ST_SUBST = {"5401", "5403", "6401", "6403"}
CFOP_ST_RETIDA = {"5405", "6404"}


def uf_da_st(nota):
    esc = st.session_state.get("uf_st", AUTO)
    return esc if esc in UFS else (nota["dest_uf"] or nota["emit_uf"])


def _fonte(info):
    f = info["origem"]
    return f + (" | " + "; ".join(info["fontes"][:2]) if info["fontes"] else "")


def auditar_item(nota, it, info, uf_st):
    erros = []
    uf_o, uf_d = nota["emit_uf"], nota["dest_uf"] or nota["emit_uf"]
    interna = uf_o == uf_d
    cst, cf = it["cst_icms"], it["cfop"]

    def add(campo, informado, correto, leg):
        erros.append({
            "Nota": nota["numero"], "Série": nota["serie"], "Item": it["item"], "Produto": it["xProd"][:60],
            "NCM": it["ncm"], "Campo": campo, "Informado": informado, "Correto": correto,
            "Legislação": leg, "Fonte": _fonte(info), "Arquivo": nota["arquivo"], "Chave": nota["chave"],
        })

    if nota["crt"] not in ("1", "2") and it["item"] in ("1", ""):
        add("CRT", nota["crt"] or "(vazio)", "1 - Simples Nacional (ou 2 - excesso de sublimite)",
            "LC 123/2006; leiaute NF-e (Ajuste SINIEF 07/2005)")
    if len(it["ncm"]) != 8:
        add("NCM", it["ncm"], "8 dígitos válidos (NCM/TIPI)", "Ajuste SINIEF 07/2005; Resolução Gecex vigente")
    if cf and cf[0] in "56":
        if interna and cf[0] != "5":
            add("CFOP", cf, "Iniciar com 5 (operação interna)", "Ajuste SINIEF 07/2001 (Tabela de CFOP)")
        elif not interna and cf[0] != "6":
            add("CFOP", cf, "Iniciar com 6 (operação interestadual)", "Ajuste SINIEF 07/2001 (Tabela de CFOP)")

    # ---- ICMS-ST ----
    if info["st"]:
        leg = f"{info['legislacao_st']} | {ricms(uf_st)}" + (f" | Segmento {info['segmento']}" if info["segmento"] else "")
        if cst not in CSOSN_ST_SUBST | CSOSN_ST_RETIDA:
            add("CSOSN ICMS", cst, f"500 - ICMS-ST já retido anteriormente (NCM com ST em {uf_st})", leg)
        if cst in CSOSN_ST_SUBST:
            if cf not in CFOP_ST_SUBST:
                add("CFOP", cf, "5403" if interna else "6403", leg)
        else:
            cf_ok = "5405" if interna else "6404"
            if cf != cf_ok:
                add("CFOP", cf, f"{cf_ok} - revenda com ST já retida", leg)
        cest_ok, cest_x = so_digitos(info["cest"]), so_digitos(it["cest"])
        if cest_ok and cest_x != cest_ok:
            add("CEST", it["cest"] or "(vazio)", info["cest"], leg)
        elif not cest_ok and not cest_x:
            add("CEST", "(vazio)", f"Informar o CEST do segmento {info['segmento']}", leg)
    else:
        leg = f"{info['legislacao_st'] or ricms(uf_st)} - NCM sem ST em {uf_st}"
        if cst in CSOSN_ST_SUBST | CSOSN_ST_RETIDA:
            add("CSOSN ICMS", cst, "102 - tributada sem permissão de crédito (NCM sem ST)", leg)
        if cf in CFOP_ST_SUBST | CFOP_ST_RETIDA:
            add("CFOP", cf, "5102" if interna else "6102", leg)

    if len(cst) == 2 and not any(e["Campo"] == "CSOSN ICMS" for e in erros):
        add("CST x CSOSN", cst, "Usar CSOSN (3 dígitos) - emitente do Simples Nacional",
            "LC 123/2006; leiaute NF-e (Aj. SINIEF 07/2005)")

    # ---- PIS/COFINS ----
    if info["monofasico"]:
        leg = f"Tabela SPED {info['tabela_sped']} | {info['legislacao_pis_cofins']}"
        for tributo, cst_p, v in (("PIS", it["cst_pis"], it["vPIS"]), ("COFINS", it["cst_cofins"], it["vCOFINS"])):
            if cst_p != "04":
                add(f"CST {tributo}", cst_p, "04 - Operação tributável monofásica (revenda a alíquota zero)", leg)
            if v and v > 0:
                add(f"Valor {tributo}", f"{v:.2f}", "0,00 - recolhido pelo fabricante/importador", leg)
    else:
        if it["cst_pis"] == "04" or it["cst_cofins"] == "04":
            add("CST PIS/COFINS", f"{it['cst_pis']}/{it['cst_cofins']}",
                "49 - Outras operações de saída (NCM não monofásico)",
                f"{info['legislacao_pis_cofins']} | NCM fora das Tabelas 4.3.10/4.3.11 do SPED")
    return erros


def classificar(nota, it, info):
    return {"nota": nota["numero"], "item": it["item"], "ncm": it["ncm"], "vProd": it["vProd"],
            "vICMSST": it["vICMSST"], "vPISCOF": it["vPIS"] + it["vCOFINS"],
            "st": info["st"], "mono": info["monofasico"]}


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
    return pd.DataFrame([
        linha("SUBSTITUIÇÃO TRIBUTÁRIA (ICMS-ST)", it_df["st"]),
        linha("MONOFÁSICO (PIS/COFINS)", it_df["mono"]),
        linha("TRIBUTADO NORMAL (sem ST e sem monofásico)", ~it_df["st"] & ~it_df["mono"]),
        linha("TOTAL GERAL DOS PRODUTOS", todos)], columns=cols)


def tabela_ncm(infos):
    linhas = [{"UF": uf, "NCM": n, "Descrição": i["descricao"], "ICMS-ST": "SIM" if i["st"] else "NÃO",
               "CEST": i["cest"], "Segmento": i["segmento"], "MVA": i["mva"], "Legislação ST": i["legislacao_st"],
               "Monofásico": "SIM" if i["monofasico"] else "NÃO", "Tabela SPED": i["tabela_sped"],
               "Legislação PIS/COFINS": i["legislacao_pis_cofins"], "IPI": i["ipi_aliquota"],
               "Origem": i["origem"], "Fontes": " ; ".join(i["fontes"])}
              for (uf, n), i in sorted(infos.items())]
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# 4) EXPORTAÇÃO
# ---------------------------------------------------------------------------
def to_excel(df, resumo, ncms):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Erros e correções")
        resumo.to_excel(w, index=False, sheet_name="Resumo ST-Mono-Tributado")
        ncms.to_excel(w, index=False, sheet_name="Classificação por NCM")
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
    est = getSampleStyleSheet()
    p = est["BodyText"].clone("p")
    p.fontSize, p.leading = 6.5, 8
    estilo = TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, 0), 7),
                         ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")])
    cols = ["Nota", "Item", "NCM", "Campo", "Informado", "Correto", "Legislação"]
    df = df.reindex(columns=cols)
    dados = [cols] + [[Paragraph(str(r[c]), p) for c in cols] for _, r in df.iterrows()]
    t = Table(dados, repeatRows=1, colWidths=[35, 25, 55, 70, 65, 220, 330])
    t.setStyle(estilo)
    elems = [Paragraph("Relatório de erros e correções - XML (Simples Nacional)", est["Title"]), Spacer(1, 8), t,
             Spacer(1, 14), Paragraph("Resumo final: ST, Monofásico e Tributado", est["Heading2"])]
    rd = [list(resumo.columns)] + [[Paragraph(str(v), p) for v in row] for row in resumo.values.tolist()]
    t2 = Table(rd, repeatRows=1, colWidths=[230, 40, 110, 55, 110, 120])
    t2.setStyle(estilo)
    elems += [t2, Spacer(1, 6), Paragraph("Item com ST e monofásico aparece nas duas primeiras linhas (ICMS e PIS/COFINS são impostos distintos).", p)]
    doc.build(elems)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 5) INTERFACE (sem barra lateral)
# ---------------------------------------------------------------------------
st.title("🧾 Auditor Fiscal de XML com IA")
st.caption("Simples Nacional | ICMS-ST por UF | PIS/COFINS monofásico (SPED 4.3.10/4.3.11) | CFOP | CSOSN | legislação")

if not get_key():
    st.error("Chave da IA não configurada. Cadastre **ANTHROPIC_API_KEY** em Settings > Secrets (Streamlit Cloud) "
             "ou em `.streamlit/secrets.toml`. Sem ela o app usa apenas uma base interna parcial.")

aba1, aba2 = st.tabs(["📂 Análise em lote", "🔎 Consulta por NCM"])

with aba1:
    st.selectbox("UF da legislação de ST", [AUTO] + UFS, key="uf_st")
    arquivos = st.file_uploader("Envie os XMLs (ou um ZIP com XMLs)", type=["xml", "zip"], accept_multiple_files=True)

    if arquivos and st.button("Analisar e corrigir", type="primary"):
        entradas = []
        for f in arquivos:
            if f.name.lower().endswith(".zip"):
                with zipfile.ZipFile(f) as z:
                    entradas += [(n, z.read(n)) for n in z.namelist() if n.lower().endswith(".xml")]
            else:
                entradas.append((f.name, f.read()))

        notas, falhas, pares = [], [], set()
        for nome, conteudo in entradas:
            try:
                nota, itens = parse_nfe(conteudo, nome)
                notas.append((nota, itens))
                uf_st = uf_da_st(nota)
                pares |= {(uf_st, it["ncm"]) for it in itens if len(it["ncm"]) == 8}
            except Exception as e:
                falhas.append((nome, str(e)))

        with st.status(f"Consultando legislação de {len(pares)} NCM(s) com a IA...", expanded=False) as status:
            infos, avisos = obter_infos(pares)
            status.update(label="Legislação consultada", state="complete")

        erros, linhas_itens = [], []
        for nota, itens in notas:
            uf_st = uf_da_st(nota)
            for it in itens:
                info = infos.get((uf_st, it["ncm"])) or info_interna(it["ncm"], uf_st)
                erros += auditar_item(nota, it, info, uf_st)
                linhas_itens.append(classificar(nota, it, info))
        st.session_state["res"] = {
            "erros": pd.DataFrame(erros), "itens": pd.DataFrame(linhas_itens), "infos": infos,
            "avisos": avisos, "falhas": falhas, "n_xml": len(entradas), "uf": st.session_state.get("uf_st", AUTO)}

    r = st.session_state.get("res")
    if r:
        df, resumo = r["erros"], montar_resumo(r["itens"])
        c1, c2, c3 = st.columns(3)
        c1.metric("XMLs lidos", r["n_xml"])
        c2.metric("Itens analisados", len(r["itens"]))
        c3.metric("Erros a corrigir", len(df))
        for nome, msg in r["falhas"]:
            st.warning(f"{nome}: {msg}")
        for a in r["avisos"]:
            st.warning("IA indisponível para: " + a + " (usada base interna parcial nesses NCMs)")

        st.subheader("❌ Erros encontrados e o correto")
        if df.empty:
            st.success("Nenhum erro encontrado.")
        else:
            campos = st.multiselect("Filtrar por campo", sorted(df["Campo"].unique()))
            st.dataframe(df[df["Campo"].isin(campos)] if campos else df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("📊 Resumo final: ST, Monofásico e Tributado")
        st.caption(f"Legislação de ST aplicada: {r['uf']}  |  Simples Nacional")
        if not resumo.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("ST (ICMS-ST)", f"R$ {resumo.iloc[0]['Valor dos produtos (R$)']:,.2f}")
            m2.metric("Monofásico (PIS/COFINS)", f"R$ {resumo.iloc[1]['Valor dos produtos (R$)']:,.2f}")
            m3.metric("Tributado normal", f"R$ {resumo.iloc[2]['Valor dos produtos (R$)']:,.2f}")
            st.dataframe(resumo, use_container_width=True, hide_index=True)
            st.caption("Item com ST e monofásico entra nas duas primeiras linhas (ICMS e PIS/COFINS são impostos distintos).")

        ncm_df = tabela_ncm(r["infos"])
        with st.expander("📚 Classificação e legislação por NCM (o que a IA encontrou)"):
            st.dataframe(ncm_df, use_container_width=True, hide_index=True)

        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Excel", to_excel(df, resumo, ncm_df), "auditoria_xml.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        d2.download_button("⬇️ PDF", to_pdf(df, resumo), "auditoria_xml.pdf", "application/pdf")

with aba2:
    c1, c2, c3 = st.columns([2, 1, 1])
    ncm_q = so_digitos(c1.text_input("NCM (8 dígitos)"))
    uf_o = c2.selectbox("UF origem", UFS, index=UFS.index("PE"), key="q_o")
    uf_d = c3.selectbox("UF da ST / destino", UFS, index=UFS.index("PE"), key="q_d")
    if len(ncm_q) == 8 and st.button("Consultar"):
        with st.spinner("Consultando legislação..."):
            infos, avisos = obter_infos({(uf_d, ncm_q)})
        info = infos[(uf_d, ncm_q)]
        interna = uf_o == uf_d
        st.subheader(f"NCM {ncm_q} - {info['descricao']}")
        a, b = st.columns(2)
        with a:
            st.markdown("**ICMS (Simples Nacional)**")
            if info["st"]:
                st.write(f"ICMS-ST: **SIM** em {uf_d} | CEST: {info['cest'] or '-'} | MVA: {info['mva'] or '-'}")
                st.write(f"CSOSN: **500** | CFOP: **{'5405' if interna else '6404'}**")
            else:
                st.write(f"ICMS-ST: **NÃO** em {uf_d}")
                st.write(f"CSOSN: **102** | CFOP: **{'5102' if interna else '6102'}**")
            st.caption(f"{info['legislacao_st']} | {ricms(uf_d)}")
        with b:
            st.markdown("**PIS / COFINS**")
            if info["monofasico"]:
                st.write(f"**Monofásico** (Tabela SPED {info['tabela_sped']}) - CST **04**, alíquota zero na revenda")
            else:
                st.write("**Tributado normal** - CST **49** (Simples Nacional)")
            st.caption(info["legislacao_pis_cofins"])
            st.markdown("**IPI**")
            st.write(f"{info['ipi_aliquota'] or '-'}")
            st.caption(info["ipi_legislacao"])
        if info["fontes"]:
            st.caption("Fontes: " + " | ".join(info["fontes"]))
        st.caption(f"Origem da resposta: {info['origem']}")
        for a_ in avisos:
            st.warning(a_)
