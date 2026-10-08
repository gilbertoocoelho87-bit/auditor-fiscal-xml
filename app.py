import argparse, csv, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

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
# Importação em lote (.xml e .zip, com subpastas)
# ------------------------------------------------------------------ #
def importar_lote(pasta):
    arquivos = []
    pasta = Path(pasta)
    if not pasta.exists():
        print(f"[ERRO] Pasta não encontrada: {pasta}")
        sys.exit(1)
    for f in sorted(pasta.rglob("*")):
        if f.suffix.lower() == ".xml":
            arquivos.append((str(f), f.read_bytes()))
        elif f.suffix.lower() == ".zip":
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    if n.lower().endswith(".xml"):
                        arquivos.append((f"{f.name}/{n}", z.read(n)))
    print(f"[INFO] {len(arquivos)} arquivo(s) XML encontrados em lote.")
    return [ler_nfe(b, n) for n, b in arquivos]

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
                "NCM não localizado na base tributária. Validação de monofásico "
                "e ICMS-ST não executada para este item.",
                "Cadastrar o NCM na tributacao_db.json com base nas tabelas oficiais.",
                "LC 70/2002; Convênio ICMS 52/2017")

        # R-03: MONOFÁSICO PIS/COFINS
        if dados and dados.get("monofasico"):
            mo = dados["monofasico"]
            lei_mono = mo.get("base_legal",
                "Lei 10.637/2002 art. 4º; Lei 10.833/2003 art. 5º; LC 70/2002 art. 7º")
            if pis["cst"] not in (None, mo.get("pis_cst", "04")):
                add("R-03", "ERRO", item, p["descricao"], ncm,
                    f"Produto MONOFÁSICO tributado em PIS com CST {pis['cst']} "
                    f"(alíquota própria); deveria ser CST {mo.get('pis_cst','04')} "
                    "(operação tributável monofásica - revenda).",
                    f"Usar PIS CST {mo.get('pis_cst','04')} com vBC=0, pPIS=0 e vPIS=0.",
                    lei_mono)
            if cofins["cst"] not in (None, mo.get("cofins_cst", "04")):
                add("R-03", "ERRO", item, p["descricao"], ncm,
                    f"Produto MONOFÁSICO tributado em COFINS com CST {cofins['cst']}; "
                    f"deveria ser CST {mo.get('cofins_cst','04')}.",
                    f"Usar COFINS CST {mo.get('cofins_cst','04')} com vBC=0, pCOFINS=0, vCOFINS=0.",
                    lei_mono)

        uf_dest = nota.get("uf_destino") or nota.get("uf_origem")
        st = dados.get("icms_st") if dados else None
        cest_oficial = st.get("cest") if st else None

        # R-04: CEST divergente
        if st and cest_oficial and p["cest"] and p["cest"] != cest_oficial:
            add("R-04", "ERRO", item, p["descricao"], ncm,
                f"CEST divergente: XML informa {p['cest']}; tabela oficial "
                f"(Convênio ICMS 52/2017) prevê {cest_oficial}.",
                f"Ajustar o CEST para {cest_oficial}.",
                "Convênio ICMS 52/2017 (Anexos); LC 87/1996 art. 8º, X")

        # R-05: ST obrigatória na operação interna e não destacada
        if st and uf_dest in st.get("uf", {}):
            regra_uf = st["uf"][uf_dest]
            cfop_interno = cfop and cfop.startswith("5")
            tem_st = icms.get("vICMSST") and icms["vICMSST"] > 0
            if cfop_interno and not tem_st and icms.get("cst") not in CST_ST_ICMS:
                add("R-05", "ERRO", item, p["descricao"], ncm,
                    f"Produto SUJEITO a ICMS-ST na UF destino ({uf_dest}) e a NF-e "
                    f"não destacou ICMS retido (CST {icms.get('cst')}).",
                    f"Destacar ICMS-ST: CST 10/70/90 (ou CSOSN 201-203), "
                    f"CEST {cest_oficial or ''}, MVA ajustada conforme RICMS/{uf_dest}.",
                    f"{regra_uf.get('base_legal', 'RICMS da UF de destino')}; LC 87/1996 art. 8º-13")
            if cfop_interno and tem_st and not p["cest"]:
                add("R-05", "ERRO", item, p["descricao"], ncm,
                    "ICMS-ST destacado sem informação do CEST.",
                    f"Informar CEST {cest_oficial} no item do produto.",
                    "Convênio ICMS 52/2017; LC 87/1996 art. 8º, X")
            # R-05A: alíquota do ICMS-ST vs alíquota interna da UF
            if cfop_interno and tem_st and regra_uf.get("aliquota_interna"):
                p_st = icms.get("pICMSST")
                ali_interna = regra_uf["aliquota_interna"]
                if p_st is not None and abs(p_st - ali_interna) > 0.5:
                    add("R-05A", "ERRO", item, p["descricao"], ncm,
                        f"Alíquota do ICMS-ST divergente: XML={p_st}%; interna da "
                        f"{uf_dest}={ali_interna}%.",
                        f"Usar {ali_interna}% sobre BC com MVA ajustada.",
                        regra_uf.get("base_legal", f"RICMS/{uf_dest}"))

        # R-06: CFOP 6.x p/ consumidor final sem ICMS retido nem partilha (EC 87/2015)
        cfop_inter = cfop and cfop.startswith("6")
        if (cfop_inter and nota.get("consumidor_final") == "1"
                and nota.get("ind_ie_dest") == "9"
                and nota.get("uf_origem") != nota.get("uf_destino")):
            sem_ret = not icms.get("vICMSSTRet")
            sem_part = not icms.get("vICMSUFDest")
            if sem_ret and sem_part:
                add("R-06", "ERRO", item, p["descricao"], ncm,
                    "Venda INTERESTADUAL a consumidor final NÃO contribuinte sem "
                    "ICMS-ST retido nem partilha do ICMS (difal).",
                    "Se o produto for ST na UF destino: destacar vBCSTRet, pST e "
                    "vICMSSTRet. Caso contrário: recolher partilha (pICMSInterPart "
                    "conforme tabela de transição 2016-2018, atualmente 100% UF destino).",
                    "EC 87/2015; ADCT da CF art. 101; LC 190/2016")

        # R-07: CFOP de ST (5.4xx/6.4xx) sem ICMS retido
        if cfop and cfop[1] == "4" and cfop[0] in "56":
            if not (icms.get("vICMSSTRet") and icms["vICMSSTRet"] > 0):
                add("R-07", "ERRO", item, p["descricao"], ncm,
                    f"CFOP {cfop} (subtrair ICMS retido por substituição) sem valor "
                    "de ICMS retido no item.",
                    "Informar vBCSTRet, pST e vICMSSTRet ou corrigir o CFOP.",
                    "LC 87/1996 art. 8º, §5º; Ajuste SINIEF 5/2004")

        # R-08: CSOSN Simples Nacional com ST e sem CEST
        if icms.get("grupo", "").startswith("ICMSSN") \
                and icms.get("cst") in CST_ST_CSOSN and not p["cest"]:
            add("R-08", "ERRO", item, p["descricao"], ncm,
                f"CSOSN {icms['cst']} (ICMS-ST devido pelo Simples) sem CEST.",
                "Informar o CEST conforme tabela do Convênio ICMS 52/2017.",
                "Convênio ICMS 52/2017; LC 123/2006 art. 25")

        # R-09: CSOSN 201-203 sem pICMS
        if icms.get("cst") in {"201", "202", "203"} and icms.get("pICMS") in (None, 0.0):
            add("R-09", "AVISO", item, p["descricao"], ncm,
                "CSOSN 201-203 exige alíquota do ICMS próprio do Simples Nacional.",
                "Informar pICMS conforme tabela do Simples no RICMS da UF.",
                f"RICMS/{nota.get('uf_origem')} (Simples Nacional)")

# ------------------------------------------------------------------ #
# Relatórios
# ------------------------------------------------------------------ #
CAMPOS = ["arquivo", "chave", "numero", "serie", "emitente", "uf_origem",
          "uf_destino", "regra", "severidade", "item", "produto", "ncm",
          "problema_identificado", "correcao_recomendada", "base_legal"]

def exportar(achados, notas, saida):
    saida = Path(saida)
    with open(saida.with_suffix(".csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=";")
        w.writeheader()
        for a in achados:
            w.writerow({k: a.get(k) for k in CAMPOS})

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Inconsistências"
        ws.append(CAMPOS)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E78")
        for a in achados:
            ws.append([a.get(k) for k in CAMPOS])
        ws.auto_filter.ref = ws.dimensions

        ws2 = wb.create_sheet("Resumo por Nota")
        ws2.append(["arquivo", "chave", "numero", "emitente", "uf_origem",
                    "uf_destino", "itens", "erros", "avisos", "status"])
        for c in ws2[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E78")
        por_nota = {}
        for a in achados:
            d = por_nota.setdefault(a["arquivo"], {"erros": 0, "avisos": 0})
            d["erros" if a["severidade"] == "ERRO" else "avisos"] += 1
        for n in notas:
            st = por_nota.get(n["arquivo"], {"erros": 0, "avisos": 0})
            status = "REPROVADO" if st["erros"] else ("ATENÇÃO" if st["avisos"] else "OK")
            ws2.append([n["arquivo"], n.get("chave"), n.get("numero"),
                        n.get("emitente"), n.get("uf_origem"), n.get("uf_destino"),
                        len(n["produtos"]), st["erros"], st["avisos"], status])
        wb.save(saida.with_suffix(".xlsx"))
        print(f"[OK] Relatório XLSX: {saida.with_suffix('.xlsx')}")
    except ImportError:
        print("[AVISO] openpyxl não instalado - gerado apenas CSV.")
    print(f"[OK] Relatório CSV : {saida.with_suffix('.csv')}")

# ------------------------------------------------------------------ #
def main():
    ap = argparse.ArgumentParser(description="Analista tributário de NF-e em lote")
    ap.add_argument("--pasta", required=True, help="Pasta com XMLs e/ou ZIPs")
    ap.add_argument("--base", default="tributacao_db.json",
                    help="Base tributária JSON (monofásico + ST por UF)")
    ap.add_argument("--saida", default="relatorio_auditoria", help="Arquivo de saída")
    args = ap.parse_args()

    with open(args.base, encoding="utf-8") as f:
        base = json.load(f)

    notas = importar_lote(args.pasta)
    achados = []
    for n in notas:
        avaliar_nota(n, base, achados)

    erros = sum(1 for a in achados if a["severidade"] == "ERRO")
    print(f"\n[INFO] Notas: {len(notas)} | Achados: {len(achados)} "
          f"(ERRO: {erros}, AVISO: {len(achados)-erros})")
    exportar(achados, notas, args.saida)

if __name__ == "__main__":
    main()
    {
  "2203": {
    "descricao": "Cervejas, chopes e bebidas fermentadas",
    "monofasico": {
      "pis_cst": "04", "cofins_cst": "04",
      "base_legal": "Lei 10.637/2002 art. 4º; Lei 10.833/2003 art. 5º; LC 70/2002 art. 7º (lista III); Decreto 13.708/2023"
    },
    "icms_st": {
      "cest": "0300100",
      "uf": {
        "SP": {"mva": 72.0, "aliquota_interna": 18.0, "base_legal": "RICMS/SP art. 313-B e Anexo V"},
        "RJ": {"mva": 70.0, "aliquota_interna": 22.0, "base_legal": "RICMS/RJ Anexo XIII"}
      }
    }
  },
  "4011": {
    "descricao": "Pneus novos de borracha",
    "icms_st": {
      "cest": "0600100",
      "uf": {
        "SP": {"mva": 55.0, "aliquota_interna": 18.0, "base_legal": "RICMS/SP art. 313-E"}
      }
    }
  },
  "30049059": {
    "descricao": "Medicamentos (outros)",
    "icms_st": {
      "cest": "1300500",
      "uf": {
        "SP": {"mva": 38.0, "aliquota_interna": 18.0, "base_legal": "RICMS/SP art. 313-K"}
      }
    }
  },
  "22021000": {
    "descricao": "Águas minerais (inclusive adicionadas de açúcar)",
    "monofasico": {
      "pis_cst": "04", "cofins_cst": "04",
      "base_legal": "Lei 10.637/2002 art. 4º; Lei 10.833/2003 art. 5º; LC 70/2002 art. 7º; Decreto 13.708/2023"
    }
  }
}
