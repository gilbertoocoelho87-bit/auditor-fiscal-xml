```python
import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io
import os
import re
from datetime import datetime

# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Auditor Fiscal de Divergências",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Auditor PGDAS - Identificador de Notas Incorretas")

st.write(
    "Sistema de auditoria de XMLs para identificação de possíveis "
    "divergências tributárias por NCM, CEST, CFOP, CST/CSOSN e UF."
)

# ============================================================
# CONSTANTES
# ============================================================

UF_CODIGOS = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}

# ============================================================
# BASE TRIBUTÁRIA INICIAL
# ============================================================

COLUNAS_BASE = [
    "UF_ORIGEM",
    "UF_DESTINO",
    "NCM",
    "CEST",
    "CFOP",
    "REGIME",
    "ICMS",
    "ICMS_ST",
    "DIFAL",
    "FCP",
    "PIS_COFINS",
    "IPI",
    "IBS_CBS",
    "ALIQUOTA_ICMS",
    "MVA",
    "REDUCAO_BASE",
    "CODIGO_BENEFICIO",
    "LEGISLACAO",
    "FUNDAMENTO_LEGAL",
    "OBSERVACAO"
]

ARQUIVO_BASE = "base_tributaria.csv"


def criar_base_inicial():
    """
    Cria uma base vazia estruturada.
    A base deve ser alimentada com regras tributárias oficiais.
    """

    if not os.path.exists(ARQUIVO_BASE):

        df = pd.DataFrame(columns=COLUNAS_BASE)

        df.to_csv(
            ARQUIVO_BASE,
            index=False,
            encoding="utf-8-sig",
            sep=";"
        )


def carregar_base():
    criar_base_inicial()

    try:
        df = pd.read_csv(
            ARQUIVO_BASE,
            sep=";",
            dtype=str,
            encoding="utf-8-sig"
        )

        df = df.fillna("")

        return df

    except Exception:
        return pd.DataFrame(columns=COLUNAS_BASE)


BASE_TRIBUTARIA = carregar_base()

# ============================================================
# NORMALIZAÇÃO
# ============================================================


def limpar_numero(valor):

    if valor is None:
        return ""

    return str(valor).strip()


def normalizar_ncm(valor):

    valor = limpar_numero(valor)

    valor = re.sub(r"\D", "", valor)

    return valor.zfill(8) if valor else ""


def normalizar_cest(valor):

    valor = limpar_numero(valor)

    valor = re.sub(r"\D", "", valor)

    return valor


def normalizar_cfop(valor):

    valor = limpar_numero(valor)

    valor = re.sub(r"\D", "", valor)

    return valor


def texto_xml(elemento):

    if elemento is None:
        return ""

    return elemento.text.strip() if elemento.text else ""


def tag_final(elemento):

    return elemento.tag.split("}")[-1]


def encontrar_elemento(parent, nome):

    for elemento in parent.iter():

        if tag_final(elemento) == nome:

            return elemento

    return None


def encontrar_texto(parent, nome):

    elemento = encontrar_elemento(parent, nome)

    return texto_xml(elemento)


# ============================================================
# LEITURA DO XML
# ============================================================


def identificar_uf(root):

    cuf = encontrar_texto(root, "cUF")

    return UF_CODIGOS.get(cuf, "")


def identificar_numero_nfe(root):

    return encontrar_texto(root, "nNF")


def identificar_serie(root):

    return encontrar_texto(root, "serie")


def identificar_data(root):

    valor = encontrar_texto(root, "dhEmi")

    if not valor:

        valor = encontrar_texto(root, "dEmi")

    return valor


def identificar_destino(root):

    # Primeiramente tenta UF do destinatário
    dest = None

    for elemento in root.iter():

        if tag_final(elemento) == "dest":

            dest = elemento

            break

    if dest is not None:

        uf = encontrar_texto(dest, "UF")

        if uf:

            return uf

    return ""


# ============================================================
# LEITURA DOS PRODUTOS
# ============================================================


def extrair_produtos(root):

    produtos = []

    for det in root.iter():

        if tag_final(det) != "det":

            continue

        prod = None

        for elemento in det:

            if tag_final(elemento) == "prod":

                prod = elemento
                break

        if prod is None:

            continue

        xprod = encontrar_texto(prod, "xProd")
        ncm = normalizar_ncm(encontrar_texto(prod, "NCM"))
        cest = normalizar_cest(encontrar_texto(prod, "CEST"))
        cfop = normalizar_cfop(encontrar_texto(prod, "CFOP"))

        quantidade = encontrar_texto(prod, "qCom")
        valor_unitario = encontrar_texto(prod, "vUnCom")
        valor_total = encontrar_texto(prod, "vProd")

        cst = ""
        csosn = ""

        for imposto in det.iter():

            nome = tag_final(imposto)

            if nome == "CST":

                cst = texto_xml(imposto)

            if nome == "CSOSN":

                csosn = texto_xml(imposto)

        # ICMS
        icms_cst = cst
        icms_csosn = csosn

        # PIS
        pis_cst = ""

        for elemento in det.iter():

            if tag_final(elemento) == "PIS":

                for filho in elemento.iter():

                    nome = tag_final(filho)

                    if nome in ["CST"]:

                        pis_cst = texto_xml(filho)
                        break

        # COFINS
        cofins_cst = ""

        for elemento in det.iter():

            if tag_final(elemento) == "COFINS":

                for filho in elemento.iter():

                    nome = tag_final(filho)

                    if nome == "CST":

                        cofins_cst = texto_xml(filho)
                        break

        # IPI
        ipi_cst = ""

        for elemento in det.iter():

            if tag_final(elemento) == "IPI":

                for filho in elemento.iter():

                    if tag_final(filho) == "CST":

                        ipi_cst = texto_xml(filho)
                        break

        produtos.append({
            "Produto": xprod,
            "NCM": ncm,
            "CEST": cest,
            "CFOP": cfop,
            "Quantidade": quantidade,
            "Valor Unitário": valor_unitario,
            "Valor Produto": valor_total,
            "CST ICMS": icms_cst,
            "CSOSN ICMS": icms_csosn,
            "CST PIS": pis_cst,
            "CST COFINS": cofins_cst,
            "CST IPI": ipi_cst
        })

    return produtos


# ============================================================
# PESQUISA NA BASE TRIBUTÁRIA
# ============================================================


def buscar_regra(
    uf_origem,
    uf_destino,
    ncm,
    cest,
    cfop
):

    if BASE_TRIBUTARIA.empty:

        return None

    base = BASE_TRIBUTARIA.copy()

    base = base.fillna("")

    # Normalização
    for coluna in [
        "UF_ORIGEM",
        "UF_DESTINO",
        "NCM",
        "CEST",
        "CFOP"
    ]:

        if coluna not in base.columns:

            base[coluna] = ""

    base["NCM"] = base["NCM"].apply(normalizar_ncm)
    base["CEST"] = base["CEST"].apply(normalizar_cest)
    base["CFOP"] = base["CFOP"].apply(normalizar_cfop)

    # ========================================================
    # PRIORIDADE 1
    # UF + NCM + CEST + CFOP
    # ========================================================

    filtro = base[
        (base["UF_DESTINO"].isin(["", uf_destino]))
        &
        (base["UF_ORIGEM"].isin(["", uf_origem]))
        &
        (base["NCM"].isin(["", ncm]))
        &
        (base["CEST"].isin(["", cest]))
        &
        (base["CFOP"].isin(["", cfop]))
    ]

    if not filtro.empty:

        return filtro.iloc[0].to_dict()

    # ========================================================
    # PRIORIDADE 2
    # UF + NCM
    # ========================================================

    filtro = base[
        (base["UF_DESTINO"].isin(["", uf_destino]))
        &
        (base["NCM"] == ncm)
    ]

    if not filtro.empty:

        return filtro.iloc[0].to_dict()

    # ========================================================
    # PRIORIDADE 3
    # NCM
    # ========================================================

    filtro = base[
        base["NCM"] == ncm
    ]

    if not filtro.empty:

        return filtro.iloc[0].to_dict()

    return None


# ============================================================
# AUDITORIA
# ============================================================


def auditar_xml(xml_file):

    resultados = []

    try:

        xml_data = xml_file.read()

        root = ET.fromstring(xml_data)

        uf_origem = identificar_uf(root)
        uf_destino = identificar_destino(root)

        numero_nfe = identificar_numero_nfe(root)
        serie = identificar_serie(root)
        data_emissao = identificar_data(root)

        produtos = extrair_produtos(root)

        if not produtos:

            return []

        for produto in produtos:

            ncm = produto["NCM"]
            cest = produto["CEST"]
            cfop = produto["CFOP"]

            regra = buscar_regra(
                uf_origem,
                uf_destino,
                ncm,
                cest,
                cfop
            )

            divergencias = []

            status = "SEM REGRA"

            if regra:

                status = "ANALISADO"

                icms_regra = regra.get("ICMS", "")
                icms_st_regra = regra.get("ICMS_ST", "")
                difal_regra = regra.get("DIFAL", "")
                pis_cofins_regra = regra.get("PIS_COFINS", "")
                ipi_regra = regra.get("IPI", "")
                ibs_cbs_regra = regra.get("IBS_CBS", "")

                # =================================================
                # ICMS-ST
                # =================================================

                if icms_st_regra.upper() == "SIM":

                    cst = produto["CST ICMS"]
                    csosn = produto["CSOSN ICMS"]

                    cst_normal = [
                        "00",
                        "20",
                        "40",
                        "41",
                        "50",
                        "90"
                    ]

                    if cst in cst_normal:

                        divergencias.append(
                            f"Possível ICMS-ST não informado. "
                            f"CST encontrado: {cst}."
                        )

                # =================================================
                # PIS/COFINS MONOFÁSICO
                # =================================================

                if pis_cofins_regra.upper() == "MONOFÁSICO":

                    pis_cst = produto["CST PIS"]
                    cofins_cst = produto["CST COFINS"]

                    if pis_cst not in ["04", "06", ""]:
                        divergencias.append(
                            f"PIS possivelmente incompatível "
                            f"com regra monofásica. CST: {pis_cst}"
                        )

                    if cofins_cst not in ["04", "06", ""]:
                        divergencias.append(
                            f"COFINS possivelmente incompatível "
                            f"com regra monofásica. CST: {cofins_cst}"
                        )

                # =================================================
                # DIFAL
                # =================================================

                if difal_regra.upper() == "SIM":

                    if uf_origem != uf_destino:

                        divergencias.append(
                            "Operação interestadual com possível incidência "
                            "de DIFAL conforme regra cadastrada."
                        )

                # =================================================
                # IBS/CBS
                # =================================================

                if ibs_cbs_regra:

                    ibs_cbs_info = ibs_cbs_regra

                else:

                    ibs_cbs_info = "Não informado"

            else:

                icms_regra = ""
                icms_st_regra = ""
                difal_regra = ""
                pis_cofins_regra = ""
                ipi_regra = ""
                ibs_cbs_info = ""

            if divergencias:

                status = "❌ INCORRETO"

            elif regra:

                status = "✅ ANALISADO"

            resultados.append({

                "Arquivo": xml_file.name,
                "NF-e": numero_nfe,
                "Série": serie,
                "Data Emissão": data_emissao,

                "UF Origem": uf_origem,
                "UF Destino": uf_destino,

                "Produto": produto["Produto"],
                "NCM": ncm,
                "CEST": cest,
                "CFOP": cfop,

                "Quantidade": produto["Quantidade"],
                "Valor Produto": produto["Valor Produto"],

                "CST ICMS": produto["CST ICMS"],
                "CSOSN ICMS": produto["CSOSN ICMS"],

                "CST PIS": produto["CST PIS"],
                "CST COFINS": produto["CST COFINS"],

                "CST IPI": produto["CST IPI"],

                "Regra ICMS": icms_regra,
                "ICMS-ST": icms_st_regra,
                "DIFAL": difal_regra,
                "PIS/COFINS": pis_cofins_regra,
                "IPI": ipi_regra,
                "IBS/CBS": ibs_cbs_info,

                "Alíquota ICMS": regra.get(
                    "ALIQUOTA_ICMS", ""
                ) if regra else "",

                "MVA": regra.get(
                    "MVA", ""
                ) if regra else "",

                "Redução Base": regra.get(
                    "REDUCAO_BASE", ""
                ) if regra else "",

                "Código Benefício": regra.get(
                    "CODIGO_BENEFICIO", ""
                ) if regra else "",

                "Legislação": regra.get(
                    "LEGISLACAO", ""
                ) if regra else "",

                "Fundamento Legal": regra.get(
                    "FUNDAMENTO_LEGAL", ""
                ) if regra else "",

                "Observação Legal": regra.get(
                    "OBSERVACAO", ""
                ) if regra else "",

                "Status": status,

                "Divergência Encontrada":
                    " | ".join(divergencias)
                    if divergencias
                    else "Nenhuma divergência identificada"

            })

    except Exception as erro:

        st.error(
            f"Erro ao processar {xml_file.name}: {erro}"
        )

    return resultados


# ============================================================
# UPLOAD XML
# ============================================================

st.subheader("📂 Importação dos XMLs")

uploaded_files = st.file_uploader(
    "Arraste e solte os XMLs das NF-e aqui",
    type=["xml"],
    accept_multiple_files=True
)

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Configurações")

    st.write(
        "A auditoria utiliza a base tributária "
        "cadastrada no arquivo:"
    )

    st.code(ARQUIVO_BASE)

    st.divider()

    st.write("📚 Base atual")

    if BASE_TRIBUTARIA.empty:

        st.warning(
            "A base tributária ainda está vazia."
        )

    else:

        st.success(
            f"{len(BASE_TRIBUTARIA)} regras cadastradas."
        )

    st.divider()

    st.write("Estados disponíveis")

    st.write(
        ", ".join(sorted(UF_CODIGOS.values()))
    )


# ============================================================
# IMPORTAÇÃO DA BASE TRIBUTÁRIA
# ============================================================

st.subheader("📚 Base Tributária")

arquivo_base_upload = st.file_uploader(
    "Se possuir uma base tributária atualizada, importe aqui",
    type=["csv", "xlsx"],
    key="base_tributaria_upload"
)

if arquivo_base_upload:

    try:

        if arquivo_base_upload.name.lower().endswith(".csv"):

            nova_base = pd.read_csv(
                arquivo_base_upload,
                sep=";",
                dtype=str,
                encoding="utf-8-sig"
            )

        else:

            nova_base = pd.read_excel(
                arquivo_base_upload,
                dtype=str
            )

        nova_base = nova_base.fillna("")

        st.success(
            f"Base carregada: {len(nova_base)} regras."
        )

        st.dataframe(
            nova_base,
            use_container_width=True
        )

        csv_nova_base = nova_base.to_csv(
            index=False,
            sep=";",
            encoding="utf-8-sig"
        )

        st.download_button(
            "⬇️ Baixar base tributária",
            data=csv_nova_base,
            file_name="base_tributaria_atualizada.csv",
            mime="text/csv"
        )

    except Exception as erro:

        st.error(
            f"Erro ao carregar base tributária: {erro}"
        )


# ============================================================
# AUDITORIA
# ============================================================

if uploaded_files:

    st.divider()

    st.subheader("🔎 Processamento")

    resultados_finais = []

    barra = st.progress(0)

    total = len(uploaded_files)

    for indice, arquivo in enumerate(uploaded_files):

        resultados = auditar_xml(arquivo)

        resultados_finais.extend(resultados)

        progresso = int(
            ((indice + 1) / total) * 100
        )

        barra.progress(progresso)

    if resultados_finais:

        df_final = pd.DataFrame(resultados_finais)

        st.success(
            f"✅ Auditoria concluída. "
            f"{len(uploaded_files)} XML(s) processado(s)."
        )

        # ====================================================
        # INDICADORES
        # ====================================================

        total_itens = len(df_final)

        incorretos = len(
            df_final[
                df_final["Status"] == "❌ INCORRETO"
            ]
        )

        analisados = len(
            df_final[
                df_final["Status"] == "✅ ANALISADO"
            ]
        )

        sem_regra = len(
            df_final[
                df_final["Status"] == "SEM REGRA"
            ]
        )

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Produtos analisados",
            total_itens
        )

        col2.metric(
            "Possíveis divergências",
            incorretos
        )

        col3.metric(
            "Regras encontradas",
            analisados
        )

        col4.metric(
            "Sem regra cadastrada",
            sem_regra
        )

        # ====================================================
        # ABAS
        # ====================================================

        aba_geral, aba_erros, aba_sem_regra, aba_legislacao = st.tabs(
            [
                "📋 Todos os Produtos",
                "⚠️ NOTAS INCORRETAS / ERROS",
                "❓ NCMs SEM REGRA",
                "📚 LEGISLAÇÃO / BASE"
            ]
        )

        # ====================================================
        # ABA GERAL
        # ====================================================

        with aba_geral:

            st.subheader(
                "📋 Painel Geral de Auditoria"
            )

            st.dataframe(
                df_final,
                use_container_width=True,
                height=600
            )

        # ====================================================
        # ABA ERROS
        # ====================================================

        with aba_erros:

            st.subheader(
                "⚠️ Produtos com possíveis divergências"
            )

            df_erros = df_final[
                df_final["Status"] == "❌ INCORRETO"
            ]

            if df_erros.empty:

                st.success(
                    "Nenhuma divergência foi identificada "
                    "com as regras cadastradas."
                )

            else:

                st.dataframe(
                    df_erros,
                    use_container_width=True,
                    height=600
                )

        # ====================================================
        # ABA SEM REGRA
        # ====================================================

        with aba_sem_regra:

            st.subheader(
                "❓ NCMs que ainda não possuem regra cadastrada"
            )

            df_sem_regra = df_final[
                df_final["Status"] == "SEM REGRA"
            ]

            if df_sem_regra.empty:

                st.success(
                    "Todos os produtos encontrados "
                    "possuem alguma regra cadastrada."
                )

            else:

                colunas = [
                    "UF Origem",
                    "UF Destino",
                    "Produto",
                    "NCM",
                    "CEST",
                    "CFOP"
                ]

                st.dataframe(
                    df_sem_regra[colunas].drop_duplicates(),
                    use_container_width=True
                )

                st.info(
                    "Esses NCMs precisam ser incluídos "
                    "na base tributária oficial antes "
                    "de uma conclusão fiscal."
                )

        # ====================================================
        # ABA LEGISLAÇÃO
        # ====================================================

        with aba_legislacao:

            st.subheader(
                "📚 Base de Legislação Tributária"
            )

            if BASE_TRIBUTARIA.empty:

                st.warning(
                    "Nenhuma regra foi cadastrada."
                )

            else:

                st.dataframe(
                    BASE_TRIBUTARIA,
                    use_container_width=True,
                    height=600
                )

        # ====================================================
        # EXPORTAÇÃO EXCEL
        # ====================================================

        st.divider()

        st.subheader(
            "📥 Exportar Auditoria"
        )

        buffer = io.BytesIO()

        with pd.ExcelWriter(
            buffer,
            engine="openpyxl"
        ) as writer:

            df_final.to_excel(
                writer,
                index=False,
                sheet_name="Auditoria"
            )

            df_erros = df_final[
                df_final["Status"] == "❌ INCORRETO"
            ]

            df_erros.to_excel(
                writer,
                index=False,
                sheet_name="Divergencias"
            )

            df_sem_regra = df_final[
                df_final["Status"] == "SEM REGRA"
            ]

            df_sem_regra.to_excel(
                writer,
                index=False,
                sheet_name="Sem_Regra"
            )

        buffer.seek(0)

        st.download_button(
            label="⬇️ BAIXAR AUDITORIA EM EXCEL",
            data=buffer,
            file_name=(
                "auditoria_tributaria_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )

    else:

        st.warning(
            "Os XMLs foram carregados, mas nenhum produto "
            "foi encontrado para análise."
        )


# ============================================================
# MODELO DA BASE TRIBUTÁRIA
# ============================================================

st.divider()

st.subheader(
    "🧾 Modelo da Base Tributária"
)

st.write(
    "Use este modelo para alimentar as regras tributárias "
    "por NCM, CEST, UF, CFOP e legislação."
)

modelo_base = pd.DataFrame(
    [
        {
            "UF_ORIGEM": "SP",
            "UF_DESTINO": "PE",
            "NCM": "00000000",
            "CEST": "",
            "CFOP": "5102",
            "REGIME": "Simples Nacional",
            "ICMS": "NORMAL",
            "ICMS_ST": "NAO",
            "DIFAL": "NAO",
            "FCP": "NAO",
            "PIS_COFINS": "NORMAL",
            "IPI": "NORMAL",
            "IBS_CBS": "ANALISAR",
            "ALIQUOTA_ICMS": "",
            "MVA": "",
            "REDUCAO_BASE": "",
            "CODIGO_BENEFICIO": "",
            "LEGISLACAO": "",
            "FUNDAMENTO_LEGAL": "",
            "OBSERVACAO": ""
        }
    ],
    columns=COLUNAS_BASE
)

st.dataframe(
    modelo_base,
    use_container_width=True
)

csv_modelo = modelo_base.to_csv(
    index=False,
    sep=";",
    encoding="utf-8-sig"
)

st.download_button(
    "⬇️ Baixar modelo da Base Tributária",
    data=csv_modelo,
    file_name="modelo_base_tributaria.csv",
    mime="text/csv"
)

# ============================================================
# RODAPÉ
# ============================================================

st.divider()

st.caption(
    "Auditor Fiscal de Divergências — análise automatizada "
    "de XML. A indicação de divergência depende da qualidade "
    "e atualização da base tributária utilizada."
)
```
