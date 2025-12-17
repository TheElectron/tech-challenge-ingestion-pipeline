provider "aws" {
  region = var.aws_region
}

# ==============================================================================
# 1. VARIÁVEIS E LOCALS
# ==============================================================================
variable "aws_region" {
  default = "us-east-1"
}

variable "project_name" {
  default = "b3-data-pipeline"
}

variable "env" {
  default = "dev"
}

locals {
  bucket_name = "${var.project_name}-${var.env}-${random_id.bucket_suffix.hex}"
  tags = {
    Project     = var.project_name
    Environment = var.env
    ManagedBy   = "Terraform"
  }
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# ==============================================================================
# 2. STORAGE (S3) - Data Lake
# ==============================================================================
resource "aws_s3_bucket" "datalake" {
  bucket = local.bucket_name
  tags   = local.tags
}

# Bloqueio de acesso público (Segurança)
resource "aws_s3_bucket_public_access_block" "datalake" {
  bucket = aws_s3_bucket.datalake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Criação das "pastas" iniciais (Placeholders)
resource "aws_s3_object" "folders" {
  for_each = toset(["raw/", "refined/", "scripts/", "temp/"])
  bucket   = aws_s3_bucket.datalake.id
  key      = each.value
  source   = "/dev/null" # Truque para criar pasta vazia
}

# ==============================================================================
# 3. GLUE CATALOG & JOB (Requisitos 5, 6, 7)
# ==============================================================================

# Banco de dados no Glue Catalog
resource "aws_glue_catalog_database" "b3_database" {
  name = "b3_market_data_${var.env}"
}

# Role do IAM para o Glue
resource "aws_iam_role" "glue_role" {
  name = "${var.project_name}-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
    }]
  })
}

# Permissões do Glue (S3 + CloudWatch + Glue Service)
resource "aws_iam_policy" "glue_policy" {
  name = "${var.project_name}-glue-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
        Resource = [
          aws_s3_bucket.datalake.arn,
          "${aws_s3_bucket.datalake.arn}/*"
        ]
      },
      {
        Effect = "Allow",
        Action = ["glue:*", "athena:*", "s3:GetBucketLocation", "logs:*"],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_attach" {
  role       = aws_iam_role.glue_role.name
  policy_arn = aws_iam_policy.glue_policy.arn
}

# Definição do Job Glue (Configurado para rodar script Visual/Spark)
resource "aws_glue_job" "b3_etl_visual" {
  name     = "b3-etl-visual-job"
  role_arn = aws_iam_role.glue_role.arn
  glue_version = "4.0"
  worker_type  = "G.1X"
  number_of_workers = 2

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.datalake.bucket}/scripts/b3_visual_etl.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.datalake.bucket}/temp/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--datalake_bucket"                  = aws_s3_bucket.datalake.bucket # Passando bucket como param
  }
}

# ==============================================================================
# 4. LAMBDA TRIGGER (Requisitos 3 e 4)
# ==============================================================================

# Compacta o código Python localmente para enviar pra AWS
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "../../src/lambdas/glue_trigger/lambda_function.py" # Caminho relativo à pasta terraform
  output_path = "lambda_trigger_payload.zip"
}

# Role do IAM para a Lambda
resource "aws_iam_role" "lambda_trigger_role" {
  name = "${var.project_name}-trigger-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# Permissão para a Lambda iniciar o Glue Job
resource "aws_iam_policy" "lambda_trigger_policy" {
  name = "${var.project_name}-trigger-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow",
        Action = ["glue:StartJobRun"],
        Resource = aws_glue_job.b3_etl_visual.arn
      },
      {
        Effect = "Allow",
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_trigger_role.name
  policy_arn = aws_iam_policy.lambda_trigger_policy.arn
}

# A Função Lambda
resource "aws_lambda_function" "glue_trigger" {
  filename      = data.archive_file.lambda_zip.output_path
  function_name = "${var.project_name}-trigger-fn"
  role          = aws_iam_role.lambda_trigger_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.9"
  timeout       = 60

  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      GLUE_JOB_NAME = aws_glue_job.b3_etl_visual.name
    }
  }
}

# Permissão para o S3 invocar esta Lambda
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.glue_trigger.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.datalake.arn
}

# ==============================================================================
# 5. S3 EVENT NOTIFICATION (O Gatilho Real)
# ==============================================================================
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.datalake.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.glue_trigger.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw/"
    filter_suffix       = ".parquet"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}

# ==============================================================================
# 6. OUTPUTS
# ==============================================================================
output "s3_bucket_name" {
  value = aws_s3_bucket.datalake.id
}

output "glue_job_name" {
  value = aws_glue_job.b3_etl_visual.name
}