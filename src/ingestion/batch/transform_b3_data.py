import sys
import time
import logging
from awsglue.job import Job
from awsglue.transforms import *
from pyspark.sql.window import Window
from pyspark.sql import functions as F
from awsglue.context import GlueContext
from pyspark.context import SparkContext
from awsglue.utils import getResolvedOptions
from pyspark.sql.types import DoubleType, IntegerType, DateType

# Configuração de Logging
start_time = time.time()
logger = logging.getLogger()
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Inicialização e Leitura de Parâmetros
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'JOB_DATE', 'TARGET_BUCKET'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

process_date_str = args['JOB_DATE']  # Formato esperado: YYYY-MM-DD
bucket_name = args['TARGET_BUCKET']  # Bucket S3 alvo para leitura e escrita
db_name = "default" # Banco de dados do Glue Catalog vms-fiap-tech-challenge-02-b3
table_name = "tb_ibov"

logger.info(f"Iniciando Tratamento de Dados da B3")
logger.info(f"\tData de Referência: {process_date_str}")
logger.info(f"\tBucket Alvo: {bucket_name}")

# Leitura dos Dados nos últimos 7 dias

raw_path = f"s3://{bucket_name}/raw/"
df_raw = spark.read.option("basePath", raw_path).parquet(raw_path)
df_input = df_raw.withColumn("data_pregao", F.to_date(F.col("dt"), "yyyy-MM-dd"))
df_window_scope = df_input.filter(
    (F.col("data_pregao") <= F.lit(process_date_str)) & 
    (F.col("data_pregao") >= F.date_sub(F.lit(process_date_str), 6))
)

# Transformações
# De (Extraction) -> Para (Transformation)
# codigo          -> ticker
# acao            -> nome_empresa
# tipo            -> tipo_acao
# qtd_teorica     -> qtd_teorica (cast)
# participacao    -> percentual_part

df_renamed = df_window_scope \
    .withColumnRenamed("codigo", "ticker") \
    .withColumnRenamed("acao", "nome_empresa") \
    .withColumnRenamed("tipo", "tipo_acao") \
    .withColumnRenamed("participacao", "percentual_part") \
    .withColumn("percentual_part", F.col("percentual_part").cast(DoubleType())) \
    .withColumn("qtd_teorica", F.col("qtd_teorica").cast(IntegerType()))
### Janela para Cálculos por Ativo ordenado por Data
w_spec = Window.partitionBy("ticker").orderBy("data_pregao").rowsBetween(-6, 0)

### Média Móvel e Volatilidade

"""
Média Móvel
    A Média Móvel é uma técnica estatística usada para suavizar flutuações de curto prazo e destacar tendências ou ciclos de longo prazo.
    Imagine uma janela que se move um dia para frente a cada novo pregão. 
    Ela descarta o dado mais antigo (dia -7) e inclui o mais novo (hoje), recalculando a média.
    Dessa forma, um ruído ou evento pontual não impacta o valor daquele ativo.
Volatilidade
    A Volatilidade é uma medida de dispersão. 
    Ela indica o quanto o valor de um ativo varia em relação à sua própria média. 
    No mundo financeiro, volatilidade é sinônimo de Risco e Incerteza.
    Alta Volatilidade: Indica instabilidade. A ação está ganhando e perdendo relevância no índice muito rapidamente.
    Baixa Volatilidade: Indica estabilidade e previsibilidade.
"""


2. 
df_metrics = df_renamed.withColumn(
    "media_movel_part_7d", 
    F.avg("percentual_part").over(w_spec)
).withColumn(
    "volatilidade_part_7d", 
    F.stddev("percentual_part").over(w_spec)
)

### Agrupamento numérico, sumarização e soma
w_day_type = Window.partitionBy("data_pregao", "tipo_acao")

df_enriched = df_metrics.withColumn(
    "total_qtd_por_tipo", 
    F.sum("qtd_teorica").over(w_day_type)
).withColumn(
    "contagem_papeis_tipo",
    F.count("ticker").over(w_day_type)
)
## Filtragem final para a data de processamento
df_final = df_enriched.filter(F.col("data_pregao") == F.lit(process_date_str))

## Escrita e Catalogação 
output_path = f"s3://{bucket_name}/refined/"

logger.info(f"Gravando dados refinados em: {output_path}")
df_final.write \
    .mode("overwrite") \
    .partitionBy("data_pregao", "ticker") \
    .format("parquet") \
    .option("path", output_path) \
    .saveAsTable(f"{db_name}.{table_name}")

logger.info("Job de Transformação finalizado com sucesso.")

## Métricas e Sumário de Execução
qtd_output = df_final.count()
qtd_input_window = df_window_scope.count()
end_time = time.time()
elapsed_time = end_time - start_time
logger.info(f"""
============================================================
SUMÁRIO DE EXECUÇÃO DO JOB GLUE
============================================================
JOB NAME           : {args['JOB_NAME']}
STATUS             : SUCESSO
------------------------------------------------------------
MÉTRICAS DE NEGÓCIO:
Data Processada    : {process_date_str}
Total Tickers (Output) : {qtd_output}
Volume Histórico Lido  : {qtd_input_window} (Janela 7 dias)
------------------------------------------------------------
DESTINO:
Database Catalog   : {db_name}
Tabela             : {table_name}
Path S3            : {output_path}
------------------------------------------------------------
PERFORMANCE:
Tempo Total        : {elapsed_time:.2f} segundos
============================================================
""")

job.commit()