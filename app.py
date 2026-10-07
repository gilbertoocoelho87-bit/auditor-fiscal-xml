import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io

# Configuração da página do site
st.set_page_config(page_title="Auditor Fiscal de Divergências", layout="wide")

st.title("📊 Auditor PGDAS - Identificador de Notas Incorretas")
st.write("Análise em lote com aba exclusiva para apontar quais XMLs vieram preenchidos de forma errada.")

# --- COMPONENTE DE CARREGAMENTO (IMPORTAÇÃO DO XML) ---
uploaded_files = st.file_uploader("📂 Arraste e solte seus XMLs de Notas Fiscais aqui", type=["xml"], accept_multiple_files=True)

# --- BASE DE LEGISLAÇÃO DE ICMS-ST (TODOS OS ESTADOS) ---
MATRIZ_ESTADUAL_ICMS = {
    "11": {"UF": "RO", "Construcao_ST": "Anexo VI do RICMS/RO", "Medicamento_ST": "Anexo VI (Medicamentos) do RICMS/RO"},
    "12": {"UF": "AC", "Construcao_ST": "Anexo IV do RICMS/AC", "Medicamento_ST": "Anexo IV (Farmacêuticos) do RICMS/AC"},
    "13": {"UF": "AM", "Construcao_ST": "Anexo II do RICMS/AM", "Medicamento_ST": "Anexo II (Farmacêuticos) do RICMS/AM"},
    "14": {"UF": "RR", "Construcao_ST": "RICMS/RR Decreto 4.335-E/01", "Medicamento_ST": "Regime de ST de Medicamentos - RICMS/RR"},
    "15": {"UF": "PA", "Construcao_ST": "Anexo I do RICMS/PA", "Medicamento_ST": "Anexo I (Fármacos) do RICMS/PA"},
    "16": {"UF": "AP", "Construcao_ST": "Decreto nº 2.269/1998", "Medicamento_ST": "Anexo Único (Medicamentos) - RICMS/AP"},
    "17": {"UF": "TO", "Construcao_ST": "Decreto nº 2.912/2006", "Medicamento_ST": "Regulamento do ICMS/TO - Medicamentos"},
    "21": {"UF": "MA", "Construcao_ST": "Anexo 4.0 do RICMS/MA", "Medicamento_ST": "Anexo 4.0 (Medicamentos) - RICMS/MA"},
    "22": {"UF": "PI", "Construcao_ST": "Anexo V do RICMS/PI", "Medicamento_ST": "Anexo V (Setor Farmacêutico) do RICMS/PI"},
    "23": {"UF": "CE", "Construcao_ST": "Livro III do RICMS/CE", "Medicamento_ST": "Livro III (Produtos Farmacêuticos) do RICMS/CE"},
    "24": {"UF": "RN", "Construcao_ST": "Anexo 05 do RICMS/RN", "Medicamento_ST": "Anexo 05 (Medicamentos) - RICMS/RN"},
    "25": {"UF": "PB", "Construcao_ST": "Livro V do RICMS/PB", "Medicamento_ST": "Livro V (Medicamentos) do RICMS/PB"},
    "26": {"UF": "PE", "Construcao_ST": "Art. 381-A e Anexos 37/37-C do RICMS/PE", "Medicamento_ST": "Decreto Estadual nº 61.284/2026 (ST Medicamentos - RICMS/PE)"},
    "27": {"UF": "AL", "Construcao_ST": "Anexo X do RICMS/AL", "Medicamento_ST": "Anexo X (Produtos Farmacêuticos) do RICMS/AL"},
    "28": {"UF": "SE", "Construcao_ST": "Título IV do RICMS/SE", "Medicamento_ST": "Título IV (Medicamentos) do RICMS/SE"},
    "29": {"UF": "BA", "Construcao_ST": "Artigo 289 do RICMS/BA", "Medicamento_ST": "Artigo 289 (Fármacos e Medicamentos) do RICMS/BA"},
    "31": {"UF": "MG", "Construcao_ST": "Anexo VII, Parte 2 do RICMS/MG", "Medicamento_ST": "Anexo VII, Parte 2 (Produtos Farmacêuticos) - RICMS/MG"},
    "32": {"UF": "ES", "Construcao_ST": "Anexo V do RICMS/ES", "Medicamento_ST": "Anexo V (Medicamentos) do RICMS/ES"},
    "33": {"UF": "RJ", "Construcao_ST": "Livro II do RICMS/RJ", "Medicamento_ST": "Anexo I do Livro II (Medicamentos) - RICMS/RJ"},
    "35": {"UF": "SP", "Construcao_ST": "Artigo 313-Y do RICMS/SP", "Medicamento_ST": "Artigo 313-A (Produtos Farmacêuticos) do RICMS/SP"},
    "41": {"UF": "PR", "Construcao_ST": "Anexo IX do RICMS/PR", "Medicamento_ST": "Anexo IX (Seção XIV - Medicamentos) do RICMS/PR"},
    "42": {"UF": "SC", "Construcao_ST": "Anexo 3 do RICMS/SC", "Medicamento_ST": "Anexo 3 (Produtos Farmacêuticos) do RICMS/SC"},
    "43": {"UF": "RS", "Construcao_ST": "Livro III, Artigo 207 do RICMS/RS", "Medicamento_ST": "Livro III, Artigo 221 (Medicamentos) do RICMS/RS"},
    "50": {"UF": "MS", "Construcao_ST": "Anexo III do RICMS/MS", "Medicamento_ST": "Anexo III (Produtos Farmacêuticos) do MS"},
    "51": {"UF": "MT", "Construcao_ST": "Anexo X do RICMS/MT", "Medicamento_ST": "Anexo X (Medicamentos) do RICMS/MT"},
    "52": {"UF": "GO", "Construcao_ST": "Anexo VIII do RCTE/GO", "Medicamento_ST": "Anexo VIII (Produtos Farmacêuticos) do RCTE/GO"},
    "53": {"UF": "DF", "Construcao_ST": "Anexo IV do RICMS/DF", "Medicamento_ST": "Caderno I do Anexo IV (Medicamentos) do RICMS/DF"}
}

# --- FUNÇÃO DE AUDITORIA CRÍTICA DE XML ---
def auditoria_lote_divergencias(xml_files):
    todos_produtos = []
    
    for xml_file in xml_files:
        try:
            xml_data = xml_file.read()
            root = ET.fromstring(xml_data)
            
            # 1. Identificar a UF da Nota
            cod_uf = "35"
            for elem in root.iter():
                if elem.tag.endswith('cUF'):
                    cod_uf = elem.text
                    break
                    
            config_uf = MATRIZ_ESTADUAL_ICMS.get(cod_uf, {"UF": "BR", "Construcao_ST": "Regulamento Local", "Medicamento_ST": "Regulamento Local"})
            uf_nome = config_uf["UF"]
            
            # 2. Identificar o número da NF-e
            numero_nfe = "Não Encontrado"
            for elem in root.iter():
                if elem.tag.endswith('nNF'):
                    numero_nfe = elem.text
                    break
            
            # 3. Varrer os itens do XML e cruzar com as tags do fornecedor
            for det in root.iter():
                if det.tag.endswith('det'):
                    xProd = "Desconhecido"
                    ncm = ""
                    cst_xml = "00"
                    
                    for elem in det.iter():
                        if elem.tag.endswith('xProd'):
                            xProd = elem.text
                        if elem.tag.endswith('NCM'):
                            ncm = elem.text
                    
                    for elem in det.iter():
                        if elem.tag.endswith('CST') or elem.tag.endswith('CSOSN'):
                            cst_xml = elem.text
                            break
                    
                    grupo_4d = ncm[:4] if ncm else ""
                    
                    # --- CRITÉRIOS DE LEGISLAÇÃO VS XML ---
                    if grupo_4d in ["3002", "3003", "3004", "3005", "3006"] or ncm.startswith("40141000"):
                        regra_icms = "ST"
                        regra_pis_cofins = "MONOFÁSICO"
                        base_icms = config_uf["Medicamento_ST"]
                        base_federal = "Tabela 4.3.10 SPED (Cód. 102 - Fármacos / Lei nº 10.147/00)"
                        
                    elif grupo_4d in ["8708", "4011", "8407", "8408", "8409"]:
                        regra_icms = "NORMAL"
                        regra_pis_cofins = "MONOFÁSICO"
                        base_icms = f"Regime Regular / Alíquota Interna de {uf_nome}"
                        base_federal = "Tabela 4.3.10 SPED (Cód. 103 - Autopeças / Lei nº 10.485/02)"
                        
                    elif grupo_4d in ["2203", "2202"]:
                        regra_icms = "NORMAL"
                        regra_pis_cofins = "MONOFÁSICO"
                        base_icms = f"Regime Regular / Alíquota Interna de {uf_nome}"
                        base_federal = "Tabela 4.3.10 SPED (Cód. 104 - Bebidas / Lei nº 13.097/15)"
                        
                    elif grupo_4d in ["3917", "8481", "8536", "7307", "6910", "7412", "7308", "3214", "2523"]:
                        regra_icms = "ST"
                        regra_pis_cofins = "NORMAL"
                        base_icms = config_uf["Construcao_ST"]
                        base_federal = "Regime Geral (PIS/COFINS Não Monofásico)"
                        
                    else:
                        regra_icms = "NORMAL"
                        regra_pis_cofins = "NORMAL"
                        base_icms = f"Regime Comum / Alíquota Interna de {uf_nome}"
                        base_federal = "Regime Geral (PIS/COFINS Não Monofásico)"
                    
                    erros_detectados = []
                    if regra_icms == "ST" and cst_xml in ["00", "20", "40", "102", "400", "90"]:
                        erros_detectados.append(f"ICMS Errado (Veio CST {cst_xml} mas deveria ser ST)")
                    
                    status_auditoria = "CORRETO" if len(erros_detectados) == 0 else "INCORRETO"
                    detalhe_erro = " e ".join(erros_detectados) if erros_detectados else "Nenhuma divergência"
                    
                    todos_produtos.append({
                        "Nota No.": numero_nfe,
                        "UF": uf_nome,
                        "Produto": xProd,
                        "NCM": ncm,
                        "CST no XML": cst_xml,
                        "ICMS PGDAS (Correto)": regra_icms,
                        "PIS/COFINS PGDAS (Correto)": regra_pis_cofins,
                        "Status XML": status_auditoria,
                        "Divergência Encontrada": detalhe_erro,
                        "Base Legal Estadual (ICMS)": base_icms,
                        "Enquadramento SPED (Federal)": base_federal
                    })
        except Exception as e:
            st.error(f"Erro no processamento: {e}")
            
    if todos_produtos:
        return pd.DataFrame(todos_produtos)
    return None

# --- PROCESSAMENTO DOS RESULTADOS ---
if uploaded_files:
    df_final = auditoria_lote_divergencias(uploaded_files)
    
    if df_final is not None and not df_final.empty:
        st.success(f"✅ Auditoria de lote finalizada. {len(uploaded_files)} XML(s) checados.")
        
        # Criação das abas de visualização
        aba_geral, aba_incorretas = st.tabs(["📋 Todos os Produtos", "⚠️ NOTAS INCORRETAS / ERROS"])
        
        with aba_geral:
            st.write("### Painel Geral de Lançamento PGDAS-D")
            st.write(df_final.to_html(escape=False, index=False), unsafe_allow_html=True)
            
        with aba_incorretas:
            st.write("### 🚨 Notas Fiscais com Erro de Preenchimento no XML")
