import json
import boto3
import urllib.parse
import os
import logging

# Configuração de Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Configurações ---
# Nome do Job de Transformação (definido via Variável de Ambiente para flexibilidade)
GLUE_JOB_NAME = os.environ.get('GLUE_JOB_NAME', 'transform_b3_data')

def lambda_handler(event, context):
    """
    Função acionada automaticamente quando um arquivo é salvo no S3.
    Ela identifica a data da partição e dispara o Job Glue de Transformação.
    """
    glue_client = boto3.client('glue')
    
    logger.info("Recebendo evento do S3...")
    
    # O evento pode conter múltiplos registros (embora raro em triggers unitários)
    for record in event['Records']:
        try:
            # 1. Extração de Metadados do Evento
            bucket_name = record['s3']['bucket']['name']
            
            # Decodifica o nome do arquivo (ex: converte %20 para espaço, caso exista)
            file_key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            
            logger.info(f"Arquivo detectado: s3://{bucket_name}/{file_key}")
            
            # 2. Validação de Caminho e Extração de Data
            # O padrão esperado é: raw/dt=YYYY-MM-DD/nome_arquivo.parquet
            if "raw/dt=" not in file_key:
                logger.info("Arquivo ignorado: Não pertence à estrutura de partição 'raw/dt='.")
                continue

            # Quebra o caminho pelas barras '/'
            # Ex: ['raw', 'dt=2026-01-17', 'ibov_data.parquet']
            path_parts = file_key.split('/')
            
            # Encontra a parte que define a data
            partition_part = next((p for p in path_parts if p.startswith('dt=')), None)
            
            if not partition_part:
                logger.error(f"Erro: Não foi possível extrair a data do caminho: {file_key}")
                continue
            
            # Extrai apenas o valor da data (remove o 'dt=')
            job_date = partition_part.split('=')[1]
            
            logger.info(f"Disparando Job '{GLUE_JOB_NAME}' para a data: {job_date}")
            
            # 3. Disparo do Job Glue (StartJobRun)
            # Passamos a data e o bucket como argumentos para o script PySpark
            response = glue_client.start_job_run(
                JobName=GLUE_JOB_NAME,
                Arguments={
                    '--JOB_DATE': job_date,           # Argumento vital para o ETL
                    '--TARGET_BUCKET': bucket_name    # Mantém consistência de ambiente
                }
            )
            
            job_run_id = response['JobRunId']
            logger.info(f"Job Glue iniciado com sucesso! Run ID: {job_run_id}")
            
        except Exception as e:
            logger.error(f"Erro fatal ao processar o registro: {str(e)}")
            # Relançar o erro faz o S3 tentar novamente (retries), dependendo da config
            raise e

    return {
        'statusCode': 200,
        'body': json.dumps('Trigger processado com sucesso.')
    }