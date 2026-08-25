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

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name}-igw" })
}

resource "aws_eip" "nat" {
  count = var.enable_nat_gateway ? 1 : 0

  domain = "vpc"

  tags = merge(var.tags, { Name = "${var.name}-nat-eip" })
}

resource "aws_nat_gateway" "this" {
  count = var.enable_nat_gateway ? 1 : 0

  allocation_id = aws_eip.nat[0].id
  # Subnet PÚBLICA: numa privada o NAT não alcança o IGW e não sai tráfego.
  subnet_id = aws_subnet.public[0].id

  tags = merge(var.tags, { Name = "${var.name}-nat" })

  # A AWS exige o IGW anexado antes de alocar o NAT.
  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name}-rt-public" })
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name}-rt-private" })
}

resource "aws_route" "private_default" {
  count = var.enable_nat_gateway ? 1 : 0

  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
