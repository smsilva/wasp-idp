"""The two STS calls the trust check needs, on the base credential or on an assumed role."""
import os

import boto3


def default_client(credentials: dict | None = None):
  """STS client on the base credential (environment variables from the Secret), or on assumed credentials."""
  keys = {}
  if credentials:
    keys = {
      "aws_access_key_id": credentials["AccessKeyId"],
      "aws_secret_access_key": credentials["SecretAccessKey"],
      "aws_session_token": credentials["SessionToken"],
    }
  return boto3.client("sts", region_name=os.environ.get("AWS_REGION", "us-east-1"), **keys)


class Sts:
  def __init__(self, client=default_client):
    self.client = client

  def caller_identity(self, credentials: dict | None = None) -> dict:
    return self.client(credentials).get_caller_identity()

  def assume_role(self, role_arn: str, session: str, external_id: str | None = None) -> dict:
    kwargs = {"RoleArn": role_arn, "RoleSessionName": session[:64], "DurationSeconds": 900}
    if external_id is not None:
      kwargs["ExternalId"] = external_id
    return self.client(None).assume_role(**kwargs)["Credentials"]
