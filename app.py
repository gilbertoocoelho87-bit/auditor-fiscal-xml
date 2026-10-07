import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io
import os
import re
from datetime import datetime

# ============================================================
# AUDITOR FISCAL XML - V2
# ============================================================

st.set_page_config(
    page_title="Auditor Fiscal de Divergências",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Auditor Fiscal de Divergências - V2")
st.caption(
    "Leitura de NF-e XML + auditoria automática de inconsistências "
    "e comparação com base tributária."
)

# ============================================================
# CONSTANTES
# ============================================================

UF_CODIGOS = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
    "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
    "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
    "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
    "52": "GO", "53": "DF"
}

UFS = sorted(UF_CODIGOS.values())

COLUNAS_BASE = [
    "UF_ORIGEM", "UF_DESTINO", "NCM", "CEST", "CFOP", "REGIME",
    "ICMS", "ICMS_ST", "DIFAL", "FCP", "PIS_COFINS", "IPI",
    "IBS_CBS", "ALIQUOTA_ICMS", "MVA", "REDUCAO_BASE",
    "CODIGO_BENEFICIO", "LEGISLACAO", "FUNDAMENTO_LEGAL",
    "OBSERVACAO"
]

ARQUIVO_BASE = "base_tributaria.csv"

# ============================================================
# FUNÇÕES BÁSICAS
# ============================================================

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

# ============================================================
# BASE TRIBUTÁRIA
# ============================================================

def criar_base():
    if not os.path.exists(ARQUIVO_BASE):
        pd.DataFrame(columns=COLUNAS_BASE).to_csv(
            ARQUIVO_BASE,
            index=False,
            sep=";",
            encoding="utf-8-sig"
        )

def carregar_base():
    criar_base()
    try:
        df = pd.read_csv(
            ARQUIVO_BASE,
            sep=";",
            dtype=str,
            encoding="utf-8-sig"
        ).fillna("")
    except Exception:
        return pd.DataFrame(columns=COLUNAS_BASE)

    for col in COLUNAS_BASE:
        if col not in df.columns:
            df[col] = ""

    return df[COLUNAS_BASE]

BASE = carregar_base()

# ============================================================
# LEITURA DA NF-E
# ============================================================

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

# ============================================================
# EXTRAÇÃO DOS ITENS
# ============================================================

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
            "CST ICMS": "",
            "CSOSN ICMS": "",
            "Origem ICMS": "",
            "Modalidade BC ICMS": "",
            "Alíquota ICMS": "",
            "Valor ICMS": "",
            "CST PIS": "",
            "CST COFINS": "",
            "CST IPI": "",
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

        # PIS
        for el in det.iter():
            if tag_final(el) == "PIS":
                for filho in el.iter():
                    if tag_final(filho) == "CST":
                        item["CST PIS"] = texto(filho)
                        break

        # COFINS
        for el in det.iter():
            if tag_final(el) == "COFINS":
                for filho in el.iter():
                    if tag_final(filho) == "CST":
                        item["CST COFINS"] = texto(filho)
                        break

        # IPI
        for el in det.iter():
            if tag_final(el) == "IPI":
                for filho in el.iter():
                    if tag_final(filho) == "CST":
                        item["CST IPI"] = texto(filho)
                        break

        itens.append(item)

    return itens

# ============================================================
# REGRAS AUTOMÁTICAS DE CONSISTÊNCIA
# ============================================================

CST_ICMS_VALIDOS = {
    "00", "10", "20", "30", "40", "41", "50", "51", "60",
    "70", "90"
}

CSOSN_VALIDOS = {
    "101", "102", "103", "201", "202", "203", "300", "400", "500", "900"
}

CST_PIS_VALIDOS = {f"{i:02d}" for i in range(1, 100)}
CST_COFINS_VALIDOS = {f"{i:02d}" for i in range(1, 100)}

def adicionar_erro(lista, tipo, descricao, gravidade="ALTA", regra=""):
    lista.append({
        "Tipo": tipo,
        "Gravidade": gravidade,
        "Descrição": descricao,
        "Regra/Referência": regra
    })

def auditoria_estrutural(item, nfe):
    erros = []
    avisos = []

    ncm = item["NCM"]
    cest = item["CEST"]
    cfop = item["CFOP"]
    cst = item["CST ICMS"]
    csosn = item["CSOSN ICMS"]
    pis = item["CST PIS"]
    cofins = item["CST COFINS"]

    # NCM
    if not ncm:
        adicionar_erro(
            erros, "NCM",
            "NCM não informado no item.",
            "ALTA"
        )
    elif len(ncm) != 8:
        adicionar_erro(
            erros, "NCM",
            f"NCM '{ncm}' possui {len(ncm)} dígitos; o NCM deve possuir 8 dígitos.",
            "ALTA"
        )

    # CFOP
    if not cfop:
        adicionar_erro(
            erros, "CFOP",
            "CFOP não informado no item.",
            "ALTA"
        )
    elif len(cfop) != 4:
        adicionar_erro(
            erros, "CFOP",
            f"CFOP '{cfop}' possui tamanho inválido.",
            "ALTA"
        )

    # CEST
    if cest and len(cest) != 7:
        adicionar_erro(
            erros, "CEST",
            f"CEST '{cest}' possui tamanho inválido.",
            "MÉDIA"
        )

    # ICMS / CSOSN
    if cst and cst not in CST_ICMS_VALIDOS:
        adicionar_erro(
            erros, "CST ICMS",
            f"CST ICMS '{cst}' não está no conjunto padrão esperado.",
            "ALTA"
        )

    if csosn and csosn not in CSOSN_VALIDOS:
        adicionar_erro(
            erros, "CSOSN",
            f"CSOSN '{csosn}' não está no conjunto padrão esperado.",
            "ALTA"
        )

    # Regra básica CST x CSOSN
    if cst and csosn:
        adicionar_erro(
            erros, "ICMS",
            f"O item apresenta CST '{cst}' e CSOSN '{csosn}' simultaneamente. "
            "Verifique a estrutura do XML e o regime tributário.",
            "ALTA"
        )

    # Simples Nacional normalmente utiliza CSOSN
    if nfe["CNPJ Emitente"] and csosn:
        pass

    # PIS / COFINS
    if pis and pis not in CST_PIS_VALIDOS:
        adicionar_erro(
            erros, "PIS",
            f"CST PIS '{pis}' inválido.",
            "ALTA"
        )

    if cofins and cofins not in CST_COFINS_VALIDOS:
        adicionar_erro(
            erros, "COFINS",
            f"CST COFINS '{cofins}' inválido.",
            "ALTA"
        )

    # Operação interestadual
    uf_o = nfe["UF Origem"]
    uf_d = nfe["UF Destino"]

    if uf_o and uf_d and uf_o != uf_d:
        if cfop.startswith(("5", "6")):
            pass
        else:
            adicionar_erro(
                erros, "CFOP",
                f"Operação entre {uf_o} e {uf_d} com CFOP '{cfop}'. "
                "Verifique se o CFOP corresponde à operação interestadual.",
                "MÉDIA"
            )

    # Alíquota negativa/impossível
    if item["Alíquota ICMS"]:
        try:
            aliq = float(item["Alíquota ICMS"].replace(",", "."))
            if aliq < 0 or aliq > 100:
                adicionar_erro(
                    erros, "ICMS",
                    f"Alíquota ICMS '{item['Alíquota ICMS']}' fora do intervalo esperado.",
                    "ALTA"
                )
        except ValueError:
            adicionar_erro(
                erros, "ICMS",
                f"Alíquota ICMS '{item['Alíquota ICMS']}' não é numérica.",
                "ALTA"
            )

    return erros, avisos

# ============================================================
# BUSCA NA BASE TRIBUTÁRIA
# ============================================================

def buscar_regra(uf_origem, uf_destino, ncm, cest, cfop):
    if BASE.empty:
        return None

    base = BASE.copy().fillna("")

    for col in ["UF_ORIGEM", "UF_DESTINO"]:
        base[col] = base[col].astype(str).str.upper().str.strip()

    base["NCM"] = base["NCM"].apply(normalizar_ncm)
    base["CEST"] = base["CEST"].apply(normalizar_cest)
    base["CFOP"] = base["CFOP"].apply(normalizar_cfop)

    # Mais específico primeiro
    filtros = [
        (
            (base["UF_ORIGEM"].isin(["", uf_origem])) &
            (base["UF_DESTINO"].isin(["", uf_destino])) &
            (base["NCM"] == ncm) &
            (base["CEST"].isin(["", cest])) &
            (base["CFOP"].isin(["", cfop]))
        ),
        (
            (base["UF_DESTINO"].isin(["", uf_destino])) &
            (base["NCM"] == ncm)
        ),
        (
            base["NCM"] == ncm
        )
    ]

    for filtro in filtros:
        achou = base[filtro]
        if not achou.empty:
            return achou.iloc[0].to_dict()

    return None

# ============================================================
# COMPARAÇÃO COM BASE TRIBUTÁRIA
# ============================================================

def comparar_com_regra(item, regra):
    erros = []

    if not regra:
        return erros

    icms_st = normalizar(regra.get("ICMS_ST", "")).upper()
    pis_cofins = normalizar(regra.get("PIS_COFINS", "")).upper()

    cst = item["CST ICMS"]
    csosn = item["CSOSN ICMS"]
    pis = item["CST PIS"]
    cofins = item["CST COFINS"]

    # ICMS-ST
    if icms_st in {"SIM", "ST", "YES"}:
        if cst in {"00", "20", "40", "41", "90"} and not csosn:
            adicionar_erro(
                erros,
                "ICMS-ST",
                f"A base tributária indica ICMS-ST, porém o XML apresenta CST ICMS '{cst}'. "
                "Verifique a aplicação da substituição tributária.",
                "ALTA",
                regra.get("FUNDAMENTO_LEGAL", "")
            )

    # Monofásico
    if pis_cofins in {"MONOFÁSICO", "MONOFASICO", "MONOFÁSICA", "MONOFASICA"}:
        if pis not in {"04", "06", ""}:
            adicionar_erro(
                erros,
                "PIS",
                f"A base indica PIS/COFINS monofásico, mas o XML apresenta CST PIS '{pis}'.",
                "ALTA",
                regra.get("FUNDAMENTO_LEGAL", "")
            )

        if cofins not in {"04", "06", ""}:
            adicionar_erro(
                erros,
                "COFINS",
                f"A base indica PIS/COFINS monofásico, mas o XML apresenta CST COFINS '{cofins}'.",
                "ALTA",
                regra.get("FUNDAMENTO_LEGAL", "")
            )

    return erros

# ============================================================
# PROCESSAMENTO
# ============================================================

def processar_xml(arquivo):
    resultados = []
    detalhes_erros = []

    try:
        conteudo = arquivo.read()
        root = ET.fromstring(conteudo)
        nfe = extrair_dados_nfe(root)
        itens = extrair_itens(root)

        for item in itens:
            erros, avisos = auditoria_estrutural(item, nfe)
            regra = buscar_regra(
                nfe["UF Origem"],
                nfe["UF Destino"],
                item["NCM"],
                item["CEST"],
                item["CFOP"]
            )

            erros_regra = comparar_com_regra(item, regra)
            erros.extend(erros_regra)

            if erros:
                status = "❌ ERRO ENCONTRADO"
            elif regra:
                status = "✅ CONFORME COM A BASE"
            else:
                status = "⚠️ SEM REGRA TRIBUTÁRIA"

            fundamento = regra.get("FUNDAMENTO_LEGAL", "") if regra else ""
            legislacao = regra.get("LEGISLACAO", "") if regra else ""

            resultados.append({
                "Arquivo": arquivo.name,
                "NF-e": nfe["NF-e"],
                "Item": item["Item"],
                "UF Origem": nfe["UF Origem"],
                "UF Destino": nfe["UF Destino"],
                "Produto": item["Produto"],
                "NCM": item["NCM"],
                "CEST": item["CEST"],
                "CFOP": item["CFOP"],
                "CST ICMS": item["CST ICMS"],
                "CSOSN ICMS": item["CSOSN ICMS"],
                "CST PIS": item["CST PIS"],
                "CST COFINS": item["CST COFINS"],
                "CST IPI": item["CST IPI"],
                "Alíquota ICMS XML": item["Alíquota ICMS"],
                "Valor ICMS XML": item["Valor ICMS"],
                "Regra ICMS": regra.get("ICMS", "") if regra else "",
                "ICMS-ST Base": regra.get("ICMS_ST", "") if regra else "",
                "PIS/COFINS Base": regra.get("PIS_COFINS", "") if regra else "",
                "DIFAL Base": regra.get("DIFAL", "") if regra else "",
                "IBS/CBS Base": regra.get("IBS_CBS", "") if regra else "",
                "Legislação": legislacao,
                "Fundamento Legal": fundamento,
                "Status": status,
                "Quantidade de Erros": len(erros)
            })

            for erro in erros:
                detalhes_erros.append({
                    "Arquivo": arquivo.name,
                    "NF-e": nfe["NF-e"],
                    "Item": item["Item"],
                    "UF Origem": nfe["UF Origem"],
                    "UF Destino": nfe["UF Destino"],
                    "Produto": item["Produto"],
                    "NCM": item["NCM"],
                    "CEST": item["CEST"],
                    "CFOP": item["CFOP"],
                    "CST ICMS": item["CST ICMS"],
                    "CSOSN ICMS": item["CSOSN ICMS"],
                    "CST PIS": item["CST PIS"],
                    "CST COFINS": item["CST COFINS"],
                    "Tipo de Erro": erro["Tipo"],
                    "Gravidade": erro["Gravidade"],
                    "ERRO ENCONTRADO": erro["Descrição"],
                    "Regra/Referência": erro["Regra/Referência"],
                    "Legislação": legislacao,
                    "Fundamento Legal": fundamento
                })

    except Exception as exc:
        st.error(f"Erro ao ler {arquivo.name}: {exc}")

    return resultados, detalhes_erros

# ============================================================
# INTERFACE
# ============================================================

with st.sidebar:
    st.header("⚙️ Configurações")
    st.write("Base tributária:")
    st.code(ARQUIVO_BASE)

    if BASE.empty:
        st.warning("Base tributária sem regras cadastradas.")
    else:
        st.success(f"{len(BASE)} regra(s) carregada(s).")

    st.divider()
    st.write("Estados:")
    st.write(", ".join(UFS))

st.subheader("📂 Importar XMLs")
arquivos = st.file_uploader(
    "Arraste os XMLs das NF-e para esta área",
    type=["xml"],
    accept_multiple_files=True
)

# Upload opcional da base
st.subheader("📚 Base tributária")
upload_base = st.file_uploader(
    "Opcional: carregue uma base CSV ou Excel para esta execução",
    type=["csv", "xlsx"],
    key="upload_base"
)

BASE_EXECUCAO = BASE.copy()

if upload_base:
    try:
        if upload_base.name.lower().endswith(".csv"):
            BASE_EXECUCAO = pd.read_csv(
                upload_base,
                sep=";",
                dtype=str,
                encoding="utf-8-sig"
            ).fillna("")
        else:
            BASE_EXECUCAO = pd.read_excel(
                upload_base,
                dtype=str
            ).fillna("")

        for col in COLUNAS_BASE:
            if col not in BASE_EXECUCAO.columns:
                BASE_EXECUCAO[col] = ""

        BASE_EXECUCAO = BASE_EXECUCAO[COLUNAS_BASE]

        # A variável global é usada pelas funções de busca.
        BASE = BASE_EXECUCAO

        st.success(
            f"Base temporária carregada com {len(BASE)} regra(s)."
        )
    except Exception as exc:
        st.error(f"Erro ao carregar a base: {exc}")

# ============================================================
# EXECUÇÃO
# ============================================================

if arquivos:
    st.divider()
    st.subheader("🔎 Auditoria")

    todos_resultados = []
    todos_erros = []

    barra = st.progress(0)

    for i, arquivo in enumerate(arquivos):
        resultados, erros = processar_xml(arquivo)
        todos_resultados.extend(resultados)
        todos_erros.extend(erros)
        barra.progress((i + 1) / len(arquivos))

    if todos_resultados:
        df = pd.DataFrame(todos_resultados)
        df_erros = pd.DataFrame(todos_erros)

        if df_erros.empty:
            df_erros = pd.DataFrame(
                columns=[
                    "Arquivo", "NF-e", "Item", "Produto", "NCM",
                    "Tipo de Erro", "Gravidade", "ERRO ENCONTRADO",
                    "Regra/Referência", "Legislação", "Fundamento Legal"
                ]
            )

        qtd_erros = len(df_erros)
        qtd_produtos_com_erro = (
            df[df["Status"] == "❌ ERRO ENCONTRADO"].shape[0]
        )
        qtd_sem_regra = (
            df[df["Status"] == "⚠️ SEM REGRA TRIBUTÁRIA"].shape[0]
        )
        qtd_conforme = (
            df[df["Status"] == "✅ CONFORME COM A BASE"].shape[0]
        )

        st.success(
            f"Auditoria concluída: {len(arquivos)} XML(s) e "
            f"{len(df)} item(ns) analisado(s)."
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Itens analisados", len(df))
        c2.metric("🚨 Itens com erro", qtd_produtos_com_erro)
        c3.metric("⚠️ Sem regra", qtd_sem_regra)
        c4.metric("✅ Conforme", qtd_conforme)

        aba_geral, aba_erros, aba_sem_regra, aba_base = st.tabs([
            "📋 TODOS OS PRODUTOS",
            "⚠️ ERROS ENCONTRADOS",
            "❓ SEM REGRA TRIBUTÁRIA",
            "📚 BASE TRIBUTÁRIA"
        ])

        with aba_geral:
            st.dataframe(
                df,
                use_container_width=True,
                height=600
            )

        with aba_erros:
            st.subheader("🚨 Produtos que apresentam erro")

            if df_erros.empty:
                st.success(
                    "Nenhum erro automático foi encontrado nos XMLs."
                )
            else:
                st.error(
                    f"{qtd_erros} divergência(s) encontrada(s)."
                )

                # Filtro de gravidade
                gravidades = sorted(
                    df_erros["Gravidade"].dropna().unique().tolist()
                )

                selecionadas = st.multiselect(
                    "Filtrar gravidade",
                    gravidades,
                    default=gravidades
                )

                exibicao = df_erros[
                    df_erros["Gravidade"].isin(selecionadas)
                ]

                st.dataframe(
                    exibicao,
                    use_container_width=True,
                    height=600
                )

                st.download_button(
                    "⬇️ Baixar somente os erros em CSV",
                    data=exibicao.to_csv(
                        index=False,
                        sep=";",
                        encoding="utf-8-sig"
                    ).encode("utf-8-sig"),
                    file_name="erros_encontrados.csv",
                    mime="text/csv"
                )

        with aba_sem_regra:
            sem_regra = df[
                df["Status"] == "⚠️ SEM REGRA TRIBUTÁRIA"
            ]

            if sem_regra.empty:
                st.success(
                    "Todos os itens possuem regra na base."
                )
            else:
                st.warning(
                    f"{len(sem_regra)} item(ns) não possuem "
                    "regra tributária cadastrada."
                )
                st.dataframe(
                    sem_regra[
                        [
                            "Arquivo", "NF-e", "Produto", "NCM",
                            "CEST", "CFOP", "UF Origem", "UF Destino"
                        ]
                    ].drop_duplicates(),
                    use_container_width=True
                )

        with aba_base:
            if BASE.empty:
                st.info(
                    "A base ainda está vazia. Você pode carregar "
                    "um CSV/XLSX ou alimentar base_tributaria.csv."
                )
            else:
                st.dataframe(
                    BASE,
                    use_container_width=True,
                    height=600
                )

        # ========================================================
        # EXPORTAÇÃO EXCEL
        # ========================================================

        st.divider()
        st.subheader("📥 Exportar auditoria")

        try:
            buffer = io.BytesIO()

            with pd.ExcelWriter(
                buffer,
                engine="openpyxl"
            ) as writer:
                df.to_excel(
                    writer,
                    index=False,
                    sheet_name="Todos_Produtos"
                )
                df_erros.to_excel(
                    writer,
                    index=False,
                    sheet_name="ERROS_ENCONTRADOS"
                )
                df[
                    df["Status"] == "⚠️ SEM REGRA TRIBUTÁRIA"
                ].to_excel(
                    writer,
                    index=False,
                    sheet_name="SEM_REGRA"
                )

            buffer.seek(0)

            st.download_button(
                "⬇️ BAIXAR AUDITORIA COMPLETA EM EXCEL",
                data=buffer.getvalue(),
                file_name=(
                    "auditoria_tributaria_"
                    + datetime.now().strftime("%Y%m%d_%H%M%S")
                    + ".xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                on_click="ignore"
            )

        except Exception as exc:
            st.warning(
                "Não foi possível gerar o Excel. "
                "Verifique se openpyxl está no requirements.txt. "
                f"Detalhe: {exc}"
            )

else:
    st.info(
        "👆 Envie um ou mais XMLs para iniciar a auditoria."
    )

# ============================================================
# MODELO DE BASE
# ============================================================

st.divider()
st.subheader("🧾 Modelo da base tributária")

modelo = pd.DataFrame([{
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
}], columns=COLUNAS_BASE)

st.dataframe(modelo, use_container_width=True)

st.download_button(
    "⬇️ Baixar modelo CSV da base",
    data=modelo.to_csv(
        index=False,
        sep=";",
        encoding="utf-8-sig"
    ).encode("utf-8-sig"),
    file_name="modelo_base_tributaria.csv",
    mime="text/csv",
    on_click="ignore"
)

st.caption(
    "V2: erros estruturais são identificados diretamente no XML. "
    "Conclusões tributárias de ICMS-ST, monofásico, DIFAL etc. "
    "dependem da base legislativa cadastrada e não devem ser "
    "inventadas pelo sistema."
)
