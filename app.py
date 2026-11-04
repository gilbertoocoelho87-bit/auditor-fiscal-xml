import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io

# Configuração da página para aproveitar melhor o espaço na tela
st.set_page_config(page_title="Auditor Fiscal XML", layout="wide", page_icon="📊")

# ==============================================================================
# 1. BASE TRIBUTÁRIA AMPLIADA (Comporta regras gerais e específicas)
# ==============================================================================
@st.cache_data
def carregar_base_tributaria():
    dados = [
        {
            "NCM": "62046900", "UF": "PE", "Descricao_NCM": "Vestuário e acessórios têxteis",
            "Regime_ICMS": "NORMAL", "Aliquota_Interna": "20,5%", "CFOP_Saida_Correto": "5102", "CST_PIS_Correto": "01",
            "Texto_Entrada": "CFOP Interno: 1102. Sujeito a eventual antecipação sem ST (Decreto nº 44.650/2017).",
            "Texto_Saida": "CFOP Interno: 5102. Produto não sujeito à Substituição Tributária em PE.",
            "PIS_COFINS_Regime": "Cumulativo (PIS: 0,65% | COFINS: 3,00%)", "IPI_Texto": "Alíquota: 0%.",
            "Alertas": "• Alíquota modal em PE é 20,5% (Lei 18.305/2023).", "Fundamentos": "• Lei nº 18.305/2023"
        },
        {
            "NCM": "30049099", "UF": "PE", "Descricao_NCM": "Medicamentos de uso humano",
            "Regime_ICMS": "SUBSTITUIÇÃO TRIBUTÁRIA", "Aliquota_Interna": "20,5%", "CFOP_Saida_Correto": "5405", "CST_PIS_Correto": "04",
            "Texto_Entrada": "CFOP Interno: 1403. Retido por Substituição Tributária.",
            "Texto_Saida": "CFOP Interno: 5405. Venda de produto com ICMS ST já retido anteriormente.",
            "PIS_COFINS_Regime": "Monofásico (CST 04 - Tabela 4.3.10 do SPED)", "IPI_Texto": "Alíquota zero ou Isento.",
            "Alertas": "• Produto Monofásico. Exija o CST 04 para evitar bitributação.", "Fundamentos": "• Lei nº 10.147/2000"
        }
    ]
    return pd.DataFrame(dados)

base_tributaria = carregar_base_tributaria()

# ==============================================================================
# 2. FUNÇÃO DE EXTRAÇÃO DE DADOS DO XML (Lê qualquer NF-e)
# ==============================================================================
def processar_arquivo_xml(conteudo_xml, nome_arquivo):
    try:
        tree = ET.parse(io.BytesIO(conteudo_xml))
        root = tree.getroot()
        ns = {'ns': 'http://portalfiscal.inf.br'}
        
        # Identifica a UF do destinatário da nota
        dest_uf = root.find('.//ns:dest/ns:enderDest/ns:UF', ns)
        uf_destino = dest_uf.text if dest_uf is not None else "PE"
        
        produtos = []
        for det in root.findall('.//ns:det', ns):
            n_item = det.attrib.get('nItem')
            prod = det.find('ns:prod', ns)
            
            c_prod = prod.find('ns:cProd', ns).text
            x_prod = prod.find('ns:xProd', ns).text
            ncm = prod.find('ns:NCM', ns).text
            cfop_emitido = prod.find('ns:CFOP', ns).text
            
            # Captura dinâmica do CST de PIS
            cst_pis = "01"
            pis_element = det.find('.//ns:PIS//ns:CST', ns)
            if pis_element is not None:
                cst_pis = pis_element.text
                
            # Captura dinâmica do CST de ICMS para ajudar na análise geral
            cst_icms = "000"
            icms_element = det.find('.//ns:ICMS//ns:CST', ns)
            if icms_element is not None:
                cst_icms = icms_element.text
            else:
                # Trata regime do Simples Nacional (CSOSN)
                csosn_element = det.find('.//ns:ICMS//ns:CSOSN', ns)
                if csosn_element is not None:
                    cst_icms = csosn_element.text
                
            produtos.append({
                "Arquivo": nome_arquivo, "Item": n_item, "Código": c_prod, "Descrição": x_prod,
                "NCM": ncm, "CFOP_Emitido": cfop_emitido, "CST_PIS_Emitido": cst_pis,
                "CST_ICMS_Emitido": cst_icms, "UF_Destino": uf_destino
            })
        return produtos
    except Exception as e:
        st.error(f"Erro ao ler o arquivo {nome_arquivo}: {e}")
        return []

# ==============================================================================
# 3. INTERFACE TELA DO STREAMLIT
# ==============================================================================
st.title("🛡️ Auditor Fiscal de XML - PIS/COFINS & ST")
st.write("Faça o upload dos seus arquivos XML em lote para analisar divergências tributárias.")

arquivos_carregados = st.file_uploader("Arraste e solte seus arquivos XML da NF-e aqui", type=["xml"], accept_multiple_files=True)

if arquivos_carregados:
    todos_produtos = []
    
    for arquivo in arquivos_carregados:
        conteudo = arquivo.read()
        dados_itens = processar_arquivo_xml(conteudo, arquivo.name)
        if dados_itens:
            todos_produtos.extend(dados_itens)
        
    if todos_produtos:
        df_xml = pd.DataFrame(todos_produtos)
        
        # Cruzamento com a base regulatória
        df_auditado = pd.merge(df_xml, base_tributaria, on=["NCM", "UF_Destino"], how="left")
        
        st.info(f"📊 Total de itens processados no lote: {len(df_xml)}")
        
        # --- MOTOR DE REGRAS DINÂMICO ---
        erros_encontrados = []
        
        for idx, row in df_auditado.iterrows():
            motivo_erro = []
            
            # Se o NCM existe na nossa base cadastrada, valida de forma rígida
            if pd.notna(row['Regime_ICMS']):
                if row['CFOP_Emitido'] != row['CFOP_Saida_Correto']:
                    motivo_erro.append(f"CFOP Divergente (Emitido: {row['CFOP_Emitido']} | Esperado: {row['CFOP_Saida_Correto']})")
                if row['CST_PIS_Emitido'] != row['CST_PIS_Correto']:
                    motivo_erro.append(f"CST PIS Incorreto (Emitido: {row['CST_PIS_Emitido']} | Esperado: {row['CST_PIS_Correto']})")
            
            # SE O NCM NÃO ESTÁ CADASTRADO: Faz validação lógica estrutural
            else:
                # Inconsistência de ICMS ST genérica
                if row['CFOP_Emitido'] in ['5403', '5405'] and row['CST_ICMS_Emitido'] in ['00', '000']:
                    motivo_erro.append(f"Inconsistência ICMS ST: CFOP {row['CFOP_Emitido']} exige CST de ST, mas foi emitido CST {row['CST_ICMS_Emitido']}.")
                
                # Inconsistência de PIS Monofásico genérica
                if row['CST_PIS_Emitido'] == '04' and row['CFOP_Emitido'] == '5102':
                    motivo_erro.append("Alerta de Operação: Produto emitido com PIS Monofásico (CST 04), mas utilizando CFOP de tributação normal (5102).")
            
            if motivo_erro:
                erros_encontrados.append({
                    "Arquivo": row['Arquivo'], "Item": row['Item'], "Produto": row['Descrição'],
                    "NCM": row['NCM'], "UF": row['UF_Destino'], "Inconformidades": " / ".join(motivo_erro),
                    "index_auditado": idx
                })
        
        # --- EXIBIÇÃO DOS RESULTADOS ---
        st.subheader("🚨 Diagnósticos e Divergências de Emissão Encontradas")
        
        if erros_encontrados:
            df_erros = pd.DataFrame(erros_encontrados)
            st.dataframe(df_erros[["Arquivo", "Item", "Produto", "NCM", "UF", "Inconformidades"]], use_container_width=True)
            
            st.markdown("---")
            st.subheader("🔍 Ficha de Detalhes Legais (Visual Padrão Econet)")
            
            opcoes_selecao = {f"Item {r['Item']} - {r['Produto']} (NCM {r['NCM']})": r['index_auditado'] for r in erros_encontrados}
            item_selecionado = st.selectbox("Escolha um produto para ver as recomendações corretas:", list(opcoes_selecao.keys()))
            
            idx_escolhido = opcoes_selecao[item_selecionado]
            dados_item = df_auditado.loc[idx_escolhido]
            
            if pd.isna(dados_item['Regime_ICMS']):
                st.warning(f"📋 Ficha Fiscal Gerada via Análise Lógica para o NCM: {dados_item['NCM']}")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("#### 📥 OPERAÇÃO DO PRODUTO")
                    st.write(f"**CFOP Atual Emitido:** {dados_item['CFOP_Emitido']}")
                    st.write(f"**CST ICMS:** {dados_item['CST_ICMS_Emitido']}")
                with col2:
                    st.markdown("#### 📦 IMPOSTOS FEDERAIS")
                    st.write(f"**CST PIS Emitido:** {dados_item['CST_PIS_Emitido']}")
                    st.write("Verifique as tabelas 4.3.10 e 4.3.11 do SPED para confirmar o enquadramento deste NCM no regime Monofásico.")
            else:
                st.markdown(f"### 📋 Ficha Fiscal Completa - NCM {dados_item['NCM']}")
                st.info(f"**Produto:** {dados_item['Descrição']} | **Classificação:** {dados_item['Descricao_NCM']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("#### 📥 ENTRADA")
                    st.write(dados_item['Texto_Entrada'])
                with col2:
                    st.markdown("#### 📤 SAÍDA")
                    st.write(dados_item['Texto_Saida'])
                    
                st.error(f"⚠️ **Alertas Tributários**\n\n{dados_item['Alertas']}")
        else:
            st.success("🎉 Análise em lote concluída! Nenhuma quebra de validação crítica encontrada nos seus XMLs.")
            st.subheader("Lista de Itens Lidos com Sucesso")
            st.dataframe(df_xml, use_container_width=True)
