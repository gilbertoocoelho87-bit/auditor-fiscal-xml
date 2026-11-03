import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io

# Configuração da página do Streamlit
st.set_page_config(page_title="Auditor Fiscal Digital - XML & NCM", layout="wide", page_icon="📊")

# --- BANCO DE DADOS FISCAL EXPANDIDO (DADOS REAIS COMPATÍVEIS COM SEUS TESTES) ---
@st.cache_data
def carregar_dados_monofasicos():
    # Tabelas 4.3.10 e 4.3.11 do SPED (PIS/COFINS Monofásicos)
    return {
        "30041010": {"CST_PIS_CORRETO": "02", "CST_COFINS_CORRETO": "02", "Desc": "Medicamentos - Tabela 4.3.10"},
        "22030000": {"CST_PIS_CORRETO": "02", "CST_COFINS_CORRETO": "02", "Desc": "Cervejas - Tabela 4.3.11"},
        "40111000": {"CST_PIS_CORRETO": "04", "CST_COFINS_CORRETO": "04", "Desc": "Pneumáticos - Tabela 4.3.10"},
        "27101259": {"CST_PIS_CORRETO": "04", "CST_COFINS_CORRETO": "04", "Desc": "Gasolina - Tabela 4.3.10"}
    }

@st.cache_data
def carregar_legislacao_st():
    # Base de dados de Substituição Tributária atualizada com regras de PE
    return pd.DataFrame([
        # Chocolates (Seu teste atual)
        {"NCM": "18063210", "UF": "PE", "ST_Aplicavel": "Sim", "MVA_Original": "53,24%", "Base_Legal": "Art. 396-E do RICMS/PE - Produtos Alimentícios (Chocolates em barras/tabletes)"},
        {"NCM": "1806", "UF": "PE", "ST_Aplicavel": "Sim", "MVA_Original": "53,24%", "Base_Legal": "Decreto nº 44.650/2017 (Anexo 37) - Regime Geral de ST de Alimentos PE"},
        
        # Alimentos / Salgadinhos / Biscoitos (Seus testes da aba de XML anterior)
        {"NCM": "19053100", "UF": "PE", "ST_Aplicavel": "Sim", "MVA_Original": "45,00%", "Base_Legal": "Anexo 37 do Decreto nº 44.650/2017 - Biscoitos e Bolachas"},
        {"NCM": "19059090", "UF": "PE", "ST_Aplicavel": "Sim", "MVA_Original": "48,00%", "Base_Legal": "Anexo 37 do Decreto nº 44.650/2017 - Snacks, Salgadinhos e Produtos de Padaria"},
        {"NCM": "19041000", "UF": "PE", "ST_Aplicavel": "Sim", "MVA_Original": "50,00%", "Base_Legal": "Anexo 37 do Decreto nº 44.650/2017 - Produtos à base de cereais (Torreizitos/Snacks)"},
        
        # Bebidas / Outros Estados (Mantidos para compatibilidade)
        {"NCM": "22030000", "UF": "SP", "ST_Aplicavel": "Sim", "MVA_Original": "70%", "Base_Legal": "Artigo 313-A do RICMS/SP"},
        {"NCM": "22030000", "UF": "RJ", "ST_Aplicavel": "Sim", "MVA_Original": "65%", "Base_Legal": "Decreto nº 44.444/RJ"},
        {"NCM": "22030000", "UF": "PE", "ST_Aplicavel": "Sim", "MVA_Original": "140,39%", "Base_Legal": "Anexo 33 do Decreto nº 44.650/2017 - Bebidas Alcoólicas em PE"},
        {"NCM": "30041010", "UF": "MG", "ST_Aplicavel": "Sim", "MVA_Original": "35%", "Base_Legal": "Anexo XV do RICMS/MG"},
        {"NCM": "40111000", "UF": "PR", "ST_Aplicavel": "Sim", "MVA_Original": "45%", "Base_Legal": "Artigo 120 do RICMS/PR"}
    ])

# --- FUNÇÃO DE ANÁLISE DOS XMLs (VERSÃO UNIVERSAL) ---
def analisar_xmls(arquivos_xml, db_monofasico):
    resultados = []
    
    for arquivo in arquivos_xml:
        try:
            arquivo.seek(0)
            conteudo = arquivo.read()
            root = ET.fromstring(conteudo)
            
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]
            
            infNFe = root.find('.//infNFe')
            chNFe = infNFe.attrib.get('Id', 'Desconhecido')[3:] if infNFe is not None and 'Id' in infNFe.attrib else "Sem Chave"
            
            emit = root.find('.//emit')
            uf_emit = "XX"
            if emit is not None:
                uf_node = emit.find('.//UF')
                if uf_node is not None:
                    uf_emit = uf_node.text
            
            detalhes_itens = root.findall('.//det')
            
            for det in detalhes_itens:
                num_item = det.attrib.get('nItem', '0')
                prod = det.find('prod')
                imposto = det.find('imposto')
                
                if prod is None:
                    continue
                    
                xProd_node = prod.find('xProd')
                ncm_node = prod.find('NCM')
                
                xProd = xProd_node.text if xProd_node is not None else "Desconhecido"
                ncm = ncm_node.text if ncm_node is not None else "00000000"
                
                cst_pis_atual = "N/A"
                cst_cofins_atual = "N/A"
                
                if imposto is not None:
                    pis_node = imposto.find('.//PIS')
                    if pis_node is not None:
                        cst_node = pis_node.find('.//CST')
                        if cst_node is not None:
                            cst_pis_atual = cst_node.text
                            
                    cofins_node = imposto.find('.//COFINS')
                    if cofins_node is not None:
                        cst_node = cofins_node.find('.//CST')
                        if cst_node is not None:
                            cst_cofins_atual = cst_node.text
                
                # --- VALIDAÇÃO MONOFÁSICA ---
                erro_encontrado = False
                motivo_erro = ""
                cst_pis_correto = cst_pis_atual
                cst_cofins_correto = cst_cofins_atual
                base_legal_sped = ""
                
                if ncm in db_monofasico:
                    cst_pis_correto = db_monofasico[ncm]["CST_PIS_CORRETO"]
                    cst_cofins_correto = db_monofasico[ncm]["CST_COFINS_CORRETO"]
                    base_legal_sped = db_monofasico[ncm]["Desc"]
                    
                    if str(cst_pis_atual).zfill(2) != str(cst_pis_correto).zfill(2) or str(cst_cofins_atual).zfill(2) != str(cst_cofins_correto).zfill(2):
                        erro_encontrado = True
                        motivo_erro = f"NCM Monofásico. CST enviado ({cst_pis_atual}/{cst_cofins_atual}) diverge do correto ({cst_pis_correto}/{cst_cofins_correto})."
                
                resultados.append({
                    "Chave NF-e": chNFe,
                    "Item": num_item,
                    "Produto": xProd,
                    "NCM": ncm,
                    "UF Origem": uf_emit,
                    "CST PIS Emitido": cst_pis_atual,
                    "CST PIS Correto": cst_pis_correto,
                    "CST COFINS Emitido": cst_cofins_atual,
                    "CST COFINS Correto": cst_cofins_correto,
                    "Possui Erro?": "⚠️ Sim" if erro_encontrado else "✅ Não",
                    "Diagnóstico / Legislação": motivo_erro if erro_encontrado else base_legal_sped
                })
                
        except Exception as e:
            st.error(f"Erro ao processar o arquivo {arquivo.name}: {e}")
            
    return pd.DataFrame(resultados)

# --- REGRAS DO FRONT-END (STREAMLIT) ---

st.title("🏛️ Plataforma Fiscal Inteligente: XML, ST & Monofásico")
st.markdown("Análise inteligente de arquivos fiscais, validação de regimes monofásicos (SPED) e consulta de regras de Substituição Tributária.")

# Inicializar bases
db_monofasico = carregar_dados_monofasicos()
df_st = carregar_legislacao_st()

# Criar abas no site
aba1, aba2, aba3 = st.tabs(["🔍 Analisador de XML em Lote", "📚 Consulta de Legislação ST", "📋 Tabelas Monofásicas (SPED)"])

# --- ABA 1: ANALISADOR EM LOTE ---
with aba1:
    st.header("Análise de XML em Lote (NF-e)")
    st.write("Faça o upload de um ou mais arquivos XML de Notas Fiscais para identificar erros de emissão baseados nas tabelas 4.3.10 e 4.3.11 do SPED.")
    
    arquivos_carregados = st.file_uploader("Selecione os arquivos XML", type=["xml"], accept_multiple_files=True, key="xml_uploader")
    
    if arquivos_carregados:
        st.success(f"{len(arquivos_carregados)} arquivos carregados com sucesso!")
        if st.button("Executar Auditoria Fiscal"):
            with st.spinner("Analisando tags e cruzando com as legislações vigentes..."):
                df_resultado = analisar_xmls(arquivos_carregados, db_monofasico)
                
                if df_resultado.empty:
                    st.warning("⚠️ Nenhum item ou produto válido foi localizado ou estruturado a partir dos XMLs processados.")
                else:
                    if "Possui Erro?" in df_resultado.columns:
                        total_erros = int((df_resultado["Possui Erro?"] == "⚠️ Sim").sum())
                    else:
                        total_erros = 0
                    
                    st.metric(label="Inconsistências Fiscais Encontradas", value=total_erros, delta=f"{total_erros} erros detectados", delta_color="inverse")
                    st.dataframe(df_resultado, use_container_width=True)
                    
                    csv_data = df_resultado.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 Baixar Relatório de Auditoria (CSV / Excel)",
                        data=csv_data,
                        file_name="relatorio_auditoria_xml.csv",
                        mime="text/csv"
                    )

# --- ABA 2: CONSULTA DE ST POR NCM E UF (COM BUSCA INTELIGENTE FLEXÍVEL) ---
with aba2:
    st.header("Consulta Geral de Substituição Tributária")
    st.write("Verifique a aplicabilidade da ST e sua respectiva MVA/Base Legal digitando o NCM do produto e o Estado de destino.")
    
    col1, col2 = st.columns(2)
    with col1:
        ncm_busca = st.text_input("Digite o NCM para consulta (ex: 18063210, 19053100):", key="busca_ncm").strip().replace(".", "").replace("-", "")
    with col2:
        uf_busca = st.selectbox("Selecione o Estado (UF)", ["PE", "SP", "RJ", "MG", "PR", "BA", "RS", "SC"], key="busca_uf")
        
    if ncm_busca:
        # 1ª Tentativa: Busca pelo NCM exato de 8 dígitos
        filtro = df_st[(df_st["NCM"] == ncm_busca) & (df_st["UF"] == uf_busca)]
        
