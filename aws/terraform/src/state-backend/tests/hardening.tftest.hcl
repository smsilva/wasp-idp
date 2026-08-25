mock_provider "aws" {}

variables {
  bucket_name = "test-tfstate-bucket"
}

run "versionamento_ligado" {
  command = plan

  # Versionamento é o que permite recuperar um state corrompido por apply concorrente.
  assert {
    condition     = aws_s3_bucket_versioning.this.versioning_configuration[0].status == "Enabled"
    error_message = "versionamento do bucket de state deveria estar Enabled"
  }
}

run "acesso_publico_bloqueado_nas_quatro_dimensoes" {
  command = plan

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.this.block_public_acls,
      aws_s3_bucket_public_access_block.this.block_public_policy,
      aws_s3_bucket_public_access_block.this.ignore_public_acls,
      aws_s3_bucket_public_access_block.this.restrict_public_buckets,
    ])
    error_message = "as 4 chaves do public access block deveriam ser true"
  }
}

run "criptografia_em_repouso" {
  command = plan

  # `rule` é um SET no schema do provider — não indexável. E a contagem tem de ser
  # exatamente 1: `alltrue([])` é true, então um `for` sem checar tamanho passaria com
  # zero regras de criptografia.
  assert {
    condition = length([
      for rule in aws_s3_bucket_server_side_encryption_configuration.this.rule : rule
      if anytrue([
        for default in rule.apply_server_side_encryption_by_default :
        default.sse_algorithm == "AES256"
      ])
    ]) == 1
    error_message = "o bucket deveria ter exatamente uma regra de SSE-S3 (AES256) por default"
  }
}

run "acl_desabilitada" {
  command = plan

  assert {
    condition     = aws_s3_bucket_ownership_controls.this.rule[0].object_ownership == "BucketOwnerEnforced"
    error_message = "object ownership deveria ser BucketOwnerEnforced (ACLs desligadas)"
  }
}

run "nega_transporte_inseguro" {
  command = plan

  # A policy é montada com jsonencode() a partir de var.bucket_name — não de
  # aws_s3_bucket.this.arn — justamente para ser conhecida em tempo de plan e
  # portanto asseverável sob mock_provider.
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.this.policy).Statement[0].Effect == "Deny"
    error_message = "a policy deveria ter um statement Deny"
  }

  assert {
    condition     = jsondecode(aws_s3_bucket_policy.this.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "o Deny deveria ser condicionado a aws:SecureTransport false"
  }

  assert {
    condition = contains(
      jsondecode(aws_s3_bucket_policy.this.policy).Statement[0].Resource,
      "arn:aws:s3:::test-tfstate-bucket/*"
    )
    error_message = "a policy deveria cobrir os objetos do bucket, não só o bucket"
  }
}
