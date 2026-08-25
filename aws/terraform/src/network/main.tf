locals {
  # Índices 0..n-1 = públicas; n..2n-1 = privadas. Determinístico e derivado do CIDR.
  public_subnets = [
    for index, az in var.availability_zones : {
      az         = az
      cidr_block = cidrsubnet(var.vpc_cidr, var.subnet_newbits, index)
    }
  ]

  private_subnets = [
    for index, az in var.availability_zones : {
      az         = az
      cidr_block = cidrsubnet(var.vpc_cidr, var.subnet_newbits, index + length(var.availability_zones))
    }
  ]
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "${var.name}-vpc" })
}

resource "aws_subnet" "public" {
  count = length(local.public_subnets)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public_subnets[count.index].cidr_block
  availability_zone       = local.public_subnets[count.index].az
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.name}-public-${local.public_subnets[count.index].az}"
    # Auto-discovery de subnet do AWS Load Balancer Controller. Inócuo no hub; obrigatório
    # na spoke, e o submódulo é o mesmo nos dois casos.
    "kubernetes.io/role/elb" = "1"
  })
}

resource "aws_subnet" "private" {
  count = length(local.private_subnets)

  vpc_id            = aws_vpc.this.id
  cidr_block        = local.private_subnets[count.index].cidr_block
  availability_zone = local.private_subnets[count.index].az

  tags = merge(var.tags, {
    Name                              = "${var.name}-private-${local.private_subnets[count.index].az}"
    "kubernetes.io/role/internal-elb" = "1"
  })
}
