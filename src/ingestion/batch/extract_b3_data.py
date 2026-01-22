import io
import sys
import json
import boto3
import base64
import logging
import requests
import pandas as pd
from datetime import datetime
from awsglue.utils import getResolvedOptions

# Configuração de Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Leitura de Parâmetros
RAW_PREFIX = "raw"
INDEX_CODE = "IBOV"
try:
    args = getResolvedOptions(sys.argv, ['TARGET_BUCKET'])
    BUCKET_NAME = args['TARGET_BUCKET']
    logger.info(f"Target Bucket definido: {BUCKET_NAME}")
except Exception as e:
    logger.error("Parâmetro TARGET_BUCKET obrigatório não encontrado.")
    sys.exit(1)

# Funções Auxiliares

def get_b3_data(index_code="IBOV"):
    """
        Busca os dados da carteira teórica na API da B3.
    """
    logger.info(f"Iniciando extração para o índice: {index_code}")
    page_num = 1
    all_data = []
    base_url = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/"
    while True:
        try:
            params = {
                "language": "pt-br",
                "pageNumber": page_num,
                "pageSize": 100,
                "index": index_code,
                "segment": "1"
            }
            params_json = json.dumps(params)
            params_b64 = base64.b64encode(params_json.encode("ascii")).decode("ascii")
            target_url = f"{base_url}{params_b64}"
            response = requests.get(target_url, timeout=30)
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])
            if not results:
                break
            all_data.extend(results)
            logger.info(f"Página {page_num} processada. Total acumulado: {len(all_data)} registros.")
            total_pages = data.get('page', {}).get('totalPages', 1)
            if page_num >= total_pages:
                break
            page_num += 1
        except Exception as e:
            logger.error(f"Erro ao processar a página {page_num}: {str(e)}")
            raise e
    df = pd.DataFrame(all_data)
    if not df.empty:
        df = df[['cod', 'asset', 'type', 'part', 'theoricalQty']]
        df.columns = ['codigo', 'acao', 'tipo', 'participacao', 'qtd_teorica']
    return df


def clean_daily_partition(bucket, prefix, partition_date):
    """
        Verifica se existem arquivos na partição do dia e os remove.
        Garante a idempotência do processo (Overwrite logic).
    """
    s3_client = boto3.client('s3')
    target_prefix = f"{prefix}/dt={partition_date}/"
    logger.info(f"Verificando existência de dados antigos em: s3://{bucket}/{target_prefix}")
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=target_prefix)
    if 'Contents' in response:
        objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
        if objects_to_delete:
            logger.info(f"Encontrados {len(objects_to_delete)} arquivos antigos. Removendo...")
            s3_client.delete_objects(
                Bucket=bucket,
                Delete={'Objects': objects_to_delete}
            )
            logger.info("Partição limpa com sucesso.")
    else:
        logger.info("Nenhum dado antigo encontrado. Partição limpa.")
    return True

def upload_raw_to_s3(df, bucket, prefix):
    """
    Armazena os dados brutos na camada RAW, no formato Parquet,
    após limpar a partição do dia.
    """
    if df.empty:
        logger.warning("Nenhum dado foi encontrado para upload.")
        return
    now = datetime.now()
    partition_date = now.strftime("%Y-%m-%d")
    clean_daily_partition(bucket, prefix, partition_date)
    file_name = f"ibov_{now.strftime('%H%M%S')}.parquet"
    s3_key = f"{prefix}/dt={partition_date}/{file_name}"
    s3_path_full = f"s3://{bucket}/{s3_key}"
    logger.info(f"Iniciando upload para: {s3_path_full}")
    out_buffer = io.BytesIO()
    df.to_parquet(out_buffer, index=False, compression='snappy', engine='pyarrow')
    s3_client = boto3.client('s3')
    s3_client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=out_buffer.getvalue()
    )
    logger.info("Upload concluído com sucesso!")

# Método Principal
if __name__ == "__main__":
    try:
        df_ibov = get_b3_data(INDEX_CODE)
        upload_raw_to_s3(df_ibov, BUCKET_NAME, RAW_PREFIX)
        logger.info("Job de Extração finalizado com sucesso.")
    except Exception as e:
        logger.error(f"Falha Crítica no Job: {str(e)}")
        sys.exit(1)
    