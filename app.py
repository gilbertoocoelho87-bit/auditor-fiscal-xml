"""
SISTEMA DE ANALISE TRIBUTARIA POR NCM  (estilo Econet)
=======================================================
Executar:   pip install streamlit
            streamlit run analise_tributaria.py

Estrutura
  1. BASE DE DADOS   -> UFs, normas federais, produtos (NCM). Tudo editavel.
  2. MOTOR           -> funcao analisar(): monta a ficha fiscal.
  3. SIMULADOR       -> calculo de ICMS-ST com MVA ajustada.
  4. INTERFACE       -> Streamlit (ficha, alertas, fundamentos, nova analise).

IMPORTANTE: aliquotas, MVAs, CESTs e artigos de lei mudam com frequencia.
Os valores abaixo sao uma BASE INICIAL e cada item traz o campo "conferir".
Valide na fonte oficial (CONFAZ, SEFAZ, Receita, DOU) antes de usar em producao.
Para ampliar a base sem mexer no codigo, crie o arquivo base_extra.json
(formato descrito em carregar_base_extra()).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# 1. BASE DE DADOS
# ----------------------------------------------------------------------------

# UF -> aliquota interna modal (%), FCP/FECOEP (%), base legal. CONFERIR vigencia.
UFS = {
    "AC": dict(aliq=19.0, fcp=0.0, lei="Lei 1.358/2000 / RICMS-AC"),
    "AL": dict(aliq=19.0, fcp=1.0, lei="Lei 5.900/1998 / RICMS-AL"),
    "AP": dict(aliq=18.0, fcp=0.0, lei="Lei 0400/1997 / RICMS-AP"),
    "AM": dict(aliq=20.0, fcp=0.0, lei="Lei 2.826/2003 / RICMS-AM"),
    "BA": dict(aliq=20.5, fcp=0.0, lei="Lei 7.014/1996 / RICMS-BA"),
    "CE": dict(aliq=20.0, fcp=0.0, lei="Lei 12.670/1996 / RICMS-CE"),
    "DF": dict(aliq=20.0, fcp=0.0, lei="Lei 1.254/1996 / RICMS-DF"),
    "ES": dict(aliq=17.0, fcp=0.0, lei="Lei 7.000/2001 / RICMS-ES"),
    "GO": dict(aliq=19.0, fcp=0.0, lei="Lei 11.651/1991 / RCTE-GO"),
    "MA": dict(aliq=22.0, fcp=0.0, lei="Lei 7.799/2002 / RICMS-MA"),
    "MT": dict(aliq=17.0, fcp=0.0, lei="LC 631/2019 / RICMS-MT"),
    "MS": dict(aliq=17.0, fcp=0.0, lei="Lei 1.810/1997 / RICMS-MS"),
    "MG": dict(aliq=18.0, fcp=0.0, lei="Lei 6.763/1975 / RICMS-MG"),
    "PA": dict(aliq=19.0, fcp=0.0, lei="Lei 5.530/1989 / RICMS-PA"),
    "PB": dict(aliq=20.0, fcp=0.0, lei="Lei 6.379/1996 / RICMS-PB"),
    "PR": dict(aliq=19.5, fcp=0.0, lei="Lei 11.580/1996 / RICMS-PR"),
    "PE": dict(aliq=20.5, fcp=0.0,
               lei="Lei 18.305/2023 (aliquota modal) / Decreto 44.650/2017 (RICMS-PE)"),
    "PI": dict(aliq=22.5, fcp=0.0, lei="Lei 4.257/1989 / RICMS-PI"),
    "RJ": dict(aliq=20.0, fcp=2.0, lei="Lei 2.657/1996 / RICMS-RJ"),
    "RN": dict(aliq=20.0, fcp=0.0, lei="Lei 6.968/1996 / RICMS-RN"),
    "RS": dict(aliq=17.0, fcp=0.0, lei="Lei 8.820/1989 / RICMS-RS"),
    "RO": dict(aliq=19.5, fcp=0.0, lei="Lei 688/1996 / RICMS-RO"),
    "RR": dict(aliq=20.0, fcp=0.0, lei="Lei 59/1993 / RICMS-RR"),
    "SC": dict(aliq=17.0, fcp=0.0, lei="Lei 10.297/1996 / RICMS-SC"),
    "SP": dict(aliq=18.0, fcp=0.0, lei="Lei 6.374/1989 / RICMS-SP"),
    "SE": dict(aliq=19.0, fcp=0.0, lei="Lei 3.796/1996 / RICMS-SE"),
    "TO": dict(aliq=20.0, fcp=0.0, lei="Lei 1.287/2001 / RICMS-TO"),
}
SUL_SUDESTE = {"SP", "RJ", "MG", "PR", "SC", "RS"}  # ES fica de fora (recebe 7%)

NORMAS_FEDERAIS = {
    "icms_geral": ("Lei Complementar 87/1996 (Lei Kandir)",
                   "Regras gerais do ICMS, creditamento e substituicao tributaria."),
    "st": ("Convenio ICMS 142/2018 e Convenio ICMS 52/2017",
           "Regras gerais de ST, MVA e segmentos de produtos (CEST)."),
    "difal": ("Lei Complementar 190/2022 e EC 87/2015",
              "DIFAL em operacoes interestaduais para consumidor final."),
    "interestadual": ("Resolucao do Senado 22/1989 e 13/2012",
                      "Aliquotas interestaduais 7%/12% e 4% para importados."),
    "simples": ("Lei Complementar 123/2006 (arts. 18 e 23) e Res. CGSN 140/2018",
                "Simples Nacional: ICMS no DAS, segregacao de receitas com ST (CSOSN 500)."),
    "pis_cofins_nc": ("Leis 10.637/2002 e 10.833/2003",
                      "PIS/COFINS nao cumulativo: 1,65% e 7,6% com creditos (Lucro Real)."),
    "pis_cofins_c": ("Lei 9.718/1998 e Lei 10.865/2004",
                     "PIS/COFINS cumulativo: 0,65% e 3% (Lucro Presumido)."),
    "ipi": ("Decreto 7.212/2010 (RIPI) e Decreto 11.158/2022 (TIPI)",
            "IPI e aliquotas da TIPI por NCM."),
    "reforma": ("EC 132/2023 e Lei Complementar 214/2025",
                "Reforma tributaria: CBS/IBS/IS. 2026 e ano de teste; transicao ate 2033."),
    "nfe": ("Ajuste SINIEF 07/2005 e NT da NF-e vigente",
            "Regras de emissao, CFOP, CST/CSOSN e CEST na NF-e."),
}

# Produtos. Cada item vale para qualquer NCM que comece com um dos "prefixos".
# st: segmento + MVA por UF (None = sem ST nessa UF / consultar).
PRODUTOS = [
    dict(
        prefixos=["1905"],
        titulo="Produtos de padaria, pastelaria ou da industria de bolachas e biscoitos, "
               "mesmo adicionados de cacau; hóstias, cápsulas vazias para medicamentos, "
               "obreias, pastas secas de farinha, amido ou fécula, em folhas, e produtos semelhantes",
        capitulo="Cap. 19 - Preparacoes a base de cereais, farinhas, amidos, féculas ou leite; "
                 "produtos de pastelaria",
        ipi=dict(aliq=0.0, base="TIPI - Posicao 1905 (aliquota 0% / NT)"),
        pis_cofins=dict(tipo="cumulativo_ou_nao", obs="Tributacao normal (nao monofasico)."),
        cest="Segmento 17 - Produtos alimenticios (Conv. ICMS 142/2018)",
        st=dict(
            segmento="Segmento 17 (Alimentos)",
            convenio="Convenio ICMS 142/2018 / Convenio ICMS 52/2017",
            ufs={
                "PE": dict(mva_orig=35.0, anexo="Anexo 13 (ST) e Anexo 37 (MVA) do RICMS-PE",
                           conferir=True),
            },
        ),
        alertas=[
            "A posicao 1905 abrange itens com tratamentos tributarios distintos: pao frances "
            "comum (1905.90.90) pode ter isencao/cesta basica; pao e biscoitos (1905.31.00), "
            "torradas, waffles e pizza industrializada podem ter regras proprias. Verifique "
            "a subposicao e o CEST do item.",
            "Optante pelo Simples Nacional: nas vendas de mercadorias sujeitas a ST, "
            "segregue a receita (CSOSN 500) para excluir o ICMS do DAS.",
            "Na aquisicao interestadual de mercadorias tributadas normalmente para "
            "revenda/industrializacao, o optante pelo Simples Nacional pode estar sujeito a "
            "recolhimento do Diferencial de Aliquotas / Antecipacao (conferir RICMS da UF).",
        ],
    ),
    dict(
        prefixos=["2202"],
        titulo="Aguas, incluindo aguas minerais e gaseificadas, adicionadas de acucar ou outros "
               "edulcorantes ou aromatizadas, e outras bebidas nao alcoolicas",
        capitulo="Cap. 22 - Bebidas, liquidos alcoolicos e vinagres",
        ipi=dict(aliq=None, base="TIPI - consultar subposicao (varia com o tipo de bebida)"),
        pis_cofins=dict(tipo="monofasico",
                        obs="Bebidas frias: regime monofasico (Lei 13.097/2015) - fabricante/importador "
                            "recolhe; revenda com aliquota zero."),
        cest="Segmento 03 - Bebidas nao alcoolicas",
        st=dict(segmento="Segmento 03", convenio="Convenio ICMS 142/2018",
                ufs={"PE": dict(mva_orig=None, anexo="Anexo 13 / Anexo 37 do RICMS-PE", conferir=True)}),
        alertas=["Verificar adicional de FCP/FECOEP nas UFs que o aplicam a bebidas."],
    ),
    dict(
        prefixos=["3004"],
        titulo="Medicamentos para usos terapeuticos ou profilaticos, em doses",
        capitulo="Cap. 30 - Produtos farmaceuticos",
        ipi=dict(aliq=0.0, base="TIPI - maioria NT/0% (conferir)"),
        pis_cofins=dict(tipo="monofasico",
                        obs="Monofasico (Lei 10.147/2000): aliquota zero na revenda."),
        cest="Segmento 13 - Medicamentos",
        st=dict(segmento="Segmento 13", convenio="Convenio ICMS 76/1994 e 142/2018",
                ufs={"PE": dict(mva_orig=None, anexo="RICMS-PE (consultar PMC/MVA)", conferir=True)}),
        alertas=["Medicamentos usam preco maximo (PMC) como base da ST em varias UFs."],
    ),
    dict(
        prefixos=["2710"],
        titulo="Oleos de petroleo ou de minerais betuminosos (gasolina, diesel e similares)",
        capitulo="Cap. 27 - Combustiveis minerais, oleos minerais e produtos de sua destilacao",
        ipi=dict(aliq=0.0, base="TIPI - NT (nao tributado)"),
        pis_cofins=dict(tipo="monofasico", obs="Monofasico - recolhimento na refinaria/importador."),
        cest="Segmento 06 - Combustiveis e lubrificantes",
        st=dict(segmento="Segmento 06", convenio="Convenio ICMS 199/2022 (ICMS monofasico)",
                ufs={}),
        alertas=["Combustiveis: ICMS monofasico com aliquota ad rem (Conv. ICMS 199/2022 / LC 192/2022)."],
    ),
    dict(
        prefixos=["8517"],
        titulo="Aparelhos telefonicos, incluindo telefones celulares e outros aparelhos",
        capitulo="Cap. 85 - Maquinas, aparelhos e materiais eletricos",
        ipi=dict(aliq=None, base="TIPI - consultar subposicao (benef. Lei de Informatica)"),
        pis_cofins=dict(tipo="cumulativo_ou_nao", obs="Tributacao normal; verificar beneficios."),
        cest="Segmento 21 - Eletronicos (Conv. ICMS 142/2018)",
        st=dict(segmento="Segmento 21", convenio="Convenio ICMS 142/2018", ufs={}),
        alertas=["Produtos de informatica/telecom: beneficios em PPB e Lei de Informatica."],
    ),
    dict(
        prefixos=["61", "62"],
        titulo="Vestuario e seus acessorios (malha - cap. 61 / exceto malha - cap. 62)",
        capitulo="Cap. 61 e 62 - Artigos de vestuario e acessorios, de malha ou nao",
        ipi=dict(aliq=0.0, base="TIPI - capitulos 61/62 (conferir a aliquota da subposicao)"),
        pis_cofins=dict(tipo="cumulativo_ou_nao", obs="Tributacao normal (nao monofasico)."),
        cest="Conferir no Conv. ICMS 142/2018 se a NCM possui CEST (vestuario em geral nao tem ST)",
        st=dict(segmento="Conferir", convenio="Convenio ICMS 142/2018", ufs={}),
        alertas=["Vestuario em geral e tributado normalmente (sem ST) - confirme no RICMS da UF "
                 "e no Anexo de ST, pois ha excecoes e beneficios estaduais."],
    ),
]


def carregar_base_extra(caminho: str = "base_extra.json") -> None:
    """Acrescenta produtos de um JSON externo, mesmo formato de PRODUTOS (lista)."""
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            PRODUTOS.extend(json.load(f))


# ----------------------------------------------------------------------------
# 2. MOTOR
# ----------------------------------------------------------------------------
REGIMES = ["Simples Nacional", "Lucro Presumido", "Lucro Real"]


def limpar_ncm(ncm: str) -> str:
    return re.sub(r"\D", "", ncm or "")


def formatar_ncm(ncm: str) -> str:
    n = limpar_ncm(ncm)
    if len(n) == 8:
        return f"{n[:4]}.{n[4:6]}.{n[6:]}"
    return n


def produto_generico(ncm: str) -> dict:
    """Regra geral quando a NCM nao esta cadastrada (para nao travar a analise)."""
    return dict(
        prefixos=[limpar_ncm(ncm)],
        titulo=f"NCM {formatar_ncm(ncm)} - sem regra especifica cadastrada (regra geral)",
        capitulo=f"Capitulo {limpar_ncm(ncm)[:2]} da NCM",
        ipi=dict(aliq=None, base="Consultar a TIPI para esta NCM"),
        pis_cofins=dict(tipo="cumulativo_ou_nao", obs="Assumida tributacao normal."),
        cest="Verificar no Conv. ICMS 142/2018 se a NCM tem CEST",
        st=dict(segmento="Nao cadastrado", convenio="Convenio ICMS 142/2018", ufs={}),
        alertas=["NCM sem regra especifica na base: o resultado usa a REGRA GERAL (tributacao normal, "
                 "sem ST). Confirme beneficios, ST e IPI antes de usar."],
    )


def importar_tipi_csv(caminho: str, saida: str = "base_extra.json") -> int:
    """Importa CSV (colunas: ncm;descricao;ipi) e gera base_extra.json com uma regra por NCM."""
    import csv
    itens = []
    with open(caminho, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            n = limpar_ncm(r["ncm"])
            ipi = r.get("ipi", "").replace("%", "").replace(",", ".").strip()
            itens.append(dict(
                prefixos=[n], titulo=r["descricao"], capitulo=f"Capitulo {n[:2]}",
                ipi=dict(aliq=float(ipi) if ipi.replace(".", "").isdigit() else None, base="TIPI"),
                pis_cofins=dict(tipo="cumulativo_ou_nao", obs="Tributacao normal."),
                cest="Conferir CEST", st=dict(segmento="Conferir", convenio="Conv. ICMS 142/2018", ufs={}),
                alertas=[]))
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(itens, f, ensure_ascii=False, indent=1)
    return len(itens)


def buscar_produto(ncm: str) -> dict | None:
    n = limpar_ncm(ncm)
    achados = [(len(pre), p) for p in PRODUTOS for pre in p["prefixos"] if n.startswith(pre)]
    return max(achados, key=lambda x: x[0])[1] if achados else None


def aliquota_interestadual(origem: str, destino: str, importado: bool = False) -> float:
    if importado:
        return 4.0
    if origem == destino:
        return UFS[origem]["aliq"]
    if origem in SUL_SUDESTE and destino not in SUL_SUDESTE:
        return 7.0
    return 12.0


def mva_ajustada(mva_orig: float, aliq_inter: float, aliq_interna: float) -> float:
    """MVA ajustada = [(1+MVA)*(1-ALQ inter)/(1-ALQ interna) - 1] * 100 (Conv. 142/2018, cl. 2a)."""
    return ((1 + mva_orig / 100) * (1 - aliq_inter / 100) / (1 - aliq_interna / 100) - 1) * 100


@dataclass
class Ficha:
    ncm: str
    uf_origem: str
    uf_destino: str
    regime: str
    produto: dict
    sujeito_st: bool
    entrada: dict = field(default_factory=dict)
    saida: dict = field(default_factory=dict)
    pis_cofins: dict = field(default_factory=dict)
    ipi: dict = field(default_factory=dict)
    alertas: list = field(default_factory=list)
    fundamentos: list = field(default_factory=list)


def analisar(ncm: str, uf_origem: str, uf_destino: str, regime: str) -> Ficha | None:
    if len(limpar_ncm(ncm)) < 4:
        return None
    p = buscar_produto(ncm) or produto_generico(ncm)
    uf_info = UFS[uf_destino]
    st_uf = p["st"]["ufs"].get(uf_destino)
    st = st_uf is not None
    simples = regime == "Simples Nacional"
    inter = uf_origem != uf_destino

    f = Ficha(ncm=formatar_ncm(ncm), uf_origem=uf_origem, uf_destino=uf_destino,
              regime=regime, produto=p, sujeito_st=st)

    # ----- ENTRADA
    cfop_in = ("2.102 / 2.403" if inter else "1.102 / 1.403") if st else \
              ("2.102" if inter else "1.102")
    f.entrada = dict(
        cfop=cfop_in,
        cfop_obs=("Compra p/ comercializacao (1.102/2.102) e compra com ST (1.403/2.403)."
                  if st else "Compra para comercializacao."),
        cst=("CST conforme escrituracao e correspondencia ao CSOSN do fornecedor; "
             "ST: CST 10 / 60 / 70 conforme o caso") if st else "CST 00 (tributada integralmente)",
        aliquota=(f"{aliquota_interestadual(uf_origem, uf_destino)}% (interestadual)" if inter
                  else f"{uf_info['aliq']}% (aliquota interna modal de {uf_destino})"),
        credito=("Nao permitido. Optante do Simples Nacional nao se apropria de creditos "
                 "de ICMS na entrada (art. 23, LC 123/2006)." if simples else
                 ("Credito do ICMS proprio permitido; ICMS-ST retido nao gera credito "
                  "para o substituido." if st else "Credito de ICMS permitido (nao cumulatividade).")),
        obs=("Se a mercadoria vier de fora do Estado, verificar exigencia de antecipacao / "
             "recolhimento do diferencial de aliquotas na fronteira." if inter else ""),
    )

    # ----- SAIDA
    if st:
        cfop_out = "6.404 (ST) / 6.102" if uf_origem != uf_destino else "5.405 (ST) / 5.102"
        cst_out = "CSOSN 500 (ICMS cobrado anteriormente por ST)" if simples else \
                  "CST 60 (ICMS cobrado anteriormente por ST)"
        aliq_out = ("Imposto ja retido anteriormente - sem destaque de ICMS "
                    "(venda de substituido).")
    else:
        cfop_out = "6.102" if inter else "5.102"
        cst_out = "CSOSN 102 (sem permissao de credito)" if simples else "CST 00 (tributada integralmente)"
        aliq_out = f"{uf_info['aliq']}% (aliquota interna modal)"
    f.saida = dict(cfop=cfop_out, cst=cst_out, aliquota_icms=aliq_out,
                   fcp=(f"FCP/FECOEP: {uf_info['fcp']}%" if uf_info["fcp"] else "Sem FCP adicional cadastrado."),
                   cest=p["cest"])
    if st:
        a = st_uf
        mva = a["mva_orig"]
        txt = "A definir no anexo da UF" if mva is None else f"{mva}% (original)"
        if mva is not None and inter:
            aj = mva_ajustada(mva, aliquota_interestadual(uf_origem, uf_destino), uf_info["aliq"])
            txt += f" | ajustada interestadual: {aj:.2f}%"
        f.saida["mva"] = txt
        f.saida["base_calculo"] = ("Base = valor da operacao + IPI + frete + seguro + despesas, "
                                   "acrescida da MVA (ou PMC/PMPF quando houver).")

    # ----- PIS / COFINS
    tipo = p["pis_cofins"]["tipo"]
    if simples:
        pc = dict(regime="Simples Nacional (incluso na tributacao unificada do DAS)",
                  pis="Incluso no DAS", cofins="Incluso no DAS",
                  base="LC 123/2006, art. 18 (+ Res. CGSN 140/2018)")
        if tipo == "monofasico":
            pc["obs"] = "Monofasico: segregar a receita (PIS/COFINS ja recolhidos na origem)."
    elif tipo == "monofasico":
        pc = dict(regime=regime, pis="0% na revenda", cofins="0% na revenda",
                  base="Regime monofasico", obs=p["pis_cofins"]["obs"])
    elif regime == "Lucro Real":
        pc = dict(regime=regime, pis="1,65%", cofins="7,60%",
                  base=NORMAS_FEDERAIS["pis_cofins_nc"][0],
                  obs="Nao cumulativo, com direito a creditos.")
    else:
        pc = dict(regime=regime, pis="0,65%", cofins="3,00%",
                  base=NORMAS_FEDERAIS["pis_cofins_c"][0], obs="Cumulativo, sem creditos.")
    f.pis_cofins = pc

    # ----- IPI
    ipi = p["ipi"]
    f.ipi = dict(aliquota=("A consultar na TIPI" if ipi["aliq"] is None else f"{ipi['aliq']}%"),
                 base=ipi["base"],
                 obs=("Empresa comercial: IPI so incide se for equiparada a industrial. "
                      "Nao ha credito de IPI no Simples Nacional."))

    # ----- ALERTAS
    f.alertas = list(p["alertas"])
    if st and st_uf.get("conferir"):
        f.alertas.append(f"MVA/anexo de {uf_destino} marcados 'conferir': valide no RICMS vigente.")
    f.alertas.append("Reforma tributaria: em 2026 ha CBS 0,9% e IBS 0,1% (ano de teste, compensaveis, "
                     "LC 214/2025). PIS/COFINS/ICMS/ISS serao extintos gradualmente ate 2033.")

    # ----- FUNDAMENTOS
    f.fundamentos = [
        (f"Aliquota modal de {uf_destino}", UFS[uf_destino]["lei"]),
        (f"Regulamento do ICMS ({uf_destino})", st_uf["anexo"] if st else f"RICMS-{uf_destino}"),
        ("Estatuto da Microempresa e EPP", NORMAS_FEDERAIS["simples"][0] + " - " + NORMAS_FEDERAIS["simples"][1]),
        ("Regras gerais de ST", NORMAS_FEDERAIS["st"][0] + " - " + NORMAS_FEDERAIS["st"][1]),
        ("Lei Kandir", NORMAS_FEDERAIS["icms_geral"][0]),
        ("Aliquotas interestaduais", NORMAS_FEDERAIS["interestadual"][0]),
        ("DIFAL", NORMAS_FEDERAIS["difal"][0]),
        ("IPI / TIPI", NORMAS_FEDERAIS["ipi"][0]),
        ("PIS/COFINS", NORMAS_FEDERAIS["pis_cofins_nc"][0] + "; " + NORMAS_FEDERAIS["pis_cofins_c"][0]),
        ("Reforma tributaria", NORMAS_FEDERAIS["reforma"][0]),
        ("NF-e", NORMAS_FEDERAIS["nfe"][0]),
    ]
    return f


# ----------------------------------------------------------------------------
# 3. SIMULADOR DE ICMS-ST
# ----------------------------------------------------------------------------
def simular_st(valor: float, ipi: float, frete: float, mva_orig: float,
               uf_origem: str, uf_destino: str) -> dict:
    inter = uf_origem != uf_destino
    a_inter = aliquota_interestadual(uf_origem, uf_destino)
    a_int = UFS[uf_destino]["aliq"] + UFS[uf_destino]["fcp"]
    mva = mva_ajustada(mva_orig, a_inter, UFS[uf_destino]["aliq"]) if inter else mva_orig
    base_op = valor + ipi + frete
    base_st = base_op * (1 + mva / 100)
    icms_proprio = valor * (a_inter / 100) if inter else valor * UFS[uf_origem]["aliq"] / 100
    icms_st = base_st * a_int / 100 - icms_proprio
    return dict(mva_aplicada=round(mva, 2), base_st=round(base_st, 2),
                icms_proprio=round(icms_proprio, 2), icms_st=round(max(icms_st, 0), 2))


# ----------------------------------------------------------------------------
# 4. INTERFACE (Streamlit)
# ----------------------------------------------------------------------------
CSS = """
<style>
.card{border:1px solid #d9dee5;border-radius:8px;padding:14px 16px;background:#fff;margin-bottom:10px}
.tag{background:#eef2f7;border-radius:4px;padding:2px 8px;font-size:12px;color:#445}
.h{font-weight:700;color:#1d3557;margin-bottom:6px}
.alerta{background:#fff7e0;border-left:4px solid #f0a500;padding:8px 12px;margin:6px 0;border-radius:4px}
.lei{border-left:4px solid #1d3557;padding:6px 12px;margin:6px 0;background:#f6f8fb;border-radius:4px}
.k{color:#1d3557;font-weight:600}
</style>
"""


def _linhas(d: dict, rotulos: dict) -> str:
    out = ""
    for k, r in rotulos.items():
        if d.get(k):
            out += f"<div><span class='k'>{r}:</span> {d[k]}</div>"
    return out


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Analise Tributaria", page_icon="📑", layout="centered")
    st.markdown(CSS, unsafe_allow_html=True)
    carregar_base_extra()

    st.title("📑 Analise Tributaria por NCM")
    c1, c2 = st.columns([2, 1])
    ncm = c1.text_input("NCM", value="1905.90.90", help="Digite com ou sem pontos")
    regime = c2.selectbox("Regime do contribuinte", REGIMES)
    c3, c4 = st.columns(2)
    uf_o = c3.selectbox("UF de origem", list(UFS), index=list(UFS).index("PE"))
    uf_d = c4.selectbox("UF de destino", list(UFS), index=list(UFS).index("PE"))

    f = analisar(ncm, uf_o, uf_d, regime)
    if not f:
        st.warning("NCM nao encontrada na base. Adicione-a em PRODUTOS ou no base_extra.json.")
        return

    p = f.produto
    st.markdown(
        f"<div class='card'><span class='tag'>Ficha fiscal IA — NCM {f.ncm} • {uf_d}</span>"
        f"<div class='h' style='margin-top:8px'>{p['titulo']}</div>"
        f"<small>{p['capitulo']}</small></div>", unsafe_allow_html=True)

    col_e, col_s = st.columns(2)
    col_e.markdown("<div class='card'><div class='h'>⬇ ENTRADA</div>" + _linhas(f.entrada, dict(
        cfop="CFOP", cst="CST", aliquota="Aliquota ICMS", credito="Credito", obs="Obs")) + "</div>",
        unsafe_allow_html=True)
    col_s.markdown("<div class='card'><div class='h'>⬆ SAIDA</div>" + _linhas(f.saida, dict(
        cfop="CFOP", cst="CST/CSOSN", aliquota_icms="ICMS", mva="MVA", base_calculo="Base de calculo",
        fcp="FCP", cest="CEST")) + "</div>", unsafe_allow_html=True)

    col_p, col_i = st.columns(2)
    col_p.markdown("<div class='card'><div class='h'>PIS / COFINS</div>" + _linhas(f.pis_cofins, dict(
        regime="Regime", pis="PIS", cofins="COFINS", base="Base legal", obs="Obs")) + "</div>",
        unsafe_allow_html=True)
    col_i.markdown("<div class='card'><div class='h'>IPI</div>" + _linhas(f.ipi, dict(
        aliquota="Aliquota", base="Base legal", obs="Obs")) + "</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'><div class='h'>⚠ Alertas</div>" + "".join(
        f"<div class='alerta'>{a}</div>" for a in f.alertas) + "</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'><div class='h'>📚 Fundamentos legais</div>" + "".join(
        f"<div class='lei'><b>{t}</b><br>{d}</div>" for t, d in f.fundamentos) + "</div>",
        unsafe_allow_html=True)

    if f.sujeito_st:
        with st.expander("🧮 Simulador de ICMS-ST"):
            mva_o = p["st"]["ufs"][uf_d]["mva_orig"] or 0.0
            a, b, c = st.columns(3)
            v = a.number_input("Valor dos produtos (R$)", value=1000.0)
            i = b.number_input("IPI (R$)", value=0.0)
            fr = c.number_input("Frete (R$)", value=0.0)
            mva_in = st.number_input("MVA original (%)", value=float(mva_o))
            r = simular_st(v, i, fr, mva_in, uf_o, uf_d)
            st.json(r)

    d1, d2 = st.columns(2)
    d1.download_button("⬇ Exportar ficha (JSON)", json.dumps(
        {k: v for k, v in f.__dict__.items() if k != "produto"}, ensure_ascii=False, indent=2),
        file_name=f"ficha_{limpar_ncm(ncm)}.json")
    if d2.button("Nova analise"):
        st.rerun()

    st.caption("Base inicial para estudo. Valide aliquotas, MVA e artigos nas fontes oficiais.")


if __name__ == "__main__":
    main()
