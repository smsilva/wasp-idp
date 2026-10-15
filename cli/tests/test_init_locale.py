from wasp_platform.bootstrap import local


def test_init_writes_english_when_the_config_has_no_locale():
  values = local.cli_config({}, "http://issuer.test")
  assert values["locale"] == "en"
  assert values["issuer"] == "http://issuer.test" and values["client_id"] == local.CLI_CLIENT_ID


def test_init_keeps_a_locale_already_chosen():
  assert local.cli_config({"locale": "pt-BR"}, "http://issuer.test")["locale"] == "pt-BR"


def test_init_overwrites_the_control_plane_keys():
  values = local.cli_config({"api_url": "http://old", "hide_empty": True}, "http://issuer.test")
  assert values["api_url"] == local.API_URL and values["hide_empty"] is True
